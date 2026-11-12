---
title: Vaultwise Password Manager
emoji: 🔐
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
---

# Vaultwise — Password Manager

A Bitwarden-like password manager pre-seeded with payment information for use alongside the flight-search environment.

## Features

- Vault UI with sidebar navigation (All Items, Favorites, by type)
- Payment card storage with masked card numbers and CVV reveal
- Identity profiles for passenger information (name, address, passport)
- Login credentials and secure notes
- One-click copy for all sensitive fields
- Session-based authentication with HTTP-only cookies

## Default Credentials

| Field    | Value      |
|----------|------------|
| Username | `agent1`   |
| Password | `agentpass` |

## Pre-seeded Vault Items

### Payment Cards
| Name                    | Brand      | Number (last 4) | Expiry  |
|-------------------------|------------|-----------------|---------|
| Visa Platinum ⭐         | Visa       | 1111            | 12/2027 |
| Mastercard Gold         | Mastercard | 5559            | 08/2026 |
| American Express Business | Amex     | 8431            | 03/2028 |
| TD Visa Classic         | Visa       | 0366            | 05/2026 |

### Identities
- **Jane Smith** — Primary traveler (passport US123456789)
- **John Smith** — Secondary traveler (passport US987654321)

### Logins
- **Flight Search** — Passkey and URL for the flight-search environment

### Secure Notes
- **Frequent Flyer Programs** — Loyalty program numbers

## Running Locally

```bash
docker compose up --build
```

Open http://localhost:4580

## API

| Method | Path                    | Description       |
|--------|-------------------------|-------------------|
| POST   | `/api/auth/login`       | Log in            |
| POST   | `/api/auth/logout`      | Log out           |
| GET    | `/api/auth/me`          | Current user      |
| GET    | `/api/vault/items`      | List vault items  |
| GET    | `/api/vault/items/{id}` | Get single item   |
| POST   | `/api/vault/items`      | Create item       |
| PUT    | `/api/vault/items/{id}` | Update item       |
| DELETE | `/api/vault/items/{id}` | Delete item       |

## License

WebArena-Pro's original application code and contributions in this directory are
licensed under the [MIT License](LICENSE).

Dependencies, datasets, media, and other third-party components retain their
respective licenses and attribution requirements. They are not relicensed by
this application's MIT license.
