# modules/auth/dependencies.py
"""
Dépendances FastAPI pour l'authentification et l'autorisation.

Stratégie de sécurité :
  - Access token lu depuis le cookie httpOnly "olea_access_token"
  - Aucun token dans le localStorage (protection XSS)
  - Vérification du token_version pour permettre la révocation
  - Le superadmin a toutes les permissions automatiquement

Performance :
  - Vérification JWT (cryptographique) sans DB = chemin rapide
  - Requête DB uniquement pour vérifier is_active et token_version
  - Le pool de connexions évite le coût d'ouverture/fermeture à chaque appel
"""

from fastapi import Request, HTTPException, status
from database import db
from .security import decode_access_token
from .models import RoleEnum


# ─── Récupérer l'utilisateur courant ───

def get_current_user(request: Request) -> dict:
    """
    Extrait et valide l'utilisateur depuis le cookie access token.
    
    Chemin rapide (pas de DB) :
      1. Cookie présent
      2. Signature JWT valide
      3. Token non expiré
    
    Chemin DB (1 SELECT léger sur index PRIMARY KEY) :
      4. L'utilisateur est actif
      5. Le token_version correspond (session non révoquée)
    """
    token = request.cookies.get("olea_access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Non authentifié — veuillez vous connecter",
        )

    # ─ Étape 1 : vérification cryptographique pure (0 DB) ─
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token malformé",
        )

    # ─ Étape 2 : vérification DB (1 SELECT sur PRIMARY KEY = très rapide) ─
    # Nécessaire pour détecter : révocation, désactivation, suppression
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT id, username, email, full_name, role, is_active, token_version "
            "FROM users WHERE id = %s",
            (int(user_id),),
        )
        user = cursor.fetchone()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur introuvable",
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé — contactez l'administrateur",
        )

    # Vérifier le token_version (permet la révocation sans stocker les tokens)
    if payload.get("tv") != user["token_version"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session révoquée — veuillez vous reconnecter",
        )

    return user


# ─── Vérifier le rôle ───

def require_role(*roles: RoleEnum):
    """
    Factory de dépendance : exige que l'utilisateur ait l'un des rôles spécifiés.
    Usage : Depends(require_role(RoleEnum.superadmin))
    """
    allowed = [r.value for r in roles]

    def checker(request: Request) -> dict:
        user = get_current_user(request)
        if user["role"] not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accès interdit — rôle requis : {', '.join(allowed)}",
            )
        return user

    return checker


# ─── Vérifier les permissions par module ───

def require_permission(module_name: str, action: str = "read"):
    """
    Factory de dépendance : exige une permission spécifique sur un module.
    Le superadmin a automatiquement toutes les permissions.

    Usage : Depends(require_permission("saisie_caisse", "write"))

    Actions possibles : "read", "write", "delete"
    """
    column_map = {
        "read": "can_read",
        "write": "can_write",
        "delete": "can_delete",
    }
    column = column_map.get(action, "can_read")

    def checker(request: Request) -> dict:
        user = get_current_user(request)

        # Le superadmin a accès à tout
        if user["role"] == "superadmin":
            return user

        with db.get_cursor() as cursor:
            cursor.execute(
                f"SELECT {column} FROM user_permissions "
                "WHERE user_id = %s AND module_name = %s",
                (user["id"], module_name),
            )
            perm = cursor.fetchone()

        if not perm or not perm[column]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accès interdit au module '{module_name}' (action : {action})",
            )

        return user

    return checker
