from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel


class AuditLogItem(BaseModel):
    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    action: str
    module: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: List[AuditLogItem]
    total: int
    page: int
    page_size: int
    pages: int
