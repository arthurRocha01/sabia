"""Configuração do motor, lida do ambiente.

Responsabilidade: reunir todas as variáveis de ambiente em um único lugar, com
validação na inicialização. Nenhuma outra parte do código lê o ambiente
diretamente, e nenhum segredo aparece no código.

O carregamento aceita um mapeamento alternativo, para que os testes rodem sem
ambiente configurado.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

# Dimensões do vetor de `gemini-embedding-001`. O banco guarda `halfvec` com
# esta dimensão (ver `Sabiá - Arquitetura.md`, seção do modelo de dados).
EMBEDDING_DIMENSIONS = 3072

# Provedores de interpretação aceitos, e a chave que cada um exige.
PROVIDERS = {
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GOOGLE_API_KEY",
}

# Variáveis obrigatórias, sempre.
REQUIRED_VARS = ("GOOGLE_API_KEY", "DATABASE_URL")


class ConfigError(Exception):
    """Configuração ausente ou inválida. Falha na inicialização, não em uso."""


def _list_value(env: Mapping[str, str], name: str) -> tuple[str, ...]:
    """Lista separada por vírgula, sem vazios. Ausente significa lista vazia."""
    bruto = (env.get(name) or "").strip()
    return tuple(item.strip() for item in bruto.split(",") if item.strip())


def _int_value(env: Mapping[str, str], name: str, default: int) -> int:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} precisa ser um número inteiro (valor lido: {raw!r})") from None


def _text_value(env: Mapping[str, str], name: str, default: str = "") -> str:
    return (env.get(name) or "").strip() or default


def _validate_database_url(url: str) -> None:
    if not url.startswith(("postgresql://", "postgres://")):
        raise ConfigError("DATABASE_URL precisa começar com postgresql://")
    # O modelo do .env.example usa <host> e <ref-do-projeto>. Sem esta checagem,
    # um endereço de exemplo passa na validação de formato e só falha depois,
    # como erro de rede ("failed to resolve host").
    if "<" in url or ">" in url:
        raise ConfigError(
            "DATABASE_URL ainda contém texto de exemplo (<>). Copie a string "
            "completa do painel do Supabase."
        )
    if "pgbouncer" in url:
        # Aprendido na prática: o parâmetro é do ecossistema Node e o cliente
        # Python o recusa com "invalid URI query parameter".
        raise ConfigError(
            "DATABASE_URL não pode conter o parâmetro 'pgbouncer': o cliente "
            "Python o recusa. Use a URL do pooler (porta 6543) sem parâmetros."
        )


@dataclass(frozen=True)
class Settings:
    """Configuração do motor, já validada."""

    google_api_key: str
    deepseek_api_key: str
    embedding_model: str
    llm_provider: str
    llm_model: str
    llm_timeout: int
    quota_daily_texts: int
    min_score_floor: float
    embedding_batch_chars: int
    embedding_batch_delay: int
    embedding_texts_per_minute: int
    database_url: str
    supabase_url: str
    supabase_publishable_key: str
    supabase_secret_key: str
    supabase_jwks_url: str
    # Origens autorizadas a chamar o motor de outro domínio. Vazio (o padrão) quer
    # dizer "só a mesma origem" — que é o caso em produção, onde o cliente e o
    # motor moram no mesmo endereço.
    allowed_origins: tuple[str, ...] = ()

    @property
    def embedding_dimensions(self) -> int:
        return EMBEDDING_DIMENSIONS

    def provider_key(self) -> str:
        """A chave exigida pelo provedor de interpretação configurado."""
        return self.deepseek_api_key if self.llm_provider == "deepseek" else self.google_api_key


def _float_value(env: Mapping[str, str], name: str, default: float) -> float:
    bruto = _text_value(env, name)
    if not bruto:
        return default
    try:
        return float(bruto.replace(",", "."))
    except ValueError as erro:
        raise ConfigError(f"{name} precisa ser um número: {bruto!r}") from erro


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Lê e valida a configuração.

    Levanta `ConfigError` reunindo tudo o que está errado de uma vez, em vez de
    reclamar de uma variável por vez.
    """
    env = os.environ if env is None else env

    missing = [name for name in REQUIRED_VARS if not _text_value(env, name)]
    if missing:
        raise ConfigError("variáveis de ambiente faltando: " + ", ".join(sorted(missing)))

    provider = _text_value(env, "LLM_PROVIDER", "deepseek").lower()
    if provider not in PROVIDERS:
        raise ConfigError(
            f"LLM_PROVIDER inválido: {provider!r}. Aceitos: {', '.join(sorted(PROVIDERS))}"
        )
    required_key = PROVIDERS[provider]
    if not _text_value(env, required_key):
        raise ConfigError(f"LLM_PROVIDER={provider} exige {required_key}")

    database_url = _text_value(env, "DATABASE_URL")
    _validate_database_url(database_url)

    # O piso de similaridade é da instalação, não do leitor: abaixo dele nada é
    # considerado conexão, e o pedido do cliente só pode subir a partir daqui.
    min_score_floor = _float_value(env, "MIN_SCORE_FLOOR", 0.65)
    if not 0.0 <= min_score_floor <= 1.0:
        raise ConfigError(f"MIN_SCORE_FLOOR precisa ficar entre 0 e 1: {min_score_floor}")

    return Settings(
        google_api_key=_text_value(env, "GOOGLE_API_KEY"),
        deepseek_api_key=_text_value(env, "DEEPSEEK_API_KEY"),
        embedding_model=_text_value(env, "EMBEDDING_MODEL", "gemini-embedding-001"),
        llm_provider=provider,
        llm_model=_text_value(env, "LLM_MODEL", "deepseek-flash"),
        llm_timeout=_int_value(env, "LLM_TIMEOUT", 60),
        quota_daily_texts=_int_value(env, "QUOTA_DAILY_TEXTS", 1000),
        min_score_floor=min_score_floor,
        embedding_batch_chars=_int_value(env, "EMBEDDING_BATCH_CHARS", 16000),
        embedding_batch_delay=_int_value(env, "EMBEDDING_BATCH_DELAY", 10),
        embedding_texts_per_minute=_int_value(env, "EMBEDDING_TEXTS_PER_MINUTE", 100),
        database_url=database_url,
        supabase_url=_text_value(env, "SUPABASE_URL"),
        supabase_publishable_key=_text_value(env, "SUPABASE_PUBLISHABLE_KEY"),
        supabase_secret_key=_text_value(env, "SUPABASE_SECRET_KEY"),
        supabase_jwks_url=_text_value(env, "SUPABASE_JWKS_URL"),
        allowed_origins=_list_value(env, "ALLOWED_ORIGINS"),
    )


@lru_cache
def get_settings() -> Settings:
    """Configuração do processo. Lida uma vez por instância."""
    return load_settings()
