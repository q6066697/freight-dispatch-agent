"""FastAPI surface: POST /dispatch and GET /health.

On startup the synthetic DB is built if it is missing, so a fresh container is
self-sufficient. All request/response bodies are the Pydantic models in schemas.py.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.config import get_settings
from app.db import db_path
from app.graph import dispatch
from app.schemas import DispatchRequest, DispatchResponse, HealthResponse
from db.seed import build


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not db_path().exists():
        build()
    yield


app = FastAPI(
    title="Freight Dispatch Agent",
    version="0.1.0",
    summary="Multi-agent freight dispatcher (LangGraph). Russian cargo requests in, "
    "carrier/price options out.",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        provider=settings.llm_provider,
        db_ready=db_path().exists(),
    )


@app.post("/dispatch", response_model=DispatchResponse)
def dispatch_endpoint(req: DispatchRequest) -> DispatchResponse:
    try:
        return dispatch(req.text, provider_name=req.provider)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
