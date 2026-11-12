import pytest

import config


def test_default_configuration_values(monkeypatch):
    monkeypatch.delenv("DATA_CACHE_SECONDS", raising=False)
    monkeypatch.delenv("MAX_RISK_DEFAULT", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.delenv("ADMIN_CHAT_ID", raising=False)

    assert config._positive_int("DATA_CACHE_SECONDS", "60") == 60
    assert config._risk_value() == 1.0
    assert config._log_level() == "INFO"
    assert config._database_path() == "nepse.db"
    assert config._admin_chat_id() == ""


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5"])
def test_cache_seconds_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setenv("DATA_CACHE_SECONDS", value)

    with pytest.raises(ValueError):
        config._positive_int("DATA_CACHE_SECONDS", "60")


@pytest.mark.parametrize("value", ["0", "-1", "5.1", "nan", "inf", "abc"])
def test_max_risk_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setenv("MAX_RISK_DEFAULT", value)

    with pytest.raises(ValueError):
        config._risk_value()


def test_max_risk_accepts_five_percent(monkeypatch):
    monkeypatch.setenv("MAX_RISK_DEFAULT", "5")

    assert config._risk_value() == 5.0


@pytest.mark.parametrize("value", ["TRACE", "INVALID", ""])
def test_log_level_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setenv("LOG_LEVEL", value)

    with pytest.raises(ValueError):
        config._log_level()


def test_log_level_accepts_debug(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "debug")

    assert config._log_level() == "DEBUG"


@pytest.mark.parametrize("value", ["", "   "])
def test_database_path_rejects_empty_values(monkeypatch, value):
    monkeypatch.setenv("DATABASE_PATH", value)

    with pytest.raises(ValueError):
        config._database_path()


@pytest.mark.parametrize("value", ["abc", "1.5", "0"])
def test_admin_chat_id_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setenv("ADMIN_CHAT_ID", value)

    with pytest.raises(ValueError):
        config._admin_chat_id()


def test_admin_chat_id_accepts_numeric_value(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "123456789")

    assert config._admin_chat_id() == "123456789"
