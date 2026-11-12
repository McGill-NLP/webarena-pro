#!/usr/bin/env python3
"""
Generate Firefly III evaluation seed SQL (initdb/002-seed.sql).

Produces a realistic 18-month personal-finance dataset (Jan 2025 - Jun 2026)
wired to support the WebArena-Pro Firefly task suite:

  T1  Tim Hortons / Starbucks transactions March 1-7 2026
  T2  February 2026 budget check (6 categories)
  T3  January 2026 Restaurants budget (pre-seeded limit, remaining to transfer)
  T4  Agent creates Videotron rule; Home Internet bill pre-exists
  T5  Agent creates Netflix subscription
  T6  Spotify Premium present Oct/Nov 2025 + Jan/Feb/Mar 2026, MISSING Dec 2025
  T7  Summer 2025 Vacation-tagged trip (distinct amounts for top-5)
  T8  Agent creates MapleTrust account
  T9  Agent creates piggy bank
  T10 Essential/Discretionary tally Jan-Feb 2026 (agent creates tags)

Run:
    python3 generate_seed.py > initdb/002-seed.sql
"""

import os
import random
from datetime import date, datetime, timedelta
from collections import defaultdict

random.seed(42)

TZ = 'America/Toronto'
CAD, USD = 14, 12
BASE_DATA_END = date(2026, 6, 24)

def parse_data_end():
    raw = os.environ.get('FIREFLY_SEED_TODAY') or os.environ.get('FIREFLY_SEED_END_DATE')
    if not raw:
        return BASE_DATA_END
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError as exc:
        raise SystemExit('FIREFLY_SEED_TODAY must use YYYY-MM-DD format') from exc

DATA_END = parse_data_end()

# ---------------------------------------------------------------------------
# ID counters
# ---------------------------------------------------------------------------
_id = defaultdict(int)
def nid(kind):
    _id[kind] += 1
    return _id[kind]

# ---------------------------------------------------------------------------
# Account definitions. IDs are assigned in declaration order.
# ---------------------------------------------------------------------------
# account_type_id: 1=asset, 7=expense, 14=revenue
# account_role (meta): defaultAsset, savingAsset, cashWalletAsset
# currency_id: 14=CAD, 12=USD
ASSET_DEFS = [
    # (name, currency, role)
    ('TD Chequing',         CAD, 'defaultAsset'),
    ('TD Savings',          CAD, 'savingAsset'),
    ('USD Travel Account',  USD, 'defaultAsset'),
    ('Cash Wallet',         CAD, 'cashWalletAsset'),
]
EXPENSE_DEFS = [
    'Tim Hortons', 'Starbucks', 'Loblaws', 'Amazon.ca', 'Shell Gas Station',
    'Netflix', 'Uber Eats', 'Canadian Tire', 'Shoppers Drug Mart',
    "McDonald's", 'Costco', 'Rogers Wireless', 'Hydro Ottawa',
    'Videotron', 'Spotify', 'Landlord', 'Metro', 'Farm Boy',
    'Esso', 'Petro-Canada', 'Cineplex', 'LCBO', 'Dollarama',
    'Best Buy', 'Indigo', 'Apple.com', 'Presto', 'No Frills',
    'Sobeys', 'Walmart', 'Rexall', 'Bell Canada', 'Enbridge Gas',
    'Home Depot', 'IKEA', 'Uber', 'Lyft', 'Local Bakery', 'Freshii',
    # Restaurants (distinct from Dining Out)
    'Pho Kim', 'The Keg Steakhouse', 'Pai Northern Thai', 'Copper Branch',
    # Vacation vendors
    'Lufthansa', 'Air Canada', 'Marriott Frankfurt', 'Vienna Wine Tours',
    'Hertz', 'Airbnb Montreal', 'Schnitzelhaus Vienna', 'Montreal Bistro',
]
REVENUE_DEFS = [
    'Employer - Payroll',
    'CRA Tax Refund',
    'Freelance USD Client',
]

ASSETS = {}   # name -> id
EXPENSES = {} # name -> id
REVENUES = {} # name -> id

def assign_account_ids():
    for name, _, _ in ASSET_DEFS:
        ASSETS[name] = nid('account')
    for name in EXPENSE_DEFS:
        EXPENSES[name] = nid('account')
    for name in REVENUE_DEFS:
        REVENUES[name] = nid('account')

assign_account_ids()

# Convenience handles
CHEQUING = ASSETS['TD Chequing']
SAVINGS  = ASSETS['TD Savings']
USDACC   = ASSETS['USD Travel Account']
CASH     = ASSETS['Cash Wallet']
PAYROLL  = REVENUES['Employer - Payroll']
CRA      = REVENUES['CRA Tax Refund']
USCLIENT = REVENUES['Freelance USD Client']

# ---------------------------------------------------------------------------
# Categories, tags, budgets, bills (pre-seeded; agent creates the rest)
# ---------------------------------------------------------------------------
CATEGORY_DEFS = [
    'Groceries', 'Gas & Transportation', 'Entertainment', 'Utilities & Bills',
    'Dining Out', 'Shopping', 'Health & Personal Care',
    'Restaurants', 'Rent',
]
TAG_DEFS = [
    'essential', 'recurring', 'impulse-buy', 'Vacation',
]
BUDGET_DEFS = [
    'Groceries', 'Gas & Transportation', 'Entertainment', 'Utilities & Bills',
    'Dining Out', 'Shopping', 'Restaurants',
]
# Default monthly cap per budget (CAD). Restaurants kept at 150 to preserve T3.
BUDGET_MONTHLY_LIMIT = {
    'Groceries':            600.00,
    'Gas & Transportation': 300.00,
    'Entertainment':         80.00,
    'Utilities & Bills':    300.00,
    'Dining Out':           150.00,
    'Shopping':             250.00,
    'Restaurants':          150.00,
}

def _last_day(y, m):
    if m == 12:
        return date(y, 12, 31)
    return date(y, m + 1, 1) - timedelta(days=1)

# (budget_name, start, end, amount) - one monthly limit per budget per seeded month
BUDGET_LIMIT_DEFS = [
    (b, f'{y}-{m:02d}-01', _last_day(y, m).strftime('%Y-%m-%d'),
     BUDGET_MONTHLY_LIMIT[b])
    for y in range(2025, DATA_END.year + 1)
    for m in range(1, 13)
    if date(y, m, 1) <= date(DATA_END.year, DATA_END.month, 1)
    for b in BUDGET_DEFS
]
# (name, match, amount_min, amount_max, start_date, repeat_freq, skipped_periods)
BILL_DEFS = [
    ('Home Internet',    'Videotron',                    84.99,   89.99, '2025-01-05', 'monthly', 0),
    ('Spotify Premium',  'Spotify',                      11.99,   11.99, '2025-01-10', 'monthly', 0),
    # Keep the two benchmark-critical subscriptions above at IDs 1 and 2.
    ('Monthly Rent',     'Monthly rent',               1400.00, 1400.00, '2025-01-01', 'monthly', 0),
    ('Mobile Phone',     'phone bill',                   72.00,   78.00, '2025-01-18', 'monthly', 0),
    ('Electricity',      'Electricity bill',             62.00,  105.00, '2025-01-22', 'monthly', 0),
    ('Natural Gas',      'Natural gas bill',             38.00,   92.00, '2025-02-24', 'monthly', 1),
    ('iCloud Storage',   'iCloud storage subscription',   3.99,    3.99, '2025-03-17', 'monthly', 2),
]

