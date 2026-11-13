from fastapi import APIRouter, Depends

from ..security import current_user
from ..services.opportunities import list_reminders

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.get("")
def get_reminders(user: dict = Depends(current_user)) -> dict:
    return {"items": list_reminders()}
