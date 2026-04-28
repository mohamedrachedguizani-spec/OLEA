# modules/auth/router.py
"""
Routes d'authentification et de gestion des utilisateurs.

Sécurité :
  - Access token (15 min) + Refresh token (7 jours) en cookies httpOnly
  - Aucun token dans localStorage (protection XSS)
  - Refresh token signé avec une clé différente (jamais stocké en DB)
  - Révocation via token_version (incrémenter = invalider toutes les sessions)
  - Le superadmin peut créer des utilisateurs et attribuer des permissions
"""

import os
import hashlib
import time
import threading
from typing import List

from fastapi import APIRouter, HTTPException, Request, Response, Depends, status

from database import db
from .models import (
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserUpdate,
    UserResponse,
    ChangePasswordRequest,
    ResetPasswordRequest,
    PermissionResponse,
    UserPermissionsUpdate,
    RoleEnum,
)
from .security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
    IS_PRODUCTION,
)
from .dependencies import get_current_user, require_role

router = APIRouter(
    prefix="/auth",
    tags=["Authentification"],
    responses={401: {"description": "Non authentifié"}},
)


# ════════════════════════════════════════════════════════════
#  Protection brute-force login (in-memory)
# ════════════════════════════════════════════════════════════

_LOGIN_MAX_ATTEMPTS = int(os.getenv("AUTH_LOGIN_MAX_ATTEMPTS", "5"))
_LOGIN_BLOCK_SECONDS = int(os.getenv("AUTH_LOGIN_BLOCK_SECONDS", "120"))
_LOGIN_ATTEMPTS: dict[str, dict[str, float]] = {}
_LOGIN_ATTEMPTS_LOCK = threading.Lock()


def _login_attempts_key(username: str, ip: str) -> str:
    return f"{username.strip().lower()}|{ip}"


def _cleanup_login_attempts_locked(now: float):
    stale_keys = []
    for key, entry in _LOGIN_ATTEMPTS.items():
        blocked_until = float(entry.get("blocked_until", 0.0) or 0.0)
        last_attempt = float(entry.get("last_attempt", 0.0) or 0.0)
        if blocked_until <= now and (now - last_attempt) > (_LOGIN_BLOCK_SECONDS * 3):
            stale_keys.append(key)
    for key in stale_keys:
        _LOGIN_ATTEMPTS.pop(key, None)


def _get_login_block_remaining(username: str, ip: str) -> int:
    now = time.monotonic()
    key = _login_attempts_key(username, ip)
    with _LOGIN_ATTEMPTS_LOCK:
        entry = _LOGIN_ATTEMPTS.get(key)
        if not entry:
            return 0
        blocked_until = float(entry.get("blocked_until", 0.0) or 0.0)
        if blocked_until <= now:
            return 0
        return max(1, int(blocked_until - now))


def _register_login_failure(username: str, ip: str):
    now = time.monotonic()
    key = _login_attempts_key(username, ip)
    with _LOGIN_ATTEMPTS_LOCK:
        _cleanup_login_attempts_locked(now)

        entry = _LOGIN_ATTEMPTS.get(key)
        if not entry:
            entry = {"count": 0.0, "last_attempt": now, "blocked_until": 0.0}
            _LOGIN_ATTEMPTS[key] = entry

        blocked_until = float(entry.get("blocked_until", 0.0) or 0.0)
        if blocked_until > now:
            return

        last_attempt = float(entry.get("last_attempt", 0.0) or 0.0)
        # Fenêtre glissante simplifiée : reset du compteur si inactivité >= durée de blocage
        if (now - last_attempt) >= _LOGIN_BLOCK_SECONDS:
            entry["count"] = 0.0

        entry["count"] = float(entry.get("count", 0.0) or 0.0) + 1.0
        entry["last_attempt"] = now

        if int(entry["count"]) >= _LOGIN_MAX_ATTEMPTS:
            entry["blocked_until"] = now + _LOGIN_BLOCK_SECONDS
            entry["count"] = 0.0


def _clear_login_failures(username: str, ip: str):
    key = _login_attempts_key(username, ip)
    with _LOGIN_ATTEMPTS_LOCK:
        _LOGIN_ATTEMPTS.pop(key, None)


# ════════════════════════════════════════════════════════════
#  Helpers : cookies
# ════════════════════════════════════════════════════════════

def _set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    """Place les tokens dans des cookies httpOnly sécurisés."""
    response.set_cookie(
        key="olea_access_token",
        value=access_token,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="olea_refresh_token",
        value=refresh_token,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",
    )


