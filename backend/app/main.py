from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import get_settings
from app.db import close_pool, open_pool
from app.logging_utils import log_event
from app.services.ledger_service import AccountNotActive, AccountNotFound


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()
    yield
    close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="FinPilot API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_credentials=False,  # bearer tokens, no cookies
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(AccountNotFound)
    async def _nf(_: Request, __: AccountNotFound):
        return JSONResponse({"detail": "Account not found."}, status_code=404)

    @app.exception_handler(AccountNotActive)
    async def _na(_: Request, __: AccountNotActive):
        return JSONResponse({"detail": "This account is disconnected."}, status_code=409)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log_event("api.error", error=type(exc).__name__)  # class only: never log payloads
        return JSONResponse({"detail": "Something went wrong. Please try again."}, status_code=500)

    app.include_router(router)
    return app


app = create_app()
