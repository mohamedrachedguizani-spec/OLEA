# modules/auth/models.py
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List
from enum import Enum
import re


_PASSWORD_POLICY_REGEX = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9])\S{8,128}$")

# Alignées sur les colonnes de la table `users` (évite un 500 « Data too long »)
USERNAME_MIN_LENGTH, USERNAME_MAX_LENGTH = 3, 50
EMAIL_MAX_LENGTH = 100
FULL_NAME_MIN_LENGTH, FULL_NAME_MAX_LENGTH = 2, 100

_USERNAME_REGEX = re.compile(r"^[a-z0-9_.-]+$")
_EMAIL_REGEX = re.compile(r"^[a-z0-9_.+-]+@[a-z0-9-]+(\.[a-z0-9-]+)+$")


def _validate_password_policy(value: str, label: str = "Le mot de passe") -> str:
    if not _PASSWORD_POLICY_REGEX.match(value):
        raise ValueError(
            f"{label} doit contenir 8 caractères minimum, avec au moins 1 majuscule, 1 minuscule, 1 chiffre et 1 caractère spécial (sans espaces)"
        )
    return value


def _normalize_username(value: str) -> str:
    """Normalise un nom d'utilisateur : retire les espaces parasites puis valide."""
    username = (value or "").strip().lower()
    if len(username) < USERNAME_MIN_LENGTH:
        raise ValueError(
            f"Le nom d'utilisateur doit contenir au moins {USERNAME_MIN_LENGTH} caractères"
        )
    if len(username) > USERNAME_MAX_LENGTH:
        raise ValueError(
            f"Le nom d'utilisateur ne peut pas dépasser {USERNAME_MAX_LENGTH} caractères"
        )
    if not _USERNAME_REGEX.match(username):
        if any(char.isspace() for char in username):
            raise ValueError(
                "Le nom d'utilisateur ne doit pas contenir d'espace — utilisez par exemple 'm.diallo'"
            )
        raise ValueError(
            "Le nom d'utilisateur ne peut contenir que des lettres (sans accent), chiffres, '.', '-' et '_'"
        )
    return username


def _normalize_email(value: str) -> str:
    """Normalise une adresse email : retire les espaces parasites puis valide."""
    email = (value or "").strip().lower()
    if not email:
        raise ValueError("L'adresse email est obligatoire")
    if len(email) > EMAIL_MAX_LENGTH:
        raise ValueError(f"L'adresse email ne peut pas dépasser {EMAIL_MAX_LENGTH} caractères")
    if not _EMAIL_REGEX.match(email):
        raise ValueError(
            "Adresse email invalide — attendu par exemple 'prenom.nom@olea.com' (sans espace ni accent)"
        )
    return email


def _normalize_full_name(value: str) -> str:
    """Nettoie le nom complet et refuse une valeur vide."""
    full_name = " ".join((value or "").split())
    if len(full_name) < FULL_NAME_MIN_LENGTH:
        raise ValueError("Le nom complet est obligatoire")
    if len(full_name) > FULL_NAME_MAX_LENGTH:
        raise ValueError(
            f"Le nom complet ne peut pas dépasser {FULL_NAME_MAX_LENGTH} caractères"
        )
    return full_name


# ─── Enums ───

class RoleEnum(str, Enum):
    superadmin = "superadmin"
    comptable = "comptable"
    financier = "financier"
    dirigeant = "dirigeant"
    consultant = "consultant"
    ressources_humaines = "ressources_humaines"


class ModuleEnum(str, Enum):
    saisie_caisse = "saisie_caisse"
    export_csv = "export_csv"
    saisie_bancaire = "saisie_bancaire"
    sage_bfc = "sage_bfc"
    reporting = "reporting"
    configuration = "configuration"
    rapprochement_bancaire = "rapprochement_bancaire"


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
        return _normalize_username(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_policy(v, "Le mot de passe")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return _normalize_email(v)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str) -> str:
        return _normalize_full_name(v)


class UserUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[RoleEnum] = None
    is_active: Optional[bool] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _normalize_email(v)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _normalize_full_name(v)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: RoleEnum
    is_active: bool
    created_at: datetime
    permissions: Optional[List["PermissionResponse"]] = None
    permission_codes: List[str] = Field(default_factory=list)
    access_role_id: Optional[int] = None
    access_role_code: Optional[str] = None
    access_role_name: Optional[str] = None
    active_sessions: Optional[int] = None


class UserPage(BaseModel):
    items: List[UserResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_policy(v, "Le nouveau mot de passe")


class ResetPasswordRequest(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_password_policy(v, "Le nouveau mot de passe")


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
