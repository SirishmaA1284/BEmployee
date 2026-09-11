import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    agents,
    approvals,
    audit,
    auth,
    businesses,
    customers,
    documents,
    inventory,
    invoices,
    notifications,
    orders,
    policies,
    products,
    purchase_orders,
    suppliers,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.mcp.server import router as mcp_router
from app.security.rate_limit import init_rate_limiter

settings = get_settings()
configure_logging()
logger = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_rate_limiter()
    yield


app = FastAPI(
    title="AI Employee Platform API",
    description="Backend for the AI Employee Platform for Small Businesses.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    logger.info("%s %s", request.method, request.url.path, extra={"request_id": request_id})
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(businesses.router)
app.include_router(products.router)
app.include_router(inventory.router)
app.include_router(customers.router)
app.include_router(suppliers.router)
app.include_router(orders.router)
app.include_router(invoices.router)
app.include_router(purchase_orders.router)
app.include_router(agents.router)
app.include_router(policies.router)
app.include_router(approvals.router)
app.include_router(audit.router)
app.include_router(notifications.router)
app.include_router(documents.router)
app.include_router(mcp_router)
