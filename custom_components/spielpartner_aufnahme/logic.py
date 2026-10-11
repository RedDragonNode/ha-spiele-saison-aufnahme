"""Reine Logik ohne Home-Assistant-Abhaengigkeit (leicht testbar)."""
from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime

from .const import NO_SUBFOLDERS

_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"})
KENNUNG_RE = re.compile(r"^[a-z0-9_]+$")


def norm(text: str) -> str:
    """Name zum Vergleichen: klein, Umlaute aufgeloest, nur Buchstaben/Ziffern."""
    return re.sub(r"[^a-z0-9]", "", str(text).translate(_UMLAUTE).lower())


def valid_kennung(kennung: str) -> bool:
    return bool(KENNUNG_RE.match(kennung or ""))


def pad(number: int | str) -> str:
    """Zwei Stellen, wie im bisherigen System (01, 02, ... 100)."""
    try:
        return f"{int(number):02d}"
    except (TypeError, ValueError):
        return "01"


def default_anzeige(kennung: str) -> str:
    return kennung.capitalize()


def parse_folder_name(raw: str) -> tuple[str | None, int | None]:
    """'Spielen mit Frank #01' -> ('Frank', 1). Fehlt etwas, kommt None."""
    if not raw:
        return None, None
    name = None
    m = re.search(r"mit (.+?) #\d+", raw)
    if m:
        name = m.group(1)
    nums = re.findall(r"#(\d+)", raw)
    return name, int(nums[-1]) if nums else None


def partner_folder(prefix: str, anzeige: str, nr: int) -> str:
    return f"{prefix} {anzeige} #{pad(nr)}".strip()


def season_folder(saison: int, datum: str) -> str:
    return f"Saison {pad(saison)} vom {datum}"


def is_new_day(existing: Iterable[str] | None, todays_folder: str) -> bool:
    """Neue Saison? Nur wenn schon Saison-Ordner existieren und der heutige fehlt."""
    options = list(existing or [])
    has_folders = bool(options) and options != [NO_SUBFOLDERS]
    return has_folders and todays_folder not in options


def file_format(nr: int, saison: int, aufnahme: int, cam: str, gesamt: int, suffix: str = "") -> str:
    """#01.02.03.FB.04 (+ Endung)."""
    return f"#{pad(nr)}.{pad(saison)}.{pad(aufnahme)}.{cam}.{pad(gesamt)}{suffix}"


def pack_thread(thread_id: str, saison: int) -> str:
    return f"{thread_id}|{pad(saison)}"


def unpack_thread(raw: str | None) -> tuple[str, str]:
    """'123|02' -> ('123', '02'); alles andere -> ('', '')."""
    if raw and "|" in raw:
        a, b = raw.split("|", 1)
        if a not in ("unknown", "unavailable"):
            return a, b
    return "", ""


def build_post_header(minutes: int, swing: object) -> str:
    swing_txt = f"{swing}%" if swing not in (None, "", "unknown", "unavailable") else "unbekannt"
    return f"Aufnahme laeuft seit {minutes} Minuten.\n\nSchaukel Position: {swing_txt}"


def build_cam_caption(cam_name: str, video_id: str) -> str:
    """Zeile unter dem Schnappschuss der Cam."""
    return f"**{cam_name}**: `{video_id}`"


_TOKENS = (
    ("%CCYY", "%Y"),
    ("%YY", "%y"),
    ("%MM", "%m"),
    ("%DD", "%d"),
    ("%hh", "%H"),
    ("%mm", "%M"),
    ("%ss", "%S"),
)


def render_tokens(text: str, when: datetime) -> str:
    """Datums-Platzhalter (%DD.%MM.%CCYY ...) in echte Werte umsetzen."""
    for token, fmt in _TOKENS:
        text = text.replace(token, when.strftime(fmt))
    return text


def split_path(text: str) -> list[str]:
    """'Der_Fuchsbau/bei Nacht' -> ['Der_Fuchsbau', 'bei Nacht'] (leere Teile und '..' fallen weg)."""
    return [p.strip() for p in re.split(r"[/\\]", text or "") if p.strip() and p.strip() not in (".", "..")]


def render_pattern(pattern: str, when: datetime, *, cam: str, kuerzel: str, profil: str) -> str:
    """Dateimuster eines Profils: {cam} {kuerzel} {profil} plus Datums-Platzhalter."""
    text = pattern.replace("{cam}", cam).replace("{kuerzel}", kuerzel).replace("{profil}", profil)
    return render_tokens(text, when)


def in_time_window(now: datetime, start: str | None, end: str | None) -> bool:
    """Liegt now im Fenster start..end ('HH:MM[:SS]')? Fenster ueber Mitternacht sind erlaubt."""
    if not start or not end:
        return True
    cur = now.strftime("%H:%M:%S")
    s, e = (start + ":00")[:8] if len(start) == 5 else start, (end + ":00")[:8] if len(end) == 5 else end
    if s == e:
        return True
    return s <= cur < e if s < e else (cur >= s or cur < e)
