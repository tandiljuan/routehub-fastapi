from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import re

router = APIRouter(prefix="/lots")

@router.get("")
async def delivery_lots_get(request: Request):
    example = ''

    if 'prefer' in request.headers:
        match = re.match(r'example=([\w\.-]+)', request.headers.get("Prefer"))
        if match:
            example = match.group(1)

    if 'empty' == example:
        return []
    elif 'list-1.0' == example:
        return [
            {
                "id": 1,
                "milestone_id": 1,
                "deliveries": [1],
                "fleet_id": 1,
                "drivers": [1],
                "state": "UNPROCESSED"
            }
        ]
    elif 'list-1.1' == example:
        return [
            {
                "id": 1,
                "milestone_id": 1,
                "deliveries": [1,2],
                "fleet_id": 1,
                "drivers": [1],
                "state": "UNPROCESSED"
            }
        ]

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

@router.post("")
async def delivery_lots_post():
    return {
        "id": 1,
        "milestone_id": 1,
        "deliveries": [1],
        "fleet_id": 1,
        "drivers": [1],
        "state": "UNPROCESSED"
    }

@router.get("/{id}")
async def delivery_lots_id_get(id: int, request: Request):
    example = ''

    if 'prefer' in request.headers:
        match = re.match(r'example=([\w\.-]+)', request.headers.get("Prefer"))
        if match:
            example = match.group(1)

    if 'delivery-lot-1.0' == example:
        return {
            "id": 1,
            "milestone_id": 1,
            "deliveries": [1],
            "fleet_id": 1,
            "drivers": [1],
            "state": "UNPROCESSED"
        }
    elif 'delivery-lot-1.1' == example:
        return {
            "id": 1,
            "milestone_id": 1,
            "deliveries": [1,2],
            "fleet_id": 1,
            "drivers": [1],
            "state": "UNPROCESSED"
        }

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

@router.patch("/{id}")
async def delivery_lots_id_patch(id: int):
    return {
        "id": 1,
        "milestone_id": 1,
        "deliveries": [1,2],
        "fleet_id": 1,
        "drivers": [1],
        "state": "UNPROCESSED"
    }

@router.delete("/{id}")
async def delivery_lots_id_delete(id: int):
    return {"message": "Delivery Lot Deleted"}

@router.post("/{id}/plan")
async def delivery_lots_id_plan_post(id: int):
    return {"message": "Delivery plan queued for processing"}

@router.get("/{id}/plan")
async def delivery_lots_id_plan_get(id: int):
    return {
        "delivery_lot_id": 1,
        "delivery_paths": [
            {
                "milestone_id": 1,
                "vehicle_id": 1,
                "driver_id": 1,
                "delivery_units": [1,2]
            }
        ]
    }
