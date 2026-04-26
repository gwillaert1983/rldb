import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import COOKIE_NAME, SESSION_MAX_AGE, create_session_token
from app.config import settings
from app.templates_config import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@router.post("/login")
async def login_submit(
    username: str = Form(...),
    password: str = Form(...),
):
    valid = secrets.compare_digest(username, settings.DASHBOARD_USERNAME) and \
            secrets.compare_digest(password, settings.DASHBOARD_PASSWORD)
    if not valid:
        return RedirectResponse("/login?error=1", status_code=303)
    token = create_session_token(username)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_MAX_AGE,
    )
    return resp


@router.post("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp
