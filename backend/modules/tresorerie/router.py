# modules/tresorerie/router.py
from datetime import date, datetime
from typing import Optional
import io
import math

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse

from database import db
from ws_manager import manager as ws_manager
from modules.auth.dependencies import get_current_user, require_permission_code
from modules.audit.service import log_audit_action
from modules.saisie_bancaire.service import (
    _extract_movements,
    _parse_csv_text,
    _parse_date,
    _parse_pdf,
)
from modules.rapprochement_bancaire.service import extract_bank_opening_balance
from .constants import (
    BANQUES_TRESORERIE,
    DEVISES_TRESORERIE,
    NATURES_TRESORERIE,
    normaliser_nature,
)
from .models import (
    BulkNatureUpdateRequest,
    NatureUpdateRequest,
    NatureUpdateResponse,
    SoldeOuvertureRequest,
    TresorerieBanqueReporting,
    TresorerieImport,
    TresorerieImportResponse,
    TresorerieMovement,
    TresorerieMovementPage,
    TresorerieReportingResponse,
)
from .service import (
    ancre_de_banque,
    calculer_solde,
    construire_controle_extraction,
    construire_reporting,
    demarrer_couverture,
    filtrer_mouvements_par_periode,
    periodes_chevauchent,
    preparer_mouvements_extraits,
    totaliser,
    totaliser_commissions,
)

router = APIRouter(
    prefix="/tresorerie",
    tags=["Trésorerie"],
    responses={404: {"description": "Non trouvé"}},
    dependencies=[],
)

MAX_SIZE = 25 * 1024 * 1024  # 25 Mo
EXTENSIONS_ACCEPTEES = {"pdf", "csv", "txt", "xlsx", "xls"}


# ═══════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════

def _conditions_periode(alias: str, date_debut: Optional[date], date_fin: Optional[date], colonne: str = "date_operation"):
    """Conditions SQL (sans le « AND » de liaison) et paramètres pour une plage de dates inclusive."""
    conditions = []
    params = []
    if date_debut:
        conditions.append(f"{alias}.{colonne} >= %s")
        params.append(date_debut)
    if date_fin:
        conditions.append(f"{alias}.{colonne} <= %s")
        params.append(date_fin)
    return conditions, params


def _parse_date_iso(valeur: Optional[str]) -> Optional[date]:
    """Date d'un champ texte au format AAAA-MM-JJ, tel qu'envoyé par <input type="date">.

    `_parse_date` du module Saisie caisse appelle dateutil avec ``dayfirst=True`` :
    il lit « 2026-01-10 » comme le 1er octobre 2026. Les dates ISO sont donc
    interprétées ici strictement, avant tout repli sur le parseur tolérant.
    """
    texte = (valeur or "").strip()
    if not texte:
        return None
    try:
        return datetime.strptime(texte, "%Y-%m-%d").date()
    except ValueError:
        return _parse_date(texte)


def _import_avec_totaux(cursor, import_id: int):
    cursor.execute(
        """
        SELECT i.*,
               (SELECT COUNT(*) FROM tresorerie_movements m WHERE m.import_id = i.id) AS total_mouvements,
               (SELECT COALESCE(SUM(m.debit), 0) FROM tresorerie_movements m WHERE m.import_id = i.id) AS total_debit,
               (SELECT COALESCE(SUM(m.credit), 0) FROM tresorerie_movements m WHERE m.import_id = i.id) AS total_credit
        FROM tresorerie_imports i
        WHERE i.id = %s
        """,
        (import_id,),
    )
    return cursor.fetchone()


def _stats_import(cursor, import_id: int):
    """Répartition des mouvements d'un import par nature."""
    cursor.execute(
        """
        SELECT COALESCE(nature, 'non_classe') AS nature,
               COUNT(*) AS nb,
               COALESCE(SUM(debit), 0) AS debit,
               COALESCE(SUM(credit), 0) AS credit
        FROM tresorerie_movements
        WHERE import_id = %s
        GROUP BY COALESCE(nature, 'non_classe')
        """,
        (import_id,),
    )
    stats = {row["nature"]: {"nb": int(row["nb"]), "debit": float(row["debit"]), "credit": float(row["credit"])}
             for row in cursor.fetchall()}
    for nature in NATURES_TRESORERIE:
        stats.setdefault(nature, {"nb": 0, "debit": 0.0, "credit": 0.0})
    stats.setdefault("non_classe", {"nb": 0, "debit": 0.0, "credit": 0.0})
    return stats


# ═══════════════════════════════════════════════════════════
# Référentiel
# ═══════════════════════════════════════════════════════════

