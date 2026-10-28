from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import radians, sin, cos, atan2, sqrt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select
from .models import db, FareRules, SurgeZone, RevenueShare, RevenueLedger
from . import repository as repo

class Problem(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status

def decimal(value, name, lo='0', hi='1000000'):
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d < Decimal(lo) or d > Decimal(hi) or d.as_tuple().exponent < -2:
            raise ValueError()
        return d
    except (InvalidOperation, ValueError, TypeError):
        raise Problem(f'{name} must be between {lo} and {hi}, with at most 2 decimal places.')

def number(value, name, lo, hi):
    try:
        n = float(value)
        if not lo <= n <= hi or isinstance(value, bool):
            raise ValueError()
        return n
    except (ValueError, TypeError):
        raise Problem(f'{name} must be between {lo} and {hi}.')

def reason(data):
    s = data.get('reason', '')
    if not isinstance(s, str) or not 3 <= len(s.strip()) <= 500:
        raise Problem('Provide a reason of 3–500 characters.')
    return s.strip()

def check_version(data, row):
    if type(data.get('version')) is not int or data['version'] != row.version:
        raise Problem('Settings changed. Reload and try again with the current version.', 409)

def boolean(data, key):
    if type(data.get(key)) is not bool:
        raise Problem(f'{key} must be true or false.')
    return data[key]

def update_fare(data, actor):
    row = repo.fare()
    check_version(data, row)
    before = repo.serialize(row)
    values = {k: decimal(data.get(k), k) for k in ('base_fare', 'per_km_rate', 'per_minute_rate', 'minimum_fare')}
    values['max_multiplier'] = decimal(data.get('max_multiplier'), 'max_multiplier', '1', '10')
    values['surge_enabled'] = boolean(data, 'surge_enabled')
    why = reason(data)
    for k, v in values.items():
        setattr(row, k, v)
    db.session.flush()
    repo.audit(actor, 'fare_rules.updated', 1, before, repo.serialize(row), why)
    return row

def save_zone(data, actor, zone_id=None):
    row = db.session.get(SurgeZone, zone_id) if zone_id else SurgeZone()
    if row is None:
        raise Problem('Zone not found.', 404)
    before = repo.serialize(row) if zone_id else None
    if zone_id:
        check_version(data, row)
    name = data.get('name', '')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        raise Problem('Zone name must contain 1–100 characters.')
    try:
        ZoneInfo(data['timezone'])
        for key in ('start_time', 'end_time'):
            if datetime.strptime(data[key], '%H:%M').strftime('%H:%M') != data[key]:
                raise ValueError()
    except (KeyError, ValueError, TypeError, ZoneInfoNotFoundError):
        raise Problem('Use a valid IANA timezone and HH:MM times.')
    days = data.get('days')
    if not isinstance(days, list) or not days or any(type(d) is not int or d not in range(7) for d in days):
        raise Problem('days must be a nonempty array of weekday numbers (Monday=0).')
    why = reason(data)
    row.name = name.strip()
    row.latitude = number(data.get('latitude'), 'latitude', -90, 90)
    row.longitude = number(data.get('longitude'), 'longitude', -180, 180)
    radius = number(data.get('radius_m'), 'radius_m', 100, 100000)
    if radius != int(radius):
        raise Problem('radius_m must be a whole number.')
    row.radius_m = int(radius)
    row.multiplier = decimal(data.get('multiplier'), 'multiplier', '1', '10')
    row.timezone, row.start_time, row.end_time = data['timezone'], data['start_time'], data['end_time']
    row.days, row.enabled = sorted(set(days)), boolean(data, 'enabled')
    db.session.add(row)
    db.session.flush()
    repo.audit(actor, 'surge_zone.updated' if zone_id else 'surge_zone.created', row.id, before, repo.serialize(row), why)
    return row

def update_share(data, actor):
    current = repo.share()
    check_version(data, current)
    driver = decimal(data.get('driver_pct'), 'driver_pct', '0', '100')
    company = decimal(data.get('company_pct'), 'company_pct', '0', '100')
    if driver + company != Decimal('100'):
        raise Problem('Driver and company percentages must total exactly 100.')
    why = reason(data)
    row = RevenueShare(driver_pct=driver, company_pct=company, updated_by=actor, version=current.version + 1)
    db.session.add(row)
    db.session.flush()
    repo.audit(actor, 'revenue_share.updated', row.id, repo.serialize(current), repo.serialize(row), why)
    return row

def money(d):
    return d.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

def settle_ride(ride_id, driver_id, eligible_fare, completed_at, currency='INR'):
    """Trusted backend hook. Call in SAME transaction as authoritative ride completion.

    Never commit here. On unique-key race caller must roll back the WHOLE transaction,
    reload the ride, and retry. The ledger is an allocation, not a payment gateway.
    """
    existing = db.session.execute(select(RevenueLedger).where(RevenueLedger.ride_id == str(ride_id))).scalar_one_or_none()
    amount = decimal(eligible_fare, 'eligible_fare')
    if not str(ride_id).strip() or not str(driver_id).strip() or currency != 'INR':
        raise Problem('Ride ID, driver ID and INR currency are required.')
    if existing:
        if existing.driver_id != str(driver_id) or existing.eligible_fare != amount or existing.currency != currency:
            raise Problem('This ride already has a different settlement.', 409)
        return existing
    if completed_at.tzinfo is None:
        raise Problem('completed_at must have a timezone.')
    setting = repo.share(completed_at.astimezone(timezone.utc).replace(tzinfo=None))
    if setting is None:
        raise Problem('No revenue setting existed at completion time.', 409)
    driver_amount = money(amount * setting.driver_pct / 100)
    row = RevenueLedger(ride_id=str(ride_id), driver_id=str(driver_id), eligible_fare=amount,
        driver_pct_snapshot=setting.driver_pct, company_pct_snapshot=setting.company_pct,
        driver_amount=driver_amount, company_amount=amount-driver_amount, currency=currency)
    db.session.add(row)
    db.session.flush()
    return row

def distance_m(lat1, lng1, lat2, lng2):
    a, b = radians(lat1), radians(lat2)
    x = sin((b-a)/2)**2 + cos(a)*cos(b)*sin(radians(lng2-lng1)/2)**2
    return 6371000 * 2 * atan2(sqrt(min(1, x)), sqrt(max(0, 1-x)))

def zone_active(zone, at):
    local = at.astimezone(ZoneInfo(zone.timezone))
    clock = local.strftime('%H:%M')
    if zone.start_time == zone.end_time:
        return local.weekday() in zone.days
    if zone.start_time < zone.end_time:
        return local.weekday() in zone.days and zone.start_time <= clock < zone.end_time
    # For overnight windows, days refer to the day on which the window STARTS.
    day = local.weekday() if clock >= zone.start_time else (local - timedelta(days=1)).weekday()
    return day in zone.days and (clock >= zone.start_time or clock < zone.end_time)

def calculate_quote(distance_meters, duration_seconds, latitude, longitude, at=None, signal_multiplier='1'):
    """Use trusted Routes API values, never a rider-supplied fare. Caller persists snapshot.

    signal_multiplier is a trusted traffic/demand policy output, not raw traffic duration.
    Highest eligible multiplier wins; never multiply overlapping zones together.
    """
    at = at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise Problem('Quote time must have a timezone.')
    distance = decimal(distance_meters, 'distance_m', hi='10000000')
    duration = decimal(duration_seconds, 'duration_seconds', hi='10000000')
    lat = number(latitude, 'latitude', -90, 90)
    lng = number(longitude, 'longitude', -180, 180)
    rules = repo.fare()
    zones = db.session.execute(select(SurgeZone).where(SurgeZone.enabled.is_(True))).scalars()
    eligible = [z for z in zones if distance_m(lat, lng, z.latitude, z.longitude) <= z.radius_m and zone_active(z, at)] if rules.surge_enabled else []
    signal = decimal(signal_multiplier, 'signal_multiplier', '1', '10') if rules.surge_enabled else Decimal(1)
    multiplier = min(rules.max_multiplier, max([Decimal(1), signal] + [z.multiplier for z in eligible]))
    distance_cost = money(distance / 1000 * rules.per_km_rate)
    duration_cost = money(duration / 60 * rules.per_minute_rate)
    subtotal = max(rules.minimum_fare, rules.base_fare + distance_cost + duration_cost)
    return {'currency': 'INR', 'base_fare': str(rules.base_fare), 'distance_amount': str(distance_cost),
        'duration_amount': str(duration_cost), 'minimum_fare': str(rules.minimum_fare), 'subtotal': str(subtotal),
        'multiplier': str(multiplier), 'total': str(money(subtotal * multiplier)), 'fare_version': rules.version,
        'zone_ids': [z.id for z in eligible], 'zone_versions': {z.id: z.version for z in eligible},
        'signal_multiplier': str(signal), 'quoted_at': at.isoformat(), 'expires_at': (at + timedelta(minutes=5)).isoformat(),
        'distance_m': str(distance), 'duration_seconds': str(duration), 'reason': 'Highest eligible multiplier, limited by global cap' if multiplier > 1 else 'Standard fare'}
