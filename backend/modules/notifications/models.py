from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel
from enum import Enum


class SeverityEnum(str, Enum):
    critical = "critical"
    warning = "warning"
    info = "info"
    success = "success"


class NotificationItem(BaseModel):
    id: int
    user_id: int
    type: str
    module: str
    severity: SeverityEnum
    title: str
    message: str
    is_read: bool
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime


class NotificationPage(BaseModel):
    items: List[NotificationItem]
    total: int
    unread: int


class UnreadCountResponse(BaseModel):
    count: int
