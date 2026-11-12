# Firefly III - Personal Finance Manager

A self-hosted personal finance application ([Firefly III](https://www.firefly-iii.org/)) configured with realistic mock data for LLM agent benchmarking.

All benchmark data is baked into a single self-contained Docker image under `/var/lib/mysql`. No external volumes, no separate database service, no environment files to configure. Resetting the environment is just: discard the container, run a new one.

## Quick Start

### Using the pre-built image

```bash
docker pull ghcr.io/mcgill-nlp/firefly:latest
docker run -d --name firefly -p 80:8080 --tmpfs /var/www/html/storage/upload ghcr.io/mcgill-nlp/firefly:latest
```

### Building locally

```bash
docker build -t firefly-populated .
docker run -d --name firefly -p 80:8080 --tmpfs /var/www/html/storage/upload firefly-populated
```

By default, Firefly is built with a fixed benchmark date: the newest
transaction is June 24, 2026, and the container runtime clock is frozen so the
application also treats June 24, 2026 as "today." To intentionally build a
different seed anchor, pass:

```bash
docker build --build-arg FIREFLY_SEED_TODAY=2026-06-24 -t firefly-populated .
```

Or via compose:

```bash
docker compose up -d
```

Open http://localhost in your browser.

### Login Credentials

- **Email**: `test@example.com`
- **Password**: `R9WrgT2vkn63TDBV`

Benchmark tasks, including read-only tasks `050` (Vacation spending) and `056`
(Spotify Premium), require auto-login as `test@example.com`. The runner logs in
after startup or reset and before handing the browser to the agent; task prompts
do not need to include credentials.

## Resetting Data

Since all data lives in the image layer, reset means discarding the container:

```bash
docker rm -f firefly
docker run -d --name firefly -p 80:8080 --tmpfs /var/www/html/storage/upload firefly-populated
```

Or via compose:

```bash
docker compose down
docker compose up -d
```

No `-v` flag is needed — there are no persistent volumes to remove. The `--tmpfs /var/www/html/storage/upload` run option only suppresses the anonymous upload volume declared by the upstream Firefly image; it is not where benchmark data lives.

## Mock Data

The database is pre-seeded with a realistic Canadian personal-finance history. Seed data is synthesized with AI assistance; see `generate_seed.py`.

- **Timeline**: January 2025 through June 24, 2026; the Firefly runtime clock is frozen to June 24, 2026 so app defaults match the seeded data even when run later
- **~529 transaction journals** across 58 accounts, with recurring paycheck, rent, savings transfers, USD freelance deposits, tax refund deposits, ATM/cash-wallet activity, utilities, subscriptions, groceries, gas, coffee, dining, errands, rideshare, and shopping patterns
- **Multi-currency accounts**: CAD (primary) and USD
  - TD Chequing (CAD), TD Savings (CAD), USD Travel Account, Cash Wallet
  - All four asset accounts have non-zero balances and account balance history
- **Expense accounts** include Tim Hortons, Starbucks, Local Bakery, Freshii, Loblaws, Metro, Costco, Farm Boy, No Frills, Sobeys, Walmart, Shell, Esso, Petro-Canada, Amazon.ca, Canadian Tire, Home Depot, IKEA, Best Buy, Indigo, Apple.com, Dollarama, Netflix, Spotify, Uber Eats, McDonald's, Rogers Wireless, Bell Canada, Hydro Ottawa, Enbridge Gas, Videotron, Shoppers Drug Mart, Rexall, Cineplex, LCBO, Presto, Uber, Lyft, Landlord, plus sit-down restaurants (Pho Kim, The Keg Steakhouse, Pai Northern Thai, Copper Branch) and vacation vendors (Lufthansa, Air Canada, Marriott Frankfurt, Vienna Wine Tours, Hertz, Airbnb Montreal, and more)
- **Revenue accounts**: Employer Payroll, CRA Tax Refund, Freelance USD Client
- **9 categories**: Groceries, Gas & Transportation, Entertainment, Utilities & Bills, Dining Out, Shopping, Health & Personal Care, Restaurants, Rent
- **4 tags**: essential, recurring, impulse-buy, Vacation
- **7 pre-existing subscriptions (Firefly "bills")**: Monthly Rent, Home Internet, Spotify Premium, Mobile Phone, Electricity, Natural Gas (every two months), and iCloud Storage (quarterly). Matching historical payments are linked to each subscription. Netflix remains intentionally unseeded as a subscription because a benchmark task creates it.
- **7 budgets** defined (Groceries, Gas & Transportation, Entertainment, Utilities & Bills, Dining Out, Shopping, Restaurants) with monthly limits through the seeded end month
- **1 piggy bank**: New Car, linked to TD Savings, with C$2,500 saved toward a C$28,000 target by June 1, 2028
- **Summer 2025 vacation block** (tagged `Vacation`) covering a Europe trip in June and a Montréal trip in August, with distinct amounts

### Regenerating the seed

The raw SQL at `initdb/002-seed.sql` is generated from `generate_seed.py`. To modify the dataset:

```bash
python3 generate_seed.py > initdb/002-seed.sql
docker compose down && docker compose up -d --build
```

Set `FIREFLY_SEED_TODAY=YYYY-MM-DD` when running `generate_seed.py` to generate
a seed whose latest transaction is anchored to that date. If you change this
away from June 24, 2026, also update the `FAKETIME` value in the Dockerfile so
Firefly's runtime "today" matches the seeded data.

## Architecture

The image bundles:
- **Firefly III core** (PHP 8.5 / Laravel / Apache via s6-overlay) from `fireflyiii/core:latest`
- **MariaDB 11.8** server with its data directory pre-populated at build time

At build time, a seed-SQL stage regenerates `002-seed.sql` with the newest transaction anchored to June 24, 2026, then a MariaDB stage applies `initdb/001-firefly.sql` (schema + default data) and the generated custom eval data. Its `/var/lib/mysql` is copied into the final image layer. At runtime, `entrypoint.sh` starts `mariadbd` on 127.0.0.1 using that baked-in data directory and hands off to Firefly's default entrypoint. The runtime image uses `libfaketime` so Firefly treats June 24, 2026 as the current date.

## File Structure

```
firefly/
  Dockerfile              # Multi-stage build (seed SQL → seeder → runtime)
  entrypoint.sh           # Starts MariaDB, then Firefly
  docker-compose.yml      # Single-service compose (optional)
  generate_seed.py        # Source of truth for 002-seed.sql
  initdb/
    001-firefly.sql       # Full schema + Firefly default data + user
    002-seed.sql          # Generated evaluation seed data
```
