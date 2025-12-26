import re
from fastapi import (
    APIRouter,
    Request,
    Response,
)
from fastapi.responses import JSONResponse
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
)
async def milestones_id_get(id: int, request: Request):
    key = ''
    example = ''

    if 'prefer' in request.headers:
        match = re.match(r'(\w+)=([\w\.-]+)', request.headers.get("Prefer"))
        if match:
            key = match.group(1)
            example = match.group(2)

    if 'code' == key:
        message = {"message": "..."}
        return JSONResponse(content=message, status_code=int(example))

    if 'milestone-1.0' == example:
        return {
            "id": 1,
            "name": "Main Depot",
            "location": "37.7749,-122.4194",
            "milestone_category": "DEPOT"
        }
    elif 'milestone-1.1' == example:
        return {
            "id": 1,
            "name": "Main Distribution Point",
            "location": "37.7749,-122.4194",
            "milestone_category": "DISTRIBUTION_CENTER"
        }

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

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
