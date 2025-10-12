from fastapi import APIRouter

router = APIRouter(prefix="/drivers")

@router.get("")
async def drivers_get():
    return []

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
