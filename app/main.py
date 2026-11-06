import os
import io
import re
import csv
import html
import json
import time
import hmac
import hashlib
import secrets
import sqlite3
import shutil
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

# =====================================================================================
#  NAME DER ANWENDUNG – hier einfach anpassen (oder per Umgebungsvariable APP_NAME).
#  Wird überall verwendet: Browser-Tab, App-Name auf dem Homescreen (manifest),
#  Berichte/Export, Push-Nachrichten und API-Titel.
# =====================================================================================
APP_NAME = os.environ.get("APP_NAME", "PurrfectHealth")
os.environ["APP_NAME"] = APP_NAME   # damit auch push.py / report.py den Namen kennen

try:
    from app.extras import (router as extras_router, migrate, vomit_keys, relevant_keys,
                            vomit_label, rating_labels, max_score)
    from app.health import router as health_router, migrate_health
    from app.meds import router as meds_router, migrate_meds
    from app.cats import router as cats_router, migrate_cats
    from app.push import router as push_router, start_scheduler
    from app.report import router as report_router, REPORT_CSS, FONT_LINK, HERO_CAT
except ImportError:  # Start ohne Paketstruktur (z. B. "uvicorn main:app")
    from extras import (router as extras_router, migrate, vomit_keys, relevant_keys,
                        vomit_label, rating_labels, max_score)
    from health import router as health_router, migrate_health
    from meds import router as meds_router, migrate_meds
    from cats import router as cats_router, migrate_cats
    from push import router as push_router, start_scheduler
    from report import router as report_router, REPORT_CSS, FONT_LINK, HERO_CAT

app = FastAPI(title=APP_NAME)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "tracker.db")
KINDS = ("food", "snack", "drink")
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS cats (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS manufacturers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)")
    c.execute("""
        CREATE TABLE IF NOT EXISTS foods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manufacturer_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            FOREIGN KEY (manufacturer_id) REFERENCES manufacturers (id) ON DELETE CASCADE,
            UNIQUE(manufacturer_id, name)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS feedings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT,
            cat_name TEXT NOT NULL,
            manufacturer_id INTEGER,
            food_id INTEGER,
            manufacturer_name TEXT NOT NULL,
            food_name TEXT NOT NULL,
            rating INTEGER NOT NULL,
            notes TEXT,
            timestamp TEXT NOT NULL
        )
    """)
    cols = [row["name"] for row in c.execute("PRAGMA table_info(feedings)").fetchall()]
    if "batch_id" not in cols:
        c.execute("ALTER TABLE feedings ADD COLUMN batch_id TEXT")

    # Alte Einträge ohne batch_id nach (Zeitpunkt + Futter + Notiz) gruppieren
    if c.execute("SELECT COUNT(*) AS cnt FROM feedings WHERE batch_id IS NULL OR batch_id = ''").fetchone()["cnt"] > 0:
        groups = c.execute("""
            SELECT timestamp, manufacturer_name, food_name, IFNULL(notes, '') AS n
            FROM feedings WHERE batch_id IS NULL OR batch_id = ''
            GROUP BY timestamp, manufacturer_name, food_name, IFNULL(notes, '')
        """).fetchall()
        for g in groups:
            c.execute("""
                UPDATE feedings SET batch_id = ?
                WHERE (batch_id IS NULL OR batch_id = '') AND timestamp = ?
                  AND manufacturer_name = ? AND food_name = ? AND IFNULL(notes, '') = ?
            """, (str(uuid.uuid4()), g["timestamp"], g["manufacturer_name"], g["food_name"], g["n"]))

    c.execute("""
        CREATE TABLE IF NOT EXISTS vomits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cat_name TEXT NOT NULL,
            vomit_type TEXT DEFAULT 'food',
            timestamp TEXT NOT NULL,
            notes TEXT,
            image_path TEXT
        )
    """)
    v_cols = [row["name"] for row in c.execute("PRAGMA table_info(vomits)").fetchall()]
    if "vomit_type" not in v_cols:
        c.execute("ALTER TABLE vomits ADD COLUMN vomit_type TEXT DEFAULT 'food'")
        c.execute("UPDATE vomits SET vomit_type = 'food' WHERE vomit_type IS NULL OR vomit_type = ''")

    if c.execute("SELECT COUNT(*) AS cnt FROM manufacturers").fetchone()["cnt"] == 0:
        default_data = {
            "MAC's": ["Rind & Hühnerherzen", "Ente, Pute & Huhn", "Lachs & Huhn"],
            "Mjamjam": ["Saftiges Huhn an Möhrchen", "Känguru pur", "Insekt & Huhn"],
            "Catz Finefood": ["Geflügel", "Wild & Rotbarsch", "Lamm & Kaninchen"],
            "Animonda Carny": ["Rind pur", "Rind + Huhn", "Multifleisch-Cocktail"],
        }
        for man_name, food_list in default_data.items():
            c.execute("INSERT INTO manufacturers (name) VALUES (?)", (man_name,))
            man_id = c.lastrowid
            for f_name in food_list:
                c.execute("INSERT INTO foods (manufacturer_id, name) VALUES (?, ?)", (man_id, f_name))

    for k, v in {"language": "de", "rating_3": "Weggeatmet", "rating_2": "Okay",
                 "rating_1": "Verweigert", "setup_completed": "0"}.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # Katzen aus der Historie übernehmen (Upgrade-Fall)
    cat_cnt = c.execute("SELECT COUNT(*) AS cnt FROM cats").fetchone()["cnt"]
    feed_cnt = c.execute("SELECT COUNT(*) AS cnt FROM feedings").fetchone()["cnt"]
    vomit_cnt = c.execute("SELECT COUNT(*) AS cnt FROM vomits").fetchone()["cnt"]
    if cat_cnt == 0 and (feed_cnt > 0 or vomit_cnt > 0):
        existing = set()
        for tbl in ("feedings", "vomits"):
            for r in c.execute(f"SELECT DISTINCT cat_name FROM {tbl}").fetchall():
                if r["cat_name"] and r["cat_name"] != "Unbekannt":
                    existing.add(r["cat_name"])
        for cname in sorted(existing):
            c.execute("INSERT OR IGNORE INTO cats (name) VALUES (?)", (cname,))
        if existing:
            c.execute("UPDATE settings SET value = '1' WHERE key = 'setup_completed'")

    conn.commit()
    conn.close()


