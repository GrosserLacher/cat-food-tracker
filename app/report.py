"""
report.py – Bericht-Export im Look der App.
Ablage: app/report.py

GET /api/export/report
  kinds      Kategorien, kommagetrennt: food,snack,drink,vomit,health   (Mehrfachauswahl)
  animals    Tier-IDs, kommagetrennt (fehlt der Parameter: alle Tiere)
  unknown    1 = Spuck-Ereignisse ohne Tierzuordnung ("Unbekannt") einschliessen
  days       Zeitraum in Tagen (Standard 30)   ODER   date_from + date_to (YYYY-MM-DD)
  mode       split = nach Kategorien getrennt (Standard) | mixed = zeitlich gemischt
  lang       de | en (Standard: Spracheinstellung der App)
  cc         Tierfarben der App, z. B. "1-f4b183,2-a8d5ba"

Das Alter eines Tieres steht genau einmal im Tierkopf (Stand: Tag des Exports).
Dieses Modul stellt ausserdem BASE_CSS, FONT_LINK und HERO_CAT bereit, damit auch der
bestehende Standard-Bericht (main.py) im selben Design erscheint.
"""
import html
import json
import math
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

try:
    from app.extras import vomit_label, max_score
except ImportError:  # Start ohne Paketstruktur
    from extras import vomit_label, max_score

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
DB_PATH = os.path.join(DATA_DIR, "tracker.db")
router = APIRouter(prefix="/api/export")

KIND_KEYS = ("food", "snack", "drink")
ALL_KINDS = KIND_KEYS + ("meds", "vomit", "stool", "finding", "health", "treat")
DEFAULT_COLORS = ["#f4b183", "#a8d5ba", "#b9a8e8", "#f2a7c3", "#9fcbe8", "#e8d08a"]
esc = html.escape


def app_name() -> str:
    return os.environ.get("APP_NAME", "PurrfectHealth")


# --- Design (entspricht der App: warme Farben, Fraunces + Inter, runde Karten) ---------

FONT_LINK = ('<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600'
             '&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">'
             '<link rel="icon" type="image/svg+xml" href="/static/favicon.svg?v=2">'
             '<link rel="shortcut icon" href="/favicon.ico">')

HERO_CAT = ("<svg class='cat' viewBox='0 0 120 90' xmlns='http://www.w3.org/2000/svg' aria-hidden='true'>"
            "<path d='M20 90V46C20 34 24 24 30 18L28 4L46 14C54 12 66 12 74 14L92 4L90 18C96 24 100 34 100 46V90Z' fill='#fff1e4'/>"
            "<path d='M33 14l1 6-5 3zM87 14l-1 6 5 3z' fill='#f3b9a6'/>"
            "<path d='M38 52q5-7 11 0M71 52q5-7 11 0' fill='none' stroke='#5a3a2e' stroke-width='3' stroke-linecap='round'/>"
            "<path d='M55 61h10l-5 6z' fill='#d9674a'/>"
            "<path d='M60 67q-3 5-9 3M60 67q3 5 9 3' fill='none' stroke='#5a3a2e' stroke-width='2.4' stroke-linecap='round'/>"
            "<path d='M22 58l-14-3M22 64l-14 3M98 58l14-3M98 64l14 3' stroke='#5a3a2e' stroke-width='1.8' stroke-linecap='round'/>"
            "<circle cx='34' cy='62' r='6' fill='#f7b8a8' opacity='.6'/><circle cx='86' cy='62' r='6' fill='#f7b8a8' opacity='.6'/></svg>")

BASE_CSS = """
:root{--bg:#fbf5ee;--card:#fffdfa;--ink:#2d2420;--mut:#85746a;--line:#eddfd2;--acc:#c8563a;--onacc:#fff;--accs:#fbe6dd;
--good:#3f8f5f;--goods:#e1f1e3;--ok:#5a7fb8;--oks:#e5edf8;--bad:#c2453b;--bads:#fbe3df;--hg1:#f9dcc7;--hg2:#f6cfd3}
@page{size:A4 portrait;margin:12mm}
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{font:500 12px/1.45 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg);margin:0;padding:18px;-webkit-font-smoothing:antialiased}
.wrap{max-width:900px;margin:0 auto}
h1,h2,h3{font-family:Fraunces,Georgia,serif;font-weight:600;margin:0;color:var(--ink)}
.no-print{background:var(--card);border:1px solid var(--line);color:var(--ink);padding:10px 14px;border-radius:16px;margin:0 auto 16px;max-width:900px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.no-print .hint{color:var(--mut);margin-left:8px}
.btn{background:var(--acc);color:var(--onacc);border:0;padding:9px 14px;border-radius:12px;font:600 12px Inter,system-ui,sans-serif;cursor:pointer}
.btn.gh{background:var(--accs);color:var(--acc)}
.hero{position:relative;overflow:hidden;min-height:112px;padding:20px 140px 18px 22px;border-radius:22px;background:linear-gradient(135deg,var(--hg1),var(--hg2));border:1px solid var(--line);margin-bottom:16px}
.hero h1{font-size:24px;line-height:1.15}
.hero .meta{color:var(--ink);opacity:.75;margin-top:6px;font-size:12px}
.hero .chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.hero .cat{position:absolute;right:20px;bottom:-2px;width:96px;height:72px}
.chip{display:inline-block;padding:3px 10px;border-radius:999px;background:rgba(255,253,250,.75);border:1px solid var(--line);font-weight:600;font-size:11px}
h2{font-size:16px;margin:20px 0 10px}
.meta{color:var(--mut);font-size:11.5px;margin-bottom:12px}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:16px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:11px 13px}
.kpi .label{font-size:11px;color:var(--mut)}
.kpi .val{font:600 21px/1.2 Fraunces,Georgia,serif;margin-top:2px}
.kpi .val small{font:500 11px Inter,sans-serif;color:var(--mut)}
table{width:100%;border-collapse:separate;border-spacing:0;margin:0 0 14px;font-size:11px;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{padding:7px 9px;text-align:left;vertical-align:top;border-top:1px solid var(--line)}
thead th{border-top:0;background:var(--accs);color:var(--acc);font-weight:600}
tr{break-inside:avoid}
.muted{color:var(--mut)}
.pill{display:inline-block;padding:2px 9px;border-radius:8px;font-weight:600;font-size:10.5px;white-space:nowrap}
.pill.good{background:var(--goods);color:var(--good)}.pill.ok{background:var(--oks);color:var(--ok)}
.pill.bad{background:var(--bads);color:var(--bad)}.pill.neutral{background:#f3ebe2;color:var(--mut)}
@media print{body{background:#fff;padding:0}.no-print{display:none!important}}
"""

