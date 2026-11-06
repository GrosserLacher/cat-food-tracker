"""
meds.py – Präparate (Medikamente, Pasten, Pulver, Supplemente).
Ablage: app/meds.py

Katalog  : /api/meds            (Name + Standarddosis, in den Stammdaten pflegbar)
Einträge : /api/med-logs        (Tier(e), Präparat, Dosis, "zusammen mit der Fütterung", Zeitpunkt, Notiz)
Mehrere Tiere in einem Vorgang teilen sich eine batch_id (wie bei den Fütterungen).
Löschen eines Präparats blendet es nur aus; bisherige Einträge behalten ihren Namen.
"""
import os
import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
DB_PATH = os.path.join(DATA_DIR, "tracker.db")
router = APIRouter(prefix="/api")


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_meds():
    """Idempotent: legt die Tabellen an, bestehende Daten bleiben unberührt."""
    conn = _db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS meds (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, dose TEXT DEFAULT '',
        hidden INTEGER DEFAULT 0, sort INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS med_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT NOT NULL, cat_id INTEGER, cat_name TEXT NOT NULL,
        med_id INTEGER, med_name TEXT NOT NULL, dose TEXT DEFAULT '', with_food INTEGER DEFAULT 0,
        timestamp TEXT NOT NULL, notes TEXT DEFAULT '')""")
    c.execute("CREATE INDEX IF NOT EXISTS ix_med_logs_ts ON med_logs (timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS ix_med_logs_batch ON med_logs (batch_id)")
    conn.commit()
    conn.close()


class MedIn(BaseModel):
    name: str
    dose: str = ""


class MedLogIn(BaseModel):
    cat_names: List[str]
    med_id: int
    dose: str = ""
    with_food: bool = False
    timestamp: Optional[str] = None
    notes: Optional[str] = ""


@router.get("/meds")
def list_meds():
    conn = _db()
    rows = conn.execute("SELECT id, name, dose FROM meds WHERE hidden = 0 ORDER BY sort, name COLLATE NOCASE").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/meds")
def add_med(data: MedIn):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = _db()
    if conn.execute("SELECT 1 FROM meds WHERE hidden = 0 AND lower(name) = lower(?)", (name,)).fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Dieses Präparat existiert bereits")
    nxt = conn.execute("SELECT COALESCE(MAX(sort), 0) + 1 AS n FROM meds").fetchone()["n"]
    cur = conn.execute("INSERT INTO meds (name, dose, sort) VALUES (?, ?, ?)", (name, data.dose.strip()[:60], nxt))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id, "name": name, "dose": data.dose.strip()[:60]}


@router.put("/meds/{med_id}")
def edit_med(med_id: int, data: MedIn):
    """Umbenennen ändert auch den Namen in bereits vorhandenen Einträgen (wie bei Herstellern)."""
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = _db()
    if conn.execute("SELECT 1 FROM meds WHERE hidden = 0 AND id != ? AND lower(name) = lower(?)", (med_id, name)).fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Dieses Präparat existiert bereits")
    conn.execute("UPDATE meds SET name = ?, dose = ? WHERE id = ?", (name, data.dose.strip()[:60], med_id))
    conn.execute("UPDATE med_logs SET med_name = ? WHERE med_id = ?", (name, med_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@router.delete("/meds/{med_id}")
def hide_med(med_id: int):
    conn = _db()
    conn.execute("UPDATE meds SET hidden = 1 WHERE id = ?", (med_id,))
    conn.commit()
    conn.close()
    return {"status": "hidden"}


@router.get("/med-logs")
def list_logs(limit: int = 2000):
    conn = _db()
    rows = conn.execute("SELECT * FROM med_logs ORDER BY timestamp DESC, id DESC LIMIT ?", (max(1, min(limit, 20000)),)).fetchall()
    conn.close()
    return [dict(r, with_food=bool(r["with_food"])) for r in rows]


@router.post("/med-logs")
def add_log(data: MedLogIn):
    names = [n for n in dict.fromkeys(x.strip() for x in data.cat_names) if n]
    if not names:
        raise HTTPException(status_code=400, detail="Bitte mindestens ein Tier wählen")
    ts = (data.timestamp or datetime.now().strftime("%Y-%m-%dT%H:%M"))[:16]
    try:
        datetime.fromisoformat(ts)
    except ValueError:
        raise HTTPException(status_code=400, detail="Zeitpunkt ungültig")
    conn = _db()
    med = conn.execute("SELECT id, name FROM meds WHERE id = ?", (data.med_id,)).fetchone()
    if not med:
        conn.close()
        raise HTTPException(status_code=400, detail="Präparat nicht gefunden")
    cats = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM cats")}
    missing = [n for n in names if n not in cats]
    if missing:
        conn.close()
        raise HTTPException(status_code=400, detail="Unbekanntes Tier: " + ", ".join(missing))
    batch = uuid.uuid4().hex
    for n in names:
        conn.execute("INSERT INTO med_logs (batch_id, cat_id, cat_name, med_id, med_name, dose, with_food, timestamp, notes) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     (batch, cats[n], n, med["id"], med["name"], data.dose.strip()[:60], int(data.with_food), ts, (data.notes or "").strip()))
    conn.commit()
    conn.close()
    return {"batch_id": batch, "count": len(names)}


class MedLogEdit(BaseModel):
    dose: str = ""
    with_food: bool = False
    timestamp: str
    notes: Optional[str] = ""


@router.put("/med-logs/batch/{batch_id}")
def edit_batch(batch_id: str, data: MedLogEdit):
    """Dosis, Fütterungs-Haken, Zeitpunkt und Anmerkung eines Eintrags ändern (Tier und Präparat bleiben)."""
    ts = data.timestamp[:16]
    try:
        datetime.fromisoformat(ts)
    except ValueError:
        raise HTTPException(status_code=400, detail="Zeitpunkt ungültig")
    conn = _db()
    cur = conn.execute("UPDATE med_logs SET dose = ?, with_food = ?, timestamp = ?, notes = ? WHERE batch_id = ?",
                       (data.dose.strip()[:60], int(data.with_food), ts, (data.notes or "").strip(), batch_id))
    conn.commit()
    conn.close()
    if not cur.rowcount:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    return {"status": "ok"}


@router.delete("/med-logs/batch/{batch_id}")
def delete_batch(batch_id: str):
    conn = _db()
    conn.execute("DELETE FROM med_logs WHERE batch_id = ?", (batch_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}
