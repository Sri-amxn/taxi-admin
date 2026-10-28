from datetime import datetime, timezone, timedelta
from decimal import Decimal
import jwt
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
from admin_module.models import db, RevenueLedger, FareRules
from admin_module.services import settle_ride, calculate_quote, zone_active, save_zone, Problem

def get(client, headers, path):
    response = client.get('/api/admin/'+path, headers=headers)
    assert response.status_code == 200
    return response.json['data']

def test_missing_and_invalid_auth(client):
    for h in ({}, {'Authorization':'Bearer nonsense'}):
        assert client.get('/api/admin/dashboard', headers=h).status_code == 401

@pytest.mark.parametrize('role,delta,status', [('rider',60,403),('admin',-60,401),('driver',60,403)])
def test_auth_roles_expiry(app,client,role,delta,status):
    token=jwt.encode({'sub':'u1','role':role,'iat':datetime.now(timezone.utc)-timedelta(minutes=5),
        'exp':datetime.now(timezone.utc)+timedelta(seconds=delta),'iss':'genz-taxi','aud':'genz-taxi-api'},app.config['JWT_SECRET'],algorithm='HS256')
    assert client.get('/api/admin/fare-rules',headers={'Authorization':'Bearer '+token}).status_code==status

def test_demo_disabled_in_integrated_mode(app,client):
    app.config['DEMO_MODE']=False
    assert client.post('/api/demo/login').status_code==404

def test_demo_not_available_over_lan(client):
    assert client.post('/api/demo/login',environ_base={'REMOTE_ADDR':'192.168.1.12'}).status_code==403

def test_dashboard_stale_drivers_and_totals(client,headers):
    data=get(client,headers,'dashboard')
    assert data['available_drivers']==1 and data['stale_drivers']==1
    assert Decimal(data['driver_allocations'])==Decimal('1092.25')
    assert len(get(client,headers,'drivers'))==4

def test_unconnected_live_feed_is_explicit(app,client,headers):
    app.config['ADMIN_MONITOR_PROVIDER']=None
    assert client.get('/api/admin/dashboard',headers=headers).status_code==503

@pytest.mark.parametrize('driver,company', [('90','20'),('-1','101'),('NaN','15'),('85.001','14.999'),('Infinity','0')])
def test_bad_revenue_rejected(client,headers,driver,company):
    share=get(client,headers,'revenue-share')
    result=client.put('/api/admin/revenue-share',headers=headers,json={**share,'driver_pct':driver,'company_pct':company,'reason':'Invalid test'})
    assert result.status_code==400
    assert get(client,headers,'revenue-share')['version']==1

def test_revenue_version_audit_and_history(client,headers):
    share=get(client,headers,'revenue-share')
    payload={**share,'driver_pct':'90','company_pct':'10','reason':'Update commercial agreement'}
    assert client.put('/api/admin/revenue-share',headers=headers,json=payload).status_code==200
    assert client.put('/api/admin/revenue-share',headers=headers,json=payload).status_code==409
    assert all(r['driver_pct_snapshot']=='85.00' for r in get(client,headers,'ledger')['items'])
    audit=get(client,headers,'audit')['items'][0]
    assert audit['before']['driver_pct']=='85.00' and audit['after']['driver_pct']=='90.00'

def test_fare_update_conflict_and_invalid_boolean(client,headers):
    fare=get(client,headers,'fare-rules')
    payload={**fare,'base_fare':'50','reason':'New base fare policy'}
    assert client.put('/api/admin/fare-rules',headers=headers,json=payload).status_code==200
    assert client.put('/api/admin/fare-rules',headers=headers,json=payload).status_code==409
    payload={**get(client,headers,'fare-rules'),'surge_enabled':'false','reason':'Invalid boolean'}
    assert client.put('/api/admin/fare-rules',headers=headers,json=payload).status_code==400

def test_bad_write_has_no_audit_or_changes(client,headers):
    before=get(client,headers,'audit')['total']
    fare=get(client,headers,'fare-rules')
    assert client.put('/api/admin/fare-rules',headers=headers,json={**fare,'base_fare':'999','reason':''}).status_code==400
    assert get(client,headers,'fare-rules')['base_fare']=='40.00'
    assert get(client,headers,'audit')['total']==before

def test_sqlalchemy_optimistic_locking(app):
    with app.app_context():
        with Session(db.engine) as one, Session(db.engine) as two:
            a,b=one.get(FareRules,1),two.get(FareRules,1)
            a.base_fare=50
            one.commit()
            b.base_fare=60
            with pytest.raises(StaleDataError):
                two.commit()

