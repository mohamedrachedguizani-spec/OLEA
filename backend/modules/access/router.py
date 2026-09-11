from fastapi import APIRouter, Depends, HTTPException, Request

from database import db
from modules.auth.dependencies import require_permission_code
from modules.audit.service import log_audit_action
from .models import PermissionResponse, RoleResponse, RolePermissionsUpdate, UserRoleUpdate

router = APIRouter(prefix="/access", tags=["Profils et permissions"])


def _role_response(cursor, role):
    cursor.execute(
        "SELECT p.code FROM access_role_permissions rp JOIN access_permissions p ON p.id = rp.permission_id "
        "WHERE rp.role_id = %s ORDER BY p.code", (role["id"],),
    )
    return RoleResponse(**role, permission_codes=[row["code"] for row in cursor.fetchall()])


@router.get("/permissions", response_model=list[PermissionResponse])
def list_permissions(_user=Depends(require_permission_code("admin.roles.read"))):
    with db.get_cursor() as cursor:
        cursor.execute("SELECT id, code, name, module, description FROM access_permissions ORDER BY module, name")
        return cursor.fetchall()


@router.get("/roles", response_model=list[RoleResponse])
def list_roles(_user=Depends(require_permission_code("admin.roles.read"))):
    with db.get_cursor() as cursor:
        cursor.execute("SELECT id, code, name, description, is_system, is_active FROM access_roles ORDER BY is_system DESC, name")
        return [_role_response(cursor, role) for role in cursor.fetchall()]


@router.put("/roles/{role_id}/permissions", response_model=RoleResponse)
def update_role_permissions(
    role_id: int, body: RolePermissionsUpdate, request: Request,
    admin=Depends(require_permission_code("admin.roles.manage")),
):
    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute("SELECT id, code, name, description, is_system, is_active FROM access_roles WHERE id = %s", (role_id,))
            role = cursor.fetchone()
            if not role:
                raise HTTPException(status_code=404, detail="Profil introuvable")
            if role["code"] == "SUPER_ADMIN":
                raise HTTPException(status_code=400, detail="Le profil Super administrateur est protégé")
            unique_codes = sorted(set(body.permission_codes))
            if unique_codes:
                placeholders = ",".join(["%s"] * len(unique_codes))
                cursor.execute(f"SELECT code FROM access_permissions WHERE code IN ({placeholders})", tuple(unique_codes))
                found = {row["code"] for row in cursor.fetchall()}
                missing = sorted(set(unique_codes) - found)
                if missing:
                    raise HTTPException(status_code=400, detail=f"Permissions inconnues : {', '.join(missing)}")
            cursor.execute("DELETE FROM access_role_permissions WHERE role_id = %s", (role_id,))
            for code in unique_codes:
                cursor.execute(
                    "INSERT INTO access_role_permissions (role_id, permission_id) "
                    "SELECT %s, id FROM access_permissions WHERE code = %s", (role_id, code),
                )
            conn.commit()
            result = _role_response(cursor, role)
    log_audit_action(user=admin, action="update_role_permissions", module="access", entity_type="role", entity_id=str(role_id), detail={"permission_codes": unique_codes}, request=request)
    return result


@router.put("/users/{user_id}/role", response_model=dict)
def assign_user_role(
    user_id: int, body: UserRoleUpdate, request: Request,
    admin=Depends(require_permission_code("admin.users.manage")),
):
    with db.get_connection() as conn:
        with db.get_cursor(conn) as cursor:
            cursor.execute("SELECT id, role FROM users WHERE id = %s", (user_id,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Utilisateur introuvable")
            if user["role"] == "superadmin":
                raise HTTPException(status_code=400, detail="Le profil du Superadmin est protégé")
            cursor.execute("SELECT id, code, name FROM access_roles WHERE id = %s AND is_active = TRUE", (body.role_id,))
            role = cursor.fetchone()
            if not role or role["code"] == "SUPER_ADMIN":
                raise HTTPException(status_code=400, detail="Profil invalide")
            cursor.execute(
                "INSERT INTO user_access_roles (user_id, role_id) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE role_id = VALUES(role_id)", (user_id, body.role_id),
            )
            conn.commit()
    log_audit_action(user=admin, action="assign_role", module="access", entity_type="user", entity_id=str(user_id), detail={"role_id": body.role_id, "role_code": role["code"]}, request=request)
    return {"status": "ok", "role": role}
