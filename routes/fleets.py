from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import re

router = APIRouter(prefix="/fleets")

@router.get("")
async def fleets_get(request: Request):
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
                "name": "my-fleet",
                "vehicles": [
                    {
                        "vehicle_id": 1,
                        "quantity": 2
                    }
                ]
            }
        ]
    elif 'list-1.1' == example:
        return [
            {
                "id": 1,
                "name": "my-fleet-update",
                "vehicles": [
                    {
                        "vehicle_id": 2,
                        "quantity": 3
                    }
                ]
            }
        ]

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

@router.post("")
async def fleets_post():
    return {
        "id": 1,
        "name": "my-fleet",
        "vehicles": [
            {
                "vehicle_id": 1,
                "quantity": 2
            }
        ]
    }

@router.get("/{id}")
async def fleets_id_get(id: int, request: Request):
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

    if 'fleet-1.0' == example:
        return {
            "id": 1,
            "name": "my-fleet",
            "vehicles": [
                {
                    "vehicle_id": 1,
                    "quantity": 2
                }
            ]
        }
    elif 'fleet-1.1' == example:
        return {
            "id": 1,
            "name": "my-fleet-update",
            "vehicles": [
                {
                    "vehicle_id": 2,
                    "quantity": 3
                }
            ]
        }

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

@router.patch("/{id}")
async def fleets_id_patch(id: int):
    return {
        "id": 1,
        "name": "my-fleet-update",
        "vehicles": [
            {
                "vehicle_id": 2,
                "quantity": 3
            }
        ]
    }

@router.delete("/{id}")
async def fleets_id_delete(id: int):
    return {"message": "Fleet Deleted"}
