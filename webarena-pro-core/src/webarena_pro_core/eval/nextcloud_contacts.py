"""Saved CardDAV contact checks, scoped by identity rather than display name."""
from __future__ import annotations

import re

import vobject

from webarena_pro_core.eval.providers.dav import report_data


def check_contact(check: dict, xml: str) -> tuple[bool, str]:
    """Match requested fields on one card; email identities must be unique.

    With an email, exactly one contact must have that address. A category-only
    check establishes that a group exists on at least one card. Malformed DAV
    or vCard responses raise so the caller can mark the probe inconclusive.
    """
    if not check.get("email") and not check.get("category"):
        raise ValueError("carddav_contact requires an email or category")
    cards = [vobject.readOne(text) for text in report_data(
        xml, "{urn:ietf:params:xml:ns:carddav}address-data"
    )]
    email = str(check.get("email", "")).strip().casefold()
    if email:
        cards = [card for card in cards if email in [
            str(prop.value).strip().casefold()
            for prop in card.contents.get("email", [])
        ]]
        if len(cards) != 1:
            return False, f"expected one contact for {email}, found {len(cards)}"
    for card in cards:
        matched, reason = _matches_fields(check, card)
        if matched:
            return True, f"{email or 'contact'}: all requested fields on one card"
    return False, f"{email or 'contact'}: no card has all requested fields"


def _matches_fields(check: dict, card) -> tuple[bool, str]:
    for key, field in (("name", "fn"), ("title", "title")):
        if key in check and not any(
            str(prop.value).strip() == check[key]
            for prop in card.contents.get(field, [])
        ):
            return False, f"missing or incorrect {field}"
    if "name_pattern" in check and not any(
        re.fullmatch(check["name_pattern"], str(prop.value).strip())
        for prop in card.contents.get("fn", [])
    ):
        return False, "display name does not match"
    if "company" in check:
        companies = [
            prop.value[0] if isinstance(prop.value, list) and prop.value else prop.value
            for prop in card.contents.get("org", [])
        ]
        if check["company"] not in companies:
            return False, "missing or incorrect company"
    if "phone" in check:
        def normalize_phone(value):
            return re.sub(r"[^0-9]", "", str(value))
        phones = [normalize_phone(prop.value) for prop in card.contents.get("tel", [])]
        if normalize_phone(check["phone"]) not in phones:
            return False, "missing or incorrect phone"
    if "category" in check:
        categories = [
            value
            for prop in card.contents.get("categories", [])
            for value in (prop.value if isinstance(prop.value, list) else [prop.value])
        ]
        if check["category"] not in categories:
            return False, "missing or incorrect category"
    return True, "all requested fields match"
