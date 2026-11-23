from __future__ import annotations

from contextlib import asynccontextmanager
import secrets
import importlib
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from server import bootstrap, database


def async_method(method):
    async def invoke(*args, **kwargs):
        return method(*args, **kwargs)
    return invoke


@pytest.fixture
def local_database(monkeypatch):
    engine = create_engine("sqlite://")
    database.Base.metadata.create_all(engine)

    @asynccontextmanager
    async def begin():
        with engine.begin() as connection:
            yield SimpleNamespace(run_sync=async_method(lambda callback: callback(connection)))

    @asynccontextmanager
    async def sessions():
        with Session(engine) as session:
            yield SimpleNamespace(
                scalar=async_method(session.scalar), execute=async_method(session.execute),
                flush=async_method(session.flush), commit=async_method(session.commit),
                add=session.add, add_all=session.add_all,
            )

    monkeypatch.setattr(bootstrap, "engine", SimpleNamespace(begin=begin))
    monkeypatch.setattr(importlib.import_module("server.database"), "async_session_factory", sessions)
    monkeypatch.setattr(bootstrap, "cfg", SimpleNamespace(
        bootstrap_admin_password=secrets.token_urlsafe(18), is_production=True,
        shop_public_url="https://shop.example.invalid", crm_base_url="https://crm.example.invalid",
        dns_domain="example.invalid",
    ))
    monkeypatch.setenv("CRM_PUBLIC_URL", "https://crm.example.invalid")
    yield engine
    engine.dispose()


def snapshot(engine):
    with engine.connect() as connection:
        return {table.name: connection.execute(
            select(table).order_by(*table.primary_key.columns)).all()
            for table in database.Base.metadata.sorted_tables}


@pytest.mark.asyncio
@pytest.mark.parametrize("password_configured", [False, True])
@pytest.mark.parametrize("account_exists", [False, True])
async def test_populated_bootstrap_preserves_accounts_and_catalog(local_database, monkeypatch, password_configured, account_exists):
    with Session(local_database) as session:
        if account_exists:
            session.add(database.User(username="admin", email="operator@example.invalid",
                                      password_hash="operator-owned-hash", role="operator"))
        session.add(database.Product(name="Operator product", sku="OPERATOR-1",
                                     price=19.5, stock=7, is_active=0))
        session.commit()
    if not password_configured:
        monkeypatch.setattr(bootstrap.cfg, "bootstrap_admin_password", "")
    before = snapshot(local_database)

    await bootstrap.bootstrap_database()
    await bootstrap.bootstrap_database()

    assert snapshot(local_database) == before


@pytest.mark.asyncio
async def test_initial_bootstrap_is_idempotent(local_database):
    await bootstrap.bootstrap_database()
    first = snapshot(local_database)
    assert first["users"] and first["products"]

    await bootstrap.bootstrap_database()

    assert snapshot(local_database) == first