def test_settlement_idempotency_rounding_and_rollback(app):
    with app.app_context():
        at=datetime.now(timezone.utc)
        row=settle_ride('TEST-1','D1','0.10',at)
        assert row.driver_amount==Decimal('0.09') and row.company_amount==Decimal('0.01')
        assert settle_ride('TEST-1','D1','0.10',at).id==row.id
        with pytest.raises(Problem):
            settle_ride('TEST-1','D1','5',at)
        db.session.rollback()
        assert db.session.execute(select(RevenueLedger).where(RevenueLedger.ride_id=='TEST-1')).scalar_one_or_none() is None

def test_settlement_uses_setting_at_completion(app,client,headers):
    old_time=datetime.now(timezone.utc)-timedelta(seconds=1)
    share=get(client,headers,'revenue-share')
    client.put('/api/admin/revenue-share',headers=headers,json={**share,'driver_pct':'100','company_pct':'0','reason':'Change for next completions'})
    with app.app_context():
        assert settle_ride('LATE','D1','500',old_time).driver_amount==Decimal('425')
        assert settle_ride('CURRENT','D1','500',datetime.now(timezone.utc)).driver_amount==Decimal('500')

def zone_payload(**changes):
    return {'name':'Test peak','latitude':28.6139,'longitude':77.209,'radius_m':4000,
        'multiplier':'2','timezone':'Asia/Kolkata','start_time':'17:00','end_time':'21:00',
        'days':[0,1,2,3,4,5,6],'enabled':True,'reason':'Zone test creation',**changes}

def test_zone_crud_validation(client,headers):
    result=client.post('/api/admin/surge-zones',headers=headers,json=zone_payload())
    assert result.status_code==200
    zone=result.json['data']
    assert client.put('/api/admin/surge-zones/'+zone['id'],headers=headers,json={**zone,'enabled':False,'reason':'Pause peak period'}).status_code==200
    assert client.put('/api/admin/surge-zones/'+zone['id'],headers=headers,json={**zone,'reason':'Stale edit'}).status_code==409
    assert client.post('/api/admin/surge-zones',headers=headers,json=zone_payload(latitude=91)).status_code==400
    assert client.post('/api/admin/surge-zones',headers=headers,json=zone_payload(timezone='Mars/City')).status_code==400

def test_quote_overlap_cap_disable_and_snapshot(app):
    with app.app_context():
        at=datetime(2026,10,28,12,30,tzinfo=timezone.utc)
        save_zone(zone_payload(multiplier='4'),'admin')
        db.session.flush()
        quote=calculate_quote('5000','900',28.6139,77.209,at)
        assert Decimal(quote['multiplier'])==3 and Decimal(quote['total'])==390
        assert len(quote['zone_ids'])==2
        db.session.get(FareRules,1).surge_enabled=False
        assert Decimal(calculate_quote(5000,900,28.6139,77.209,at)['total'])==130
        assert Decimal(quote['total'])==390
        assert Decimal(calculate_quote(0,0,0,0,at)['total'])==60

def test_schedule_boundaries_overnight(app):
    with app.app_context():
        z=save_zone(zone_payload(start_time='22:00',end_time='02:00',days=[0],timezone='UTC'),'admin')
        assert zone_active(z,datetime(2026,10,26,22,0,tzinfo=timezone.utc))
        assert zone_active(z,datetime(2026,10,27,1,59,tzinfo=timezone.utc))
        assert not zone_active(z,datetime(2026,10,27,2,0,tzinfo=timezone.utc))
        assert not zone_active(z,datetime(2026,10,27,22,0,tzinfo=timezone.utc))

@pytest.mark.parametrize('path',['/api/admin/audit?page=0','/api/admin/ledger?page_size=101'])
def test_pagination_invalid(client,headers,path):
    assert client.get(path,headers=headers).status_code==400

def test_unknown_route_and_non_json_payload(client,headers):
    assert client.get('/api/not-a-route').status_code==404
    assert client.put('/api/admin/fare-rules',headers=headers,data='bad').status_code==400

def test_preview_endpoint(client,headers):
    result=client.post('/api/admin/quote-preview',headers=headers,json={'distance_m':5000,'duration_seconds':900,'latitude':0,'longitude':0})
    assert result.status_code==200 and Decimal(result.json['data']['total'])==130

def test_db_sql_server_ddl_compiles(app):
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects import mssql
    with app.app_context():
        for table in db.metadata.sorted_tables:
            assert 'CREATE TABLE' in str(CreateTable(table).compile(dialect=mssql.dialect()))
