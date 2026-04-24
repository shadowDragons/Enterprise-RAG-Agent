from fastapi import APIRouter

from app.api.routes import (
    assistants,
    auth,
    chat,
    documents,
    health,
    jobs,
    knowledge_bases,
    reviews,
    sessions,
    system,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(assistants.router)
api_router.include_router(knowledge_bases.router)
api_router.include_router(documents.router)
api_router.include_router(jobs.router)
api_router.include_router(sessions.router)
api_router.include_router(chat.router)
api_router.include_router(reviews.router)