REPORT_CSS = BASE_CSS + """
h3{font-size:14px;margin:16px 0 8px;break-after:avoid}
.pet{margin-bottom:22px}
.pet+.pet{break-before:page;padding-top:4px}
.pethead{display:flex;align-items:center;gap:14px;background:var(--card);border:1px solid var(--line);border-radius:18px;padding:12px 16px;margin-bottom:6px;break-after:avoid}
.pethead h2{margin:0;font-size:20px}
.pethead .sub{color:var(--mut);margin-top:2px}
.av{position:relative;flex:none;width:46px;height:46px;border-radius:50%;display:grid;place-items:center;font:700 19px Inter,system-ui,sans-serif;background:var(--ib);color:var(--ct)}
.av::before,.av::after{content:"";position:absolute;top:-.28em;width:0;height:0;border-left:.34em solid transparent;border-right:.34em solid transparent;border-bottom:.85em solid var(--ib)}
.av::before{left:.06em;transform:rotate(-18deg)}.av::after{right:.06em;transform:rotate(18deg)}
.av.dog::before,.av.dog::after{top:.05em;width:.5em;height:.9em;border:0;background:var(--ib);border-radius:.15em .15em .5em .5em}
.av.dog::before{left:-.28em;transform:rotate(10deg)}.av.dog::after{right:-.28em;transform:rotate(-10deg)}
.pill.k-food{background:#fbe6dd;color:#c8563a}.pill.k-snack{background:#fdf0d5;color:#a8730f}.pill.k-drink{background:#e5edf8;color:#5a7fb8}
.pill.k-stool{background:#efe4d6;color:#8a5a2b}.pill.k-finding{background:#fde7ee;color:#b0426b}
.thumbs{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}.thumbs img{height:70px;width:auto;max-width:110px;object-fit:cover;border-radius:8px;border:1px solid var(--line)}
.pill.k-treat{background:#dff1f0;color:#2a8079}
.pill.k-meds{background:#ece6fb;color:#6b52b8}
.pill.k-vomit{background:#fbe3df;color:#c2453b}.pill.k-health{background:#e1f1e3;color:#3f8f5f}
.tcard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin:0 0 12px}
.tcard h4{margin:0;font:600 14px Fraunces,Georgia,serif}.tcard .tmeta{color:var(--mut);font-size:11px;margin:4px 0 8px}
.tcard .tnote{background:#fbf1de;border-radius:10px;padding:7px 10px;margin:0 0 8px;font-size:11px}
.tcard table{margin:0}
.sum{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 8px}
.nw{white-space:nowrap}
.fields{display:grid;grid-template-columns:1fr 1fr;gap:10px;align-items:start}
.fcard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:11px 13px;break-inside:avoid}
.fcard h4{margin:0 0 4px;font:600 13px Fraunces,Georgia,serif}
.fcard .big{font:600 22px Fraunces,Georgia,serif}
.fcard .stats{display:flex;flex-wrap:wrap;gap:4px 12px;color:var(--mut);font-size:10.5px;margin-top:2px}
.spark{display:block;width:100%;height:auto;margin:6px 0}
.fcard table{margin:6px 0 0;font-size:10.5px;border-radius:8px}
.fcard th,.fcard td{padding:4px 7px}
.foot{color:var(--mut);font-size:10.5px;text-align:center;margin:18px 0 0}
@media (max-width:640px){.fields{grid-template-columns:1fr}.hero{padding-right:22px}.hero .cat{display:none}}
@media print{.fields{grid-template-columns:1fr 1fr}.hero .cat{display:block}}
"""

# --- Texte ---------------------------------------------------------------------------------

