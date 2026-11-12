#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import requests


DEFAULT_USER_LANGUAGE = "en"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed ERPNext users and mock data via REST API")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--admin-username", required=True)
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--seed-file", required=True)
    return parser.parse_args()


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def login(session: requests.Session, base_url: str, username: str, password: str) -> None:
    response = session.post(
        f"{base_url}/api/method/login",
        data={"usr": username, "pwd": password},
        timeout=20,
    )
    response.raise_for_status()


def query_first(
    session: requests.Session,
    base_url: str,
    doctype: str,
    field_name: str,
    field_value: str,
) -> str | None:
    filters = json.dumps([[field_name, "=", field_value]])
    fields = json.dumps(["name"])
    query = urllib.parse.urlencode(
        {
            "filters": filters,
            "fields": fields,
            "limit_page_length": 1,
        }
    )
    response = session.get(
        f"{base_url}/api/resource/{urllib.parse.quote(doctype, safe='')}/?{query}",
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("data", [])
    if not items:
        return None
    return items[0].get("name")


def create_resource(session: requests.Session, base_url: str, doctype: str, doc: dict) -> bool:
    response = session.post(
        f"{base_url}/api/resource/{urllib.parse.quote(doctype, safe='')}",
        json={"data": doc},
        timeout=20,
    )

    # ERPNext may return 409/417-ish validation errors for duplicates/mandatory fields.
    if response.status_code >= 400:
        body = response.text.lower()
        if "duplicate" in body or "already exists" in body:
            return False

        # Keep startup robust: log validation/API errors and continue seeding.
        print(f"[seed] warning: could not create {doctype}: {response.status_code} {response.text[:240]}")
        return False

    return True


def create_resource_with_name(
    session: requests.Session,
    base_url: str,
    doctype: str,
    doc: dict,
) -> str | None:
    response = session.post(
        f"{base_url}/api/resource/{urllib.parse.quote(doctype, safe='')}",
        json={"data": doc},
        timeout=20,
    )

    if response.status_code >= 400:
        body = response.text.lower()
        if "duplicate" in body or "already exists" in body:
            return None
        print(f"[seed] warning: could not create {doctype}: {response.status_code} {response.text[:240]}")
        return None

    payload = response.json().get("data", {})
    return payload.get("name")


def call_method(
    session: requests.Session,
    base_url: str,
    method: str,
    payload: dict,
) -> dict | None:
    response = session.post(
        f"{base_url}/api/method/{method}",
        json=payload,
        timeout=20,
    )
    if response.status_code >= 400:
        print(f"[seed] warning: could not call {method}: {response.status_code} {response.text[:240]}")
        return None
    return response.json().get("message")


def strip_unsaved_metadata(value):
    if isinstance(value, list):
        return [strip_unsaved_metadata(row) for row in value]
    if not isinstance(value, dict):
        return value

    metadata_keys = {
        "name",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "_user_tags",
        "_comments",
        "_assign",
        "_liked_by",
    }
    cleaned = {}
    for key, item in value.items():
        if key in metadata_keys:
            continue
        cleaned[key] = strip_unsaved_metadata(item)
    return cleaned


def update_resource(
    session: requests.Session,
    base_url: str,
    doctype: str,
    name: str,
    doc: dict,
) -> bool:
    response = session.put(
        f"{base_url}/api/resource/{urllib.parse.quote(doctype, safe='')}/{urllib.parse.quote(name, safe='')}",
        json={"data": doc},
        timeout=20,
    )
    if response.status_code >= 400:
        print(f"[seed] warning: could not update {doctype}/{name}: {response.status_code} {response.text[:240]}")
        return False
    return True


def upsert_singleton(session: requests.Session, base_url: str, doctype: str, values: dict) -> bool:
    encoded = urllib.parse.quote(doctype, safe="")
    response = session.put(
        f"{base_url}/api/resource/{encoded}/{encoded}",
        json={"data": values},
        timeout=20,
    )
    if response.status_code >= 400:
        print(
            f"[seed] warning: could not update singleton {doctype}: "
            f"{response.status_code} {response.text[:240]}"
        )
        return False
    return True


def query_many(
    session: requests.Session,
    base_url: str,
    doctype: str,
    fields: list[str],
    filters: list[list[str]] | None = None,
    limit: int = 50,
) -> list[dict]:
    query = urllib.parse.urlencode(
        {
            "fields": json.dumps(fields),
            "filters": json.dumps(filters or []),
            "limit_page_length": limit,
        }
    )
    response = session.get(
        f"{base_url}/api/resource/{urllib.parse.quote(doctype, safe='')}/?{query}",
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    return list(payload.get("data", []))


def count_documents(
    session: requests.Session,
    base_url: str,
    doctype: str,
    filters: list[list[str]] | None = None,
    limit: int = 1000,
) -> int:
    return len(
        query_many(
            session=session,
            base_url=base_url,
            doctype=doctype,
            fields=["name"],
            filters=filters,
            limit=limit,
        )
    )


def sum_numeric_field(
    session: requests.Session,
    base_url: str,
    doctype: str,
    field_name: str,
    filters: list[list[str]] | None = None,
    limit: int = 1000,
) -> float:
    rows = query_many(
        session=session,
        base_url=base_url,
        doctype=doctype,
        fields=[field_name],
        filters=filters,
        limit=limit,
    )
    total = 0.0
    for row in rows:
        value = row.get(field_name)
        if value in (None, ""):
            continue
        total += float(value)
    return total


def get_resource(
    session: requests.Session,
    base_url: str,
    doctype: str,
    name: str,
) -> dict | None:
    response = session.get(
        f"{base_url}/api/resource/{urllib.parse.quote(doctype, safe='')}/{urllib.parse.quote(name, safe='')}",
        timeout=20,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json().get("data")


def submit_resource(
    session: requests.Session,
    base_url: str,
    doctype: str,
    name: str,
) -> bool:
    doc = get_resource(session=session, base_url=base_url, doctype=doctype, name=name)
    if not doc:
        return False

    if doc.get("docstatus") == 1:
        return True
    if doc.get("docstatus") == 2:
        return False

    response = session.post(
        f"{base_url}/api/method/frappe.client.submit",
        json={"doc": doc},
        timeout=20,
    )
    if response.status_code >= 400:
        print(
            f"[seed] warning: could not submit {doctype}/{name}: "
            f"{response.status_code} {response.text[:240]}"
        )
        return False
    return True


def get_default_company(session: requests.Session, base_url: str) -> str | None:
    companies = query_many(
        session=session,
        base_url=base_url,
        doctype="Company",
        fields=["name"],
        limit=1,
    )
    if not companies:
        return None
    return str(companies[0]["name"])


def get_company_warehouses(session: requests.Session, base_url: str, company: str) -> list[str]:
    warehouses = query_many(
        session=session,
        base_url=base_url,
        doctype="Warehouse",
        fields=["name"],
        filters=[["company", "=", company], ["is_group", "=", 0]],
        limit=100,
    )
    return [str(row["name"]) for row in warehouses if row.get("name")]


def get_default_warehouse(session: requests.Session, base_url: str, company: str) -> str | None:
    warehouses = get_company_warehouses(session=session, base_url=base_url, company=company)
    return warehouses[0] if warehouses else None


def ensure_master_prerequisites(session: requests.Session, base_url: str) -> None:
    # These references are required before Customers/Suppliers/Items can be created.
    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="UOM",
        unique_field="uom_name",
        docs=[{"uom_name": "Nos"}],
    )
    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="Territory",
        unique_field="territory_name",
        docs=[{"territory_name": "All Territories", "is_group": 1}],
    )
    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="Customer Group",
        unique_field="customer_group_name",
        docs=[{"customer_group_name": "All Customer Groups", "is_group": 1}],
    )
    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="Supplier Group",
        unique_field="supplier_group_name",
        docs=[{"supplier_group_name": "All Supplier Groups", "is_group": 1}],
    )
    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="Item Group",
        unique_field="item_group_name",
        docs=[{"item_group_name": "All Item Groups", "is_group": 1}],
    )

    # Company creation validates Warehouse Type links.
    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="Warehouse Type",
        unique_field="name",
        docs=[
            {"name": "Transit"},
            {"name": "Stores"},
            {"name": "Work In Progress"},
        ],
    )
    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="Stock Entry Type",
        unique_field="name",
        docs=[
            {"name": "Material Receipt", "purpose": "Material Receipt"},
            {"name": "Material Issue", "purpose": "Material Issue"},
            {"name": "Material Transfer", "purpose": "Material Transfer"},
        ],
    )

    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="Price List",
        unique_field="price_list_name",
        docs=[
            {
                "price_list_name": "Standard Selling",
                "currency": "EUR",
                "selling": 1,
            },
            {
                "price_list_name": "Standard Buying",
                "currency": "EUR",
                "buying": 1,
            },
        ],
    )


