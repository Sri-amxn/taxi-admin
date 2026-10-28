# Send this to all six teammates

Contract version: 1.0. Proposed shared conventions for concurrent development. Agree on changes in the shared repository; do not silently rename fields.

## Shared baseline

React/Vite frontend, Python/Flask REST API, SQLAlchemy ORM and SQL Server for integrated persistence. One Flask app and one SQLAlchemy `db`/session per request. One coordinated Alembic history. Admin tables use `admin_` prefixes; this is a deliberate collision-avoidance choice, not a demand that other modules rename their tables.

Use `/api` for API routes and `/admin/*` for admin pages. Vite proxies `/api` to Flask on port 5001, avoiding macOS services that commonly occupy port 5000. Production needs a same-origin reverse proxy and SPA fallback for `/admin/*`.

IDs at module boundaries are opaque strings. Do not infer IDs from names/phones or send numeric IDs sometimes and strings elsewhere. Timestamps are ISO 8601 with explicit UTC `Z` or offset. Decimal money and percentages are JSON strings, e.g. `"500.00"`. Currency is INR in version 1.

Success: `{"data": ..., "request_id": "uuid"}`. Failure: `{"error":{"code":"REQUEST_FAILED","message":"..."},"request_id":"uuid"}`. Codes: 400 validation, 401 auth, 403 role, 404 missing, 409 edit/settlement conflict, 503 missing provider. This envelope is implemented for admin routes; other modules may adapt at their boundaries.

## Ownership and the specific handoff

| Person | Owns | Admin needs from them |
|---|---|---|
| Anurag | Users, mobile/password login, token security | Verified user ID + role, short-lived bearer token, active-account validation |
| Joy | Map, route quote and rider request | Server-validated route distance/duration; call shared fare service and persist returned snapshot |
| Naveen | Rider lifecycle/status | Read adapter for authoritative rides; settlement hook in ride-completion transaction |
| Shivendra | Driver onboarding, permissions and status | Driver identity/status; no duplicated driver model in admin |
| Udit | Dashboard, locations, invitation and trip UI | UTC latest location timestamp, active ride ID and completion-service coordination |
| Ujjwala | Admin policies, surge zones, shares, ledger, audit | Publishes admin API and service hooks; coordinates migration/API contracts |

Naveen and Udit should agree on ONE backend ride-completion owner. Both frontends must call that service, rather than independently creating settlements.

## Auth contract

`Authorization: Bearer <access_token>`. Default implementation accepts HS256 JWT with `sub` (string user ID), `role` (`admin`, `driver` or `rider`), `iat`, `exp`, issuer `genz-taxi`, audience `genz-taxi-api`. Share the secret through a private environment variable, never React/Git. If the auth team chooses another token shape/algorithm, supply `ADMIN_AUTH_VERIFIER(request)`; do not weaken signature verification. The callback must also enforce account status/revocation.

Demo login is localhost-only and disabled when `APP_MODE=integrated`. Do not use it in the merged application. This module does not duplicate the authentication owner's registration/login APIs.

## Monitoring adapter

The shared backend supplies `ADMIN_MONITOR_PROVIDER`, a callable returning:

```json
{
  "source": "live",
  "as_of": "2026-10-28T10:00:00Z",
  "drivers": [{
    "driver_id": "DRV-001", "name": "Example", "status": "available",
    "location_updated_at": "2026-10-28T09:59:45Z", "active_ride_id": null
  }],
  "rides": [{
    "ride_id": "RIDE-001", "rider_id": "RID-001", "driver_id": null,
    "status": "SEARCHING", "pickup_label": "Pickup", "dropoff_label": "Destination",
    "fare_total": "240.00"
  }]
}
```

Return an authorized, bounded monitoring snapshot in v1; for large datasets extend the contract with server-side filters/pagination. Admin computes freshness at 90 seconds; offline drivers do not trigger stale-location alerts. Available means `available`, fresh location and no active ride.

Driver statuses: `offline`, `available`, `ride_requested`, `ride_accepted`, `arriving_at_pickup`, `waiting_for_rider`, `ongoing_ride`, `ride_completed`, `temporarily_unavailable`, `suspended`. Ride statuses: `SEARCHING`, `ASSIGNED`, `ARRIVING`, `WAITING`, `ONGOING`, `COMPLETED`, `CANCELLED`, `NO_DRIVER_FOUND`. Map your internal enums in the adapter if needed. Admin does not implement or override either state machine.

## Admin endpoints

All require backend-verified admin access. See `swagger.json` or running `/api/docs/` for request schemas.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/admin/dashboard` | Operations snapshot and all-time recorded allocations |
| GET | `/api/admin/drivers`, `/api/admin/rides` | Monitoring feeds |
| GET / PUT | `/api/admin/fare-rules` | Single active fare policy |
| GET / POST | `/api/admin/surge-zones` | List/create circular zones |
| PUT | `/api/admin/surge-zones/{id}` | Edit/disable zone |
| GET / PUT | `/api/admin/revenue-share` | Current effective split; append historical setting |
| GET | `/api/admin/audit`, `/api/admin/ledger` | `page=1&page_size=25`, maximum size 100 |
| POST | `/api/admin/quote-preview` | Admin calculator only, never a rider quote authority |

Admin updates send current `version` and a 3–500 character `reason`. A 409 means reload and review before resubmitting. Surge zones are disabled rather than deleted to preserve audit/quote references.

## Pricing and settlement policy v1

Eligible fare = locked transport fare in INR, excluding separately accounted taxes, tips, gateway fees, refunds and cancellations. This is an explicit project assumption; commercial requirements may change it. No refund/payment execution is implemented.

Fare = `max(minimum, base + rounded distance charge + rounded duration charge) × highest eligible multiplier`, with a global cap. Round HALF_UP to paise. Circular geofence boundaries are inclusive; time windows are start-inclusive/end-exclusive. Monday=0. Overnight day refers to starting day; equal start/end means all day. Settings changes affect new quotes; the ride owner must store and honor accepted snapshots.

Traffic/demand is a trusted backend policy output passed as `signal_multiplier`; this module does not invent a signal from client data. Missing signal defaults to 1. Do not let a rider send their own distance, duration, multiplier, eligible fare or settlement request.

Driver settlement rounds half up; company gets the remainder so amounts exactly equal eligible fare. One unique ledger per ride. Repeated identical completion is idempotent; a changed amount/driver conflicts. Split is selected for the authoritative completion timestamp, preserving delayed retry behavior.
