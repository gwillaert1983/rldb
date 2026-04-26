from itsdangerous import URLSafeTimedSerializer, BadSignature
from app.config import settings

_serializer = URLSafeTimedSerializer(settings.SECRET_KEY)
COOKIE_NAME = "rldb_session"
SESSION_MAX_AGE = 60 * 60 * 8  # 8 hours


def create_session_token(username: str) -> str:
    return _serializer.dumps(username, salt="session")


def verify_session_token(token: str) -> str | None:
    try:
        return _serializer.loads(token, salt="session", max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None
