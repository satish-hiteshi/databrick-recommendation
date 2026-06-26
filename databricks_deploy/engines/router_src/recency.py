"""Recency: convert an extracted temporal window (years) to UTC epoch-second bounds for a NATIVE
payload range filter on the vector record's `release_date_ts` (Unix seconds, UTC).

Stdlib only (datetime) → Databricks-portable. The vector backend then range-filters numerically:
`from_ts <= release_date_ts <= to_ts` (open where a bound is None). Putting the date on the vector
record and range-filtering at search removes the droppable NLU/vs_store date layer (RECENCY_DIAG.md).
"""
import re
from datetime import datetime, timezone


def _year_start_ts(y: int) -> int:
    return int(datetime(int(y), 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())


def _year_end_ts(y: int) -> int:
    return int(datetime(int(y), 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())


def _today_end_ts() -> int:
    d = datetime.now(timezone.utc).date()                       # dynamic current date (UTC), no hardcoded year
    return int(datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc).timestamp())


# The "new"/"newest"/"latest" recency family — the LLM extracts a window for "recent"/"last N years"
# reliably but NOT for these, so we recognise them deterministically. SORT = most-recent-first intent;
# WINDOW = default-recent. Both resolve to a today-clamped recent window (so "newest" never surfaces the
# 71 future-dated test titles). NOTE: "recent" is intentionally NOT here — the LLM already handles it.
_NEW_SORT_WORDS = ("newest", "latest", "freshest")
_NEW_WINDOW_WORDS = ("new", "newer", "newly", "lately", "nowadays", "freshly", "currently")
# A category/vertical word must accompany "new" so a TITLE token never triggers recency
# ("Fallout New Vegas", "New Girl", "New York" carry no category word).
_CATEGORY_WORDS = ("game", "movie", "film", "show", "series", "tv", "podcast", "title", "release",
                   "sci-fi", "scifi", "science fiction", "thriller", "comedy", "comedies", "horror",
                   "drama", "rpg", "action", "fantasy", "documentary", "documentaries", "crime",
                   "mystery", "western", "anime", "animation", "content", "stuff")


def detect_new_recency(raw_query, has_anchor: bool):
    """Return 'sort' | 'window' | None for the new/newest/latest family. TITLE GUARDS: never fires when an
    anchor (seed/franchise) was extracted, and requires a category/vertical word in the query — so
    'Fallout New Vegas', 'New Girl', 'New Super Mario Bros', 'New York' do NOT trigger recency."""
    if has_anchor:
        return None
    r = " " + (raw_query or "").lower() + " "
    toks = set(re.findall(r"[a-z0-9][a-z0-9'-]*", r))
    has_cat = any(c in r for c in _CATEGORY_WORDS)              # substring (covers "science fiction")
    if not has_cat:
        return None
    if any(w in toks for w in _NEW_SORT_WORDS) or "most recent" in r:
        return "sort"
    if any(w in toks for w in _NEW_WINDOW_WORDS) or "these days" in r or "right now" in r:
        return "window"
    return None


def epoch_window(temporal, raw_query=None, has_anchor: bool = False):
    """(from_ts, to_ts) UTC epoch-second bounds; None bound = open.

    LLM temporal window first ({from,to}/{from}/{to}/{year}); then, only if no seed/franchise anchor,
    the deterministic "new"/"newest"/"latest" family → a today-clamped recent window
    [(this_year-2)-01-01 .. today] (overrides the LLM's inconsistent temporal for that family, and the
    today clamp keeps future-dated test titles out). "recent"/explicit-year queries are untouched.
    """
    fr = to = None
    if isinstance(temporal, dict):
        yfrom, yto, yyear = temporal.get("from"), temporal.get("to"), temporal.get("year")
        if yyear is not None and yfrom is None and yto is None:
            yfrom = yto = yyear
        fr = _year_start_ts(yfrom) if yfrom is not None else None
        to = _year_end_ts(yto) if yto is not None else None
    if detect_new_recency(raw_query, has_anchor):              # new/newest/latest <category>
        fr = _year_start_ts(datetime.now(timezone.utc).year - 2)
        to = _today_end_ts()                                   # clamp to today → no future-dated rows
    return (fr, to)


def in_window(ts, from_ts, to_ts) -> bool:
    """Range predicate used by the vector search (and the local harness): a record with epoch
    `ts` passes iff it is within [from_ts, to_ts]. A NULL/absent ts is EXCLUDED when any bound is set
    (a date-bounded query requires a known date)."""
    if from_ts is None and to_ts is None:
        return True
    if ts is None:
        return False
    if from_ts is not None and ts < from_ts:
        return False
    if to_ts is not None and ts > to_ts:
        return False
    return True
