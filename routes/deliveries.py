import logging
import time

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
)
from starlette.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from pydantic import TypeAdapter, ValidationError
from libs.delivery_bulk import normalize_bulk_delivery_item, parse_bulk_deliveries_body
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
from libs.tenant.context import CompanyDep, assert_company_match, assert_related_company_id
from models.milestone import Milestone

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/deliveries",
    tags=["deliveries"],
)

# TypeAdapter for validation
dlv_create_adapter = TypeAdapter(DeliveryCreate)

@router.get(
    "",
    summary="List deliveries",
    response_model=list[DeliveryResponse],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
def deliveries_get(db: DbSession, company_id: CompanyDep):
    # `Delivery.serialize_model` reads self.milestone per row; without eager load
    # the list fires one query per delivery (N+1).
    dlv_list = db.exec(
        select(Delivery)
        .options(selectinload(Delivery.milestone))
        .where(Delivery.company_id == company_id)
    ).all()
    return dlv_list

@router.post(
    "",
    summary="Create delivery",
    response_model=DeliveryResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    status_code=201,
)
def deliveries_post(
    request: Request,
    response: Response,
    db: DbSession,
    post_data: DeliveryCreate,
    company_id: CompanyDep,
):
    dlv_dict = post_data.model_dump()
    dlv_dict['company_id'] = company_id
    assert_related_company_id(db, Milestone, post_data.milestone_id, company_id, "Milestone")
    dlv_db = Delivery.model_validate(dlv_dict)
    db.add(dlv_db)
    db.commit()
    dlv_url = request.url_for("deliveries_id_get", id=dlv_db.id)
    response.headers["location"] = f"{dlv_url}"
    db.refresh(dlv_db)
    return dlv_db

@router.post(
    "/bulk",
    summary="Create deliveries in bulk",
    response_model=DeliveryBulkResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def deliveries_bulk_post(
    request: Request,
    db: DbSession,
    company_id: CompanyDep,
):
    # Stays `async def` because it needs `await request.json()` (the body is not
    # a declared parameter — the rows are validated one by one so a bad row is
    # reported, not fatal). The blocking DB work goes to the threadpool, which
    # is what the plain `def` on every other route buys them implicitly.
    raw_items = parse_bulk_deliveries_body(await request.json())
    return await run_in_threadpool(_create_deliveries_bulk, db, company_id, raw_items)


def _milestone_ids_for_company(
    db: DbSession,
    raw_ids: set[str],
    company_id: int,
) -> set[int]:
    """The subset of `raw_ids` that exists and belongs to `company_id`.

    One query for the whole batch. Non-numeric ids are dropped here and
    reported per row by the caller, which owns the error shape.
    """
    ids: set[int] = set()
    for raw in raw_ids:
        try:
            ids.add(int(raw))
        except (ValueError, TypeError):
            continue
    if not ids:
        return set()
    rows = db.exec(
        select(Milestone.id).where(
            Milestone.id.in_(ids),
            Milestone.company_id == company_id,
        )
    ).all()
    return {int(row) for row in rows}


def _create_deliveries_bulk(
    db: DbSession,
    company_id: int,
    raw_items: list,
) -> dict:
    """Validate, then insert, a whole bulk batch.

    Split into two passes on purpose. The previous single loop called
    ``assert_related_company_id`` per row, and its ``Session.get`` triggered an
    autoflush on every iteration — so SQLAlchemy INSERTed the deliveries one at
    a time instead of batching them, which dominated the request (~1.6 s for a
    1500-row batch vs ~0.27 s here). Resolving the milestones up front and
    building the objects under ``no_autoflush`` keeps a single flush at the end.

    Per-row error reporting is unchanged: same messages, same ``loc``, same
    ``idx``, and one bad row still never fails the rest of the batch.
    """
    started = time.perf_counter()
    success = []
    failure = []
    created: list[tuple[int, Delivery]] = []

    # Pass 1 — payload validation only, so a malformed field is still reported
    # before (and instead of) the milestone check, exactly as it was.
    pending: list[tuple[int, object, DeliveryCreate]] = []
    for index, item in enumerate(raw_items):
        try:
            dlv_post = dlv_create_adapter.validate_python(
                normalize_bulk_delivery_item(item),
            )
        except ValidationError as e:
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
            continue
        except (ValueError, TypeError) as e:
            # Non-numeric lat/lng in normalize_bulk_delivery_item, etc.
            failure.append({
                "idx": index,
                "err": [{"msg": str(e), "inp": item, "loc": ["destination"]}],
            })
            continue
        pending.append((index, item, dlv_post))

    allowed_milestones = _milestone_ids_for_company(
        db, {p[2].milestone_id for p in pending}, company_id,
    )

    # Pass 2 — build the ORM objects with autoflush off so the batch lands as
    # one flush below.
    with db.no_autoflush:
        for index, item, dlv_post in pending:
            try:
                if int(dlv_post.milestone_id) not in allowed_milestones:
                    raise HTTPException(status_code=404, detail="Milestone not found")
                dlv_dict = dlv_post.model_dump()
                dlv_dict['company_id'] = company_id
                # Keep optimizer package payload verbatim (dimensions, weight_kg, etc.)
                if isinstance(item, dict) and item.get('extra') is not None:
                    dlv_dict['extra'] = item['extra']
                dlv_db = Delivery.model_validate(dlv_dict)
                db.add(dlv_db)
                created.append((index, dlv_db))

            except HTTPException as e:
                # Cross-tenant / missing milestone: record the row, keep the batch going.
                failure.append({
                    "idx": index,
                    "err": [{"msg": e.detail, "inp": item, "loc": ["milestone_id"]}],
                })
            except (ValueError, TypeError) as e:
                failure.append({
                    "idx": index,
                    "err": [{"msg": str(e), "inp": item, "loc": ["destination"]}],
                })

    if created:
        db.flush()
        for index, dlv_db in created:
            success.append({"idx": index, "id": str(dlv_db.id)})

    db.commit()
    # Two passes append out of order; callers index by `idx` but a stable,
    # input-ordered list is what the single loop used to return.
    failure.sort(key=lambda f: f["idx"])
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "bulk company=%s ok=%s fail=%s ms=%s",
        company_id,
        len(success),
        len(failure),
        elapsed_ms,
    )
    return {"success": success, "failure": failure}

@router.get(
    "/{id}",
    name="deliveries_id_get",
    summary="Get delivery",
    response_model=DeliveryResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
def deliveries_id_get(id: int, db: DbSession, company_id: CompanyDep):
    dlv_db = db.get(Delivery, id)
    assert_company_match(dlv_db, company_id, "Delivery")
    return dlv_db

@router.patch(
    "/{id}",
    summary="Update delivery",
    response_model=DeliveryResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
def deliveries_id_patch(
    id: int,
    db: DbSession,
    patch_data: DeliveryUpdate,
    company_id: CompanyDep,
):
    dlv_db = db.get(Delivery, id)
    assert_company_match(dlv_db, company_id, "Delivery")
    dlv_dict = patch_data.model_dump(exclude_unset=True)
    if patch_data.milestone_id is not None:
        assert_related_company_id(
            db, Milestone, patch_data.milestone_id, company_id, "Milestone",
        )
    dlv_db.sqlmodel_update(dlv_dict)
    db.add(dlv_db)
    db.commit()
    db.refresh(dlv_db)
    return dlv_db

@router.delete("/{id}", summary="Delete delivery")
def deliveries_id_delete(id: int, db: DbSession, company_id: CompanyDep):
    dlv_db = db.get(Delivery, id)
    assert_company_match(dlv_db, company_id, "Delivery")

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
