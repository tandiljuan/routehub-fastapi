from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
)
from sqlmodel import select
from models.database import Session as DbSession
from models.milestone import (
    Milestone,
    MilestoneCreate,
    MilestoneResponse,
    MilestoneUpdate,
)

router = APIRouter(prefix="/milestones")

@router.get(
    "",
    response_model=list[MilestoneResponse],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def milestones_get(db: DbSession):
    mst_list = db.exec(select(Milestone)).all()
    return mst_list

@router.post(
    "",
    response_model=MilestoneResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    status_code=201,
)
async def milestones_post(
    request: Request,
    response: Response,
    db: DbSession,
    post_data: MilestoneCreate,
):
    mst_dict = post_data.model_dump()
    mst_dict['company_id'] = 1
    mst_db = Milestone.model_validate(mst_dict)
    db.add(mst_db)
    db.commit()
    mst_url = request.url_for("milestones_id_get", id=mst_db.id)
    response.headers["location"] = f"{mst_url}"
    db.refresh(mst_db)
    return mst_db

@router.get(
    "/{id}",
    name="milestones_id_get",
    response_model=MilestoneResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def milestones_id_get(id: int, db: DbSession):
    mst_db = db.get(Milestone, id)
    if not mst_db:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return mst_db

@router.patch(
    "/{id}",
    response_model=MilestoneResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def milestones_id_patch(id: int, db: DbSession, patch_data: MilestoneUpdate):
    mst_db = db.get(Milestone, id)
    if not mst_db:
        raise HTTPException(status_code=404, detail="Milestone not found")
    mst_dict = patch_data.model_dump(exclude_unset=True)
    mst_db.sqlmodel_update(mst_dict)
    db.add(mst_db)
    db.commit()
    db.refresh(mst_db)
    return mst_db

@router.delete("/{id}")
async def milestones_id_delete(id: int, db: DbSession):
    mst_db = db.get(Milestone, id)
    if not mst_db:
        raise HTTPException(status_code=404, detail="Milestone not found")
    db.delete(mst_db)
    db.commit()
    return {"code": 200, "message": "Milestone Deleted"}