def ensure_company_and_fiscal_year(session: requests.Session, base_url: str) -> tuple[str | None, str | None]:
    company_name = get_default_company(session=session, base_url=base_url)
    if not company_name:
        created = upsert_by_field(
            session=session,
            base_url=base_url,
            doctype="Company",
            unique_field="company_name",
            doc={
                "company_name": "WebArena Corp",
                "abbr": "WAC",
                "default_currency": "EUR",
                "country": "France",
            },
        )
        if created:
            company_name = "WebArena Corp"

    current_year = str(date.today().year)
    fiscal_name = query_first(
        session=session,
        base_url=base_url,
        doctype="Fiscal Year",
        field_name="year",
        field_value=current_year,
    )
    if not fiscal_name:
        year = int(current_year)
        created = upsert_by_field(
            session=session,
            base_url=base_url,
            doctype="Fiscal Year",
            unique_field="year",
            doc={
                "year": current_year,
                "year_start_date": f"{year}-01-01",
                "year_end_date": f"{year}-12-31",
            },
        )
        if created:
            fiscal_name = current_year

    if company_name:
        defaults = {
            "default_company": company_name,
            "default_currency": "EUR",
        }
        if fiscal_name:
            defaults["current_fiscal_year"] = fiscal_name
        upsert_singleton(
            session=session,
            base_url=base_url,
            doctype="Global Defaults",
            values=defaults,
        )

    return company_name, fiscal_name


def ensure_dashboard_chart_filters(
    session: requests.Session,
    base_url: str,
    company: str,
    fiscal_year: str,
) -> None:
    chart_filters = {
        "Purchase Order Trends": {
            "period": "Monthly",
            "based_on": "Item",
            "company": company,
            "fiscal_year": fiscal_year,
        },
        "Sales Order Trends": {
            "period": "Monthly",
            "based_on": "Item",
            "company": company,
            "fiscal_year": fiscal_year,
        },
    }

    for chart_name, filters in chart_filters.items():
        update_resource(
            session=session,
            base_url=base_url,
            doctype="Dashboard Chart",
            name=chart_name,
            doc={"filters_json": json.dumps(filters)},
        )


def get_default_accounts(
    session: requests.Session,
    base_url: str,
    company: str,
) -> tuple[str, str] | None:
    rows = query_many(
        session=session,
        base_url=base_url,
        doctype="Account",
        fields=["name", "root_type", "account_type", "is_group"],
        filters=[["company", "=", company], ["is_group", "=", 0]],
        limit=500,
    )
    if not rows:
        return None

    def account_type_blank(row: dict) -> bool:
        value = row.get("account_type")
        return value in (None, "", "null")

    debit = next(
        (r["name"] for r in rows if account_type_blank(r) and r.get("root_type") in {"Asset", "Expense"}),
        None,
    )
    credit = next(
        (r["name"] for r in rows if account_type_blank(r) and r.get("root_type") in {"Income", "Liability", "Equity"}),
        None,
    )

    if not debit or not credit:
        return None
    return str(debit), str(credit)


def find_company_account(
    session: requests.Session,
    base_url: str,
    company: str,
    account_type: str | None = None,
    root_type: str | None = None,
    name_contains: str | None = None,
) -> str | None:
    filters = [["company", "=", company], ["is_group", "=", 0]]
    if account_type is not None:
        filters.append(["account_type", "=", account_type])
    if root_type is not None:
        filters.append(["root_type", "=", root_type])

    accounts = query_many(
        session=session,
        base_url=base_url,
        doctype="Account",
        fields=["name"],
        filters=filters,
        limit=100,
    )
    if not accounts:
        return None

    if name_contains:
        needle = name_contains.lower()
        match = next((row["name"] for row in accounts if needle in str(row["name"]).lower()), None)
        if match:
            return str(match)

    return str(accounts[0]["name"])


def upsert_by_field(
    session: requests.Session,
    base_url: str,
    doctype: str,
    unique_field: str,
    doc: dict,
    update_existing: bool = False,
) -> bool:
    unique_value = str(doc[unique_field])
    existing = query_first(
        session=session,
        base_url=base_url,
        doctype=doctype,
        field_name=unique_field,
        field_value=unique_value,
    )
    if existing:
        if update_existing:
            return update_resource(
                session=session,
                base_url=base_url,
                doctype=doctype,
                name=existing,
                doc=doc,
            )
        return True
    return create_resource(session=session, base_url=base_url, doctype=doctype, doc=doc)


def create_or_get_by_field(
    session: requests.Session,
    base_url: str,
    doctype: str,
    unique_field: str,
    doc: dict,
    update_existing: bool = False,
) -> str | None:
    unique_value = str(doc[unique_field])
    existing = query_first(
        session=session,
        base_url=base_url,
        doctype=doctype,
        field_name=unique_field,
        field_value=unique_value,
    )
    if existing:
        if update_existing:
            update_resource(
                session=session,
                base_url=base_url,
                doctype=doctype,
                name=existing,
                doc=doc,
            )
        return existing
    return create_resource_with_name(session=session, base_url=base_url, doctype=doctype, doc=doc)


def seed_users(session: requests.Session, base_url: str, users: list[dict]) -> None:
    for user in users:
        upsert_by_field(
            session=session,
            base_url=base_url,
            doctype="User",
            unique_field="email",
            doc=user,
            update_existing=True,
        )


def ensure_default_workspace_for_system_users(
    session: requests.Session,
    base_url: str,
    workspace: str,
) -> None:
    users = query_many(
        session=session,
        base_url=base_url,
        doctype="User",
        fields=["name", "default_workspace"],
        filters=[["enabled", "=", 1], ["user_type", "=", "System User"]],
        limit=500,
    )
    for row in users:
        name = str(row["name"])
        if row.get("default_workspace") == workspace:
            continue
        update_resource(
            session=session,
            base_url=base_url,
            doctype="User",
            name=name,
            doc={"default_workspace": workspace},
        )


def apply_user_defaults(users: list[dict]) -> None:
    for user in users:
        user.setdefault("language", DEFAULT_USER_LANGUAGE)
        user.setdefault("default_workspace", "Home")


def append_roles_to_user_docs(users: list[dict], role_names: list[str]) -> None:
    for user in users:
        roles = user.setdefault("roles", [])
        existing = {role.get("role") for role in roles}
        for role_name in role_names:
            if role_name not in existing:
                roles.append({"role": role_name})
                existing.add(role_name)


def ensure_roles_for_system_users(
    session: requests.Session,
    base_url: str,
    role_names: list[str],
) -> None:
    users = query_many(
        session=session,
        base_url=base_url,
        doctype="User",
        fields=["name"],
        filters=[["enabled", "=", 1], ["user_type", "=", "System User"]],
        limit=500,
    )
    for row in users:
        name = str(row["name"])
        user_doc = get_resource(session=session, base_url=base_url, doctype="User", name=name)
        if not user_doc:
            continue

        roles = user_doc.get("roles") or []
        existing = {role.get("role") for role in roles}
        changed = False
        for role_name in role_names:
            if role_name not in existing:
                roles.append({"role": role_name})
                existing.add(role_name)
                changed = True

        if changed:
            update_resource(
                session=session,
                base_url=base_url,
                doctype="User",
                name=name,
                doc={"roles": roles},
            )


def seed_doctype(
    session: requests.Session,
    base_url: str,
    doctype: str,
    unique_field: str,
    docs: list[dict],
) -> None:
    for doc in docs:
        upsert_by_field(
            session=session,
            base_url=base_url,
            doctype=doctype,
            unique_field=unique_field,
            doc=doc,
        )


def append_unique_docs(docs: list[dict], unique_field: str, new_docs: list[dict]) -> None:
    seen = {str(doc.get(unique_field)) for doc in docs if doc.get(unique_field) is not None}
    for doc in new_docs:
        value = doc.get(unique_field)
        if value is None:
            continue
        key = str(value)
        if key in seen:
            continue
        docs.append(doc)
        seen.add(key)


def add_days(date_value: str, days: int) -> str:
    return (date.fromisoformat(date_value) + timedelta(days=days)).isoformat()


def synthetic_current_year_date(index: int) -> str:
    today = date.today()
    month = ((index - 1) % today.month) + 1
    day = min(28, 3 + ((index * 5) % 23))
    candidate = date(today.year, month, day)
    if candidate > today:
        candidate = today
    return candidate.isoformat()


SYNTHETIC_CUSTOMERS = [
    ("Aster Logistics Group", "asterlogistics.com"),
    ("Boreal Retail Partners", "borealretail.com"),
    ("Caldera Workspace Solutions", "calderaworkspace.com"),
    ("Davenport Financial Services", "davenportfs.com"),
    ("Eastbridge Property Management", "eastbridgeproperties.com"),
    ("Fjordline Education Trust", "fjordlineeducation.org"),
    ("Granite Health Network", "granitehealthnetwork.com"),
    ("Harborview Publishing House", "harborviewpublishing.com"),
    ("Ironwood Manufacturing Ltd", "ironwoodmanufacturing.com"),
    ("Juniper Energy Services", "juniperenergy.com"),
    ("Keystone Architecture Studio", "keystonearchitecture.com"),
    ("Linden Digital Commerce", "lindendigital.com"),
    ("Maritime Export Agency", "maritimeexports.com"),
    ("Northstar Research Labs", "northstarresearchlabs.com"),
    ("Oakridge Consulting Group", "oakridgeconsulting.com"),
    ("Palisade Hospitality Co", "palisadehospitality.com"),
    ("Quarry Lane Design", "quarrylanedesign.com"),
    ("Redwood Civic Services", "redwoodcivicservices.org"),
    ("Summit Field Operations", "summitfieldops.com"),
    ("Tidewater Distribution", "tidewaterdistribution.com"),
]


SYNTHETIC_SUPPLIERS = [
    "Apex Commercial Interiors",
    "Beacon Office Supply",
    "Cobalt Technology Wholesale",
    "Dorset Facilities Group",
    "Evergreen Packaging Supply",
    "Frontier Electrical Distributors",
    "Grange Furniture Works",
    "Helios Print Systems",
    "Inlet Safety Products",
    "Juno Cable & Connectors",
    "Kingsley Storage Equipment",
    "Lattice Workspace Hardware",
    "Meridian Audio Visual",
    "Noble Paper Merchants",
    "Orchard Cleaning Supplies",
    "Portico Business Machines",
    "Quill Stationery Company",
    "Riverton Fixtures",
    "Sterling Facility Services",
    "Tandem Office Products",
]


SYNTHETIC_LEADS = [
    ("Elena Vargas", "elena.vargas"),
    ("Marcus Lee", "marcus.lee"),
    ("Priya Shah", "priya.shah"),
    ("Noah Keller", "noah.keller"),
    ("Amara Okafor", "amara.okafor"),
    ("Jonas Richter", "jonas.richter"),
    ("Sofia Moreau", "sofia.moreau"),
    ("Nadia Hassan", "nadia.hassan"),
    ("Liam O'Connor", "liam.oconnor"),
    ("Iris Chen", "iris.chen"),
]


SYNTHETIC_ITEM_CATALOG = [
    ("ERG-CHAIR-MESH", "Ergonomic Mesh Task Chair", 215.0),
    ("ERG-CHAIR-EXEC", "Executive High-Back Office Chair", 340.0),
    ("SITSTAND-DESK-140", "Sit-Stand Desk 140cm", 520.0),
    ("BENCH-DESK-2P", "Two-Person Bench Desk", 780.0),
    ("ACOUSTIC-PANEL-120", "Acoustic Desk Divider Panel", 95.0),
    ("MONITOR-QHD-27", "27in QHD Business Monitor", 310.0),
    ("MONITOR-UHD-32", "32in UHD Design Monitor", 540.0),
    ("USB-C-DOCK-PRO", "USB-C Triple Display Dock", 225.0),
    ("WEBCAM-CONF-HD", "HD Conference Webcam", 115.0),
    ("HEADSET-UC-WIRELESS", "Wireless UC Headset", 190.0),
    ("KEYBOARD-BUSINESS", "Business Keyboard with Number Pad", 62.0),
    ("MOUSE-ERG-WIRELESS", "Wireless Ergonomic Mouse", 54.0),
    ("CONF-PHONE-4MIC", "Four-Microphone Conference Phone", 420.0),
    ("PROJECTOR-LASER-4000", "Laser Projector 4000 Lumen", 960.0),
    ("SCREEN-MOTOR-120", "Motorized Projection Screen 120in", 380.0),
    ("PRINTER-MFP-A4", "A4 Multifunction Laser Printer", 410.0),
    ("SCANNER-DOC-60PPM", "Document Scanner 60ppm", 690.0),
    ("TONER-BLACK-HY", "High-Yield Black Toner Cartridge", 88.0),
    ("LABEL-PRINTER-NET", "Network Label Printer", 185.0),
    ("PAPER-A4-RECYCLED", "A4 Recycled Copy Paper Case", 42.0),
    ("NOTEBOOK-HARDCOVER-A5", "A5 Hardcover Meeting Notebook", 11.0),
    ("PEN-GEL-BLUE-12", "Blue Gel Pen Pack of 12", 18.0),
    ("MARKER-WB-ASSORTED", "Assorted Whiteboard Marker Set", 16.0),
    ("BINDER-A4-LEVER", "A4 Lever Arch Binder", 7.5),
    ("FOLDER-HANGING-A4", "A4 Hanging File Folder Pack", 24.0),
    ("ARCHIVE-BOX-HEAVY", "Heavy-Duty Archive Box", 8.5),
    ("FILING-CAB-4DRAWER", "Four-Drawer Filing Cabinet", 260.0),
    ("LOCKER-STAFF-6DOOR", "Six-Door Staff Locker", 620.0),
    ("BOOKCASE-180-OAK", "Oak Bookcase 180cm", 285.0),
    ("MEETING-TABLE-8P", "Eight-Person Meeting Table", 920.0),
    ("VISITOR-CHAIR-STACK", "Stackable Visitor Chair", 88.0),
    ("LOUNGE-CHAIR-RECEPTION", "Reception Lounge Chair", 360.0),
    ("COAT-STAND-METAL", "Metal Reception Coat Stand", 74.0),
    ("DESK-LAMP-LED-ADJ", "Adjustable LED Desk Lamp", 46.0),
    ("POWER-STRIP-8WAY", "Eight-Outlet Surge Protector", 35.0),
    ("UPS-1500VA", "1500VA UPS Battery Backup", 310.0),
    ("HDMI-CABLE-5M", "HDMI Cable 5m", 19.0),
    ("USB-C-CABLE-2M", "USB-C Cable 2m", 16.0),
    ("CABLE-TRAY-UNDERDESK", "Under-Desk Cable Tray", 32.0),
    ("FLOOR-MAT-CHAIR", "Hard Floor Chair Mat", 68.0),
    ("AIR-PURIFIER-OFFICE", "Office Air Purifier", 260.0),
    ("COFFEE-BREWER-COMM", "Commercial Coffee Brewer", 520.0),
    ("WATER-DISPENSER-FLOOR", "Floor Standing Water Dispenser", 330.0),
    ("FIRST-AID-CABINET", "Workplace First Aid Cabinet", 145.0),
    ("FIRE-EXT-CO2-5KG", "CO2 Fire Extinguisher 5kg", 115.0),
    ("SAFETY-SIGN-EXIT", "Illuminated Exit Sign", 72.0),
    ("CLEANING-CART", "Janitorial Cleaning Cart", 240.0),
    ("PAPER-TOWEL-CASE", "Paper Towel Case", 38.0),
    ("HAND-SOAP-REFILL", "Hand Soap Refill Case", 31.0),
    ("RECYCLING-BIN-60L", "60L Recycling Bin", 52.0),
    ("SHREDDER-CROSSCUT", "Cross-Cut Document Shredder", 240.0),
    ("SAFE-FIRE-RATED", "Fire-Rated Document Safe", 580.0),
    ("TIME-CLOCK-BIOMETRIC", "Biometric Time Clock", 410.0),
    ("BADGE-PRINTER-ID", "ID Badge Printer", 740.0),
    ("ACCESS-CARD-PACK", "Access Card Pack of 50", 95.0),
    ("WHITEBOARD-180-MAG", "Magnetic Whiteboard 180cm", 210.0),
    ("PINBOARD-FELT-120", "Felt Notice Board 120cm", 86.0),
    ("ROOM-SCHED-DISPLAY", "Room Scheduling Display", 490.0),
    ("TABLET-KIOSK-STAND", "Tablet Kiosk Floor Stand", 260.0),
    ("BARCODE-SCANNER-USB", "USB Barcode Scanner", 155.0),
]


PROJECT_ACCESS_ROLES = ["Projects User", "Projects Manager"]


SYNTHETIC_ASSET_LOCATIONS = [
    "Paris HQ - Workspace Floor",
    "Paris HQ - Server Room",
    "Lyon Support Office",
    "Berlin Sales Office",
    "Madrid Operations Hub",
]


