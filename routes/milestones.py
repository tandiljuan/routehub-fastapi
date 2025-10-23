from fastapi import APIRouter

router = APIRouter(prefix="/milestones")

@router.get("")
async def milestones_get():
    return []

@router.post("")
async def milestones_post():
    return {
        "id": 1,
        "name": "Main Depot",
        "location": "37.7749,-122.4194",
        "milestone_category": "DEPOT"
    }