TXT = {
    "de": dict(
        title="Bericht", created="Erstellt am", period="Zeitraum", animals="Tiere",
        kinds=dict(food="Futter", snack="Snacks", drink="Getränke", meds="Präparate", vomit="Spucken", stool="Kot", finding="Befunde", health="Gesundheit", treat="Behandlungen"),
        fkind=dict(skin="Haut", wound="Wunde", ear="Ohren", other="Sonstiges"), flags=dict(blood="Blut", mucus="Schleim", worms="Würmer"),
        bristol_l=["Harte, einzelne Klümpchen", "Klumpige Wurst", "Wurst mit Rissen", "Glatte, weiche Wurst", "Weiche Klümpchen", "Breiig", "Flüssig"],
        bristol="Bristol", location="Stelle", photos="Fotos", detail="Details",
        t_active="aktiv", t_done="abgeschlossen", t_start="Start", t_end="Ende", t_interval="Intervall", t_every="alle {n} Std.",
        t_none_interval="kein festes Intervall", t_notes="Anweisungen", t_type="Art", t_desc="Beschreibung", t_nologs="Keine Log-Einträge.", t_logs="Einträge",
        med="Präparat", dose="Dosis", with_food="mit Fütterung",
        species=dict(cat="Katze", dog="Hund"), born="geboren am", age="Alter am Exporttag", no_birthday="Geburtstag nicht eingetragen",
        unknown="Unbekannt", unknown_note="Spuck-Ereignisse ohne Tierzuordnung",
        time="Zeitpunkt", item="Hersteller & Sorte", rating="Bewertung", note="Notiz", category="Kategorie",
        before="Davor gefüttert (12 h, ohne Getränke)", none_before="keine Mahlzeit gefunden",
        none_entries="Keine Einträge im Zeitraum.", no_values="Keine Werte im Zeitraum.", last_known="Zuletzt gemessen",
        value="Wert", last="Zuletzt", change="Veränderung", min="Min", max="Max", count="Messungen",
        entries=("Eintrag", "Einträge"), scale="Bewertungsskala", print_btn="🖨️ Als PDF speichern / Drucken", close="Schließen",
        hint="Wähle im Druckdialog „Als PDF speichern“.", days="Tage",
        years=("Jahr", "Jahre"), months=("Monat", "Monate"), day_words=("Tag", "Tage"),
        footer="Dient der Dokumentation und ersetzt keine tierärztliche Beratung.", relevant="futterrelevant",
        timeline="Zeitverlauf", details="Details", total="gesamt", dfmt="%d.%m.%Y %H:%M", dshort="%d.%m.%Y",
    ),
    "en": dict(
        title="Report", created="Created on", period="Period", animals="Animals",
        kinds=dict(food="Food", snack="Snacks", drink="Drinks", meds="Medication", vomit="Vomiting", stool="Stool", finding="Findings", health="Health", treat="Treatments"),
        fkind=dict(skin="Skin", wound="Wound", ear="Ears", other="Other"), flags=dict(blood="Blood", mucus="Mucus", worms="Worms"),
        bristol_l=["Hard lumps", "Lumpy sausage", "Sausage with cracks", "Smooth, soft sausage", "Soft blobs", "Mushy", "Liquid"],
        bristol="Bristol", location="Location", photos="Photos", detail="Details",
        t_active="active", t_done="completed", t_start="Start", t_end="End", t_interval="Interval", t_every="every {n} h",
        t_none_interval="no fixed interval", t_notes="Instructions", t_type="Type", t_desc="Description", t_nologs="No log entries.", t_logs="entries",
        med="Medication", dose="Dose", with_food="with feeding",
        species=dict(cat="Cat", dog="Dog"), born="born on", age="Age on export day", no_birthday="Birthday not set",
        unknown="Unknown", unknown_note="Vomiting incidents without an assigned animal",
        time="Time", item="Brand & variety", rating="Rating", note="Notes", category="Category",
        before="Fed before (12 h, excl. drinks)", none_before="no meal found",
        none_entries="No entries in this period.", no_values="No values in this period.", last_known="Last measured",
        value="Value", last="Latest", change="Change", min="Min", max="Max", count="Measurements",
        entries=("entry", "entries"), scale="Rating scale", print_btn="🖨️ Save as PDF / Print", close="Close",
        hint="Choose “Save as PDF” in the print dialog.", days="days",
        years=("year", "years"), months=("month", "months"), day_words=("day", "days"),
        footer="For documentation only; does not replace veterinary advice.", relevant="food-related",
        timeline="Timeline", details="Details", total="total", dfmt="%Y-%m-%d %H:%M", dshort="%Y-%m-%d",
    ),
}


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _num(x: float, lang: str) -> str:
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    s = "0" if s in ("", "-0") else s
    return s.replace(".", ",") if lang == "de" else s


def _ent(n: int, t: dict) -> str:
    return t["entries"][0 if n == 1 else 1]


def _cls(ratio: float) -> str:
    return "good" if ratio >= 0.83 else ("ok" if ratio >= 0.6 else "bad")


def _age(b: date, today: date, t: dict) -> str:
    y, m = today.year - b.year, today.month - b.month
    if today.day < b.day:
        m -= 1
    if m < 0:
        y, m = y - 1, m + 12
    if y < 0:
        return ""
    w = lambda n, pair: f"{n} {pair[0] if n == 1 else pair[1]}"
    if y > 0:
        return w(y, t["years"]) + (", " + w(m, t["months"]) if m else "")
    if m > 0:
        return w(m, t["months"])
    return w(max(0, (today - b).days), t["day_words"])


def _fmt_dt(s: str, t: dict) -> str:
    try:
        return datetime.fromisoformat(s).strftime(t["dfmt"])
    except (ValueError, TypeError):
        return s or ""


def _nice_ticks(lo: float, hi: float, n: int = 4) -> list:
    if hi == lo:
        lo, hi = lo - 1, hi + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    v, out = math.floor(lo / step + 1e-9) * step, []
    for _ in range(30):
        out.append(round(v, 6))
        if v >= hi - 1e-9:
            break
        v += step
    return out


def _chart(pts, unit: str, lang: str, band=None) -> str:
    """Liniendiagramm mit Achsen. pts = [(datetime, value)], mindestens 2 Punkte, aufsteigend."""
    if len(pts) < 2:
        return ""
    W, H, L, R, T, B = 360, 170, 40, 12, 12, 24
    t0, t1 = pts[0][0].timestamp(), pts[-1][0].timestamp()
    if t0 == t1:
        t0, t1 = t0 - 43200, t1 + 43200
    ys = [v for _, v in pts]
    lo, hi = min(ys), max(ys)
    if band:
        lo, hi = min(lo, band[0] - 0.2), max(hi, band[1] + 0.2)
    ticks = _nice_ticks(lo, hi)
    y0, y1 = ticks[0], ticks[-1]
    sx = lambda t: L + (t - t0) / (t1 - t0) * (W - L - R)
    sy = lambda v: T + (1 - (v - y0) / (y1 - y0)) * (H - T - B)
    long_range = (t1 - t0) > 3e7
    fmt = (lambda t: datetime.fromtimestamp(t).strftime("%m/%y")) if long_range else (
        (lambda t: datetime.fromtimestamp(t).strftime("%d.%m.")) if lang == "de" else (lambda t: datetime.fromtimestamp(t).strftime("%m-%d")))
    line = " ".join(f"{sx(d.timestamp()):.1f},{sy(v):.1f}" for d, v in pts)
    lx, ly = sx(pts[-1][0].timestamp()), sy(pts[-1][1])
    out = [f'<svg class="spark" viewBox="0 0 {W} {H}" aria-hidden="true">']
    if band:
        out.append(f'<rect x="{L}" y="{sy(band[1]):.1f}" width="{W - L - R}" height="{sy(band[0]) - sy(band[1]):.1f}" fill="rgba(63,143,95,.14)"/>')
    for v in ticks:
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" stroke="#eddfd2" stroke-width="1"/>'
                   f'<text x="{L - 5}" y="{sy(v) + 3.5:.1f}" text-anchor="end" font-size="10" fill="#85746a">{_num(v, lang)}</text>')
    for i in range(4):
        t = t0 + (t1 - t0) * i / 3
        anchor = "start" if i == 0 else ("end" if i == 3 else "middle")
        out.append(f'<text x="{sx(t):.1f}" y="{H - 7}" text-anchor="{anchor}" font-size="10" fill="#85746a">{fmt(t)}</text>')
    out.append(f'<polygon points="{sx(t0):.1f},{sy(y0):.1f} {line} {lx:.1f},{sy(y0):.1f}" fill="#c8563a" opacity=".10"/>')
    out.append(f'<polyline fill="none" stroke="#c8563a" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" points="{line}"/>')
    if len(pts) <= 45:
        out += [f'<circle cx="{sx(d.timestamp()):.1f}" cy="{sy(v):.1f}" r="2.8" fill="#fff" stroke="#c8563a" stroke-width="1.8"/>' for d, v in pts]
    out.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4.5" fill="#c8563a"/>'
               f'<text x="{min(lx, W - R - 3):.1f}" y="{ly - 8:.1f}" text-anchor="end" font-size="11" font-weight="700" fill="#2d2420">{_num(pts[-1][1], lang)}</text></svg>')
    return "".join(out)