CATS   = {n: nid('category') for n in CATEGORY_DEFS}
TAGS   = {n: nid('tag')      for n in TAG_DEFS}
BUDS   = {n: nid('budget')   for n in BUDGET_DEFS}
BILLS  = {n: nid('bill')     for n, *_ in BILL_DEFS}
PIGGY_BANK_DEFS = [
    # (name, account_id, currency_id, target_amount, current_amount, start_date, target_date)
    ('New Car', SAVINGS, CAD, 28000.00, 2500.00, '2026-06-01', '2028-06-01'),
]
PIGS = {n: nid('piggy_bank') for n, *_ in PIGGY_BANK_DEFS}

# ---------------------------------------------------------------------------
# Journal / transaction accumulators
# ---------------------------------------------------------------------------
groups   = []   # (id, date, title_or_None)
journals = []   # (id, type, group_id, bill_id_or_None, currency, description, date_time)
tx_rows  = []   # (id, account_id, journal_id, currency, amount, description_or_None, foreign_amt, foreign_cur, identifier, balance_before, balance_after)
cat_tj   = []   # (category_id, journal_id)
tag_tj   = []   # (tag_id, journal_id)
bud_tj   = []   # (budget_id, journal_id)
bud_t    = []   # (budget_id, transaction_id)

# Transaction types: 1=Deposit, 6=Transfer, 7=Withdrawal
TT_DEPOSIT, TT_TRANSFER, TT_WITHDRAWAL = 1, 6, 7

_BUDGET_UNSET = object()

def add_withdrawal(d: datetime, source_asset_id: int, expense_name: str,
                   amount_cad: float, description: str,
                   category: str = None, tags: list = None,
                   bill: str = None, title: str = None,
                   foreign_amount: float = None, foreign_currency: int = None,
                   currency: int = CAD, budget=_BUDGET_UNSET):
    """Add a one-line withdrawal tx. Amount in primary currency.

    Budget linkage: if `budget` is omitted, auto-derive from `category` when a
    same-named budget exists (Groceries, Gas & Transportation, ...). Pass
    `budget=None` to suppress; pass an explicit name to override.
    """
    tags = tags or []
    if budget is _BUDGET_UNSET:
        budget = category if category in BUDS else None
    gid = nid('group')
    groups.append((gid, d, title))
    jid = nid('journal')
    bill_id = BILLS.get(bill) if bill else None
    journals.append((jid, TT_WITHDRAWAL, gid, bill_id, currency,
                     description, d, len(tags)))
    amt = round(amount_cad, 2)
    # source (negative)
    src_tid = nid('transaction')
    tx_rows.append((src_tid, source_asset_id, jid, currency,
                    -amt, None, -foreign_amount if foreign_amount else None,
                    foreign_currency, 0, None, None))
    # destination expense (positive)
    dest = EXPENSES[expense_name]
    dst_tid = nid('transaction')
    tx_rows.append((dst_tid, dest, jid, currency,
                    amt, None, foreign_amount, foreign_currency, 0, None, None))
    if category:
        cat_tj.append((CATS[category], jid))
    if budget:
        bud_tj.append((BUDS[budget], jid))
        bud_t.append((BUDS[budget], src_tid))
        bud_t.append((BUDS[budget], dst_tid))
    for t in tags:
        tag_tj.append((TAGS[t], jid))
    return jid

def add_deposit(d: datetime, dest_asset_id: int, revenue_name: str,
                amount: float, description: str,
                category: str = None, tags: list = None,
                title: str = None,
                foreign_amount: float = None, foreign_currency: int = None,
                currency: int = CAD):
    tags = tags or []
    gid = nid('group')
    groups.append((gid, d, title))
    jid = nid('journal')
    journals.append((jid, TT_DEPOSIT, gid, None, currency,
                     description, d, len(tags)))
    amt = round(amount, 2)
    src = REVENUES[revenue_name]
    tx_rows.append((nid('transaction'), src, jid, currency,
                    -amt, None, -foreign_amount if foreign_amount else None,
                    foreign_currency, 0, None, None))
    tx_rows.append((nid('transaction'), dest_asset_id, jid, currency,
                    amt, None, foreign_amount, foreign_currency, 0, None, None))
    if category:
        cat_tj.append((CATS[category], jid))
    for t in tags:
        tag_tj.append((TAGS[t], jid))
    return jid

def add_transfer(d: datetime, src_id: int, dest_id: int, amount: float,
                 description: str, category: str = None, tags: list = None):
    tags = tags or []
    gid = nid('group')
    groups.append((gid, d, None))
    jid = nid('journal')
    journals.append((jid, TT_TRANSFER, gid, None, CAD,
                     description, d, len(tags)))
    amt = round(amount, 2)
    tx_rows.append((nid('transaction'), src_id,  jid, CAD, -amt, None, None, None, 0, None, None))
    tx_rows.append((nid('transaction'), dest_id, jid, CAD,  amt, None, None, None, 0, None, None))
    if category:
        cat_tj.append((CATS[category], jid))
    for t in tags:
        tag_tj.append((TAGS[t], jid))
    return jid

# ---------------------------------------------------------------------------
# Monthly regulars
# ---------------------------------------------------------------------------
def at(d: date, h=9, m=0):
    return datetime(d.year, d.month, d.day, h, m)

def last_day(y, m):
    if m == 12:
        return date(y, 12, 31)
    return date(y, m + 1, 1) - timedelta(days=1)

