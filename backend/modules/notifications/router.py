from fastapi import APIRouter, Depends, Query, HTTPException

from modules.auth.dependencies import get_current_user
from .models import NotificationPage, UnreadCountResponse
from . import service


router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=NotificationPage)
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    user: dict = Depends(get_current_user),
):
    """Liste des notifications filtrées par permissions module."""
    data = service.get_user_notifications(
        user_id=user["id"],
        user_role=user["role"],
        limit=limit,
        offset=offset,
        unread_only=unread_only,
    )
    return data


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(user: dict = Depends(get_current_user)):
    """Compteur de notifications non lues."""
    count = service.get_unread_count(user["id"], user["role"])
    return {"count": count}


@router.put("/{notification_id}/read")
def mark_read(notification_id: int, user: dict = Depends(get_current_user)):
    """Marquer une notification comme lue."""
    ok = service.mark_as_read(notification_id, user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Notification introuvable")
    return {"ok": True}


@router.put("/read-all")
def mark_all_read(user: dict = Depends(get_current_user)):
    """Marquer toutes les notifications comme lues."""
    count = service.mark_all_read(user["id"], user["role"])
    return {"marked": count}


@router.delete("/{notification_id}")
def delete_notification(notification_id: int, user: dict = Depends(get_current_user)):
    """Supprimer une notification."""
    ok = service.delete_notification(notification_id, user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Notification introuvable")
    return {"ok": True}
