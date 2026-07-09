"""Endpoint 3 (Home Feed) HTTP API — FastAPI app on :8040.

POST /home/feed → the UC3 v1.0 home-feed envelope. The user just opens the app — NO query, NO LLM on
this path. The engine (follow source + 44k graph + Qwen vectors) is built lazily on first request so
import stays cheap and the process starts even if :7688 is briefly down.
"""

from __future__ import annotations

from typing import List, Optional, Union

from fastapi import FastAPI
from pydantic import BaseModel

from . import config
from .engine import HomeFeedEngine
from .follow_source import CsvFollowSource
from .graph_moments import GraphMoments
from .request import HomeFeedRequest
from .vectors import VectorStore

app = FastAPI(title="Feeds.ai Home Feed (Endpoint 3)", version="1.0")
_engine: Optional[HomeFeedEngine] = None


def get_engine() -> HomeFeedEngine:
    global _engine
    if _engine is None:
        _engine = HomeFeedEngine(follow_source=CsvFollowSource(config.FOLLOWERS_CSV),
                                 graph=GraphMoments(), vectors=VectorStore())
    return _engine


class HomeFeedRequestBody(BaseModel):
    user_id: int
    sort_order: str = config.HOME_SORT_MODE
    time_window: Optional[str] = None
    limit: int = config.HOME_DEFAULT_LIMIT
    offset: int = config.HOME_DEFAULT_OFFSET
    seen_ids: List[int] = []
    done_ids: List[int] = []
    # entity_id | composite {profile_key|vertical, media_source_guid} | (backward-compat) bare source_id int
    dismissed_property_ids: List[Union[int, str, dict]] = []
    blocked_property_ids: List[Union[int, str, dict]] = []
    reacted_moment_ids: List[int] = []
    debug: bool = False


@app.get("/home/health")
def health() -> dict:
    return {"status": "ok", "endpoint": "home_feed", **config.summary()}


@app.post("/home/feed")
def home_feed(body: HomeFeedRequestBody) -> dict:
    req = HomeFeedRequest.from_dict(body.model_dump())
    return get_engine().build(req)
