import logging
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, Form, Query, Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from src.integrations.google_push import (
    create_google_tokens_table,
    google_oauth_enabled,
    get_oauth_flow,
    store_google_tokens,
    create_weathercal_calendar,
    build_google_service,
    delete_google_tokens,
    is_google_connected,
    push_events_for_user,
)
from src.integrations.ics_service import generate_ics
from src.services.email_service import send_welcome_email
from src.services.forecast_store import ForecastStore
from src.services.forecast_service import ForecastService
from jose import jwt
from src.web.auth import create_session_token, decode_session_token, SECRET_KEY
from src.events.db import create_event_tables, get_future_events, get_user_id_by_feed_token
from src.events.ics_events import build_event_ics
from src.constants import DEFAULT_PREFS
from src.web.db import (
    check_password,
    resolve_prefs,
    create_feed_token,
    create_feedback_table,
    create_user,
    set_user_location,
    create_user_preferences_table,
    delete_user_account,
    export_user_data,
    get_admin_stats,
    get_feedback,
    get_feed_token_by_user,
    get_last_forecast_update,
    get_rows_by_token,
    get_user_by_email,
    get_user_by_id,
    get_user_locations,
    get_user_preferences,
    increment_settings_clicks,
    log_feed_poll,
    save_feedback,
    update_feed_poll,
    update_user_email,
    update_user_password,
    upsert_user_preferences,
)

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "data/forecast.db")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")


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

MAINTENANCE_FLAG = Path(os.getenv("DB_PATH", "data/forecast.db")).parent / "maintenance.flag"
MAINTENANCE_PAGE = Path(__file__).resolve().parent.parent.parent / "maintenance.html"

app = FastAPI()
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.middleware("http")
async def maintenance_mode(request: Request, call_next):
    if MAINTENANCE_FLAG.exists():
        try:
            content = MAINTENANCE_PAGE.read_text()
        except FileNotFoundError:
            content = "<h1>Under maintenance</h1><p>We'll be back shortly.</p>"
        return HTMLResponse(content=content, status_code=503)
    return await call_next(request)

ForecastStore(db_path=DB_PATH)  # ensures all tables exist before anything else runs
create_feedback_table(DB_PATH)
create_user_preferences_table(DB_PATH)
create_event_tables(DB_PATH)
create_google_tokens_table(DB_PATH)


def _get_user_id(request: Request):
    token = request.cookies.get("session")
    if not token:
        return None
    return decode_session_token(token)


class _LoginRequired(Exception):
    """Sentinel exception used by _require_login to trigger a redirect."""
    pass


@app.exception_handler(_LoginRequired)
async def _handle_login_required(request: Request, exc: _LoginRequired):
    return RedirectResponse(url="/login", status_code=303)


def _require_login(request: Request) -> int:
    """Return user_id or raise _LoginRequired to redirect to /login."""
    user_id = _get_user_id(request)
    if not user_id:
        raise _LoginRequired()
    return user_id


def _convert_thresholds_to_celsius(cold: float, warm: float, hot: float) -> tuple[float, float, float]:
    """Convert Fahrenheit threshold values to Celsius."""
    return (cold - 32) * 5 / 9, (warm - 32) * 5 / 9, (hot - 32) * 5 / 9


def _is_admin(user_id: int) -> bool:
    if not ADMIN_EMAIL:
        return False
    user = get_user_by_id(DB_PATH, user_id)
    return bool(user and user["email"] == ADMIN_EMAIL)


def _template(name: str, request: Request, ctx: dict | None = None, **kwargs):
    base = {"request": request, "is_authenticated": bool(_get_user_id(request))}
    if ctx:
        base.update(ctx)
    return templates.TemplateResponse(name, base, **kwargs)


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return _template("landing.html", request)


@app.get("/signup", response_class=HTMLResponse)
async def signup_get(request: Request):
    return _template("signup.html", request, {"error": None})


@app.post("/signup")
async def signup_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    if len(password) < 12:
        return _template(
            "signup.html", request,
            {"error": "Password must be at least 12 characters."},
            status_code=422,
        )

    try:
        user_id = create_user(DB_PATH, email, password)
    except sqlite3.IntegrityError:
        return _template(
            "signup.html", request,
            {"error": "An account with that email already exists."},
            status_code=422,
        )

    create_feed_token(DB_PATH, user_id)

    session_token = create_session_token(user_id)
    response = RedirectResponse(url="/setup", status_code=303)
    response.set_cookie("session", session_token, httponly=True, samesite="lax")
    return response


