import asyncio
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.poller import run_poller
from app.routers import audit, auth, documents, health, query


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    app.state.arq_pool = pool
    task = asyncio.create_task(run_poller(pool))
    yield
    task.cancel()
    await pool.aclose()


app = FastAPI(
    title="KnowledgeGuard API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env == "development" else None,
    redoc_url="/redoc" if settings.app_env == "development" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router, prefix="/auth")
app.include_router(documents.router, prefix="/documents")
app.include_router(query.router)
app.include_router(audit.router, prefix="/audit")
