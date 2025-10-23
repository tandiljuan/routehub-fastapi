from fastapi import APIRouter

router = APIRouter(prefix="/milestones")

@router.get("")
async def milestones_get():
    return []
