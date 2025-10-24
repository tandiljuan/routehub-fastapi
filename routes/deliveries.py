from fastapi import APIRouter

router = APIRouter(prefix="/deliveries")

@router.get("")
async def deliveries_get():
    return []

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
