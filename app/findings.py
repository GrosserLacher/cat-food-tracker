"""
findings.py – Foto-Dokumentation von Kot (Bristol-Skala) sowie Haut, Wunden, Ohren und Sonstigem.
Ablage: app/findings.py

Tabelle "findings" (additiv, wird beim Start angelegt):
  kind     stool | skin | wound | ear | other
  bristol  1..7 (nur bei kind = stool)
  details  kommagetrennt: blood, mucus, worms (nur bei Kot)
  images   JSON-Liste mit bis zu 4 Foto-Pfaden unter /uploads/

Endpunkte
  GET    /api/findings?kind=&limit=
  POST   /api/findings        (multipart: cat_name, kind, bristol, details, location, timestamp, notes, images[])
  PUT    /api/findings/{id}   (JSON: Zeit, Notiz, Stelle, Bristol, Details; Fotos bleiben unverändert)
  DELETE /api/findings/{id}   (löscht auch die Foto-Dateien)
"""
import json
import os
import sqlite3
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
DB_PATH = os.path.join(DATA_DIR, "tracker.db")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
router = APIRouter(prefix="/api/findings")

KINDS = ("stool", "skin", "wound", "ear", "other")
FLAGS = ("blood", "mucus", "worms")
MAX_PHOTOS = 4
MAX_BYTES = 12 * 1024 * 1024
UNKNOWN = ("Unbekannt", "Unknown")


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def migrate_findings():
    conn = _db()
    conn.execute("""CREATE TABLE IF NOT EXISTS findings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cat_name TEXT NOT NULL, kind TEXT NOT NULL, bristol INTEGER,
        details TEXT DEFAULT '', location TEXT DEFAULT '', timestamp TEXT NOT NULL, notes TEXT DEFAULT '',
        images TEXT DEFAULT '[]')""")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_findings_ts ON findings (timestamp)")
    conn.commit()
    conn.close()
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def _ext_from_bytes(head: bytes) -> Optional[str]:
    """Dateityp anhand der ersten Bytes bestimmen (nicht anhand des vom Client gesendeten Namens)."""
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return None


def _row(r) -> dict:
    d = dict(r)
    try:
        d["images"] = json.loads(d.get("images") or "[]")
    except ValueError:
        d["images"] = []
    d["details"] = [x for x in (d.get("details") or "").split(",") if x]
    return d


def _clean_details(raw: Optional[str]) -> str:
    return ",".join(x for x in FLAGS if x in {p.strip() for p in (raw or "").split(",")})


def _clean_ts(raw: Optional[str]) -> str:
    v = (raw or "").strip()[:16] or datetime.now().strftime("%Y-%m-%dT%H:%M")
    try:
        datetime.fromisoformat(v)
    except ValueError:
        raise HTTPException(status_code=400, detail="Zeitpunkt ungültig")
    return v


def _remove_files(paths):
    for rel in paths:
        p = os.path.join(UPLOAD_DIR, os.path.basename(rel))
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


@router.get("")
def list_findings(kind: Optional[str] = None, limit: int = 2000):
    conn = _db()
    q, params = "SELECT * FROM findings", []
    if kind:
        q += " WHERE kind = ?"
        params.append(kind)
    rows = conn.execute(q + " ORDER BY timestamp DESC, id DESC LIMIT ?", (*params, max(1, min(limit, 20000)))).fetchall()
    conn.close()
    return [_row(r) for r in rows]


@router.post("")
async def create_finding(
    cat_name: str = Form(...),
    kind: str = Form(...),
    bristol: Optional[int] = Form(None),
    details: Optional[str] = Form(""),
    location: Optional[str] = Form(""),
    timestamp: Optional[str] = Form(None),
    notes: Optional[str] = Form(""),
    images: List[UploadFile] = File(default=[]),
):
    if kind not in KINDS:
        raise HTTPException(status_code=400, detail="Unbekannte Art")
    if kind == "stool" and not (bristol and 1 <= bristol <= 7):
        raise HTTPException(status_code=400, detail="Bitte die Bristol-Stufe (1–7) wählen")
    if kind != "stool":
        bristol, details = None, ""
    ts = _clean_ts(timestamp)
    files = [f for f in images if f and f.filename]
    if len(files) > MAX_PHOTOS:
        raise HTTPException(status_code=400, detail=f"Höchstens {MAX_PHOTOS} Fotos pro Eintrag")
    conn = _db()
    names = {r["name"] for r in conn.execute("SELECT name FROM cats")}
    if cat_name not in names and cat_name not in UNKNOWN:
        conn.close()
        raise HTTPException(status_code=400, detail="Unbekanntes Tier")
    saved = []
    try:
        for i, f in enumerate(files):
            data = await f.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise HTTPException(status_code=413, detail="Foto zu groß (max. 12 MB)")
            ext = _ext_from_bytes(data[:16])
            if not ext:
                raise HTTPException(status_code=400, detail="Nur Fotos im Format JPG, PNG, WebP oder GIF erlaubt")
            name = f"finding_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{i}{ext}"
            with open(os.path.join(UPLOAD_DIR, name), "wb") as out:
                out.write(data)
            saved.append(f"/uploads/{name}")
        cur = conn.execute("INSERT INTO findings (cat_name, kind, bristol, details, location, timestamp, notes, images) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (cat_name, kind, bristol, _clean_details(details), (location or "").strip()[:80], ts,
                            (notes or "").strip()[:1000], json.dumps(saved)))
        conn.commit()
        new_id = cur.lastrowid
    except Exception:
        _remove_files(saved)   # bei Fehler keine verwaisten Dateien hinterlassen
        raise
    finally:
        conn.close()
    return {"id": new_id, "images": saved}


class FindingEdit(BaseModel):
    timestamp: Optional[str] = None
    notes: Optional[str] = None
    location: Optional[str] = None
    bristol: Optional[int] = None
    details: Optional[str] = None


@router.put("/{fid}")
def edit_finding(fid: int, data: FindingEdit):
    sent = data.model_dump(exclude_unset=True) if hasattr(data, "model_dump") else data.dict(exclude_unset=True)
    conn = _db()
    row = conn.execute("SELECT kind FROM findings WHERE id = ?", (fid,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    upd = {}
    try:
        if "timestamp" in sent:
            upd["timestamp"] = _clean_ts(sent["timestamp"])
        if "notes" in sent:
            upd["notes"] = (sent["notes"] or "").strip()[:1000]
        if "location" in sent:
            upd["location"] = (sent["location"] or "").strip()[:80]
        if row["kind"] == "stool":
            if "bristol" in sent:
                if not (sent["bristol"] and 1 <= sent["bristol"] <= 7):
                    raise HTTPException(status_code=400, detail="Bristol-Stufe 1–7")
                upd["bristol"] = sent["bristol"]
            if "details" in sent:
                upd["details"] = _clean_details(sent["details"])
    except HTTPException:
        conn.close()
        raise
    if upd:
        cols = ", ".join(f"{k} = ?" for k in upd)   # Spaltennamen stammen aus dem Code
        conn.execute(f"UPDATE findings SET {cols} WHERE id = ?", (*upd.values(), fid))
        conn.commit()
    conn.close()
    return {"status": "ok"}


@router.delete("/{fid}")
def delete_finding(fid: int):
    conn = _db()
    row = conn.execute("SELECT images FROM findings WHERE id = ?", (fid,)).fetchone()
    if row:
        try:
            _remove_files(json.loads(row["images"] or "[]"))
        except ValueError:
            pass
    conn.execute("DELETE FROM findings WHERE id = ?", (fid,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}
