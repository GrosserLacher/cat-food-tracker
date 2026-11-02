"""
push.py – Web-Push-Erinnerung an die Fütterung.
Ablage: app/push.py     Zusätzliches Paket im Dockerfile:  pip install pywebpush

Ablauf
  * Aus den Futter-Einträgen der letzten 30 Tage werden die üblichen Fütterungszeiten berechnet
    (Einträge innerhalb von 90 Minuten bilden eine Zeit; sie muss an mind. 3 Tagen und an mind.
    40 % der aktiven Tage vorkommen). Snacks und Getränke zählen nicht.
  * Etwa 2 Stunden nach so einer Zeit wird eine Erinnerung gesendet, falls seit 90 Minuten vor
    der Zeit kein Futter eingetragen wurde. Pro Zeit und Tag höchstens eine Nachricht.
  * Die Ortszeit kommt vom Gerät (wird beim Anmelden der Erinnerung und bei jedem App-Start
    mitgeschickt), die Zeitzone des Containers spielt keine Rolle.
"""
import asyncio
import base64
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

try:
    from pywebpush import webpush, WebPushException
    from py_vapid import Vapid
    from cryptography.hazmat.primitives import serialization
    HAVE_PUSH = True
except Exception:  # Paket nicht installiert: App läuft weiter, nur ohne Push
    HAVE_PUSH = False

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
DB_PATH = os.path.join(DATA_DIR, "tracker.db")
KEY_PATH = os.path.join(DATA_DIR, "vapid_private.pem")
CONTACT = os.environ.get("PUSH_CONTACT", "mailto:admin@example.com")
DELAY_MIN = 120      # Erinnerung so viele Minuten nach der üblichen Zeit
WINDOW_MIN = 90      # danach wird nicht mehr erinnert
router = APIRouter(prefix="/api/push")