def _clear_auth_cookies(response: Response):
    """Supprime les cookies d'authentification."""
    response.delete_cookie("olea_access_token", path="/", samesite="lax", secure=IS_PRODUCTION)
    response.delete_cookie("olea_refresh_token", path="/", samesite="lax", secure=IS_PRODUCTION)


def _fetch_user_permissions(cursor, user_id: int) -> List[PermissionResponse]:
    """Charge les permissions d'un utilisateur."""
    cursor.execute(
        "SELECT module_name, can_read, can_write, can_delete "
        "FROM user_permissions WHERE user_id = %s",
        (user_id,),
    )
    return [PermissionResponse(**row) for row in cursor.fetchall()]


def _build_user_response(user: dict, permissions: list = None, active_sessions: int = None) -> UserResponse:
    """Construit un UserResponse à partir d'un row dict."""
    return UserResponse(
        id=user["id"],
        username=user["username"],
        email=user["email"],
        full_name=user["full_name"],
        role=user["role"],
        is_active=bool(user["is_active"]),
        created_at=user["created_at"],
        permissions=permissions,
        active_sessions=active_sessions,
    )


def _make_session_key(user_id: int, token_version: int, ip: str, ua: str) -> str:
    """Génère une clé unique de 64 caractères pour identifier une session (user + appareil)."""
    raw = f"{user_id}:{token_version}:{ip}:{ua[:200]}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _count_active_sessions(cursor, user_id: int) -> int:
    """Compte les sessions actives d'un utilisateur (visibles dans les 45 dernières secondes)."""
    cursor.execute(
        "SELECT COUNT(*) as cnt FROM user_sessions us "
        "JOIN users u ON u.id = us.user_id "
        "WHERE us.user_id = %s AND us.token_version = u.token_version "
        "AND us.last_seen_at > NOW() - INTERVAL 45 SECOND",
        (user_id,),
    )
    row = cursor.fetchone()
    return row["cnt"] if row else 0


# ════════════════════════════════════════════════════════════
#  LOGIN / LOGOUT / REFRESH
# ════════════════════════════════════════════════════════════

@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, response: Response):
    """
    Authentifie un utilisateur et place les tokens dans des cookies httpOnly.
    Aucun token n'est renvoyé dans le corps de la réponse.
    """
    username = body.username.lower().strip()
    ip = request.client.host if request.client else "unknown"

    block_remaining = _get_login_block_remaining(username, ip)
    if block_remaining > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Trop de tentatives de connexion. Réessayez dans {block_remaining} secondes.",
        )

    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute(
                "SELECT id, username, email, full_name, role, is_active, "
                "hashed_password, token_version, created_at "
                "FROM users WHERE username = %s",
                (username,),
            )
            user = cursor.fetchone()

    if not user or not verify_password(body.password, user["hashed_password"]):
        _register_login_failure(username, ip)
        block_remaining = _get_login_block_remaining(username, ip)
        if block_remaining > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Trop de tentatives de connexion. Réessayez dans {block_remaining} secondes.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom d'utilisateur ou mot de passe incorrect",
        )

    _clear_login_failures(username, ip)

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte désactivé — contactez l'administrateur",
        )

    # Générer les tokens
    access = create_access_token(user["id"], user["username"], user["role"], user["token_version"])
    refresh = create_refresh_token(user["id"], user["token_version"])

    # Les placer dans les cookies httpOnly
    _set_auth_cookies(response, access, refresh)

    # Charger les permissions et enregistrer la session
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")[:500]
    session_key = _make_session_key(user["id"], user["token_version"], ip, ua)
    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            permissions = _fetch_user_permissions(cursor, user["id"])
            cursor.execute(
                "INSERT INTO user_sessions (user_id, token_version, ip_address, user_agent, session_key) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE last_seen_at = NOW()",
                (user["id"], user["token_version"], ip, ua, session_key),
            )
            conn.commit()

    return TokenResponse(
        message="Connexion réussie",
        user=_build_user_response(user, permissions),
    )