def gen_month(y, m):
    """Generate all regular recurring + random-sprinkled transactions for a month."""
    rng = random.Random(y * 100 + m)
    eom = last_day(y, m)

    # --- Income: 15th + last day payroll ---
    add_deposit(at(date(y, m, 15), 9, 0), CHEQUING, 'Employer - Payroll',
                3500.00, f'Salary - first half of {date(y,m,1):%B}',
                tags=['recurring'])
    add_deposit(at(eom, 9, 0), CHEQUING, 'Employer - Payroll',
                3500.00, f'Salary - second half of {date(y,m,1):%B}',
                tags=['recurring'])

    # --- Other asset accounts: savings, USD, and cash activity ---
    add_transfer(at(date(y, m, min(16, eom.day)), 12, 0), CHEQUING, SAVINGS,
                 500.00, 'Automatic transfer to emergency savings',
                 tags=['recurring'])
    add_transfer(at(date(y, m, min(12, eom.day)), 12, 30), CHEQUING, CASH,
                 120.00, 'ATM cash withdrawal')

    if m in (1, 4, 7, 10):
        add_deposit(at(date(y, m, min(20, eom.day)), 11, 0), USDACC,
                    'Freelance USD Client', 950.00,
                    'Quarterly freelance USD payment', currency=USD)

    if m == 4:
        add_deposit(at(date(y, m, 28), 11, 0), CHEQUING, 'CRA Tax Refund',
                    rng.choice([725.00, 840.00, 910.00]),
                    'CRA tax refund deposit')

    # --- Rent: 1st of month ---
    add_withdrawal(at(date(y, m, 1), 8, 0), CHEQUING, 'Landlord',
                   1400.00, 'Monthly rent', category='Rent',
                   tags=['recurring'], bill='Monthly Rent')

    # --- Utilities & subscriptions ---
    # Videotron (Home Internet bill) ~5th
    videotron_amt = rng.choice([84.99, 89.99, 87.99])
    add_withdrawal(at(date(y, m, 5), 10, 0), CHEQUING, 'Videotron',
                   videotron_amt, 'Videotron home internet',
                   category='Utilities & Bills', tags=['recurring'],
                   bill='Home Internet')

    # Mobile phone ~18th
    mobile_vendor = rng.choice(['Rogers Wireless', 'Bell Canada'])
    add_withdrawal(at(date(y, m, 18), 10, 0), CHEQUING, mobile_vendor,
                   rng.choice([72.00, 75.00, 78.00]), f'{mobile_vendor} phone bill',
                   category='Utilities & Bills', tags=['recurring'],
                   bill='Mobile Phone')

    # Hydro ~22nd  (every month)
    add_withdrawal(at(date(y, m, 22), 10, 0), CHEQUING, 'Hydro Ottawa',
                   round(rng.uniform(62, 105), 2), 'Electricity bill',
                   category='Utilities & Bills', tags=['recurring'],
                   bill='Electricity')

    # Natural gas every other month.
    if m % 2 == 0:
        add_withdrawal(at(date(y, m, 24), 10, 0), CHEQUING, 'Enbridge Gas',
                       round(rng.uniform(38, 92), 2), 'Natural gas bill',
                       category='Utilities & Bills', tags=['recurring'],
                       bill='Natural Gas')

    # Spotify ~10th (EXCEPT December 2025 — task T6 gap)
    if not (y == 2025 and m == 12):
        add_withdrawal(at(date(y, m, 10), 7, 0), CHEQUING, 'Spotify',
                       11.99, 'Spotify Premium subscription',
                       category='Entertainment', tags=['recurring'],
                       bill='Spotify Premium')

    # Netflix ~22nd
    add_withdrawal(at(date(y, m, 22), 7, 0), CHEQUING, 'Netflix',
                   16.99, 'Netflix monthly subscription',
                   category='Entertainment', tags=['recurring'])

    if m in (3, 6, 9, 12):
        add_withdrawal(at(date(y, m, 17), 7, 15), CHEQUING, 'Apple.com',
                       3.99, 'iCloud storage subscription',
                       category='Utilities & Bills', tags=['recurring'],
                       bill='iCloud Storage')

    # --- Groceries: 4 per month ---
    grocery_stores = ['Loblaws', 'Metro', 'Costco', 'Farm Boy', 'No Frills',
                      'Sobeys', 'Walmart']
    for i, day in enumerate(sorted(rng.sample(range(2, 29), 4))):
        store = rng.choice(grocery_stores)
        amt = round(rng.uniform(38, 155), 2)
        desc = rng.choice([
            'Weekly groceries', 'Produce and pantry restock',
            'Household groceries', 'Dinner ingredients',
        ])
        if store == 'Costco':
            desc = 'Costco bulk shopping'
        add_withdrawal(at(date(y, m, day), 17, 0), CHEQUING, store,
                       amt, desc, category='Groceries', tags=['essential'])

    # --- Gas: 1 per month ---
    gas_stations = ['Shell Gas Station', 'Esso', 'Petro-Canada']
    station = rng.choice(gas_stations)
    add_withdrawal(at(date(y, m, rng.randint(3, 27)), 17, 30), CHEQUING, station,
                   round(rng.uniform(45, 82), 2), 'Gas fill-up',
                   category='Gas & Transportation')

    # --- Coffee / bakery: 3 per month (non-first-week-of-March 2026) ---
    coffee_count = 3
    for day in sorted(rng.sample(range(8, 29), coffee_count)):
        if y == 2026 and m == 3 and day <= 7:
            continue
        vendor = rng.choice(['Tim Hortons', 'Starbucks', 'Local Bakery'])
        amt = round(rng.uniform(3.50, 11.50), 2)
        desc_map = {
            'Tim Hortons': rng.choice(['Double double and muffin', 'Iced capp and donut',
                                        'Dark roast large', 'Tim Hortons breakfast sandwich']),
            'Starbucks':   rng.choice(['Grande latte', 'Venti caramel macchiato',
                                        'Flat white and scone', 'Pike Place large']),
            'Local Bakery': rng.choice(['Coffee and croissant', 'Breakfast pastry',
                                        'Sandwich and coffee']),
        }
        add_withdrawal(at(date(y, m, day), 8, 15), CHEQUING, vendor,
                       amt, desc_map[vendor], category='Dining Out')

    # --- Dining Out: 3 per month (fast food / delivery / casual meals) ---
    for day in sorted(rng.sample(range(5, 28), 3)):
        vendor = rng.choice(['Uber Eats', "McDonald's", 'Freshii'])
        amt = round(rng.uniform(11, 38), 2)
        desc = {
            'Uber Eats': 'Dinner delivery',
            "McDonald's": 'Lunch combo',
            'Freshii': 'Quick lunch bowl',
        }[vendor]
        add_withdrawal(at(date(y, m, day), 19, 0), CHEQUING, vendor,
                       amt, desc, category='Dining Out')

    # --- Restaurants: 1 per month (sit-down dining) ---
    rest_options = [
        ('Pho Kim',            'Pho and spring rolls',        (22, 42)),
        ('The Keg Steakhouse', 'Dinner at The Keg',           (65, 125)),
        ('Pai Northern Thai',  'Pad thai dinner',             (35, 68)),
        ('Copper Branch',      'Plant-based bowl',            (18, 29)),
    ]
    vendor, desc, (lo, hi) = rng.choice(rest_options)
    amt = round(rng.uniform(lo, hi), 2)
    add_withdrawal(at(date(y, m, rng.randint(4, 28)), 20, 0), CHEQUING, vendor,
                   amt, desc, category='Restaurants')

    # --- Shopping / errands: 2 per month ---
    shop_options = [
        ('Amazon.ca',      'Amazon order',        (25, 180), None),
        ('Canadian Tire',  'Canadian Tire run',   (15, 145), None),
        ('Best Buy',       'Electronics purchase',(60, 340), ['impulse-buy']),
        ('Indigo',         'Books and magazines', (18, 55),  None),
        ('Dollarama',      'Household items',     (6, 30),   None),
        ('Home Depot',     'Home repair supplies',(22, 160), None),
        ('IKEA',           'Home organization',   (18, 125), None),
        ('Walmart',        'Household essentials',(20, 110), None),
    ]
    for day in sorted(rng.sample(range(3, 29), 2)):
        vendor, desc, (lo, hi), extra_tags = rng.choice(shop_options)
        amt = round(rng.uniform(lo, hi), 2)
        add_withdrawal(at(date(y, m, day), 14, 0), CHEQUING, vendor,
                       amt, desc, category='Shopping',
                       tags=extra_tags or [])

    # --- Health / pharmacy: 1 per month ---
    add_withdrawal(at(date(y, m, rng.randint(8, 24)), 15, 0),
                   CHEQUING, rng.choice(['Shoppers Drug Mart', 'Rexall']),
                   round(rng.uniform(12, 58), 2), 'Vitamins and toiletries',
                   category='Health & Personal Care')

    # --- Entertainment (misc, non-subscription): 0-1 per month ---
    if rng.random() < 0.5:
        vendor, desc, (lo, hi) = rng.choice([
            ('Cineplex', 'Movie tickets',          (14, 32)),
            ('LCBO',     'Wine for the weekend',   (22, 65)),
        ])
        add_withdrawal(at(date(y, m, rng.randint(5, 27)), 20, 0),
                       CHEQUING, vendor, round(rng.uniform(lo, hi), 2),
                       desc, category='Entertainment')

    # --- Transit / rideshare occasional ---
    if rng.random() < 0.5:
        vendor = ['Presto', 'Uber', 'Lyft'][(m - 1) % 3]
        desc = 'Presto transit loading' if vendor == 'Presto' else 'Rideshare trip'
        add_withdrawal(at(date(y, m, rng.randint(2, 20)), 7, 30),
                       CHEQUING, vendor,
                       round(rng.uniform(14, 85), 2), desc,
                       category='Gas & Transportation')

    # --- Small cash-wallet purchase so the cash account has history too ---
    cash_vendor, cash_desc, cash_category, cash_amount = rng.choice([
        ('Tim Hortons', 'Cash coffee purchase', 'Dining Out', round(rng.uniform(3.25, 7.75), 2)),
        ('Dollarama', 'Cash household purchase', 'Shopping', round(rng.uniform(8.00, 22.00), 2)),
        ('Local Bakery', 'Cash bakery stop', 'Dining Out', round(rng.uniform(4.50, 13.00), 2)),
    ])
    add_withdrawal(at(date(y, m, min(24, eom.day)), 13, 15), CASH,
                   cash_vendor, cash_amount, cash_desc, category=cash_category)

