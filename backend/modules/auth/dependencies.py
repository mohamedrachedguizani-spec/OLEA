# modules/auth/dependencies.py
"""
Dépendances FastAPI pour l'authentification et l'autorisation.

Stratégie de sécurité :
  - Access token lu depuis le cookie httpOnly "olea_access_token"
  - Aucun token dans le localStorage (protection XSS)
  - Vérification du token_version pour permettre la révocation
  - Le superadmin a toutes les permissions automatiquement
"""

from fastapi import Request, HTTPException, status
from database import db
from .security import decode_access_token
from .models import RoleEnum


# ─── Récupérer l'utilisateur courant ───

def get_current_user(request: Request) -> dict:
    """
    Extrait et valide l'utilisateur depuis le cookie access token.
    Vérifie que :
      1. Le cookie existe
      2. Le JWT est valide et non expiré
      3. L'utilisateur existe en base et est actif
      4. Le token_version correspond (pas de session révoquée)
    """
    token = request.cookies.get("olea_access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Non authentifié — veuillez vous connecter",
        )

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
