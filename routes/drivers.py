from fastapi import APIRouter

router = APIRouter(prefix="/drivers")

@router.get("")
async def drivers_get():
    return []