@router.get("/banques", dependencies=[Depends(require_permission_code("tresorerie.read"))])
def get_banques():
    """Banques disponibles pour l'import des extraits."""
    return [
        {
            "code": code,
            "libelle": config["libelle"],
            "compte_comptable": config["compte_comptable"],
            "devise": DEVISES_TRESORERIE.get(code, "TND"),
            "requiert_taux": code in DEVISES_TRESORERIE,
        }
        for code, config in BANQUES_TRESORERIE.items()
    ]


@router.get("/soldes-ouverture", dependencies=[Depends(require_permission_code("tresorerie.read"))])
def lister_soldes_ouverture():
    """Ancres de solde de départ, une par banque."""
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT compte_banque, solde, date_solde, source_file_name, created_at
            FROM tresorerie_soldes_ouverture
            ORDER BY compte_banque
            """
        )
        ancres = cursor.fetchall()
    for ancre in ancres:
        banque = BANQUES_TRESORERIE.get(ancre["compte_banque"])
        ancre["libelle_banque"] = banque["libelle"] if banque else None
    return ancres


@router.put("/soldes-ouverture/{compte_banque}")
def definir_solde_ouverture(
    compte_banque: str,
    payload: SoldeOuvertureRequest,
    request: Request,
    user: dict = Depends(require_permission_code("tresorerie.import")),
):
    """Corrige l'ancre d'une banque dont la lecture automatique s'est trompée."""
    code_banque = (compte_banque or "").strip().upper()
    if code_banque not in BANQUES_TRESORERIE:
        raise HTTPException(status_code=400, detail="Compte bancaire invalide")

    with db.get_cursor() as cursor:
        cursor.execute("SELECT compte_banque FROM tresorerie_soldes_ouverture WHERE compte_banque = %s", (code_banque,))
        existe = cursor.fetchone() is not None
        if existe:
            cursor.execute(
                """
                UPDATE tresorerie_soldes_ouverture
                SET solde = %s, date_solde = %s, source_file_name = %s
                WHERE compte_banque = %s
                """,
                (payload.solde, payload.date_solde, "Correction manuelle", code_banque),
            )
        else:
            cursor.execute(
                """
                INSERT INTO tresorerie_soldes_ouverture
                (compte_banque, solde, date_solde, source_import_id, source_file_name)
                VALUES (%s, %s, %s, NULL, %s)
                """,
                (code_banque, payload.solde, payload.date_solde, "Saisie manuelle"),
            )

    log_audit_action(
        user=user,
        action="update" if existe else "create",
        module="tresorerie",
        entity_type="tresorerie_solde_ouverture",
        entity_id=code_banque,
        detail={"solde": payload.solde, "date_solde": str(payload.date_solde)},
        request=request,
    )
    ws_manager.broadcast("tresorerie", "solde", {"compte_banque": code_banque})
    return {
        "compte_banque": code_banque,
        "solde": payload.solde,
        "date_solde": payload.date_solde,
    }


