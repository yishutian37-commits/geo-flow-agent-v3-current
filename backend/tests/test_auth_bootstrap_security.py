import pytest

import app.main as main


def test_env_flag_enabled_accepts_explicit_truthy_values(monkeypatch):
    for value in ["1", "true", "TRUE", "yes", "on"]:
        monkeypatch.setenv("GEO_TEST_FLAG", value)
        assert main._env_flag_enabled("GEO_TEST_FLAG") is True


def test_env_flag_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("GEO_TEST_FLAG", raising=False)
    assert main._env_flag_enabled("GEO_TEST_FLAG") is False


@pytest.mark.asyncio
async def test_default_project_owner_seed_is_opt_in(monkeypatch):
    class FailingSessionFactory:
        def __call__(self):
            raise AssertionError("database should not be opened when default seed is disabled")

    monkeypatch.setattr(main, "SEED_DEFAULT_PROJECT_OWNER", False)
    monkeypatch.setattr(main, "AsyncSessionLocal", FailingSessionFactory())

    await main.ensure_default_project_owner()
