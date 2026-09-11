from typing import List, Optional
from pydantic import BaseModel, Field


class PermissionResponse(BaseModel):
    id: int
    code: str
    name: str
    module: str
    description: Optional[str] = None


class RoleResponse(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    is_system: bool
    is_active: bool
    permission_codes: List[str] = Field(default_factory=list)


class RolePermissionsUpdate(BaseModel):
    permission_codes: List[str]


class UserRoleUpdate(BaseModel):
    role_id: int
