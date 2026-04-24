from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session as DBSession

from app.api.deps.auth import require_permissions
from app.db.session import get_db
from app.schemas.system import (
    SystemMaintenanceRequest,
    SystemMaintenanceResult,
    SystemOverview,
)
from app.services.system_overview import SystemOverviewService

router = APIRouter(
    prefix="/system",
    tags=["system"],
    dependencies=[Depends(require_permissions("system:read"))],
)

@router.get("/overview", response_model=SystemOverview)
async def overview(
    db: DBSession = Depends(get_db),
) -> SystemOverview:
    return SystemOverviewService(db).build_overview()


@router.post(
    "/maintenance/run",
    response_model=SystemMaintenanceResult,
    dependencies=[Depends(require_permissions("system:write"))],
)
async def run_maintenance(
    payload: SystemMaintenanceRequest,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db),
) -> SystemMaintenanceResult:
    return SystemOverviewService(db).run_maintenance(payload, background_tasks)