@router.get("/summary", dependencies=[Depends(require_permission_code("tresorerie.read"))])
def get_summary():
    """Compteurs globaux affichés dans l'en-tête du module."""
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) AS imports_count,
                   (SELECT COUNT(*) FROM tresorerie_movements) AS mouvements_count,
                   (SELECT COUNT(*) FROM tresorerie_movements WHERE nature IS NULL) AS non_classes_count,
                   (SELECT COUNT(DISTINCT compte_banque) FROM tresorerie_imports) AS banques_count,
                   (SELECT MAX(updated_at) FROM tresorerie_imports) AS dernier_import
            FROM tresorerie_imports
            """
        )
        row = cursor.fetchone() or {}
    return {
        "imports_count": int(row.get("imports_count") or 0),
        "mouvements_count": int(row.get("mouvements_count") or 0),
        "non_classes_count": int(row.get("non_classes_count") or 0),
        "banques_count": int(row.get("banques_count") or 0),
        "dernier_import": row.get("dernier_import"),
    }


# ═══════════════════════════════════════════════════════════
# Imports d'extraits bancaires
# ═══════════════════════════════════════════════════════════

@router.post(
    "/imports",
    response_model=TresorerieImportResponse,
    dependencies=[Depends(require_permission_code("tresorerie.import"))],
)
def importer_extrait(
    request: Request,
    file: UploadFile = File(...),
    compte_banque: str = Form(...),
    periode_debut: Optional[str] = Form(None),
    periode_fin: Optional[str] = Form(None),
    taux_conversion: Optional[float] = Form(None),
    remplacer_import_id: Optional[int] = Form(None),
    user: dict = Depends(get_current_user),
):
    """Importe un extrait bancaire (PDF/CSV/Excel) et en extrait les mouvements.

    L'extraction est celle du module Saisie caisse (même service), afin que
    les deux modules lisent les relevés de la même manière.

    La période début/fin est obligatoire : elle délimite les mouvements à
    retenir dans un relevé plus large et sert au contrôle anti-doublon
    (un même jour ne peut pas être importé deux fois pour une banque).
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Fichier manquant")

    raw_bytes = file.file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Fichier vide")
    if len(raw_bytes) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (max 25 Mo)")

    code_banque = (compte_banque or "").strip().upper()
    if code_banque not in BANQUES_TRESORERIE:
        raise HTTPException(status_code=400, detail="Compte bancaire invalide")

    extension = (file.filename.split(".")[-1] or "").lower()
    if extension not in EXTENSIONS_ACCEPTEES:
        raise HTTPException(status_code=400, detail="Format non supporté (PDF, CSV ou Excel)")
    file_type = (file.content_type or "").lower()

    # ─── Période obligatoire ───
    if not (periode_debut or "").strip() or not (periode_fin or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Les périodes de début et de fin sont obligatoires.",
        )
    date_debut = _parse_date_iso(periode_debut)
    date_fin = _parse_date_iso(periode_fin)
    if date_debut is None or date_fin is None:
        raise HTTPException(
            status_code=400,
            detail="Période invalide : utilisez une date au format AAAA-MM-JJ.",
        )
    if date_debut > date_fin:
        raise HTTPException(status_code=400, detail="La période de début doit précéder la période de fin")

    # ─── Extraction ───
    try:
        if extension in {"xlsx", "xls"}:
            df = pd.read_excel(io.BytesIO(raw_bytes), dtype=str)
        elif extension in {"csv", "txt"}:
            df = _parse_csv_text(raw_bytes.decode("utf-8", errors="ignore"))
        else:
            df = _parse_pdf(raw_bytes)
        mouvements = _extract_movements(df)
    except HTTPException:
        raise
    except Exception as exc:  # PDF illisible, encodage inattendu…
        raise HTTPException(status_code=400, detail=f"Extraction impossible : {exc}")

    lignes_source = int(len(df.index))

    # ─── Restriction à la période demandée ───
    mouvements, hors_periode = filtrer_mouvements_par_periode(mouvements, date_debut, date_fin)
    if not mouvements:
        dates_releve = sorted({m.get("date_operation") for m in hors_periode if m.get("date_operation")})
        precision = ""
        if dates_releve:
            precision = (
                f" Le relevé couvre du {dates_releve[0].strftime('%d/%m/%Y')} "
                f"au {dates_releve[-1].strftime('%d/%m/%Y')}."
            )
        raise HTTPException(
            status_code=422,
            detail=(
                f"Aucun mouvement n'est daté entre le {date_debut.strftime('%d/%m/%Y')} "
                f"et le {date_fin.strftime('%d/%m/%Y')}.{precision}"
            ),
        )

    devise_source = DEVISES_TRESORERIE.get(code_banque)
    if devise_source:
        if not taux_conversion or taux_conversion <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"Le compte {code_banque} est en {devise_source}. Veuillez saisir un taux de conversion valide.",
            )
        for mouvement in mouvements:
            mouvement["debit"] = round(float(mouvement["debit"]) * taux_conversion, 3)
            mouvement["credit"] = round(float(mouvement["credit"]) * taux_conversion, 3)

    # ─── Solde de départ : figé une seule fois par banque ───
    # Il est lu sur le premier extrait importé, puis conservé dans une ancre
    # propre à la banque. Les relevés suivants ne le modifient plus.
    solde_ouverture = None
    solde_ouverture_date = None
    try:
        info_solde = extract_bank_opening_balance(raw_bytes, file.filename, file_type)
        solde_ouverture = info_solde.amount
        solde_ouverture_date = info_solde.balance_date
    except Exception:
        info_solde = None
        solde_ouverture = None
        solde_ouverture_date = None
    if solde_ouverture is not None and devise_source:
        solde_ouverture = round(float(solde_ouverture) * taux_conversion, 3)
    if solde_ouverture is None:
        # Repli raisonnable : le relevé commence au début de la période demandée.
        solde_ouverture_date = date_debut

    mouvements = preparer_mouvements_extraits(mouvements)

    # Un Grand Livre Sage ou une mise en page non reconnue peut produire des
    # lignes sans montant : on refuse l'import plutôt que de polluer le reporting.
    total_importe = sum(abs(float(m.get("debit") or 0)) + abs(float(m.get("credit") or 0)) for m in mouvements)
    if total_importe <= 0.0005:
        raise HTTPException(
            status_code=422,
            detail=(
                "Aucun montant n'a pu être extrait de ce fichier : vérifiez qu'il s'agit bien "
                "d'un relevé bancaire (débit/crédit) et non d'un grand livre comptable."
            ),
        )

    with db.get_cursor() as cursor:
        # ─── Contrôle anti-doublon : une période déjà importée pour cette banque ───
        cursor.execute(
            """
            SELECT id, file_name, periode_debut, periode_fin
            FROM tresorerie_imports
            WHERE compte_banque = %s
              AND periode_debut IS NOT NULL
              AND periode_fin IS NOT NULL
              AND (%s IS NULL OR id <> %s)
            ORDER BY periode_debut ASC
            """,
            (code_banque, remplacer_import_id, remplacer_import_id),
        )
        conflits = [
            ligne for ligne in cursor.fetchall()
            if periodes_chevauchent(
                date_debut, date_fin, ligne["periode_debut"], ligne["periode_fin"]
            )
        ]
        if conflits:
            details = " ; ".join(
                f"du {c['periode_debut'].strftime('%d/%m/%Y')} au {c['periode_fin'].strftime('%d/%m/%Y')} "
                f"({c['file_name']})"
                for c in conflits
            )
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Des mouvements existent déjà pour la banque {code_banque} sur une période qui "
                    f"chevauche celle demandée : {details}. Choisissez une période non couverte, "
                    "ou supprimez l'import existant puis recommencez."
                ),
            )

        # Remplacement explicite d'un import erroné (suppression en cascade des mouvements)
        if remplacer_import_id:
            cursor.execute("SELECT id FROM tresorerie_imports WHERE id = %s", (remplacer_import_id,))
            if cursor.fetchone():
                # L'ancre issue de l'import remplacé est retirée elle aussi : le
                # nouveau relevé doit pouvoir fixer son propre solde de départ.
                cursor.execute(
                    "DELETE FROM tresorerie_soldes_ouverture WHERE source_import_id = %s",
                    (remplacer_import_id,),
                )
                cursor.execute("DELETE FROM tresorerie_imports WHERE id = %s", (remplacer_import_id,))

        messages = []
        if hors_periode:
            messages.append(
                f"{len(hors_periode)} mouvement(s) hors période ignoré(s) "
                f"(relevé en contenant davantage)."
            )
        controle = construire_controle_extraction(
            fichier=file.filename,
            format_detecte=extension,
            lignes_source=lignes_source,
            mouvements=mouvements,
            messages=messages,
        )

        cursor.execute(
            """
            INSERT INTO tresorerie_imports
            (compte_banque, periode_debut, periode_fin, file_name, file_type,
             taux_conversion, devise_source, solde_ouverture, solde_ouverture_date,
             created_by_user_id, created_by_username)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                code_banque,
                date_debut,
                date_fin,
                file.filename,
                extension,
                taux_conversion if devise_source else None,
                devise_source,
                solde_ouverture,
                solde_ouverture_date,
                user.get("id"),
                user.get("username"),
            ),
        )
        import_id = cursor.lastrowid

        cursor.executemany(
            """
            INSERT INTO tresorerie_movements
            (import_id, date_operation, reference, libelle, debit, credit, nature_suggeree)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    import_id,
                    mouvement["date_operation"],
                    mouvement.get("reference"),
                    mouvement["libelle"],
                    mouvement["debit"],
                    mouvement["credit"],
                    mouvement.get("nature_suggeree"),
                )
                for mouvement in mouvements
            ],
        )

        entete = _import_avec_totaux(cursor, import_id)

        # ─── Figement de l'ancre de solde ───
        # INSERT IGNORE : l'ancre d'une banque n'est jamais réécrite par un
        # relevé ultérieur. Une banque sans ancre n'en reçoit une que si ce
        # relevé porte un solde réellement lu (jamais un zéro inventé).
        ancre_creee = False
        if solde_ouverture is not None and info_solde is not None and info_solde.amount is not None:
            cursor.execute(
                """
                INSERT IGNORE INTO tresorerie_soldes_ouverture
                (compte_banque, solde, date_solde, source_import_id, source_file_name)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    code_banque,
                    solde_ouverture,
                    solde_ouverture_date or date_debut,
                    import_id,
                    file.filename,
                ),
            )
            ancre_creee = cursor.rowcount == 1

        # Une ancre existe-t-elle pour la banque après cet import ?
        cursor.execute(
            "SELECT solde, date_solde FROM tresorerie_soldes_ouverture WHERE compte_banque = %s",
            (code_banque,),
        )
        ancre_banque = cursor.fetchone()

        cursor.execute(
            """
            SELECT id, import_id, date_operation, reference, libelle, debit, credit,
                   nature, nature_suggeree, classified_by_username, classified_at, created_at
            FROM tresorerie_movements
            WHERE import_id = %s
            ORDER BY date_operation ASC, id ASC
            LIMIT 50
            """,
            (import_id,),
        )
        preview = cursor.fetchall()

    log_audit_action(
        user=user,
        action="import",
        module="tresorerie",
        entity_type="tresorerie_import",
        entity_id=str(import_id),
        detail={
            "file_name": file.filename,
            "compte_banque": code_banque,
            "total_mouvements": len(mouvements),
            "remplace_import_id": remplacer_import_id,
            "solde_ouverture_fige": ancre_creee,
        },
        request=request,
    )
    ws_manager.broadcast("tresorerie", "import", {"id": import_id, "compte_banque": code_banque})

    return {
        "import_batch": entete,
        "total_mouvements": len(mouvements),
        "preview": preview,
        "controle_extraction": controle,
        # Solde de départ à valider/corriger dans la modale de contrôle :
        # on renvoie toujours l'état courant de l'ancre de la banque, qu'elle
        # vienne d'être créée par cet import ou qu'elle existe déjà.
        "solde_ouverture_fige": ancre_creee,
        "solde_ouverture_lu": solde_ouverture if info_solde is not None and info_solde.amount is not None else None,
        "solde_ouverture_date_lue": solde_ouverture_date if info_solde is not None and info_solde.amount is not None else None,
        "solde_ouverture_actuel": float(ancre_banque["solde"]) if ancre_banque else None,
        "solde_ouverture_date_actuelle": ancre_banque["date_solde"] if ancre_banque else None,
        "a_un_solde": ancre_banque is not None,
    }


@router.get(
    "/imports",
    dependencies=[Depends(require_permission_code("tresorerie.read"))],
)
def lister_imports(
    compte_banque: Optional[str] = None,
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
    search: str = "",
    page: int = 1,
    page_size: int = 20,
):
    safe_page = max(1, page)
    safe_size = min(max(1, page_size), 200)
    offset = (safe_page - 1) * safe_size

    conditions = ["1=1"]
    params = []
    if compte_banque:
        conditions.append("i.compte_banque = %s")
        params.append(compte_banque.strip().upper())
    if date_debut:
        conditions.append("COALESCE(i.periode_fin, DATE(i.created_at)) >= %s")
        params.append(date_debut)
    if date_fin:
        conditions.append("COALESCE(i.periode_debut, DATE(i.created_at)) <= %s")
        params.append(date_fin)
    if search.strip():
        conditions.append("i.file_name LIKE %s")
        params.append(f"%{search.strip()}%")
    where = " AND ".join(conditions)

    with db.get_cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM tresorerie_imports i WHERE {where}", params)
        total = int((cursor.fetchone() or {}).get("cnt") or 0)

        cursor.execute(
            f"""
            SELECT i.*,
                   (SELECT COUNT(*) FROM tresorerie_movements m WHERE m.import_id = i.id) AS total_mouvements,
                   (SELECT COALESCE(SUM(m.debit), 0) FROM tresorerie_movements m WHERE m.import_id = i.id) AS total_debit,
                   (SELECT COALESCE(SUM(m.credit), 0) FROM tresorerie_movements m WHERE m.import_id = i.id) AS total_credit,
                   (SELECT COUNT(*) FROM tresorerie_movements m WHERE m.import_id = i.id AND m.nature IS NOT NULL) AS classe_count,
                   (SELECT COUNT(*) FROM tresorerie_movements m WHERE m.import_id = i.id AND m.nature IS NULL) AS non_classe_count
            FROM tresorerie_imports i
            WHERE {where}
            ORDER BY COALESCE(i.periode_fin, DATE(i.created_at)) DESC, i.id DESC
            LIMIT %s OFFSET %s
            """,
            params + [safe_size, offset],
        )
        items = cursor.fetchall()

    return {
        "items": items,
        "total": total,
        "page": safe_page,
        "page_size": safe_size,
        "pages": max(1, math.ceil(total / safe_size)),
    }


@router.get(
    "/imports/{import_id}",
    dependencies=[Depends(require_permission_code("tresorerie.read"))],
)
def get_import(import_id: int):
    with db.get_cursor() as cursor:
        entete = _import_avec_totaux(cursor, import_id)
        if not entete:
            raise HTTPException(status_code=404, detail="Import introuvable")
        stats = _stats_import(cursor, import_id)
    return {"import_batch": entete, "stats": stats}


@router.delete(
    "/imports/{import_id}",
    dependencies=[Depends(require_permission_code("tresorerie.delete"))],
)
def supprimer_import(import_id: int, request: Request, user: dict = Depends(get_current_user)):
    with db.get_cursor() as cursor:
        entete = _import_avec_totaux(cursor, import_id)
        if not entete:
            raise HTTPException(status_code=404, detail="Import introuvable")

        # L'ancre de solde créée par cet import disparaît avec lui : sans son
        # relevé d'origine, le solde de départ n'a plus de justification. Une
        # ancre saisie manuellement (source_import_id vide) est conservée.
        cursor.execute(
            "DELETE FROM tresorerie_soldes_ouverture WHERE source_import_id = %s",
            (import_id,),
        )
        ancres_supprimees = cursor.rowcount

        cursor.execute("DELETE FROM tresorerie_imports WHERE id = %s", (import_id,))

    log_audit_action(
        user=user,
        action="delete",
        module="tresorerie",
        entity_type="tresorerie_import",
        entity_id=str(import_id),
        detail={
            "file_name": entete.get("file_name"),
            "compte_banque": entete.get("compte_banque"),
            "ancres_solde_supprimees": ancres_supprimees,
        },
        request=request,
    )
    ws_manager.broadcast("tresorerie", "delete", {"id": import_id})
    return {"message": "Import supprimé", "id": import_id, "ancres_supprimees": ancres_supprimees}


# ═══════════════════════════════════════════════════════════
# Mouvements et classement
# ═══════════════════════════════════════════════════════════

@router.get(
    "/movements",
    response_model=TresorerieMovementPage,
    dependencies=[Depends(require_permission_code("tresorerie.read"))],
)
def lister_mouvements(
    import_id: Optional[int] = None,
    compte_banque: Optional[str] = None,
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
    nature: Optional[str] = None,
    search: str = "",
    order: str = "asc",
    page: int = 1,
    page_size: int = 50,
):
    safe_page = max(1, page)
    safe_size = min(max(1, page_size), 500)
    offset = (safe_page - 1) * safe_size
    safe_order = "DESC" if str(order).lower() == "desc" else "ASC"

    # Filtres communs (sans la nature) : servent aussi aux compteurs.
    conditions = ["1=1"]
    params = []
    if import_id:
        conditions.append("m.import_id = %s")
        params.append(import_id)
    if compte_banque:
        conditions.append("i.compte_banque = %s")
        params.append(compte_banque.strip().upper())
    frag, frag_params = _conditions_periode("m", date_debut, date_fin)
    conditions.extend(frag)
    params.extend(frag_params)
    if search.strip():
        conditions.append("(m.libelle LIKE %s OR m.reference LIKE %s)")
        params.extend([f"%{search.strip()}%", f"%{search.strip()}%"])
    where_commun = " AND ".join(conditions)

    where = where_commun
    params_page = list(params)
    if nature:
        valeur = str(nature).strip().lower()
        if valeur == "non_classe":
            where += " AND m.nature IS NULL"
        else:
            where += " AND m.nature = %s"
            params_page.append(valeur)

    with db.get_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*) AS cnt
            FROM tresorerie_movements m
            JOIN tresorerie_imports i ON i.id = m.import_id
            WHERE {where}
            """,
            params_page,
        )
        total = int((cursor.fetchone() or {}).get("cnt") or 0)

        cursor.execute(
            f"""
            SELECT m.id, m.import_id, i.compte_banque, m.date_operation, m.reference, m.libelle,
                   m.debit, m.credit, m.nature, m.nature_suggeree,
                   m.classified_by_username, m.classified_at, m.created_at
            FROM tresorerie_movements m
            JOIN tresorerie_imports i ON i.id = m.import_id
            WHERE {where}
            ORDER BY m.date_operation {safe_order}, m.id {safe_order}
            LIMIT %s OFFSET %s
            """,
            params_page + [safe_size, offset],
        )
        items = cursor.fetchall()

        # Compteurs par nature sur le filtre courant (nature exclue)
        cursor.execute(
            f"""
            SELECT COALESCE(m.nature, 'non_classe') AS nature, COUNT(*) AS nb
            FROM tresorerie_movements m
            JOIN tresorerie_imports i ON i.id = m.import_id
            WHERE {where_commun}
            GROUP BY COALESCE(m.nature, 'non_classe')
            """,
            params,
        )
        par_nature = {row["nature"]: int(row["nb"]) for row in cursor.fetchall()}
    for valeur in NATURES_TRESORERIE:
        par_nature.setdefault(valeur, 0)
    par_nature.setdefault("non_classe", 0)

    return {
        "items": items,
        "total": total,
        "page": safe_page,
        "page_size": safe_size,
        "pages": max(1, math.ceil(total / safe_size)),
        "compteurs": par_nature,
    }


