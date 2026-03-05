"""Simulation control module — toggles chaos flags and simulates issues.

Allows runtime control of DB latency, disconnects, memory leaks, CPU spikes.
"""

import asyncio
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel

from server.config import cfg
from server.observability.otel_setup import get_tracer
from server.observability.logging_sdk import push_log

router = APIRouter(prefix="/api/simulate", tags=["Issue Simulation"])
tracer_fn = get_tracer

# Runtime-mutable simulation state (overrides frozen config for chaos testing)
_sim_state = {
    "db_latency": False,
    "db_disconnect": False,
    "memory_leak": False,
    "cpu_spike": False,
    "slow_queries": False,
    "error_rate": 0.0,
}


class SimulationConfig(BaseModel):
    db_latency: bool | None = None
    db_disconnect: bool | None = None
    memory_leak: bool | None = None
    cpu_spike: bool | None = None
    slow_queries: bool | None = None
    error_rate: float | None = None


@router.get("/status")
async def simulation_status(request: Request):
    """Get current simulation state."""
    tracer = tracer_fn()
    with tracer.start_as_current_span("simulation.status"):
        return {"simulation": _sim_state}


@router.post("/configure")
async def configure_simulation(config: SimulationConfig, request: Request):
    """Toggle simulation flags at runtime."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("simulation.configure") as span:
        changes = {}
        for field, value in config.model_dump(exclude_none=True).items():
            old = _sim_state.get(field)
            _sim_state[field] = value
            changes[field] = {"old": old, "new": value}
            span.set_attribute(f"simulation.{field}", value)

        push_log("WARNING", "Simulation configuration changed", **{
            "simulation.changes": str(changes),
        })
        return {"status": "updated", "changes": changes, "current": _sim_state}


@router.post("/reset")
async def reset_simulation(request: Request):
    """Reset all simulation flags to off."""
    tracer = tracer_fn()
    with tracer.start_as_current_span("simulation.reset"):
        for key in _sim_state:
            _sim_state[key] = False if isinstance(_sim_state[key], bool) else 0.0
        push_log("INFO", "Simulation state reset to defaults")
        return {"status": "reset", "current": _sim_state}


@router.post("/db-latency")
async def trigger_db_latency(request: Request):
    """Manually trigger a DB latency spike (one-shot)."""
    tracer = tracer_fn()
    body = await request.json()
    delay = min(body.get("delay_seconds", 3.0), 30.0)

    with tracer.start_as_current_span("simulation.db_latency") as span:
        span.set_attribute("simulation.delay_seconds", delay)
        await asyncio.sleep(delay)
        push_log("WARNING", f"Simulated DB latency: {delay}s", **{
            "simulation.type": "db_latency",
            "simulation.delay": delay,
        })
        return {"status": "completed", "delay": delay}


@router.post("/db-disconnect")
async def trigger_db_disconnect(request: Request):
    """Simulate a temporary DB disconnect."""
    tracer = tracer_fn()

    with tracer.start_as_current_span("simulation.db_disconnect") as span:
        _sim_state["db_disconnect"] = True
        push_log("ERROR", "Simulated DB disconnect activated", **{
            "simulation.type": "db_disconnect",
        })
        # Auto-reset after 10 seconds
        await asyncio.sleep(10)
        _sim_state["db_disconnect"] = False
        return {"status": "db disconnect simulated for 10 seconds"}


@router.post("/error-burst")
async def trigger_error_burst(request: Request):
    """Generate a burst of errors for log/APM testing."""
    tracer = tracer_fn()
    body = await request.json()
    count = min(body.get("count", 10), 100)

    with tracer.start_as_current_span("simulation.error_burst") as span:
        span.set_attribute("simulation.error_count", count)
        for i in range(count):
            with tracer.start_as_current_span(f"simulation.error_{i}") as err_span:
                err_span.set_attribute("error.simulated", True)
                err_span.set_attribute("error.index", i)
                push_log("ERROR", f"Simulated error {i+1}/{count}", **{
                    "simulation.type": "error_burst",
                    "simulation.index": i,
                })

        return {"status": "completed", "errors_generated": count}


def get_sim_state() -> dict:
    """Accessor for middleware to check current sim state."""
    return _sim_state
