import io
import json
import re
import uuid
from decimal import Decimal
from datetime import date
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, File, UploadFile, HTTPException, Query, Depends, Request
from fastapi.responses import StreamingResponse

from database import db
from ws_manager import manager as ws_manager
from modules.auth.dependencies import get_current_user, restrict_superadmin
from modules.audit.service import log_audit_action
from modules.forecast.engine import (
    sync_actuals_from_resume,
    clear_actuals_for_month,
    clear_all_actuals,
    invalidate_adjustment_cycles_for_year,
    purge_all_adjustment_cycles,
    sync_closed_years_into_history,
    generate_forecast,
)
from .config import get_mapping_config, save_mapping_config
from .mapper import SageBFCMapper
from .parser import SageBalanceParser
from .models import (
    TableauBFCResponse,
    TableauBFCSummary,
    LigneBudgetBFC,
    MappingStats, 
    ParseRequest,
    MonthlyDataSummary,
    MonthlyDataFull,
    MappingEntryBase,
    MappingEntryResponse,
    MappingConfigResponse
)

router = APIRouter(
    prefix="/sage-bfc",
    tags=["SAGE → BFC Parser"],
    responses={404: {"description": "Non trouvé"}},
    dependencies=[Depends(restrict_superadmin("sage_bfc"))],
)

# Stockage temporaire des tableaux générés (en production, utiliser Redis/DB)
_tableaux_cache = {}

_AGREGAT_ALIASES = {
    # clés internes
    "ca_brut": "ca_brut",
    "retrocessions": "retrocessions",
    "ca_net": "ca_net",
    "autres_produits": "autres_produits",
    "total_produits": "total_produits",
    "frais_personnel": "frais_personnel",
    "honoraires": "honoraires",
    "frais_commerciaux": "frais_commerciaux",
    "impots_taxes": "impots_taxes",
    "fonctionnement": "fonctionnement",
    "autres_charges": "autres_charges",
    "produits_financiers": "produits_financiers",
    "charges_financieres": "charges_financieres",
    "dotations": "dotations",
    "impot_societes": "impot_societes",
    "produits_exceptionnels": "produits_exceptionnels",
    "charges_exceptionnelles": "charges_exceptionnelles",
    "resultat_financier": "resultat_financier",
    "resultat_exceptionnel": "resultat_exceptionnel",
    "resultat_avant_impot": "resultat_avant_impot",
    "resultat_net": "resultat_net",
    # libellés courants
    "ca brut": "ca_brut",
    "retrocessions": "retrocessions",
    "ca net": "ca_net",
    "autres produits exploitation": "autres_produits",
    "frais personnel": "frais_personnel",
    "honoraires sous traitance": "honoraires",
    "frais commerciaux": "frais_commerciaux",
    "impots taxes": "impots_taxes",
    "fonctionnement courant": "fonctionnement",
    "autres charges": "autres_charges",
    "produits financiers": "produits_financiers",
    "charges financieres": "charges_financieres",
    "dotations amortissements": "dotations",
    "impot societes": "impot_societes",
    "produits exceptionnels": "produits_exceptionnels",
    "charges exceptionnelles": "charges_exceptionnelles",
}

_MAPPING_SECTIONS = [
    "mapping_chiffre_affaires",
    "mapping_retrocessions",
    "mapping_frais_personnel",
    "mapping_interco_frais",
    "mapping_honoraires",
    "mapping_frais_commerciaux",
    "mapping_impots",
    "mapping_fonctionnement",
    "mapping_autres_charges",
    "mapping_produits_exploitation",
    "mapping_produits_financiers",
    "mapping_charges_financieres",
    "mapping_dotations",
    "mapping_produits_exceptionnels",
    "mapping_charges_exceptionnelles",
    "mapping_impots_societes",
    "mapping_capex",
]

_CODE_COMPTE_RE = re.compile(r"^\d{5,7}[A-Z]?$")
_TYPE_ALLOWED = {"Produit", "Charge", "Actif"}
_SENS_ALLOWED = {"+", "-"}
_TYPE_CANONICAL = {
    "produit": "Produit",
    "charge": "Charge",
    "actif": "Actif",
}


def _normalize_agregat_name(value: str) -> str:
    key = " ".join(str(value).strip().lower().replace("_", " ").replace("-", " ").split())
    mapped = _AGREGAT_ALIASES.get(key)
    if not mapped:
        raise HTTPException(
            status_code=400,
            detail=f"Agrégat inconnu: '{value}'. Exemple: ca_brut, frais_personnel, resultat_net"
        )
    return mapped

def _validate_code_compte(code: str) -> None:
    if not code or not _CODE_COMPTE_RE.match(code.strip()):
        raise HTTPException(status_code=400, detail=f"Code compte invalide: '{code}'")

def _normalize_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return str(value).strip()

def _validate_mapping_entry(payload: MappingEntryBase) -> None:
    payload.code_compte = _normalize_str(payload.code_compte) or ""
    payload.libelle_sage = _normalize_str(payload.libelle_sage) or ""
    payload.categorie = _normalize_str(payload.categorie) or ""
    payload.agregat_bfc = _normalize_str(payload.agregat_bfc) or ""
    payload.sens = _normalize_str(payload.sens) or ""
    payload.type_ligne = _normalize_str(payload.type_ligne) or ""

    _validate_code_compte(payload.code_compte)
    if not payload.libelle_sage:
        raise HTTPException(status_code=400, detail="libelle_sage est obligatoire")
    if not payload.categorie:
        raise HTTPException(status_code=400, detail="categorie est obligatoire")
    if not payload.agregat_bfc:
        raise HTTPException(status_code=400, detail="agregat_bfc est obligatoire")

    if payload.sens not in _SENS_ALLOWED:
        raise HTTPException(status_code=400, detail="sens doit être '+' ou '-'")

    type_key = payload.type_ligne.lower()
    payload.type_ligne = _TYPE_CANONICAL.get(type_key, payload.type_ligne)
    if payload.type_ligne not in _TYPE_ALLOWED:
        raise HTTPException(status_code=400, detail="type doit être Produit, Charge ou Actif")

def _find_sections_for_code(config: Dict[str, Any], code_compte: str) -> List[str]:
    sections = []
    for section in _MAPPING_SECTIONS:
        if code_compte in config.get(section, {}):
            sections.append(section)
    return sections

