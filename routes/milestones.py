from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import re

router = APIRouter(prefix="/milestones")

@router.get("")
async def milestones_get(request: Request):
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
                "name": "Main Depot",
                "location": "37.7749,-122.4194",
                "milestone_category": "DEPOT"
            }
        ]

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

@router.post("")
async def milestones_post():
    return {
        "id": 1,
        "name": "Main Depot",
        "location": "37.7749,-122.4194",
        "milestone_category": "DEPOT"
    }

@router.get("/{id}")
async def milestones_id_get(id: int):
    return {
        "id": 1,
        "name": "Main Depot",
        "location": "37.7749,-122.4194",
        "milestone_category": "DEPOT"
    }

@router.patch("/{id}")
async def milestones_id_patch(id: int):
    return {
        "id": 1,
        "name": "Main Distribution Point",
        "location": "37.7749,-122.4194",
        "milestone_category": "DISTRIBUTION_CENTER"
    }