init_db()
migrate()                       # Tierarten, Reihenfolge, kind-Spalten, Spuck-Kategorien, Bewertungsstufen
app.include_router(extras_router)
migrate_health()                # Geburtstag, Gesundheitsfelder und -werte
app.include_router(health_router)
migrate_meds()                  # Präparate (Medikamente, Pasten, Pulver, Supplemente)
app.include_router(meds_router)
migrate_cats()                  # erweiterte Tier-Stammdaten (nach migrate_health)
app.include_router(cats_router)
app.include_router(push_router)  # Push-Erinnerung (braucht das Paket "pywebpush")
app.include_router(report_router)  # Bericht-Export mit Mehrfachauswahl (Futter, Snacks, Getränke, Spucken, Gesundheit)


@app.on_event("startup")
async def _start_push_scheduler():
    start_scheduler()


# ======================= BENUTZER & LOGIN =======================

COOKIE = "cft_session"
SESSION_DAYS = 400                      # so lange bleibt ein Gerät angemeldet
OPEN_PATHS = {"/api/auth/status", "/api/login", "/api/setup-admin"}


def init_auth_tables():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
        pw_hash TEXT NOT NULL, is_admin INTEGER DEFAULT 0, prefs TEXT DEFAULT '{}')""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created REAL, last_seen REAL)""")
    conn.commit()
    conn.close()


init_auth_tables()


def hash_pw(pw: str) -> str:
    salt = secrets.token_bytes(16)
    return salt.hex() + ":" + hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1).hex()


def check_pw(pw: str, stored: str) -> bool:
    salt, h = stored.split(":")
    test = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()
    return hmac.compare_digest(test, h)


def _th(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    conn = get_db()
    row = conn.execute("""
        SELECT u.id, u.username, u.is_admin FROM sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ? AND s.last_seen > ?
    """, (_th(token), time.time() - SESSION_DAYS * 86400)).fetchone()
    if row:
        conn.execute("UPDATE sessions SET last_seen = ? WHERE token_hash = ?", (time.time(), _th(token)))
        conn.commit()
    conn.close()
    return dict(row) if row else None


@app.middleware("http")
async def require_login(request: Request, call_next):
    p = request.url.path
    if (p.startswith("/api/") or p.startswith("/uploads/")) and p not in OPEN_PATHS:
        user = current_user(request)
        if not user:
            return JSONResponse({"detail": "Nicht angemeldet"}, status_code=401)
        request.state.user = user
    return await call_next(request)


class Credentials(BaseModel):
    username: str
    password: str


def _new_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn = get_db()
    conn.execute("INSERT INTO sessions (token_hash, user_id, created, last_seen) VALUES (?, ?, ?, ?)",
                 (_th(token), user_id, time.time(), time.time()))
    conn.commit()
    conn.close()
    return token


def _set_cookie(response: Response, request: Request, token: str):
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True,
                        samesite="lax", secure=request.url.scheme == "https")


@app.get("/api/auth/status")
def auth_status(request: Request, response: Response):
    conn = get_db()
    n = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    conn.close()
    user = current_user(request)
    if user:  # Cookie bei jedem App-Start verlängern
        _set_cookie(response, request, request.cookies.get(COOKIE))
    return {"needs_setup": n == 0, "user": user}


@app.post("/api/setup-admin")
def setup_admin(data: Credentials, request: Request, response: Response):
    conn = get_db()
    if conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] > 0:
        conn.close()
        raise HTTPException(status_code=403, detail="Einrichtung bereits abgeschlossen")
    name = data.username.strip()
    if not name or len(data.password) < 8:
        conn.close()
        raise HTTPException(status_code=400, detail="Name angeben, Passwort mind. 8 Zeichen")
    cur = conn.execute("INSERT INTO users (username, pw_hash, is_admin) VALUES (?, ?, 1)", (name, hash_pw(data.password)))
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    _set_cookie(response, request, _new_session(uid))
    return {"status": "ok"}


@app.post("/api/login")
def login(data: Credentials, request: Request, response: Response):
    conn = get_db()
    row = conn.execute("SELECT id, pw_hash FROM users WHERE username = ?", (data.username.strip(),)).fetchone()
    conn.close()
    if not row or not check_pw(data.password, row["pw_hash"]):
        time.sleep(0.6)  # bremst Durchprobieren; zusätzlich Rate-Limit im Reverse Proxy empfohlen
        raise HTTPException(status_code=401, detail="Name oder Passwort falsch")
    _set_cookie(response, request, _new_session(row["id"]))
    return {"status": "ok"}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        conn = get_db()
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_th(token),))
        conn.commit()
        conn.close()
    response.delete_cookie(COOKIE)
    return {"status": "ok"}


@app.post("/api/users")
def create_user(data: Credentials, request: Request):
    if not request.state.user["is_admin"]:
        raise HTTPException(status_code=403, detail="Nur für Administratoren")
    name = data.username.strip()
    if not name or len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Name angeben, Passwort mind. 8 Zeichen")
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (username, pw_hash) VALUES (?, ?)", (name, hash_pw(data.password)))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Benutzer existiert bereits")
    finally:
        conn.close()
    return {"status": "ok"}


@app.get("/api/prefs")
def get_prefs(request: Request):
    conn = get_db()
    row = conn.execute("SELECT prefs FROM users WHERE id = ?", (request.state.user["id"],)).fetchone()
    conn.close()
    return json.loads(row["prefs"] or "{}")


@app.put("/api/prefs")
def put_prefs(prefs: dict, request: Request):
    raw = json.dumps(prefs)
    if len(raw) > 100_000:
        raise HTTPException(status_code=413, detail="Einstellungen zu groß")
    conn = get_db()
    conn.execute("UPDATE users SET prefs = ? WHERE id = ?", (raw, request.state.user["id"]))
    conn.commit()
    conn.close()
    return {"status": "ok"}


# ======================= PYDANTIC MODELLE =======================

class SettingsUpdate(BaseModel):
    language: Optional[str] = None
    rating_3: Optional[str] = None
    rating_2: Optional[str] = None
    rating_1: Optional[str] = None
    setup_completed: Optional[str] = None

class InitialSetupPayload(BaseModel):
    language: str
    cats: List[str]

class CatCreate(BaseModel):
    name: str

class CatUpdate(BaseModel):
    name: str

class ManufacturerCreate(BaseModel):
    name: str

class ManufacturerUpdate(BaseModel):
    name: str

class FoodCreate(BaseModel):
    manufacturer_id: int
    name: str

class FoodUpdate(BaseModel):
    manufacturer_id: int
    name: str

class FeedingBatchPayload(BaseModel):
    cat_ratings: Dict[str, int]
    manufacturer_id: int
    food_id: int
    notes: Optional[str] = ""
    timestamp: Optional[str] = None
    kind: Optional[str] = "food"        # food | snack | drink


# ======================= SETTINGS & ERST-SETUP =======================

@app.get("/api/settings")
def get_settings():
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


@app.put("/api/settings")
def update_settings(data: SettingsUpdate):
    conn = get_db()
    for k, v in data.dict(exclude_unset=True).items():
        if v is not None:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v).strip()))
    conn.commit()
    conn.close()
    return get_settings()


@app.post("/api/setup")
def complete_initial_setup(data: InitialSetupPayload):
    clean = [x.strip() for x in data.cats if x.strip()]
    if not clean:
        raise HTTPException(status_code=400, detail="Mindestens ein Tier angeben")
    conn = get_db()
    c = conn.cursor()
    lang = "en" if data.language == "en" else "de"
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('language', ?)", (lang,))
    for cname in clean:
        c.execute("INSERT OR IGNORE INTO cats (name) VALUES (?)", (cname,))
    c.execute("UPDATE cats SET sort = id WHERE sort IS NULL OR sort = 0")
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('setup_completed', '1')")
    conn.commit()
    conn.close()
    return {"status": "ok"}


# ======================= TIERE (Tabelle "cats") =======================

@app.get("/api/cats")
def get_cats():
    conn = get_db()
    rows = conn.execute("SELECT id, name, species FROM cats ORDER BY sort, id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/cats")
def create_cat(data: CatCreate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO cats (name, sort) VALUES (?, (SELECT COALESCE(MAX(sort), 0) + 1 FROM cats))", (name,))
        conn.commit()
        new_id = c.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Tier existiert bereits")
    conn.close()
    return {"id": new_id, "name": name}


@app.put("/api/cats/{cat_id}")
def update_cat(cat_id: int, data: CatUpdate):
    new_name = data.name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT name FROM cats WHERE id = ?", (cat_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Tier nicht gefunden")
    old_name = row["name"]
    try:
        c.execute("UPDATE cats SET name = ? WHERE id = ?", (new_name, cat_id))
        c.execute("UPDATE feedings SET cat_name = ? WHERE cat_name = ?", (new_name, old_name))
        c.execute("UPDATE vomits SET cat_name = ? WHERE cat_name = ?", (new_name, old_name))
        c.execute("UPDATE med_logs SET cat_name = ? WHERE cat_name = ?", (new_name, old_name))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Ein Tier mit diesem Namen existiert bereits")
    conn.close()
    return {"status": "ok", "id": cat_id, "name": new_name}


@app.delete("/api/cats/{cat_id}")
def delete_cat(cat_id: int):
    # Entfernt das Tier nur aus der aktiven Auswahl; die Historie bleibt erhalten.
    conn = get_db()
    conn.execute("DELETE FROM cats WHERE id = ?", (cat_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


# ======================= HERSTELLER & SORTEN =======================

@app.get("/api/manufacturers")
def get_manufacturers():
    conn = get_db()
    rows = conn.execute("SELECT id, name, kind FROM manufacturers ORDER BY name COLLATE NOCASE").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/manufacturers")
def create_manufacturer(data: ManufacturerCreate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO manufacturers (name) VALUES (?)", (name,))
        conn.commit()
        new_id = c.lastrowid
    except sqlite3.IntegrityError:
        row = c.execute("SELECT id FROM manufacturers WHERE name = ?", (name,)).fetchone()
        new_id = row["id"] if row else None
    finally:
        conn.close()
    return {"id": new_id, "name": name}


@app.put("/api/manufacturers/{man_id}")
def update_manufacturer(man_id: int, data: ManufacturerUpdate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT name FROM manufacturers WHERE id = ?", (man_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Hersteller nicht gefunden")
    try:
        c.execute("UPDATE manufacturers SET name = ? WHERE id = ?", (name, man_id))
        c.execute("UPDATE feedings SET manufacturer_name = ? WHERE manufacturer_id = ? OR manufacturer_name = ?",
                  (name, man_id, row["name"]))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Hersteller existiert bereits")
    conn.close()
    return {"status": "ok", "id": man_id, "name": name}


@app.delete("/api/manufacturers/{man_id}")
def delete_manufacturer(man_id: int):
    conn = get_db()
    conn.execute("DELETE FROM foods WHERE manufacturer_id = ?", (man_id,))
    conn.execute("DELETE FROM manufacturers WHERE id = ?", (man_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


@app.get("/api/foods")
def get_foods():
    conn = get_db()
    rows = conn.execute("SELECT id, manufacturer_id, name FROM foods ORDER BY name COLLATE NOCASE").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/foods")
def create_food(data: FoodCreate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO foods (manufacturer_id, name) VALUES (?, ?)", (data.manufacturer_id, name))
        conn.commit()
        new_id = c.lastrowid
    except sqlite3.IntegrityError:
        row = c.execute("SELECT id FROM foods WHERE manufacturer_id = ? AND name = ?", (data.manufacturer_id, name)).fetchone()
        new_id = row["id"] if row else None
    finally:
        conn.close()
    return {"id": new_id, "manufacturer_id": data.manufacturer_id, "name": name}


@app.put("/api/foods/{food_id}")
def update_food(food_id: int, data: FoodUpdate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = get_db()
    c = conn.cursor()
    row = c.execute("SELECT name FROM foods WHERE id = ?", (food_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Sorte nicht gefunden")
    try:
        c.execute("UPDATE foods SET name = ?, manufacturer_id = ? WHERE id = ?", (name, data.manufacturer_id, food_id))
        c.execute("UPDATE feedings SET food_name = ?, manufacturer_id = ? WHERE food_id = ? OR food_name = ?",
                  (name, data.manufacturer_id, food_id, row["name"]))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Diese Sorte existiert bereits")
    conn.close()
    return {"status": "ok", "id": food_id, "name": name}


@app.delete("/api/foods/{food_id}")
def delete_food(food_id: int):
    conn = get_db()
    conn.execute("DELETE FROM foods WHERE id = ?", (food_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


# ======================= FÜTTERUNGEN (Futter, Snacks, Getränke) =======================

def _write_feedings(c, batch_id: str, data: FeedingBatchPayload):
    man = c.execute("SELECT name FROM manufacturers WHERE id = ?", (data.manufacturer_id,)).fetchone()
    food = c.execute("SELECT name FROM foods WHERE id = ?", (data.food_id,)).fetchone()
    if not man or not food:
        raise HTTPException(status_code=400, detail="Hersteller oder Sorte ungültig")
    top = max_score()
    if any(not 1 <= r <= top for r in data.cat_ratings.values()):
        raise HTTPException(status_code=400, detail=f"Bewertung muss zwischen 1 und {top} liegen")
    ts = data.timestamp or datetime.now().strftime("%Y-%m-%dT%H:%M")
    kind = data.kind if data.kind in KINDS else "food"
    ids = []
    for cat_name, rating in data.cat_ratings.items():
        c.execute("""
            INSERT INTO feedings (batch_id, cat_name, manufacturer_id, food_id, manufacturer_name,
                                  food_name, rating, notes, timestamp, kind)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (batch_id, cat_name, data.manufacturer_id, data.food_id, man["name"], food["name"],
              rating, data.notes, ts, kind))
        ids.append(c.lastrowid)
    return ids


