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
ALL_KINDS = KIND_KEYS + ("vomit", "health")
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
.pill.k-vomit{background:#fbe3df;color:#c2453b}.pill.k-health{background:#e1f1e3;color:#3f8f5f}
.sum{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 8px}
.nw{white-space:nowrap}
.fields{display:grid;grid-template-columns:1fr 1fr;gap:10px;align-items:start}
.fcard{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:11px 13px;break-inside:avoid}
.fcard h4{margin:0 0 4px;font:600 13px Fraunces,Georgia,serif}
.fcard .big{font:600 22px Fraunces,Georgia,serif}
.fcard .stats{display:flex;flex-wrap:wrap;gap:4px 12px;color:var(--mut);font-size:10.5px;margin-top:2px}
.spark{display:block;width:100%;height:46px;margin:6px 0}
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
        kinds=dict(food="Futter", snack="Snacks", drink="Getränke", vomit="Spucken", health="Gesundheit"),
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
        kinds=dict(food="Food", snack="Snacks", drink="Drinks", vomit="Vomiting", health="Health"),
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


def _spark(vals) -> str:
    if len(vals) < 2:
        return ""
    w, h, p = 300, 56, 6
    mn, mx = min(vals), max(vals)
    r = (mx - mn) or 1
    pts = [(p + i * (w - 2 * p) / (len(vals) - 1), h - p - (v - mn) / r * (h - 2 * p)) for i, v in enumerate(vals)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    lx, ly = pts[-1]
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" aria-hidden="true"><polyline fill="none" stroke="#c8563a" '
            f'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" points="{poly}"/>'
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="4" fill="#c8563a"/></svg>')


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
    show_unknown = bool(unknown) and "vomit" in sel
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
        for f in fields:
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
            delta = nums[-1] - nums[0]
            stats = (f"<span>{t['count']}: {len(nums)}</span><span>{t['min']}: {_num(min(nums), lang)}</span>"
                     f"<span>{t['max']}: {_num(max(nums), lang)}</span>")
            if len(nums) > 1:
                stats += f"<span>{t['change']}: {'+' if delta > 0 else ''}{_num(delta, lang)}{unit}</span>"
            trs = "".join(f"<tr><td class='nw'>{_fmt_dt(v['ts'], t)}</td><td class='nw'><strong>{_num(v['value'], lang)}</strong>{unit}</td>"
                          f"<td>{esc(v['note'] or '')}</td></tr>" for v in reversed(vs))
            cards += (f"<div class='fcard'>{title}<div><span class='big'>{_num(nums[-1], lang)}</span>{unit} "
                      f"<span class='muted'>· {_fmt_dt(vs[-1]['ts'], t)}</span></div><div class='stats'>{stats}</div>{_spark(nums)}"
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
        tl = mixed and bool(food_kinds or "vomit" in sel)   # Zeitverlauf nur, wenn es neben Gesundheit etwas zu mischen gibt
        body = health_section(p, tables=not tl) if "health" in sel else ""   # Gesundheit direkt unter dem Tiernamen
        if tl:
            body += timeline_section(p)
        else:
            body += "".join(food_section(p["name"], k) for k in food_kinds)
            if "vomit" in sel:
                body += vomit_section(p["name"])
        return (f"<section class='pet'><div class='pethead'><span class='av{' dog' if dog else ''}' style='{style}'>{esc(p['name'][:1].upper())}</span>"
                f"<div><h2>{esc(p['name'])}</h2><div class='sub'>{' · '.join(sub)}</div></div></div>{body}</section>")

    blocks = "".join(pet_block(p) for p in pets)
    if show_unknown:
        blocks += (f"<section class='pet'><div class='pethead'><span class='av' style='--ib:#d9c7b8;--ct:#1d1a17'>?</span>"
                   f"<div><h2>{t['unknown']}</h2><div class='sub'>{t['unknown_note']}</div></div></div>{vomit_section('?')}</section>")
    if not blocks:
        blocks = f"<p class='muted'>{t['none_entries']}</p>"

    # Kennzahlen
    kpis = [(t["animals"], len(pets), "")]   # "Unbekannt" zählt nicht mit
    for k in food_kinds:
        n_k = sum(len(v) for (n, kk), v in feeds.items() if kk == k)
        kpis.append((t["kinds"][k], n_k, _ent(n_k, t)))
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
