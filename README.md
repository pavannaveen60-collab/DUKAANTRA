# DUKAANTRA

DUKAANTRA is a merchant workspace for local retailers. It provides inventory,
customer and order management, sales analytics, ML-assisted forecasts, business
recommendations, a Gemini-powered chat assistant, and a PayPal Sandbox checkout
flow.

## Architecture

- `backend/`: FastAPI API, SQLAlchemy models, PostgreSQL access, AI/ML services,
  authentication, and payment integration.
- `frontend/`: Next.js App Router application.
- `database/`: database-related project resources.

The frontend calls the backend through `NEXT_PUBLIC_API_BASE_URL`. Protected
endpoints use a JWT created by the backend. Merchants register and sign in
through the frontend; the server returns their authorized shops and the
frontend requires an explicit selection when an account has multiple shops.

## Technology

- Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL with Psycopg 3
- Pydantic Settings, PyJWT, and `pwdlib` with Argon2
- Next.js, React, TypeScript, and Tailwind CSS
- Gemini API for the shop-aware chat assistant
- scikit-learn, XGBoost, pandas, NumPy, and joblib for ML predictions

## Prerequisites

- Python 3.12
- Node.js 20.9 or later and npm
- A running PostgreSQL instance

## PostgreSQL

Create a PostgreSQL database named `dukaantra` and a database role for the
application. Keep the role password private and use it only in the local
backend environment file. Set `DATABASE_URL` there to a Psycopg SQLAlchemy URL,
for example:

```text
postgresql+psycopg://USER:PASSWORD@localhost:5432/dukaantra
```

The application does not apply schema changes automatically at startup.
Install backend dependencies, configure the database, then create a fresh
database schema with the versioned migration workflow:

```bash
cd backend
python -m alembic -c alembic.ini upgrade head
```

## Backend setup

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` locally with the PostgreSQL URL and a strong,
unique `JWT_SECRET_KEY`. Add a Gemini key only if you intend to use chat. The
PayPal values in the example are for Sandbox configuration; do not put live
credentials in this project or use this checkout flow for real payments.

Start the API from the `backend/` directory:

```bash
source .venv/bin/activate
uvicorn app:app --reload
```

The API health check is at `http://127.0.0.1:8000/health`. Interactive API
documentation is available at `http://127.0.0.1:8000/docs`.

## Frontend setup

```bash
cd frontend
npm ci
cp .env.local.example .env.local
```

The example frontend environment file contains the API base URL; no shop ID is
needed. Start the frontend with:

```bash
npm run dev
```

Open `http://localhost:3000`. New merchants can register, create a shop, and
continue to the dashboard. Returning merchants sign in; users without a shop
are sent through shop setup, while users with multiple shops choose one. Shop
creation stores a business phone number on the shop record.

### Existing database adoption and upgrade

Alembic's first revision is a baseline for the existing DUKAANTRA schema
before the nullable `shops.phone` column; the next revision adds that column.
The baseline describes `users`, `shops`, `products`, `customers`, `inventory`,
`orders`, `order_items`, `payments`, `inventory_movements`, and `agent_tasks`,
including their model-defined constraints and indexes.
The old standalone SQL file at
`backend/migrations/20261111_add_shop_phone.sql` is retained for historical
reference and must not be run alongside Alembic.

Before adopting an existing database, take a verified backup and compare its
schema with the baseline. Do not stamp a database whose tables, columns,
constraints, indexes, or foreign keys differ from the documented baseline.
No existing table or merchant data is recreated by stamping.

For an unversioned existing database whose schema matches the baseline and
does **not** contain `shops.phone`, run these commands manually. This applies
the phone revision and then the order-idempotency table:

```bash
cd backend
python -m alembic -c alembic.ini stamp 202611110001
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini check
```

For an unversioned existing database that already contains `shops.phone` and
otherwise matches the current model schema, stamp it at the phone revision
instead, then upgrade to add the idempotency table:

```bash
cd backend
python -m alembic -c alembic.ini stamp 202611110002
python -m alembic -c alembic.ini upgrade head
python -m alembic -c alembic.ini check
```

Stamping writes only Alembic's version marker; `upgrade head` applies pending
revisions. These commands are operator-run and are never executed on
application startup. If schema inspection or `alembic check` reveals other
differences, stop and prepare a reviewed reconciliation migration rather than
stamping or altering the database blindly. `backend/init_db.py` no longer
calls `Base.metadata.create_all()` because that bypasses migration tracking.
The baseline cannot be downgraded because it would drop application data, and
the phone revision refuses downgrade because that would discard saved phone
values.

## AI and ML behavior

The AI Workforce is a controlled, shop-scoped analysis workflow. The
Inventory Intelligence agent compares current stock with configured thresholds
and confirmed sales; demand-based reorder quantities require at least 14 days
of history and 3 distinct sale days, and assume a 14-day supplier lead time.
Sales and Growth Intelligence reports confirmed-order revenue, order value,
product performance, co-purchase evidence, and a 28-day revenue comparison.
Demand Intelligence reports trends and provides a 7-day historical-average
estimate only when it has at least 14 observed days and 3 sale days. The
estimate is experimental and does not model seasonality, promotions, stockouts,
or future events.

