import logging
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, Form, Query, Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from src.integrations.ics_service import generate_ics
from src.services.forecast_store import ForecastStore
from src.services.forecast_service import ForecastService
from src.web.auth import create_session_token, decode_session_token
from src.web.db import (
    check_password,
    create_feed_token,
    create_user,
    create_user_location,
    get_feed_token_by_user,
    get_rows_by_token,
    get_user_by_email,
    get_user_by_id,
    get_user_locations,
    wipe_accounts,
)

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "data/forecast.db")


def _initial_forecast_fetch(location: str, db_path: str, lat: float = None, lon: float = None, timezone: str = None):
    """Fetch and store 14-day forecasts for a newly registered location."""
    from src.services.forecast_formatting import format_detailed_forecast, format_summary
    from src.services.forecast_service import ForecastService
    from src.services.forecast_store import ForecastStore
    try:
        store = ForecastStore(db_path=db_path)
        forecasts = ForecastService.fetch_forecasts(location=location, forecast_days=14, lat=lat, lon=lon, timezone=timezone)
        for f in forecasts:
            f.summary = format_summary(f)
            f.description = format_detailed_forecast(f)
            store.upsert_forecast(f)
        logger.info("Initial forecast fetch complete for location=%s", location)
    except Exception:
        logger.exception("Initial forecast fetch failed for location=%s", location)

app = FastAPI()
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

ForecastStore(db_path=DB_PATH)  # ensures all tables exist before anything else runs
if os.getenv("WIPE_ACCOUNTS_ON_START"):
    wipe_accounts(DB_PATH)


def _get_user_id(request: Request):
    token = request.cookies.get("session")
    if not token:
        return None
    return decode_session_token(token)


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})


@app.get("/signup", response_class=HTMLResponse)
async def signup_get(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "error": None})


@app.post("/signup")
async def signup_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    if len(password) < 12:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": "Password must be at least 12 characters."},
            status_code=422,
        )

    try:
        user_id = create_user(DB_PATH, email, password)
    except sqlite3.IntegrityError:
        return templates.TemplateResponse(
            "signup.html",
            {"request": request, "error": "An account with that email already exists."},
            status_code=422,
        )

    create_feed_token(DB_PATH, user_id)

    session_token = create_session_token(user_id)
    response = RedirectResponse(url="/setup", status_code=303)
    response.set_cookie("session", session_token, httponly=True, samesite="lax")
    return response


@app.get("/setup", response_class=HTMLResponse)
async def setup_get(request: Request):
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("setup.html", {"request": request, "error": None})


@app.post("/setup")
async def setup_post(
    request: Request,
    background_tasks: BackgroundTasks,
    location: str = Form(...),
    lat: str = Form(default=""),
    lon: str = Form(default=""),
    timezone: str = Form(default=""),
):
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    if lat and lon and timezone:
        resolved_lat, resolved_lon, resolved_tz = float(lat), float(lon), timezone
    else:
        try:
            resolved_lat, resolved_lon, resolved_tz = ForecastService.get_coordinates_with_timezone(location)
        except Exception:
            return templates.TemplateResponse(
                "setup.html",
                {"request": request, "error": "We couldn't find that location. Please try a different city name."},
                status_code=422,
            )

    create_user_location(DB_PATH, user_id, location, resolved_lat, resolved_lon, resolved_tz)
    background_tasks.add_task(_initial_forecast_fetch, location, DB_PATH, resolved_lat, resolved_lon, resolved_tz)
    return RedirectResponse(url="/dashboard", status_code=303)


@app.get("/geocode")
async def geocode(q: str = Query(default="", min_length=0)):
    if len(q) < 3:
        return JSONResponse([])
    try:
        import requests as _requests
        resp = _requests.get(
            ForecastService.GEOCODE_URL,
            params={"name": q, "count": 8, "language": "en", "format": "json"},
            timeout=(5, 10),
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return JSONResponse([
            {
                "name": r.get("name", ""),
                "country": r.get("country", ""),
                "admin1": r.get("admin1", ""),
                "lat": r["latitude"],
                "lon": r["longitude"],
                "timezone": r.get("timezone", "UTC"),
            }
            for r in results
        ])
    except Exception:
        return JSONResponse([])


@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    user = get_user_by_email(DB_PATH, email)
    if not user or not check_password(password, user["password_hash"]):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid email or password."},
            status_code=401,
        )

    session_token = create_session_token(user["id"])
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie("session", session_token, httponly=True, samesite="lax")
    return response


@app.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    user = get_user_by_id(DB_PATH, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    feed_token = get_feed_token_by_user(DB_PATH, user_id)
    locations = get_user_locations(DB_PATH, user_id)

    webcal_url = None
    google_cal_url = None
    if feed_token:
        base_url = str(request.base_url).rstrip("/")
        feed_path = f"/feed/{feed_token}/weather.ics"
        webcal_url = base_url.replace("https://", "webcal://").replace("http://", "webcal://") + feed_path
        https_url = base_url + feed_path
        google_cal_url = f"https://calendar.google.com/calendar/r?cid={quote(webcal_url, safe='')}"

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "feed_token": feed_token,
            "webcal_url": webcal_url,
            "google_cal_url": google_cal_url,
            "locations": locations,
        },
    )


@app.get("/feed/{token}/weather.ics")
async def feed(token: str):
    rows = get_rows_by_token(DB_PATH, token)
    if not rows:
        return Response(content="Invalid or expired token.", status_code=404)

    locations = list({row["location"] for row in rows})
    store = ForecastStore(db_path=DB_PATH)
    forecasts = store.get_forecasts_for_locations(locations, days=14)

    location_name = locations[0] if locations else "Unknown"
    ics_content = generate_ics(forecasts, location_name)

    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="weather.ics"'},
    )
