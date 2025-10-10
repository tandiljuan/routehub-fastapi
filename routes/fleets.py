from fastapi import APIRouter

router = APIRouter(prefix="/fleets")

@router.get("")
async def fleets_get():
    return []

