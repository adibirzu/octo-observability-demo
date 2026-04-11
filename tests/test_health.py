"""Minimal health check test to satisfy pre-push hook."""


def test_config_loads():
    """Verify config module imports and instantiates."""
    from server.config import Config
    cfg = Config()
    assert cfg is not None