SYNTHETIC_ASSET_CATEGORIES = [
    ("Computer Equipment", "Electronic Equipments"),
    ("Office Furniture", "Furnitures and Fixtures"),
    ("Facilities Equipment", "Office Equipments"),
    ("Audio Visual Equipment", "Office Equipments"),
]


SYNTHETIC_FIXED_ASSET_ITEMS = [
    ("ASSET-LAPTOP-PRO-14", "14in Business Laptop", "Computer Equipment", 1450.0),
    ("ASSET-MONITOR-VIDEO", "Video Editing Monitor", "Computer Equipment", 920.0),
    ("ASSET-NETWORK-SWITCH", "Managed Network Switch", "Computer Equipment", 780.0),
    ("ASSET-EXEC-DESK", "Executive Workstation Desk", "Office Furniture", 880.0),
    ("ASSET-CONF-TABLE", "Conference Room Table", "Office Furniture", 1750.0),
    ("ASSET-AIR-PURIFIER", "Commercial Air Purifier", "Facilities Equipment", 620.0),
    ("ASSET-COFFEE-SYSTEM", "Office Coffee System", "Facilities Equipment", 1100.0),
    ("ASSET-AV-CAMERA", "Meeting Room Camera System", "Audio Visual Equipment", 1350.0),
    ("ASSET-PROJECTOR-LASER", "Boardroom Laser Projector", "Audio Visual Equipment", 2200.0),
    ("ASSET-BADGE-PRINTER", "Security Badge Printer", "Computer Equipment", 840.0),
]


SYNTHETIC_PROJECTS = [
    ("HQ Collaboration Space Refresh", "Northwind Logistics", "High", 68000.0),
    ("Retail Back Office Standardization", "Sunset Retail Co", "Medium", 42000.0),
    ("Design Studio Equipment Rollout", "Atlas Design Studio", "High", 56000.0),
    ("Regional Procurement Process Upgrade", "Meridian Tech Solutions", "Medium", 38000.0),
    ("Facilities Preventive Maintenance Program", "Crestview Consulting", "Low", 24000.0),
    ("Document Workflow Modernization", "Harbor Digital Agency", "Medium", 51000.0),
]


PROJECT_TASK_TEMPLATES = [
    ("Confirm scope and site inventory", "Open", "High"),
    ("Finalize vendor quotes", "Working", "Medium"),
    ("Schedule delivery windows", "Working", "Medium"),
    ("Install and configure equipment", "Open", "High"),
    ("Complete user acceptance review", "Pending Review", "Medium"),
]


CRM_OPPORTUNITY_TEMPLATES = [
    ("Workspace lifecycle program", "Qualification", 38000.0, "Open"),
    ("Managed procurement retainer", "Needs Analysis", 54000.0, "Open"),
    ("Hybrid meeting room rollout", "Proposal", 72000.0, "Quotation"),
    ("Facilities supply agreement", "Negotiation", 29500.0, "Open"),
    ("Document management refresh", "Proposal", 46500.0, "Open"),
]


