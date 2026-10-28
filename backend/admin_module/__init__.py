"""Mountable Flask module. See docs/INTEGRATION.md before merging."""
from uuid import uuid4
from flask import g, jsonify
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from werkzeug.exceptions import HTTPException
from .models import db
from .routes import bp
from .services import Problem

def register_admin(app):
    """Register after initializing THIS db instance with the shared Flask app."""
    app.register_blueprint(bp)

    @app.before_request
    def request_id():
        g.request_id = str(uuid4())

    @app.after_request
    def headers(response):
        response.headers['X-Request-ID'] = getattr(g, 'request_id', '')
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.errorhandler(Problem)
    def problem(error):
        db.session.rollback()
        return jsonify(error={'code': 'REQUEST_FAILED', 'message': error.message}, request_id=getattr(g, 'request_id', '')), error.status

    @app.errorhandler(StaleDataError)
    @app.errorhandler(IntegrityError)
    def conflict(error):
        return problem(Problem('A concurrent change conflicted. Reload and retry.', 409))

    @app.errorhandler(HTTPException)
    def http_error(error):
        return problem(Problem(error.description, error.code))

    @app.errorhandler(Exception)
    def unexpected(error):
        app.logger.exception('Request failed: %s', getattr(g, 'request_id', ''))
        return problem(Problem('Internal server error. Use the request ID for support.', 500))
