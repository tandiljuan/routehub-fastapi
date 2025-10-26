from fastapi import APIRouter

router = APIRouter(prefix="/lots")

@router.get("")
async def delivery_lots_get():
    return []

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