@router.put(
    "/movements/bulk-nature",
    response_model=NatureUpdateResponse,
    dependencies=[Depends(require_permission_code("tresorerie.classify"))],
)
def classer_mouvements(
    payload: BulkNatureUpdateRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Classe (ou déclasse si nature = null) un lot de mouvements."""
    try:
        nature = normaliser_nature(payload.nature)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    ids = [int(mid) for mid in (payload.movement_ids or [])]
    if not ids:
        raise HTTPException(status_code=400, detail="Aucun mouvement sélectionné")

    placeholders = ",".join(["%s"] * len(ids))
    with db.get_cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE tresorerie_movements
            SET nature = %s,
                classified_by_user_id = %s,
                classified_by_username = %s,
                classified_at = %s
            WHERE id IN ({placeholders})
            """,
            (nature, user.get("id"), user.get("username"), datetime.now() if nature else None, *ids),
        )
        updated = cursor.rowcount

    log_audit_action(
        user=user,
        action="classify",
        module="tresorerie",
        entity_type="tresorerie_movement",
        entity_id=None,
        detail={"nature": nature, "movement_ids": ids, "updated": updated},
        request=request,
    )
    ws_manager.broadcast("tresorerie", "classify", {"nature": nature, "count": updated})
    return {"updated": updated, "nature": nature}


