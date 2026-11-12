"""FastAPI application — flight search backend."""

import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .api import airports, auth, booking, calendar, currency, destinations, geolocation, search
from .benchmark import BENCHMARK_DATE, BENCHMARK_MODE
from .booking_store import reset_bookings
from .data_loader import get_route_graph
from .hub_detector import compute_hub_scores
from .eval_state import router as eval_router

app = FastAPI(title="Flight Search API", version="1.0.0")

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Passkey middleware — protects /api/* routes when REQUIRE_PASSKEY is enabled
class PasskeyMiddleware(BaseHTTPMiddleware):
    EXEMPT_PREFIXES = (
        "/api/auth/",
        "/api/health",
        "/api/reset",
        "/api/geolocation",
        "/api/currency/",
        "/api/destinations/",
        "/api/eval/",  # Separately authenticated with X-Eval-Token.
    )

    async def dispatch(self, request: Request, call_next):
        if not auth._require_passkey():
            return await call_next(request)

        path = request.url.path
        if path.startswith("/api/") and not any(
            path.startswith(p) for p in self.EXEMPT_PREFIXES
        ):
            token = request.cookies.get("flight_auth")
            if token != auth.AUTH_TOKEN:
                return JSONResponse(
                    status_code=401, content={"detail": "Not authenticated"}
                )

        return await call_next(request)


app.add_middleware(PasskeyMiddleware)

# Register API routers
app.include_router(auth.router)
app.include_router(airports.router)
app.include_router(search.router)
app.include_router(calendar.router)
app.include_router(booking.router)
app.include_router(currency.router)
app.include_router(geolocation.router)
app.include_router(destinations.router)
app.include_router(eval_router)


@app.on_event("startup")
async def startup():
    """Load data and compute hub scores on startup."""
    t0 = time.time()
    graph = get_route_graph()
    hubs = compute_hub_scores(graph)
    elapsed = time.time() - t0
    print(f"Loaded {len(graph.airports)} airports, {len(hubs)} hubs in {elapsed:.1f}s")


@app.get("/api/health")
async def health():
    graph = get_route_graph()
    return {"status": "ok", "airports": len(graph.airports)}


@app.get("/api/config")
async def config():
    """Return client-visible configuration (e.g. benchmark mode)."""
    return {
        "benchmark_mode": BENCHMARK_MODE,
        "benchmark_date": BENCHMARK_DATE.isoformat() if BENCHMARK_MODE else None,
    }


@app.post("/api/reset")
async def reset_state():
    """Reset runtime booking state back to the packaged baseline."""
    reset_bookings()
    return {"status": "ok"}


# Serve frontend static files (production)
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the React SPA for all non-API routes."""
        file_path = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
