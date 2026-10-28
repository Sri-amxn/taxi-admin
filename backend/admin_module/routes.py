from datetime import datetime, timezone
from uuid import uuid4
from flask import Blueprint, jsonify, request, current_app, g
from sqlalchemy import select
from .auth import admin_required
from .models import db, SurgeZone, AuditLog, RevenueLedger
from . import repository as repo, services

bp = Blueprint('admin_module', __name__, url_prefix='/api/admin')

def payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise services.Problem('Request body must be a JSON object.')
    return data

def response(data, status=200):
    return jsonify({'data': data, 'request_id': g.request_id}), status

def write(fn, *args):
    row = fn(*args)
    db.session.commit()
    return response(repo.serialize(row))

@bp.get('/fare-rules')
@admin_required
def get_fare():
    return response(repo.serialize(repo.fare()))

@bp.put('/fare-rules')
@admin_required
def put_fare():
    return write(services.update_fare, payload(), g.admin_id)

@bp.get('/surge-zones')
@admin_required
def zones():
    return response([repo.serialize(z) for z in db.session.execute(select(SurgeZone).order_by(SurgeZone.name)).scalars()])

@bp.post('/surge-zones')
@admin_required
def post_zone():
    return write(services.save_zone, payload(), g.admin_id)

@bp.put('/surge-zones/<zone_id>')
@admin_required
def put_zone(zone_id):
    return write(services.save_zone, payload(), g.admin_id, zone_id)

@bp.get('/revenue-share')
@admin_required
def get_share():
    return response(repo.serialize(repo.share()))

@bp.put('/revenue-share')
@admin_required
def put_share():
    return write(services.update_share, payload(), g.admin_id)

def page_args():
    try:
        page, size = int(request.args.get('page', 1)), int(request.args.get('page_size', 25))
        if page < 1 or not 1 <= size <= 100:
            raise ValueError()
        return page, size
    except ValueError:
        raise services.Problem('Use page >= 1 and page_size between 1 and 100.')

@bp.get('/audit')
@admin_required
def audit():
    return response(repo.list_rows(AuditLog, *page_args()))

@bp.get('/ledger')
@admin_required
def ledger():
    return response(repo.list_rows(RevenueLedger, *page_args()))

def monitoring():
    provider = current_app.config.get('ADMIN_MONITOR_PROVIDER')
    if provider is None:
        raise services.Problem('Live ride/driver provider has not been connected.', 503)
    data = provider()
    now = datetime.now(timezone.utc)
    drivers = []
    for item in data['drivers']:
        driver = dict(item)
        stamp = driver.get('location_updated_at')
        try:
            timestamp = datetime.fromisoformat(stamp.replace('Z', '+00:00')) if stamp else None
            age = (now-timestamp).total_seconds() if timestamp else None
            driver['location_stale'] = age is None or age < -30 or age > 90
        except (ValueError, TypeError):
            driver['location_stale'] = True
        drivers.append(driver)
    return {**data, 'drivers': drivers}

@bp.get('/drivers')
@admin_required
def drivers():
    return response(monitoring()['drivers'])

@bp.get('/rides')
@admin_required
def rides():
    return response(monitoring()['rides'])

@bp.get('/dashboard')
@admin_required
def dashboard():
    data = monitoring()
    # Ledger totals are allocations recorded by this module, not cash receipts.
    driver_total, company_total = db.session.execute(select(
        db.func.coalesce(db.func.sum(RevenueLedger.driver_amount), 0),
        db.func.coalesce(db.func.sum(RevenueLedger.company_amount), 0))).one()
    return response({'source': data['source'], 'as_of': data['as_of'], 'driver_count': len(data['drivers']),
        'available_drivers': sum(d['status'] == 'available' and not d['location_stale'] and not d.get('active_ride_id') for d in data['drivers']),
        'stale_drivers': sum(d['location_stale'] and d['status'] != 'offline' for d in data['drivers']),
        'active_rides': sum(r['status'] not in ['COMPLETED', 'CANCELLED', 'NO_DRIVER_FOUND'] for r in data['rides']),
        'driver_allocations': str(driver_total), 'company_allocations': str(company_total),
        'recent_rides': data['rides'][:8]})

@bp.post('/quote-preview')
@admin_required
def preview():
    data = payload()
    return response(services.calculate_quote(data.get('distance_m'), data.get('duration_seconds'), data.get('latitude'), data.get('longitude')))