def _entry_to_response(section: str, code: str, entry: Dict[str, Any]) -> MappingEntryResponse:
    merged = {"code_compte": code, **entry, "mapping_section": section}
    if "type" in merged:
        merged["type"] = merged.pop("type")
    return MappingEntryResponse(**merged)

def _validate_regles_agregation_payload(payload: Dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="regles_agregation doit être un objet")

    for key, rule in payload.items():
        if not isinstance(rule, dict):
            raise HTTPException(status_code=400, detail=f"Règle '{key}' invalide")

        formule = rule.get("formule")
        dependances = rule.get("dependances")

        if not isinstance(formule, str) or not formule.strip():
            raise HTTPException(status_code=400, detail=f"Règle '{key}': formule obligatoire")

        if dependances is not None:
            if not isinstance(dependances, list) or any(not isinstance(d, str) or not d.strip() for d in dependances):
                raise HTTPException(status_code=400, detail=f"Règle '{key}': dependances doit être une liste de chaînes")

def _validate_validations_interco_payload(payload: Dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="validations_interco doit être un objet")

    for key, rule in payload.items():
        if not isinstance(rule, dict):
            raise HTTPException(status_code=400, detail=f"Validation '{key}' invalide")

        if "taux" in rule and not isinstance(rule.get("taux"), (int, float)):
            raise HTTPException(status_code=400, detail=f"Validation '{key}': taux doit être numérique")

        if "taux_trimestriel" in rule:
            taux = rule.get("taux_trimestriel")
            if not isinstance(taux, list) or len(taux) != 4 or any(not isinstance(v, (int, float)) for v in taux):
                raise HTTPException(status_code=400, detail=f"Validation '{key}': taux_trimestriel doit être une liste de 4 nombres")

        for field in ["tolerance", "tolerance_absolue", "tolerance_relative"]:
            if field in rule and not isinstance(rule.get(field), (int, float)):
                raise HTTPException(status_code=400, detail=f"Validation '{key}': {field} doit être numérique")

        if "actif" in rule and not isinstance(rule.get("actif"), bool):
            raise HTTPException(status_code=400, detail=f"Validation '{key}': actif doit être booléen")

def _validate_correspondances_bpc_bfc_payload(payload: Dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="correspondances_bpc_bfc doit être un objet")

    code_re = re.compile(r"^[A-Z]\d{3,5}$")
    for key, value in payload.items():
        if not isinstance(key, str) or not key.strip():
            raise HTTPException(status_code=400, detail="Clé de correspondance invalide")
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(status_code=400, detail=f"Valeur vide pour la clé '{key}'")
        if not code_re.match(key.strip()):
            raise HTTPException(status_code=400, detail=f"Code BPC invalide: '{key}'")
        if not code_re.match(value.strip()):
            raise HTTPException(status_code=400, detail=f"Code BFC invalide: '{value}'")

def get_mapper():
    """Dependency pour obtenir le mapper"""
    config = get_mapping_config()
    return SageBFCMapper(config)

def get_parser(mapper: SageBFCMapper = Depends(get_mapper)):
    """Dependency pour obtenir le parser"""
    return SageBalanceParser(mapper)

@router.get("/mapping/sections")
async def get_mapping_sections():
    return {"sections": _MAPPING_SECTIONS}

@router.get("/mapping/meta")
async def get_mapping_meta():
    config = get_mapping_config()
    categories = set()
    agregats = set()
    for section in _MAPPING_SECTIONS:
        entries = config.get(section, {})
        for entry in entries.values():
            if not isinstance(entry, dict):
                continue
            categorie = entry.get("categorie")
            agregat = entry.get("agregat_bfc")
            if categorie:
                categories.add(categorie)
            if agregat:
                agregats.add(agregat)

    return {
        "sections": _MAPPING_SECTIONS,
        "categories": sorted(categories),
        "agregats": sorted(agregats),
    }

@router.get("/mapping/config", response_model=MappingConfigResponse)
async def get_mapping_config_full():
    config = get_mapping_config()
    mapping = {section: config.get(section, {}) for section in _MAPPING_SECTIONS}
    return MappingConfigResponse(
        version=config.get("version"),
        description=config.get("description"),
        metadata=config.get("metadata"),
        regles_agregation=config.get("regles_agregation"),
        validations_interco=config.get("validations_interco"),
        alertes_metier=config.get("alertes_metier"),
        correspondances_bpc_bfc=config.get("correspondances_bpc_bfc"),
        mapping=mapping,
    )

@router.put("/mapping/config")
async def put_mapping_config_full(
    payload: Dict[str, Any],
    request: Request,
    user: dict = Depends(get_current_user),
):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload JSON invalide")
    save_mapping_config(payload)
    ws_manager.broadcast("sage_bfc", "mapping_updated", {"scope": "full"})
    log_audit_action(
        user=user,
        action="update",
        module="sage_bfc_mapping",
        entity_type="mapping_config",
        entity_id=None,
        detail={"scope": "full"},
        request=request,
    )
    return {"status": "ok"}

