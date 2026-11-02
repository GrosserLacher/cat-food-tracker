"""
extras.py - Erweiterungen fuer den Cat Food Tracker

Neu:
  - Tierarten (Katze/Hund) und feste Reihenfolge der Tiere
  - Kataloge fuer Futter, Snacks und Getraenke (kind = food | snack | drink)
  - frei anlegbare Spuck-Kategorien
  - erweiterbares Bewertungssystem (2 bis 7 Stufen)
  - Standardgetraenk

Einbinden in main.py: siehe README_BACKEND.md bzw. die Hinweise im Chat.
Alle Aenderungen an der Datenbank sind additiv und werden beim Start automatisch migriert.
"""
import os
import secrets
import sqlite3
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

DB_PATH = os.path.join(os.environ.get("DATA_DIR", "/app/data"), "tracker.db")
router = APIRouter(prefix="/api")
KINDS = ("food", "snack", "drink")
SPECIES = ("cat", "dog")

DEFAULT_VOMIT = [
    ("food", "Unverdautes Futter", "\U0001F356", 1),
    ("bile_grass", "Galle / Schaum / Gras", "\U0001F33F", 0),
    ("hairball", "Haarballen", "\U0001F9F6", 0),
    ("other", "Sonstiges / Unklar", "\u2753", 1),
]


