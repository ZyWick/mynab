# my-ynab

Custom YNAB-style personal-finance backend. FastAPI + Postgres + Plaid. iOS frontend planned later.

## Stack

- Python 3.12, FastAPI, SQLAlchemy 2.x (async), asyncpg
- Postgres 16 (Docker Compose)
- Alembic for migrations
- argon2 + JWT for auth
- Plaid (sandbox) for bank linking — wired in a later milestone

## First-time setup

```powershell
# 1. Copy env file
Copy-Item .env.example .env

# 2. Generate a Fernet key for Plaid access-token encryption, then paste it
#    into .env as TOKEN_ENCRYPTION_KEY
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 3. Fill in your Plaid sandbox creds in .env (PLAID_CLIENT_ID, PLAID_SECRET)
#    Get them at https://dashboard.plaid.com/team/keys

# 4. Start Postgres
docker compose up -d

# 5. Install Python deps (uv reads pyproject.toml and creates .venv)
uv sync

# 6. Create initial migration from current models, then apply it
uv run alembic revision --autogenerate -m "init"
uv run alembic upgrade head
```

## Run the API

```powershell
uv run uvicorn app.main:app --reload
```

Open http://localhost:8000/docs for the Swagger UI.

## Smoke test

```powershell
# Register a user (returns a JWT)
curl -X POST http://localhost:8000/auth/register -H "Content-Type: application/json" `
  -d '{"email":"me@example.com","password":"supersecret"}'

# Use the token
curl http://localhost:8000/me -H "Authorization: Bearer <token>"
```

## Project layout

```
app/
  main.py          FastAPI app + router wiring
  config.py        Settings (pydantic-settings, reads .env)
  db.py            Async engine, session dependency, declarative Base
  security.py      Argon2 hashing, JWT encode/decode
  deps.py          get_current_user dependency
  models/          SQLAlchemy ORM (User, PlaidItem, Account, Category, Transaction, BudgetMonth)
  schemas/         Pydantic request/response models
  routers/         auth.py, me.py
migrations/        Alembic env + versions
docker-compose.yml Postgres service
```

## Plaid link flow (sandbox)

The backend exposes three endpoints. All require a JWT.

1. **`POST /plaid/link-token`** → returns a `link_token`. A client (Plaid Link JS / iOS SDK)
   uses this to open the bank-selection UI and produces a short-lived `public_token`.
2. **`POST /plaid/exchange-public-token`** with `{"public_token": "..."}` → exchanges it for
   a long-lived `access_token`, stores it Fernet-encrypted, and ingests the linked accounts.
3. **`POST /plaid/sync`** → calls `/transactions/sync` for every linked item, persists added /
   modified / removed transactions, and advances the per-item cursor. Idempotent — call as
   often as you want.

### Trying it without a real client (sandbox shortcut)

Plaid's sandbox can mint a `public_token` directly via `/sandbox/public_token/create`, which
lets you exercise the whole pipeline from curl. The Plaid dashboard has a sandbox playground
that does this for you. Once you have a `public_token`, POST it to
`/plaid/exchange-public-token`, then call `/plaid/sync`.

## Envelope budgeting

Categories are user-scoped envelopes. Each month you assign money to envelopes; transactions
get categorized; "available" is the running balance carried across months.

- `GET /categories` (optional `?include_archived=true`)
- `POST /categories` — `{ "name": "Groceries", "group_name": "Food" }`
- `PATCH /categories/{id}` — rename, regroup, or set `archived`
- `DELETE /categories/{id}` — hard delete (transactions referencing it are set to uncategorized)
- `POST /budget/assign` — `{ "category_id": "...", "year": 2026, "month": 5, "assigned_amount": "400.00" }` (upsert)
- `GET /budget/{year}/{month}` — per-category `assigned`, `activity` (sum of transactions this
  month), and `available` (cumulative `assigned − activity` through the target month)
- `PATCH /transactions/{id}/category` — `{ "category_id": "..." }` or `{ "category_id": null }`

Plaid sends spending as **positive** amounts, so `activity` is positive for outflows and
`available = sum(assigned) − sum(activity)` works the YNAB way: a positive `available` means
money still in the envelope, negative means you overspent.

## What's next (planned milestones)

- **iOS client** — native Swift app talking to this JSON API via JWT bearer auth.
- Nice-to-haves: payee rules (auto-categorize), split transactions, scheduled/recurring
  transactions, goals per category.
