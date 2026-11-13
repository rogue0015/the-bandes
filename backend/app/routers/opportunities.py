from fastapi import APIRouter, Depends, HTTPException, Query

from ..schemas import StatusUpdate
from ..security import current_user
from ..services.opportunities import counts, list_opportunities, update_status

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


@router.get("")
def get_opportunities(
    status: str | None = Query(default=None, pattern="^(active|completed|withdrawn|expired)$"),
    user: dict = Depends(current_user),
) -> dict:
    return {"items": list_opportunities(status), "counts": counts()}


@router.patch("/{opportunity_id}")
def patch_opportunity(
    opportunity_id: int,
    body: StatusUpdate,
    user: dict = Depends(current_user),
) -> dict:
    updated = update_status(opportunity_id, body.status)
    if updated is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return updated
