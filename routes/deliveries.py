from typing import Any
from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
)
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

    for index, item in enumerate(post_data):
        try:
            dlv_post = dlv_create_adapter.validate_python(item)
            dlv_dict = dlv_post.model_dump()
            dlv_dict['company_id'] = 1
            dlv_db = Delivery.model_validate(dlv_dict)
            db.add(dlv_db)
            db.commit()
            db.refresh(dlv_db)
            success.append({
                "idx": index,
                "id": str(dlv_db.id),
            })

        except Exception as e:
            tx = db.get_transaction()
            if tx is not None and not tx.is_active:
                db.rollback()
            errors = e.errors() if hasattr(e, "errors") else [
                {
                    "msg": "Invalid delivery",
                    "input": None,
                    "loc": None,
                }
            ]
            failure.append({
                "idx": index,
                "err": [
                    {
                        "msg": error["msg"],
                        "inp": error["input"],
                        "loc": error["loc"],
                    } for error in errors
                ],
            })

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
    db.delete(dlv_db)
    db.commit()
    return {"code": 200, "message": "Delivery Deleted"}
