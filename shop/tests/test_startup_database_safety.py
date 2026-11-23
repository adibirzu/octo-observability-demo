from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from server import database


@pytest.fixture
def local_engine(monkeypatch):
    engine = create_engine("sqlite://")
    database.Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "sync_engine", engine)
    monkeypatch.setattr(database, "cfg", SimpleNamespace(
        use_postgres=False, allow_destructive_db_bootstrap=False))
    yield engine
    engine.dispose()


def product():
    return database.Product(name="Operator product", sku="OPERATOR-1",
                            price=19.5, stock=7, is_active=0)


def snapshot(engine):
    with engine.connect() as connection:
        return {table.name: connection.execute(
            select(table).order_by(*table.primary_key.columns)).all()
            for table in database.Base.metadata.sorted_tables}


def test_startup_preserves_catalog_when_users_table_is_empty(local_engine):
    with Session(local_engine) as session:
        session.add(product())
        session.commit()
    before = snapshot(local_engine)

    database.init_tables()

    assert snapshot(local_engine) == before


def test_destructive_bootstrap_requires_explicit_opt_in(local_engine, monkeypatch):
    monkeypatch.setattr(database.cfg, "allow_destructive_db_bootstrap", True)
    with Session(local_engine) as session:
        session.add(product())
        session.commit()

    database.init_tables()

    with Session(local_engine) as session:
        assert session.query(database.Product).count() == 0


@pytest.mark.parametrize(("value", "enabled"), [(None, False), ("false", False), ("true", True)])
def test_destructive_bootstrap_setting_defaults_off(monkeypatch, value, enabled):
    if value is None:
        monkeypatch.delenv("ALLOW_DESTRUCTIVE_DB_BOOTSTRAP", raising=False)
    else:
        monkeypatch.setenv("ALLOW_DESTRUCTIVE_DB_BOOTSTRAP", value)
    spec = importlib.util.spec_from_file_location(
        "startup_config", Path(database.__file__).with_name("config.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.Config.allow_destructive_db_bootstrap is enabled


@pytest.mark.parametrize("account_exists", [False, True])
def test_seeding_preserves_existing_accounts_and_catalog(local_engine, account_exists):
    with Session(local_engine) as session:
        if account_exists:
            session.add(database.User(username="admin", email="operator@example.invalid",
                                      password_hash="operator-owned-hash", role="operator", is_active=0))
        session.add(product())
        session.commit()
    before = snapshot(local_engine)

    database.seed_data()
    database.seed_data()

    assert snapshot(local_engine) == before


def test_initial_seed_is_idempotent(local_engine):
    database.seed_data()
    first = snapshot(local_engine)
    assert first["users"] and first["products"]

    database.seed_data()

    assert snapshot(local_engine) == first


def test_deploy_assets_never_enable_destructive_bootstrap():
    deploy = Path(__file__).resolve().parents[2] / "deploy"
    for path in deploy.rglob("*"):
        if path.is_file() and path.suffix in {".yaml", ".yml", ".tf", ".tftpl", ".sh", ".template"}:
            assert "ALLOW_DESTRUCTIVE_DB_BOOTSTRAP" not in path.read_text(), path
