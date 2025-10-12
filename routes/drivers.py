from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import re

router = APIRouter(prefix="/drivers")

@router.get("")
async def drivers_get(request: Request):
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
                "first_name": "John",
                "last_name": "Doe",
                "work_schedules": [
                    "DTSTART:20250101T120000Z\nDURATION:PT8H\nRRULE:FREQ=DAILY"
                ],
                "start_point": "37.7749,-122.4194",
                "work_areas": [
                    [
                        "37.7749,-122.4194",
                        "37.7749,-122.4195",
                        "37.7750,-122.4194"
                    ]
                ],
                "vehicles": [
                    {
                        "vehicle_id": 1,
                        "quantity": 2
                    }
                ]
            }
        ]

    message = {"message": "Work In Progress"}
    return JSONResponse(content=message, status_code=503)

@router.post("")
async def drivers_post():
    return {
        "id": 1,
        "first_name": "John",
        "last_name": "Doe",
        "work_schedules": [
            "DTSTART:20250101T120000Z\nDURATION:PT8H\nRRULE:FREQ=DAILY"
        ],
        "start_point": "37.7749,-122.4194",
        "work_areas": [
            [
                "37.7749,-122.4194",
                "37.7749,-122.4195",
                "37.7750,-122.4194"
            ]
        ],
        "vehicles": [
            {
                "vehicle_id": 1,
                "quantity": 2
            }
        ]
    }