@app.get("/setup", response_class=HTMLResponse)
async def setup_get(request: Request):
    user_id = _require_login(request)
    return _template("setup.html", request, {"error": None})


@app.post("/setup")
async def setup_post(
    request: Request,
    background_tasks: BackgroundTasks,
    location: str = Form(...),
    lat: str = Form(default=""),
    lon: str = Form(default=""),
    timezone: str = Form(default=""),
    country: str = Form(default=""),
):
    user_id = _require_login(request)

    existing_locations = get_user_locations(DB_PATH, user_id)
    is_location_change = len(existing_locations) > 0

    if lat and lon and timezone:
        resolved_lat, resolved_lon, resolved_tz = float(lat), float(lon), timezone
    else:
        try:
            resolved_lat, resolved_lon, resolved_tz = ForecastService.get_coordinates_with_timezone(location)
        except Exception:
            return _template(
                "setup.html", request,
                {"error": "We couldn't find that location. Please try a different city name."},
                status_code=422,
            )

    set_user_location(DB_PATH, user_id, location, resolved_lat, resolved_lon, resolved_tz)
    existing_prefs = get_user_preferences(DB_PATH, user_id)
    if not existing_prefs and "united states" in country.lower():
        upsert_user_preferences(DB_PATH, user_id, **{**DEFAULT_PREFS, "temp_unit": "F"})
    if not is_location_change and os.getenv("ENABLE_WELCOME_EMAIL"):
        user = get_user_by_id(DB_PATH, user_id)
        feed_token = get_feed_token_by_user(DB_PATH, user_id)
        if feed_token and user:
            webcal_url, _ = _build_feed_urls(request, feed_token)
            background_tasks.add_task(send_welcome_email, user["email"], webcal_url, location)
    background_tasks.add_task(_initial_forecast_fetch, location, DB_PATH, resolved_lat, resolved_lon, resolved_tz)
    redirect_url = "/settings" if is_location_change else "/connect?from=setup"
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
    return _template("login.html", request, {"error": None})


@app.post("/login")
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    user = get_user_by_email(DB_PATH, email)
    if not user or not check_password(password, user["password_hash"]):
        return _template(
            "login.html", request,
            {"error": "Invalid email or password.", "email": email},
            status_code=401,
        )

    session_token = create_session_token(user["id"])
    response = RedirectResponse(url="/settings", status_code=303)
    response.set_cookie("session", session_token, httponly=True, samesite="lax")
    return response


@app.post("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
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
    user_id = _require_login(request)

    # Returning users go to settings; new users from setup see the connect page
    from_setup = request.query_params.get("from") == "setup"
    if not from_setup:
        return RedirectResponse(url="/settings?tab=reconnect", status_code=303)

    feed_token = get_feed_token_by_user(DB_PATH, user_id)
    webcal_url, google_cal_url = _build_feed_urls(request, feed_token) if feed_token else (None, None)

    return _template("connect.html", request, {
        "webcal_url": webcal_url,
        "google_cal_url": google_cal_url,
        "google_oauth_enabled": google_oauth_enabled(),
        "google_connected": is_google_connected(DB_PATH, user_id),
    })


@app.get("/settings", response_class=HTMLResponse)
async def settings(
    request: Request,
    success: str = Query(default=""),
    error: str = Query(default=""),
    ref: str = Query(default=""),
):
    user_id = _require_login(request)

    user = get_user_by_id(DB_PATH, user_id)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if ref == "cal":
        increment_settings_clicks(DB_PATH, user_id)

    feed_token = get_feed_token_by_user(DB_PATH, user_id)
    locations = get_user_locations(DB_PATH, user_id)
    webcal_url, google_cal_url = _build_feed_urls(request, feed_token) if feed_token else (None, None)
    prefs_row = get_user_preferences(DB_PATH, user_id)
    prefs = resolve_prefs(prefs_row)

    # Convert thresholds for display in user's preferred unit
    if prefs.get("temp_unit") == "F":
        from src.services.forecast_formatting import c_to_f
        prefs["cold_threshold"] = round(c_to_f(prefs["cold_threshold"]) * 2) / 2
        prefs["warm_threshold"] = round(c_to_f(prefs["warm_threshold"]) * 2) / 2
        prefs["hot_threshold"] = round(c_to_f(prefs["hot_threshold"]) * 2) / 2

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

    return _template("settings.html", request, {
        "user": user,
        "feed_token": feed_token,
        "webcal_url": webcal_url,
        "google_cal_url": google_cal_url,
        "locations": locations,
        "prefs": prefs,
        "success": success,
        "error": error,
        "last_updated": last_updated,
        "is_admin": _is_admin(user_id),
        "google_oauth_enabled": google_oauth_enabled(),
        "google_connected": is_google_connected(DB_PATH, user_id),
    })


@app.post("/settings")
async def settings_post(
    request: Request,
    background_tasks: BackgroundTasks,
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
    temp_unit: str = Form(default="C"),
):
    user_id = _require_login(request)

    if temp_unit == "F":
        cold_threshold, warm_threshold, hot_threshold = _convert_thresholds_to_celsius(
            cold_threshold, warm_threshold, hot_threshold
        )

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
        temp_unit=temp_unit,
    )
    if is_google_connected(DB_PATH, user_id):
        background_tasks.add_task(_google_push_initial, DB_PATH, user_id)

    return RedirectResponse(url="/settings?success=prefs", status_code=303)


