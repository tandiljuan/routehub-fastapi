from fastapi import APIRouter

router = APIRouter(prefix="/fleets")

@router.get("")
async def fleets_get():
    return []

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
