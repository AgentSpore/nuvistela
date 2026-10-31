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
