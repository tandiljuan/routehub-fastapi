from fastapi import APIRouter

router = APIRouter(prefix="/deliveries")

@router.get("")
async def deliveries_get():
    return []