@router.get("/session-check")
def session_check(request: Request):
    """
    Vérification légère de la validité de la session.
    Utilisé par le heartbeat frontend pour détecter en temps réel
    les révocations, désactivations et suppressions.
    Retourne 200 si la session est valide, 401/403 sinon.
    Met à jour last_seen_at pour le tracking des sessions actives.
    """
    user = get_current_user(request)
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")[:500]
    session_key = _make_session_key(user["id"], user["token_version"], ip, ua)
    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute(
                "INSERT INTO user_sessions (user_id, token_version, ip_address, user_agent, session_key) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE last_seen_at = NOW()",
                (user["id"], user["token_version"], ip, ua, session_key),
            )
            conn.commit()
    return {"valid": True}


@router.post("/logout")
def logout(request: Request, response: Response):
    """Déconnexion : supprime les cookies d'authentification et ferme la session."""
    try:
        user = get_current_user(request)
        ip = request.client.host if request.client else "unknown"
        ua = request.headers.get("user-agent", "")[:500]
        session_key = _make_session_key(user["id"], user["token_version"], ip, ua)
        with db.get_connection() as conn:
            with db.get_cursor(conn) as cursor:
                cursor.execute(
                    "UPDATE user_sessions SET last_seen_at = '2000-01-01 00:00:00' "
                    "WHERE session_key = %s",
                    (session_key,),
                )
                conn.commit()
    except Exception:
        pass  # Token déjà expiré ou invalide — on supprime quand même les cookies
    _clear_auth_cookies(response)
    return {"message": "Déconnexion réussie"}


@router.post("/refresh", response_model=TokenResponse)
def refresh_tokens(request: Request, response: Response):
    """
    Rafraîchit la paire access/refresh token.

    Fonctionnement :
      1. Lit le refresh token depuis le cookie httpOnly
      2. Vérifie la signature (clé secrète différente de l'access token)
      3. Vérifie que le token_version correspond (non révoqué)
      4. Génère une nouvelle paire de tokens (rotation)
      5. Place les nouveaux tokens dans les cookies
    """
    token = request.cookies.get("olea_refresh_token")
    if not token:
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token manquant — veuillez vous reconnecter",
        )

    payload = decode_refresh_token(token)
    if not payload:
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalide ou expiré",
        )

    user_id = int(payload["sub"])
    token_version = payload.get("tv")

    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute(
                "SELECT id, username, email, full_name, role, is_active, "
                "token_version, created_at FROM users WHERE id = %s",
                (user_id,),
            )
            user = cursor.fetchone()

    if not user or not user["is_active"]:
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur introuvable ou désactivé",
        )

    # Vérifier le token_version (révocation sans stockage en DB)
    if token_version != user["token_version"]:
        _clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session révoquée — veuillez vous reconnecter",
        )

    # Rotation : générer une nouvelle paire
    new_access = create_access_token(user["id"], user["username"], user["role"], user["token_version"])
    new_refresh = create_refresh_token(user["id"], user["token_version"])
    _set_auth_cookies(response, new_access, new_refresh)

    with db.get_cursor() as cursor:
        permissions = _fetch_user_permissions(cursor, user["id"])

    return TokenResponse(
        message="Tokens rafraîchis",
        user=_build_user_response(user, permissions),
    )


# ════════════════════════════════════════════════════════════
#  PROFIL UTILISATEUR COURANT
# ════════════════════════════════════════════════════════════

@router.get("/me", response_model=UserResponse)
def get_me(request: Request):
    """Retourne les infos de l'utilisateur connecté avec ses permissions."""
    user = get_current_user(request)

    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute(
                "SELECT id, username, email, full_name, role, is_active, created_at "
                "FROM users WHERE id = %s",
                (user["id"],),
            )
            user_data = cursor.fetchone()
            permissions = _fetch_user_permissions(cursor, user["id"])

    return _build_user_response(user_data, permissions)


@router.put("/me/password")
def change_my_password(body: ChangePasswordRequest, request: Request, response: Response):
    """
    Change le mot de passe de l'utilisateur connecté.
    Incrémente le token_version pour invalider toutes les autres sessions.
    """
    user = get_current_user(request)

    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute(
                "SELECT hashed_password, token_version FROM users WHERE id = %s",
                (user["id"],),
            )
            row = cursor.fetchone()

            if not verify_password(body.current_password, row["hashed_password"]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Mot de passe actuel incorrect",
                )

            new_hash = hash_password(body.new_password)
            new_tv = row["token_version"] + 1

            cursor.execute(
                "UPDATE users SET hashed_password = %s, token_version = %s WHERE id = %s",
                (new_hash, new_tv, user["id"]),
            )
            conn.commit()

    # Regénérer les tokens avec le nouveau token_version
    access = create_access_token(user["id"], user["username"], user["role"], new_tv)
    refresh = create_refresh_token(user["id"], new_tv)
    _set_auth_cookies(response, access, refresh)

    return {"message": "Mot de passe modifié avec succès"}


