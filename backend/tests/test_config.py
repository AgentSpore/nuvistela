import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert [e["loc"] for e in exc.value.errors()] == [("database_url",)]


def test_validation_error_does_not_echo_env_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sentinel-not-a-real-key")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)
    assert "sentinel-not-a-real-key" not in str(exc.value)


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, database_url="postgresql+asyncpg://u:p@h/d", **kw)


@pytest.mark.parametrize("limit", [0, -1])
def test_history_limit_must_be_positive(limit: int) -> None:
    with pytest.raises(ValidationError):
        _settings(agent_history_limit=limit, agent_request_limit=0)


def test_history_must_cover_two_messages_per_request() -> None:
    with pytest.raises(ValidationError, match="agent_history_limit"):
        _settings(agent_history_limit=19, agent_request_limit=10)
    assert _settings(agent_history_limit=20, agent_request_limit=10).agent_history_limit == 20


def test_history_validator_error_does_not_echo_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sentinel-not-a-real-key")
    with pytest.raises(ValidationError) as exc:
        _settings(agent_history_limit=1)
    assert "sentinel-not-a-real-key" not in str(exc.value)