TEXT = {
    "de": ("Futter-Erinnerung", "Gegen {t} wird normalerweise gefüttert – heute ist noch keine Fütterung eingetragen."),
    "en": ("Feeding reminder", "Feeding usually happens around {t} – nothing logged yet today."),
}


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS push_subs (
        endpoint TEXT PRIMARY KEY, user_id INTEGER, p256dh TEXT, auth TEXT, lang TEXT DEFAULT 'de',
        tz INTEGER DEFAULT 0, created REAL)""")
    conn.execute("CREATE TABLE IF NOT EXISTS push_sent (day TEXT, slot TEXT, tz INTEGER, PRIMARY KEY (day, slot, tz))")
    return conn


def _vapid():
    if os.path.exists(KEY_PATH):
        return Vapid.from_file(KEY_PATH)
    v = Vapid()
    v.generate_keys()
    v.save_key(KEY_PATH)
    return v


def public_key() -> str:
    raw = _vapid().public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def typical_slots(conn, now_local: datetime, days: int = 30) -> List[int]:
    """Übliche Fütterungszeiten (Minuten seit Mitternacht), nur Futter."""
    since = (now_local - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")
    rows = conn.execute("SELECT DISTINCT COALESCE(batch_id, id) AS b, timestamp FROM feedings "
                        "WHERE COALESCE(kind, 'food') = 'food' AND timestamp >= ?", (since,)).fetchall()
    pts = []
    for r in rows:
        try:
            t = datetime.fromisoformat(r["timestamp"])
        except ValueError:
            continue
        pts.append((t.date(), t.hour * 60 + t.minute))
    if not pts:
        return []
    active_days = {d for d, _ in pts}
    pts.sort(key=lambda p: p[1])
    clusters, cur = [], [pts[0]]
    for p in pts[1:]:
        if p[1] - cur[-1][1] > 90:
            clusters.append(cur)
            cur = [p]
        else:
            cur.append(p)
    clusters.append(cur)
    need = max(3, int(0.4 * len(active_days) + 0.5))
    return sorted(round(sum(m for _, m in cl) / len(cl)) for cl in clusters if len({d for d, _ in cl}) >= need)


def due_slots(conn, now_local: datetime, tz: int) -> List[int]:
    today = now_local.date().isoformat()
    now_min = now_local.hour * 60 + now_local.minute
    out = []
    for avg in typical_slots(conn, now_local):
        fire = avg + DELAY_MIN
        if fire >= 24 * 60 or not (fire <= now_min < fire + WINDOW_MIN):
            continue
        if conn.execute("SELECT 1 FROM push_sent WHERE day = ? AND slot = ? AND tz = ?", (today, str(avg), tz)).fetchone():
            continue
        start = max(0, avg - 90)
        since = f"{today}T{start // 60:02d}:{start % 60:02d}"
        if conn.execute("SELECT 1 FROM feedings WHERE COALESCE(kind, 'food') = 'food' AND timestamp >= ?", (since,)).fetchone():
            continue
        out.append(avg)
    return out


def _send(sub, payload: dict):
    try:
        webpush(subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=json.dumps(payload), vapid_private_key=KEY_PATH, vapid_claims={"sub": CONTACT}, ttl=3600)
        return True, ""
    except WebPushException as e:
        code = getattr(e.response, "status_code", None)
        if code in (404, 410):
            c = _db()
            c.execute("DELETE FROM push_subs WHERE endpoint = ?", (sub["endpoint"],))
            c.commit()
            c.close()
        return False, f"{code or ''} {e}"[:200]
    except Exception as e:  # Netzwerkfehler o. Ä.
        return False, str(e)[:200]


def _message(lang: str, avg: int) -> dict:
    title, body = TEXT.get(lang, TEXT["de"])
    return {"title": title, "body": body.format(t=f"{avg // 60:02d}:{avg % 60:02d}"), "url": "/", "tag": "feeding-reminder"}


def run_once(now_utc: datetime = None, send=None):
    """Prüft alle Zeitzonen der angemeldeten Geräte und sendet fällige Erinnerungen. Gibt die Anzahl zurück."""
    send = send or _send
    now_utc = now_utc or datetime.utcnow()
    conn = _db()
    subs = [dict(r) for r in conn.execute("SELECT * FROM push_subs").fetchall()]
    sent = 0
    try:
        for tz in sorted({s["tz"] for s in subs}):
            now_local = now_utc + timedelta(minutes=tz)
            for avg in due_slots(conn, now_local, tz):
                conn.execute("INSERT OR IGNORE INTO push_sent (day, slot, tz) VALUES (?, ?, ?)",
                             (now_local.date().isoformat(), str(avg), tz))
                conn.commit()
                for s in (x for x in subs if x["tz"] == tz):
                    if send(s, _message(s["lang"], avg))[0]:
                        sent += 1
        conn.execute("DELETE FROM push_sent WHERE day < ?", ((now_utc - timedelta(days=3)).date().isoformat(),))
        conn.commit()
    finally:
        conn.close()
    return sent


async def _loop():
    while True:
        try:
            await asyncio.to_thread(run_once)
        except Exception as e:
            print("push-loop:", e)
        await asyncio.sleep(300)


def start_scheduler():
    if HAVE_PUSH:
        asyncio.get_event_loop().create_task(_loop())


class SubIn(BaseModel):
    endpoint: str
    keys: Dict[str, str]
    lang: str = "de"
    tz: int = 0


class UnsubIn(BaseModel):
    endpoint: str


@router.get("/status")
def status():
    return {"available": HAVE_PUSH, "public_key": public_key() if HAVE_PUSH else None}


@router.get("/preview")
def preview():
    conn = _db()
    slots = typical_slots(conn, datetime.now())
    conn.close()
    f = lambda m: f"{m // 60:02d}:{m % 60:02d}"
    return [{"time": f(m), "reminder": f(m + DELAY_MIN)} for m in slots if m + DELAY_MIN < 24 * 60]


@router.post("/subscribe")
def subscribe(data: SubIn, request: Request):
    if not HAVE_PUSH:
        raise HTTPException(status_code=501, detail="Push ist auf dem Server nicht installiert")
    if "p256dh" not in data.keys or "auth" not in data.keys:
        raise HTTPException(status_code=400, detail="Abo unvollständig")
    conn = _db()
    conn.execute("INSERT OR REPLACE INTO push_subs (endpoint, user_id, p256dh, auth, lang, tz, created) VALUES (?,?,?,?,?,?,?)",
                 (data.endpoint, request.state.user["id"], data.keys["p256dh"], data.keys["auth"],
                  data.lang if data.lang in TEXT else "de", max(-840, min(840, data.tz)), time.time()))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@router.post("/unsubscribe")
def unsubscribe(data: UnsubIn):
    conn = _db()
    conn.execute("DELETE FROM push_subs WHERE endpoint = ?", (data.endpoint,))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@router.post("/test")
def test(request: Request):
    if not HAVE_PUSH:
        raise HTTPException(status_code=501, detail="Push ist auf dem Server nicht installiert")
    conn = _db()
    subs = [dict(r) for r in conn.execute("SELECT * FROM push_subs WHERE user_id = ?", (request.state.user["id"],)).fetchall()]
    conn.close()
    sent, errors = 0, []
    for s in subs:
        ok, err = _send(s, _message(s["lang"], 8 * 60 + 30))
        sent += 1 if ok else 0
        if err:
            errors.append(err)
    return {"sent": sent, "errors": errors}