def ensure_minimum_seed_volume(seed_data: dict) -> None:
    synthetic = seed_data.get("synthetic_data", {})
    count = int(synthetic.get("count", 0))
    if count <= 0:
        return

    mock_data = seed_data.setdefault("mock_data", {})
    customers = mock_data.setdefault("customers", [])
    suppliers = mock_data.setdefault("suppliers", [])
    items = mock_data.setdefault("items", [])
    leads = mock_data.setdefault("leads", [])

    regions = [
        "North",
        "South",
        "East",
        "West",
        "Central",
        "Coastal",
        "Midlands",
        "Metro",
        "Valley",
        "Highlands",
    ]
    transaction_topics = [
        "Workspace refresh",
        "Regional office fit-out",
        "Hybrid meeting room rollout",
        "Operations supply replenishment",
        "Facilities maintenance order",
        "New employee onboarding kit",
        "Document management upgrade",
        "Reception area refurbishment",
        "IT accessory restock",
        "Training room equipment order",
    ]

    generated_customers: list[dict] = []
    for i in range(1, count + 1):
        base_name, _domain = SYNTHETIC_CUSTOMERS[(i - 1) % len(SYNTHETIC_CUSTOMERS)]
        customer_name = base_name
        if i > len(SYNTHETIC_CUSTOMERS):
            region = regions[((i - 1) // len(SYNTHETIC_CUSTOMERS)) % len(regions)]
            customer_name = f"{base_name} {region} Office"
        generated_customers.append(
            {
                "customer_name": customer_name,
                "customer_type": "Company",
                "customer_group": "All Customer Groups",
                "territory": "All Territories",
            }
        )
    append_unique_docs(customers, "customer_name", generated_customers)

    generated_suppliers: list[dict] = []
    for i in range(1, count + 1):
        base_name = SYNTHETIC_SUPPLIERS[(i - 1) % len(SYNTHETIC_SUPPLIERS)]
        supplier_name = base_name
        if i > len(SYNTHETIC_SUPPLIERS):
            region = regions[((i - 1) // len(SYNTHETIC_SUPPLIERS)) % len(regions)]
            supplier_name = f"{base_name} {region} Warehouse"
        generated_suppliers.append(
            {
                "supplier_name": supplier_name,
                "supplier_group": "All Supplier Groups",
                "supplier_type": "Company",
            }
        )
    append_unique_docs(suppliers, "supplier_name", generated_suppliers)

    generated_leads: list[dict] = []
    for i in range(1, count + 1):
        lead_name, local_part = SYNTHETIC_LEADS[(i - 1) % len(SYNTHETIC_LEADS)]
        _company_name, domain = SYNTHETIC_CUSTOMERS[(i - 1) % len(SYNTHETIC_CUSTOMERS)]
        if i > len(SYNTHETIC_CUSTOMERS):
            local_part = f"{local_part}.{i:02d}"
        generated_leads.append(
            {
                "lead_name": lead_name,
                "email_id": f"{local_part}@{domain}",
                "status": "Lead",
            }
        )
    append_unique_docs(leads, "email_id", generated_leads)

    generated_items: list[dict] = []
    item_count = max(20, min(60, count))
    for i in range(1, item_count + 1):
        item_code, item_name, standard_rate = SYNTHETIC_ITEM_CATALOG[i - 1]
        generated_items.append(
            {
                "item_code": item_code,
                "item_name": item_name,
                "item_group": "All Item Groups",
                "stock_uom": "Nos",
                "is_stock_item": 1,
                "standard_rate": standard_rate,
            }
        )
    append_unique_docs(items, "item_code", generated_items)

    stock_item_rows = [row for row in items if int(row.get("is_stock_item", 0)) == 1]
    if not stock_item_rows:
        return

    selling = seed_data.setdefault("selling", {})
    buying = seed_data.setdefault("buying", {})
    stock = seed_data.setdefault("stock", {})

    sales_orders = selling.setdefault("sales_orders", [])
    sales_invoices = selling.setdefault("sales_invoices", [])
    purchase_orders = buying.setdefault("purchase_orders", [])
    purchase_invoices = buying.setdefault("purchase_invoices", [])
    stock_entries = stock.setdefault("stock_entries", [])
    purchase_receipts = stock.setdefault("purchase_receipts", [])
    delivery_notes = stock.setdefault("delivery_notes", [])

    assets = seed_data.setdefault("assets", {})
    asset_locations = assets.setdefault("locations", [])
    asset_categories = assets.setdefault("asset_categories", [])
    fixed_asset_items = assets.setdefault("fixed_asset_items", [])
    asset_docs = assets.setdefault("assets", [])

    crm = seed_data.setdefault("crm", {})
    opportunity_types = crm.setdefault("opportunity_types", [])
    sales_stages = crm.setdefault("sales_stages", [])
    opportunities = crm.setdefault("opportunities", [])

    projects = seed_data.setdefault("projects", {})
    project_docs = projects.setdefault("projects", [])
    tasks = projects.setdefault("tasks", [])

    customer_names = [str(row["customer_name"]) for row in customers if row.get("customer_name")]
    supplier_names = [str(row["supplier_name"]) for row in suppliers if row.get("supplier_name")]
    if not customer_names or not supplier_names:
        return

    generated_sales_orders: list[dict] = []
    generated_sales_invoices: list[dict] = []
    generated_purchase_orders: list[dict] = []
    generated_purchase_invoices: list[dict] = []
    generated_stock_entries: list[dict] = []
    generated_purchase_receipts: list[dict] = []
    generated_delivery_notes: list[dict] = []

    def transaction_line_count(index: int) -> int:
        if index % 10 == 0:
            return 4
        if index % 4 == 0:
            return 3
        if index % 2 == 0:
            return 2
        return 1

    def item_rows(
        index: int,
        qty: int,
        rate_multiplier: float,
        rate_field: str = "rate",
    ) -> list[dict]:
        line_count = min(transaction_line_count(index), len(stock_item_rows))
        rows: list[dict] = []
        for line_index in range(line_count):
            item = stock_item_rows[(index - 1 + line_index * 7) % len(stock_item_rows)]
            item_rate = float(item.get("standard_rate", 50.0))
            rows.append(
                {
                    "item_code": str(item["item_code"]),
                    "qty": max(1, qty + line_index),
                    rate_field: round(item_rate * rate_multiplier, 2),
                }
            )
        return rows

    for i in range(1, count + 1):
        customer = customer_names[(i - 1) % len(customer_names)]
        supplier = supplier_names[(i - 1) % len(supplier_names)]
        topic = transaction_topics[(i - 1) % len(transaction_topics)]
        qty = (i % 8) + 2

        generated_sales_orders.append(
            {
                "customer": customer,
                "remarks": f"{topic} sales order {i:03d}",
                "submit": True,
                "items": item_rows(i, qty, 1.25),
            }
        )
        generated_sales_invoices.append(
            {
                "customer": customer,
                "remarks": f"{topic} customer invoice {i:03d}",
                "submit": True,
                "items": item_rows(i + 3, max(1, qty - 1), 1.25),
            }
        )
        generated_purchase_orders.append(
            {
                "supplier": supplier,
                "remarks": f"{topic} purchase order {i:03d}",
                "submit": True,
                "items": item_rows(i + 5, qty + 5, 0.8),
            }
        )
        generated_purchase_invoices.append(
            {
                "supplier": supplier,
                "remarks": f"{topic} supplier invoice {i:03d}",
                "bill_no": f"SUP-{i:04d}",
                "submit": True,
                "items": item_rows(i + 7, qty + 3, 0.8),
            }
        )
        generated_stock_entries.append(
            {
                "stock_entry_type": "Material Receipt",
                "remarks": f"{topic} warehouse receipt {i:03d}",
                "submit": True,
                "items": item_rows(
                    i + 9,
                    qty + 7,
                    0.8,
                    rate_field="basic_rate",
                ),
            }
        )
        if i <= min(18, count):
            generated_purchase_receipts.append(
                {
                    "supplier": supplier,
                    "remarks": f"{topic} inbound receipt {i:03d}",
                    "submit": True,
                    "items": item_rows(i + 11, qty + 9, 0.82),
                }
            )
        if i <= min(10, count):
            generated_delivery_notes.append(
                {
                    "customer": customer,
                    "remarks": f"{topic} outbound delivery {i:03d}",
                    "submit": True,
                    "items": item_rows(i + 13, max(1, qty - 1), 1.18),
                }
            )

    append_unique_docs(sales_orders, "remarks", generated_sales_orders)
    append_unique_docs(sales_invoices, "remarks", generated_sales_invoices)
    append_unique_docs(purchase_orders, "remarks", generated_purchase_orders)
    append_unique_docs(purchase_invoices, "remarks", generated_purchase_invoices)
    append_unique_docs(stock_entries, "remarks", generated_stock_entries)
    append_unique_docs(purchase_receipts, "remarks", generated_purchase_receipts)
    append_unique_docs(delivery_notes, "remarks", generated_delivery_notes)

    append_unique_docs(
        asset_locations,
        "location_name",
        [{"location_name": location} for location in SYNTHETIC_ASSET_LOCATIONS],
    )
    append_unique_docs(
        asset_categories,
        "asset_category_name",
        [
            {
                "asset_category_name": category,
                "fixed_asset_account_hint": account_hint,
            }
            for category, account_hint in SYNTHETIC_ASSET_CATEGORIES
        ],
    )
    append_unique_docs(
        fixed_asset_items,
        "item_code",
        [
            {
                "item_code": item_code,
                "item_name": item_name,
                "item_group": "All Item Groups",
                "stock_uom": "Nos",
                "is_stock_item": 0,
                "is_fixed_asset": 1,
                "auto_create_assets": 0,
                "asset_category": category,
                "standard_rate": rate,
            }
            for item_code, item_name, category, rate in SYNTHETIC_FIXED_ASSET_ITEMS
        ],
    )
    append_unique_docs(
        asset_docs,
        "asset_name",
        [
            {
                "asset_name": f"{item_name} {index:02d}",
                "item_code": item_code,
                "asset_category": category,
                "location": SYNTHETIC_ASSET_LOCATIONS[(index - 1) % len(SYNTHETIC_ASSET_LOCATIONS)],
                "purchase_date": synthetic_current_year_date(index + 3),
                "available_for_use_date": add_days(synthetic_current_year_date(index + 3), 2),
                "gross_purchase_amount": rate,
                "is_existing_asset": 1,
                "asset_quantity": 1,
            }
            for index, (item_code, item_name, category, rate) in enumerate(SYNTHETIC_FIXED_ASSET_ITEMS, start=1)
        ],
    )

    append_unique_docs(
        opportunity_types,
        "name",
        [{"name": "Sales"}, {"name": "Renewal"}, {"name": "Implementation"}],
    )
    append_unique_docs(
        sales_stages,
        "stage_name",
        [
            {"stage_name": "Qualification"},
            {"stage_name": "Needs Analysis"},
            {"stage_name": "Proposal"},
            {"stage_name": "Negotiation"},
            {"stage_name": "Closed Won"},
        ],
    )
    generated_opportunities: list[dict] = []
    for index in range(1, min(18, count) + 1):
        customer = customer_names[(index - 1) % len(customer_names)]
        title, sales_stage, amount, status = CRM_OPPORTUNITY_TEMPLATES[
            (index - 1) % len(CRM_OPPORTUNITY_TEMPLATES)
        ]
        item = stock_item_rows[(index - 1) % len(stock_item_rows)]
        item_code = str(item["item_code"])
        item_rate = round(float(item.get("standard_rate", 50.0)) * 1.3, 2)
        qty = (index % 5) + 2
        generated_opportunities.append(
            {
                "title": f"{customer} - {title}",
                "opportunity_from": "Customer",
                "party_name": customer,
                "opportunity_type": "Sales",
                "status": status,
                "transaction_date": synthetic_current_year_date(index + 1),
                "expected_closing": add_days(synthetic_current_year_date(index + 1), 30),
                "currency": "EUR",
                "conversion_rate": 1,
                "opportunity_amount": amount,
                "sales_stage": sales_stage,
                "probability": min(90, 30 + index * 3),
                "items": [
                    {
                        "item_code": item_code,
                        "qty": qty,
                        "uom": "Nos",
                        "rate": item_rate,
                        "base_rate": item_rate,
                        "amount": round(qty * item_rate, 2),
                        "base_amount": round(qty * item_rate, 2),
                    }
                ],
            }
        )
    append_unique_docs(opportunities, "title", generated_opportunities)

    generated_projects: list[dict] = []
    generated_tasks: list[dict] = []
    for project_index, (project_name, customer, priority, costing) in enumerate(SYNTHETIC_PROJECTS, start=1):
        expected_start = synthetic_current_year_date(project_index + 2)
        expected_end = add_days(expected_start, 45 + project_index * 3)
        generated_projects.append(
            {
                "project_name": project_name,
                "status": "Open",
                "is_active": "Yes",
                "priority": priority,
                "percent_complete_method": "Task Completion",
                "expected_start_date": expected_start,
                "expected_end_date": expected_end,
                "customer": customer,
                "estimated_costing": costing,
            }
        )
        for task_index, (subject, status, task_priority) in enumerate(PROJECT_TASK_TEMPLATES, start=1):
            task_start = add_days(expected_start, (task_index - 1) * 6)
            generated_tasks.append(
                {
                    "subject": f"{project_name}: {subject}",
                    "project_name": project_name,
                    "status": status,
                    "priority": task_priority,
                    "exp_start_date": task_start,
                    "exp_end_date": add_days(task_start, 5),
                    "expected_time": 8 + task_index * 2,
                    "description": f"{subject} for {project_name}.",
                }
            )
    append_unique_docs(project_docs, "project_name", generated_projects)
    append_unique_docs(tasks, "subject", generated_tasks)

    for index, doc in enumerate(sales_orders, start=1):
        transaction_date = doc.setdefault("transaction_date", synthetic_current_year_date(index))
        doc.setdefault("delivery_date", add_days(transaction_date, 10))

    for index, doc in enumerate(sales_invoices, start=1):
        posting_date = doc.setdefault("posting_date", synthetic_current_year_date(index + 2))
        doc.setdefault("due_date", add_days(posting_date, 14))

    for index, doc in enumerate(purchase_orders, start=1):
        transaction_date = doc.setdefault("transaction_date", synthetic_current_year_date(index + 4))
        doc.setdefault("schedule_date", add_days(transaction_date, 7))

    for index, doc in enumerate(purchase_invoices, start=1):
        posting_date = doc.setdefault("posting_date", synthetic_current_year_date(index + 6))
        doc.setdefault("bill_date", posting_date)
        doc.setdefault("due_date", add_days(posting_date, 14))

    for index, doc in enumerate(stock_entries, start=1):
        doc.setdefault("posting_date", synthetic_current_year_date(index + 8))

    for index, doc in enumerate(purchase_receipts, start=1):
        doc.setdefault("posting_date", synthetic_current_year_date(index + 10))
        doc.setdefault("posting_time", "09:00:00")

    for index, doc in enumerate(delivery_notes, start=1):
        doc.setdefault("posting_date", synthetic_current_year_date(index + 12))
        doc.setdefault("posting_time", "14:00:00")


def seed_sales_invoices(
    session: requests.Session,
    base_url: str,
    company: str,
    docs: list[dict],
) -> None:
    today = str(date.today())
    for doc in docs:
        remarks = doc.get("remarks", "Seeded sample sales invoice")
        payload = {
            "customer": doc["customer"],
            "company": company,
            "set_posting_time": doc.get("set_posting_time", 1),
            "posting_date": doc.get("posting_date", today),
            "due_date": doc.get("due_date", today),
            "selling_price_list": doc.get("selling_price_list", "Standard Selling"),
            "price_list_currency": doc.get("price_list_currency", "EUR"),
            "plc_conversion_rate": doc.get("plc_conversion_rate", 1),
            "items": doc["items"],
            "remarks": remarks,
        }
        name = create_resource_with_name(
            session=session,
            base_url=base_url,
            doctype="Sales Invoice",
            doc=payload,
        )
        if name and doc.get("submit", False):
            submit_resource(
                session=session,
                base_url=base_url,
                doctype="Sales Invoice",
                name=name,
            )


def seed_purchase_invoices(
    session: requests.Session,
    base_url: str,
    company: str,
    docs: list[dict],
) -> None:
    today = str(date.today())
    for doc in docs:
        remarks = doc.get("remarks", "Seeded sample purchase invoice")
        payload = {
            "supplier": doc["supplier"],
            "company": company,
            "set_posting_time": doc.get("set_posting_time", 1),
            "posting_date": doc.get("posting_date", today),
            "bill_date": doc.get("bill_date", today),
            "due_date": doc.get("due_date", doc.get("bill_date", today)),
            "items": doc["items"],
            "remarks": remarks,
        }
        if doc.get("bill_no"):
            payload["bill_no"] = doc["bill_no"]

        name = create_resource_with_name(
            session=session,
            base_url=base_url,
            doctype="Purchase Invoice",
            doc=payload,
        )
        if name and doc.get("submit", False):
            submit_resource(
                session=session,
                base_url=base_url,
                doctype="Purchase Invoice",
                name=name,
            )


def seed_stock_entries(
    session: requests.Session,
    base_url: str,
    company: str,
    docs: list[dict],
) -> None:
    today = str(date.today())
    warehouse = get_default_warehouse(session=session, base_url=base_url, company=company)

    for doc in docs:
        remarks = doc.get("remarks", "Seeded sample stock entry")
        stock_entry_type = doc.get("stock_entry_type", "Material Receipt")
        payload_items: list[dict] = []
        for item in doc.get("items", []):
            item_row = dict(item)
            if stock_entry_type == "Material Receipt":
                item_row.setdefault("t_warehouse", warehouse)
            elif stock_entry_type == "Material Issue":
                item_row.setdefault("s_warehouse", warehouse)
            else:
                item_row.setdefault("s_warehouse", warehouse)
                item_row.setdefault("t_warehouse", warehouse)
            rate = item_row.get("basic_rate", item_row.get("rate", item_row.get("valuation_rate")))
            if rate is not None:
                qty = float(item_row.get("qty", 0) or 0)
                valuation_rate = round(float(rate), 2)
                amount = round(qty * valuation_rate, 2)
                item_row.setdefault("basic_rate", valuation_rate)
                item_row.setdefault("valuation_rate", valuation_rate)
                item_row.setdefault("amount", amount)
                item_row.setdefault("basic_amount", amount)
            payload_items.append(item_row)

        payload = {
            "company": company,
            "purpose": doc.get("purpose", stock_entry_type),
            "stock_entry_type": stock_entry_type,
            "set_posting_time": doc.get("set_posting_time", 1),
            "posting_date": doc.get("posting_date", today),
            "items": payload_items,
            "remarks": remarks,
        }
        name = create_resource_with_name(
            session=session,
            base_url=base_url,
            doctype="Stock Entry",
            doc=payload,
        )

        if name and doc.get("submit", True):
            submit_resource(
                session=session,
                base_url=base_url,
                doctype="Stock Entry",
                name=name,
            )


def seed_purchase_receipts(
    session: requests.Session,
    base_url: str,
    company: str,
    docs: list[dict],
) -> None:
    today = str(date.today())
    warehouses = get_company_warehouses(session=session, base_url=base_url, company=company)
    default_warehouse = warehouses[0] if warehouses else None

    for index, doc in enumerate(docs, start=1):
        remarks = doc.get("remarks", "Seeded sample purchase receipt")
        warehouse = doc.get("set_warehouse")
        if not warehouse and warehouses:
            warehouse = warehouses[(index - 1) % len(warehouses)]
        if not warehouse:
            warehouse = default_warehouse

        payload_items: list[dict] = []
        for item in doc.get("items", []):
            item_row = dict(item)
            item_row.setdefault("warehouse", warehouse)
            payload_items.append(item_row)

        payload = {
            "supplier": doc["supplier"],
            "company": company,
            "set_posting_time": doc.get("set_posting_time", 1),
            "posting_date": doc.get("posting_date", today),
            "posting_time": doc.get("posting_time", "09:00:00"),
            "set_warehouse": doc.get("set_warehouse", warehouse),
            "currency": doc.get("currency", "EUR"),
            "conversion_rate": doc.get("conversion_rate", 1),
            "items": payload_items,
            "remarks": remarks,
        }
        name = create_resource_with_name(
            session=session,
            base_url=base_url,
            doctype="Purchase Receipt",
            doc=payload,
        )
        if name and doc.get("submit", True):
            submit_resource(
                session=session,
                base_url=base_url,
                doctype="Purchase Receipt",
                name=name,
            )


def seed_delivery_notes(
    session: requests.Session,
    base_url: str,
    company: str,
    docs: list[dict],
) -> None:
    today = str(date.today())
    warehouse = get_default_warehouse(session=session, base_url=base_url, company=company)

    for doc in docs:
        remarks = doc.get("remarks", "Seeded sample delivery note")
        payload_items: list[dict] = []
        for item in doc.get("items", []):
            item_row = dict(item)
            item_row.setdefault("warehouse", warehouse)
            payload_items.append(item_row)

        payload = {
            "customer": doc["customer"],
            "company": company,
            "set_posting_time": doc.get("set_posting_time", 1),
            "posting_date": doc.get("posting_date", today),
            "posting_time": doc.get("posting_time", "14:00:00"),
            "set_warehouse": doc.get("set_warehouse", warehouse),
            "currency": doc.get("currency", "EUR"),
            "conversion_rate": doc.get("conversion_rate", 1),
            "selling_price_list": doc.get("selling_price_list", "Standard Selling"),
            "price_list_currency": doc.get("price_list_currency", "EUR"),
            "plc_conversion_rate": doc.get("plc_conversion_rate", 1),
            "items": payload_items,
            "remarks": remarks,
        }
        name = create_resource_with_name(
            session=session,
            base_url=base_url,
            doctype="Delivery Note",
            doc=payload,
        )
        if name and doc.get("submit", True):
            submit_resource(
                session=session,
                base_url=base_url,
                doctype="Delivery Note",
                name=name,
            )


def seed_item_prices(
    session: requests.Session,
    base_url: str,
    docs: list[dict],
) -> None:
    for doc in docs:
        item_code = doc.get("item_code")
        price_list = doc.get("price_list")
        if not item_code or not price_list:
            continue

        filters = json.dumps([
            ["item_code", "=", item_code],
            ["price_list", "=", price_list],
        ])
        query = urllib.parse.urlencode({
            "filters": filters,
            "fields": json.dumps(["name"]),
            "limit_page_length": 1,
        })
        response = session.get(
            f"{base_url}/api/resource/{urllib.parse.quote('Item Price', safe='')}/?{query}",
            timeout=20,
        )
        if response.ok and response.json().get("data"):
            continue

        create_resource(session=session, base_url=base_url, doctype="Item Price", doc=doc)


def seed_journal_entries(
    session: requests.Session,
    base_url: str,
    company: str,
    docs: list[dict],
) -> None:
    accounts = get_default_accounts(session=session, base_url=base_url, company=company)
    if not accounts:
        print("[seed] warning: no suitable default accounts found; skipping Journal Entry seed")
        return

    debit_account, credit_account = accounts
    today = str(date.today())

    for doc in docs:
        amount = float(doc.get("amount", 250.0))
        payload = {
            "voucher_type": "Journal Entry",
            "company": company,
            "set_posting_time": doc.get("set_posting_time", 1),
            "posting_date": doc.get("posting_date", today),
            "user_remark": doc.get("user_remark", "Seeded sample journal entry"),
            "accounts": [
                {
                    "account": debit_account,
                    "debit_in_account_currency": amount,
                },
                {
                    "account": credit_account,
                    "credit_in_account_currency": amount,
                },
            ],
        }
        create_resource(
            session=session,
            base_url=base_url,
            doctype="Journal Entry",
            doc=payload,
        )


def seed_assets(
    session: requests.Session,
    base_url: str,
    company: str,
    docs: dict,
) -> None:
    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="Location",
        unique_field="location_name",
        docs=docs.get("locations", []),
    )

    accumulated_depreciation = find_company_account(
        session=session,
        base_url=base_url,
        company=company,
        account_type="Accumulated Depreciation",
    )
    depreciation_expense = find_company_account(
        session=session,
        base_url=base_url,
        company=company,
        account_type="Depreciation",
    )
    cwip_account = find_company_account(
        session=session,
        base_url=base_url,
        company=company,
        account_type="Capital Work in Progress",
    )

    for category in docs.get("asset_categories", []):
        fixed_asset = find_company_account(
            session=session,
            base_url=base_url,
            company=company,
            account_type="Fixed Asset",
            name_contains=category.get("fixed_asset_account_hint"),
        )
        if not fixed_asset:
            print(f"[seed] warning: no fixed asset account found for {category['asset_category_name']}")
            continue

        account_row = {
            "company_name": company,
            "fixed_asset_account": fixed_asset,
        }
        if accumulated_depreciation:
            account_row["accumulated_depreciation_account"] = accumulated_depreciation
        if depreciation_expense:
            account_row["depreciation_expense_account"] = depreciation_expense
        if cwip_account:
            account_row["capital_work_in_progress_account"] = cwip_account

        create_or_get_by_field(
            session=session,
            base_url=base_url,
            doctype="Asset Category",
            unique_field="asset_category_name",
            doc={
                "asset_category_name": category["asset_category_name"],
                "accounts": [account_row],
            },
            update_existing=True,
        )

    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="Item",
        unique_field="item_code",
        docs=docs.get("fixed_asset_items", []),
    )

    today = str(date.today())
    for doc in docs.get("assets", []):
        purchase_date = doc.get("purchase_date", today)
        payload = {
            "asset_name": doc["asset_name"],
            "item_code": doc["item_code"],
            "asset_category": doc["asset_category"],
            "company": company,
            "location": doc["location"],
            "asset_owner": doc.get("asset_owner", "Company"),
            "asset_owner_company": doc.get("asset_owner_company", company),
            "purchase_date": purchase_date,
            "available_for_use_date": doc.get("available_for_use_date", purchase_date),
            "gross_purchase_amount": doc.get("gross_purchase_amount", 0),
            "is_existing_asset": doc.get("is_existing_asset", 1),
            "asset_quantity": doc.get("asset_quantity", 1),
        }
        name = create_or_get_by_field(
            session=session,
            base_url=base_url,
            doctype="Asset",
            unique_field="asset_name",
            doc=payload,
        )
        if name and doc.get("submit", True):
            submit_resource(
                session=session,
                base_url=base_url,
                doctype="Asset",
                name=name,
            )


def seed_crm(
    session: requests.Session,
    base_url: str,
    company: str,
    docs: dict,
) -> None:
    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="Opportunity Type",
        unique_field="name",
        docs=docs.get("opportunity_types", []),
    )
    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="Sales Stage",
        unique_field="stage_name",
        docs=docs.get("sales_stages", []),
    )

    today = str(date.today())
    for doc in docs.get("opportunities", []):
        payload = {
            "title": doc["title"],
            "opportunity_from": doc.get("opportunity_from", "Customer"),
            "party_name": doc["party_name"],
            "opportunity_type": doc.get("opportunity_type", "Sales"),
            "status": doc.get("status", "Open"),
            "transaction_date": doc.get("transaction_date", today),
            "expected_closing": doc.get("expected_closing", today),
            "currency": doc.get("currency", "EUR"),
            "conversion_rate": doc.get("conversion_rate", 1),
            "opportunity_amount": doc.get("opportunity_amount", 0),
            "sales_stage": doc.get("sales_stage"),
            "probability": doc.get("probability"),
            "company": company,
            "items": doc.get("items", []),
        }
        create_or_get_by_field(
            session=session,
            base_url=base_url,
            doctype="Opportunity",
            unique_field="title",
            doc=payload,
            update_existing=True,
        )


