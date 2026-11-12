import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .api import auth, vault
from .store import get_store
from .seed import SEED_USER

app = FastAPI(title="Password Manager API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(vault.router)


def reset_seed_data():
    store = get_store()
    store.clear()
    user = store.add_user(SEED_USER["username"], SEED_USER["password"])
    for item in SEED_USER["items"]:
        store.add_item(user.id, item.model_copy(deep=True))
    return user


@app.on_event("startup")
async def startup() -> None:
    user = reset_seed_data()
    print(f"Seeded vault for '{user.username}' with {len(SEED_USER['items'])} items")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/reset")
async def reset_state() -> dict[str, str]:
    reset_seed_data()
    return {"status": "ok"}


STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.isdir(STATIC_DIR):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(STATIC_DIR, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str) -> FileResponse:
        file_path = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
