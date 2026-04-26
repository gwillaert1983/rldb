from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.auth import COOKIE_NAME, verify_session_token
from app.database import SessionLocal


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_login(request: Request) -> str:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return RedirectResponse("/login", status_code=303)
    username = verify_session_token(token)
    if not username:
        return RedirectResponse("/login", status_code=303)
    return username
