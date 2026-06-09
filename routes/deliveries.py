from typing import Any
from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from pydantic import TypeAdapter
from models.database import Session as DbSession
from models.delivery import (
    Delivery,
    DeliveryBulkResponse,
    DeliveryCreate,
    DeliveryResponse,
    DeliveryUpdate,
)
from models.delivery_lot import DeliveryLotDelivery
from models.delivery_plan import DeliveryPathDelivery

router = APIRouter(
    prefix="/deliveries",
    tags=["deliveries"],
)

# TypeAdapter for validation
dlv_create_adapter = TypeAdapter(DeliveryCreate)

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

@router.post(
    "/bulk",
    response_model=DeliveryBulkResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def deliveries_bulk_post(db: DbSession, post_data: list[Any]):
    success = []
    failure = []
    created: list[tuple[int, Delivery]] = []

    for index, item in enumerate(post_data):
        try:
            dlv_post = dlv_create_adapter.validate_python(item)
            dlv_dict = dlv_post.model_dump()
            dlv_dict['company_id'] = 1
            # Keep optimizer package payload verbatim (dimensions, weight_kg, etc.)
            if isinstance(item, dict) and item.get('extra') is not None:
                dlv_dict['extra'] = item['extra']
            dlv_db = Delivery.model_validate(dlv_dict)
            db.add(dlv_db)
            created.append((index, dlv_db))

        except Exception as e:
            failure.append({
                "idx": index,
                "err": [
                    {
                        "msg": error["msg"],
                        "inp": error["input"],
                        "loc": error["loc"],
                    } for error in e.errors()
                ],
            })

    if created:
        db.flush()
        for index, dlv_db in created:
            success.append({"idx": index, "id": str(dlv_db.id)})

    db.commit()
    return {"success": success, "failure": failure}

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

@router.patch(
    "/{id}",
    response_model=DeliveryResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def deliveries_id_patch(
    id: int,
    db: DbSession,
    patch_data: DeliveryUpdate,
):
    dlv_db = db.get(Delivery, id)
    if not dlv_db:
        raise HTTPException(status_code=404, detail="Delivery not found")
    dlv_dict = patch_data.model_dump(exclude_unset=True)
    dlv_db.sqlmodel_update(dlv_dict)
    db.add(dlv_db)
    db.commit()
    db.refresh(dlv_db)
    return dlv_db

@router.delete("/{id}")
async def deliveries_id_delete(id: int, db: DbSession):
    dlv_db = db.get(Delivery, id)
    if not dlv_db:
        raise HTTPException(status_code=404, detail="Delivery not found")

    in_lot = db.exec(
        select(DeliveryLotDelivery.delivery_lot_id)
        .where(DeliveryLotDelivery.delivery_id == id)
        .limit(1)
    ).first()
    if in_lot is not None:
        raise HTTPException(
            status_code=409,
            detail="Delivery is linked to a lot; delete the lot first",
        )

    in_route = db.exec(
        select(DeliveryPathDelivery.delivery_path_id)
        .where(DeliveryPathDelivery.delivery_id == id)
        .limit(1)
    ).first()
    if in_route is not None:
        raise HTTPException(
            status_code=409,
            detail="Delivery is linked to a route plan; delete the lot first",
        )

    try:
        db.delete(dlv_db)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Delivery is referenced by other records",
        )
    return {"code": 200, "message": "Delivery Deleted"}
