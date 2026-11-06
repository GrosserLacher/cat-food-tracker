"""
push.py – Web-Push-Erinnerung an die Fütterung.
Ablage: app/push.py     Zusätzliches Paket im Dockerfile:  pip install pywebpush

Ablauf
  * Aus den Futter-Einträgen der letzten 30 Tage werden die üblichen Fütterungszeiten berechnet
    (Einträge innerhalb von 90 Minuten bilden eine Zeit; sie muss an mind. 3 Tagen und an mind.
    40 % der aktiven Tage vorkommen). Snacks und Getränke zählen nicht.
  * Etwa 2 Stunden nach so einer Zeit wird eine Erinnerung gesendet, falls seit 90 Minuten vor
    der Zeit kein Futter eingetragen wurde. Pro Zeit und Tag höchstens eine Nachricht.
  * Geburtstage: 14 Tage vorher kommt eine Vorab-Erinnerung, am Geburtstag selbst eine
    "Happy Birthday"-Nachricht – jeweils um 09:00 Uhr Ortszeit des Geräts (mit wechselnden Texten).
    Wurde der Server um 09:00 Uhr nicht erreicht, wird bis 12:00 Uhr nachgeholt. Pro Tier und Anlass nur einmal.
  * Impfungen: Läuft eine eingetragene Impfung (valid_until) in den nächsten 30 Tagen ab, kommt um 09:00 Uhr
    eine Erinnerung. Weitere Erinnerungen folgen 7 Tage vorher und am Ablauftag (je Stufe nur einmal).
    Ist für dasselbe Tier und dieselbe Impfung bereits ein neuerer Eintrag vorhanden, wird nicht erinnert.
  * Die Ortszeit kommt vom Gerät (wird beim Anmelden der Erinnerung und bei jedem App-Start
    mitgeschickt), die Zeitzone des Containers spielt keine Rolle.
"""
import asyncio
import base64
import json
import os
import random
import sqlite3
import time
from datetime import date, datetime, timedelta
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
BDAY_HOUR = 9        # Uhrzeit der Geburtstags-Nachrichten (Ortszeit des Geräts)
BDAY_WINDOW = 180   # so viele Minuten nach 09:00 wird noch nachgeholt (falls der Server nicht lief)
VAC_STAGES = (30, 7, 0)   # Erinnerungsstufen: Tage vor Ablauf der Impfung
BDAY_ADVANCE = 14   # Vorab-Erinnerung so viele Tage vor dem Geburtstag
DELAY_MIN = 120      # Erinnerung so viele Minuten nach der üblichen Zeit
WINDOW_MIN = 90      # danach wird nicht mehr erinnert
router = APIRouter(prefix="/api/push")

TEXT = {
    "de": ("Futter-Erinnerung", "Gegen {t} wird normalerweise gefüttert – heute ist noch keine Fütterung eingetragen."),
    "en": ("Feeding reminder", "Feeding usually happens around {t} – nothing logged yet today."),
}


