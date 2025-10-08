from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import re

router = APIRouter(prefix="/vehicles")

@router.get("")
async def vehicles_get(request: Request):
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
                "name": "pickup",
                "volume": 1230000,
                "volume_unit": "CUBIC_CENTIMETER",
                "consumption": 12,
                "consumption_unit": "LITERS_PER_100KM",
                "category_type": "PICKUP",
                "engine_type": "DIESEL"
            }
        ]
    elif 'list-1.1' == example:
        return [
            {
                "id": 1,
                "name": "pickup-update",
                "volume": 1230000,
                "volume_unit": "CUBIC_CENTIMETER",
                "consumption": 10,
                "consumption_unit": "LITERS_PER_100KM",
                "category_type": "PICKUP",
                "engine_type": "DIESEL"
            }
        ]

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

@router.post("")
async def vehicles_post():
    return {
        "id": 1,
        "name": "pickup",
        "volume": 1230000,
        "volume_unit": "CUBIC_CENTIMETER",
        "consumption": 12,
        "consumption_unit": "LITERS_PER_100KM",
        "category_type": "PICKUP",
        "engine_type": "DIESEL"
    }

@router.get("/{id}")
async def vehicles_id_get(id: int, request: Request):
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

    if 'vehicle-1.0' == example:
        return {
            "id": 1,
            "name": "pickup",
            "volume": 1230000,
            "volume_unit": "CUBIC_CENTIMETER",
            "consumption": 12,
            "consumption_unit": "LITERS_PER_100KM",
            "category_type": "PICKUP",
            "engine_type": "DIESEL"
        }
    elif 'vehicle-1.1' == example:
        return {
            "id": 1,
            "name": "pickup-update",
            "volume": 1230000,
            "volume_unit": "CUBIC_CENTIMETER",
            "consumption": 10,
            "consumption_unit": "LITERS_PER_100KM",
            "category_type": "PICKUP",
            "engine_type": "DIESEL"
        }

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

@router.patch("/{id}")
async def vehicles_id_patch(id: int):
    return {
        "id": 1,
        "name": "pickup-update",
        "volume": 1230000,
        "volume_unit": "CUBIC_CENTIMETER",
        "consumption": 10,
        "consumption_unit": "LITERS_PER_100KM",
        "category_type": "PICKUP",
        "engine_type": "DIESEL"
    }

@router.delete("/{id}")
async def vehicles_id_delete(id: int):
    return {"message": "Vehicle Deleted"}