Use the **Run analysis** control on Insights, or call
`POST /api/v1/shops/{shop_id}/ai-workforce/run`. The authenticated owner must
own the supplied shop. `GET /api/v1/shops/{shop_id}/ai-workforce/` reads the
latest persisted report and execution history without starting a run. The
existing `AgentTask` table stores orchestrator and per-agent status, timestamps,
results, and safe error summaries. A PostgreSQL advisory lock serializes active
runs per shop. Recommendation priorities use explicit stock and revenue-change
rules; no purchasing, messaging, pricing, inventory, order, or payment changes
are performed automatically. Recommendations remain pending merchant approval.

This deterministic workforce does not require Gemini or the synthetic-trained
ML artifacts. The separate ML endpoints still use the model bundle described
below; those predictions remain experimental decision support, not proven
business outcomes.

The optional model bundle is stored locally under
`backend/ml/artifacts/dukaantra_retail_models.joblib` and is intentionally
ignored by Git. Version 2 uses time-ordered train/validation/test partitions,
rolling-origin evaluation when enough dates exist, and explicit feature and
target metadata. Demand predicts the next seven days; stockout labels indicate
whether that horizon's demand exceeds stock at prediction time; sales predicts
next-day revenue from prior-day features. Same-day units and average price are
not inputs to the revenue forecast. Training data is reproducible synthetic
retail data, not merchant data, so all resulting model metrics and predictions
remain experimental and are not validated for real shops.

The existing v1 artifact is incompatible and is rejected by the v2 loader.
The existing local `training_metrics.json` records v1 random-split results;
those historical figures are stale and must not be interpreted as valid
forecast or merchant-accuracy evidence.
The merchant ML API endpoints instead use transparent shop-scoped baselines
and return an insufficient-data status when a minimum 14-day history is not
available. They do not consume the unvalidated synthetic artifact.

To explicitly train and replace the ignored local model artifact:

```bash
cd backend
.venv/bin/python -c "from ml.retail_ml import train_models; train_models()"
```

Training uses synthetic retail data only. It records sample counts, evaluation
periods, baseline comparisons, and limitations; it does not claim merchant
accuracy. Model loading is cached in the API process, validates the v2 schema
and feature compatibility, and does not automatically train. Restart the
backend after replacing the model bundle so the process loads the new artifact.

Gemini chat receives the authenticated shop's inventory and recent order
context and is intended to answer using that supplied data. Gemini requires a
configured key and network access. No live Gemini calls are made by the local
test suite.

## PayPal Sandbox limitations

PayPal is configured for Sandbox checkout in USD. The application converts its
INR order total to USD using a published exchange-rate snapshot. A valid OAuth
access token confirms app authentication only; it does not prove that a
particular buyer/merchant combination can complete approval or capture.

The observed Sandbox results reported for this project were:

- US Business Sandbox seller with US Personal Sandbox buyer: a $5 capture
  succeeded.
- India Business Sandbox seller with US Personal Sandbox buyer: PayPal declined
  the attempt with an international-regulations message.

These are observed test outcomes, not a guarantee of current PayPal policy.
Indian cross-border payment acceptance is not established by this application.
Do not initiate real payments or treat this Sandbox integration as production
payment readiness.

There is a post-capture reconciliation risk: PayPal may complete a capture
before the application commits its local payment, order, and inventory
transaction. If the process/database fails at that point, the local payment can
remain pending even though PayPal captured funds, and inventory may not be
deducted. A safe production design needs a durable reconciliation mechanism
(for example, verified PayPal webhooks plus a periodic order/capture status
reconciler) that idempotently records capture state and inventory movement.
That payment-flow change has not been implemented.

## Demo checklist

1. Start PostgreSQL and initialize the schema.
2. Configure local backend/frontend environment files.
3. Start the backend and frontend in separate terminals.
4. Register or sign in, create/select an authorized shop, then demonstrate
   inventory, confirmed orders, analytics, and the
   AI Workforce with available shop data.
5. Demonstrate Gemini only when configured and describe ML outputs as
   estimates trained initially on synthetic retail data.
6. If showing PayPal, use Sandbox accounts only and explain the observed
   country-pair limitation and pending reconciliation risk.

## Local quality checks

Backend unit tests:

```bash
cd backend
.venv/bin/python -m unittest discover -s tests -v
```

The real PostgreSQL order-idempotency tests are opt-in and destructive only to
their dedicated disposable database. Run them against an isolated local
PostgreSQL cluster using a database named
`dukaantra_idempotency_disposable` and a Unix socket under
`/tmp/dukaantra-idempotency-pg-...`; never point either URL at the working
application database:

```bash
cd backend
export DUKAANTRA_TEST_DATABASE_URL='postgresql+psycopg://<local-role>@/dukaantra_idempotency_disposable?host=/tmp/dukaantra-idempotency-pg-<unique>&port=<port>'
export DATABASE_URL="$DUKAANTRA_TEST_DATABASE_URL"
.venv/bin/alembic -c alembic.ini upgrade head
.venv/bin/python -m unittest -v tests.test_order_idempotency_postgres
```

The integration test refuses database names or socket paths outside that
disposable namespace and clears only the dedicated test database between
cases. It verifies PostgreSQL's configured default isolation level and also
exercises `REPEATABLE READ` and `SERIALIZABLE`. The application does not set a
SQLAlchemy isolation override, so PostgreSQL's configured default applies; the
disposable PostgreSQL 16 cluster used for verification reported
`READ COMMITTED`.

Frontend lint and production build:

```bash
cd frontend
npm run lint
npm run build
```

Do not commit `.env`, `.env.local`, `.venv`, `node_modules`, Next.js build
output, or trained model bundles.
