from fastapi import APIRouter

from tema.modules.assignments.router import router as assignments_router
from tema.modules.auth.router import router as auth_router
from tema.modules.chat.router import dm_router
from tema.modules.chat.router import router as chat_router
from tema.modules.chat.websocket import router as ws_router
from tema.modules.classrooms.router import channels_router
from tema.modules.classrooms.router import router as classrooms_router
from tema.modules.notes.router import router as notes_router
from tema.modules.users.router import router as users_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(classrooms_router)
api_router.include_router(channels_router)
api_router.include_router(chat_router)
api_router.include_router(dm_router)
api_router.include_router(ws_router)
api_router.include_router(notes_router)
api_router.include_router(assignments_router)
