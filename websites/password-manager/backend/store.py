import uuid
from typing import Optional
from .models import VaultItem, User


class Store:
    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        self._users_by_username: dict[str, str] = {}
        self._passwords: dict[str, str] = {}
        self._sessions: dict[str, str] = {}
        self._vault: dict[str, list[VaultItem]] = {}

    def add_user(self, username: str, password: str) -> User:
        user_id = str(uuid.uuid4())
        user = User(id=user_id, username=username)
        self._users[user_id] = user
        self._users_by_username[username] = user_id
        self._passwords[user_id] = password
        self._vault[user_id] = []
        return user

    def authenticate(self, username: str, password: str) -> Optional[User]:
        user_id = self._users_by_username.get(username)
        if not user_id:
            return None
        if self._passwords.get(user_id) != password:
            return None
        return self._users[user_id]

    def create_session(self, user_id: str) -> str:
        token = str(uuid.uuid4())
        self._sessions[token] = user_id
        return token

    def get_user_by_session(self, token: str) -> Optional[User]:
        user_id = self._sessions.get(token)
        if not user_id:
            return None
        return self._users.get(user_id)

    def delete_session(self, token: str) -> None:
        self._sessions.pop(token, None)

    def get_items(self, user_id: str) -> list[VaultItem]:
        return list(self._vault.get(user_id, []))

    def get_item(self, user_id: str, item_id: str) -> Optional[VaultItem]:
        for item in self._vault.get(user_id, []):
            if item.id == item_id:
                return item
        return None

    def add_item(self, user_id: str, item: VaultItem) -> VaultItem:
        if user_id not in self._vault:
            self._vault[user_id] = []
        self._vault[user_id].append(item)
        return item

    def update_item(self, user_id: str, item_id: str, updated: VaultItem) -> Optional[VaultItem]:
        items = self._vault.get(user_id, [])
        for i, item in enumerate(items):
            if item.id == item_id:
                items[i] = updated
                return updated
        return None

    def delete_item(self, user_id: str, item_id: str) -> bool:
        items = self._vault.get(user_id, [])
        for i, item in enumerate(items):
            if item.id == item_id:
                items.pop(i)
                return True
        return False

    def clear(self) -> None:
        self._users.clear()
        self._users_by_username.clear()
        self._passwords.clear()
        self._sessions.clear()
        self._vault.clear()


_store = Store()


def get_store() -> Store:
    return _store