@app.post("/settings/email")
async def settings_email_post(
    request: Request,
    new_email: str = Form(...),
    current_password: str = Form(...),
):
    user_id = _require_login(request)

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
    user_id = _require_login(request)

    user = get_user_by_id(DB_PATH, user_id)
    if not user or not check_password(current_password, user["password_hash"]):
        return RedirectResponse(url="/settings?error=wrong_password", status_code=303)

    if len(new_password) < 12:
        return RedirectResponse(url="/settings?error=password_too_short", status_code=303)

    update_user_password(DB_PATH, user_id, new_password)
    return RedirectResponse(url="/settings?success=password", status_code=303)


@app.get("/settings/export")
async def settings_export(request: Request):
    user_id = _require_login(request)

    data = export_user_data(DB_PATH, user_id)
    return JSONResponse(
        content=data,
        headers={"Content-Disposition": 'attachment; filename="weathercal-data.json"'},
    )


@app.post("/settings/delete")
async def settings_delete_post(
    request: Request,
    confirm_email: str = Form(...),
):
    user_id = _require_login(request)

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
    user_id = _require_login(request)

    user = get_user_by_id(DB_PATH, user_id)
    email = user["email"] if user else ""
    feed_token = get_feed_token_by_user(DB_PATH, user_id)
    webcal_url, _ = _build_feed_urls(request, feed_token) if feed_token else (None, None)
    locations = get_user_locations(DB_PATH, user_id)
    locations_str = ", ".join(loc["location"] for loc in locations)

    full_description = f"[{topic}] {description}" if topic else description

    save_feedback(
        DB_PATH, user_id, email,
        feed_url=webcal_url or "",
        locations=locations_str,
        calendar_app=topic,
        description=full_description,
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
    if user_id:
        return RedirectResponse(url="/settings?tab=feedback", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


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
    user_id = _require_login(request)

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

    return _template("feedback.html", request, {
        "webcal_url": webcal_url, "locations": user_locations, "sent": True,
    })


def _google_push_initial(db_path, user_id):
    """Background task: push initial forecast events to Google Calendar."""
    try:
        from src.web.db import get_user_preferences, get_user_locations, resolve_prefs as _resolve_prefs
        locations = get_user_locations(db_path, user_id)
        prefs_row = get_user_preferences(db_path, user_id)
        prefs = _resolve_prefs(prefs_row)
        for loc in locations:
            store = ForecastStore(db_path=db_path)
            forecasts = store.get_forecasts_for_locations([loc["location"]], days=14)
            push_events_for_user(db_path, user_id, forecasts, prefs, loc["location"], loc["timezone"])
    except Exception:
        logger.exception("Initial Google push failed for user_id=%s", user_id)


@app.get("/auth/google")
async def google_auth_start(request: Request):
    user_id = _require_login(request)
    if not google_oauth_enabled():
        return RedirectResponse(url="/settings", status_code=303)

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = base_url + "/auth/google/callback"
    flow = get_oauth_flow(redirect_uri)

    state = jwt.encode(
        {"user_id": user_id, "purpose": "google_oauth"},
        SECRET_KEY,
        algorithm="HS256",
    )
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        state=state,
    )
    return RedirectResponse(url=authorization_url, status_code=303)


@app.get("/auth/google/callback")
async def google_auth_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    code: str = Query(default=""),
    state: str = Query(default=""),
):
    if not code or not state:
        return RedirectResponse(url="/settings?error=google_auth_failed", status_code=303)

    try:
        payload = jwt.decode(state, SECRET_KEY, algorithms=["HS256"])
        state_user_id = payload.get("user_id")
    except Exception:
        return RedirectResponse(url="/settings?error=google_auth_failed", status_code=303)

    session_user_id = _get_user_id(request)
    if not session_user_id or session_user_id != state_user_id:
        return RedirectResponse(url="/login", status_code=303)

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = base_url + "/auth/google/callback"
    flow = get_oauth_flow(redirect_uri)

    try:
        flow.fetch_token(code=code)
    except Exception:
        logger.exception("Google token exchange failed for user_id=%s", session_user_id)
        return RedirectResponse(url="/settings?error=google_auth_failed", status_code=303)

    credentials = flow.credentials

    try:
        service = build_google_service(credentials)
        locations = get_user_locations(DB_PATH, session_user_id)
        location_name = locations[0]["location"] if locations else ""
        calendar_id = create_weathercal_calendar(service, location_name)
    except Exception:
        logger.exception("Failed to create WeatherCal calendar for user_id=%s", session_user_id)
        return RedirectResponse(url="/settings?error=google_auth_failed", status_code=303)

    store_google_tokens(DB_PATH, session_user_id, credentials, calendar_id)
    background_tasks.add_task(_google_push_initial, DB_PATH, session_user_id)
    return RedirectResponse(url="/settings?tab=reconnect&success=google_connected", status_code=303)


