"""Persistence only; callers own commit/rollback boundaries."""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import select
from .models import db, FareRules, SurgeZone, RevenueShare, RevenueLedger, AuditLog, now

def serialize(row):
    if row is None:
        return None
    result = {}
    for c in row.__table__.columns:
        v = getattr(row, c.name)
        result[c.name] = format(v, '.2f') if isinstance(v, Decimal) else v.isoformat(timespec='milliseconds') + 'Z' if isinstance(v, datetime) else v
    return result

def fare():
    return db.session.get(FareRules, 1)

def share(at=None):
    q = select(RevenueShare).where(RevenueShare.effective_from <= (at or now()))
    return db.session.execute(q.order_by(RevenueShare.version.desc())).scalars().first()

def list_rows(model, page=1, size=25):
    order = model.created_at.desc() if hasattr(model, 'created_at') else model.id
    result = db.paginate(select(model).order_by(order), page=page, per_page=size, error_out=False)
    return {'items': [serialize(r) for r in result.items], 'page': page, 'page_size': size, 'total': result.total}

def audit(actor, action, entity_id, before, after, reason):
    db.session.add(AuditLog(admin_id=actor, action=action, entity_id=str(entity_id), before=before, after=after, reason=reason))
