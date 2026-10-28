"""Only admin-owned tables. Never define teammates' USERS, RIDES or DRIVERS here."""
from datetime import datetime, timezone
from uuid import uuid4
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def uid():
    return str(uuid4())

class FareRules(db.Model):
    __tablename__ = 'admin_fare_rules'
    id = db.Column(db.Integer, primary_key=True)
    base_fare = db.Column(db.Numeric(12, 2), nullable=False)
    per_km_rate = db.Column(db.Numeric(12, 2), nullable=False)
    per_minute_rate = db.Column(db.Numeric(12, 2), nullable=False)
    minimum_fare = db.Column(db.Numeric(12, 2), nullable=False)
    max_multiplier = db.Column(db.Numeric(5, 2), nullable=False)
    surge_enabled = db.Column(db.Boolean, nullable=False, default=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}

class SurgeZone(db.Model):
    __tablename__ = 'admin_surge_zones'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    name = db.Column(db.String(100), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    radius_m = db.Column(db.Integer, nullable=False)
    multiplier = db.Column(db.Numeric(5, 2), nullable=False)
    timezone = db.Column(db.String(60), nullable=False)
    start_time = db.Column(db.String(5), nullable=False)
    end_time = db.Column(db.String(5), nullable=False)
    days = db.Column(db.JSON, nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}

class RevenueShare(db.Model):
    __tablename__ = 'admin_revenue_share_settings'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    driver_pct = db.Column(db.Numeric(5, 2), nullable=False)
    company_pct = db.Column(db.Numeric(5, 2), nullable=False)
    effective_from = db.Column(db.DateTime, nullable=False, default=now)
    updated_by = db.Column(db.String(100), nullable=False)
    version = db.Column(db.Integer, nullable=False, unique=True)
    __table_args__ = (db.CheckConstraint('driver_pct >= 0 AND driver_pct <= 100 AND company_pct >= 0 AND company_pct <= 100 AND ROUND(driver_pct + company_pct, 2) = 100', name='ck_admin_share_total'),)

class RevenueLedger(db.Model):
    __tablename__ = 'admin_revenue_ledger'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    ride_id = db.Column(db.String(100), nullable=False, unique=True)
    driver_id = db.Column(db.String(100), nullable=False)
    eligible_fare = db.Column(db.Numeric(12, 2), nullable=False)
    driver_pct_snapshot = db.Column(db.Numeric(5, 2), nullable=False)
    company_pct_snapshot = db.Column(db.Numeric(5, 2), nullable=False)
    driver_amount = db.Column(db.Numeric(12, 2), nullable=False)
    company_amount = db.Column(db.Numeric(12, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='INR')
    settlement_status = db.Column(db.String(30), nullable=False, default='recorded')
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    __table_args__ = (db.CheckConstraint('eligible_fare >= 0 AND driver_amount >= 0 AND company_amount >= 0 AND ROUND(driver_amount + company_amount, 2) = ROUND(eligible_fare, 2)', name='ck_admin_ledger_balance'),)

class AuditLog(db.Model):
    __tablename__ = 'admin_audit_log'
    id = db.Column(db.String(36), primary_key=True, default=uid)
    admin_id = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(60), nullable=False)
    entity_id = db.Column(db.String(100), nullable=False)
    before = db.Column(db.JSON, nullable=True)
    after = db.Column(db.JSON, nullable=True)
    reason = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now, index=True)