# --- Geburtstags-Texte -----------------------------------------------------------------------
# Platzhalter: {name} Name des Tieres, {age} z. B. "5 Jahre", {years} z. B. 5, {date} z. B. 12.03.
# "any" gilt für alle Tiere, "cat"/"dog" kommen je nach Tierart zusätzlich in den Lostopf.
# Pro Tier und Jahr wird einmal ausgelost (auf allen Geräten derselbe Text).
BDAY_TEXT = {
    "de": {
        "pre": {
            "any": [
                ("Noch 14 Tage bis zur Party 🎉", "{name} wird am {date} {age} alt. Höchste Zeit, Leckerli-Törtchen zu planen!"),
                ("Save the Date 📅", "In 14 Tagen feiert {name} Geburtstag ({age}!). Die Gästeliste ist streng geheim."),
                ("Geburtstags-Countdown läuft ⏳", "Nur noch 14 Tage, dann ist {name} {age} alt. Geschenke bitte rechtzeitig besorgen!"),
                ("Psst – nicht verraten! 🤫", "{name} hat am {date} Geburtstag und weiß noch von nichts. Zeit für Überraschungen!"),
                ("Zwei Wochen noch 🎈", "Am {date} wird {name} {age} alt. Wie wäre es mit einem Extra-Napf als Geschenk?"),
                ("Party-Planung ⏰", "{name} wird bald {age} alt! 14 Tage Zeit, den besten Geburtstagsnapf aller Zeiten zu planen."),
            ],
            "cat": [
                ("Miau-Alarm 🐱", "In 14 Tagen wird {name} {age} alt. Der Kratzbaum bekommt schon mal Girlanden."),
                ("Samtpfoten-Gala 🐾", "{name} feiert am {date} – das Sofa ist bereits als Ehrenplatz reserviert."),
            ],
            "dog": [
                ("Wuff-Alarm 🐶", "In 14 Tagen wird {name} {age} alt. Die Stöckchen-Torte ist noch nicht bestellt!"),
                ("Gassi-Gala 🦴", "{name} feiert am {date}. Ein Extra-Knochen wäre ein guter Anfang."),
            ],
        },
        "day": {
            "any": [
                ("Happy Birthday, {name}! 🎂", "Heute {age} alt – und immer noch 100 % flauschig. Extra-Streicheleinheiten sind Pflicht!"),
                ("Alles Gute, {name}! 🎉", "Heute ist dein Ehrentag. Der Napf bleibt nicht leer – das ist Gesetz."),
                ("Pfötchen hoch – Geburtstag! 🐾", "{name} wird heute {age} alt. Bitte singen, aber nicht zu laut: Die Ohren sind empfindlich."),
                ("Happy Birthday! 🥳", "{name} ist heute {age} alt und jeden Tag ein bisschen besser als der Rest der Familie. Mindestens."),
                ("Zeit für Torte! 🍰", "{name} feiert heute Geburtstag ({age})! Diäten sind heute offiziell abgesagt."),
                ("Hurra, {name} hat Geburtstag! 🎈", "{age} alt und kein bisschen leise. Heute zählt nur: kuscheln, fressen, feiern."),
            ],
            "cat": [
                ("Miau-Geburtstag! 🐱", "Alles Gute, {name}! Heute werden alle Befehle vom Thron aus erteilt – und die Dosenöffner gehorchen."),
            ],
            "dog": [
                ("Wau-Geburtstag! 🐶", "Alles Gute, {name}! Heute gibt es eine Extra-Gassirunde, und der Ball darf auch mal gewinnen."),
            ],
        },
    },
    "en": {
        "pre": {
            "any": [
                ("14 days until the party 🎉", "{name} turns {years} on {date}. High time to plan some treat cakes!"),
                ("Save the date 📅", "In 14 days {name} celebrates a birthday. The guest list is top secret."),
                ("Birthday countdown ⏳", "Only 14 days until {name} is {years}. Order the presents now!"),
                ("Shh – don’t tell! 🤫", "{name}’s birthday is on {date} and they suspect nothing. Time for surprises!"),
                ("Two weeks to go 🎈", "On {date} {name} turns {years}. How about an extra bowl as a gift?"),
            ],
            "cat": [("Meow alert 🐱", "In 14 days {name} turns {years}. The scratching post is already getting streamers.")],
            "dog": [("Woof alert 🐶", "In 14 days {name} turns {years}. Has the stick cake been ordered yet?")],
        },
        "day": {
            "any": [
                ("Happy Birthday, {name}! 🎂", "{age} young and still 100% fluffy. Extra cuddles are mandatory!"),
                ("Best wishes, {name}! 🎉", "Today is your day. The bowl will not stay empty – that’s the law."),
                ("Paws up – it’s a birthday! 🐾", "{name} turns {years} today. Please sing, but not too loud: those ears are sensitive."),
                ("Happy Birthday! 🥳", "{name} is {years} today and a little better than the rest of the family every day. At least."),
                ("Cake time! 🍰", "It’s {name}’s birthday ({years})! Diets are officially cancelled today."),
            ],
            "cat": [("Meow-day! 🐱", "Happy birthday, {name}! All orders are issued from the throne today – and the can openers will obey.")],
            "dog": [("Woof-day! 🐶", "Happy birthday, {name}! Extra walk today, and the ball is allowed to win for once.")],
        },
    },
}


