from fastapi import APIRouter

router = APIRouter(prefix="/lots")

@router.get("")
async def delivery_lots_get():
    return []
