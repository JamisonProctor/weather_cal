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
    DEFAULT_PREFS,
    check_password,
    create_feed_token,
    create_feedback_table,
    create_user,
    create_user_location,
    create_user_preferences_table,
    delete_user_account,
    get_feed_token_by_user,
    get_last_forecast_update,
    get_rows_by_token,
    get_user_by_email,
    get_user_by_id,
    get_user_locations,
    get_user_preferences,
    save_feedback,
    update_user_email,
    update_user_password,
    upsert_user_preferences,
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
create_feedback_table(DB_PATH)
create_user_preferences_table(DB_PATH)
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

    existing_locations = get_user_locations(DB_PATH, user_id)
    is_location_change = len(existing_locations) > 0

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
    redirect_url = "/settings" if is_location_change else "/connect"
    return RedirectResponse(url=redirect_url, status_code=303)


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
    response = RedirectResponse(url="/settings", status_code=303)
    response.set_cookie("session", session_token, httponly=True, samesite="lax")
    return response


@app.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session")
    return response


@app.get("/dashboard")
async def dashboard():
    return RedirectResponse(url="/settings", status_code=301)


def _build_feed_urls(request: Request, feed_token: str):
    base_url = str(request.base_url).rstrip("/")
    feed_path = f"/feed/{feed_token}/weather.ics"
    webcal_url = base_url.replace("https://", "webcal://").replace("http://", "webcal://") + feed_path
    google_cal_url = f"https://calendar.google.com/calendar/r?cid={quote(webcal_url, safe='')}"
    return webcal_url, google_cal_url


@app.get("/connect", response_class=HTMLResponse)
async def connect(request: Request):
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    feed_token = get_feed_token_by_user(DB_PATH, user_id)
    webcal_url, google_cal_url = _build_feed_urls(request, feed_token) if feed_token else (None, None)

    return templates.TemplateResponse(
        "connect.html",
        {
            "request": request,
            "webcal_url": webcal_url,
            "google_cal_url": google_cal_url,
        },
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request, success: str = Query(default=""), error: str = Query(default="")):
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    user = get_user_by_id(DB_PATH, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    feed_token = get_feed_token_by_user(DB_PATH, user_id)
    locations = get_user_locations(DB_PATH, user_id)
    webcal_url, google_cal_url = _build_feed_urls(request, feed_token) if feed_token else (None, None)
    prefs_row = get_user_preferences(DB_PATH, user_id)
    prefs = dict(prefs_row) if prefs_row else DEFAULT_PREFS

    location_names = [loc["location"] for loc in locations]
    last_updated_raw = get_last_forecast_update(DB_PATH, location_names)
    if last_updated_raw:
        from datetime import datetime as _dt
        try:
            last_updated = _dt.fromisoformat(last_updated_raw).strftime("%-d %b %Y, %H:%M UTC")
        except Exception:
            last_updated = last_updated_raw
    else:
        last_updated = None

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "user": user,
            "feed_token": feed_token,
            "webcal_url": webcal_url,
            "google_cal_url": google_cal_url,
            "locations": locations,
            "prefs": prefs,
            "success": success,
            "error": error,
            "last_updated": last_updated,
        },
    )


@app.post("/settings")
async def settings_post(
    request: Request,
    cold_threshold: float = Form(default=3.0),
    warn_in_allday: str = Form(default=""),
    warn_rain: str = Form(default=""),
    warn_wind: str = Form(default=""),
    warn_cold: str = Form(default=""),
    warn_snow: str = Form(default=""),
    warn_sunny: str = Form(default=""),
    show_allday_events: str = Form(default=""),
    timed_events_enabled: str = Form(default=""),
    allday_rain: str = Form(default=""),
    allday_wind: str = Form(default=""),
    allday_cold: str = Form(default=""),
    allday_snow: str = Form(default=""),
    allday_sunny: str = Form(default=""),
    warm_threshold: float = Form(default=14.0),
    hot_threshold: float = Form(default=28.0),
    allday_hot: str = Form(default=""),
    warn_hot: str = Form(default=""),
):
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    upsert_user_preferences(
        DB_PATH,
        user_id,
        cold_threshold=cold_threshold,
        warn_in_allday=1 if warn_in_allday == "on" else 0,
        warn_rain=1 if warn_rain == "on" else 0,
        warn_wind=1 if warn_wind == "on" else 0,
        warn_cold=1 if warn_cold == "on" else 0,
        warn_snow=1 if warn_snow == "on" else 0,
        warn_sunny=1 if warn_sunny == "on" else 0,
        show_allday_events=1 if show_allday_events == "on" else 0,
        timed_events_enabled=1 if timed_events_enabled == "on" else 0,
        allday_rain=1 if allday_rain == "on" else 0,
        allday_wind=1 if allday_wind == "on" else 0,
        allday_cold=1 if allday_cold == "on" else 0,
        allday_snow=1 if allday_snow == "on" else 0,
        allday_sunny=1 if allday_sunny == "on" else 0,
        warm_threshold=warm_threshold,
        hot_threshold=hot_threshold,
        allday_hot=1 if allday_hot == "on" else 0,
        warn_hot=1 if warn_hot == "on" else 0,
    )
    return RedirectResponse(url="/settings?success=prefs", status_code=303)


