from fastapi import APIRouter

from tema.modules.auth.router import router as auth_router
from tema.modules.users.router import router as users_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(users_router)
