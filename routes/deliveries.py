from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import re

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
async def deliveries_id_get(id: int):
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
