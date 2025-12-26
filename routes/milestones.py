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

@router.patch("/{id}")
async def milestones_id_patch(id: int):
    return {
        "id": 1,
        "name": "Main Distribution Point",
        "location": "37.7749,-122.4194",
        "milestone_category": "DISTRIBUTION_CENTER"
    }

@router.delete("/{id}")
async def milestones_id_delete(id: int):
    return {"message": "Milestone Deleted"}