VAC_TEXT = {
    "de": {
        30: [("Impfung läuft bald ab 💉", "Erinnerung: Die Impfung {vaccine} für {name} läuft bald ab (am {date}, in {days} Tagen)!"),
             ("Impf-Check fällig 📅", "Die Impfung {vaccine} für {name} läuft am {date} ab. Zeit, einen Termin beim Tierarzt zu machen!")],
        7: [("Impfung läuft in einer Woche ab ⏳", "Erinnerung: Die Impfung {vaccine} für {name} läuft in {days} Tagen ab ({date}). Hast du schon einen Termin?")],
        0: [("Impfung heute abgelaufen ⚠️", "Die Impfung {vaccine} für {name} läuft heute ab. Bitte beim Tierarzt auffrischen lassen!"),
            ("Impfschutz endet heute ⚠️", "Heute endet der Schutz der Impfung {vaccine} für {name}. Ein Anruf in der Praxis lohnt sich!")],
    },
    "en": {
        30: [("Vaccination expires soon 💉", "Reminder: the {vaccine} vaccination for {name} expires soon (on {date}, in {days} days)!"),
             ("Vaccination check due 📅", "{name}’s {vaccine} vaccination expires on {date}. Time to book a vet appointment!")],
        7: [("Vaccination expires in a week ⏳", "Reminder: the {vaccine} vaccination for {name} expires in {days} days ({date}). Already booked an appointment?")],
        0: [("Vaccination expires today ⚠️", "The {vaccine} vaccination for {name} expires today. Please get it renewed at the vet!"),
            ("Vaccine protection ends today ⚠️", "Today the {vaccine} vaccination for {name} runs out. A call to the vet is worth it!")],
    },
}


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS push_subs (
        endpoint TEXT PRIMARY KEY, user_id INTEGER, p256dh TEXT, auth TEXT, lang TEXT DEFAULT 'de',
        tz INTEGER DEFAULT 0, created REAL)""")
    conn.execute("CREATE TABLE IF NOT EXISTS push_vac_sent (vac_id INTEGER, stage INTEGER, PRIMARY KEY (vac_id, stage))")
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
    return {"title": title, "body": body.format(t=f"{avg // 60:02d}:{avg % 60:02d}"), "url": "/", "tag": "feeding-reminder",
            "app": os.environ.get("APP_NAME", "")}


def _bday_on(b: date, year: int) -> date:
    """Geburtstag im angegebenen Jahr (29.02. wird in Nicht-Schaltjahren auf den 28.02. gelegt)."""
    try:
        return b.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


def _age_words(lang: str, years: int) -> str:
    if lang == "en":
        return f"{years} year" + ("" if years == 1 else "s")
    return f"{years} " + ("Jahr" if years == 1 else "Jahre")


def birthday_message(lang: str, kind: str, name: str, species: str, years: int, on: date, cat_id: int = 0) -> dict:
    """kind: "pre" (14 Tage vorher) oder "day" (am Geburtstag). Der Text wird je Tier und Jahr ausgelost."""
    lang = lang if lang in BDAY_TEXT else "de"
    pool = BDAY_TEXT[lang][kind]
    options = pool["any"] + pool.get(species if species in ("cat", "dog") else "", [])
    title, body = random.Random(f"{cat_id}:{kind}:{on.year}").choice(options)
    d = on.strftime("%d.%m.") if lang == "de" else on.strftime("%b %d")
    f = dict(name=name, age=_age_words(lang, years), years=years, date=d)
    return {"title": title.format(**f), "body": body.format(**f), "url": "/", "tag": f"birthday-{kind}-{cat_id}",
            "app": os.environ.get("APP_NAME", "")}


def vaccination_message(lang: str, stage: int, vaccine: str, name: str, valid_until: date, days: int, cat_id: int = 0) -> dict:
    lang = lang if lang in VAC_TEXT else "de"
    title, body = random.Random(f"vac:{cat_id}:{vaccine}:{stage}:{valid_until}").choice(VAC_TEXT[lang][stage])
    d = valid_until.strftime("%d.%m.%Y") if lang == "de" else valid_until.isoformat()
    f = dict(vaccine=vaccine, name=name, date=d, days=max(days, 0))
    return {"title": title.format(**f), "body": body.format(**f), "url": "/", "tag": f"vaccination-{cat_id}-{stage}",
            "app": os.environ.get("APP_NAME", "")}


def due_vaccinations(conn, now_local: datetime) -> list:
    """Fällige Impf-Erinnerungen (um 09:00 Ortszeit, bis 12:00 nachholbar). Pro Impfung und Stufe nur einmal."""
    now_min = now_local.hour * 60 + now_local.minute
    if not (BDAY_HOUR * 60 <= now_min < BDAY_HOUR * 60 + BDAY_WINDOW):
        return []
    today = now_local.date()
    try:
        rows = conn.execute("SELECT v.id, v.cat_id, v.vaccine_name, v.valid_until, c.name AS cat_name FROM vaccinations v "
                            "JOIN cats c ON c.id = v.cat_id WHERE v.valid_until IS NOT NULL AND v.valid_until != ''").fetchall()
    except sqlite3.OperationalError:  # Tabelle fehlt noch
        return []
    newest = {}
    for r in rows:   # je Tier + Impfung zählt nur der Eintrag mit dem spätesten Ablaufdatum
        key = (r["cat_id"], r["vaccine_name"].strip().lower())
        if key not in newest or r["valid_until"] > newest[key]["valid_until"]:
            newest[key] = r
    out = []
    for r in newest.values():
        try:
            until = date.fromisoformat(r["valid_until"])
        except ValueError:
            continue
        days = (until - today).days
        reached = [s for s in VAC_STAGES if days <= s]
        if not reached or days < -7:
            continue
        stage = min(reached)
        sent = {x["stage"] for x in conn.execute("SELECT stage FROM push_vac_sent WHERE vac_id = ?", (r["id"],))}
        if stage in sent:
            continue
        out.append(dict(id=r["id"], cat_id=r["cat_id"], vaccine=r["vaccine_name"], name=r["cat_name"], until=until,
                        days=days, stage=stage, reached=reached))
    return out


def due_birthdays(conn, now_local: datetime, tz: int) -> list:
    """Fällige Geburtstags-Nachrichten (um 09:00 Ortszeit, bis 12:00 nachholbar)."""
    now_min = now_local.hour * 60 + now_local.minute
    if not (BDAY_HOUR * 60 <= now_min < BDAY_HOUR * 60 + BDAY_WINDOW):
        return []
    today = now_local.date()
    target = today + timedelta(days=BDAY_ADVANCE)
    out = []
    try:
        cats = conn.execute("SELECT id, name, species, birthday FROM cats WHERE birthday IS NOT NULL AND birthday != ''").fetchall()
    except sqlite3.OperationalError:  # Spalte "birthday" fehlt noch
        return []
    for c in cats:
        try:
            b = date.fromisoformat(c["birthday"])
        except ValueError:
            continue
        for kind, on in (("pre", target), ("day", today)):
            years = on.year - b.year
            if years < 1 or _bday_on(b, on.year) != on:
                continue
            slot = f"bd-{kind}:{c['id']}"
            if conn.execute("SELECT 1 FROM push_sent WHERE day = ? AND slot = ? AND tz = ?", (today.isoformat(), slot, tz)).fetchone():
                continue
            out.append(dict(slot=slot, kind=kind, id=c["id"], name=c["name"], species=c["species"] or "cat", years=years, on=on))
    return out


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
            for ev in due_birthdays(conn, now_local, tz):
                conn.execute("INSERT OR IGNORE INTO push_sent (day, slot, tz) VALUES (?, ?, ?)",
                             (now_local.date().isoformat(), ev["slot"], tz))
                conn.commit()
                for s in (x for x in subs if x["tz"] == tz):
                    msg = birthday_message(s["lang"], ev["kind"], ev["name"], ev["species"], ev["years"], ev["on"], ev["id"])
                    if send(s, msg)[0]:
                        sent += 1
            for ev in due_vaccinations(conn, now_local):
                for st in ev["reached"]:   # frühere Stufen mit abhaken, damit nicht mehrere Nachrichten kommen
                    conn.execute("INSERT OR IGNORE INTO push_vac_sent (vac_id, stage) VALUES (?, ?)", (ev["id"], st))
                conn.commit()
                for s in (x for x in subs if x["tz"] == tz):
                    if send(s, vaccination_message(s["lang"], ev["stage"], ev["vaccine"], ev["name"], ev["until"], ev["days"], ev["cat_id"]))[0]:
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
def test(request: Request, kind: str = "feeding"):
    """kind=feeding: Futter-Erinnerung. kind=birthday: beide Geburtstags-Nachrichten. kind=vaccination: Impf-Erinnerung (Vorschau)."""
    if not HAVE_PUSH:
        raise HTTPException(status_code=501, detail="Push ist auf dem Server nicht installiert")
    conn = _db()
    subs = [dict(r) for r in conn.execute("SELECT * FROM push_subs WHERE user_id = ?", (request.state.user["id"],)).fetchall()]
    pet = None
    if kind == "birthday":
        try:
            pet = conn.execute("SELECT id, name, species, birthday FROM cats WHERE birthday IS NOT NULL AND birthday != '' "
                               "ORDER BY sort, id LIMIT 1").fetchone()
        except sqlite3.OperationalError:
            pet = None
    conn.close()
    sample = dict(id=0, name="Mausi", species="cat", years=3)
    if pet:
        try:
            b = date.fromisoformat(pet["birthday"])
            sample = dict(id=pet["id"], name=pet["name"], species=pet["species"] or "cat", years=max(1, date.today().year - b.year))
        except ValueError:
            pass
    sent, errors = 0, []
    for s in subs:
        if kind == "vaccination":
            msgs = [vaccination_message(s["lang"], 30, "Tollwut", sample["name"], date.today() + timedelta(days=30), 30, sample["id"])]
        elif kind == "birthday":
            msgs = [birthday_message(s["lang"], k, sample["name"], sample["species"], sample["years"],
                                     date.today() + timedelta(days=BDAY_ADVANCE if k == "pre" else 0), sample["id"])
                    for k in ("pre", "day")]
        else:
            msgs = [_message(s["lang"], 8 * 60 + 30)]
        for m in msgs:
            ok, err = _send(s, m)
            sent += 1 if ok else 0
            if err:
                errors.append(err)
    return {"sent": sent, "errors": errors}