@app.post("/settings/email")
async def settings_email_post(
    request: Request,
    new_email: str = Form(...),
    current_password: str = Form(...),
):
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    user = get_user_by_id(DB_PATH, user_id)
    if not user or not check_password(current_password, user["password_hash"]):
        return RedirectResponse(url="/settings?error=wrong_password", status_code=303)

    try:
        update_user_email(DB_PATH, user_id, new_email)
    except sqlite3.IntegrityError:
        return RedirectResponse(url="/settings?error=email_taken", status_code=303)

    return RedirectResponse(url="/settings?success=email", status_code=303)


@app.post("/settings/password")
async def settings_password_post(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
):
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    user = get_user_by_id(DB_PATH, user_id)
    if not user or not check_password(current_password, user["password_hash"]):
        return RedirectResponse(url="/settings?error=wrong_password", status_code=303)

    if len(new_password) < 12:
        return RedirectResponse(url="/settings?error=password_too_short", status_code=303)

    update_user_password(DB_PATH, user_id, new_password)
    return RedirectResponse(url="/settings?success=password", status_code=303)


@app.post("/settings/delete")
async def settings_delete_post(
    request: Request,
    confirm_email: str = Form(...),
):
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    user = get_user_by_id(DB_PATH, user_id)
    if not user or confirm_email.strip().lower() != user["email"].lower():
        return RedirectResponse(url="/settings?error=email_mismatch", status_code=303)

    delete_user_account(DB_PATH, user_id)
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("session")
    return response


@app.post("/settings/feedback")
async def settings_feedback_post(
    request: Request,
    topic: str = Form(default=""),
    description: str = Form(default=""),
    user_agent: str = Form(default=""),
    platform: str = Form(default=""),
    screen_width: str = Form(default=""),
    screen_height: str = Form(default=""),
    timezone: str = Form(default=""),
):
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    user = get_user_by_id(DB_PATH, user_id)
    email = user["email"] if user else ""
    feed_token = get_feed_token_by_user(DB_PATH, user_id)
    webcal_url, _ = _build_feed_urls(request, feed_token) if feed_token else (None, None)
    locations = get_user_locations(DB_PATH, user_id)
    locations_str = ", ".join(loc["location"] for loc in locations)

    save_feedback(
        DB_PATH, user_id, email,
        feed_url=webcal_url or "",
        locations=locations_str,
        calendar_app=topic,
        description=description,
        user_agent=user_agent,
        platform=platform,
        screen_width=screen_width,
        screen_height=screen_height,
        timezone=timezone,
    )
    return RedirectResponse(url="/settings?success=feedback#feedback", status_code=303)


@app.get("/feedback", response_class=HTMLResponse)
async def feedback_get(request: Request):
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    feed_token = get_feed_token_by_user(DB_PATH, user_id)
    locations = get_user_locations(DB_PATH, user_id)
    webcal_url, _ = _build_feed_urls(request, feed_token) if feed_token else (None, None)

    return templates.TemplateResponse(
        "feedback.html",
        {"request": request, "webcal_url": webcal_url, "locations": locations, "sent": False},
    )


@app.post("/feedback", response_class=HTMLResponse)
async def feedback_post(
    request: Request,
    calendar_app: str = Form(default=""),
    description: str = Form(default=""),
    user_agent: str = Form(default=""),
    platform: str = Form(default=""),
    screen_width: str = Form(default=""),
    screen_height: str = Form(default=""),
    timezone: str = Form(default=""),
    feed_url: str = Form(default=""),
    locations: str = Form(default=""),
):
    user_id = _get_user_id(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    user = get_user_by_id(DB_PATH, user_id)
    email = user["email"] if user else ""

    save_feedback(
        DB_PATH, user_id, email, feed_url, locations,
        calendar_app, description, user_agent, platform,
        screen_width, screen_height, timezone,
    )

    user_locations = get_user_locations(DB_PATH, user_id)
    feed_token = get_feed_token_by_user(DB_PATH, user_id)
    webcal_url, _ = _build_feed_urls(request, feed_token) if feed_token else (None, None)

    return templates.TemplateResponse(
        "feedback.html",
        {"request": request, "webcal_url": webcal_url, "locations": user_locations, "sent": True},
    )


@app.get("/feed/{token}/weather.ics")
async def feed(request: Request, token: str):
    rows = get_rows_by_token(DB_PATH, token)
    if not rows:
        return Response(content="Invalid or expired token.", status_code=404)

    user_id = rows[0]["id"]
    locations = list({row["location"] for row in rows})
    store = ForecastStore(db_path=DB_PATH)
    forecasts = store.get_forecasts_for_locations(locations, days=14)

    location_name = locations[0] if locations else "Unknown"
    prefs_row = get_user_preferences(DB_PATH, user_id)
    prefs = dict(prefs_row) if prefs_row else DEFAULT_PREFS
    settings_url = str(request.base_url).rstrip("/") + "/settings"
    ics_content = generate_ics(forecasts, location_name, prefs=prefs, settings_url=settings_url)

    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="weather.ics"'},
    )
