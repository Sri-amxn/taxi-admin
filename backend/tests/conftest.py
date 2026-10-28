import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from app import create_app
from admin_module.models import db
from admin_module.demo import seed

@pytest.fixture
def app():
    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://', 'DEMO_MODE': True,
        'JWT_SECRET': 'test-secret-that-is-long-enough-for-hmac'})
    with app.app_context():
        db.create_all()
        seed()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def headers(client):
    token = client.post('/api/demo/login').json['data']['access_token']
    return {'Authorization': f'Bearer {token}'}
