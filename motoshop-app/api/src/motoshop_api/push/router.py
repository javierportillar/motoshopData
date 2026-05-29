"""Push notifications - placeholder endpoints (DT-F3-11).

En F3 SOLO se prepara la infraestructura:
  - POST /api/push/subscribe — guarda subscription
  - POST /api/push/unsubscribe — elimina subscription

NO se disparan notificaciones hasta F4 (alertas de quiebre).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from motoshop_api.auth.deps import get_current_user
from motoshop_api.auth.users import User

router = APIRouter(tags=["push"])


@router.post("/api/push/subscribe")
async def push_subscribe(body: dict, _user: User = Depends(get_current_user)) -> dict:
    """Guarda la subscription push del usuario. Placeholder - no persiste aún."""
    # TODO(F4): guardar en DB (app_push_subscriptions) asociado al user
    return {"status": "ok", "message": "Subscription received (placeholder)"}


@router.post("/api/push/unsubscribe")
async def push_unsubscribe(body: dict, _user: User = Depends(get_current_user)) -> dict:
    """Elimina la subscription push del usuario."""
    # TODO(F4): eliminar de app_push_subscriptions
    return {"status": "ok", "message": "Subscription removed (placeholder)"}