def seed_projects(
    session: requests.Session,
    base_url: str,
    company: str,
    docs: dict,
) -> None:
    project_names: dict[str, str] = {}

    for doc in docs.get("projects", []):
        payload = dict(doc)
        project_label = str(payload["project_name"])
        payload["company"] = company
        name = create_or_get_by_field(
            session=session,
            base_url=base_url,
            doctype="Project",
            unique_field="project_name",
            doc=payload,
            update_existing=True,
        )
        if name:
            project_names[project_label] = name

    for doc in docs.get("tasks", []):
        payload = dict(doc)
        project_label = payload.pop("project_name", None)
        if project_label:
            project_name = project_names.get(str(project_label))
            if not project_name:
                project_name = query_first(
                    session=session,
                    base_url=base_url,
                    doctype="Project",
                    field_name="project_name",
                    field_value=str(project_label),
                )
            if project_name:
                payload["project"] = project_name
        create_or_get_by_field(
            session=session,
            base_url=base_url,
            doctype="Task",
            unique_field="subject",
            doc=payload,
            update_existing=True,
        )


def verify_seed_documents(session: requests.Session, base_url: str) -> None:
    # Task 049 scores the agent discovering and creating this prerequisite.
    # This verifier runs before capturing the clean image/reset snapshot.
    if query_first(
        session=session,
        base_url=base_url,
        doctype="UOM",
        field_name="uom_name",
        field_value="Percent",
    ) is not None:
        raise RuntimeError("Seed verification failed: task 049 requires Percent UOM to be absent")

    required_counts = [
        ("customers", "Customer", None, 50),
        ("suppliers", "Supplier", None, 50),
        ("items", "Item", None, 50),
        ("submitted sales orders", "Sales Order", [["docstatus", "=", 1]], 50),
        ("submitted sales invoices", "Sales Invoice", [["docstatus", "=", 1]], 50),
        ("submitted purchase orders", "Purchase Order", [["docstatus", "=", 1]], 50),
        ("billed purchase orders", "Purchase Order", [["docstatus", "=", 1], ["per_billed", ">", 0]], 10),
        (
            "purchase orders to receive",
            "Purchase Order",
            [["docstatus", "=", 1], ["status", "in", ["To Receive and Bill", "To Receive"]]],
            50,
        ),
        ("submitted purchase receipts", "Purchase Receipt", [["docstatus", "=", 1]], 10),
        ("submitted delivery notes", "Delivery Note", [["docstatus", "=", 1]], 5),
        ("submitted purchase invoices", "Purchase Invoice", [["docstatus", "=", 1]], 40),
        ("submitted stock entries", "Stock Entry", [["docstatus", "=", 1]], 50),
        ("assets", "Asset", None, 8),
        ("opportunities", "Opportunity", None, 10),
        ("projects", "Project", None, 5),
        ("tasks", "Task", None, 20),
    ]
    shortfalls: list[str] = []
    for label, doctype, filters, minimum in required_counts:
        count = count_documents(
            session=session,
            base_url=base_url,
            doctype=doctype,
            filters=filters,
        )
        if count < minimum:
            shortfalls.append(f"{label} ({count}/{minimum})")

    stock_value = sum_numeric_field(
        session=session,
        base_url=base_url,
        doctype="Bin",
        field_name="stock_value",
    )
    if stock_value <= 0:
        shortfalls.append("warehouse stock value (0/>0)")

    warehouse_stock_rows = query_many(
        session=session,
        base_url=base_url,
        doctype="Bin",
        fields=["warehouse", "stock_value"],
        limit=1000,
    )
    warehouses_with_stock = {
        str(row["warehouse"])
        for row in warehouse_stock_rows
        if row.get("warehouse") and float(row.get("stock_value") or 0) > 0
    }
    if len(warehouses_with_stock) < 3:
        shortfalls.append(f"warehouse stock distribution ({len(warehouses_with_stock)}/3)")

    if shortfalls:
        raise RuntimeError("Seed verification failed; insufficient " + ", ".join(shortfalls))
    print("[seed] verification passed.")


