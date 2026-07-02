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
from libs.tenant.context import CompanyDep, assert_company_match

router = APIRouter(
    prefix="/milestones",
    tags=["milestones"],
)

@router.get(
    "",
    summary="List milestones",
    response_model=list[MilestoneResponse],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def milestones_get(db: DbSession, company_id: CompanyDep):
    mst_list = db.exec(select(Milestone).where(Milestone.company_id == company_id)).all()
    return mst_list

@router.post(
    "",
    summary="Create milestone",
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
    company_id: CompanyDep,
):
    mst_dict = post_data.model_dump()
    mst_dict['company_id'] = company_id
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
    summary="Get milestone",
    response_model=MilestoneResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def milestones_id_get(id: int, db: DbSession, company_id: CompanyDep):
    mst_db = db.get(Milestone, id)
    assert_company_match(mst_db, company_id, "Milestone")
    return mst_db

@router.patch(
    "/{id}",
    summary="Update milestone",
    response_model=MilestoneResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def milestones_id_patch(id: int, db: DbSession, patch_data: MilestoneUpdate, company_id: CompanyDep):
    mst_db = db.get(Milestone, id)
    assert_company_match(mst_db, company_id, "Milestone")
    mst_dict = patch_data.model_dump(exclude_unset=True)
    mst_db.sqlmodel_update(mst_dict)
    db.add(mst_db)
    db.commit()
    db.refresh(mst_db)
    return mst_db

@router.delete("/{id}", summary="Delete milestone")
async def milestones_id_delete(id: int, db: DbSession, company_id: CompanyDep):
    mst_db = db.get(Milestone, id)
    assert_company_match(mst_db, company_id, "Milestone")
    db.delete(mst_db)
    db.commit()
    return {"code": 200, "message": "Milestone Deleted"}