# ---------------------------------------------------------------------------
# Main timeline
# ---------------------------------------------------------------------------
MONTHS = [(y, m) for y in range(2025, DATA_END.year + 1) for m in range(1, 13)
          if date(y, m, 1) <= date(DATA_END.year, DATA_END.month, 1)]

for (y, m) in MONTHS:
    gen_month(y, m)

# ---------------------------------------------------------------------------
# TASK-SPECIFIC OVERRIDES
# ---------------------------------------------------------------------------

# T7: Summer 2025 Europe/Canada vacation (distinct amounts for top-5)
VACATION = [
    ('2025-06-20', 'Lufthansa',           1295.00, 'Lufthansa flight YOW to Frankfurt', 'Gas & Transportation'),
    ('2025-06-21', 'Marriott Frankfurt',   740.80, 'Marriott Frankfurt 4 nights',       None),
    ('2025-06-22', 'Vienna Wine Tours',    142.75, 'Vienna wine tasting tour',          None),
    ('2025-06-23', 'Schnitzelhaus Vienna',  87.60, 'Dinner in Vienna',                  'Restaurants'),
    ('2025-06-25', 'Lufthansa',           1186.50, 'Lufthansa flight Frankfurt to YOW', 'Gas & Transportation'),
    ('2025-08-10', 'Air Canada',           368.40, 'Air Canada YOW to YUL',             'Gas & Transportation'),
    ('2025-08-11', 'Airbnb Montreal',      420.00, 'Airbnb Montreal 3 nights',          None),
    ('2025-08-12', 'Hertz',                215.80, 'Hertz car rental',                  'Gas & Transportation'),
    ('2025-08-13', 'Montreal Bistro',       62.40, 'Dinner Old Montreal',               'Restaurants'),
    ('2025-08-15', 'Air Canada',           382.10, 'Air Canada YUL to YOW',             'Gas & Transportation'),
]
for ds, vendor, amt, desc, cat in VACATION:
    d = datetime.strptime(ds, '%Y-%m-%d').replace(hour=10)
    add_withdrawal(d, CHEQUING, vendor, amt, desc, category=cat,
                   tags=['Vacation'])

# T1: Exactly 7 Tim Hortons/Starbucks transactions Mar 1-7, 2026, totaling C$46.50
MARCH_COFFEE = [
    ('2026-03-01 09:15', 'Tim Hortons', 5.47, 'Double double and muffin'),
    ('2026-03-02 08:30', 'Starbucks',   6.45, 'Grande latte'),
    ('2026-03-03 07:45', 'Tim Hortons', 8.23, 'Large coffee and BELT bagel'),
    ('2026-03-04 08:00', 'Starbucks',   7.20, 'Venti caramel macchiato'),
    ('2026-03-05 09:00', 'Tim Hortons', 2.35, 'Large dark roast'),
    ('2026-03-06 08:15', 'Starbucks',   8.95, 'Pike Place and cake pop'),
    ('2026-03-07 07:30', 'Tim Hortons', 7.85, 'Iced capp and donut'),
]
for ds, vendor, amt, desc in MARCH_COFFEE:
    d = datetime.strptime(ds, '%Y-%m-%d %H:%M')
    add_withdrawal(d, CHEQUING, vendor, amt, desc)  # no category, no tag

# T3: January 2026 Restaurants budget check - remove auto-generated Jan restaurant
# tx, seed a fixed C$97.45 total so "remaining under C$150 budget" = C$52.55.
# Find and drop the January 2026 Restaurants transactions added by gen_month().
JAN_2026_START, JAN_2026_END = datetime(2026, 1, 1), datetime(2026, 2, 1)
jids_to_drop = set()
for j in journals:
    jid, jtype, gid, bill, cur, desc, dt, tagc = j
    if (JAN_2026_START <= dt < JAN_2026_END and
            any(ct[1] == jid and ct[0] == CATS['Restaurants'] for ct in cat_tj)):
        jids_to_drop.add(jid)
tids_to_drop = {t[0] for t in tx_rows if t[2] in jids_to_drop}
journals = [j for j in journals if j[0] not in jids_to_drop]
tx_rows  = [t for t in tx_rows if t[2] not in jids_to_drop]
cat_tj   = [c for c in cat_tj if c[1] not in jids_to_drop]
tag_tj   = [t for t in tag_tj if t[1] not in jids_to_drop]
bud_tj   = [b for b in bud_tj if b[1] not in jids_to_drop]
bud_t    = [b for b in bud_t  if b[1] not in tids_to_drop]
# (groups left in place; their journal_ids just don't exist - harmless orphans.
#  Cleaner approach below: also prune those groups.)
gids_from_dropped_j = {j[2] for j in journals}  # still-alive group refs
# Drop groups with no journal
live_group_ids = {j[2] for j in journals}
groups = [g for g in groups if g[0] in live_group_ids]

# Now seed fixed January 2026 Restaurants transactions - total C$97.45
JAN_RESTAURANTS = [
    ('2026-01-08', 'Pho Kim',            32.50, 'Pho dinner with friends'),
    ('2026-01-17', 'The Keg Steakhouse', 45.95, 'Birthday dinner at The Keg'),
    ('2026-01-24', 'Pai Northern Thai',  19.00, 'Pad thai lunch'),
]
for ds, vendor, amt, desc in JAN_RESTAURANTS:
    d = datetime.strptime(ds, '%Y-%m-%d').replace(hour=19)
    add_withdrawal(d, CHEQUING, vendor, amt, desc, category='Restaurants')