def seed_purchase_orders(
    session: requests.Session,
    base_url: str,
    company: str,
    docs: list[dict],
) -> None:
    today = str(date.today())
    warehouse = get_default_warehouse(session=session, base_url=base_url, company=company)

    for doc in docs:
        remarks = doc.get("remarks", "Seeded sample purchase order")
        payload = {
            "supplier": doc["supplier"],
            "company": company,
            "transaction_date": doc.get("transaction_date", today),
            "schedule_date": doc.get("schedule_date", today),
            "set_warehouse": doc.get("set_warehouse", warehouse),
            "items": doc["items"],
            "remarks": remarks,
        }
        name = create_resource_with_name(
            session=session,
            base_url=base_url,
            doctype="Purchase Order",
            doc=payload,
        )

        if name and doc.get("submit", True):
            submit_resource(
                session=session,
                base_url=base_url,
                doctype="Purchase Order",
                name=name,
            )


def seed_purchase_order_bills(
    session: requests.Session,
    base_url: str,
    company: str,
    count: int = 12,
) -> None:
    purchase_orders = query_many(
        session=session,
        base_url=base_url,
        doctype="Purchase Order",
        fields=["name", "supplier", "transaction_date"],
        filters=[["docstatus", "=", 1], ["per_billed", "=", 0]],
        limit=count,
    )
    for index, order in enumerate(purchase_orders, start=1):
        po_name = str(order["name"])
        supplier = str(order["supplier"])
        bill_no = f"PO-BILL-{index:04d}"
        existing = query_many(
            session=session,
            base_url=base_url,
            doctype="Purchase Invoice",
            fields=["name"],
            filters=[["supplier", "=", supplier], ["bill_no", "=", bill_no]],
            limit=1,
        )
        if existing:
            continue

        invoice = call_method(
            session=session,
            base_url=base_url,
            method="erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_invoice",
            payload={"source_name": po_name},
        )
        if not invoice:
            continue

        posting_date = add_days(str(order.get("transaction_date") or date.today()), 7)
        if date.fromisoformat(posting_date) > date.today():
            posting_date = date.today().isoformat()
        due_date = add_days(posting_date, 14)
        invoice = strip_unsaved_metadata(invoice)
        invoice.update(
            {
                "company": company,
                "set_posting_time": 1,
                "posting_date": posting_date,
                "bill_date": posting_date,
                "due_date": due_date,
                "bill_no": bill_no,
                "remarks": f"Seeded billed purchase order {po_name}",
            }
        )
        for payment_row in invoice.get("payment_schedule", []):
            payment_row["due_date"] = due_date
        name = create_resource_with_name(
            session=session,
            base_url=base_url,
            doctype="Purchase Invoice",
            doc=invoice,
        )
        if name:
            submit_resource(
                session=session,
                base_url=base_url,
                doctype="Purchase Invoice",
                name=name,
            )