@app.post("/auth/google/disconnect")
async def google_auth_disconnect(request: Request):
    user_id = _require_login(request)

    from src.integrations.google_push import get_google_credentials, delete_google_calendar
    # Delete the WeatherCal calendar from user's Google account first
    delete_google_calendar(DB_PATH, user_id)

    # Revoke the OAuth token with Google
    credentials = get_google_credentials(DB_PATH, user_id)
    if credentials and credentials.token:
        try:
            import requests as _requests
            _requests.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": credentials.token},
                timeout=5,
            )
        except Exception:
            logger.warning("Failed to revoke Google token for user_id=%s", user_id)

    delete_google_tokens(DB_PATH, user_id)
    return RedirectResponse(url="/settings?tab=reconnect&success=google_disconnected", status_code=303)


@app.get("/feed/{token}/weather.ics")
async def feed(request: Request, token: str):
    rows = get_rows_by_token(DB_PATH, token)
    if not rows:
        return Response(content="Invalid or expired token.", status_code=404)

    ua = request.headers.get("user-agent", "")
    update_feed_poll(DB_PATH, token, ua)
    log_feed_poll(DB_PATH, token, ua)

    user_id = rows[0]["id"]
    locations = list({row["location"] for row in rows})
    store = ForecastStore(db_path=DB_PATH)
    forecasts = store.get_forecasts_for_locations(locations, days=14)

    location_name = locations[0] if locations else "Unknown"
    prefs_row = get_user_preferences(DB_PATH, user_id)
    prefs = resolve_prefs(prefs_row)
    settings_url = str(request.base_url).rstrip("/") + "/settings?ref=cal"
    ics_content = generate_ics(forecasts, location_name, prefs=prefs, settings_url=settings_url)

    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="weather.ics"'},
    )


# --- Event ICS Feed Routes ---


@app.get("/events.ics")
async def events_ics():
    events = get_future_events(DB_PATH)
    ics_content = build_event_ics(events)
    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="events.ics"'},
    )


@app.get("/events/free.ics")
async def events_free_ics():
    events = get_future_events(DB_PATH, free_only=True)
    ics_content = build_event_ics(events)
    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="events.ics"'},
    )


@app.get("/feed/{token}/events.ics")
async def feed_events(token: str):
    user_id = get_user_id_by_feed_token(DB_PATH, token)
    if not user_id:
        return Response(content="Invalid or expired token.", status_code=404)
    events = get_future_events(DB_PATH)
    ics_content = build_event_ics(events)
    return Response(
        content=ics_content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="events.ics"'},
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request):
    user_id = _require_login(request)
    if not _is_admin(user_id):
        return Response(content="Forbidden", status_code=403)
    stats = get_admin_stats(DB_PATH)
    feedback = get_feedback(DB_PATH)
    return _template("admin.html", request, {"stats": stats, "feedback": feedback})


@app.get("/impressum", response_class=HTMLResponse)
async def impressum(request: Request):
    return _template("impressum.html", request)


@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return _template("privacy.html", request)


@app.get("/terms", response_class=HTMLResponse)
async def terms(request: Request):
    return _template("terms.html", request)
