from __future__ import annotations

import time

from fastapi.testclient import TestClient

from neuroscalper.web.api import app


def test_local_api_starts_demo_and_never_enables_live_orders():
    with TestClient(app) as client:
        response = client.post("/api/actions/start-demo")
        assert response.status_code == 200
        time.sleep(0.25)
        status = client.get("/api/status").json()
        assert status["app"]["running"] is True
        assert status["app"]["live_orders_enabled"] is False
        assert status["market"]["price"] > 0
        stopped = client.post("/api/actions/stop").json()
        assert stopped["stopped"] is True
