from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import FRONTEND_ORIGINS
from api.routers import auth as auth_router
from api.routers import chat as chat_router
from api.routers import clauses as clauses_router
from api.routers import comparison as comparison_router
from api.routers import contradictions as contradictions_router
from api.routers import documents as documents_router
from api.routers import risk as risk_router
from database.models import init_db

app = FastAPI(title="LQ-LegalAI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(auth_router.router)
app.include_router(documents_router.router)
app.include_router(clauses_router.router)
app.include_router(risk_router.router)
app.include_router(contradictions_router.router)
app.include_router(comparison_router.router)
app.include_router(chat_router.router)