@router.get("/mapping/entries")
async def list_mapping_entries(
    search: str = "",
    page: int = 1,
    page_size: int = 50,
):
    config = get_mapping_config()
    results: List[MappingEntryResponse] = []
    for section in _MAPPING_SECTIONS:
        entries = config.get(section, {})
        for code, entry in entries.items():
            if isinstance(entry, dict):
                results.append(_entry_to_response(section, code, entry))

    query = " ".join(str(search or "").lower().split())
    if query:
        filtered = []
        for entry in results:
            haystack = " ".join(
                str(v).lower()
                for v in [
                    entry.code_compte,
                    entry.libelle_sage,
                    entry.categorie,
                    entry.agregat_bfc,
                    entry.mapping_section,
                ]
                if v is not None
            )
            if query in haystack:
                filtered.append(entry)
        results = filtered

    results.sort(key=lambda e: (e.mapping_section or "", e.code_compte or ""))

    safe_page = max(1, int(page))
    safe_page_size = max(1, min(int(page_size), 500))
    total = len(results)
    pages = max(1, (total + safe_page_size - 1) // safe_page_size)
    if safe_page > pages:
        safe_page = pages

    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    items = results[start:end]

    return {
        "items": items,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "pages": pages,
    }

@router.post("/mapping/entries", response_model=MappingEntryResponse)
async def create_mapping_entry(
    payload: MappingEntryBase,
    request: Request,
    user: dict = Depends(get_current_user),
):
    _validate_mapping_entry(payload)
    if not payload.mapping_section:
        raise HTTPException(status_code=400, detail="mapping_section est obligatoire pour l'ajout")
    if payload.mapping_section not in _MAPPING_SECTIONS:
        raise HTTPException(status_code=400, detail="mapping_section invalide")

    config = get_mapping_config()
    existing_sections = _find_sections_for_code(config, payload.code_compte)
    if existing_sections:
        raise HTTPException(status_code=409, detail="Le code compte existe déjà dans le mapping")

    entry_data = payload.dict(by_alias=True, exclude_none=True)
    entry_data.pop("mapping_section", None)
    config.setdefault(payload.mapping_section, {})[payload.code_compte] = entry_data
    save_mapping_config(config)
    ws_manager.broadcast("sage_bfc", "mapping_updated", {"scope": "entry", "code_compte": payload.code_compte})
    log_audit_action(
        user=user,
        action="create",
        module="sage_bfc_mapping",
        entity_type="mapping_entry",
        entity_id=payload.code_compte,
        detail={"mapping_section": payload.mapping_section},
        request=request,
    )
    return _entry_to_response(payload.mapping_section, payload.code_compte, entry_data)

@router.put("/mapping/entries/{code_compte}", response_model=MappingEntryResponse)
async def update_mapping_entry(
    code_compte: str,
    payload: MappingEntryBase,
    request: Request,
    user: dict = Depends(get_current_user),
):
    _validate_mapping_entry(payload)
    original_code = code_compte
    new_code = payload.code_compte
    if not original_code:
        raise HTTPException(status_code=400, detail="code_compte dans l'URL est obligatoire")

    config = get_mapping_config()
    sections = _find_sections_for_code(config, original_code)
    if not sections:
        raise HTTPException(status_code=404, detail="Code compte introuvable")

    target_section = payload.mapping_section
    if not target_section:
        if len(sections) > 1:
            raise HTTPException(status_code=400, detail="mapping_section requis (code présent dans plusieurs sections)")
        target_section = sections[0]
    if target_section not in _MAPPING_SECTIONS:
        raise HTTPException(status_code=400, detail="mapping_section invalide")

    if new_code != original_code:
        existing_sections = _find_sections_for_code(config, new_code)
        if existing_sections:
            raise HTTPException(status_code=409, detail="Le nouveau code compte existe déjà dans le mapping")

    for section in sections:
        if original_code in config.get(section, {}):
            del config[section][original_code]

    entry_data = payload.dict(by_alias=True, exclude_none=True)
    entry_data.pop("mapping_section", None)
    config.setdefault(target_section, {})[new_code] = entry_data
    save_mapping_config(config)
    ws_manager.broadcast("sage_bfc", "mapping_updated", {"scope": "entry", "code_compte": new_code})
    log_audit_action(
        user=user,
        action="update",
        module="sage_bfc_mapping",
        entity_type="mapping_entry",
        entity_id=new_code,
        detail={"old_code": original_code, "mapping_section": target_section},
        request=request,
    )
    return _entry_to_response(target_section, new_code, entry_data)

@router.delete("/mapping/entries/{code_compte}")
async def delete_mapping_entry(
    code_compte: str,
    mapping_section: Optional[str] = Query(None),
    request: Request = None,
    user: dict = Depends(get_current_user),
):
    _validate_code_compte(code_compte)
    config = get_mapping_config()
    sections = _find_sections_for_code(config, code_compte)
    if not sections:
        raise HTTPException(status_code=404, detail="Code compte introuvable")

    target_section = mapping_section
    if not target_section:
        if len(sections) > 1:
            raise HTTPException(status_code=400, detail="mapping_section requis (code présent dans plusieurs sections)")
        target_section = sections[0]
    if target_section not in _MAPPING_SECTIONS:
        raise HTTPException(status_code=400, detail="mapping_section invalide")
    if code_compte not in config.get(target_section, {}):
        raise HTTPException(status_code=404, detail="Code compte introuvable dans cette section")

    del config[target_section][code_compte]
    save_mapping_config(config)
    ws_manager.broadcast("sage_bfc", "mapping_updated", {"scope": "entry", "code_compte": code_compte})
    log_audit_action(
        user=user,
        action="delete",
        module="sage_bfc_mapping",
        entity_type="mapping_entry",
        entity_id=code_compte,
        detail={"mapping_section": target_section},
        request=request,
    )
    return {"status": "deleted", "code_compte": code_compte}

@router.get("/mapping/regles-agregation")
async def get_regles_agregation():
    config = get_mapping_config()
    return config.get("regles_agregation", {})

@router.put("/mapping/regles-agregation")
async def put_regles_agregation(
    payload: Dict[str, Any],
    request: Request,
    user: dict = Depends(get_current_user),
):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload invalide")
    _validate_regles_agregation_payload(payload)
    config = get_mapping_config()
    config["regles_agregation"] = payload
    save_mapping_config(config)
    ws_manager.broadcast("sage_bfc", "mapping_updated", {"scope": "regles_agregation"})
    log_audit_action(
        user=user,
        action="update",
        module="sage_bfc_mapping",
        entity_type="regles_agregation",
        entity_id=None,
        request=request,
    )
    return {"status": "ok"}

@router.get("/mapping/validations-interco")
async def get_validations_interco():
    config = get_mapping_config()
    return config.get("validations_interco", {})

@router.put("/mapping/validations-interco")
async def put_validations_interco(
    payload: Dict[str, Any],
    request: Request,
    user: dict = Depends(get_current_user),
):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload invalide")
    _validate_validations_interco_payload(payload)
    config = get_mapping_config()
    config["validations_interco"] = payload
    save_mapping_config(config)
    ws_manager.broadcast("sage_bfc", "mapping_updated", {"scope": "validations_interco"})
    log_audit_action(
        user=user,
        action="update",
        module="sage_bfc_mapping",
        entity_type="validations_interco",
        entity_id=None,
        request=request,
    )
    return {"status": "ok"}

@router.get("/mapping/correspondances-bpc-bfc")
async def get_correspondances_bpc_bfc():
    config = get_mapping_config()
    return config.get("correspondances_bpc_bfc", {})

@router.put("/mapping/correspondances-bpc-bfc")
async def put_correspondances_bpc_bfc(
    payload: Dict[str, Any],
    request: Request,
    user: dict = Depends(get_current_user),
):
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload invalide")
    _validate_correspondances_bpc_bfc_payload(payload)
    config = get_mapping_config()
    config["correspondances_bpc_bfc"] = payload
    save_mapping_config(config)
    ws_manager.broadcast("sage_bfc", "mapping_updated", {"scope": "correspondances_bpc_bfc"})
    log_audit_action(
        user=user,
        action="update",
        module="sage_bfc_mapping",
        entity_type="correspondances_bpc_bfc",
        entity_id=None,
        request=request,
    )
    return {"status": "ok"}

@router.get("/mapping/stats", response_model=MappingStats)
async def get_mapping_stats(mapper: SageBFCMapper = Depends(get_mapper)):
    """
    Récupère les statistiques du mapping SAGE → BFC
    """
    stats = mapper.get_stats()
    return MappingStats(**stats)

@router.post("/parse", response_model=TableauBFCResponse)
async def parse_balance(
    file: UploadFile = File(..., description="Fichier balance SAGE (Excel ou CSV)"),
    periode: str = Query(..., description="Période comptable (YYYY-MM ou YYYY-MM-DD)"),
    parser: SageBalanceParser = Depends(get_parser),
    request: Request = None,
    user: dict = Depends(get_current_user),
):
    """
    Parse un fichier balance SAGE et retourne le tableau BFC.
    La période comptable est obligatoire (format YYYY-MM ou YYYY-MM-DD).
    Les résultats sont automatiquement sauvegardés en base de données.
    """
    # Convertir la période string en date
    try:
        if len(periode) == 7:  # Format YYYY-MM
            periode_date = date.fromisoformat(periode + "-01")
        else:  # Format YYYY-MM-DD
            periode_date = date.fromisoformat(periode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Format de période invalide: {periode}. Utilisez YYYY-MM ou YYYY-MM-DD")
    # Vérification extension
    allowed_extensions = ['.xlsx', '.xls', '.csv']
    file_ext = file.filename.lower().split('.')[-1]
    if f'.{file_ext}' not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Format non supporté. Formats acceptés: {', '.join(allowed_extensions)}"
        )
    
    try:
        content = await file.read()
        
        # Parsing avec la période obligatoire
        resultat_cumule = parser.parse_file(
            file_content=content,
            filename=file.filename,
            periode=periode_date
        )

        # Conversion cumulé -> réel mensuel (M réel = M cumulé - M-1 cumulé)
        resultat_reel = _convert_cumulative_to_real(resultat_cumule, parser)
        
        # Stockage en cache pour export ultérieur
        tableau_id = str(uuid.uuid4())
        _tableaux_cache[tableau_id] = resultat_reel
        
        # Sauvegarde automatique en base de données
        _save_monthly_data(resultat_reel, file.filename)
        _save_monthly_cumulative_data(resultat_cumule, file.filename)

        # Synchronisation temps réel des écarts forecast vs réalisé
        resume_payload = (
            resultat_reel.resume.model_dump(mode="json")
            if hasattr(resultat_reel.resume, "model_dump")
            else resultat_reel.resume.dict()
        )
        sync_actuals_from_resume(resultat_reel.periode, resume_payload)

        ws_manager.broadcast("sage_bfc", "upload", {"periode": str(resultat_reel.periode)})
        ws_manager.broadcast(
            "forecast",
            "annual_comparison_updated",
            {"year": resultat_reel.periode.year, "month": resultat_reel.periode.month},
        )

        log_audit_action(
            user=user,
            action="parse",
            module="sage_bfc",
            entity_type="balance",
            entity_id=str(resultat_reel.periode),
            detail={"filename": file.filename},
            request=request,
        )

        return resultat_reel
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de traitement: {str(e)}")

@router.get("/tableau/{tableau_id}", response_model=TableauBFCResponse)
async def get_tableau(tableau_id: str):
    """
    Récupère un tableau BFC précédemment généré (stocké en cache)
    """
    if tableau_id not in _tableaux_cache:
        raise HTTPException(status_code=404, detail="Tableau non trouvé ou expiré")
    
    return _tableaux_cache[tableau_id]

@router.get("/tableau/{tableau_id}/export/excel")
async def export_excel(tableau_id: str):
    """
    Exporte un tableau BFC au format Excel
    """
    if tableau_id not in _tableaux_cache:
        raise HTTPException(status_code=404, detail="Tableau non trouvé ou expiré")
    
    tableau = _tableaux_cache[tableau_id]
    
    try:
        import pandas as pd
        
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            workbook = writer.book
            
            # Formats
            money_format = workbook.add_format({'num_format': '#,##0.00', 'align': 'right'})
            header_format = workbook.add_format({
                'bold': True, 'bg_color': '#4472C4', 
                'font_color': 'white', 'border': 1
            })
            
            # Feuille 1: Détail des lignes
            df_detail = pd.DataFrame([l.dict() for l in tableau.lignes])
            df_detail.to_excel(writer, sheet_name='Lignes BFC', index=False)
            worksheet1 = writer.sheets['Lignes BFC']
            worksheet1.set_column('E:F', 15, money_format)
            
            # Feuille 2: Résumé P&L
            resume_data = {
                'Ligne': [
                    'CA BRUT', 'Rétrocessions', 'CA NET',
                    'Autres Produits', 'TOTAL PRODUITS',
                    '', 'Frais Personnel', 'Honoraires', 'Frais Commerciaux',
                    'Impôts', 'Fonctionnement', 'Autres Charges',
                    'Brand Fees', 'Management Fees', 'TOTAL CHARGES',
                    '', 'EBITDA', 'EBITDA %',
                    'Produits Financiers', 'Charges Financières', 'Résultat Financier',
                    'Dotations', 'Résultat avant Impôt', 'Impôt', 'RÉSULTAT NET', 'RN %'
                ],
                'Montant (TND)': [
                    tableau.resume.ca_brut, tableau.resume.retrocessions, tableau.resume.ca_net,
                    tableau.resume.autres_produits, tableau.resume.total_produits,
                    '',
                    tableau.resume.frais_personnel, tableau.resume.honoraires,
                    tableau.resume.frais_commerciaux, tableau.resume.impots_taxes,
                    tableau.resume.fonctionnement, tableau.resume.autres_charges,
                    tableau.resume.brand_fees, tableau.resume.management_fees,
                    tableau.resume.total_charges,
                    '',
                    tableau.resume.ebitda, f"{tableau.resume.ebitda_pct:.2f}%",
                    tableau.resume.produits_financiers, tableau.resume.charges_financieres,
                    tableau.resume.resultat_financier,
                    tableau.resume.dotations, tableau.resume.resultat_avant_impot,
                    tableau.resume.impot_societes, tableau.resume.resultat_net,
                    f"{tableau.resume.resultat_net_pct:.2f}%"
                ]
            }
            df_resume = pd.DataFrame(resume_data)
            df_resume.to_excel(writer, sheet_name='Résumé P&L', index=False)
            worksheet2 = writer.sheets['Résumé P&L']
            worksheet2.set_column('B:B', 20, money_format)
        
        output.seek(0)
        
        periode_str = tableau.periode.strftime('%Y%m')
        filename = f"BFC_{periode_str}.xlsx"
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'export: {str(e)}")


# ===================== Helper: Sauvegarder en BDD =====================

def _serialize_lignes(lignes):
    """Sérialise la liste de lignes BFC en JSON"""
    return json.dumps([l.model_dump(mode='json') if hasattr(l, 'model_dump') else _ligne_to_dict(l) for l in lignes], default=str)

def _ligne_to_dict(ligne):
    """Convertit une LigneBudgetBFC en dict sérialisable"""
    d = ligne.dict() if hasattr(ligne, 'dict') else ligne.__dict__
    # Convertir les Decimal et date en types sérialisables
    result = {}
    for k, v in d.items():
        if hasattr(v, 'isoformat'):
            result[k] = v.isoformat()
        elif hasattr(v, '__float__'):
            result[k] = float(v)
        else:
            result[k] = v
    return result

def _serialize_resume(resume):
    """Sérialise le résumé en JSON"""
    if hasattr(resume, 'model_dump'):
        d = resume.model_dump(mode='json')
    else:
        d = resume.dict() if hasattr(resume, 'dict') else resume.__dict__
        result = {}
        for k, v in d.items():
            if hasattr(v, 'isoformat'):
                result[k] = v.isoformat()
            elif hasattr(v, '__float__'):
                result[k] = float(v)
            else:
                result[k] = v
        d = result
    return json.dumps(d, default=str)

def _save_monthly_data(resultat: TableauBFCResponse, file_name: str):
    """Sauvegarde ou met à jour les données mensuelles en BDD"""
    resume_json = _serialize_resume(resultat.resume)
    lignes_json = _serialize_lignes(resultat.lignes)
    
    with db.get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO sage_bfc_monthly 
                (periode, resume, lignes, file_name, lignes_count)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                resume = VALUES(resume),
                lignes = VALUES(lignes),
                file_name = VALUES(file_name),
                lignes_count = VALUES(lignes_count),
                updated_at = CURRENT_TIMESTAMP
        """, (
            resultat.periode,
            resume_json,
            lignes_json,
            file_name,
            len(resultat.lignes)
        ))


def _save_monthly_cumulative_data(resultat: TableauBFCResponse, file_name: str):
    """Sauvegarde ou met à jour les données cumulées brutes en BDD"""
    resume_json = _serialize_resume(resultat.resume)
    lignes_json = _serialize_lignes(resultat.lignes)

    with db.get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO sage_bfc_monthly_cumule
                (periode, resume, lignes, file_name, lignes_count)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                resume = VALUES(resume),
                lignes = VALUES(lignes),
                file_name = VALUES(file_name),
                lignes_count = VALUES(lignes_count),
                updated_at = CURRENT_TIMESTAMP
        """, (
            resultat.periode,
            resume_json,
            lignes_json,
            file_name,
            len(resultat.lignes)
        ))


