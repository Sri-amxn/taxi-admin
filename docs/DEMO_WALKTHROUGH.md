# Demonstrate your module

1. Run `python3 run.py` on Mac or `py run.py` on Windows, then open http://127.0.0.1:5173/admin.
2. Open the demo workspace. Explain that operations are sample data while settings are persisted.
3. Overview: show available driver count, stale-location warning and recorded allocation totals.
4. Drivers: search `Kabir`. His stale location means he is excluded from available count.
5. Fare & surge: change the base fare with a reason and save. Use the preview calculator to verify the price changes.
6. Edit a surge zone: review radius, weekdays, time window and timezone. Disable the zone or global surge to show no-surge behavior.
7. Revenue share: initial 85/15 preview on ₹500 is ₹425/₹75. Try an invalid total, then save 90/10 with a reason. Historical ledger rows stay 85/15.
8. Audit trail: expand before/after JSON to show the admin identity, timestamp and reason.
9. Open Swagger at http://127.0.0.1:5001/api/docs/. Obtain a demo token through `POST /api/demo/login` using an API client. Click Authorize and enter `Bearer <token>`. Test settings validation or a stale `version` returning 409. Do not screenshot or commit tokens.
10. Show `TEAM_CONTRACT.md`: explain the provider adapters and atomic ride-completion settlement hook your teammates will connect.

The standalone UI does not complete real rides or process money. Settlement behavior is demonstrated by the seeded ledger and backend tests until the shared ride service is connected.