BUILTIN_VOMIT = {k for k, *_ in DEFAULT_VOMIT}
EN_VOMIT = {"food": "Undigested Food", "bile_grass": "Bile / Foam / Grass",
            "hairball": "Hairball", "other": "Other / Unclear"}


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _add_col(c, table, col, ddl):
    if col not in [r["name"] for r in c.execute(f"PRAGMA table_info({table})")]:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def migrate():
    """Nach init_db() in main.py aufrufen."""
    conn = _db()
    c = conn.cursor()
    _add_col(c, "cats", "species", "TEXT DEFAULT 'cat'")
    _add_col(c, "cats", "sort", "INTEGER DEFAULT 0")
    _add_col(c, "manufacturers", "kind", "TEXT DEFAULT 'food'")
    _add_col(c, "feedings", "kind", "TEXT DEFAULT 'food'")
    c.execute("UPDATE cats SET sort = id WHERE sort IS NULL OR sort = 0")
    c.execute("""
        CREATE TABLE IF NOT EXISTS vomit_types (
            key TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            emoji TEXT DEFAULT '',
            relevant INTEGER DEFAULT 1,
            hidden INTEGER DEFAULT 0,
            sort INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS rating_levels (
            score INTEGER PRIMARY KEY,
            label TEXT NOT NULL,
            emoji TEXT DEFAULT ''
        )
    """)
    if not c.execute("SELECT 1 FROM vomit_types").fetchone():
        c.executemany(
            "INSERT INTO vomit_types (key, label, emoji, relevant, sort) VALUES (?, ?, ?, ?, ?)",
            [(k, l, e, r, i) for i, (k, l, e, r) in enumerate(DEFAULT_VOMIT)],
        )
    if not c.execute("SELECT 1 FROM rating_levels").fetchone():
        s = {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")}
        c.executemany(
            "INSERT INTO rating_levels (score, label, emoji) VALUES (?, ?, ?)",
            [(3, s.get("rating_3", "Weggeatmet"), "\U0001F60B"),
             (2, s.get("rating_2", "Okay"), "\U0001F642"),
             (1, s.get("rating_1", "Verweigert"), "\U0001F641")],
        )
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('default_drink', 'Wasser')")
    _ensure_default_drink(c)
    conn.commit()
    conn.close()


def _ensure_default_drink(c):
    """Das Standardgetraenk muss immer als Sorte im Getraenke-Katalog existieren."""
    row = c.execute("SELECT value FROM settings WHERE key = 'default_drink'").fetchone()
    name = row["value"] if row else "Wasser"
    if c.execute("""SELECT 1 FROM foods f JOIN manufacturers m ON m.id = f.manufacturer_id
                    WHERE m.kind = 'drink' AND f.name = ?""", (name,)).fetchone():
        return
    m = c.execute("SELECT id, kind FROM manufacturers WHERE name = 'Standard'").fetchone()
    if m and m["kind"] == "drink":
        mid = m["id"]
    else:
        nm = "Standard" if not m else "Standard-Getraenke"
        r = c.execute("SELECT id FROM manufacturers WHERE name = ?", (nm,)).fetchone()
        mid = r["id"] if r else c.execute("INSERT INTO manufacturers (name, kind) VALUES (?, 'drink')", (nm,)).lastrowid
    c.execute("INSERT OR IGNORE INTO foods (manufacturer_id, name) VALUES (?, ?)", (mid, name))


# --- Hilfsfunktionen fuer main.py (CSV, PDF-Bericht, Validierung) -------------

def vomit_keys() -> List[str]:
    conn = _db()
    keys = [r["key"] for r in conn.execute("SELECT key FROM vomit_types WHERE hidden = 0")]
    conn.close()
    return keys


def relevant_keys() -> tuple:
    """Spuck-Kategorien, die als futterrelevant zaehlen (ersetzt ("food", "other"))."""
    conn = _db()
    keys = tuple(r["key"] for r in conn.execute("SELECT key FROM vomit_types WHERE relevant = 1"))
    conn.close()
    return keys


def vomit_label(key: str, lang: str = "de") -> str:
    conn = _db()
    if lang == "en" and key in EN_VOMIT:
        conn.close()
        return EN_VOMIT[key]
    row = conn.execute("SELECT label FROM vomit_types WHERE key = ?", (key or "food",)).fetchone()
    conn.close()
    return row["label"] if row else (key or "")


def rating_labels() -> dict:
    """{score: label} - ersetzt das feste r_labels-Dict (3/2/1)."""
    conn = _db()
    d = {r["score"]: r["label"] for r in conn.execute("SELECT score, label FROM rating_levels")}
    conn.close()
    return d


def max_score() -> int:
    """Hoechste Bewertungsstufe (ersetzt die feste 3 in den Berichten)."""
    conn = _db()
    m = conn.execute("SELECT MAX(score) AS m FROM rating_levels").fetchone()["m"]
    conn.close()
    return m or 3


# --- Tiere: Art und Reihenfolge ----------------------------------------------

class Order(BaseModel):
    ids: List[int]


class AnimalMeta(BaseModel):
    species: str


@router.get("/animals")
def animals():
    conn = _db()
    rows = conn.execute("SELECT id, name, species, sort FROM cats ORDER BY sort, id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.put("/animals/order")
def animals_order(data: Order):
    conn = _db()
    for pos, aid in enumerate(data.ids, start=1):
        conn.execute("UPDATE cats SET sort = ? WHERE id = ?", (pos, aid))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@router.put("/animals/{aid}")
def animal_meta(aid: int, data: AnimalMeta):
    if data.species not in SPECIES:
        raise HTTPException(status_code=400, detail="species muss 'cat' oder 'dog' sein")
    conn = _db()
    conn.execute("UPDATE cats SET species = ? WHERE id = ?", (data.species, aid))
    conn.commit()
    conn.close()
    return {"status": "ok"}


class AnimalNew(BaseModel):
    name: str
    species: str = "cat"


@router.post("/animals")
def animal_create(data: AnimalNew):
    name = data.name.strip()
    if not name or data.species not in SPECIES:
        raise HTTPException(status_code=400, detail="Name oder Tierart ungueltig")
    conn = _db()
    try:
        pos = conn.execute("SELECT COALESCE(MAX(sort), 0) + 1 AS n FROM cats").fetchone()["n"]
        cur = conn.execute("INSERT INTO cats (name, species, sort) VALUES (?, ?, ?)", (name, data.species, pos))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Ein Tier mit diesem Namen existiert bereits")
    conn.close()
    return {"id": cur.lastrowid, "name": name, "species": data.species}


# --- Kataloge: Futter, Snacks, Getraenke ---------------------------------------
# Sorten selbst werden weiter ueber /api/foods (POST/PUT/DELETE) verwaltet,
# Hersteller-Umbenennen/Loeschen ueber /api/manufacturers/{id}.

class CatalogManufacturer(BaseModel):
    name: str
    kind: str = "food"


@router.get("/catalog")
def catalog(kind: str = "food"):
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail="Unbekannte Art")
    conn = _db()
    out = []
    for m in conn.execute("SELECT id, name FROM manufacturers WHERE kind = ? ORDER BY name COLLATE NOCASE", (kind,)):
        foods = conn.execute(
            "SELECT id, name FROM foods WHERE manufacturer_id = ? ORDER BY name COLLATE NOCASE", (m["id"],)
        ).fetchall()
        out.append({"id": m["id"], "name": m["name"], "kind": kind, "foods": [dict(f) for f in foods]})
    conn.close()
    return out


@router.post("/catalog/manufacturers")
def catalog_add_manufacturer(data: CatalogManufacturer):
    name = data.name.strip()
    if not name or data.kind not in KINDS:
        raise HTTPException(status_code=400, detail="Name oder Art ungueltig")
    conn = _db()
    try:
        cur = conn.execute("INSERT INTO manufacturers (name, kind) VALUES (?, ?)", (name, data.kind))
        conn.commit()
        new_id = cur.lastrowid
    except sqlite3.IntegrityError:  # Name ist in der Tabelle global eindeutig
        row = conn.execute("SELECT id FROM manufacturers WHERE name = ?", (name,)).fetchone()
        new_id = row["id"]
    conn.close()
    return {"id": new_id, "name": name, "kind": data.kind}


# --- Standardgetraenk ---------------------------------------------------------

class DrinkIn(BaseModel):
    name: str


@router.get("/default-drink")
def get_default_drink():
    conn = _db()
    row = conn.execute("SELECT value FROM settings WHERE key = 'default_drink'").fetchone()
    conn.close()
    return {"name": row["value"] if row else "Wasser"}


@router.put("/default-drink")
def put_default_drink(data: DrinkIn):
    name = data.name.strip() or "Wasser"
    conn = _db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('default_drink', ?)", (name,))
    _ensure_default_drink(conn.cursor())
    conn.commit()
    conn.close()
    return {"name": name}


# --- Spuck-Kategorien -----------------------------------------------------------

class VomitTypeIn(BaseModel):
    label: str
    emoji: str = ""
    relevant: bool = True


@router.get("/vomit-types")
def vomit_types(include_hidden: bool = False):
    conn = _db()
    q = "SELECT key, label, emoji, relevant, hidden FROM vomit_types"
    if not include_hidden:
        q += " WHERE hidden = 0"
    rows = conn.execute(q + " ORDER BY sort, key").fetchall()
    conn.close()
    return [dict(r, relevant=bool(r["relevant"]), hidden=bool(r["hidden"])) for r in rows]


@router.post("/vomit-types")
def vomit_type_add(data: VomitTypeIn):
    label = data.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="Name darf nicht leer sein")
    key = "c_" + secrets.token_hex(3)
    conn = _db()
    pos = conn.execute("SELECT COALESCE(MAX(sort), 0) + 1 AS n FROM vomit_types").fetchone()["n"]
    conn.execute(
        "INSERT INTO vomit_types (key, label, emoji, relevant, sort) VALUES (?, ?, ?, ?, ?)",
        (key, label, data.emoji.strip(), int(data.relevant), pos),
    )
    conn.commit()
    conn.close()
    return {"key": key}


