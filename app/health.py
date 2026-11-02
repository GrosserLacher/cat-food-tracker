"""
health.py – Gesundheitsdaten je Tier (Geburtstag, Größe, Gewicht, Temperatur und eigene Felder).
Ablage: app/health.py
"""
import math
import os
import re
import sqlite3
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
DB_PATH = os.path.join(DATA_DIR, "tracker.db")
router = APIRouter(prefix="/api/health")
DEFAULT_FIELDS = [("Größe", "cm"), ("Gewicht", "kg"), ("Temperatur", "°C")]


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_health():
    """Idempotent: legt Spalte und Tabellen an, bestehende Daten bleiben erhalten."""
    conn = _db()
    c = conn.cursor()
    cols = [r["name"] for r in c.execute("PRAGMA table_info(cats)").fetchall()]
    if "birthday" not in cols:
        c.execute("ALTER TABLE cats ADD COLUMN birthday TEXT")
    c.execute("""CREATE TABLE IF NOT EXISTS health_fields (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, unit TEXT DEFAULT '',
        builtin INTEGER DEFAULT 0, hidden INTEGER DEFAULT 0, sort INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS health_values (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cat_id INTEGER NOT NULL, field_id INTEGER NOT NULL,
        value REAL NOT NULL, ts TEXT NOT NULL, note TEXT DEFAULT '')""")
    c.execute("CREATE INDEX IF NOT EXISTS ix_health_values ON health_values (cat_id, field_id, ts)")
    if not c.execute("SELECT 1 FROM health_fields").fetchone():
        for i, (name, unit) in enumerate(DEFAULT_FIELDS, start=1):
            c.execute("INSERT INTO health_fields (name, unit, builtin, sort) VALUES (?, ?, 1, ?)", (name, unit, i))
    conn.commit()
    conn.close()


class FieldIn(BaseModel):
    name: str
    unit: str = ""


class ValueIn(BaseModel):
    cat_id: int
    field_id: int
    value: float
    ts: Optional[str] = None
    note: Optional[str] = ""


class BirthdayIn(BaseModel):
    birthday: Optional[str] = None


@router.get("/overview")
def overview():
    conn = _db()
    fields = conn.execute("SELECT id, name, unit, builtin FROM health_fields WHERE hidden = 0 ORDER BY sort, id").fetchall()
    births = conn.execute("SELECT id, birthday FROM cats WHERE birthday IS NOT NULL AND birthday != ''").fetchall()
    conn.close()
    return {"fields": [dict(f, builtin=bool(f["builtin"])) for f in fields],
            "birthdays": {str(b["id"]): b["birthday"] for b in births}}


@router.put("/birthday/{cat_id}")
def set_birthday(cat_id: int, data: BirthdayIn):
    b = (data.birthday or "").strip() or None
    if b:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", b):
            raise HTTPException(status_code=400, detail="Datum ungültig")
        try:
            if datetime.strptime(b, "%Y-%m-%d") > datetime.now():
                raise HTTPException(status_code=400, detail="Geburtstag liegt in der Zukunft")
        except ValueError:
            raise HTTPException(status_code=400, detail="Datum ungültig")
    conn = _db()
    conn.execute("UPDATE cats SET birthday = ? WHERE id = ?", (b, cat_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@router.post("/fields")
def add_field(data: FieldIn):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = _db()
    dup = conn.execute("SELECT 1 FROM health_fields WHERE hidden = 0 AND lower(name) = lower(?)", (name,)).fetchone()
    if dup:
        conn.close()
        raise HTTPException(status_code=400, detail="Dieses Feld existiert bereits")
    nxt = (conn.execute("SELECT COALESCE(MAX(sort), 0) + 1 AS n FROM health_fields").fetchone()["n"])
    cur = conn.execute("INSERT INTO health_fields (name, unit, sort) VALUES (?, ?, ?)", (name, data.unit.strip()[:12], nxt))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id, "name": name}


@router.put("/fields/{field_id}")
def edit_field(field_id: int, data: FieldIn):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    conn = _db()
    conn.execute("UPDATE health_fields SET name = ?, unit = ? WHERE id = ?", (name, data.unit.strip()[:12], field_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@router.delete("/fields/{field_id}")
def hide_field(field_id: int):
    """Eigene Felder werden ausgeblendet (Werte bleiben erhalten); Standardfelder sind geschützt."""
    conn = _db()
    row = conn.execute("SELECT builtin FROM health_fields WHERE id = ?", (field_id,)).fetchone()
    if row and row["builtin"]:
        conn.close()
        raise HTTPException(status_code=400, detail="Standardfelder können nicht gelöscht werden")
    conn.execute("UPDATE health_fields SET hidden = 1 WHERE id = ?", (field_id,))
    conn.commit()
    conn.close()
    return {"status": "hidden"}


@router.get("/values")
def list_values(limit: int = 5000, cat_id: Optional[int] = None):
    conn = _db()
    if cat_id is not None:
        rows = conn.execute("SELECT * FROM health_values WHERE cat_id = ? ORDER BY ts DESC, id DESC LIMIT ?", (cat_id, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM health_values ORDER BY ts DESC, id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/values")
def add_value(data: ValueIn):
    if not math.isfinite(data.value) or abs(data.value) > 1e6:
        raise HTTPException(status_code=400, detail="Wert ungültig")
    conn = _db()
    if not conn.execute("SELECT 1 FROM cats WHERE id = ?", (data.cat_id,)).fetchone() or \
       not conn.execute("SELECT 1 FROM health_fields WHERE id = ?", (data.field_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Tier oder Feld ungültig")
    ts = data.ts or datetime.now().strftime("%Y-%m-%dT%H:%M")
    cur = conn.execute("INSERT INTO health_values (cat_id, field_id, value, ts, note) VALUES (?, ?, ?, ?, ?)",
                       (data.cat_id, data.field_id, data.value, ts, data.note or ""))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id}


@router.delete("/values/{value_id}")
def delete_value(value_id: int):
    conn = _db()
    conn.execute("DELETE FROM health_values WHERE id = ?", (value_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}
