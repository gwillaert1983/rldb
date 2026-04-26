import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.routers import auth, dashboard, settings, status
from app.scheduler import shutdown_scheduler, start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(status.router)
app.include_router(settings.router)