@router.put("/vomit-types/{key}")
def vomit_type_update(key: str, data: VomitTypeIn):
    conn = _db()
    conn.execute(
        "UPDATE vomit_types SET label = ?, emoji = ?, relevant = ? WHERE key = ?",
        (data.label.strip(), data.emoji.strip(), int(data.relevant), key),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@router.delete("/vomit-types/{key}")
def vomit_type_delete(key: str):
    # nur eigene Kategorien; ausblenden statt loeschen, damit alte Eintraege ihren Namen behalten
    if key in BUILTIN_VOMIT:
        raise HTTPException(status_code=400, detail="Standard-Kategorien koennen nicht geloescht werden")
    conn = _db()
    conn.execute("UPDATE vomit_types SET hidden = 1 WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    return {"status": "hidden"}


# --- Bewertungssystem -------------------------------------------------------------

class Level(BaseModel):
    score: int
    label: str
    emoji: str = ""


@router.get("/rating-levels")
def rating_levels():
    conn = _db()
    rows = conn.execute("SELECT score, label, emoji FROM rating_levels ORDER BY score DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.put("/rating-levels")
def rating_levels_put(levels: List[Level]):
    scores = sorted(l.score for l in levels)
    if not 2 <= len(levels) <= 7 or scores != list(range(1, len(levels) + 1)):
        raise HTTPException(status_code=400, detail="2 bis 7 Stufen mit den Punkten 1..N erforderlich")
    if any(not l.label.strip() for l in levels):
        raise HTTPException(status_code=400, detail="Jede Stufe braucht einen Namen")
    conn = _db()
    used = conn.execute("SELECT MAX(rating) AS m FROM feedings").fetchone()["m"] or 0
    if used > len(levels):
        conn.close()
        raise HTTPException(status_code=409, detail="Eine entfernte Stufe wird noch in Eintraegen verwendet")
    conn.execute("DELETE FROM rating_levels")
    conn.executemany(
        "INSERT INTO rating_levels (score, label, emoji) VALUES (?, ?, ?)",
        [(l.score, l.label.strip(), l.emoji.strip()) for l in levels],
    )
    for l in levels:  # Kompatibilitaet: alte Einstellungen rating_1..3 mitpflegen
        if l.score <= 3:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"rating_{l.score}", l.label.strip()))
    conn.commit()
    conn.close()
    return {"status": "ok"}
