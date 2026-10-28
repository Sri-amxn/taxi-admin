from functools import wraps
from flask import current_app, request, g
import jwt
from .services import Problem

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        verifier = current_app.config.get('ADMIN_AUTH_VERIFIER')
        if verifier:
            # Adapter must verify signature, expiry, issuer/audience and account status.
            claims = verifier(request)
        else:
            header = request.headers.get('Authorization', '')
            if not header.startswith('Bearer '):
                raise Problem('Authentication required.', 401)
            try:
                claims = jwt.decode(header[7:], current_app.config['JWT_SECRET'], algorithms=['HS256'],
                    issuer=current_app.config['JWT_ISSUER'], audience=current_app.config['JWT_AUDIENCE'],
                    options={'require': ['exp', 'iat', 'sub', 'role']})
            except jwt.InvalidTokenError:
                raise Problem('Invalid or expired access token.', 401)
        if not isinstance(claims, dict) or not claims.get('sub'):
            raise Problem('Invalid identity.', 401)
        if claims.get('role') != 'admin':
            raise Problem('Administrator access required.', 403)
        g.admin_id = str(claims['sub'])
        return fn(*args, **kwargs)
    return wrapper
