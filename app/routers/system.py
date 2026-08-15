from fastapi import APIRouter

from app.release import get_release_version


router = APIRouter()


@router.get("/system/version", tags=["System"])
async def get_system_version():
    return {"version": get_release_version()}
