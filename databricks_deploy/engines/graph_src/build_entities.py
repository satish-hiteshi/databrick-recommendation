import json
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
RAW = _ROOT / "data" / "raw"
OUT = _ROOT / "data" / "entities.jsonl"
STATS = _ROOT / "results" / "load_file_stats.json"

COMPOSITIONS = RAW / "all_compositions_v2.json"
PROFILES = RAW / "entity_profiles_v2.json"

# Per-attribute-type canonicalization maps: lower(trim(value)) -> display string.
# Guarantees case-insensitive dedup with a stable, first-seen display casing so
# MERGE-by-name in Neo4j dedups correctly.
_canon = {}


def _canon_value(kind, value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    table = _canon.setdefault(kind, {})
    key = s.lower()
    if key not in table:
        table[key] = s  # preserve first-seen display casing
    return table[key]


def _canon_list(kind, values):
    out, seen = [], set()
    for v in values or []:
        cv = _canon_value(kind, v)
        if cv is None:
            continue
        k = cv.lower()
        if k not in seen:
            seen.add(k)
            out.append(cv)
    return out


def _coerce_int(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return None


def main():
    compositions = json.loads(COMPOSITIONS.read_text())
    profiles = json.loads(PROFILES.read_text())

    prof_by_id = {p["entity_id"]: p for p in profiles}
    # (normalized name, vertical) -> profile, for the TV id-drift fallback.
    prof_by_nv = {}
    for p in profiles:
        key = (str(p.get("name", "")).strip().lower(), p.get("vertical"))
        prof_by_nv.setdefault(key, p)

    n_id_join = 0
    n_nv_join = 0
    n_missing_desc = 0
    matched_profile_ids = set()
    records = []

    for c in compositions:
        eid = c["entity_id"]
        prof = prof_by_id.get(eid)
        join_method = None
        if prof is not None:
            join_method = "entity_id"
            n_id_join += 1
        else:
            key = (str(c.get("name", "")).strip().lower(), c.get("vertical"))
            prof = prof_by_nv.get(key)
            if prof is not None:
                join_method = "name_vertical"
                n_nv_join += 1
            else:
                prof = {}  # should not happen; all 6,945 join per PROMPT 00
                join_method = "unjoined"
        if prof:
            matched_profile_ids.add(prof.get("entity_id"))

        # description MUST be the composition's composed_text (enriched). Never the profile's.
        description = (c.get("composed_text") or "").strip()
        if not description:
            n_missing_desc += 1

        name = (prof.get("name") or c.get("name") or "").strip()
        vertical = prof.get("vertical") or c.get("vertical")

        rec = {
            "entity_id": eid,
            "name": name,
            "vertical": vertical,
            "description": description,
            "word_count": _coerce_int(c.get("word_count")),
            "bm25_keywords": _canon_list("bm25", c.get("bm25_keywords")),
            "genres": _canon_list("genre", prof.get("canonical_genres")),   # canonical_genres!
            "themes": _canon_list("theme", prof.get("themes")),
            "keywords": _canon_list("keyword", prof.get("keywords")),
            "franchise": _canon_value("franchise", prof.get("franchise")),
            "developer": _canon_value("developer", prof.get("developer")),
            "publisher": _canon_value("publisher", prof.get("publisher")),
            "_join": join_method,
        }
        records.append(rec)

    # Surplus profiles: present in profiles, never matched to any composition.
    surplus = [p for p in profiles if p.get("entity_id") not in matched_profile_ids]
    surplus_summary = {
        "count": len(surplus),
        "by_vertical": dict(Counter(p.get("vertical") for p in surplus)),
        "examples": [{"entity_id": p["entity_id"], "name": p.get("name"),
                      "vertical": p.get("vertical")} for p in surplus],
    }

    # Per-attribute coverage (entities having >= 1 value).
    def cov(field):
        return sum(1 for r in records if r[field])
    coverage = {
        "genres": cov("genres"), "themes": cov("themes"), "keywords": cov("keywords"),
        "franchise": cov("franchise"), "developer": cov("developer"), "publisher": cov("publisher"),
        "bm25_keywords": cov("bm25_keywords"), "description": cov("description"),
    }
    distinct = {k: len(v) for k, v in _canon.items()}

    # Write JSONL (drop the internal _join helper from the persisted record).
    with OUT.open("w") as f:
        for r in records:
            r_out = {k: v for k, v in r.items() if k != "_join"}
            f.write(json.dumps(r_out, ensure_ascii=False) + "\n")

    stats = {
        "total_entities": len(records),
        "joined_on_entity_id": n_id_join,
        "joined_via_name_vertical_fallback": n_nv_join,
        "unjoined": sum(1 for r in records if r["_join"] == "unjoined"),
        "entities_missing_description": n_missing_desc,
        "vertical_split": dict(Counter(r["vertical"] for r in records)),
        "surplus_profiles_excluded": surplus_summary,
        "attribute_coverage": coverage,
        "distinct_attribute_values": distinct,
        "output_file": str(OUT.relative_to(_ROOT)),
    }
    STATS.write_text(json.dumps(stats, indent=2, ensure_ascii=False))

    # Console report
    print(f"Wrote {len(records)} records -> {OUT.relative_to(_ROOT)}")
    print(f"  join: {n_id_join} on entity_id + {n_nv_join} via (name,vertical) TV fallback "
          f"= {n_id_join + n_nv_join}")
    print(f"  unjoined: {stats['unjoined']}  |  missing description: {n_missing_desc}")
    print(f"  vertical split: {stats['vertical_split']}")
    print(f"  surplus profiles excluded: {surplus_summary['count']} "
          f"{surplus_summary['by_vertical']}")
    print("  per-attribute coverage (entities with >=1):")
    for k in ["genres", "themes", "keywords", "franchise", "developer", "publisher"]:
        print(f"      {k:10}: {coverage[k]:5}  ({distinct.get(_kind_for(k), 0)} distinct)")
    print(f"      bm25_keywords (Entity prop): {coverage['bm25_keywords']}")
    print(f"  stats -> {STATS.relative_to(_ROOT)}")


def _kind_for(field):
    return {"genres": "genre", "themes": "theme", "keywords": "keyword",
            "franchise": "franchise", "developer": "developer", "publisher": "publisher"}[field]


if __name__ == "__main__":
    main()