def _build_ligne_key(ligne: LigneBudgetBFC) -> str:
    return "|".join([
        str(ligne.code_sage or ""),
        str(ligne.agregat_bfc or ""),
        str(ligne.sous_categorie or ""),
        str(ligne.type_ligne or ""),
        str(ligne.sens or ""),
    ])


def _group_lignes_by_key(lignes: list[LigneBudgetBFC]) -> dict[str, dict]:
    """
    Regroupe les lignes par clé technique pour éviter les doubles soustractions
    quand plusieurs lignes partagent le même code/aggrégat.
    """
    grouped: dict[str, dict] = {}
    for l in lignes:
        k = _build_ligne_key(l)
        if k not in grouped:
            grouped[k] = {
                "template": l,
                "total": Decimal('0'),
            }
        grouped[k]["total"] += Decimal(str(l.montant))
    return grouped


def _load_previous_cumulative_lignes(periode: date) -> list[LigneBudgetBFC]:
    """
    Charge les lignes cumulées du mois précédent disponible.
    Priorité: table cumulative; fallback: table monthly (rétrocompatibilité).
    """
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT lignes
            FROM sage_bfc_monthly_cumule
            WHERE periode < %s
              AND YEAR(periode) = YEAR(%s)
            ORDER BY periode DESC
            LIMIT 1
        """, (periode, periode))
        row = cursor.fetchone()

    if not row:
        with db.get_cursor() as cursor:
            cursor.execute("""
                SELECT lignes
                FROM sage_bfc_monthly
                WHERE periode < %s
                  AND YEAR(periode) = YEAR(%s)
                ORDER BY periode DESC
                LIMIT 1
            """, (periode, periode))
            row = cursor.fetchone()

    if not row:
        return []

    raw = row['lignes'] if isinstance(row['lignes'], list) else json.loads(row['lignes'])
    lignes = []
    for item in raw:
        try:
            lignes.append(LigneBudgetBFC(**item))
        except Exception:
            continue
    return lignes


def _convert_cumulative_to_real(resultat_cumule: TableauBFCResponse, parser: SageBalanceParser) -> TableauBFCResponse:
    """Convertit un résultat cumulé en réel mensuel via delta au cumul précédent."""
    previous_lignes = _load_previous_cumulative_lignes(resultat_cumule.periode)
    if not previous_lignes:
        # Premier mois disponible: réel = cumulé
        return resultat_cumule

    previous_grouped = _group_lignes_by_key(previous_lignes)
    current_grouped = _group_lignes_by_key(resultat_cumule.lignes)

    lignes_reelles: list[LigneBudgetBFC] = []
    for k, current_info in current_grouped.items():
        template = current_info["template"]
        current_amount = current_info["total"]
        prev_amount = previous_grouped.get(k, {}).get("total", Decimal('0'))
        real_amount = current_amount - prev_amount

        lignes_reelles.append(
            template.model_copy(update={
                "montant": real_amount,
                "montant_absolu": abs(real_amount),
            })
        )

    agregats = parser.mapper.calculer_agregats(lignes_reelles)
    resume_reel = TableauBFCSummary(
        periode=resultat_cumule.periode,
        ca_brut=float(agregats['ca_brut']),
        retrocessions=float(agregats['retrocessions']),
        ca_net=float(agregats['ca_net']),
        autres_produits=float(agregats['autres_produits']),
        total_produits=float(agregats['total_produits']),
        frais_personnel=float(agregats['frais_personnel']),
        honoraires=float(agregats['honoraires']),
        frais_commerciaux=float(agregats['frais_commerciaux']),
        impots_taxes=float(agregats['impots_taxes']),
        fonctionnement=float(agregats['fonctionnement']),
        autres_charges=float(agregats['autres_charges']),
        brand_fees=float(agregats['brand_fees']),
        management_fees=float(agregats['management_fees']),
        interco_charges=float(agregats['interco_charges']),
        total_charges=float(agregats['total_charges']),
        ebitda=float(agregats['ebitda']),
        ebitda_pct=float(agregats['ebitda_pct']),
        produits_financiers=float(agregats['produits_financiers']),
        charges_financieres=float(agregats['charges_financieres']),
        resultat_financier=float(agregats['resultat_financier']),
        dotations=float(agregats['dotations']),
        produits_exceptionnels=float(agregats['produits_exceptionnels']),
        charges_exceptionnelles=float(agregats['charges_exceptionnelles']),
        resultat_exceptionnel=float(agregats['resultat_exceptionnel']),
        resultat_avant_impot=float(agregats['resultat_avant_impot']),
        impot_societes=float(agregats['impot_societes']),
        resultat_net=float(agregats['resultat_net']),
        resultat_net_pct=float(agregats['resultat_net_pct']),
    )

    return TableauBFCResponse(
        periode=resultat_cumule.periode,
        lignes=lignes_reelles,
        resume=resume_reel,
    )


# ===================== CRUD: Données mensuelles =====================

@router.get("/monthly", response_model=list[MonthlyDataSummary])
async def get_all_monthly():
    """
    Récupère la liste de tous les mois stockés (sans lignes détaillées)
    """
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT periode, file_name, lignes_count, resume, created_at, updated_at
            FROM sage_bfc_monthly
            ORDER BY periode ASC
        """)
        rows = cursor.fetchall()
    
    result = []
    for row in rows:
        resume_data = row['resume'] if isinstance(row['resume'], dict) else json.loads(row['resume'])
        result.append(MonthlyDataSummary(
            periode=row['periode'],
            file_name=row['file_name'],
            lignes_count=row['lignes_count'],
            resume=resume_data,
            created_at=str(row['created_at']) if row['created_at'] else None,
            updated_at=str(row['updated_at']) if row['updated_at'] else None
        ))
    
    return result


