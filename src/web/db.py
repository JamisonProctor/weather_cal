import secrets
import sqlite3
import logging
from datetime import datetime

import bcrypt

logger = logging.getLogger(__name__)


def _conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_user(db_path: str, email: str, password: str) -> int:
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    created_at = datetime.now().isoformat()
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email, password_hash, created_at),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_user_by_email(db_path: str, email: str):
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ? AND is_active = 1", (email,))
        return cur.fetchone()
    finally:
        conn.close()


def get_user_by_id(db_path: str, user_id: int):
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,))
        return cur.fetchone()
    finally:
        conn.close()


def create_user_location(
    db_path: str, user_id: int, location: str, lat: float, lon: float, timezone: str
) -> int:
    created_at = datetime.now().isoformat()
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO user_locations (user_id, location, lat, lon, timezone, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, location, lat, lon, timezone, created_at),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_user_locations(db_path: str, user_id: int):
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM user_locations WHERE user_id = ?", (user_id,))
        return cur.fetchall()
    finally:
        conn.close()


def create_feed_token(db_path: str, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    created_at = datetime.now().isoformat()
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO feed_tokens (user_id, token, created_at) VALUES (?, ?, ?)",
            (user_id, token, created_at),
        )
        conn.commit()
        return token
    finally:
        conn.close()


def get_feed_token_by_user(db_path: str, user_id: int):
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT token FROM feed_tokens WHERE user_id = ? LIMIT 1", (user_id,))
        row = cur.fetchone()
        return row["token"] if row else None
    finally:
        conn.close()


def get_rows_by_token(db_path: str, token: str):
    """Return user+location rows for a feed token, or [] if invalid."""
    conn = _conn(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT u.id, u.email, ul.location, ul.lat, ul.lon, ul.timezone
            FROM feed_tokens ft
            JOIN users u ON ft.user_id = u.id
            JOIN user_locations ul ON ul.user_id = u.id
            WHERE ft.token = ? AND u.is_active = 1
            """,
            (token,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def check_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())
