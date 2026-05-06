# modules/export_csv/router.py
import csv
import io
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request

from database import db
from modules.auth.dependencies import get_current_user, restrict_superadmin
from modules.audit.service import log_audit_action

router = APIRouter(
    tags=["Export CSV"],
    responses={404: {"description": "Non trouvé"}},
    dependencies=[Depends(restrict_superadmin("export_csv"))],
)


# ═══════════════════════════════════════════════════════════
# 1. Export CSV Sage
# ═══════════════════════════════════════════════════════════

@router.get("/export-csv/")
def export_csv(
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
    request: Request = None,
    user: dict = Depends(get_current_user),
):
    """Exporter les écritures Sage au format CSV compatible Sage"""
    with db.get_cursor() as cursor:
        query = "SELECT * FROM ecritures_sage WHERE 1=1"
        params = []

        if date_debut:
            query += " AND date_compta >= %s"
            params.append(date_debut)

        if date_fin:
            query += " AND date_compta <= %s"
            params.append(date_fin)

        query += " ORDER BY date_compta ASC, id ASC"
        cursor.execute(query, params)
        ecritures = cursor.fetchall()

    # Créer le CSV en mémoire avec BOM UTF-8 pour Excel
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')

    # En-tête
    writer.writerow([
        'Societe', 'Journal', 'Date compta', 'Compte', 'Tiers',
        'Montant debit', 'Montant credit', 'Section analytique',
        'Numero de piece', 'Libelle ecriture', 'Devise', 'Type de piece',
    ])

    # Données
    for ecriture in ecritures:
        writer.writerow([
            ecriture['societe'],
            ecriture['journal'],
            ecriture['date_compta'].strftime('%d/%m/%Y'),
            ecriture['compte'],
            ecriture['tiers'] or '',
            str(ecriture['montant_debit']).replace('.', ','),
            str(ecriture['montant_credit']).replace('.', ','),
            ecriture['section_analytique'] or '',
            ecriture['numero_piece'],
            ecriture['libelle_ecriture'],
            ecriture['devise'],
            ecriture['type_piece'],
        ])

    output.seek(0)
    log_audit_action(
        user=user,
        action="export",
        module="export_csv",
        entity_type="ecritures_sage",
        entity_id=None,
        detail={"date_debut": str(date_debut) if date_debut else None, "date_fin": str(date_fin) if date_fin else None},
        request=request,
    )
    return {
        "filename": f"export_sage_{date.today().strftime('%Y%m%d')}.csv",
        "content": output.getvalue(),
    }


# ═══════════════════════════════════════════════════════════
# 2. Export Brouillard de Caisse
# ═══════════════════════════════════════════════════════════

@router.get("/export-brouillard-caisse/")
def export_brouillard_caisse(
    date_debut: Optional[date] = None,
    date_fin: Optional[date] = None,
    request: Request = None,
    user: dict = Depends(get_current_user),
):
    """Exporter le brouillard de caisse au format CSV avec solde calculé"""
    with db.get_cursor() as cursor:
        # Solde initial
        solde_initial = 0
        date_solde_initial = None
        if date_debut:
            cursor.execute("""
                SELECT solde
                FROM ecritures_caisse
                WHERE date_ecriture < %s
                ORDER BY date_ecriture DESC, id DESC
                LIMIT 1
            """, (date_debut,))
            result = cursor.fetchone()
            solde_initial = float(result['solde']) if result else 0
            date_solde_initial = date_debut - timedelta(days=1)

        # Écritures de la période
        query = "SELECT * FROM ecritures_caisse WHERE 1=1"
        params = []

        if date_debut:
            query += " AND date_ecriture >= %s"
            params.append(date_debut)

        if date_fin:
            query += " AND date_ecriture <= %s"
            params.append(date_fin)

        query += " ORDER BY date_ecriture ASC, id ASC"
        cursor.execute(query, params)
        ecritures = cursor.fetchall()

    # CSV avec BOM UTF-8
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')

    writer.writerow([
        'Date écriture', 'Libellé écriture', 'Débit', 'Crédit', 'Solde',
    ])

    solde_courant = solde_initial
    if date_debut and solde_initial != 0:
        writer.writerow([
            date_solde_initial.strftime('%d/%m/%Y'),
            '*** SOLDE INITIAL ***',
            '',
            '',
            str(solde_initial).replace('.', ','),
        ])

    for ecriture in ecritures:
        solde_courant = float(ecriture['solde'])
        writer.writerow([
            ecriture['date_ecriture'].strftime('%d/%m/%Y'),
            ecriture['libelle_ecriture'],
            str(ecriture['debit']).replace('.', ',') if ecriture['debit'] > 0 else '',
            str(ecriture['credit']).replace('.', ',') if ecriture['credit'] > 0 else '',
            str(round(solde_courant, 3)).replace('.', ','),
        ])

    total_debit = sum(float(e['debit']) for e in ecritures)
    total_credit = sum(float(e['credit']) for e in ecritures)

    output.seek(0)
    log_audit_action(
        user=user,
        action="export",
        module="export_csv",
        entity_type="brouillard_caisse",
        entity_id=None,
        detail={"date_debut": str(date_debut) if date_debut else None, "date_fin": str(date_fin) if date_fin else None},
        request=request,
    )

    if date_debut:
        mois = date_debut.strftime('%m')
        annee = date_debut.strftime('%y')
    else:
        mois = date.today().strftime('%m')
        annee = date.today().strftime('%y')

    filename = f"Brouillard_caisse_{mois}_{annee}.csv"

    return {
        "filename": filename,
        "content": output.getvalue(),
        "stats": {
            "nb_ecritures": len(ecritures),
            "total_debit": round(total_debit, 3),
            "total_credit": round(total_credit, 3),
            "solde_initial": round(solde_initial, 3),
            "solde_final": round(solde_courant, 3),
        },
    }