@router.get("/monthly/{periode}", response_model=MonthlyDataFull)
async def get_monthly_detail(periode: str):
    """
    Récupère les données complètes d'un mois (avec lignes, validations, etc.)
    """
    try:
        if len(periode) == 7:
            periode = date.fromisoformat(periode + "-01")
        else:
            periode = date.fromisoformat(periode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Format de période invalide: {periode}")
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT periode, file_name, lignes_count, resume, lignes, 
                   created_at, updated_at
            FROM sage_bfc_monthly
            WHERE periode = %s
        """, (periode,))
        row = cursor.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail=f"Aucune donnée pour la période {periode}")
    
    resume_data = row['resume'] if isinstance(row['resume'], dict) else json.loads(row['resume'])
    lignes_data = row['lignes'] if isinstance(row['lignes'], list) else json.loads(row['lignes'])
    
    return MonthlyDataFull(
        periode=row['periode'],
        file_name=row['file_name'],
        lignes_count=row['lignes_count'],
        resume=resume_data,
        lignes=lignes_data,
        created_at=str(row['created_at']) if row['created_at'] else None,
        updated_at=str(row['updated_at']) if row['updated_at'] else None
    )


@router.delete("/monthly/{periode}")
async def delete_monthly(
    periode: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Supprime les données d'un mois spécifique
    """
    try:
        if len(periode) == 7:
            periode = date.fromisoformat(periode + "-01")
        else:
            periode = date.fromisoformat(periode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Format de période invalide: {periode}")
    with db.get_cursor() as cursor:
        cursor.execute("SELECT id FROM sage_bfc_monthly WHERE periode = %s", (periode,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Aucune donnée pour la période {periode}")
        
        cursor.execute("DELETE FROM sage_bfc_monthly WHERE periode = %s", (periode,))
        cursor.execute("DELETE FROM sage_bfc_monthly_cumule WHERE periode = %s", (periode,))

    # Synchroniser le module forecast: suppression des réels/écarts pour ce mois
    clear_actuals_for_month(periode.year, periode.month)

    # Invalider les cycles d'ajustement devenus incohérents (ex: M03 sans 3 mois réels)
    invalidation_payload = invalidate_adjustment_cycles_for_year(periode.year)

    ws_manager.broadcast("sage_bfc", "delete", {"periode": str(periode)})
    ws_manager.broadcast("forecast", "actuals_cleared", {"year": periode.year, "month": periode.month})
    ws_manager.broadcast("forecast", "cycles_invalidated", invalidation_payload)

    log_audit_action(
        user=user,
        action="delete",
        module="sage_bfc",
        entity_type="monthly",
        entity_id=str(periode),
        request=request,
    )

    return {
        "status": "supprimé",
        "periode": str(periode),
        "forecast_cycle_invalidation": invalidation_payload,
    }


@router.delete("/monthly")
async def delete_all_monthly(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """
    Supprime toutes les données mensuelles
    """
    with db.get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as cnt FROM sage_bfc_monthly")
        count = cursor.fetchone()['cnt']
        cursor.execute("DELETE FROM sage_bfc_monthly")
        cursor.execute("DELETE FROM sage_bfc_monthly_cumule")

    # Synchroniser le module forecast: suppression globale des réels/écarts
    clear_all_actuals()
    purge_payload = purge_all_adjustment_cycles()

    ws_manager.broadcast("sage_bfc", "delete_all", {"count": count})
    ws_manager.broadcast("forecast", "actuals_cleared_all", {"count": count})
    ws_manager.broadcast("forecast", "cycles_purged", purge_payload)

    log_audit_action(
        user=user,
        action="delete_all",
        module="sage_bfc",
        entity_type="monthly",
        entity_id=None,
        detail={"count": count},
        request=request,
    )

    return {
        "status": "supprimé",
        "count": count,
        "forecast_cycle_purge": purge_payload,
    }


@router.post("/close-year")
async def close_year(
    year: int = Query(..., ge=2000, le=2100, description="Année à clôturer"),
    force: bool = Query(False, description="Autorise la clôture sans 12 mois"),
    request: Request = None,
    user: dict = Depends(get_current_user),
):
    """
    Clôture annuelle SAGE→BFC:
    1) Vérifie la complétude (12 mois sauf force)
    2) Archive un snapshot annuel (historique)
    3) Synchronise l'année clôturée vers bfc_budget_history
    4) Génère le budget initial de l'année suivante
    """
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT periode, file_name, lignes_count, resume, lignes, created_at, updated_at
            FROM sage_bfc_monthly
            WHERE YEAR(periode) = %s
            ORDER BY periode ASC
            """,
            (year,),
        )
        monthly_rows = cursor.fetchall() or []

        cursor.execute(
            """
            SELECT periode, file_name, lignes_count, resume, lignes, created_at, updated_at
            FROM sage_bfc_monthly_cumule
            WHERE YEAR(periode) = %s
            ORDER BY periode ASC
            """,
            (year,),
        )
        cumulative_rows = cursor.fetchall() or []

    if not monthly_rows:
        raise HTTPException(status_code=404, detail=f"Aucune donnée mensuelle trouvée pour {year}")

    months_count = len({int(r["periode"].month) for r in monthly_rows if r.get("periode") is not None})
    if months_count < 12 and not force:
        raise HTTPException(
            status_code=400,
            detail=f"Clôture refusée: {months_count}/12 mois disponibles pour {year}",
        )

    def _normalize_rows(rows):
        out = []
        for r in rows:
            resume_raw = r.get("resume")
            lignes_raw = r.get("lignes")
            out.append(
                {
                    "periode": str(r.get("periode")) if r.get("periode") is not None else None,
                    "file_name": r.get("file_name"),
                    "lignes_count": int(r.get("lignes_count") or 0),
                    "resume": resume_raw if isinstance(resume_raw, dict) else json.loads(resume_raw or "{}"),
                    "lignes": lignes_raw if isinstance(lignes_raw, list) else json.loads(lignes_raw or "[]"),
                    "created_at": str(r.get("created_at")) if r.get("created_at") is not None else None,
                    "updated_at": str(r.get("updated_at")) if r.get("updated_at") is not None else None,
                }
            )
        return out

    archive_payload = {
        "year": year,
        "months_count": months_count,
        "monthly": _normalize_rows(monthly_rows),
        "monthly_cumule": _normalize_rows(cumulative_rows),
    }

    next_year = year + 1
    sync_payload = sync_closed_years_into_history(before_year=next_year)
    run_id, rows_written = generate_forecast(target_year=next_year, cycle_code="INITIAL", cycle_month=None)
    forecast_payload = {
        "target_year": next_year,
        "cycle_code": "INITIAL",
        "run_id": run_id,
        "rows_written": rows_written,
    }

    with db.get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO sage_bfc_year_closure (closed_year, monthly_count, archive_payload, sync_payload, forecast_payload)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                monthly_count = VALUES(monthly_count),
                archive_payload = VALUES(archive_payload),
                sync_payload = VALUES(sync_payload),
                forecast_payload = VALUES(forecast_payload),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                year,
                months_count,
                json.dumps(archive_payload, ensure_ascii=False, default=str),
                json.dumps(sync_payload, ensure_ascii=False, default=str),
                json.dumps(forecast_payload, ensure_ascii=False, default=str),
            ),
        )

    ws_manager.broadcast("sage_bfc", "year_closed", {"year": year, "next_year": next_year})
    ws_manager.broadcast("forecast", "generated", forecast_payload)

    log_audit_action(
        user=user,
        action="close_year",
        module="sage_bfc",
        entity_type="year",
        entity_id=str(year),
        detail={"months_count": months_count, "force": force, "next_year": next_year},
        request=request,
    )

    return {
        "status": "closed",
        "closed_year": year,
        "months_count": months_count,
        "next_year": next_year,
        "archive_saved": True,
        "history_sync": sync_payload,
        "forecast": forecast_payload,
    }


@router.get("/closed-years")
async def get_closed_years():
    """
    Retourne la liste des années déjà clôturées.
    """
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT closed_year
            FROM sage_bfc_year_closure
            ORDER BY closed_year DESC
            """
        )
        rows = cursor.fetchall() or []

    years = [int(r["closed_year"]) for r in rows if r.get("closed_year") is not None]
    return {
        "years": years,
        "latest": years[0] if years else None,
    }


@router.get("/audit/cumulative-delta")
async def get_audit_cumulative_delta(
    year: int = Query(..., ge=2000, le=2100, description="Année fiscale"),
    agregat: str = Query(..., description="Agrégat (ex: ca_brut, frais_personnel, resultat_net)"),
):
    """
    Renvoie la table d'audit comptable mensuelle pour un agrégat:
    - Cn   : cumul courant
    - Cn-1 : cumul précédent (même année)
    - Vn   : valeur mensuelle réelle = Cn - Cn-1
    """
    agregat_key = _normalize_agregat_name(agregat)

    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT MONTH(periode) AS mois, resume
            FROM sage_bfc_monthly_cumule
            WHERE YEAR(periode) = %s
            ORDER BY periode ASC
        """, (year,))
        rows = cursor.fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Aucune donnée cumulée trouvée pour l'année {year}."
        )

    table = []
    previous_cumul = Decimal('0')

    for row in rows:
        mois = int(row['mois'])
        resume = row['resume'] if isinstance(row['resume'], dict) else json.loads(row['resume'])
        current_cumul = Decimal(str(resume.get(agregat_key, 0) or 0))
        valeur_periode = current_cumul - previous_cumul

        table.append({
            "mois": mois,
            "Cn": float(current_cumul),
            "Cn_1": float(previous_cumul),
            "Vn": float(valeur_periode),
            "equation_check": float(previous_cumul + valeur_periode),
            "equation_ok": bool((previous_cumul + valeur_periode) == current_cumul),
        })

        previous_cumul = current_cumul

    return {
        "year": year,
        "agregat": agregat_key,
        "formula": "Cn = Cn-1 + Vn",
        "rows": table,
    }


@router.post("/monthly/recompute-real")
async def recompute_monthly_real_values(
    mapper: SageBFCMapper = Depends(get_mapper),
    request: Request = None,
    user: dict = Depends(get_current_user),
):
    """
    Recalcule les mois stockés en réel mensuel (delta cumulé M - cumulé M-1)
    à partir des données déjà présentes dans sage_bfc_monthly.
    Utile après migration/activation de la logique cumulée.
    """
    with db.get_cursor() as cursor:
        cursor.execute("""
            SELECT periode, resume, lignes, file_name, lignes_count
            FROM sage_bfc_monthly
            ORDER BY periode ASC
        """)
        rows = cursor.fetchall()

    if not rows:
        log_audit_action(
            user=user,
            action="recompute_real",
            module="sage_bfc",
            entity_type="monthly",
            entity_id=None,
            detail={"updated_months": 0},
            request=request,
        )
        return {"status": "ok", "updated_months": 0, "message": "Aucune donnée à recalculer"}

    prev_cum_by_key: dict[str, Decimal] = {}
    prev_year: Optional[int] = None
    updated = 0

    for row in rows:
        periode = row['periode']
        current_year = int(periode.year)

        # Réinitialisation annuelle: en janvier (ou changement d'année), Cn-1 = 0
        if prev_year is None or current_year != prev_year:
            prev_cum_by_key = {}

        raw_lignes = row['lignes'] if isinstance(row['lignes'], list) else json.loads(row['lignes'])

        cum_lignes: list[LigneBudgetBFC] = []
        for item in raw_lignes:
            try:
                cum_lignes.append(LigneBudgetBFC(**item))
            except Exception:
                continue

        # Sauvegarder le cumul brut pour usage futur
        cum_result = TableauBFCResponse(
            periode=periode,
            lignes=cum_lignes,
            resume=TableauBFCSummary(**(row['resume'] if isinstance(row['resume'], dict) else json.loads(row['resume'])))
        )
        _save_monthly_cumulative_data(cum_result, row.get('file_name'))

        # Calcul réel par delta (sur montants agrégés par clé)
        real_lignes: list[LigneBudgetBFC] = []
        current_grouped = _group_lignes_by_key(cum_lignes)
        current_cum_by_key: dict[str, Decimal] = {}

        for key, info in current_grouped.items():
            template = info["template"]
            current_amount = info["total"]
            current_cum_by_key[key] = current_amount

            prev_amount = prev_cum_by_key.get(key, Decimal('0'))
            real_amount = current_amount - prev_amount
            real_lignes.append(
                template.model_copy(update={
                    "montant": real_amount,
                    "montant_absolu": abs(real_amount),
                })
            )

        agregats = mapper.calculer_agregats(real_lignes)
        resume_reel = TableauBFCSummary(
            periode=periode,
            ca_brut=float(agregats['ca_brut']),
            retrocessions=float(agregats['retrocessions']),
            ca_net=float(agregats['ca_net']),
            autres_produits=float(agregats['autres_produits']),
            total_produits=float(agregats['total_produits']),
            frais_personnel=float(agregats['frais_personnel']),
            honoraires=float(agregats['honoraires']),
            frais_commerciaux=float(agregats['frais_commerciaux']),
            impots_taxes=float(agregats['impots_taxes']),
            fonctionnement=float(agregats['fonctionnement']),
            autres_charges=float(agregats['autres_charges']),
            brand_fees=float(agregats['brand_fees']),
            management_fees=float(agregats['management_fees']),
            interco_charges=float(agregats['interco_charges']),
            total_charges=float(agregats['total_charges']),
            ebitda=float(agregats['ebitda']),
            ebitda_pct=float(agregats['ebitda_pct']),
            produits_financiers=float(agregats['produits_financiers']),
            charges_financieres=float(agregats['charges_financieres']),
            resultat_financier=float(agregats['resultat_financier']),
            dotations=float(agregats['dotations']),
            produits_exceptionnels=float(agregats['produits_exceptionnels']),
            charges_exceptionnelles=float(agregats['charges_exceptionnelles']),
            resultat_exceptionnel=float(agregats['resultat_exceptionnel']),
            resultat_avant_impot=float(agregats['resultat_avant_impot']),
            impot_societes=float(agregats['impot_societes']),
            resultat_net=float(agregats['resultat_net']),
            resultat_net_pct=float(agregats['resultat_net_pct']),
        )

        real_result = TableauBFCResponse(periode=periode, lignes=real_lignes, resume=resume_reel)
        _save_monthly_data(real_result, row.get('file_name'))

        prev_cum_by_key = current_cum_by_key
        prev_year = current_year
        updated += 1

    ws_manager.broadcast("sage_bfc", "recompute_real", {"updated_months": updated})
    ws_manager.broadcast("forecast", "recompute_real", {"updated_months": updated})

    log_audit_action(
        user=user,
        action="recompute_real",
        module="sage_bfc",
        entity_type="monthly",
        entity_id=None,
        detail={"updated_months": updated},
        request=request,
    )
    return {"status": "ok", "updated_months": updated}