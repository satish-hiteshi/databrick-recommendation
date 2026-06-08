"""Throwaway EGRESS PROBE — answers deployment question #4: can a served model on THIS workspace make
the outbound calls the router needs (Voyage, the FM endpoint, the Graph/Vector Apps, AuraDS bolt)?

Deploy as a scratch endpoint, query once, read the verdict, delete it. We only need to see whether the
TCP/TLS connection + an HTTP response happen — not a successful auth — so no secrets are required.

Register (on Databricks):
    import mlflow
    mlflow.set_registry_uri("databricks-uc")
    mlflow.pyfunc.log_model(python_model="databricks_deploy/probe/egress_probe.py",
                            artifact_path="probe", registered_model_name="dev_feeds_silver.ml.egress_probe")
Then create a tiny serving endpoint for it, set TARGETS / BOLT_HOST env vars, and POST any body.
"""

import os
import socket
import time

import mlflow
from mlflow.models import set_model

# url|label, comma-separated; override with the TARGETS env var on the endpoint.
DEFAULT_TARGETS = (
    "https://api.voyageai.com|voyage,"
    "https://dbc-f79d5cae-0d05.cloud.databricks.com|workspace-self"
)


def _probe_http(url, timeout=8):
    import httpx
    t0 = time.time()
    try:
        r = httpx.get(url, timeout=timeout)
        return {"reachable": True, "status": r.status_code, "ms": round((time.time() - t0) * 1000)}
    except Exception as e:
        return {"reachable": False, "error": f"{type(e).__name__}: {e}",
                "ms": round((time.time() - t0) * 1000)}


def _probe_tcp(host, port, timeout=8):
    t0 = time.time()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return {"reachable": True, "ms": round((time.time() - t0) * 1000)}
    except Exception as e:
        return {"reachable": False, "error": f"{type(e).__name__}: {e}",
                "ms": round((time.time() - t0) * 1000)}


class EgressProbe(mlflow.pyfunc.PythonModel):
    def predict(self, context, model_input, params=None):
        out = {}
        for t in os.getenv("TARGETS", DEFAULT_TARGETS).split(","):
            t = t.strip()
            if not t:
                continue
            url, _, label = t.partition("|")
            out[label or url] = _probe_http(url.strip())
        bolt_host = os.getenv("BOLT_HOST")               # AuraDS host, bolt port 7687
        if bolt_host:
            out["auradb-bolt"] = _probe_tcp(bolt_host, os.getenv("BOLT_PORT", "7687"))
        return [out]


set_model(EgressProbe())