def _band(name: str, unit: str, species: str):
    """Grober Normalbereich für Temperatur (nur zur Orientierung)."""
    if "temp" in name.lower() or unit == "°C":
        return (37.5, 39.2) if species == "dog" else (38.0, 39.2)
    return None


def _text_color(hexcol: str) -> str:
    n = int(hexcol[1:], 16)
    lum = (0.299 * (n >> 16) + 0.587 * (n >> 8 & 255) + 0.114 * (n & 255)) / 255
    return "#1d1a17" if lum > 0.6 else "#fff"


@router.get("/report", response_class=HTMLResponse)
def export_report(kinds: str = ",".join(ALL_KINDS), animals: Optional[str] = None, unknown: int = 0,
                  days: int = 30, date_from: Optional[str] = None, date_to: Optional[str] = None,
                  lang: Optional[str] = None, cc: str = "", mode: str = "split"):
    mixed = mode == "mixed"   # mixed = alle Kategorien in zeitlicher Abfolge, split = nach Kategorien getrennt
    conn = _db()
    s_map = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
    lang = lang if lang in TXT else (s_map.get("language") if s_map.get("language") in TXT else "de")
    t = TXT[lang]
    sel = [k for k in ALL_KINDS if k in {x.strip() for x in kinds.split(",")}] or list(ALL_KINDS)
    food_kinds = [k for k in KIND_KEYS if k in sel]

    # Zeitraum
    now = datetime.now()
    try:
        if not (date_from and date_to):
            raise ValueError
        d0, d1 = date.fromisoformat(date_from), date.fromisoformat(date_to)
        if d0 > d1:
            d0, d1 = d1, d0
        start, end = f"{d0.isoformat()}T00:00", f"{d1.isoformat()}T23:59"
    except ValueError:
        days = max(1, min(3650, days))
        st = now - timedelta(days=days)
        d0, d1 = st.date(), now.date()
        start, end = st.strftime("%Y-%m-%dT%H:%M"), f"{d1.isoformat()}T23:59"
    n_days = (d1 - d0).days + 1

    # Tiere und Farben (gleiche Zuordnung wie in der App: Reihenfolge -> Farbpalette)
    rows = conn.execute("SELECT id, name, species, birthday FROM cats ORDER BY sort, id").fetchall()
    custom = {}
    for part in cc.split(","):
        m = re.fullmatch(r"(\d+)-([0-9a-fA-F]{6})", part.strip())
        if m:
            custom[int(m.group(1))] = "#" + m.group(2).lower()
    ids = None if animals is None else {int(x) for x in animals.split(",") if x.strip().isdigit()}
    pets = []
    for i, r in enumerate(rows):
        if ids is None or r["id"] in ids:
            pets.append(dict(r, color=custom.get(r["id"], DEFAULT_COLORS[i % 6])))
    show_unknown = bool(unknown) and ("vomit" in sel or "stool" in sel)
    pet_names = {p["name"] for p in pets}

    # Daten
    levels = {r["score"]: (r["label"], r["emoji"] or "") for r in conn.execute("SELECT score, label, emoji FROM rating_levels")}
    top = max_score()
    feeds = {}
    if food_kinds and pets:
        q = ",".join("?" * len(food_kinds))
        for f in conn.execute(f"SELECT * FROM feedings WHERE COALESCE(kind,'food') IN ({q}) AND timestamp >= ? AND timestamp <= ? "
                              "ORDER BY timestamp DESC, id DESC", (*food_kinds, start, end)):
            if f["cat_name"] in pet_names:
                feeds.setdefault((f["cat_name"], f["kind"] or "food"), []).append(f)

    meds_by_cat = {}
    if "meds" in sel and pets:
        for m in conn.execute("SELECT * FROM med_logs WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC, id DESC", (start, end)):
            if m["cat_name"] in pet_names:
                meds_by_cat.setdefault(m["cat_name"], []).append(m)

    stool_by, find_by = {}, {}
    if ("stool" in sel or "finding" in sel) and (pets or show_unknown):
        for f in conn.execute("SELECT * FROM findings WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC, id DESC", (start, end)):
            key = "?" if f["cat_name"] in ("Unbekannt", "Unknown") else f["cat_name"]
            if key != "?" and key not in pet_names:
                continue
            if key == "?" and not show_unknown:
                continue
            if f["kind"] == "stool" and "stool" in sel:
                stool_by.setdefault(key, []).append(f)
            elif f["kind"] != "stool" and "finding" in sel:
                find_by.setdefault(key, []).append(f)

    treats_by_cat = {}
    if "treat" in sel and pets:
        pid2 = ",".join(str(p["id"]) for p in pets)
        for tr in conn.execute(f"SELECT * FROM treatments WHERE cat_id IN ({pid2}) AND start_timestamp <= ? "
                               "AND (end_timestamp IS NULL OR end_timestamp >= ?) ORDER BY start_timestamp", (end, start)):
            logs = conn.execute("SELECT timestamp, log_type, value_comment FROM treatment_logs WHERE treatment_id = ? ORDER BY timestamp, id",
                                (tr["id"],)).fetchall()
            treats_by_cat.setdefault(tr["cat_id"], []).append((tr, logs))

    vtypes = {r["key"]: (r["emoji"] or "", bool(r["relevant"])) for r in conn.execute("SELECT key, emoji, relevant FROM vomit_types")}
    vomits = {}
    if "vomit" in sel:
        for v in conn.execute("SELECT * FROM vomits WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC", (start, end)):
            if v["cat_name"] in pet_names or (show_unknown and v["cat_name"] in ("Unbekannt", "Unknown")):
                key = "?" if v["cat_name"] in ("Unbekannt", "Unknown") else v["cat_name"]
                vomits.setdefault(key, []).append(v)

    def meals_before(cat_name, ts):
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            return []
        a, b = (dt - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M"), dt.strftime("%Y-%m-%dT%H:%M")
        base = ("SELECT timestamp, manufacturer_name, food_name FROM feedings WHERE COALESCE(kind,'food') IN ('food','snack') "
                "AND timestamp >= ? AND timestamp <= ? ")
        if cat_name == "?":
            return conn.execute(base + "ORDER BY timestamp DESC", (a, b)).fetchall()
        return conn.execute(base + "AND cat_name = ? ORDER BY timestamp DESC", (a, b, cat_name)).fetchall()

    fields, hvals, hlast = [], {}, {}
    if "health" in sel and pets:
        fields = conn.execute("SELECT id, name, unit FROM health_fields WHERE hidden = 0 ORDER BY sort, id").fetchall()
        pid = ",".join(str(p["id"]) for p in pets)
        for v in conn.execute(f"SELECT * FROM health_values WHERE cat_id IN ({pid}) AND ts >= ? AND ts <= ? ORDER BY ts", (start, end)):
            hvals.setdefault((v["cat_id"], v["field_id"]), []).append(v)
        for p in pets:
            for f in fields:
                if (p["id"], f["id"]) not in hvals:
                    r = conn.execute("SELECT value, ts FROM health_values WHERE cat_id = ? AND field_id = ? ORDER BY ts DESC LIMIT 1",
                                     (p["id"], f["id"])).fetchone()
                    if r:
                        hlast[(p["id"], f["id"])] = r
    # Texte der Spuck-Kategorien vorab holen, dann Verbindung schliessen
    vlabels = {k: vomit_label(k, lang) for k in {v["vomit_type"] or "food" for lst in vomits.values() for v in lst}}
    meals = {}
    for key, lst in vomits.items():
        for v in lst:
            if vtypes.get(v["vomit_type"] or "food", ("", True))[1]:
                meals[v["id"]] = [dict(x) for x in meals_before(key, v["timestamp"])]
    conn.close()

    # --- Rendering -------------------------------------------------------------------------
    def rating_pill(r):
        lab, em = levels.get(r, (str(r), ""))
        return f"<span class='pill {_cls(r / top)}'>{esc((em + ' ' + lab).strip())} ({r})</span>"

    def food_section(name, kind):
        lst = feeds.get((name, kind), [])
        h = f"<h3>{esc(t['kinds'][kind])}</h3>"
        if not lst:
            return h + f"<p class='muted'>{t['none_entries']}</p>"
        avg = sum(f["rating"] for f in lst) / len(lst)
        out = (h + f"<div class='sum'><span class='pill neutral'>{len(lst)} {_ent(len(lst), t)}</span>"
               f"<span class='pill {_cls(avg / top)}'>Ø {_num(avg, lang)} / {top}</span></div>"
               f"<table><thead><tr><th style='width:112px'>{t['time']}</th><th>{t['item']}</th><th style='width:150px'>{t['rating']}</th>"
               f"<th style='width:28%'>{t['note']}</th></tr></thead><tbody>")
        for f in lst:
            out += (f"<tr><td class='nw'>{_fmt_dt(f['timestamp'], t)}</td><td><strong>{esc(f['manufacturer_name'])}</strong> – {esc(f['food_name'])}</td>"
                    f"<td>{rating_pill(f['rating'])}</td><td>{esc(f['notes'] or '–')}</td></tr>")
        return out + "</tbody></table>"

    def _thumbs(f):
        try:
            paths = [x for x in json.loads(f["images"] or "[]") if str(x).startswith("/uploads/")]
        except ValueError:
            paths = []
        return ("<div class='thumbs'>" + "".join(f"<a href='{esc(x)}' target='_blank'><img src='{esc(x)}' alt=''></a>" for x in paths) + "</div>") if paths else ""

    def _bristol(n):
        cls = "good" if n in (3, 4) else ("ok" if n in (2, 5) else "bad")
        return f"<span class='pill {cls}'>{t['bristol']} {n} · {esc(t['bristol_l'][n - 1])}</span>"

    def _flags(f):
        fl = [x for x in (f["details"] or "").split(",") if x in t["flags"]]
        return "".join(f" <span class='pill bad'>{esc(t['flags'][x])}</span>" for x in fl)

    def stool_section(key):
        lst = stool_by.get(key, [])
        h = f"<h3>{esc(t['kinds']['stool'])}</h3>"
        if not lst:
            return h + f"<p class='muted'>{t['none_entries']}</p>"
        out = (h + f"<div class='sum'><span class='pill neutral'>{len(lst)} {_ent(len(lst), t)}</span></div>"
               f"<table><thead><tr><th style='width:112px'>{t['time']}</th><th>{t['bristol']}</th><th style='width:30%'>{t['note']}</th>"
               f"<th style='width:28%'>{t['photos']}</th></tr></thead><tbody>")
        for f in lst:
            out += (f"<tr><td class='nw'>{_fmt_dt(f['timestamp'], t)}</td><td>{_bristol(f['bristol'] or 4)}{_flags(f)}</td>"
                    f"<td>{esc(f['notes'] or '–')}</td><td>{_thumbs(f) or '–'}</td></tr>")
        return out + "</tbody></table>"

    def finding_section(key):
        lst = find_by.get(key, [])
        h = f"<h3>{esc(t['kinds']['finding'])}</h3>"
        if not lst:
            return h + f"<p class='muted'>{t['none_entries']}</p>"
        out = (h + f"<div class='sum'><span class='pill neutral'>{len(lst)} {_ent(len(lst), t)}</span></div>"
               f"<table><thead><tr><th style='width:112px'>{t['time']}</th><th style='width:26%'>{t['category']}</th><th>{t['note']}</th>"
               f"<th style='width:28%'>{t['photos']}</th></tr></thead><tbody>")
        for f in lst:
            loc = f"<div class='muted'>{t['location']}: {esc(f['location'])}</div>" if f["location"] else ""
            out += (f"<tr><td class='nw'>{_fmt_dt(f['timestamp'], t)}</td><td><span class='pill k-finding'>{esc(t['fkind'].get(f['kind'], f['kind']))}</span>{loc}</td>"
                    f"<td>{esc(f['notes'] or '–')}</td><td>{_thumbs(f) or '–'}</td></tr>")
        return out + "</tbody></table>"

    def treat_section(p):
        lst = treats_by_cat.get(p["id"], [])
        h = f"<h3>{esc(t['kinds']['treat'])}</h3>"
        if not lst:
            return h + f"<p class='muted'>{t['none_entries']}</p>"
        out = h
        for tr, logs in lst:
            active = bool(tr["is_active"])
            status = f"<span class='pill {'bad' if active else 'neutral'}'>{t['t_active'] if active else t['t_done']}</span>"
            iv = t["t_every"].format(n=tr["interval_hours"]) if tr["interval_hours"] else t["t_none_interval"]
            meta = f"{t['t_start']}: {_fmt_dt(tr['start_timestamp'], t)}"
            if tr["end_timestamp"]:
                meta += f" · {t['t_end']}: {_fmt_dt(tr['end_timestamp'], t)}"
            meta += f" · {t['t_interval']}: {iv} · {len(logs)} {t['t_logs']}"
            note = f"<div class='tnote'><strong>{t['t_notes']}:</strong> {esc(tr['notes'])}</div>" if tr["notes"] else ""
            rows_ = "".join(f"<tr><td class='nw'>{_fmt_dt(l['timestamp'], t)}</td><td><span class='pill k-treat'>{esc(l['log_type'])}</span></td>"
                            f"<td>{esc(l['value_comment'] or '–')}</td></tr>" for l in logs)
            table = (f"<table><thead><tr><th style='width:112px'>{t['time']}</th><th style='width:150px'>{t['t_type']}</th>"
                     f"<th>{t['t_desc']}</th></tr></thead><tbody>{rows_}</tbody></table>") if logs else f"<p class='muted' style='margin:0'>{t['t_nologs']}</p>"
            out += f"<div class='tcard'><h4>{esc(tr['title'])} {status}</h4><div class='tmeta'>{meta}</div>{note}{table}</div>"
        return out

    def med_section(name):
        lst = meds_by_cat.get(name, [])
        h = f"<h3>{esc(t['kinds']['meds'])}</h3>"
        if not lst:
            return h + f"<p class='muted'>{t['none_entries']}</p>"
        out = (h + f"<div class='sum'><span class='pill neutral'>{len(lst)} {_ent(len(lst), t)}</span></div>"
               f"<table><thead><tr><th style='width:112px'>{t['time']}</th><th>{t['med']}</th><th style='width:26%'>{t['dose']}</th>"
               f"<th style='width:24%'>{t['note']}</th></tr></thead><tbody>")
        for m in lst:
            wf = f" <span class='pill k-food'>{t['with_food']}</span>" if m["with_food"] else ""
            out += (f"<tr><td class='nw'>{_fmt_dt(m['timestamp'], t)}</td><td><strong>{esc(m['med_name'])}</strong></td>"
                    f"<td>{esc(m['dose'] or '–')}{wf}</td><td>{esc(m['notes'] or '–')}</td></tr>")
        return out + "</tbody></table>"

    def vomit_section(key):
        lst = vomits.get(key, [])
        h = f"<h3>{esc(t['kinds']['vomit'])}</h3>"
        if not lst:
            return h + f"<p class='muted'>{t['none_entries']}</p>"
        n_rel = sum(1 for v in lst if vtypes.get(v["vomit_type"] or "food", ("", True))[1])
        out = (h + f"<div class='sum'><span class='pill neutral'>{len(lst)} {_ent(len(lst), t)}</span>"
               f"<span class='pill {'bad' if n_rel else 'neutral'}'>{n_rel}× {t['relevant']}</span></div>"
               f"<table><thead><tr><th style='width:112px'>{t['time']}</th><th style='width:170px'>{t['category']}</th>"
               f"<th>{t['before']}</th><th style='width:24%'>{t['note']}</th></tr></thead><tbody>")
        for v in lst:
            vt = v["vomit_type"] or "food"
            em, rel = vtypes.get(vt, ("", True))
            lab = esc((em + " " + vlabels.get(vt, vt)).strip())
            badge = f"<span class='pill bad'>{lab}</span>" if rel else f"<span class='pill neutral'>{lab}</span>"
            if rel:
                ms = meals.get(v["id"], [])
                before = ("<br>".join(f"{esc(m['timestamp'][11:16])} {esc(m['manufacturer_name'])} – {esc(m['food_name'])}" for m in ms)
                          if ms else f"<span class='muted'>{t['none_before']}</span>")
            else:
                before = "<span class='muted'>–</span>"
            out += (f"<tr><td class='nw'>{_fmt_dt(v['timestamp'], t)}</td><td>{badge}</td><td>{before}</td>"
                    f"<td>{esc(v['notes'] or '–')}</td></tr>")
        return out + "</tbody></table>"

    def health_section(p, tables=True):
        h = f"<h3>{esc(t['kinds']['health'])}</h3>"
        if not fields:
            return h + f"<p class='muted'>{t['no_values']}</p>"
        cards = ""
        for f in sorted(fields, key=lambda x: (p["id"], x["id"]) not in hvals):   # Felder mit Werten zuerst
            vs = hvals.get((p["id"], f["id"]), [])
            unit = f" {esc(f['unit'])}" if f["unit"] else ""
            title = f"<h4>{esc(f['name'])}{(' <span class=muted>(' + esc(f['unit']) + ')</span>') if f['unit'] else ''}</h4>"
            if not vs:
                lk = hlast.get((p["id"], f["id"]))
                extra = (f"<div class='stats'><span>{t['last_known']}: <strong>{_num(lk['value'], lang)}{unit}</strong> "
                         f"({_fmt_dt(lk['ts'], t)})</span></div>") if lk else ""
                cards += f"<div class='fcard'>{title}<p class='muted' style='margin:2px 0'>{t['no_values']}</p>{extra}</div>"
                continue
            nums = [v["value"] for v in vs]
            pts_series = [(datetime.fromisoformat(v["ts"]), v["value"]) for v in vs]
            delta = nums[-1] - nums[0]
            stats = (f"<span>{t['count']}: {len(nums)}</span><span>{t['min']}: {_num(min(nums), lang)}</span>"
                     f"<span>{t['max']}: {_num(max(nums), lang)}</span>")
            if len(nums) > 1:
                pct = f" ({'+' if delta > 0 else ''}{_num(delta / nums[0] * 100, lang)} %)" if nums[0] else ""
                stats += f"<span>{t['change']}: {'+' if delta > 0 else ''}{_num(delta, lang)}{unit}{pct}</span>"
            trs = "".join(f"<tr><td class='nw'>{_fmt_dt(v['ts'], t)}</td><td class='nw'><strong>{_num(v['value'], lang)}</strong>{unit}</td>"
                          f"<td>{esc(v['note'] or '')}</td></tr>" for v in reversed(vs))
            cards += (f"<div class='fcard'>{title}<div><span class='big'>{_num(nums[-1], lang)}</span>{unit} "
                      f"<span class='muted'>· {_fmt_dt(vs[-1]['ts'], t)}</span></div><div class='stats'>{stats}</div>{_chart(pts_series, f['unit'] or '', lang, _band(f['name'], f['unit'] or '', p['species']))}"
                      + (f"<table><thead><tr><th>{t['time']}</th><th>{t['value']}</th><th>{t['note']}</th></tr></thead><tbody>{trs}</tbody></table>" if tables else "") + "</div>")
        return h + f"<div class='fields'>{cards}</div>"

    def timeline_section(p):
        """Alle gewählten Kategorien eines Tieres in einer Tabelle, neueste zuerst."""
        name, rows_, counts = p["name"], [], {}
        def add(k, ts, detail, note):
            rows_.append((ts, k, detail, note))
            counts[k] = counts.get(k, 0) + 1
        for k in food_kinds:
            for f in feeds.get((name, k), []):
                add(k, f["timestamp"], f"<strong>{esc(f['manufacturer_name'])}</strong> – {esc(f['food_name'])} {rating_pill(f['rating'])}", f["notes"])
        for f in stool_by.get(name, []):
            add("stool", f["timestamp"], f"{_bristol(f['bristol'] or 4)}{_flags(f)}{_thumbs(f)}", f["notes"])
        for f in find_by.get(name, []):
            loc = f" · {esc(f['location'])}" if f["location"] else ""
            add("finding", f["timestamp"], f"<strong>{esc(t['fkind'].get(f['kind'], f['kind']))}</strong>{loc}{_thumbs(f)}", f["notes"])
        for m in meds_by_cat.get(name, []):
            wf = f" <span class='pill k-food'>{t['with_food']}</span>" if m["with_food"] else ""
            add("meds", m["timestamp"], f"<strong>{esc(m['med_name'])}</strong>{(' · ' + esc(m['dose'])) if m['dose'] else ''}{wf}", m["notes"])
        for v in vomits.get(name, []):
            vt = v["vomit_type"] or "food"
            em, rel = vtypes.get(vt, ("", True))
            det = f"<span class='pill {'bad' if rel else 'neutral'}'>{esc((em + ' ' + vlabels.get(vt, vt)).strip())}</span>"
            if rel:
                ms = meals.get(v["id"], [])
                det += "<div class='muted' style='margin-top:3px'>" + t["before"] + ": " + (
                    "; ".join(f"{esc(m['timestamp'][11:16])} {esc(m['manufacturer_name'])} – {esc(m['food_name'])}" for m in ms)
                    if ms else t["none_before"]) + "</div>"
            add("vomit", v["timestamp"], det, v["notes"])
        if "health" in sel:
            fname = {f["id"]: f for f in fields}
            for (pid_, fid), vs in hvals.items():
                if pid_ == p["id"] and fid in fname:
                    f = fname[fid]
                    for v in vs:
                        add("health", v["ts"], f"<strong>{esc(f['name'])}</strong>: {_num(v['value'], lang)}{(' ' + esc(f['unit'])) if f['unit'] else ''}", v["note"])
        h = f"<h3>{t['timeline']}</h3>"
        if not rows_:
            return h + f"<p class='muted'>{t['none_entries']}</p>"
        rows_.sort(key=lambda r: r[0], reverse=True)
        summ = "".join(f"<span class='pill k-{k}'>{counts[k]}× {esc(t['kinds'][k])}</span>" for k in ALL_KINDS if k in counts)
        out = (h + f"<div class='sum'>{summ}</div><table><thead><tr><th style='width:112px'>{t['time']}</th><th style='width:110px'>{t['category']}</th>"
               f"<th>{t['details']}</th><th style='width:24%'>{t['note']}</th></tr></thead><tbody>")
        for ts, k, det, note in rows_:
            out += (f"<tr><td class='nw'>{_fmt_dt(ts, t)}</td><td><span class='pill k-{k}'>{esc(t['kinds'][k])}</span></td>"
                    f"<td>{det}</td><td>{esc(note or '–')}</td></tr>")
        return out + "</tbody></table>"

    def pet_block(p):
        dog = p["species"] == "dog"
        style = f"--ib:{p['color']};--ct:{_text_color(p['color'])}"
        sub = [t["species"]["dog" if dog else "cat"]]
        if p["birthday"]:
            try:
                b = date.fromisoformat(p["birthday"])
                a = _age(b, now.date(), t)
                sub.append(f"{t['born']} {b.strftime(t['dshort'])}")
                if a:
                    sub.append(f"{t['age']}: <strong>{a}</strong>")   # Alter: genau einmal, Stand Exporttag
            except ValueError:
                pass
        else:
            sub.append(t["no_birthday"])
        tl = mixed and bool(food_kinds or {"meds", "vomit", "stool", "finding"} & set(sel))   # Zeitverlauf nur, wenn es neben Gesundheit etwas zu mischen gibt
        body = health_section(p, tables=not tl) if "health" in sel else ""   # Gesundheit direkt unter dem Tiernamen
        if "treat" in sel:
            body += treat_section(p)   # Behandlungen: Log-Einträge gruppiert unter dem jeweiligen Titel
        if tl:
            body += timeline_section(p)
        else:
            body += "".join(food_section(p["name"], k) for k in food_kinds)
            if "meds" in sel:
                body += med_section(p["name"])
            if "vomit" in sel:
                body += vomit_section(p["name"])
            if "stool" in sel:
                body += stool_section(p["name"])
            if "finding" in sel:
                body += finding_section(p["name"])
        return (f"<section class='pet'><div class='pethead'><span class='av{' dog' if dog else ''}' style='{style}'>{esc(p['name'][:1].upper())}</span>"
                f"<div><h2>{esc(p['name'])}</h2><div class='sub'>{' · '.join(sub)}</div></div></div>{body}</section>")

    blocks = "".join(pet_block(p) for p in pets)
    if show_unknown:
        blocks += (f"<section class='pet'><div class='pethead'><span class='av' style='--ib:#d9c7b8;--ct:#1d1a17'>?</span>"
                   f"<div><h2>{t['unknown']}</h2><div class='sub'>{t['unknown_note']}</div></div></div>{vomit_section('?') if 'vomit' in sel else ''}{stool_section('?') if 'stool' in sel else ''}</section>")
    if not blocks:
        blocks = f"<p class='muted'>{t['none_entries']}</p>"

    # Kennzahlen
    kpis = [(t["animals"], len(pets), "")]   # "Unbekannt" zählt nicht mit
    for k in food_kinds:
        n_k = sum(len(v) for (n, kk), v in feeds.items() if kk == k)
        kpis.append((t["kinds"][k], n_k, _ent(n_k, t)))
    if "stool" in sel:
        n_s = sum(len(v) for k, v in stool_by.items() if k != "?")
        kpis.append((t["kinds"]["stool"], n_s, _ent(n_s, t)))
    if "finding" in sel:
        n_f = sum(len(v) for k, v in find_by.items() if k != "?")
        kpis.append((t["kinds"]["finding"], n_f, _ent(n_f, t)))
    if "treat" in sel:
        n_t = sum(len(v) for v in treats_by_cat.values())
        kpis.append((t["kinds"]["treat"], n_t, ""))
    if "meds" in sel:
        n_m = sum(len(v) for v in meds_by_cat.values())
        kpis.append((t["kinds"]["meds"], n_m, _ent(n_m, t)))
    if "vomit" in sel:
        allv = [v for key, lst in vomits.items() if key != "?" for v in lst]   # ohne "Unbekannt"
        kpis.append((t["kinds"]["vomit"], len(allv), f"{sum(1 for v in allv if vtypes.get(v['vomit_type'] or 'food', ('', True))[1])}× {t['relevant']}"))
    kpi_html = "".join(f"<div class='kpi'><div class='label'>{esc(str(l))}</div><div class='val'>{v}"
                       f"{(' <small>' + esc(s) + '</small>') if s else ''}</div></div>" for l, v, s in kpis)

    name = esc(app_name())
    chips = "".join(f"<span class='chip'>{esc(t['kinds'][k])}</span>" for k in sel)
    chips += "".join(f"<span class='chip'>{esc(p['name'])}</span>" for p in pets)
    scale = ", ".join(f"{s} = {esc(l)}" for s, (l, _e) in sorted(levels.items(), reverse=True))
    period = f"{d0.strftime(t['dshort'])} – {d1.strftime(t['dshort'])} ({n_days} {t['days']})"
    created = now.strftime(t["dfmt"])
    scale_html = f" · {t['scale']}: {scale}" if food_kinds and scale else ""

    doc = f"""<!DOCTYPE html><html lang="{lang}"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name} – {t['title']} ({created})</title>{FONT_LINK}<style>{REPORT_CSS}</style></head><body>
<div class="no-print"><div><strong>🐾 {name}</strong><span class="hint">{t['hint']}</span></div>
<div style="display:flex;gap:8px"><button class="btn" onclick="window.print()">{t['print_btn']}</button>
<button class="btn gh" onclick="window.close()">{t['close']}</button></div></div>
<div class="wrap">
<header class="hero"><div><h1>{name} – {t['title']}</h1>
<div class="meta">{t['period']}: {period} · {t['created']} {created}{scale_html}</div>
<div class="chips">{chips}</div></div>{HERO_CAT}</header>
<div class="kpi-grid">{kpi_html}</div>
{blocks}
<p class="foot">{t['footer']}</p></div>
<script>window.addEventListener('load',()=>{{setTimeout(()=>window.print(),600)}});</script></body></html>"""
    return HTMLResponse(content=doc)
