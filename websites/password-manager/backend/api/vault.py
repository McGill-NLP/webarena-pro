import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Cookie, HTTPException
from ..store import get_store
from ..models import VaultItem, VaultItemCreate

router = APIRouter(prefix="/api/vault")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_user(vault_session: str | None) -> str:
    if not vault_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = get_store().get_user_by_session(vault_session)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user.id


@router.get("/items")
async def list_items(
    vault_session: str | None = Cookie(default=None),
) -> list[VaultItem]:
    user_id = _require_user(vault_session)
    return get_store().get_items(user_id)


@router.get("/items/{item_id}")
async def get_item(
    item_id: str,
    vault_session: str | None = Cookie(default=None),
) -> VaultItem:
    user_id = _require_user(vault_session)
    item = get_store().get_item(user_id, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.post("/items", status_code=201)
async def create_item(
    body: VaultItemCreate,
    vault_session: str | None = Cookie(default=None),
) -> VaultItem:
    user_id = _require_user(vault_session)
    now = _now()
    item = VaultItem(
        id=str(uuid.uuid4()),
        createdAt=now,
        updatedAt=now,
        **body.model_dump(),
    )
    return get_store().add_item(user_id, item)


@router.put("/items/{item_id}")
async def update_item(
    item_id: str,
    body: VaultItemCreate,
    vault_session: str | None = Cookie(default=None),
) -> VaultItem:
    user_id = _require_user(vault_session)
    existing = get_store().get_item(user_id, item_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Item not found")
    updated = VaultItem(
        id=item_id,
        createdAt=existing.createdAt,
        updatedAt=_now(),
        **body.model_dump(),
    )
    result = get_store().update_item(user_id, item_id, updated)
    if not result:
        raise HTTPException(status_code=404, detail="Item not found")
    return result


@router.delete("/items/{item_id}", status_code=204)
async def delete_item(
    item_id: str,
    vault_session: str | None = Cookie(default=None),
) -> None:
    user_id = _require_user(vault_session)
    if not get_store().delete_item(user_id, item_id):
        raise HTTPException(status_code=404, detail="Item not found")
