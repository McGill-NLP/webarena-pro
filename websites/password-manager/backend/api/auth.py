from fastapi import APIRouter, Cookie, HTTPException, Response
from pydantic import BaseModel
from ..store import get_store

router = APIRouter(prefix="/api/auth")


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> dict[str, str]:
    store = get_store()
    user = store.authenticate(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = store.create_session(user.id)
    response.set_cookie("vault_session", token, httponly=True, samesite="lax")
    return {"id": user.id, "username": user.username}


@router.post("/logout")
async def logout(
    response: Response,
    vault_session: str | None = Cookie(default=None),
) -> dict[str, bool]:
    if vault_session:
        get_store().delete_session(vault_session)
    response.delete_cookie("vault_session")
    return {"ok": True}


@router.get("/me")
async def me(vault_session: str | None = Cookie(default=None)) -> dict[str, str]:
    if not vault_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = get_store().get_user_by_session(vault_session)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"id": user.id, "username": user.username}
