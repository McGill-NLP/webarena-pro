import uuid
from datetime import datetime, timezone
from .models import VaultItem, ItemType, CardData, IdentityData, LoginData, NoteData, BillingAddress


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


_US_BILLING = BillingAddress(
    address1="742 Evergreen Terrace",
    city="Springfield",
    state="IL",
    postalCode="62701",
    country="USA",
)

_CA_BILLING = BillingAddress(
    address1="100 Queen St W",
    city="Toronto",
    state="ON",
    postalCode="M5H 2N2",
    country="Canada",
)

SEED_ITEMS: list[VaultItem] = [
    VaultItem(
        id=_id(),
        name="Visa Platinum",
        type=ItemType.CARD,
        favorite=True,
        card=CardData(
            cardholderName="Jane Smith",
            brand="Visa",
            number="4111111111111111",
            expMonth="12",
            expYear="2027",
            code="123",
            billingAddress=_US_BILLING,
        ),
        createdAt=_now(),
        updatedAt=_now(),
    ),
    VaultItem(
        id=_id(),
        name="Mastercard Gold",
        type=ItemType.CARD,
        card=CardData(
            cardholderName="Jane Smith",
            brand="Mastercard",
            number="5500005555555559",
            expMonth="08",
            expYear="2026",
            code="456",
            billingAddress=_US_BILLING,
        ),
        createdAt=_now(),
        updatedAt=_now(),
    ),
    VaultItem(
        id=_id(),
        name="American Express Business",
        type=ItemType.CARD,
        card=CardData(
            cardholderName="Jane Smith",
            brand="Amex",
            number="371449635398431",
            expMonth="03",
            expYear="2028",
            code="7890",
            billingAddress=_CA_BILLING,
        ),
        createdAt=_now(),
        updatedAt=_now(),
    ),
    VaultItem(
        id=_id(),
        name="TD Visa Classic",
        type=ItemType.CARD,
        card=CardData(
            cardholderName="John Smith",
            brand="Visa",
            number="4532015112830366",
            expMonth="05",
            expYear="2026",
            code="789",
            billingAddress=_CA_BILLING,
        ),
        createdAt=_now(),
        updatedAt=_now(),
    ),
    VaultItem(
        id=_id(),
        name="Jane Smith",
        type=ItemType.IDENTITY,
        identity=IdentityData(
            title="Ms.",
            firstName="Jane",
            lastName="Smith",
            email="jane.smith@example.com",
            phone="+1 514 555 0100",
            address1="742 Evergreen Terrace",
            city="Springfield",
            state="IL",
            postalCode="62701",
            country="USA",
            passportNumber="US123456789",
            dateOfBirth="1988-04-15",
        ),
        createdAt=_now(),
        updatedAt=_now(),
    ),
    VaultItem(
        id=_id(),
        name="John Smith",
        type=ItemType.IDENTITY,
        identity=IdentityData(
            title="Mr.",
            firstName="John",
            lastName="Smith",
            email="john.smith@example.com",
            phone="+1 514 555 0101",
            address1="742 Evergreen Terrace",
            city="Springfield",
            state="IL",
            postalCode="62701",
            country="USA",
            passportNumber="US987654321",
            dateOfBirth="1985-07-22",
        ),
        createdAt=_now(),
        updatedAt=_now(),
    ),
    VaultItem(
        id=_id(),
        name="Flight Search",
        type=ItemType.LOGIN,
        login=LoginData(
            username="agent1",
            password="flyingagents",
            uris=["http://localhost:2210"],
        ),
        createdAt=_now(),
        updatedAt=_now(),
    ),
    VaultItem(
        id=_id(),
        name="Frequent Flyer Programs",
        type=ItemType.NOTE,
        note=NoteData(
            content=(
                "Air Canada Aeroplan: 123456789\n"
                "United MileagePlus: MP987654\n"
                "Delta SkyMiles: 1234567890\n"
                "Lufthansa Miles & More: 987654321"
            )
        ),
        createdAt=_now(),
        updatedAt=_now(),
    ),
]

SEED_USER = {
    "username": "agent1",
    "password": "agentpass",
    "items": SEED_ITEMS,
}
