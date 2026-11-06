"""
health.py – Gesundheitsdaten je Tier (Geburtstag, Größe, Gewicht, Temperatur und eigene Felder).
Der Geburtstag wird beim Anlegen eines Tieres und in den Stammdaten gepflegt (nicht im Gesundheits-Reiter).
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
    c.execute("""CREATE TABLE IF NOT EXISTS vaccinations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cat_id INTEGER NOT NULL, vaccine_name TEXT NOT NULL,
        date_given TEXT, valid_until TEXT)""")
    c.execute("CREATE INDEX IF NOT EXISTS ix_vacc_cat ON vaccinations (cat_id)")
    c.execute("""CREATE TABLE IF NOT EXISTS treatments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cat_id INTEGER NOT NULL, title TEXT NOT NULL,
        start_timestamp TEXT NOT NULL, end_timestamp TEXT, interval_hours INTEGER, notes TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS treatment_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, treatment_id INTEGER NOT NULL, timestamp TEXT NOT NULL,
        log_type TEXT NOT NULL, value_comment TEXT DEFAULT '')""")
    c.execute("CREATE INDEX IF NOT EXISTS ix_treat_cat ON treatments (cat_id, is_active)")
    c.execute("CREATE INDEX IF NOT EXISTS ix_treat_logs ON treatment_logs (treatment_id, timestamp)")
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


def clean_birthday(raw) -> Optional[str]:
    """Prueft ein Geburtsdatum (YYYY-MM-DD, nicht in der Zukunft). Leer -> None."""
    b = (raw or "").strip() or None
    if b:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", b):
            raise HTTPException(status_code=400, detail="Datum ungültig")
        try:
            if datetime.strptime(b, "%Y-%m-%d") > datetime.now():
                raise HTTPException(status_code=400, detail="Geburtstag liegt in der Zukunft")
        except ValueError:
            raise HTTPException(status_code=400, detail="Datum ungültig")
    return b


@router.put("/birthday/{cat_id}")
def set_birthday(cat_id: int, data: BirthdayIn):
    """Wird nur von den Stammdaten der App aufgerufen (Geburtstag ist nur dort editierbar)."""
    b = clean_birthday(data.birthday)
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


# --- Impfpass -----------------------------------------------------------------------------

class VaccinationIn(BaseModel):
    cat_id: int
    vaccine_name: str
    date_given: Optional[str] = None
    valid_until: Optional[str] = None


def _iso_date(raw, label: str) -> Optional[str]:
    v = (raw or "").strip()
    if not v:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        raise HTTPException(status_code=400, detail=f"{label}: Datum ungültig")
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label}: Datum ungültig")
    return v


@router.get("/vaccinations")
def list_vaccinations(cat_id: Optional[int] = None):
    conn = _db()
    q = "SELECT id, cat_id, vaccine_name, date_given, valid_until FROM vaccinations"
    rows = conn.execute(q + (" WHERE cat_id = ?" if cat_id is not None else "") + " ORDER BY COALESCE(valid_until, '9999'), id",
                        (cat_id,) if cat_id is not None else ()).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("/vaccinations")
def add_vaccination(data: VaccinationIn):
    name = data.vaccine_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name der Impfung fehlt")
    given, until = _iso_date(data.date_given, "Verabreicht"), _iso_date(data.valid_until, "Gültig bis")
    if given and until and until < given:
        raise HTTPException(status_code=400, detail="„Gültig bis“ liegt vor dem Impfdatum")
    conn = _db()
    if not conn.execute("SELECT 1 FROM cats WHERE id = ?", (data.cat_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Tier ungültig")
    cur = conn.execute("INSERT INTO vaccinations (cat_id, vaccine_name, date_given, valid_until) VALUES (?, ?, ?, ?)",
                       (data.cat_id, name[:80], given, until))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id}


@router.delete("/vaccinations/{vac_id}")
def delete_vaccination(vac_id: int):
    conn = _db()
    conn.execute("DELETE FROM vaccinations WHERE id = ?", (vac_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


# --- Behandlungen / Post-Op-Modus -------------------------------------------------------------
# Eine Behandlung hat einen Titel, Startzeit, optionales Erinnerungs-Intervall (Stunden), Notizen
# und beliebig viele Log-Einträge (Medikament, Wundkontrolle, Futteraufnahme, Allgemeinbefinden …).
# "Abschließen" setzt is_active = 0 und end_timestamp; die Behandlung bleibt für Berichte erhalten.

def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def _clean_ts(raw: Optional[str], label: str = "Zeitpunkt") -> str:
    v = (raw or "").strip()[:16]
    try:
        datetime.fromisoformat(v)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label} ungültig")
    return v


def _clean_interval(v: Optional[int]) -> Optional[int]:
    if v is None:
        return None
    if not 1 <= int(v) <= 168:
        raise HTTPException(status_code=400, detail="Intervall muss zwischen 1 und 168 Stunden liegen")
    return int(v)


class TreatmentIn(BaseModel):
    cat_id: Optional[int] = None
    title: Optional[str] = None
    start_timestamp: Optional[str] = None
    end_timestamp: Optional[str] = None
    interval_hours: Optional[int] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class TreatmentLogIn(BaseModel):
    timestamp: Optional[str] = None
    log_type: str
    value_comment: Optional[str] = ""


def _sent_fields(data: BaseModel) -> dict:
    return data.model_dump(exclude_unset=True) if hasattr(data, "model_dump") else data.dict(exclude_unset=True)


def _treatment_rows(conn, where: str = "", params: tuple = ()):
    rows = conn.execute("SELECT t.*, c.name AS cat_name FROM treatments t LEFT JOIN cats c ON c.id = t.cat_id " + where +
                        " ORDER BY t.is_active DESC, t.start_timestamp DESC, t.id DESC", params).fetchall()
    out = []
    for r in rows:
        d = dict(r, is_active=bool(r["is_active"]))
        d["logs"] = [dict(x) for x in conn.execute(
            "SELECT id, treatment_id, timestamp, log_type, value_comment FROM treatment_logs WHERE treatment_id = ? "
            "ORDER BY timestamp, id", (r["id"],))]
        out.append(d)
    return out


def _title_taken(conn, cat_id: int, title: str, exclude_id: int = 0) -> bool:
    return bool(conn.execute("SELECT 1 FROM treatments WHERE cat_id = ? AND lower(title) = lower(?) AND id != ?",
                             (cat_id, title, exclude_id)).fetchone())


@router.get("/treatments")
def list_treatments(cat_id: Optional[int] = None, active: Optional[bool] = None):
    where, params = [], []
    if cat_id is not None:
        where.append("t.cat_id = ?")
        params.append(cat_id)
    if active is not None:
        where.append("t.is_active = ?")
        params.append(int(active))
    conn = _db()
    out = _treatment_rows(conn, ("WHERE " + " AND ".join(where)) if where else "", tuple(params))
    conn.close()
    return out


@router.post("/treatments")
def add_treatment(data: TreatmentIn):
    title = (data.title or "").strip()
    if not title or data.cat_id is None:
        raise HTTPException(status_code=400, detail="Tier und Bezeichnung sind erforderlich")
    start = _clean_ts(data.start_timestamp, "Startzeitpunkt") if data.start_timestamp else _now_ts()
    interval = _clean_interval(data.interval_hours)
    conn = _db()
    if not conn.execute("SELECT 1 FROM cats WHERE id = ?", (data.cat_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Tier ungültig")
    if _title_taken(conn, data.cat_id, title):
        conn.close()
        raise HTTPException(status_code=400, detail="Für dieses Tier gibt es bereits eine Behandlung mit dieser Bezeichnung")
    cur = conn.execute("INSERT INTO treatments (cat_id, title, start_timestamp, interval_hours, notes, is_active) VALUES (?, ?, ?, ?, ?, 1)",
                       (data.cat_id, title[:120], start, interval, (data.notes or "").strip()[:2000]))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id}


@router.put("/treatments/{tid}")
def edit_treatment(tid: int, data: TreatmentIn):
    """Nur gesendete Felder werden geändert. is_active=false schließt die Behandlung ab (Endzeit = jetzt)."""
    sent = _sent_fields(data)
    conn = _db()
    row = conn.execute("SELECT * FROM treatments WHERE id = ?", (tid,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Behandlung nicht gefunden")
    upd = {}
    if "title" in sent:
        title = (sent["title"] or "").strip()
        if not title:
            conn.close()
            raise HTTPException(status_code=400, detail="Bezeichnung darf nicht leer sein")
        if _title_taken(conn, row["cat_id"], title, tid):
            conn.close()
            raise HTTPException(status_code=400, detail="Für dieses Tier gibt es bereits eine Behandlung mit dieser Bezeichnung")
        upd["title"] = title[:120]
    try:
        if "start_timestamp" in sent:
            upd["start_timestamp"] = _clean_ts(sent["start_timestamp"], "Startzeitpunkt")
        if "interval_hours" in sent:
            upd["interval_hours"] = _clean_interval(sent["interval_hours"])
        if "notes" in sent:
            upd["notes"] = (sent["notes"] or "").strip()[:2000]
        if "end_timestamp" in sent:
            upd["end_timestamp"] = _clean_ts(sent["end_timestamp"], "Endzeitpunkt") if sent["end_timestamp"] else None
        if "is_active" in sent:
            upd["is_active"] = int(bool(sent["is_active"]))
            if not sent["is_active"] and "end_timestamp" not in sent:
                upd["end_timestamp"] = _now_ts()
            if sent["is_active"]:
                upd["end_timestamp"] = None
    except HTTPException:
        conn.close()
        raise
    if upd:
        cols = ", ".join(f"{k} = ?" for k in upd)   # Spaltennamen stammen aus dem Code, nicht vom Client
        conn.execute(f"UPDATE treatments SET {cols} WHERE id = ?", (*upd.values(), tid))
        conn.commit()
    conn.close()
    return {"status": "ok"}


@router.delete("/treatments/{tid}")
def delete_treatment(tid: int):
    """Löscht die Behandlung samt Log-Einträgen endgültig (zum Archivieren stattdessen abschließen)."""
    conn = _db()
    conn.execute("DELETE FROM treatment_logs WHERE treatment_id = ?", (tid,))
    conn.execute("DELETE FROM treatments WHERE id = ?", (tid,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


@router.post("/treatments/{tid}/logs")
def add_treatment_log(tid: int, data: TreatmentLogIn):
    kind = data.log_type.strip()
    if not kind:
        raise HTTPException(status_code=400, detail="Art des Eintrags fehlt")
    ts = _clean_ts(data.timestamp) if data.timestamp else _now_ts()
    conn = _db()
    if not conn.execute("SELECT 1 FROM treatments WHERE id = ?", (tid,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Behandlung nicht gefunden")
    cur = conn.execute("INSERT INTO treatment_logs (treatment_id, timestamp, log_type, value_comment) VALUES (?, ?, ?, ?)",
                       (tid, ts, kind[:40], (data.value_comment or "").strip()[:1000]))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id}


@router.delete("/treatments/{tid}/logs/{log_id}")
def delete_treatment_log(tid: int, log_id: int):
    conn = _db()
    conn.execute("DELETE FROM treatment_logs WHERE id = ? AND treatment_id = ?", (log_id, tid))
    conn.commit()
    conn.close()
    return {"status": "deleted"}