# Cross-task total locks. These preserve the exact numeric answers used by the
# Firefly task suite after the broader "daily life" transaction generation above.
def drop_journals(jids_to_drop):
    global journals, tx_rows, cat_tj, tag_tj, bud_tj, bud_t, groups
    tids_to_drop = {t[0] for t in tx_rows if t[2] in jids_to_drop}
    journals = [j for j in journals if j[0] not in jids_to_drop]
    tx_rows  = [t for t in tx_rows if t[2] not in jids_to_drop]
    cat_tj   = [c for c in cat_tj if c[1] not in jids_to_drop]
    tag_tj   = [t for t in tag_tj if t[1] not in jids_to_drop]
    bud_tj   = [b for b in bud_tj if b[1] not in jids_to_drop]
    bud_t    = [b for b in bud_t  if b[1] not in tids_to_drop]
    live_group_ids = {j[2] for j in journals}
    groups = [g for g in groups if g[0] in live_group_ids]

def drop_month_category(y, m, category):
    start = datetime(y, m, 1)
    end = datetime(y + 1, 1, 1) if m == 12 else datetime(y, m + 1, 1)
    cat_id = CATS[category]
    jids = {
        jid for cid, jid in cat_tj
        if cid == cat_id and start <= journal_by_id_current()[jid][6] < end
    }
    drop_journals(jids)

def journal_by_id_current():
    return {j[0]: j for j in journals}

def add_fixed_withdrawals(category, entries):
    for ds, vendor, amt, desc, tags, bill in entries:
        d = datetime.strptime(ds, '%Y-%m-%d').replace(hour=10)
        add_withdrawal(d, CHEQUING, vendor, amt, desc, category=category,
                       tags=tags or [], bill=bill)

# Groceries: preserves Jan-vs-Mar comparison, Jan-Mar count/total, February
# budget overage, and the March largest-expense task.
for y, m in [(2026, 1), (2026, 2), (2026, 3)]:
    drop_month_category(y, m, 'Groceries')
add_fixed_withdrawals('Groceries', [
    ('2026-01-02', 'Farm Boy', 104.66, 'Household groceries', ['essential'], None),
    ('2026-01-08', 'Costco', 100.25, 'Costco bulk shopping', ['essential'], None),
    ('2026-01-16', 'Metro', 111.30, 'Household groceries', ['essential'], None),
    ('2026-01-26', 'Walmart', 117.35, 'Weekly groceries', ['essential'], None),
    ('2026-02-03', 'Loblaws', 110.25, 'Weekly groceries', ['essential'], None),
    ('2026-02-09', 'Farm Boy', 132.45, 'Produce and pantry restock', ['essential'], None),
    ('2026-02-17', 'Metro', 99.55, 'Dinner ingredients', ['essential'], None),
    ('2026-02-25', 'Costco', 119.87, 'Costco bulk shopping', ['essential'], None),
    ('2026-03-06', 'Metro', 92.13, 'Household groceries', ['essential'], None),
    ('2026-03-13', 'Loblaws', 71.20, 'Dinner ingredients', ['essential'], None),
    ('2026-03-20', 'Farm Boy', 129.74, 'Produce and pantry restock', ['essential'], None),
    ('2026-03-27', 'Costco', 58.20, 'Costco bulk shopping', ['essential'], None),
])

# Utilities: keeps Jan-Feb Essential totals and the Jan-Apr Home Internet total.
for y, m in [(2026, 1), (2026, 2), (2026, 4)]:
    drop_month_category(y, m, 'Utilities & Bills')
add_fixed_withdrawals('Utilities & Bills', [
    ('2026-01-05', 'Videotron', 84.99, 'Videotron home internet', ['recurring'], 'Home Internet'),
    ('2026-01-18', 'Rogers Wireless', 72.00, 'Rogers Wireless phone bill', ['recurring'], 'Mobile Phone'),
    ('2026-01-22', 'Hydro Ottawa', 89.70, 'Electricity bill', ['recurring'], 'Electricity'),
    ('2026-02-05', 'Videotron', 89.99, 'Videotron home internet', ['recurring'], 'Home Internet'),
    ('2026-02-18', 'Bell Canada', 72.00, 'Bell Canada phone bill', ['recurring'], 'Mobile Phone'),
    ('2026-02-22', 'Hydro Ottawa', 65.05, 'Electricity bill', ['recurring'], 'Electricity'),
    ('2026-04-05', 'Videotron', 84.99, 'Videotron home internet', ['recurring'], 'Home Internet'),
    ('2026-04-18', 'Rogers Wireless', 75.00, 'Rogers Wireless phone bill', ['recurring'], 'Mobile Phone'),
    ('2026-04-22', 'Hydro Ottawa', 80.00, 'Electricity bill', ['recurring'], 'Electricity'),
])

# February budget overage locks.
for category in ['Gas & Transportation', 'Dining Out', 'Shopping']:
    drop_month_category(2026, 2, category)
add_fixed_withdrawals('Gas & Transportation', [
    ('2026-02-06', 'Shell Gas Station', 76.20, 'Gas fill-up', [], None),
    ('2026-02-14', 'Presto', 58.10, 'Presto transit loading', [], None),
    ('2026-02-23', 'Uber', 84.43, 'Rideshare trip', [], None),
])
add_fixed_withdrawals('Dining Out', [
    ('2026-02-04', 'Uber Eats', 32.40, 'Dinner delivery', [], None),
    ('2026-02-11', "McDonald's", 18.75, 'Lunch combo', [], None),
    ('2026-02-19', 'Freshii', 27.35, 'Quick lunch bowl', [], None),
    ('2026-02-26', 'Tim Hortons', 35.62, 'Coffee and lunch stop', [], None),
])
add_fixed_withdrawals('Shopping', [
    ('2026-02-07', 'Amazon.ca', 89.90, 'Amazon order', [], None),
    ('2026-02-16', 'Canadian Tire', 64.22, 'Canadian Tire run', [], None),
    ('2026-02-24', 'Best Buy', 110.95, 'Electronics purchase', ['impulse-buy'], None),
])

# January discretionary totals for the Essential/Discretionary tag task.
for category in ['Dining Out', 'Entertainment', 'Shopping']:
    drop_month_category(2026, 1, category)
add_fixed_withdrawals('Dining Out', [
    ('2026-01-06', 'Uber Eats', 31.20, 'Dinner delivery', [], None),
    ('2026-01-14', "McDonald's", 22.45, 'Lunch combo', [], None),
    ('2026-01-27', 'Freshii', 16.35, 'Quick lunch bowl', [], None),
])
add_fixed_withdrawals('Entertainment', [
    ('2026-01-10', 'Spotify', 11.99, 'Spotify Premium subscription', ['recurring'], 'Spotify Premium'),
    ('2026-01-22', 'Netflix', 16.99, 'Netflix monthly subscription', ['recurring'], None),
])
add_fixed_withdrawals('Shopping', [
    ('2026-01-09', 'Dollarama', 32.10, 'Household items', [], None),
    ('2026-01-21', 'Indigo', 24.74, 'Books and magazines', [], None),
])

