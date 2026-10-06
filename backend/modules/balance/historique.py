"""Historique des balances âgées (clients / fournisseurs) enregistrées en base de données.

Chaque génération est conservée telle quelle (JSON complet de l'analyse + colonnes de synthèse pour la liste),
ce qui permet de la consulter plus tard sans réimporter le PDF Sage. Table : balance_agee_reports
(créée par init_balance_tables() dans modules/balance/__init__.py).
"""
import json
import logging
from typing import Any, Dict, Optional

from database import db

logger = logging.getLogger(__name__)
KINDS = ("clients", "fournisseurs")


def _iso(v) -> Optional[str]:
    if v is None:
        return None
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S") if hasattr(v, "hour") else v.strftime("%Y-%m-%d")
    return str(v)


def _vers_dict(modele) -> Dict[str, Any]:
    if hasattr(modele, "model_dump"):      # pydantic v2
        return modele.model_dump()
    return modele.dict()                   # pydantic v1


def _resume(kind: str, d: Dict[str, Any]) -> Dict[str, Any]:
    """Chiffres clés affichés dans la liste (selon le type de balance)."""
    if kind == "clients":
        nb, principal, contre, net = d["nb_clients"], d["total_debiteur"], d["total_crediteur"], d["total_general"]
    else:
        nb, principal, contre, net = d["nb_fournisseurs"], d["total_dettes"], d["total_non_imputes"], d["total_net"]
    return {"nb": nb, "principal": principal, "contre": contre, "net": net,
            "plus90": (d.get("totaux_buckets") or {}).get("+90", 0.0),
            "statut": (d.get("controle") or {}).get("statut")}


def enregistrer(kind: str, data: Dict[str, Any], nom_fichier: Optional[str],
                user_id: Optional[int] = None, username: Optional[str] = None) -> Dict[str, Any]:
    """Insère une balance et renvoie {id, created_at}."""
    if kind not in KINDS:
        raise ValueError(f"Type de balance inconnu : {kind}")
    r = _resume(kind, data)
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO balance_agee_reports
                (kind, date_reference, file_name, nb_tiers, montant_principal, montant_contre, montant_net,
                 montant_plus_90, controle_statut, result_json, created_by_user_id, created_by_username)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (kind, data["date_reference"], (nom_fichier or None) and nom_fichier[:255], r["nb"], r["principal"],
             r["contre"], r["net"], r["plus90"], r["statut"], json.dumps(data, ensure_ascii=False, default=str),
             user_id, (username or None) and username[:64]),
        )
        new_id = cursor.lastrowid
        cursor.execute("SELECT created_at FROM balance_agee_reports WHERE id = %s", (new_id,))
        row = cursor.fetchone()
    return {"id": new_id, "created_at": _iso(row["created_at"]) if row else None}


def lister(kind: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """Balances du type demandé, de la plus récente à la plus ancienne."""
    with db.get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS cnt FROM balance_agee_reports WHERE kind = %s", (kind,))
        total = cursor.fetchone()["cnt"]
        cursor.execute(
            """
            SELECT id, date_reference, file_name, nb_tiers, montant_principal, montant_contre, montant_net,
                   montant_plus_90, controle_statut, created_by_username, created_at
            FROM balance_agee_reports WHERE kind = %s
            ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s
            """,
            (kind, int(limit), int(offset)),
        )
        rows = cursor.fetchall()
    items = [{
        "id": r["id"], "date_reference": _iso(r["date_reference"]), "fichier": r["file_name"], "nb_tiers": r["nb_tiers"],
        "montant_principal": float(r["montant_principal"] or 0), "montant_contre": float(r["montant_contre"] or 0),
        "montant_net": float(r["montant_net"] or 0), "montant_plus_90": float(r["montant_plus_90"] or 0),
        "controle_statut": r["controle_statut"], "genere_par": r["created_by_username"], "genere_le": _iso(r["created_at"]),
    } for r in rows]
    return {"items": items, "total": total}


def charger(kind: str, rapport_id: int) -> Optional[Dict[str, Any]]:
    """Analyse complète d'une balance enregistrée (même structure que la réponse de génération)."""
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT id, file_name, result_json, created_by_username, created_at FROM balance_agee_reports "
            "WHERE id = %s AND kind = %s", (rapport_id, kind))
        row = cursor.fetchone()
    if not row:
        return None
    data = json.loads(row["result_json"])
    data.update({"rapport_id": row["id"], "fichier": row["file_name"],
                 "genere_le": _iso(row["created_at"]), "genere_par": row["created_by_username"]})
    return data


def supprimer(kind: str, rapport_id: int) -> bool:
    """Supprime une balance de l'historique. Renvoie False si elle n'existe pas (ou n'est pas de ce type)."""
    with db.get_cursor() as cursor:
        cursor.execute("DELETE FROM balance_agee_reports WHERE id = %s AND kind = %s", (rapport_id, kind))
        return cursor.rowcount > 0


def enregistrer_resultat(kind: str, result, nom_fichier: Optional[str], user: Optional[dict]):
    """Enregistre le résultat d'une génération et renseigne rapport_id / fichier / genere_le / genere_par.
    Une erreur d'enregistrement ne doit jamais empêcher l'affichage de l'analyse : elle est signalée en avertissement."""
    user = user or {}
    username = user.get("username") or user.get("full_name")
    result.fichier = nom_fichier
    result.genere_par = username
    try:
        info = enregistrer(kind, _vers_dict(result), nom_fichier, user.get("id"), username)
        result.rapport_id = info["id"]
        result.genere_le = info["created_at"]
    except Exception:
        logger.exception("Enregistrement de la balance âgée (%s) impossible", kind)
        result.avertissements = [*(result.avertissements or []),
                                 "Cette balance n'a pas pu être enregistrée dans l'historique (erreur base de données)."]
    return result