def seed_sales_orders(
    session: requests.Session,
    base_url: str,
    company: str,
    docs: list[dict],
) -> None:
    today = str(date.today())
    warehouse = get_default_warehouse(session=session, base_url=base_url, company=company)

    for doc in docs:
        remarks = doc.get("remarks", "Seeded sample sales order")
        payload = {
            "customer": doc["customer"],
            "company": company,
            "transaction_date": doc.get("transaction_date", today),
            "delivery_date": doc.get("delivery_date", today),
            "set_warehouse": doc.get("set_warehouse", warehouse),
            "selling_price_list": doc.get("selling_price_list", "Standard Selling"),
            "price_list_currency": doc.get("price_list_currency", "EUR"),
            "plc_conversion_rate": doc.get("plc_conversion_rate", 1),
            "items": doc["items"],
            "remarks": remarks,
        }
        name = create_resource_with_name(
            session=session,
            base_url=base_url,
            doctype="Sales Order",
            doc=payload,
        )

        if name and doc.get("submit", True):
            submit_resource(
                session=session,
                base_url=base_url,
                doctype="Sales Order",
                name=name,
            )


def main() -> None:
    args = parse_args()

    seed_data = json.loads(Path(args.seed_file).read_text(encoding="utf-8"))
    base_url = normalize_base_url(args.base_url)

    session = requests.Session()
    login(
        session=session,
        base_url=base_url,
        username=args.admin_username,
        password=args.admin_password,
    )

    ensure_minimum_seed_volume(seed_data)

    users = seed_data.get("users", [])
    apply_user_defaults(users)
    append_roles_to_user_docs(users, PROJECT_ACCESS_ROLES)
    seed_users(session=session, base_url=base_url, users=users)
    ensure_roles_for_system_users(session=session, base_url=base_url, role_names=PROJECT_ACCESS_ROLES)
    ensure_default_workspace_for_system_users(
        session=session,
        base_url=base_url,
        workspace="Home",
    )

    ensure_master_prerequisites(session=session, base_url=base_url)
    company, fiscal_year = ensure_company_and_fiscal_year(session=session, base_url=base_url)
    if company and fiscal_year:
        ensure_dashboard_chart_filters(
            session=session,
            base_url=base_url,
            company=company,
            fiscal_year=fiscal_year,
        )

    mock_data = seed_data.get("mock_data", {})
    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="Customer",
        unique_field="customer_name",
        docs=mock_data.get("customers", []),
    )
    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="Supplier",
        unique_field="supplier_name",
        docs=mock_data.get("suppliers", []),
    )
    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="Item",
        unique_field="item_code",
        docs=mock_data.get("items", []),
    )
    seed_doctype(
        session=session,
        base_url=base_url,
        doctype="Lead",
        unique_field="email_id",
        docs=mock_data.get("leads", []),
    )
    seed_item_prices(
        session=session,
        base_url=base_url,
        docs=mock_data.get("item_prices", []),
    )

    company = company or get_default_company(session=session, base_url=base_url)
    if not company:
        print("[seed] warning: no Company found; skipping accounting/buying/selling transaction seed")
        return

    selling = seed_data.get("selling", {})
    buying = seed_data.get("buying", {})
    stock = seed_data.get("stock", {})
    accounting = seed_data.get("accounting", {})
    assets = seed_data.get("assets", {})
    crm = seed_data.get("crm", {})
    projects = seed_data.get("projects", {})

    seed_assets(
        session=session,
        base_url=base_url,
        company=company,
        docs=assets,
    )
    seed_crm(
        session=session,
        base_url=base_url,
        company=company,
        docs=crm,
    )
    seed_projects(
        session=session,
        base_url=base_url,
        company=company,
        docs=projects,
    )

    seed_stock_entries(
        session=session,
        base_url=base_url,
        company=company,
        docs=stock.get("stock_entries", []),
    )
    seed_purchase_receipts(
        session=session,
        base_url=base_url,
        company=company,
        docs=stock.get("purchase_receipts", []),
    )
    seed_delivery_notes(
        session=session,
        base_url=base_url,
        company=company,
        docs=stock.get("delivery_notes", []),
    )
    seed_sales_invoices(
        session=session,
        base_url=base_url,
        company=company,
        docs=selling.get("sales_invoices", []),
    )
    seed_sales_orders(
        session=session,
        base_url=base_url,
        company=company,
        docs=selling.get("sales_orders", []),
    )
    seed_purchase_orders(
        session=session,
        base_url=base_url,
        company=company,
        docs=buying.get("purchase_orders", []),
    )
    seed_purchase_order_bills(
        session=session,
        base_url=base_url,
        company=company,
    )
    seed_purchase_invoices(
        session=session,
        base_url=base_url,
        company=company,
        docs=buying.get("purchase_invoices", []),
    )
    seed_journal_entries(
        session=session,
        base_url=base_url,
        company=company,
        docs=accounting.get("journal_entries", []),
    )
    verify_seed_documents(session=session, base_url=base_url)


if __name__ == "__main__":
    main()
