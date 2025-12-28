import re
from fastapi import (
    APIRouter,
    Request,
)
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/deliveries")

@router.get("")
async def deliveries_get(request: Request):
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
                "delivery_method": "DELIVERY",
                "milestone_id": 1,
                "destination": "37.7749,-122.4194",
                "schedule": ["DTSTART:20240704T120000Z"],
                "width": 10,
                "height": 20,
                "depth": 30,
                "length_unit": "CENTIMETER",
                "volume": 6000,
                "volume_unit": "CUBIC_CENTIMETER",
                "weight": 1000,
                "weight_unit": "GRAMS"
            }
        ]
    elif 'list-1.1' == example:
        return [
            {
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
        ]

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

@router.post("")
async def deliveries_post():
    return {
        "id": 1,
        "delivery_method": "DELIVERY",
        "milestone_id": 1,
        "destination": "37.7749,-122.4194",
        "schedule": ["DTSTART:20240704T120000Z"],
        "width": 10,
        "height": 20,
        "depth": 30,
        "length_unit": "CENTIMETER",
        "volume": 6000,
        "volume_unit": "CUBIC_CENTIMETER",
        "weight": 1000,
        "weight_unit": "GRAMS"
    }

@router.get("/{id}")
async def deliveries_id_get(id: int, request: Request):
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

    if 'delivery-1.0' == example:
        return {
            "id": 1,
            "delivery_method": "DELIVERY",
            "milestone_id": 1,
            "destination": "37.7749,-122.4194",
            "schedule": ["DTSTART:20240704T120000Z"],
            "width": 10,
            "height": 20,
            "depth": 30,
            "length_unit": "CENTIMETER",
            "volume": 6000,
            "volume_unit": "CUBIC_CENTIMETER",
            "weight": 1000,
            "weight_unit": "GRAMS"
        }
    elif 'delivery-1.1' == example:
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

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

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