@app.get("/api/feedings")
def get_feedings(limit: int = 1000, kind: Optional[str] = None):
    conn = get_db()
    if kind in KINDS:
        rows = conn.execute("SELECT * FROM feedings WHERE kind = ? ORDER BY timestamp DESC, id DESC LIMIT ?",
                            (kind, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM feedings ORDER BY timestamp DESC, id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/feedings")
def create_feeding(data: FeedingBatchPayload):
    if not data.cat_ratings:
        raise HTTPException(status_code=400, detail="Mindestens ein Tier auswählen")
    conn = get_db()
    try:
        batch_id = str(uuid.uuid4())
        ids = _write_feedings(conn.cursor(), batch_id, data)
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok", "batch_id": batch_id, "created": ids}


@app.put("/api/feedings/batch/{batch_id}")
def update_feeding_batch(batch_id: str, data: FeedingBatchPayload):
    if not data.cat_ratings:
        raise HTTPException(status_code=400, detail="Mindestens ein Tier auswählen")
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM feedings WHERE batch_id = ?", (batch_id,))
        _write_feedings(c, batch_id, data)
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok"}


@app.delete("/api/feedings/batch/{batch_id}")
def delete_feeding_batch(batch_id: str):
    conn = get_db()
    conn.execute("DELETE FROM feedings WHERE batch_id = ?", (batch_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


# ======================= SPUCK-TRACKER (12h-Korrelation) =======================

def get_recent_feedings_for_vomit(conn, cat_name: str, vomit_ts_str: str):
    try:
        vomit_dt = datetime.fromisoformat(vomit_ts_str)
    except ValueError:
        return []
    start_str = (vomit_dt - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M")
    end_str = vomit_dt.strftime("%Y-%m-%dT%H:%M")
    if cat_name in ("Unbekannt", "Unknown"):
        rows = conn.execute("""
            SELECT cat_name, manufacturer_name, food_name, timestamp, kind FROM feedings
            WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC
        """, (start_str, end_str)).fetchall()
    else:
        rows = conn.execute("""
            SELECT cat_name, manufacturer_name, food_name, timestamp, kind FROM feedings
            WHERE cat_name = ? AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC
        """, (cat_name, start_str, end_str)).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/vomits")
def get_vomits(limit: int = 200):
    conn = get_db()
    rows = conn.execute("SELECT * FROM vomits ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    result = []
    for r in rows:
        item = dict(r)
        item["vomit_type"] = item.get("vomit_type") or "food"
        item["recent_feedings"] = get_recent_feedings_for_vomit(conn, item["cat_name"], item["timestamp"])
        result.append(item)
    conn.close()
    return result


@app.post("/api/vomits")
async def create_vomit(
    cat_name: str = Form(...),
    vomit_type: Optional[str] = Form("food"),
    timestamp: Optional[str] = Form(None),
    notes: Optional[str] = Form(""),
    image: Optional[UploadFile] = File(None),
):
    ts = timestamp or datetime.now().strftime("%Y-%m-%dT%H:%M")
    v_type = vomit_type if vomit_type in vomit_keys() else "food"
    img_rel_path = None
    if image and image.filename:
        ext = os.path.splitext(image.filename)[1].lower()
        if ext not in IMG_EXT:
            ext = ".jpg"
        safe_name = f"vomit_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{ext}"
        with open(os.path.join(UPLOAD_DIR, safe_name), "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        img_rel_path = f"/uploads/{safe_name}"
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO vomits (cat_name, vomit_type, timestamp, notes, image_path) VALUES (?, ?, ?, ?, ?)",
              (cat_name, v_type, ts, notes, img_rel_path))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return {"status": "ok", "id": new_id}


def _store_image(image: UploadFile) -> str:
    ext = os.path.splitext(image.filename)[1].lower()
    if ext not in IMG_EXT:
        ext = ".jpg"
    name = f"vomit_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{ext}"
    with open(os.path.join(UPLOAD_DIR, name), "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)
    return f"/uploads/{name}"


def _remove_image(rel_path: Optional[str]):
    if rel_path:
        path = os.path.join(UPLOAD_DIR, os.path.basename(rel_path))
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


@app.put("/api/vomits/{vomit_id}")
async def update_vomit(
    vomit_id: int,
    cat_name: str = Form(...),
    vomit_type: Optional[str] = Form("food"),
    timestamp: Optional[str] = Form(None),
    notes: Optional[str] = Form(""),
    remove_image: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
):
    conn = get_db()
    row = conn.execute("SELECT image_path, timestamp, vomit_type FROM vomits WHERE id = ?", (vomit_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    # ausgeblendete eigene Kategorien bleiben erlaubt, wenn der Eintrag sie schon hatte
    v_type = vomit_type if (vomit_type in vomit_keys() or vomit_type == row["vomit_type"]) else "food"
    img = row["image_path"]
    if image and image.filename:          # neues Foto ersetzt das alte
        new_img = _store_image(image)
        _remove_image(img)
        img = new_img
    elif remove_image == "1":             # Foto entfernen
        _remove_image(img)
        img = None
    conn.execute("UPDATE vomits SET cat_name = ?, vomit_type = ?, timestamp = ?, notes = ?, image_path = ? WHERE id = ?",
                 (cat_name, v_type, timestamp or row["timestamp"], notes or "", img, vomit_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.delete("/api/vomits/{vomit_id}")
def delete_vomit(vomit_id: int):
    conn = get_db()
    row = conn.execute("SELECT image_path FROM vomits WHERE id = ?", (vomit_id,)).fetchone()
    if row and row["image_path"]:
        path = os.path.join(UPLOAD_DIR, os.path.basename(row["image_path"]))
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    conn.execute("DELETE FROM vomits WHERE id = ?", (vomit_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


# ======================= EXPORT (CSV & PDF-BERICHT) =======================

KIND_DE = {"food": "Futter", "snack": "Snack", "drink": "Getränk"}
KIND_EN = {"food": "Food", "snack": "Snack", "drink": "Drink"}


@app.get("/api/export/db")
def export_db(request: Request):
    """Konsistente Sicherung der kompletten SQLite-Datenbank (nur Administratoren, enthält auch die Benutzerkonten)."""
    if not request.state.user["is_admin"]:
        raise HTTPException(status_code=403, detail="Nur Administratoren")
    import tempfile
    from starlette.background import BackgroundTask
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)   # sicher auch während die App läuft
    finally:
        dst.close()
        src.close()
    slug = re.sub(r"[^a-z0-9]+", "_", APP_NAME.lower()).strip("_") or "backup"
    filename = f"{slug}_backup_{datetime.now().strftime('%Y-%m-%d_%H%M')}.db"
    return FileResponse(tmp, media_type="application/octet-stream", filename=filename,
                        background=BackgroundTask(os.remove, tmp))


@app.get("/api/export/csv")
def export_csv(kind: Optional[str] = None, lang: Optional[str] = None):
    conn = get_db()
    s_map = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings").fetchall()}
    lang = lang if lang in ("de", "en") else s_map.get("language", "de")
    r_labels = rating_labels()
    if kind in KINDS:
        feedings = conn.execute("SELECT * FROM feedings WHERE kind = ? ORDER BY timestamp DESC, id DESC", (kind,)).fetchall()
    else:
        feedings = conn.execute("SELECT * FROM feedings ORDER BY timestamp DESC, id DESC").fetchall()
    vomits = conn.execute("SELECT * FROM vomits ORDER BY timestamp DESC").fetchall()
    conn.close()

    rel = relevant_keys()
    food_vomits = []
    for v in vomits:
        vtype = v["vomit_type"] or "food"
        if vtype in rel:
            try:
                food_vomits.append((v["cat_name"], datetime.fromisoformat(v["timestamp"]), vtype, v["timestamp"]))
            except ValueError:
                pass

    out = io.StringIO()
    out.write("\ufeff")  # BOM für Excel
    w = csv.writer(out, delimiter=";")
    if lang == "en":
        w.writerow(["Date", "Time", "Batch_ID", "Type", "Brand", "Variety", "Animal", "Rating_Score",
                    "Rating_Label", "Notes", "Food_Vomit_Within_12h"])
    else:
        w.writerow(["Datum", "Uhrzeit", "Batch_ID", "Art", "Hersteller", "Sorte", "Tier", "Bewertung_Score",
                    "Bewertung_Text", "Notiz", "Futter_Erbrochen_12h"])
    names = KIND_EN if lang == "en" else KIND_DE
    for f in feedings:
        ts = f["timestamp"] or ""
        hit = "No" if lang == "en" else "Nein"
        try:
            f_dt = datetime.fromisoformat(ts)
            for v_cat, v_dt, v_type, v_ts in food_vomits:
                if v_cat in (f["cat_name"], "Unbekannt", "Unknown") and 0 <= (v_dt - f_dt).total_seconds() / 3600.0 <= 12:
                    hit = f"{'Yes' if lang == 'en' else 'Ja'} ({v_ts[11:16]} - {vomit_label(v_type, lang)})"
                    break
        except ValueError:
            pass
        w.writerow([ts[:10], ts[11:16] if len(ts) >= 16 else "", f["batch_id"] or "",
                    names.get(f["kind"] or "food", ""), f["manufacturer_name"], f["food_name"], f["cat_name"],
                    f["rating"], r_labels.get(f["rating"], str(f["rating"])), f["notes"] or "", hit])
    slug = re.sub(r"[^a-z0-9]+", "_", APP_NAME.lower()).strip("_") or "export"
    filename = f"{slug}_export_{datetime.now().strftime('%Y-%m-%d')}.csv"
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# REPORT_CSS (App-Design) kommt aus report.py


@app.get("/api/export/pdf", response_class=HTMLResponse)
def export_pdf_report(hide_deleted: bool = False, kind: str = "food", lang: Optional[str] = None):
    kind = kind if kind in KINDS else "food"
    conn = get_db()
    s_map = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings").fetchall()}
    lang = lang if lang in ("de", "en") else s_map.get("language", "de")
    r_labels = rating_labels()
    top = max_score()
    rel = relevant_keys()
    animals = conn.execute("SELECT name, species FROM cats ORDER BY sort, id").fetchall()
    active_cats = [a["name"] for a in animals]
    icon = {a["name"]: ("🐶" if a["species"] == "dog" else "🐱") for a in animals}
    active_set = set(active_cats)
    all_feedings = [dict(r) for r in conn.execute(
        "SELECT * FROM feedings WHERE kind = ? ORDER BY timestamp DESC, id DESC", (kind,)).fetchall()]
    all_vomits = [dict(r) for r in conn.execute("SELECT * FROM vomits ORDER BY timestamp DESC").fetchall()]
    conn.close()

    if hide_deleted:
        all_feedings = [f for f in all_feedings if f["cat_name"] in active_set]
        all_vomits = [v for v in all_vomits if v["cat_name"] in active_set or v["cat_name"] in ("Unbekannt", "Unknown")]

    cat_columns = list(active_cats)
    if not hide_deleted:
        for f in all_feedings:
            if f["cat_name"] and f["cat_name"] not in cat_columns:
                cat_columns.append(f["cat_name"])

    food_vomit_events = []
    for v in all_vomits:
        if (v.get("vomit_type") or "food") in rel:
            try:
                food_vomit_events.append((v["cat_name"], datetime.fromisoformat(v["timestamp"])))
            except ValueError:
                pass
    rel_count = len(food_vomit_events)

    summary = {}
    for f in all_feedings:
        key = f"{f['manufacturer_name']} – {f['food_name']}"
        e = summary.setdefault(key, {"label": key, "count": 0, "sum": 0, "cats": {}, "hits": 0, "hit_cats": set()})
        e["count"] += 1
        e["sum"] += f["rating"]
        e["cats"].setdefault(f["cat_name"], []).append(f["rating"])
        try:
            f_dt = datetime.fromisoformat(f["timestamp"])
            for v_cat, v_dt in food_vomit_events:
                if v_cat in (f["cat_name"], "Unbekannt", "Unknown") and 0 <= (v_dt - f_dt).total_seconds() / 3600.0 <= 12:
                    e["hits"] += 1
                    e["hit_cats"].add(f["cat_name"])
                    break
        except ValueError:
            pass
    ranked = sorted(summary.values(), key=lambda x: (x["sum"] / x["count"], x["count"]), reverse=True)

    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M")
    recent_vomits = [v for v in all_vomits if (v.get("timestamp") or "") >= cutoff]
    recent_feedings = [f for f in all_feedings if (f.get("timestamp") or "") >= cutoff]
    grouped, bmap = [], {}
    for f in recent_feedings:
        k = f.get("batch_id") or f"single_{f['id']}"
        if k not in bmap:
            bmap[k] = {"timestamp": f["timestamp"], "food": f"{f['manufacturer_name']} – {f['food_name']}",
                       "notes": f.get("notes") or "", "items": []}
            grouped.append(bmap[k])
        bmap[k]["items"].append((f["cat_name"], f["rating"]))

    def fmt_dt(s):
        try:
            return datetime.fromisoformat(s).strftime("%d.%m.%Y %H:%M")
        except Exception:
            return s or ""

    def cls(avg):
        return "good" if avg >= top * 0.83 else ("ok" if avg >= top * 0.6 else "bad")

    heads = "".join(f"<th>{icon.get(c, '🐾')} {html.escape(c)}</th>" for c in cat_columns)
    rows = ""
    for it in ranked:
        avg = it["sum"] / it["count"]
        cells = ""
        for c in cat_columns:
            sc = it["cats"].get(c, [])
            if not sc:
                cells += "<td class='muted'>–</td>"
            else:
                ca = sum(sc) / len(sc)
                warn = " ⚠️" if c in it["hit_cats"] else ""
                cells += f"<td><span class='pill {cls(ca)}'>Ø {ca:.1f} ({len(sc)}x){warn}</span></td>"
        vc = f"<span class='pill bad'>⚠️ {it['hits']}x</span>" if it["hits"] else "<span class='muted'>0x</span>"
        rows += (f"<tr><td><strong>{html.escape(it['label'])}</strong></td><td>{it['count']}</td>"
                 f"<td><span class='pill {cls(avg)}'>Ø {avg:.2f} / {top:.2f}</span></td>{cells}<td>{vc}</td></tr>")
    if not rows:
        rows = f"<tr><td colspan='{4 + len(cat_columns)}' class='muted'>Keine Daten vorhanden.</td></tr>"

    vrows = ""
    for v in recent_vomits:
        vt = v.get("vomit_type") or "food"
        lab = html.escape(vomit_label(vt, lang))
        badge = f"<span class='pill bad'>🚨 {lab}</span>" if vt in rel else f"<span class='pill neutral'>ℹ️ {lab}</span>"
        vrows += (f"<tr><td>{fmt_dt(v.get('timestamp', ''))}</td><td><strong>{html.escape(v.get('cat_name', ''))}</strong></td>"
                  f"<td>{badge}</td><td>{html.escape(v.get('notes') or '–')}</td></tr>")
    if not vrows:
        vrows = "<tr><td colspan='4' class='muted'>Keine Spuck-Ereignisse in den letzten 30 Tagen.</td></tr>"

    frows = ""
    for g in grouped:
        rs = ", ".join(f"<strong>{html.escape(c)}:</strong> {html.escape(r_labels.get(r, str(r)))} ({r})" for c, r in g["items"])
        frows += (f"<tr><td style='white-space:nowrap'>{fmt_dt(g['timestamp'])}</td><td><strong>{html.escape(g['food'])}</strong></td>"
                  f"<td>{rs}</td><td>{html.escape(g['notes'] or '–')}</td></tr>")
    if not frows:
        frows = "<tr><td colspan='4' class='muted'>Keine Einträge in den letzten 30 Tagen.</td></tr>"

    total = len(all_feedings)
    overall = f"{sum(f['rating'] for f in all_feedings) / total:.2f}" if total else "–"
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    scale = ", ".join(f"{s} = {html.escape(l)}" for s, l in sorted(r_labels.items(), reverse=True))
    title = KIND_DE[kind]

    doc = f"""<!DOCTYPE html><html lang="{lang}"><head><meta charset="UTF-8">
<title>{html.escape(APP_NAME)} – Bericht {title} ({now_str})</title>{FONT_LINK}<style>{REPORT_CSS}</style></head><body>
<div class="no-print"><div><strong>🐾 {html.escape(APP_NAME)} – Druck- &amp; PDF-Ansicht</strong>
<span style="margin-left:10px;color:#94a3b8">Wähle im Druckdialog „Als PDF speichern“.</span></div>
<div style="display:flex;gap:8px"><button class="btn" onclick="window.print()">🖨️ Als PDF speichern / Drucken</button>
<button class="btn" style="background:#475569" onclick="window.close()">Schließen</button></div></div>
<div class="wrap"><header class="hero"><div><h1>{html.escape(APP_NAME)} – Gesamt-Auswertung &amp; 30-Tage-Bericht ({title})</h1>
<div class="meta">Erstellt am: {now_str} Uhr | Tiere: {html.escape(", ".join(active_cats)) if active_cats else "–"} | Bewertungs-Skala: {scale}</div></div>{HERO_CAT}</header>
<div class="kpi-grid">
<div class="kpi"><div class="label">Einträge gesamt</div><div class="val">{total}</div></div>
<div class="kpi"><div class="label">Ø Akzeptanz (Gesamt)</div><div class="val">{overall} / {top:.2f}</div></div>
<div class="kpi"><div class="label">Spuck-Vorfälle (Gesamt)</div><div class="val">{len(all_vomits)} (davon {rel_count}x futterrelevant)</div></div>
<div class="kpi"><div class="label">Letzte 30 Tage</div><div class="val">{len(grouped)} Runden / {len(recent_vomits)}x Spucken</div></div></div>
<h2>1. Akzeptanz-Matrix (gesamter Zeitraum)</h2>
<p class="meta">Durchschnittliche Bewertung je Sorte und Tier. <strong>⚠️ Spucken (12h)</strong> zählt nur futterrelevante Spuck-Ereignisse.</p>
<table><thead><tr><th>Hersteller &amp; Sorte</th><th>Portionen</th><th>Ø Gesamt</th>{heads}<th>Spucken (12h)</th></tr></thead><tbody>{rows}</tbody></table>
<h2>2. Spuck-Ereignisse der letzten 30 Tage</h2>
<table><thead><tr><th style="width:130px">Zeitpunkt</th><th style="width:120px">Tier</th><th style="width:190px">Kategorie</th><th>Notiz</th></tr></thead><tbody>{vrows}</tbody></table>
<h2>3. Einträge der letzten 30 Tage (gruppiert nach Runde)</h2>
<table><thead><tr><th style="width:130px">Zeitpunkt</th><th style="width:220px">Hersteller &amp; Sorte</th><th>Tiere &amp; Bewertung</th><th style="width:160px">Notiz</th></tr></thead><tbody>{frows}</tbody></table>
</div><script>window.addEventListener('load',()=>{{setTimeout(()=>window.print(),600)}});</script></body></html>"""
    return HTMLResponse(content=doc)


# ======================= STATISCHE DATEIEN & FRONTEND =======================

@app.get("/static/manifest.json")
def manifest():
    # Name der Anwendung kommt aus APP_NAME; alle anderen Felder stehen in static/manifest.json
    data = {"start_url": "/", "display": "standalone"}
    try:
        with open(os.path.join(STATIC_DIR, "manifest.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    data["name"] = APP_NAME
    data["short_name"] = APP_NAME
    return JSONResponse(data, media_type="application/manifest+json", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico")
def favicon():
    for name, mt in (("favicon.ico", "image/x-icon"), ("favicon-32.png", "image/png"), ("icon-192-v2.png", "image/png")):
        path = os.path.join(STATIC_DIR, name)
        if os.path.exists(path):
            return FileResponse(path, media_type=mt, headers={"Cache-Control": "public, max-age=86400"})
    raise HTTPException(status_code=404, detail="Kein Favicon vorhanden")


app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/sw.js")
def service_worker():
    # Service Worker muss im Root-Scope liegen, damit er die ganze App abdecken darf
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="text/javascript",
                        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@app.get("/")
def serve_index():
    # {{APP_NAME}} und <!--APP_CONFIG--> in index.html werden hier durch den Namen aus APP_NAME ersetzt
    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
        page = f.read()
    cfg = "<script>window.APP_NAME=" + json.dumps(APP_NAME).replace("</", "<\\/") + ";</script>"
    page = page.replace("<!--APP_CONFIG-->", cfg).replace("{{APP_NAME}}", html.escape(APP_NAME))
    return HTMLResponse(page, headers={"Cache-Control": "no-cache"})
