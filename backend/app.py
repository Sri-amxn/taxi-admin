import os
import secrets
from pathlib import Path
from datetime import datetime, timedelta, timezone
import click
import jwt
from dotenv import load_dotenv
from flask import Flask, jsonify, request, g
from flask_migrate import Migrate
from flasgger import Swagger
from admin_module import register_admin, db
from admin_module import demo
from admin_module.models import FareRules, RevenueShare
from admin_module.services import Problem

load_dotenv(Path(__file__).with_name('.env'))

def create_app(config=None):
    app = Flask(__name__)
    demo_mode = os.getenv('APP_MODE', 'demo') == 'demo'
    app.config.update(SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', 'sqlite:///' + str(Path(__file__).with_name('demo.db'))),
        SQLALCHEMY_TRACK_MODIFICATIONS=False, DEMO_MODE=demo_mode,
        JWT_SECRET=os.getenv('JWT_SECRET') or (secrets.token_hex(32) if demo_mode else ''),
        JWT_ISSUER=os.getenv('JWT_ISSUER', 'genz-taxi'), JWT_AUDIENCE=os.getenv('JWT_AUDIENCE', 'genz-taxi-api'),
        MAX_CONTENT_LENGTH=64*1024)
    if config:
        app.config.update(config)
    if not app.config['DEMO_MODE'] and (len(app.config['JWT_SECRET']) < 32 and not app.config.get('ADMIN_AUTH_VERIFIER')):
        raise RuntimeError('Integrated mode needs a JWT secret of at least 32 characters or ADMIN_AUTH_VERIFIER.')
    db.init_app(app)
    Migrate(app, db, render_as_batch=True)
    register_admin(app)
    from admin_module.swagger import specification
    Swagger(app, template=specification(), config={
        'headers': [], 'specs': [{'endpoint':'admin_spec','route':'/api/swagger.json','rule_filter':lambda rule: False}],
        'static_url_path':'/flasgger_static','swagger_ui':True,'specs_route':'/api/docs/'})
    if app.config['DEMO_MODE']:
        app.config['ADMIN_MONITOR_PROVIDER'] = demo.monitoring

    @app.get('/api/health')
    def health():
        db.session.execute(db.text('SELECT 1'))
        return jsonify(data={'status': 'ok', 'mode': 'demo' if app.config['DEMO_MODE'] else 'integrated'})

    @app.post('/api/demo/login')
    def demo_login():
        # Loopback-only development shortcut; never available in integrated mode.
        if not app.config['DEMO_MODE']:
            raise Problem('Not found.', 404)
        if request.remote_addr not in ('127.0.0.1', '::1'):
            raise Problem('Demo login is available on localhost only.', 403)
        issued = datetime.now(timezone.utc)
        token = jwt.encode({'sub': 'demo-admin', 'role': 'admin', 'iat': issued,
            'exp': issued+timedelta(hours=1), 'iss': app.config['JWT_ISSUER'], 'aud': app.config['JWT_AUDIENCE']},
            app.config['JWT_SECRET'], algorithm='HS256')
        return jsonify(data={'access_token': token, 'role': 'admin', 'name': 'Ujjwala', 'expires_in': 3600})

    @app.cli.command('init-demo')
    def init_demo():
        if not app.config['DEMO_MODE']:
            raise click.ClickException('Demo seeding is disabled outside demo mode.')
        # Schema is created by Alembic, never silently on server startup.
        demo.seed()
        click.echo('Demo data ready. Start Flask and the React frontend.')

    @app.cli.command('init-settings')
    def init_settings():
        if not db.session.get(FareRules, 1):
            db.session.add(FareRules(id=1, base_fare=40, per_km_rate=12, per_minute_rate=2, minimum_fare=60, max_multiplier=3, surge_enabled=True))
            db.session.add(RevenueShare(driver_pct=85, company_pct=15, version=1, updated_by='system'))
            db.session.commit()
        click.echo('Initial settings ready.')

    return app