# ════════════════════════════════════════════════════════════
#  GESTION DES UTILISATEURS (superadmin uniquement)
# ════════════════════════════════════════════════════════════

@router.get("/users", response_model=List[UserResponse])
def list_users(
    request: Request,
    admin: dict = Depends(require_role(RoleEnum.superadmin)),
):
    """Liste tous les utilisateurs (superadmin uniquement)."""
    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute(
                "SELECT id, username, email, full_name, role, is_active, created_at "
                "FROM users ORDER BY created_at DESC"
            )
            users = cursor.fetchall()

            result = []
            for u in users:
                permissions = _fetch_user_permissions(cursor, u["id"])
                active_sessions = _count_active_sessions(cursor, u["id"])
                result.append(_build_user_response(u, permissions, active_sessions))

    return result


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    request: Request,
    admin: dict = Depends(require_role(RoleEnum.superadmin)),
):
    """Crée un nouvel utilisateur (superadmin uniquement)."""
    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            # Vérifier l'unicité username / email
            cursor.execute(
                "SELECT id FROM users WHERE username = %s OR email = %s",
                (body.username, body.email),
            )
            if cursor.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Un utilisateur avec ce nom ou cet email existe déjà",
                )

            hashed = hash_password(body.password)
            cursor.execute(
                "INSERT INTO users (username, email, full_name, hashed_password, role) "
                "VALUES (%s, %s, %s, %s, %s)",
                (body.username, body.email, body.full_name, hashed, body.role.value),
            )
            conn.commit()
            user_id = cursor.lastrowid

            cursor.execute(
                "SELECT id, username, email, full_name, role, is_active, created_at "
                "FROM users WHERE id = %s",
                (user_id,),
            )
            new_user = cursor.fetchone()

    return _build_user_response(new_user, [])


@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    request: Request,
    admin: dict = Depends(require_role(RoleEnum.superadmin)),
):
    """Détails d'un utilisateur (superadmin uniquement)."""
    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute(
                "SELECT id, username, email, full_name, role, is_active, created_at "
                "FROM users WHERE id = %s",
                (user_id,),
            )
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

            permissions = _fetch_user_permissions(cursor, user_id)

    return _build_user_response(user, permissions)


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    body: UserUpdate,
    request: Request,
    admin: dict = Depends(require_role(RoleEnum.superadmin)),
):
    """Met à jour un utilisateur (superadmin uniquement)."""
    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

            # Construire la requête de mise à jour dynamiquement
            updates = []
            params = []
            if body.email is not None:
                # Vérifier l'unicité de l'email
                cursor.execute(
                    "SELECT id FROM users WHERE email = %s AND id != %s",
                    (body.email, user_id),
                )
                if cursor.fetchone():
                    raise HTTPException(status_code=409, detail="Cet email est déjà utilisé")
                updates.append("email = %s")
                params.append(body.email)
            if body.full_name is not None:
                updates.append("full_name = %s")
                params.append(body.full_name)
            if body.role is not None:
                updates.append("role = %s")
                params.append(body.role.value)
            if body.is_active is not None:
                updates.append("is_active = %s")
                params.append(body.is_active)

            if not updates:
                raise HTTPException(status_code=400, detail="Aucune modification fournie")

            params.append(user_id)
            cursor.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = %s",
                tuple(params),
            )
            conn.commit()

            cursor.execute(
                "SELECT id, username, email, full_name, role, is_active, created_at "
                "FROM users WHERE id = %s",
                (user_id,),
            )
            updated = cursor.fetchone()
            permissions = _fetch_user_permissions(cursor, user_id)

    return _build_user_response(updated, permissions)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    admin: dict = Depends(require_role(RoleEnum.superadmin)),
):
    """
    Désactive un utilisateur (soft delete) et révoque ses sessions.
    Le superadmin ne peut pas se supprimer lui-même.
    """
    if admin["id"] == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas désactiver votre propre compte",
        )

    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

            # Désactiver + incrémenter token_version pour révoquer les sessions
            cursor.execute(
                "UPDATE users SET is_active = FALSE, token_version = token_version + 1 "
                "WHERE id = %s",
                (user_id,),
            )
            conn.commit()

    return {"message": "Utilisateur désactivé avec succès"}