@router.put(
    "/movements/{movement_id}/nature",
    response_model=NatureUpdateResponse,
    dependencies=[Depends(require_permission_code("tresorerie.classify"))],
)
def classer_mouvement(
    movement_id: int,
    payload: NatureUpdateRequest,
    request: Request,
    user: dict = Depends(get_current_user),
):
    try:
        nature = normaliser_nature(payload.nature)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    with db.get_cursor() as cursor:
        cursor.execute(
            """
            UPDATE tresorerie_movements
            SET nature = %s,
                classified_by_user_id = %s,
                classified_by_username = %s,
                classified_at = %s
            WHERE id = %s
            """,
            (nature, user.get("id"), user.get("username"), datetime.now() if nature else None, movement_id),
        )
        if cursor.rowcount == 0:
            cursor.execute("SELECT id FROM tresorerie_movements WHERE id = %s", (movement_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Mouvement introuvable")

    log_audit_action(
        user=user,
        action="classify",
        module="tresorerie",
        entity_type="tresorerie_movement",
        entity_id=str(movement_id),
        detail={"nature": nature},
        request=request,
    )
    ws_manager.broadcast("tresorerie", "classify", {"id": movement_id, "nature": nature})
    return {"updated": 1, "nature": nature}


# ═══════════════════════════════════════════════════════════
# Reporting
# ═══════════════════════════════════════════════════════════

def _verifier_periode(date_debut: Optional[date], date_fin: Optional[date]) -> None:
    """« Du » ne peut pas être postérieur à « Au » (400 sinon)."""
    if date_debut and date_fin and date_debut > date_fin:
        raise HTTPException(
            status_code=400,
            detail="La date de début doit précéder la date de fin",
        )


def _calculer_reporting(
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
    compte_banque: Optional[str] = None,
) -> dict:
    """Calcul unique du reporting trésorerie (écran et export PDF).

    C'est la seule source de vérité pour les ratios, les soldes et le contrôle :
    GET /reporting et GET /reporting/export-pdf passent tous les deux par ici,
    de sorte que le PDF ne peut pas diverger de l'écran.
    """
    _verifier_periode(date_debut, date_fin)

    conditions = ["1=1"]
    params = []
    if compte_banque:
        conditions.append("i.compte_banque = %s")
        params.append(compte_banque.strip().upper())
    frag, frag_params = _conditions_periode("m", date_debut, date_fin)
    conditions.extend(frag)
    params.extend(frag_params)
    where = " AND ".join(conditions)

    with db.get_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT i.compte_banque, m.nature, m.debit, m.credit
            FROM tresorerie_movements m
            JOIN tresorerie_imports i ON i.id = m.import_id
            WHERE {where}
            """,
            params,
        )
        rows = cursor.fetchall()

        # Contre-vérification SQL indépendante de l'agrégation Python.
        cursor.execute(
            f"""
            SELECT COUNT(*) AS nb,
                   COALESCE(SUM(m.debit), 0) AS debit,
                   COALESCE(SUM(m.credit), 0) AS credit,
                   MAX(m.date_operation) AS derniere_date
            FROM tresorerie_movements m
            JOIN tresorerie_imports i ON i.id = m.import_id
            WHERE {where}
            """,
            params,
        )
        controle_sql = cursor.fetchone() or {}

    # ─── Solde par banque ───
    # L'ancre de solde est figée par banque (lue une seule fois sur le premier
    # import). Le solde affiché reste un cumul : ancre + mouvements jusqu'à la
    # borne « Au ». Le filtre « Du » ne sert qu'aux ratios de la période.
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT compte_banque, solde, date_solde, source_file_name
            FROM tresorerie_soldes_ouverture
            """
        )
        ancres = cursor.fetchall()

    banques = construire_reporting(rows)
    if compte_banque:
        banques = [b for b in banques if b["compte_banque"] == compte_banque.strip().upper()]

    with db.get_cursor() as cursor:
        for banque in banques:
            code = banque["compte_banque"]
            ancre = ancre_de_banque(ancres, code, date_fin)
            if not ancre:
                continue
            depart = demarrer_couverture(ancre)
            if depart is None:
                continue

            borne_fin = " AND m.date_operation <= %s" if date_fin else ""
            borne_fin_params = [date_fin] if date_fin else []

            # Solde de départ de la période = ancre projetée à la veille de « Du ».
            # Sans filtre « Du », c'est l'ancre elle-même. Une période qui commence
            # avant l'ancre n'a pas de solde de départ calculable (n.d.), mais le
            # solde à « Au » reste calculable.
            ouverture = ancre.get("solde")
            ouverture_date = depart
            if date_debut and date_debut < depart:
                ouverture = None
            elif date_debut and date_debut > depart:
                cursor.execute(
                    f"""
                    SELECT COALESCE(SUM(CASE WHEN m.date_operation < %s
                                             THEN m.credit - m.debit ELSE 0 END), 0) AS net_avant
                    FROM tresorerie_movements m
                    JOIN tresorerie_imports i ON i.id = m.import_id
                    WHERE i.compte_banque = %s
                      AND m.date_operation >= %s
                      {borne_fin}
                    """,
                    [date_debut, code, depart] + borne_fin_params,
                )
                net_avant = float((cursor.fetchone() or {}).get("net_avant") or 0)
                ouverture = calculer_solde(ancre.get("solde"), net_avant)
                ouverture_date = date_debut

            # Solde à « Au » : ancre + mouvements depuis l'ancre jusqu'à cette date.
            cursor.execute(
                f"""
                SELECT COALESCE(SUM(m.credit - m.debit), 0) AS net
                FROM tresorerie_movements m
                JOIN tresorerie_imports i ON i.id = m.import_id
                WHERE i.compte_banque = %s
                  AND m.date_operation >= %s
                  {borne_fin}
                """,
                [code, depart] + borne_fin_params,
            )
            net = float((cursor.fetchone() or {}).get("net") or 0)
            banque["solde_ouverture"] = ouverture
            banque["solde_ouverture_date"] = ouverture_date
            banque["solde"] = calculer_solde(ancre.get("solde"), net)

    totaux = totaliser(banques)
    commissions = totaliser_commissions(banques)

    ecart_debit = round(float(controle_sql.get("debit") or 0) - totaux["total_debit"], 3)
    ecart_credit = round(float(controle_sql.get("credit") or 0) - totaux["total_credit"], 3)
    statut = "OK"
    if abs(ecart_debit) > 0.01 or abs(ecart_credit) > 0.01:
        statut = "ERREUR"
    elif totaux["non_classe_count"] > 0:
        statut = "INCOMPLET"

    # ─── Situation arrêtée au ───
    # Date à laquelle les soldes du rapport sont arrêtés. C'est la borne « Au »
    # lorsqu'elle est saisie ; sinon le rapport porte sur tout l'historique et
    # s'arrête donc à la dernière date de mouvement effectivement importée.
    # Sans mouvement du tout, aucune situation ne peut être arrêtée.
    date_arret = date_fin or controle_sql.get("derniere_date")

    return {
        "date_debut": date_debut,
        "date_fin": date_fin,
        "date_arret": date_arret,
        "banques": banques,
        "totaux": totaux,
        "commissions": commissions,
        "controle": {
            "statut": statut,
            "non_classes": totaux["non_classe_count"],
            "ecart_debit": ecart_debit,
            "ecart_credit": ecart_credit,
            "nb_mouvements_sql": int(controle_sql.get("nb") or 0),
            "nb_mouvements_agreges": totaux["nb_mouvements"],
        },
    }


@router.get(
    "/reporting",
    response_model=TresorerieReportingResponse,
    dependencies=[Depends(require_permission_code("tresorerie.report"))],
)
def get_reporting(
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
    compte_banque: Optional[str] = None,
):
    return _calculer_reporting(date_debut, date_fin, compte_banque)


# ═══════════════════════════════════════════════════════════
# Export PDF du reporting trésorerie
# ═══════════════════════════════════════════════════════════

@router.get(
    "/reporting/export-pdf",
    response_class=StreamingResponse,
    summary="Génère et télécharge le rapport PDF du reporting trésorerie",
    dependencies=[Depends(require_permission_code("tresorerie.report"))],
)
def export_reporting_pdf(
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
    compte_banque: Optional[str] = None,
):
    """
    Réutilise le calcul de GET /reporting (`_calculer_reporting`) puis génère
    le PDF via reportlab et le renvoie en streaming.
    """
    from .pdf_export import build_tresorerie_pdf

    rapport = _calculer_reporting(date_debut, date_fin, compte_banque)

    # ── Génération PDF ──
    try:
        pdf_buffer = build_tresorerie_pdf(
            banques=rapport["banques"],
            totaux=rapport["totaux"],
            controle=rapport["controle"],
            date_debut=date_debut,
            date_fin=date_fin,
            date_arret=rapport.get("date_arret"),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la génération du PDF : {exc}") from exc

    # ── Nom du fichier ──
    if date_debut and date_fin:
        suffixe = f"{date_debut}_{date_fin}"
    elif date_debut:
        suffixe = f"depuis_{date_debut}"
    elif date_fin:
        suffixe = f"jusquau_{date_fin}"
    else:
        suffixe = "global"
    filename = f"reporting_tresorerie_{suffixe}.pdf"

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
