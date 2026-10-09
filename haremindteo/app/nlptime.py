"""Natural-language time parser for reminders (Polish + English). By TeodorTeo.com."""
import re
from datetime import datetime, timedelta

WEEKDAYS = {"poniedziałek": 0, "poniedzialek": 0, "wtorek": 1, "środę": 2, "srode": 2, "środa": 2, "sroda": 2, "czwartek": 3,
            "piątek": 4, "piatek": 4, "sobotę": 5, "sobote": 5, "sobota": 5, "niedzielę": 6, "niedziele": 6, "niedziela": 6,
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
UNIT_SECONDS = [("sekund", 1), ("sek", 1), ("seconds", 1), ("second", 1), ("sec", 1), ("s", 1),
                ("minut", 60), ("min", 60), ("minutes", 60), ("minute", 60), ("m", 60),
                ("godzin", 3600), ("godz", 3600), ("hours", 3600), ("hour", 3600), ("hrs", 3600), ("hr", 3600), ("h", 3600),
                ("dni", 86400), ("dzień", 86400), ("dzien", 86400), ("days", 86400), ("day", 86400), ("d", 86400)]
UNIT_RE = r"(?:sekund\w*|sek\.?|seconds?|sec|s|minut\w*|min\.?|minutes?|m|godzin\w*|godz\.?|hours?|hrs?|h|dni|dzień|dzien|days?|d)\b"
FILLERS = [r"\bprzypomnij mi\b", r"\bprzypomnij\b", r"\bremind me to\b", r"\bremind me about\b", r"\bremind me\b",
           r"\bżeby\b", r"\bzeby\b", r"\bby\b(?=\s)", r"\bthat\b"]


def unit_seconds(word):
    w = word.lower().rstrip(".")
    for prefix, secs in UNIT_SECONDS:
        if w == prefix or (len(prefix) > 2 and w.startswith(prefix)):
            return secs
    return 60


def _cut(text, m):
    return (text[:m.start()] + " " + text[m.end():]).strip()


def parse(text, now):
    """Return {"due": datetime|None, "text": str, "repeat": dict|None, "error": str|None}. `now` is timezone-aware."""
    src = " " + str(text or "").strip() + " "
    low = src.lower()
    repeat, due, error = None, None, None

    # ---- repeats
    m = re.search(r"\b(codziennie|co dzień|co dzien|every day|everyday|daily)\b", low)
    if m:
        repeat = {"type": "daily"}; src = _cut(src, m); low = src.lower()
    m = re.search(r"\b(w dni robocze|weekdays?|every weekday|dni roboczych)\b", low)
    if m:
        repeat = {"type": "weekdays"}; src = _cut(src, m); low = src.lower()
    m = re.search(r"\b(co tydzień|co tydzien|every week|weekly)\b", low)
    if m:
        repeat = {"type": "weekly"}; src = _cut(src, m); low = src.lower()
    m = re.search(r"\b(?:co|every)\s+(\d+(?:[.,]\d+)?)?\s*(" + UNIT_RE + ")", low)
    if m:
        n = float((m.group(1) or "1").replace(",", "."))
        repeat = {"type": "interval", "every": int(n * unit_seconds(m.group(2)))}
        src = _cut(src, m); low = src.lower()

    # ---- day words
    day_offset, weekday = None, None
    m = re.search(r"\b(pojutrze|day after tomorrow)\b", low)
    if m: day_offset = 2; src = _cut(src, m); low = src.lower()
    m = re.search(r"\b(jutro|tomorrow)\b", low)
    if m and day_offset is None: day_offset = 1; src = _cut(src, m); low = src.lower()
    m = re.search(r"\b(dziś|dzis|dzisiaj|today|tonight)\b", low)
    if m and day_offset is None: day_offset = 0; src = _cut(src, m); low = src.lower()
    if day_offset is None:
        m = re.search(r"\b(?:w|we|on|next)?\s*(" + "|".join(sorted(WEEKDAYS, key=len, reverse=True)) + r")\b", low)
        if m: weekday = WEEKDAYS[m.group(1)]; src = _cut(src, m); low = src.lower()

    # ---- clock time
    hh = mm = None
    m = re.search(r"(?:\b(?:o|at|@)\s*)?\b(\d{1,2})[:.](\d{2})\s*(am|pm)?\b", low)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        if m.group(3) == "pm" and hh < 12: hh += 12
        if m.group(3) == "am" and hh == 12: hh = 0
        src = _cut(src, m); low = src.lower()
    else:
        m = re.search(r"\b(?:o|at|@)\s*(\d{1,2})\s*(am|pm)?\b(?!\s*(?:" + UNIT_RE + "))", low) or re.search(r"\b(\d{1,2})\s*(am|pm)\b", low)
        if m:
            hh, mm = int(m.group(1)), 0
            if m.group(2) == "pm" and hh < 12: hh += 12
            if m.group(2) == "am" and hh == 12: hh = 0
            src = _cut(src, m); low = src.lower()
    if hh is not None and (hh > 23 or mm > 59):
        return {"due": None, "text": text, "repeat": None, "error": "invalid time"}

    # ---- relative durations
    rel = None
    if hh is None and weekday is None and day_offset is None:
        m = re.search(r"(?:\b(?:za|in)\s+)?\b(pół godziny|pol godziny|half an hour)\b", low)
        if m:
            rel = 1800; src = _cut(src, m); low = src.lower()
        else:
            m = re.search(r"\b(?:za|in)\s+((?:\d+(?:[.,]\d+)?\s*" + UNIT_RE + r"\s*(?:i|and|,)?\s*)+)", low) or \
                re.search(r"(?:^|\s)((?:\d+(?:[.,]\d+)?\s*(?:h|m|s|min|godz|sek)\b\s*)+)(?=\s|$)", low)
            if m:
                total = 0.0
                for num, unit in re.findall(r"(\d+(?:[.,]\d+)?)\s*(" + UNIT_RE + ")", m.group(1)):
                    total += float(num.replace(",", ".")) * unit_seconds(unit)
                rel = int(total); src = _cut(src, m); low = src.lower()

    if rel is not None:
        due = now + timedelta(seconds=rel)
    elif hh is not None or day_offset is not None or weekday is not None or repeat:
        if hh is None:
            if repeat and repeat["type"] == "interval":
                due = now + timedelta(seconds=repeat["every"])
            elif day_offset is not None or weekday is not None:
                hh, mm = 8, 0
            else:
                error = "time of day required for repeats (e.g. 'every day at 7:30')"
        if due is None and error is None:
            base = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if day_offset is not None:
                due = base + timedelta(days=day_offset)
            elif weekday is not None:
                ahead = (weekday - now.weekday()) % 7
                due = base + timedelta(days=ahead)
                if due <= now: due += timedelta(days=7)
            else:
                due = base if base > now else base + timedelta(days=1)
            if repeat and repeat["type"] == "weekdays":
                while due.weekday() > 4: due += timedelta(days=1)
            if due <= now and day_offset == 0:
                error = "that time has already passed today"
    else:
        error = "no time found (try 'in 15 min', 'at 18:30', 'tomorrow 8:00')"

    msg = src
    for pat in FILLERS:
        msg = re.sub(pat, " ", msg, flags=re.I)
    msg = re.sub(r"\s+", " ", re.sub(r"^[\s,.:;-]+|[\s,.:;-]+$", "", msg))
    msg = re.sub(r"^(to|na|o|że|ze)\s+", "", msg, flags=re.I) if msg.lower().startswith(("to ", "na ")) else msg
    return {"due": due, "text": msg, "repeat": repeat, "error": error}


def next_due(due, repeat, now):
    """Next occurrence after `due` for a repeating reminder (always in the future)."""
    t = repeat["type"]
    if t == "interval":
        step = max(60, int(repeat["every"]))
        while due <= now: due += timedelta(seconds=step)
        return due
    step = {"daily": 1, "weekly": 7, "weekdays": 1}[t]
    while due <= now: due += timedelta(days=step)
    if t == "weekdays":
        while due.weekday() > 4: due += timedelta(days=1)
    return due