@router.post("/users/{user_id}/activate")
def activate_user(
    user_id: int,
    request: Request,
    admin: dict = Depends(require_role(RoleEnum.superadmin)),
):
    """
    Réactive un utilisateur précédemment désactivé.
    """
    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute(
                "SELECT id, is_active FROM users WHERE id = %s", (user_id,)
            )
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

            if user["is_active"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cet utilisateur est déjà actif",
                )

            cursor.execute(
                "UPDATE users SET is_active = TRUE WHERE id = %s",
                (user_id,),
            )
            conn.commit()

    return {"message": "Utilisateur activé avec succès"}


@router.delete("/users/{user_id}/permanent")
def permanent_delete_user(
    user_id: int,
    request: Request,
    admin: dict = Depends(require_role(RoleEnum.superadmin)),
):
    """
    Supprime définitivement un utilisateur et toutes ses données associées.
    Le superadmin ne peut pas se supprimer lui-même.
    Cette action est irréversible.
    """
    if admin["id"] == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas supprimer votre propre compte",
        )

    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute("SELECT id, role FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

            if user["role"] == "superadmin":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Impossible de supprimer un superadmin",
                )

            # Supprimer les permissions associées
            cursor.execute(
                "DELETE FROM user_permissions WHERE user_id = %s", (user_id,)
            )
            # Supprimer l'utilisateur
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            conn.commit()

    return {"message": "Utilisateur supprimé définitivement"}


@router.post("/users/{user_id}/revoke")
def revoke_user_sessions(
    user_id: int,
    request: Request,
    admin: dict = Depends(require_role(RoleEnum.superadmin)),
):
    """
    Révoque toutes les sessions d'un utilisateur en incrémentant son token_version.
    Les tokens existants deviennent immédiatement invalides sans les stocker en DB.
    """
    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

            cursor.execute(
                "UPDATE users SET token_version = token_version + 1 WHERE id = %s",
                (user_id,),
            )
            conn.commit()

    return {"message": "Toutes les sessions de l'utilisateur ont été révoquées"}


@router.put("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    body: ResetPasswordRequest,
    request: Request,
    admin: dict = Depends(require_role(RoleEnum.superadmin)),
):
    """
    Réinitialise le mot de passe d'un utilisateur (superadmin uniquement).
    Révoque aussi toutes les sessions existantes.
    """
    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

            new_hash = hash_password(body.new_password)
            cursor.execute(
                "UPDATE users SET hashed_password = %s, token_version = token_version + 1 "
                "WHERE id = %s",
                (new_hash, user_id),
            )
            conn.commit()

    return {"message": "Mot de passe réinitialisé avec succès"}


# ════════════════════════════════════════════════════════════
#  GESTION DES PERMISSIONS (superadmin uniquement)
# ════════════════════════════════════════════════════════════

@router.get("/users/{user_id}/permissions", response_model=List[PermissionResponse])
def get_user_permissions(
    user_id: int,
    request: Request,
    admin: dict = Depends(require_role(RoleEnum.superadmin)),
):
    """Récupère les permissions d'un utilisateur."""
    with db.get_cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

        return _fetch_user_permissions(cursor, user_id)


@router.put("/users/{user_id}/permissions", response_model=List[PermissionResponse])
def set_user_permissions(
    user_id: int,
    body: UserPermissionsUpdate,
    request: Request,
    admin: dict = Depends(require_role(RoleEnum.superadmin)),
):
    """
    Définit les permissions d'un utilisateur sur les modules de l'application.
    Remplace toutes les permissions existantes (upsert).

    Modules disponibles : saisie_caisse, migration_sage, export_csv, sage_bfc, reporting, configuration
    Actions : can_read, can_write, can_delete
    """
    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute("SELECT id, role FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

            if user["role"] == "superadmin":
                raise HTTPException(
                    status_code=400,
                    detail="Le superadmin a toutes les permissions par défaut",
                )

            # Supprimer les anciennes permissions
            cursor.execute("DELETE FROM user_permissions WHERE user_id = %s", (user_id,))

            # Insérer les nouvelles
            for perm in body.permissions:
                cursor.execute(
                    "INSERT INTO user_permissions (user_id, module_name, can_read, can_write, can_delete) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (user_id, perm.module_name.value, perm.can_read, perm.can_write, perm.can_delete),
                )

            conn.commit()

            return _fetch_user_permissions(cursor, user_id)