# April Restaurants is used by a cross-app Mattermost task.
drop_month_category(2026, 4, 'Restaurants')
add_fixed_withdrawals('Restaurants', [
    ('2026-04-10', 'Pai Northern Thai', 74.25, 'Pad thai dinner', [], None),
    ('2026-04-18', 'The Keg Steakhouse', 126.00, 'Dinner at The Keg', [], None),
    ('2026-04-24', 'Pho Kim', 62.40, 'Pho and spring rolls', [], None),
])

# Make the freshest visible transaction land exactly on the build-time anchor
# date when extending the seed beyond the checked-in June 2026 snapshot.
if DATA_END > BASE_DATA_END and not any(j[6].date() == DATA_END for j in journals):
    rng = random.Random(DATA_END.strftime('%Y%m%d'))
    vendor, desc, category, hour, minute = rng.choice([
        ('Tim Hortons', 'Morning coffee stop', 'Dining Out', 8, 20),
        ('Local Bakery', 'Breakfast pastry and coffee', 'Dining Out', 8, 35),
        ('Dollarama', 'Small household items', 'Shopping', 16, 10),
        ('Presto', 'Transit card top-up', 'Gas & Transportation', 7, 45),
    ])
    add_withdrawal(
        at(DATA_END, hour, minute),
        CHEQUING,
        vendor,
        round(rng.uniform(4.50, 18.75), 2),
        desc,
        category=category,
    )

# Keep the demo current without adding future-dated transactions.
DATA_END_AT = datetime(DATA_END.year, DATA_END.month, DATA_END.day, 23, 59, 59)
jids_after_data_end = {j[0] for j in journals if j[6] > DATA_END_AT}
tids_after_data_end = {t[0] for t in tx_rows if t[2] in jids_after_data_end}
journals = [j for j in journals if j[0] not in jids_after_data_end]
tx_rows  = [t for t in tx_rows if t[2] not in jids_after_data_end]
cat_tj   = [c for c in cat_tj if c[1] not in jids_after_data_end]
tag_tj   = [t for t in tag_tj if t[1] not in jids_after_data_end]
bud_tj   = [b for b in bud_tj if b[1] not in jids_after_data_end]
bud_t    = [b for b in bud_t  if b[1] not in tids_after_data_end]
live_group_ids = {j[2] for j in journals}
groups = [g for g in groups if g[0] in live_group_ids]

# Running balances feed Firefly's account history charts. This includes all
# accounts, but the account_balances table below is limited to asset accounts.
journal_by_id = {j[0]: j for j in journals}
running = defaultdict(float)
balanced_tx_rows = []
for row in sorted(tx_rows, key=lambda r: (journal_by_id[r[2]][6], r[0])):
    tid, acct_id, jid, cur, amt, desc, famt, fcur, ident, _, _ = row
    before = round(running[acct_id], 12)
    after = round(before + amt, 12)
    running[acct_id] = after
    balanced_tx_rows.append((tid, acct_id, jid, cur, amt, desc, famt, fcur, ident, before, after))
tx_rows = sorted(balanced_tx_rows, key=lambda r: r[0])

asset_ids = {ASSETS[name] for name, _, _ in ASSET_DEFS}
account_balance_rows = []
for row in sorted(tx_rows, key=lambda r: (journal_by_id[r[2]][6], r[0])):
    tid, acct_id, jid, cur, amt, desc, famt, fcur, ident, before, after = row
    if acct_id in asset_ids:
        account_balance_rows.append((acct_id, cur, journal_by_id[jid][6].date(), jid, after))

# ---------------------------------------------------------------------------
# SQL emission
# ---------------------------------------------------------------------------
out = []
def p(s=''):
    out.append(s)

def dt_sql(d):
    if isinstance(d, datetime):
        return d.strftime('%Y-%m-%d %H:%M:%S')
    return d.strftime('%Y-%m-%d 00:00:00')

def esc(s):
    if s is None:
        return 'NULL'
    return "'" + s.replace("'", "''") + "'"

def nnum(v):
    return 'NULL' if v is None else f'{v}'

# Header
p('-- ============================================================')
p('-- Firefly III Evaluation Seed Data')
p('-- Generated by generate_seed.py - DO NOT EDIT BY HAND.')
p(f'-- Timeline: Jan 2025 - {DATA_END:%b %d, %Y}')
p(f'-- Total transaction journals: {len(journals)}')
p('-- ============================================================')
p('')
p('SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;')
p('')

# Wipe demo data (same list as the previous seed)
p('-- Clean up existing demo data')
for t in ['rule_triggers', 'rule_actions', 'rules', 'rule_groups',
          'account_piggy_bank', 'piggy_bank_events', 'piggy_bank_repetitions',
          'piggy_banks',
          'tag_transaction_journal', 'category_transaction_journal',
          'category_transaction', 'budget_transaction_journal',
          'budget_transaction', 'auto_budgets', 'budget_limits',
          'available_budgets', 'budgets', 'bills',
          'transactions', 'transaction_journals', 'transaction_groups',
          'account_balances', 'account_meta']:
    p(f'DELETE FROM `{t}`;')
p('DELETE FROM `accounts` WHERE `account_type_id` IN (1,7,14);')
p('DELETE FROM `categories`;')
p('DELETE FROM `tags`;')
p('DELETE FROM `transaction_currency_user_group`;')
p('DELETE FROM `transaction_currency_user`;')
p('')

# Currencies: CAD default
p('-- Currencies: CAD default, USD enabled, EUR disabled')
p('UPDATE `transaction_currencies` SET `enabled`=0 WHERE `id`=1;')
p('UPDATE `transaction_currencies` SET `enabled`=1 WHERE `id`=14;')
p('UPDATE `transaction_currencies` SET `enabled`=1 WHERE `id`=12;')
p("INSERT INTO `transaction_currency_user_group` (`id`,`created_at`,`updated_at`,`user_group_id`,`transaction_currency_id`,`group_default`) VALUES "
  "(1,'2025-01-01 00:00:00','2025-01-01 00:00:00',1,14,1);")
p("INSERT INTO `transaction_currency_user` (`id`,`created_at`,`updated_at`,`user_id`,`transaction_currency_id`,`user_default`) VALUES "
  "(1,'2025-01-01 00:00:00','2025-01-01 00:00:00',1,14,1);")
p("UPDATE `preferences` SET `data`='[1,2,3,4]' WHERE `name`='frontpageAccounts' AND `user_id`=1;")
p('')

# Accounts
p('-- Asset accounts')
p('INSERT INTO `accounts` (`id`,`created_at`,`updated_at`,`deleted_at`,`user_id`,`user_group_id`,`account_type_id`,`name`,`virtual_balance`,`iban`,`active`,`encrypted`,`order`,`native_virtual_balance`) VALUES')
rows = []
for i, (name, _, _) in enumerate(ASSET_DEFS, 1):
    rows.append(f"({ASSETS[name]},'2025-01-01 00:00:00','2025-01-01 00:00:00',NULL,1,1,1,{esc(name)},0.000000000000,NULL,1,0,{i},NULL)")
