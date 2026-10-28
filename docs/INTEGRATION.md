# Merge into the team's app

The standalone module is working, but adapters must be implemented against teammates’ eventual models. Do not copy demo driver/ride data into production or run the demo login as real authentication.

## 1. Shared Flask app and ORM

Before merging, agree on one `db` object. Either let the shared app import `db` from `admin_module.models`, or change that single import source to your shared `extensions.db`. Every admin import must ultimately reference the same instance as the ride repository. Do not create a second independent SQLAlchemy instance/session for settlement.

```python
from flask import Flask
from admin_module import db, register_admin
from flask_migrate import Migrate

app = Flask(__name__)
app.config.from_object(YourConfig)
db.init_app(app)
Migrate(app, db)
register_admin(app)
app.config['ADMIN_AUTH_VERIFIER'] = verify_team_access_token
app.config['ADMIN_MONITOR_PROVIDER'] = get_operations_snapshot
```

`register_admin` installs app-wide error/request-ID handlers. If the shared app already owns these, reconcile them centrally rather than overwriting them blindly. It does not create schema, seed records or install demo login. Configure the shared app's body limit, logging, auth rate limiting, HTTPS and deployment settings centrally.

The default verifier validates signature/expiry/issuer/audience but does not query the shared Users table. The real auth callback must enforce active-account/revocation state and return `{'sub':'user-id','role':'admin'}`. Never accept role or actor IDs directly from admin request bodies.

## 2. SQL Server and migrations

Use a shared SQL Server reachable from both OSes. Install `pyodbc` and Microsoft ODBC Driver 18 locally. Example `backend/.env` (replace credentials; percent-encode special URL characters):

```dotenv
APP_MODE=integrated
DATABASE_URL=mssql+pyodbc://USER:PASSWORD@HOST:1433/TaxiDb?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes
JWT_SECRET=team-secret-at-least-32-random-characters
JWT_ISSUER=genz-taxi
JWT_AUDIENCE=genz-taxi-api
```

For complex passwords prefer `sqlalchemy.engine.URL.create()` in shared Python config. Keep certificate validation enabled; configure trusted certificates for the SQL Server host. No server credentials belong in `VITE_*` variables.

On the standalone backend:

```sh
../.venv/bin/python -m pip install pyodbc
../.venv/bin/flask --app app db upgrade
../.venv/bin/flask --app app init-settings
```

Windows equivalents use `..\.venv\Scripts\python.exe`. `run.py setup` is specifically a demo setup and intentionally refuses demo seeding when integrated mode is selected. Do not reuse it as a production migration command.

In an existing shared Alembic history, do **not** replace its migrations or run an unrelated root history. Import admin models, generate a revision against the team's current head, review it to ensure it only adds `admin_*` tables, and apply the single reviewed migration. The included standalone revision is the reference schema. Only the migration coordinator should change shared migration heads. Cross-module IDs are strings without foreign keys here because teammate schema/types do not exist yet; add reviewed FKs once authoritative table names/types are agreed.

## 3. Authoritative rider pricing hook (Joy)

```python
from admin_module.services import calculate_quote

# Obtain distance/duration from the server-side Routes API adapter.
snapshot = calculate_quote(
    distance_meters=route.distance_m,
    duration_seconds=route.duration_seconds,
    latitude=ride.pickup_lat,
    longitude=ride.pickup_lng,
    signal_multiplier=trusted_demand_policy_multiplier, # defaults to 1
)
# Save the WHOLE snapshot in the fare quote repository and associate it with the ride.
# Return a quote_id plus the snapshot to the rider.
```

The route adapter must normalize provider measurements to at most two decimal places before calling the service. Validate quote ownership/expiry before confirmation. Once confirmed, use that persisted snapshot rather than recalculating against later admin settings. The admin preview endpoint accepts manual figures for testing and must never be used as a public authoritative quote endpoint.

This module intentionally does not register `/api/fares/quote`, avoiding collision with Joy's implementation. No Google key is needed to run the admin module.

## 4. Atomic completion and settlement (Naveen/Udit)

```python
from datetime import datetime, timezone
from admin_module import db
from admin_module.services import settle_ride

# In the shared ride service, after auth and state validation:
# Lock/conditionally update the ride using your repository.
# Verify assigned driver identity and the allowed transition.
ride.status = 'COMPLETED'
ride.completed_at = datetime.now(timezone.utc)  # authoritative server value; set once
ledger = settle_ride(
    ride_id=str(ride.id), driver_id=str(ride.driver_id),
    eligible_fare=ride.locked_transport_fare,
    completed_at=ride.completed_at,
)
# Update driver status in this same session/transaction.
db.session.commit()
```

The hook flushes but NEVER commits. The ride service must roll back all ride/status/ledger changes together on failure. On duplicate/concurrent settlement unique-key errors, roll back the whole transaction, reload authoritative ride state, then retry or return existing completion. Do not catch a failed flush and continue using that session without rollback. Reuse the original completion timestamp on retry; do not overwrite it.

Ledger uniqueness prevents two settlements; it does not independently solve the team's ride state concurrency. That must be handled by the ride service and tested against SQL Server. There is no client-facing arbitrary settlement endpoint.

## 5. React integration

`frontend/src/main.jsx` is the standalone entry point. `App.jsx` exports `AdminRoutes` without mounting a root. In the team's existing BrowserRouter, import and render that route tree at `/admin/*` (it uses absolute `/admin` routes):

```jsx
import {AdminRoutes} from './admin/App';
import {setAccessToken} from './admin/api';
// On successful shared login / token refresh:
setAccessToken(auth.accessToken);
// Inside the team's existing router layout:
<Route path="/admin/*" element={<div className="genz-admin"><AdminRoutes /></div>} />
```

Do not wrap an existing router in a second BrowserRouter. Place the example Route inside your shared Routes component. AdminRoutes uses relative child paths. Render your shared navigation/layout around it, or reuse the standalone sidebar. Keep role-based navigation in the shared UI; server checks remain mandatory.

The stylesheet is prefixed with `.genz-admin`; keep the wrapper when integrating. It does not style other modules. Fonts have system fallbacks and do not require network access for functionality.

Calls use relative `/api` URLs. Use the dev proxy or a same-origin reverse proxy; if deploying separate origins, implement explicit allowed origins/CORS in the shared backend. Never hardcode someone's LAN IP in source code. Admin monitoring is manually refreshed in v1; it is not a WebSocket client.

## 6. Team integration checks

1. Anurag's actual admin token works; rider/driver/expired/disabled identities fail.
2. Driver/ride adapter reflects authoritative statuses and stale timestamps, not sample data.
3. Admin fare change affects a new rider quote; confirmed quote remains locked.
4. Concurrent settings edits return conflict rather than silent overwrites.
5. Complete a ₹500 eligible ride: ledger ₹425 driver / ₹75 company by default.
6. Retry/concurrently complete it: exactly one settlement, one completion, valid driver state.
7. Change split to 90/10; a new completion allocates ₹450/₹50 while old entries stay unchanged.
8. Run migration/auth/quote/completion tests against the team's SQL Server on both development OSes.

Remaining team policies: actual tax/refund/cancellation treatment, demand/traffic thresholds, Google route integration, user lifecycle, support/incident actions and production operations. They are not simulated as completed integrations.
