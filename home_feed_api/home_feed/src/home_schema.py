"""home_schema.py — Pydantic request models for the UC3 home-feed endpoint.

Lives in the SEPARATE ``home_feed/`` folder (the UC3 surface), NOT in ``discovery/``.
This module is schema-only: it imports ONLY pydantic + typing, declares NO engine
dependency, and therefore needs NO ``sys.path`` bootstrap (unlike its sibling
``home_carousels.py``, which reuses the discovery engine as a library).

Spec: ``V1.3 Feeds Endpoints and Recommender Use Cases/UC3_Home_Feed_v1.3.md`` §5
(Input Parameters and Request Payload). The request wire format is a Databricks
serving ``dataframe_records: [ {…} ]`` envelope; ``HomeFeedBody`` models ONE record.

Pydantic target
---------------
Pydantic **v2** (installed: 2.13.x; ``databricks_deploy/serving/requirements.txt``
pins ``pydantic>=2.0``). Mutable list defaults use ``Field(default_factory=list)``
so no shared-mutable-default bug is possible. ``sort_order`` is normalised with a
v2 ``@field_validator``.

How this differs from discovery's ``HomeBody`` (``discovery/src/api.py``)
------------------------------------------------------------------------
The home feed is a DISTINCT contract from the discovery feed, not a tweak of it:

* ``user_id`` is **required** (``int``, no default). The home feed has NO anonymous
  mode — a missing ``user_id`` must 422 automatically via FastAPI. discovery's
  ``HomeBody.user_id`` is ``Optional[int] = None`` (null triggers a cold-start
  global feed).
* ``sort_order`` defaults to ``"relevance"`` and is constrained to
  ``"relevance"`` | ``"recent"`` (unknown values coerce to ``"relevance"``).
  discovery defaults to ``"hot"`` and is free-form.
* Suppression is **split into four typed lists**: ``done_ids`` (MOMENT ids,
  permanent suppression — distinct from ``seen_ids``, which is per-session) and
  ``dismissed_property_ids`` (soft) / ``blocked_property_ids`` (hard) PROPERTY
  lists. discovery collapses these into a single undifferentiated
  ``property_ids`` exclusion list plus ``seen_ids``.
* ``date_range`` is a nested **object** (``DateRange{start, end}``), not the
  ``"A..B"`` string discovery's ``HomeBody`` accepts.
* ``user_prefs`` (``UserPrefs{weight_today, excluded_platforms,
  excluded_verticals}``) is a home-feed-only block; discovery has no equivalent.
* ``carousel_slots`` / ``carousel_interval`` expose endpoint-side carousel
  interleaving control absent from ``HomeBody``.
* ``now`` pins the current time for reproducible feeds; ``HomeBody`` has no such
  field.

Schema only — NO business logic / ranking / suppression lives here.
"""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

# Allowed sort orders; anything else coerces to the first (the spec default).
_VALID_SORT_ORDERS = ("relevance", "recent")
_DEFAULT_SORT_ORDER = _VALID_SORT_ORDERS[0]


class DateRange(BaseModel):
    """Explicit ISO-8601 feed bounds (UC3 §5: ``date_range`` is an OBJECT, not a string).

    When present, it overrides ``time_window``. Both bounds are carried as raw
    strings here — validation/parsing of the timestamps is the engine's concern,
    not this schema's.
    """

    start: str
    end: str


class UserPrefs(BaseModel):
    """User-configured feed rules (UC3 §5: ``user_prefs``).

    A future (Aug–Sep) feature: the endpoint must accept and ignore these
    gracefully until implemented. All fields are optional with safe defaults.
    """

    weight_today: bool = False                                # boost moments starting today
    excluded_platforms: List[str] = Field(default_factory=list)   # e.g. ["tiktok", "xbox"]
    excluded_verticals: List[str] = Field(default_factory=list)   # e.g. ["movie"]


class HomeFeedBody(BaseModel):
    """One UC3 home-feed request record (the inner object of ``dataframe_records``).

    ``HomeFeedBody(user_id=5)`` constructs fine: every field except ``user_id``
    has a default. See the module docstring for how this diverges from
    discovery's ``HomeBody``.
    """

    # REQUIRED — no default. Missing user_id -> FastAPI 422 (home feed has no
    # anonymous mode; UC3 §5 marks user_id as the one required field).
    user_id: int

    # Pagination over the moment stream.
    limit: int = 20
    offset: int = 0

    # "relevance" (personal taste + recency blend) | "recent". Validator below
    # coerces any unknown value back to "relevance".
    sort_order: str = _DEFAULT_SORT_ORDER

    # "last_7d" | "last_30d" | null. Overridden by date_range when both are sent.
    time_window: Optional[str] = None

    # Explicit ISO-8601 bounds (object form). Overrides time_window.
    date_range: Optional[DateRange] = None

    # MOMENT-id suppression lists (distinct concerns):
    #   seen_ids  -> per-session "already seen", suppress from this stream
    #   done_ids  -> permanently marked done/watched; carries a positive ML signal
    seen_ids: List[int] = Field(default_factory=list)
    done_ids: List[int] = Field(default_factory=list)

    # PROPERTY-id suppression lists (distinct severities):
    #   dismissed_property_ids -> soft suppression
    #   blocked_property_ids   -> hard filter (never surface)
    dismissed_property_ids: List[int] = Field(default_factory=list)
    blocked_property_ids: List[int] = Field(default_factory=list)

    # User-configured feed rules (optional; accepted-and-ignored until shipped).
    user_prefs: Optional[UserPrefs] = None

    # Carousel interleaving controls.
    carousel_slots: int = 3        # number of carousel units in the response
    carousel_interval: int = 5     # insert a carousel after every N moments

    # debug -> attach per-item score breakdowns. now -> pin current time for
    # reproducible feeds (null = server time).
    debug: bool = False
    now: Optional[str] = None

    @field_validator("sort_order", mode="before")
    @classmethod
    def _coerce_sort_order(cls, v: object) -> str:
        """Coerce any unknown / null / non-string sort_order to "relevance"."""
        if isinstance(v, str) and v.strip().lower() in _VALID_SORT_ORDERS:
            return v.strip().lower()
        return _DEFAULT_SORT_ORDER
