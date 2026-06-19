"""V2-P6 wiring tests: engine selector (v1 unchanged / v2 selectable) + bundle cache + cold-start routing.
Run:  .venv/bin/python discovery_api/test_v2p6_wiring.py   (needs substrate :8000/:8010 up for v2)
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient

from discovery_api.src.api import app
from discovery_api.src.data_access.csv_source import CsvDataSource
from discovery_api.src.feed.profile import build_profile

client = TestClient(app)
NOW = "2026-06-18T00:00:00Z"
FAILS = []
def check(n, c, d=""):
    print(f"   [{'PASS' if c else 'FAIL'}] {n}{(' — ' + d) if d else ''}")
    if not c:
        FAILS.append(n)

def body(**k):
    return {"now": NOW, "limit": 6, **k}


def main():
    print("##### health #####")
    h = client.get("/discovery/health").json()
    check("health reports default_engine=v1 + lists v2", h.get("default_engine") == "v1" and "v2" in h.get("engines", []))

    print("\n##### v1 unchanged (default == explicit v1; no 'engine' key in v1 context) #####")
    r_def = client.post("/discovery/feed", json=body(user_id=7064)).json()
    r_v1 = client.post("/discovery/feed", json=body(user_id=7064, engine="v1")).json()
    check("v1 envelope has the v1.0 keys", all(k in r_def for k in ("version", "context", "main_feed", "carousels")))
    check("default engine is v1 (selector inert for v1)", r_def["main_feed"]["count"] == r_v1["main_feed"]["count"])
    check("v1 context has NO engine field (original serializer)", "engine" not in r_def["context"])

    print("\n##### bundle cache: cold (miss) vs warm (hit) for 12305 #####")
    t0 = time.time(); a = client.post("/discovery/feed", json=body(user_id=12305, engine="v2", debug=True)).json(); cold = time.time() - t0
    t1 = time.time(); b = client.post("/discovery/feed", json=body(user_id=12305, engine="v2", debug=True)).json(); warm = time.time() - t1
    check("1st v2 call = bundle MISS", a["debug"]["bundle_cache"] == "miss", a["debug"].get("bundle_cache"))
    check("2nd v2 call = bundle HIT", b["debug"]["bundle_cache"] == "hit", b["debug"].get("bundle_cache"))
    check("warm is much faster than cold", warm < cold * 0.6, f"cold={cold:.2f}s warm={warm:.3f}s")
    print(f"   12305 v2: COLD {cold:.2f}s  WARM {warm:.3f}s  (retrieve_calls cold={a['debug']['n_retrieve_calls']} warm={b['debug']['n_retrieve_calls']})")

    print("\n##### v2 selectable (body + query) + same v1.0 envelope + v2 debug #####")
    check("v2 context.engine == v2", b["context"].get("engine") == "v2")
    check("v2 envelope identical top-level keys", all(k in b for k in ("version", "context", "main_feed", "carousels")))
    items = b["main_feed"]["items"]
    check("v2 debug shows three-signal breakdown",
          bool(items) and all(k in items[0].get("debug", {}) for k in ("taste_match", "trending_velocity", "recency", "cluster_id")))
    car_ids = {c["carousel_id"] for c in b["carousels"]}
    check("v2 emits trending + exploration carousels", "trending" in car_ids and "exploration" in car_ids, str(sorted(car_ids)))
    rq = client.post("/discovery/feed?engine=v2", json=body(user_id=12305)).json()
    check("?engine=v2 query param works", rq["context"].get("engine") == "v2")

    print("\n##### exclusions: followed never leaks (v2, 12305) #####")
    ds = CsvDataSource().load()
    followed = set(build_profile(12305, ds).followed_entity_ids)
    feed_ids = {i["entity_id"] for i in b["main_feed"]["items"]} | {it["entity_id"] for c in b["carousels"] for it in c["items"]}
    check("no followed entity in v2 feed", not (feed_ids & followed), f"leak={feed_ids & followed}")

    print("\n##### cold-start (7064) on v2 → global fallback #####")
    rc = client.post("/discovery/feed", json=body(user_id=7064, engine="v2", debug=True)).json()
    check("cold-start v2 → mode cold_start", rc["context"]["mode"] == "cold_start")
    check("cold-start v2 → path global_fallback", rc["debug"].get("path") == "global_fallback")
    check("cold-start v2 → non-empty feed", rc["main_feed"]["count"] > 0)

    print(f"\n{'='*70}\nRESULT: {'ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}\n{'='*70}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
