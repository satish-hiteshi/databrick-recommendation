from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ALLOWED_VERTICALS = {"game", "movie", "tv", "podcast", "any"}
REAL_VERTICALS = ["game", "movie", "tv", "podcast"]


def _to_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    return [str(x).strip() for x in v if str(x).strip()]


def _empty_to_none(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str):
        return v if v.strip() else None
    if v in ({}, []):
        return None
    return v


class HardConstraints(BaseModel):
    model_config = ConfigDict(extra="ignore")

    concepts: List[str] = Field(default_factory=list)          # genre/theme-level, must hold
    franchise: Optional[str] = None
    developer_relation: Optional[Dict[str, Any]] = None        # e.g. {"also_made": "RPG"} (graph-only)
    structural: Dict[str, Any] = Field(default_factory=dict)   # other REQUIRED exact attrs (mode, developer…)
    semantic_core: Optional[str] = None                        # HARD-but-semantic universe-definer
    negations: List[str] = Field(default_factory=list)         # must NOT have
    temporal: Optional[Any] = None                             # release window etc.

    @field_validator("concepts", "negations", mode="before")
    @classmethod
    def _lists(cls, v):
        return _to_list(v)

    @field_validator("franchise", "semantic_core", mode="before")
    @classmethod
    def _strs(cls, v):
        return _empty_to_none(v)

    @field_validator("developer_relation", "temporal", mode="before")
    @classmethod
    def _objs(cls, v):
        return _empty_to_none(v)

    @field_validator("structural", mode="before")
    @classmethod
    def _struct(cls, v):
        return v or {}


class SoftIntent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    semantic: Optional[str] = None                              # → vector reranks within the set
    structural_prefs: Dict[str, Any] = Field(default_factory=dict)  # → graph reranks within the set

    @field_validator("semantic", mode="before")
    @classmethod
    def _sem(cls, v):
        return _empty_to_none(v)

    @field_validator("structural_prefs", mode="before")
    @classmethod
    def _prefs(cls, v):
        return v or {}


class Seed(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    vertical: Optional[str] = None

    @field_validator("vertical", mode="before")
    @classmethod
    def _sv(cls, v):
        s = str(v or "").lower().strip()
        return s if s in REAL_VERTICALS else None


class Intent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    verticals: List[str] = Field(default_factory=list)   # explicit SET of requested verticals (source of truth)
    vertical: str = "any"                                # back-compat (derived from verticals)
    hard_constraints: HardConstraints = Field(default_factory=HardConstraints)
    soft_intent: SoftIntent = Field(default_factory=SoftIntent)
    seed_entities: List[Seed] = Field(default_factory=list)   # proper LIST of seeds, each vertical-tagged
    seed_entity: Optional[str] = None                        # back-compat (derived: comma-joined names)
    raw_query: str = ""
    notes: str = ""

    @model_validator(mode="before")
    @classmethod
    def _reconcile(cls, data):
        if not isinstance(data, dict):
            return data
        d = dict(data)

        # ── verticals (set of requested verticals) ──
        raw_vs = d.get("verticals")
        if not raw_vs:
            raw_vs = [d.get("vertical")] if d.get("vertical") else []
        norm: List[str] = []
        for x in (raw_vs if isinstance(raw_vs, list) else [raw_vs]):
            s = str(x or "").lower().strip()
            if s == "any":
                norm = list(REAL_VERTICALS)
                break
            if s in REAL_VERTICALS:
                norm.append(s)
        # "any"/unspecified → all four; dedup, preserve order
        if not norm:
            norm = list(REAL_VERTICALS) if str(d.get("vertical", "")).lower() == "any" else []
        seen = set()
        norm = [x for x in norm if not (x in seen or seen.add(x))]
        d["verticals"] = norm
        d["vertical"] = norm[0] if len(norm) == 1 else "any"

        # ── seed_entities (proper list; NEVER cram/mangle) ──
        se = d.get("seed_entities")
        if not se:
            old = d.get("seed_entity")
            se = []
            if isinstance(old, list):
                for x in old:
                    se.append(x if isinstance(x, dict) else {"name": str(x), "vertical": None})
            elif isinstance(old, str) and old.strip():
                # split ONLY on commas / the word 'and' — NOT '&' or ':' (Dungeons & Dragons, Hollow Knight: Silksong)
                for nm in re.split(r",|\band\b", old):
                    nm = nm.strip()
                    if nm:
                        se.append({"name": nm, "vertical": None})
        clean = []
        for x in se:
            if isinstance(x, dict) and str(x.get("name", "")).strip():
                clean.append({"name": str(x["name"]).strip(), "vertical": x.get("vertical")})
            elif isinstance(x, str) and x.strip():
                clean.append({"name": x.strip(), "vertical": None})
        d["seed_entities"] = clean
        names = [s["name"] for s in clean]
        d["seed_entity"] = ", ".join(names) if names else None
        return d


def parse_intents(data: Any) -> List[Intent]:
    if isinstance(data, dict) and isinstance(data.get("intents"), list):
        items = data["intents"]
    elif isinstance(data, dict):
        items = [data]
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError(f"expected object or array, got {type(data).__name__}")
    if not items:
        raise ValueError("no intent objects in output")
    return [Intent.model_validate(x) for x in items]


if __name__ == "__main__":
    import json
    demo = {"vertical": "GAME", "hard_constraints": {"concepts": "horror",
            "developer_relation": {"also_made": "RPG"}, "negations": []},
            "soft_intent": {"semantic": "atmospheric, dread-soaked"}, "seed_entity": "",
            "raw_query": "x"}
    print(json.dumps(parse_intents(demo)[0].model_dump(), indent=2))
