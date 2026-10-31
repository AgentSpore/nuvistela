from app.channels.telegram import set_webhook


def test_missing_env_prints_failure_without_values(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "x")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:secret-token")
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_URL", raising=False)
    assert set_webhook.main() == 2
    out = capsys.readouterr().out
    assert out.startswith("failure") and "secret-token" not in out


def test_failure_prints_class_only(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", "x")
    for name, value in (
        ("TELEGRAM_BOT_TOKEN", "123:secret-token"),
        ("TELEGRAM_WEBHOOK_SECRET", "s"),
        ("TELEGRAM_WEBHOOK_URL", "https://x.test/hook"),
    ):
        monkeypatch.setenv(name, value)

    async def boom(token: str, secret: str, url: str) -> None:
        raise RuntimeError(f"bad {token}")

    monkeypatch.setattr(set_webhook, "register", boom)
    assert set_webhook.main() == 1
    assert capsys.readouterr().out.strip() == "failure: RuntimeError"
