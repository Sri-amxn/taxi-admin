"""Explicit demo adapters: these do not pretend to be live ride/driver tables."""
from datetime import datetime, timedelta, timezone
from .models import db, FareRules, RevenueShare
from .services import save_zone, settle_ride

def seed():
    if db.session.get(FareRules, 1):
        return
    db.session.add(FareRules(id=1, base_fare=40, per_km_rate=12, per_minute_rate=2,
        minimum_fare=60, max_multiplier=3, surge_enabled=True))
    db.session.add(RevenueShare(driver_pct=85, company_pct=15, updated_by='system', version=1,
        effective_from=datetime(2020, 1, 1)))
    db.session.flush()
    save_zone({'name': 'City centre · evening peak', 'latitude': 28.6139, 'longitude': 77.2090,
        'radius_m': 4000, 'multiplier': '1.50', 'timezone': 'Asia/Kolkata', 'start_time': '17:00',
        'end_time': '21:00', 'days': [0, 1, 2, 3, 4, 5, 6], 'enabled': True, 'reason': 'Initial demonstration zone'}, 'demo-admin')
    for i, amount in enumerate(['500.00', '240.00', '380.00', '165.00']):
        settle_ride(f'DEMO-{i+1:03}', f'DRV-{i+1:03}', amount, datetime.now(timezone.utc))
    db.session.commit()

def monitoring():
    now = datetime.now(timezone.utc)
    return {
        'source': 'demo', 'as_of': now.isoformat(),
        'drivers': [
            {'driver_id': 'DRV-001', 'name': 'Aarav Sharma', 'status': 'available', 'location_updated_at': now.isoformat(), 'active_ride_id': None},
            {'driver_id': 'DRV-002', 'name': 'Meera Singh', 'status': 'ongoing_ride', 'location_updated_at': now.isoformat(), 'active_ride_id': 'RIDE-102'},
            {'driver_id': 'DRV-003', 'name': 'Kabir Das', 'status': 'available', 'location_updated_at': (now-timedelta(minutes=8)).isoformat(), 'active_ride_id': None},
            {'driver_id': 'DRV-004', 'name': 'Riya Kapoor', 'status': 'offline', 'location_updated_at': None, 'active_ride_id': None},
        ],
        'rides': [
            {'ride_id': 'RIDE-101', 'rider_id': 'RID-001', 'driver_id': None, 'status': 'SEARCHING', 'pickup_label': 'Connaught Place', 'dropoff_label': 'India Gate', 'fare_total': '180.00'},
            {'ride_id': 'RIDE-102', 'rider_id': 'RID-002', 'driver_id': 'DRV-002', 'status': 'ONGOING', 'pickup_label': 'Saket', 'dropoff_label': 'Hauz Khas', 'fare_total': '240.00'},
            {'ride_id': 'DEMO-001', 'rider_id': 'RID-003', 'driver_id': 'DRV-001', 'status': 'COMPLETED', 'pickup_label': 'Airport', 'dropoff_label': 'City centre', 'fare_total': '500.00'},
        ]}
