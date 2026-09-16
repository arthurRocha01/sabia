"""Testes da configuração. Offline: nenhum ambiente real é necessário."""

import pytest

from engine.core.config import EMBEDDING_DIMENSIONS, ConfigError, load_settings

VALID_ENV = {
    "GOOGLE_API_KEY": "chave-do-google",
    "DEEPSEEK_API_KEY": "chave-do-deepseek",
    "DATABASE_URL": "postgresql://u:p@host.pooler.supabase.com:6543/postgres",
}


def test_minimal_valid_env_applies_defaults():
    settings = load_settings(dict(VALID_ENV))
    assert settings.embedding_model == "gemini-embedding-001"
    assert settings.llm_provider == "deepseek"
    assert settings.llm_model == "deepseek-flash"
    assert settings.llm_timeout == 60
    assert settings.quota_daily_texts == 1000
    assert settings.embedding_batch_chars == 16000
    assert settings.embedding_batch_delay == 10
    assert settings.embedding_dimensions == EMBEDDING_DIMENSIONS == 3072


def test_reports_all_missing_vars_at_once():
    with pytest.raises(ConfigError) as error:
        load_settings({"DEEPSEEK_API_KEY": "x"})
    assert "GOOGLE_API_KEY" in str(error.value)
    assert "DATABASE_URL" in str(error.value)


def test_gemini_provider_does_not_require_deepseek_key():
    env = {k: v for k, v in VALID_ENV.items() if k != "DEEPSEEK_API_KEY"}
    settings = load_settings({**env, "LLM_PROVIDER": "gemini"})
    assert settings.llm_provider == "gemini"
    assert settings.provider_key() == env["GOOGLE_API_KEY"]


def test_unknown_provider_is_rejected():
    with pytest.raises(ConfigError) as error:
        load_settings({**VALID_ENV, "LLM_PROVIDER": "openai"})
    assert "LLM_PROVIDER" in str(error.value)


def test_pooler_param_is_rejected_with_explanation():
    """Erro verificado na prática: o cliente Python recusa ?pgbouncer=true."""
    with pytest.raises(ConfigError) as error:
        load_settings({**VALID_ENV, "DATABASE_URL": VALID_ENV["DATABASE_URL"] + "?pgbouncer=true"})
    assert "pgbouncer" in str(error.value)


def test_non_postgres_url_is_rejected():
    with pytest.raises(ConfigError):
        load_settings({**VALID_ENV, "DATABASE_URL": "mysql://x"})


def test_non_numeric_value_is_rejected():
    with pytest.raises(ConfigError) as error:
        load_settings({**VALID_ENV, "LLM_TIMEOUT": "sessenta"})
    assert "LLM_TIMEOUT" in str(error.value)


def test_blank_values_fall_back_to_defaults():
    settings = load_settings({**VALID_ENV, "LLM_MODEL": "   ", "LLM_TIMEOUT": " "})
    assert settings.llm_model == "deepseek-flash"
    assert settings.llm_timeout == 60
