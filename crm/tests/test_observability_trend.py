import json
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, insert

from server.modules import observability_dashboard

ROOT = Path(__file__).parents[1]


def test_trend_card_renders_only_supplied_samples():
    template = (ROOT / 'server/templates/observability.html').read_text()
    assert 'id="signal-trend"' in template
    assert 'renderSignalTrend((payload.charts || {}).signal_trend)' in template
    script = template.split('function renderSignalTrend(', 1)[1].split('\nfunction ', 1)[0]
    fixtures = json.loads((ROOT / 'tests/fixtures/observability_trend.json').read_text())
    program = '''
const element = {innerHTML: ''};
const document = {getElementById: () => element};
function escapeHtml(value) { return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
function renderSignalTrend(''' + script + '''
const fixtures = JSON.parse(process.argv[1]);
for (const [name, data] of Object.entries(fixtures)) { renderSignalTrend(data); console.log(JSON.stringify([name, element.innerHTML])); }
renderSignalTrend({samples: [{time: '<script>', value: 1}, {time: 'later', value: null}]}); console.log(JSON.stringify(['escaped', element.innerHTML]));
renderSignalTrend({samples: Array(25).fill({time: 'x', value: 1})}); console.log(JSON.stringify(['oversized', element.innerHTML]));
'''
    result = subprocess.run(['node', '-e', program, json.dumps(fixtures)], check=True, capture_output=True, text=True)
    cards = dict(json.loads(line) for line in result.stdout.splitlines())
    assert 'Missing' in cards['missing'] and '<svg' not in cards['missing']
    assert 'Partial' in cards['partial'] and '09:05' in cards['partial'] and 'missing' in cards['partial'].lower()
    assert 'Observed' in cards['observed'] and '<svg' in cards['observed']
    assert '09:00' in cards['observed'] and '09:10' in cards['observed']
    assert 'Missing' in cards['oversized'] and '<svg' not in cards['oversized']
    assert '&lt;script&gt;' in cards['escaped'] and '<script>' not in cards['escaped']
    assert '<line' not in cards['partial']


@pytest.fixture
def trend_endpoint(monkeypatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2025, 1, 2, 1, 30, tzinfo=tz)

    async def summary():
        return {}

    for helper in (
        "_app_health_summary", "_db_health_summary", "_integration_health_summary",
        "_security_summary", "_order_sync_health",
    ):
        monkeypatch.setattr(observability_dashboard, helper, summary)
    monkeypatch.setattr(observability_dashboard, "datetime", FrozenDatetime)
    monkeypatch.setattr(observability_dashboard, "push_log", lambda *args, **kwargs: None)

    async def request_with_query(execute):
        session = AsyncMock()
        session.execute.side_effect = execute

        @asynccontextmanager
        async def session_factory():
            yield session

        monkeypatch.setattr(observability_dashboard, "async_session_factory", session_factory)
        app = FastAPI()
        app.include_router(observability_dashboard.router)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get("/api/observability/360")
        assert response.status_code == 200
        return response.json()

    return request_with_query


def render_response_card(payload):
    template = (ROOT / "server/templates/observability.html").read_text()
    script = template.split("<script", 1)[1].split(">", 1)[1].split("</script>", 1)[0]
    program = """
const elements = new Map();
const document = {getElementById(id) {
    if (!elements.has(id)) elements.set(id, {style: {}, addEventListener() {}});
    return elements.get(id);
}};
const _fetch = async (path) => {
    if (path !== '/api/observability/360') throw new Error(path);
    return {ok: true, json: async () => JSON.parse(process.argv[1])};
};
""" + script + """
setImmediate(() => console.log(elements.get('signal-trend')?.innerHTML ?? ''));
"""
    return subprocess.run(
        ["node", "-e", program, json.dumps(payload)], check=True, capture_output=True, text=True,
    ).stdout


@pytest.mark.asyncio
async def test_endpoint_supplies_ordered_bounded_samples_to_trend_card(trend_endpoint):
    first_hour = datetime(2025, 1, 1, 2)
    events = [
        (datetime(2025, 1, 2, 1, 29), "success"),
        (first_hour - timedelta(seconds=1), "success"),
        (first_hour, "success"),
        (first_hour + timedelta(minutes=10), "success"),
        (first_hour + timedelta(hours=1), "failed"),
        (first_hour + timedelta(hours=3), "success"),
        (datetime(2025, 1, 2, 1, 31), "success"),
        (None, "success"),
    ]
    table = observability_dashboard.OrderSyncAudit.__table__
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            table.create(connection)
            connection.execute(insert(table), [
                {
                    "id": index, "created_at": timestamp, "sync_status": status,
                    "source_system": "synthetic-audit-source", "sync_action": "synthetic-audit-action",
                    "source_order_id": "synthetic-order-reference", "message": "synthetic-audit-message",
                }
                for index, (timestamp, status) in enumerate(events, start=1)
            ])
            payload = await trend_endpoint(connection.execute)
    finally:
        engine.dispose()

    samples = payload["charts"]["signal_trend"]["samples"]
    assert [point["time"] for point in samples] == [
        (first_hour + timedelta(hours=hour)).isoformat() + "Z" for hour in range(24)
    ]
    assert [point["value"] for point in samples] == [2, 0, None, 1] + [None] * 19 + [1]
    assert all(point.keys() == {"time", "value"} for point in samples)
    assert "synthetic-" not in json.dumps(payload)
    card = render_response_card(payload)
    assert "Partial" in card
    assert "2025-01-01T03:00:00Z: 0" in card
    assert "2025-01-01T04:00:00Z: missing" in card


@pytest.mark.asyncio
@pytest.mark.parametrize("rows", [[], [(1, "malformed-count")]])
async def test_endpoint_keeps_trend_card_missing_without_valid_evidence(trend_endpoint, rows):
    payload = await trend_endpoint(lambda statement: rows)
    assert payload["charts"]["signal_trend"] == {"samples": []}
    card = render_response_card(payload)
    assert "Missing" in card
    assert "<svg" not in card
