from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
)
from sqlmodel import select
from models.database import Session as DbSession
from models.delivery import (
    Delivery,
    DeliveryCreate,
    DeliveryResponse,
)

router = APIRouter(prefix="/deliveries")

@router.get(
    "",
    response_model=list[DeliveryResponse],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def deliveries_get(db: DbSession):
    dlv_list = db.exec(select(Delivery)).all()
    return dlv_list

@router.post(
    "",
    response_model=DeliveryResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    status_code=201,
)
async def deliveries_post(
    request: Request,
    response: Response,
    db: DbSession,
    post_data: DeliveryCreate,
):
    dlv_dict = post_data.model_dump()
    dlv_dict['company_id'] = 1
    dlv_db = Delivery.model_validate(dlv_dict)
    db.add(dlv_db)
    db.commit()
    dlv_url = request.url_for("deliveries_id_get", id=dlv_db.id)
    response.headers["location"] = f"{dlv_url}"
    db.refresh(dlv_db)
    return dlv_db

@router.get(
    "/{id}",
    name="deliveries_id_get",
    response_model=DeliveryResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def deliveries_id_get(id: int, db: DbSession):
    dlv_db = db.get(Delivery, id)
    if not dlv_db:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return dlv_db

@router.patch("/{id}")
async def deliveries_id_patch(id: int):
    return {
        "id": 1,
        "delivery_method": "DELIVERY",
        "milestone_id": 1,
        "destination": "37.7749,-122.4194",
        "schedule": ["DTSTART:20240704T120000Z"],
        "width": 15,
        "height": 25,
        "depth": 35,
        "length_unit": "CENTIMETER",
        "volume": 6500,
        "volume_unit": "CUBIC_CENTIMETER",
        "weight": 1500,
        "weight_unit": "GRAMS"
    }

@router.delete("/{id}")
async def deliveries_id_delete(id: int):
    return {"message": "Fleet Deleted"}
