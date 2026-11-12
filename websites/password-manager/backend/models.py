from enum import Enum
from typing import Optional
from pydantic import BaseModel


class ItemType(str, Enum):
    LOGIN = "login"
    CARD = "card"
    IDENTITY = "identity"
    NOTE = "note"


class User(BaseModel):
    id: str
    username: str


class BillingAddress(BaseModel):
    address1: str = ""
    address2: str = ""
    city: str = ""
    state: str = ""
    postalCode: str = ""
    country: str = ""


class CardData(BaseModel):
    cardholderName: str = ""
    brand: str = ""
    number: str = ""
    expMonth: str = ""
    expYear: str = ""
    code: str = ""
    billingAddress: Optional[BillingAddress] = None


class IdentityData(BaseModel):
    title: str = ""
    firstName: str = ""
    lastName: str = ""
    email: str = ""
    phone: str = ""
    company: str = ""
    address1: str = ""
    address2: str = ""
    city: str = ""
    state: str = ""
    postalCode: str = ""
    country: str = ""
    passportNumber: str = ""
    dateOfBirth: str = ""


class LoginData(BaseModel):
    username: str = ""
    password: str = ""
    uris: list[str] = []


class NoteData(BaseModel):
    content: str = ""


class VaultItem(BaseModel):
    id: str
    name: str
    type: ItemType
    favorite: bool = False
    notes: Optional[str] = None
    card: Optional[CardData] = None
    identity: Optional[IdentityData] = None
    login: Optional[LoginData] = None
    note: Optional[NoteData] = None
    createdAt: str
    updatedAt: str


class VaultItemCreate(BaseModel):
    name: str
    type: ItemType
    favorite: bool = False
    notes: Optional[str] = None
    card: Optional[CardData] = None
    identity: Optional[IdentityData] = None
    login: Optional[LoginData] = None
    note: Optional[NoteData] = None
