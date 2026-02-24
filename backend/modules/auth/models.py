# modules/auth/models.py
from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional, List
from enum import Enum
import re


# ─── Enums ───

class RoleEnum(str, Enum):
    superadmin = "superadmin"
    comptable = "comptable"
    financier = "financier"
    dirigeant = "dirigeant"


class ModuleEnum(str, Enum):
    saisie_caisse = "saisie_caisse"
    migration_sage = "migration_sage"
    export_csv = "export_csv"
    sage_bfc = "sage_bfc"


# ─── Auth Schemas ───

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    message: str
    user: "UserResponse"


# ─── User Schemas ───

class UserCreate(BaseModel):
    username: str
    email: str
    full_name: str
    password: str
    role: RoleEnum = RoleEnum.comptable

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError("Le nom d'utilisateur doit contenir au moins 3 caractères")
        if not re.match(r"^[a-zA-Z0-9_.-]+$", v):
            raise ValueError("Le nom d'utilisateur ne peut contenir que des lettres, chiffres, '.', '-' et '_'")
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Le mot de passe doit contenir au moins 6 caractères")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", v):
            raise ValueError("Adresse email invalide")
        return v.lower()


class UserUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[RoleEnum] = None
    is_active: Optional[bool] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", v):
            raise ValueError("Adresse email invalide")
        return v.lower() if v else v


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: RoleEnum
    is_active: bool
    created_at: datetime
    permissions: Optional[List["PermissionResponse"]] = None
    active_sessions: Optional[int] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Le nouveau mot de passe doit contenir au moins 6 caractères")
        return v


class ResetPasswordRequest(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Le nouveau mot de passe doit contenir au moins 6 caractères")
        return v


# ─── Permission Schemas ───

class PermissionSet(BaseModel):
    module_name: ModuleEnum
    can_read: bool = False
    can_write: bool = False
    can_delete: bool = False


class PermissionResponse(BaseModel):
    module_name: str
    can_read: bool
    can_write: bool
    can_delete: bool


class UserPermissionsUpdate(BaseModel):
    permissions: List[PermissionSet]


# Rebuild forward references
UserResponse.model_rebuild()
TokenResponse.model_rebuild()