p(',\n'.join(rows) + ';')
p('')
p('-- Expense accounts')
p('INSERT INTO `accounts` (`id`,`created_at`,`updated_at`,`deleted_at`,`user_id`,`user_group_id`,`account_type_id`,`name`,`virtual_balance`,`iban`,`active`,`encrypted`,`order`,`native_virtual_balance`) VALUES')
rows = []
for name in EXPENSE_DEFS:
    rows.append(f"({EXPENSES[name]},'2025-01-01 00:00:00','2025-01-01 00:00:00',NULL,1,1,7,{esc(name)},NULL,NULL,1,0,0,NULL)")
p(',\n'.join(rows) + ';')
p('')
p('-- Revenue accounts')
p('INSERT INTO `accounts` (`id`,`created_at`,`updated_at`,`deleted_at`,`user_id`,`user_group_id`,`account_type_id`,`name`,`virtual_balance`,`iban`,`active`,`encrypted`,`order`,`native_virtual_balance`) VALUES')
rows = []
for name in REVENUE_DEFS:
    rows.append(f"({REVENUES[name]},'2025-01-01 00:00:00','2025-01-01 00:00:00',NULL,1,1,14,{esc(name)},NULL,NULL,1,0,0,NULL)")
p(',\n'.join(rows) + ';')
p('')

# Account metadata
p('-- Account metadata')
p('INSERT INTO `account_meta` (`id`,`created_at`,`updated_at`,`account_id`,`name`,`data`) VALUES')
meta_rows = []
for name, cur, role in ASSET_DEFS:
    meta_rows.append(f"({nid('account_meta')},'2025-01-01 00:00:00','2025-01-01 00:00:00',{ASSETS[name]},'account_role',{esc(chr(34) + role + chr(34))})")
    meta_rows.append(f"({nid('account_meta')},'2025-01-01 00:00:00','2025-01-01 00:00:00',{ASSETS[name]},'currency_id',{esc(chr(34) + str(cur) + chr(34))})")
for name in EXPENSE_DEFS:
    meta_rows.append(f"({nid('account_meta')},'2025-01-01 00:00:00','2025-01-01 00:00:00',{EXPENSES[name]},'BIC','\"\"')")
    meta_rows.append(f"({nid('account_meta')},'2025-01-01 00:00:00','2025-01-01 00:00:00',{EXPENSES[name]},'account_number','\"\"')")
for name in REVENUE_DEFS:
    meta_rows.append(f"({nid('account_meta')},'2025-01-01 00:00:00','2025-01-01 00:00:00',{REVENUES[name]},'BIC','\"\"')")
    meta_rows.append(f"({nid('account_meta')},'2025-01-01 00:00:00','2025-01-01 00:00:00',{REVENUES[name]},'account_number','\"\"')")
p(',\n'.join(meta_rows) + ';')
p('')

# Piggy banks
p('-- Piggy banks')
p('INSERT INTO `piggy_banks` (`id`,`created_at`,`updated_at`,`deleted_at`,`account_id`,`transaction_currency_id`,`name`,`target_amount`,`start_date`,`start_date_tz`,`target_date`,`target_date_tz`,`order`,`active`,`encrypted`,`native_target_amount`) VALUES')
pb_rows = []
for i, (name, acct_id, cur, target, current, start, target_date) in enumerate(PIGGY_BANK_DEFS, 1):
    pb_rows.append(f"({PIGS[name]},'2026-06-24 00:00:00','2026-06-24 00:00:00',NULL,{acct_id},{cur},{esc(name)},{target:.12f},'{start}','{TZ}','{target_date}','{TZ}',{i},1,0,NULL)")
p(',\n'.join(pb_rows) + ';')
p('')

p('INSERT INTO `account_piggy_bank` (`id`,`account_id`,`piggy_bank_id`,`current_amount`,`native_current_amount`) VALUES')
apb_rows = []
for i, (name, acct_id, cur, target, current, start, target_date) in enumerate(PIGGY_BANK_DEFS, 1):
    apb_rows.append(f"({i},{acct_id},{PIGS[name]},{current:.12f},NULL)")
p(',\n'.join(apb_rows) + ';')
p('')

p('INSERT INTO `piggy_bank_events` (`id`,`created_at`,`updated_at`,`piggy_bank_id`,`transaction_journal_id`,`date`,`date_tz`,`amount`,`native_amount`) VALUES')
pbe_rows = []
for i, (name, acct_id, cur, target, current, start, target_date) in enumerate(PIGGY_BANK_DEFS, 1):
    pbe_rows.append(f"({i},'2026-06-24 00:00:00','2026-06-24 00:00:00',{PIGS[name]},NULL,'2026-06-24','{TZ}',{current:.12f},NULL)")
p(',\n'.join(pbe_rows) + ';')
p('')

p('INSERT INTO `piggy_bank_repetitions` (`id`,`created_at`,`updated_at`,`piggy_bank_id`,`start_date`,`start_date_tz`,`target_date`,`target_date_tz`,`current_amount`) VALUES')
pbr_rows = []
for i, (name, acct_id, cur, target, current, start, target_date) in enumerate(PIGGY_BANK_DEFS, 1):
    pbr_rows.append(f"({i},'2026-06-24 00:00:00','2026-06-24 00:00:00',{PIGS[name]},'{start}','{TZ}','{target_date}','{TZ}',{current:.12f})")
p(',\n'.join(pbr_rows) + ';')
p('')

# Categories
p('-- Categories')
p('INSERT INTO `categories` (`id`,`created_at`,`updated_at`,`deleted_at`,`user_id`,`user_group_id`,`name`,`encrypted`) VALUES')
p(',\n'.join(f"({CATS[c]},'2025-01-01 00:00:00','2025-01-01 00:00:00',NULL,1,1,{esc(c)},0)" for c in CATEGORY_DEFS) + ';')
p('')

# Tags
p('-- Tags')
p('INSERT INTO `tags` (`id`,`created_at`,`updated_at`,`deleted_at`,`user_id`,`user_group_id`,`tag`,`tag_mode`,`date`,`date_tz`,`description`,`latitude`,`longitude`,`zoomLevel`) VALUES')
p(',\n'.join(f"({TAGS[t]},'2025-01-01 00:00:00','2025-01-01 00:00:00',NULL,1,1,{esc(t)},'nothing',NULL,NULL,NULL,NULL,NULL,NULL)" for t in TAG_DEFS) + ';')
p('')

# Budgets
p('-- Budgets')
p('INSERT INTO `budgets` (`id`,`created_at`,`updated_at`,`deleted_at`,`user_id`,`user_group_id`,`name`,`active`,`encrypted`,`order`) VALUES')
p(',\n'.join(f"({BUDS[b]},'2025-01-01 00:00:00','2025-01-01 00:00:00',NULL,1,1,{esc(b)},1,0,{i})" for i, b in enumerate(BUDGET_DEFS, 1)) + ';')
p('')

# Budget limits
p('-- Budget limits')
p('INSERT INTO `budget_limits` (`id`,`created_at`,`updated_at`,`budget_id`,`transaction_currency_id`,`start_date`,`start_date_tz`,`end_date`,`end_date_tz`,`amount`,`period`,`native_amount`) VALUES')
bl_rows = []
for name, s, e, amt in BUDGET_LIMIT_DEFS:
    bl_rows.append(f"({nid('budget_limit')},'2025-01-01 00:00:00','2025-01-01 00:00:00',{BUDS[name]},14,'{s}','{TZ}','{e}','{TZ}',{amt:.12f},'monthly',NULL)")
