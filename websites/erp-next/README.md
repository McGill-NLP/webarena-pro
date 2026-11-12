# ERPNext (WebArena-Pro)

ERPNext environment backed by the official Frappe ERPNext image, with the local bench setup and seed data baked into the image during build.

## Quick Start

```bash
# Build
docker build -t webarenapro/erp-next .

# Run
docker run -d --name erp-next -p 8090:8000 webarenapro/erp-next

# Reset to original seed state
docker rm -f erp-next
docker run -d --name erp-next -p 8090:8000 webarenapro/erp-next
```

ERPNext URL: **http://localhost:8090**

The default build applies the ERPNext Local setup flow once during `docker build`:

- `bench new-site erpnext.localhost`
- `bench get-app https://github.com/frappe/erpnext` (only if app repo is missing)
- `bench --site erpnext.localhost install-app erpnext`
- seed data import
- reset snapshot creation

At runtime the entrypoint starts MariaDB, Redis, and:

- starts server with `bench --site erpnext.localhost serve --port 8000 --noreload`

Supporting local services (`mariadb` and `redis`) are started in-container by the entrypoint.

## Seeded User Accounts

| Name | Email / Username | Password | Primary Role |
|------|-------------------|----------|--------------|
| Avery Nguyen | `agent1@erpnext.local` | `User@Secure123` | Sales, Projects |
| Jordan Patel | `agent2@erpnext.local` | `User@Secure123` | Purchase, Projects |
| Sam Kim | `agent3@erpnext.local` | `User@Secure123` | Accounts, Projects |

## Included Mock Data

The seed includes realistic baseline records used by benchmark-style tasks:

- 100 customers
- 100 suppliers
- 95 items
- 53 leads
- 89 item prices
- 102 sales orders
- 102 sales invoices
- 102 purchase orders
- 12 purchase orders billed through linked purchase invoices
- 18 purchase receipts
- 10 delivery notes
- 50 purchase invoices
- 95 stock entries
- Positive stock value distributed across multiple warehouses for inventory dashboards
- 10 assets across fixed asset categories and office locations
- 18 CRM opportunities
- 6 projects with 30 linked tasks
- 5 journal entries

Task 044 asks for one acoustic panel. Its rubrics use the seeded
`ACOUSTIC-PANEL-120` item, and its delivery-note check requires that exact item
and quantity on the same row, with the requested customer, return series, and
source warehouse.

Seed source of truth: [seed_data.json](seed_data.json)

The `synthetic_data.count` setting adds deterministic bulk records at startup so the dataset stays easy to tune without hand-writing every row.
Synthetic transactions are spread across the current year-to-date for dashboard charts, and selected invoices and orders include multiple item rows for child-table tasks.
All seeded system users receive Projects roles so the Projects workspace is usable from every account.

Task 049 starts without the `Percent` unit of measure. Its intent is unchanged:
the agent must discover and create this prerequisite to complete the requested
Quality Goal. The evaluator scores an enabled, exactly named `Percent` unit and
the existing Quality Goal criterion independently with equal weights; creating
only the unit earns half credit. Seed verification rejects a pre-existing
`Percent` before the clean reset snapshot is captured. Reset must remove the
agent-created unit, goal, and any role changes.

## Notes

- Seed data is applied at image build time through ERPNext REST APIs.
- To keep the old first-container-start seeding behavior, build with `--build-arg WEBARENA_ERPNEXT_PRESEED=0`.
- If a build-time seed process is interrupted, rebuild the image to retry from a clean state.
- Site defaults can be customized via environment variables:
	- `ERPNEXT_SITE_NAME` (default: `erpnext.localhost`)
	- `ERPNEXT_ADMIN_PASSWORD` (default: `admin`)
	- `ERPNEXT_DB_ROOT_PASSWORD` (default: `root`)
	- `ERPNEXT_BASE_URL` (default: `http://127.0.0.1:8000`)
