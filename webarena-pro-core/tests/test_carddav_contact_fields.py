"""CardDAV field matching decodes transport and keeps all fields on one card."""
import html

import pytest

from webarena_pro_core.eval.nextcloud_contacts import check_contact


def report(*cards):
    records = "".join('<d:response><d:propstat><d:prop><c:address-data>' + html.escape(card).replace("\r", "&#13;") + '</c:address-data></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>' for card in cards)
    return '<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">' + records + '</d:multistatus>'


def card(name="Eric", email="eric.samuel@cloud.com", category="friends,marketing team"):
    return f"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:{name}\r\nEMAIL:{email}\r\nTEL;TYPE=CELL:555-0987\r\nCATEGORIES:{category}\r\nEND:VCARD"


CHECK = {"email": "eric.samuel@cloud.com", "name_pattern": r"Eric(?:\s+.*)?", "phone": "555-0987", "category": "marketing team"}


@pytest.mark.parametrize("name", ["Eric", "Eric Samuel"])
def test_surname_optional_when_only_first_name_was_requested(name):
    assert check_contact(CHECK, report(card(name)))[0]


def test_folded_properties_are_decoded():
    raw = card().replace("marketing team", "marketing \r\n team").replace("555-0987", "555-\r\n 0987")
    assert check_contact(CHECK, report(raw))[0]


def test_email_and_group_cannot_be_combined_across_cards():
    assert not check_contact(CHECK, report(card(category="friends"), card(email="another@cloud.com")))[0]


def test_duplicate_identity_is_not_arbitrarily_selected():
    assert not check_contact(CHECK, report(card(), card()))[0]


@pytest.mark.parametrize("category", ["marketing teammates", "not marketing team", "marketing team old"])
def test_categories_are_exact_members_not_substrings(category):
    assert not check_contact(CHECK, report(card(category=category)))[0]


def test_group_existence_does_not_require_a_specific_contact():
    assert check_contact({"category": "marketing team"}, report(card()))[0]


def test_empty_contact_check_is_invalid():
    with pytest.raises(ValueError, match="requires an email or category"):
        check_contact({}, report(card()))