p(',\n'.join(bl_rows) + ';')
p('')

# Bills (subscriptions)
p('-- Bills (Firefly III "subscriptions")')
p('INSERT INTO `bills` (`id`,`created_at`,`updated_at`,`deleted_at`,`user_id`,`user_group_id`,`transaction_currency_id`,`name`,`match`,`amount_min`,`amount_max`,`date`,`date_tz`,`end_date`,`end_date_tz`,`extension_date`,`extension_date_tz`,`repeat_freq`,`skip`,`automatch`,`active`,`name_encrypted`,`match_encrypted`,`order`,`native_amount_min`,`native_amount_max`) VALUES')
b_rows = []
for i, (name, match, amin, amax, sdate, repf, skip) in enumerate(BILL_DEFS, 1):
    b_rows.append(f"({BILLS[name]},'2025-01-01 00:00:00','2025-01-01 00:00:00',NULL,1,1,14,{esc(name)},{esc(match)},{amin:.12f},{amax:.12f},'{sdate}','{TZ}',NULL,NULL,NULL,NULL,{esc(repf)},{skip},1,1,0,0,{i},NULL,NULL)")
p(',\n'.join(b_rows) + ';')
p('')

# Transaction groups
p(f'-- Transaction groups ({len(groups)})')
p('INSERT INTO `transaction_groups` (`id`,`created_at`,`updated_at`,`deleted_at`,`user_id`,`user_group_id`,`title`) VALUES')
g_rows = []
for (gid, d, title) in groups:
    g_rows.append(f"({gid},{esc(dt_sql(d))},{esc(dt_sql(d))},NULL,1,1,{esc(title)})")
p(',\n'.join(g_rows) + ';')
p('')

# Transaction journals
p(f'-- Transaction journals ({len(journals)})')
p('INSERT INTO `transaction_journals` (`id`,`created_at`,`updated_at`,`deleted_at`,`user_id`,`user_group_id`,`transaction_type_id`,`transaction_group_id`,`bill_id`,`transaction_currency_id`,`description`,`date`,`date_tz`,`interest_date`,`book_date`,`process_date`,`order`,`tag_count`,`encrypted`,`completed`) VALUES')
j_rows = []
for (jid, jtype, gid, bill_id, cur, desc, dt, tagc) in journals:
    j_rows.append(f"({jid},{esc(dt_sql(dt))},{esc(dt_sql(dt))},NULL,1,1,{jtype},{gid},{nnum(bill_id)},{cur},{esc(desc)},{esc(dt_sql(dt))},{esc(TZ)},NULL,NULL,NULL,0,{tagc},0,1)")
p(',\n'.join(j_rows) + ';')
p('')

# Transactions (two per journal)
p(f'-- Transactions ({len(tx_rows)})')
p('INSERT INTO `transactions` (`id`,`created_at`,`updated_at`,`deleted_at`,`reconciled`,`account_id`,`transaction_journal_id`,`description`,`transaction_currency_id`,`amount`,`balance_before`,`balance_after`,`balance_dirty`,`foreign_amount`,`foreign_currency_id`,`identifier`,`native_amount`,`native_foreign_amount`) VALUES')
t_rows = []
for (tid, acct_id, jid, cur, amt, desc, famt, fcur, ident, before, after) in tx_rows:
    # Need a created/updated timestamp per row -> pull from journal
    jrec = next(j for j in journals if j[0] == jid)
    ts = dt_sql(jrec[6])
    t_rows.append(f"({tid},{esc(ts)},{esc(ts)},NULL,0,{acct_id},{jid},{esc(desc)},{cur},{amt:.12f},{before:.12f},{after:.12f},0,{nnum(famt)},{nnum(fcur)},{ident},NULL,NULL)")
p(',\n'.join(t_rows) + ';')
p('')

# Account balance history
p(f'-- Account balance history ({len(account_balance_rows)})')
p('INSERT INTO `account_balances` (`id`,`created_at`,`updated_at`,`title`,`account_id`,`transaction_currency_id`,`date`,`date_tz`,`transaction_journal_id`,`balance`) VALUES')
ab_rows = []
for i, (acct_id, cur, d, jid, balance) in enumerate(account_balance_rows, 1):
    ab_rows.append(f"({i},'{d} 00:00:00','{d} 00:00:00',NULL,{acct_id},{cur},'{d}','{TZ}',{jid},{balance:.12f})")
p(',\n'.join(ab_rows) + ';')
p('')

# Category links
p(f'-- Category <-> Transaction Journal links ({len(cat_tj)})')
p('INSERT INTO `category_transaction_journal` (`id`,`category_id`,`transaction_journal_id`) VALUES')
ctj_rows = [f"({i},{cid},{jid})" for i, (cid, jid) in enumerate(cat_tj, 1)]
p(',\n'.join(ctj_rows) + ';')
p('')

# Tag links
p(f'-- Tag <-> Transaction Journal links ({len(tag_tj)})')
p('INSERT INTO `tag_transaction_journal` (`id`,`tag_id`,`transaction_journal_id`) VALUES')
ttj_rows = [f"({i},{tid},{jid})" for i, (tid, jid) in enumerate(tag_tj, 1)]
p(',\n'.join(ttj_rows) + ';')
p('')

# Budget links
p(f'-- Budget <-> Transaction Journal links ({len(bud_tj)})')
p('INSERT INTO `budget_transaction_journal` (`id`,`budget_id`,`budget_limit_id`,`transaction_journal_id`) VALUES')
btj_rows = [f"({i},{bid},NULL,{jid})" for i, (bid, jid) in enumerate(bud_tj, 1)]
p(',\n'.join(btj_rows) + ';')
p('')

p(f'-- Budget <-> Transaction links ({len(bud_t)})')
p('INSERT INTO `budget_transaction` (`id`,`budget_id`,`transaction_id`) VALUES')
bt_rows = [f"({i},{bid},{tid})" for i, (bid, tid) in enumerate(bud_t, 1)]
p(',\n'.join(bt_rows) + ';')
p('')

p('SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;')
p('')

# Sanity summary at bottom for human review
p('-- ============================================================')
p('-- Summary (expected answers the seed was designed for)')
p('-- ============================================================')
march_coffee_total = sum(a for _, _, a, _ in MARCH_COFFEE)
p(f'-- T1 Mar 1-7 Tim Hortons/Starbucks total: C${march_coffee_total:.2f}')
jan_rest_total = sum(a for _, _, a, _ in JAN_RESTAURANTS)
p(f'-- T3 Jan 2026 Restaurants total: C${jan_rest_total:.2f} (budget C$150.00; remaining C${150-jan_rest_total:.2f})')
vac_total = sum(a for _, _, a, _, _ in VACATION)
p(f'-- T7 Vacation summer 2025 total: C${vac_total:.2f}')
p('-- T7 Vacation top-5 by amount (largest first):')
for d, v, a, *_ in sorted(VACATION, key=lambda x: -x[2])[:5]:
    p(f'--     C${a:>8.2f}  {v:<20}  {d}')

print('\n'.join(out))
