"""Erros tipados do motor.

Responsabilidade: definir os erros que o domínio levanta e a correspondência
entre cada um e um código de erro do contrato. A conversão em resposta HTTP é
feita na camada de entrada, a partir do que está definido aqui.

Os códigos são os do contrato (ver `Sabiá - Arquitetura.md`, seção do contrato) e não mudam
sem que o documento mude. As mensagens são escritas em português porque
chegam ao leitor; os códigos são identificadores estáveis, em inglês.
"""


class SabiaError(Exception):
    """Base dos erros do motor.

    Cada erro carrega o código do contrato (`code`) e o estado HTTP
    correspondente (`http_status`), para que a camada de entrada não precise
    manter uma segunda tabela de correspondência.
    """

    code = "internal_error"
    http_status = 500

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def to_payload(self) -> dict[str, str]:
        """Formato único de erro do contrato: código e mensagem."""
        payload = {"code": self.code, "message": self.message}
        if self.detail:
            payload["detail"] = self.detail
        return payload

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class Unauthorized(SabiaError):
    """Pedido sem sessão válida. O leitor entra de novo antes de continuar."""

    code = "unauthorized"
    http_status = 401


class InvalidInput(SabiaError):
    """Pedido malformado ou fora dos limites (teto de palavras, número de conexões)."""

    code = "invalid_input"
    http_status = 400


class BookNotFound(SabiaError):
    """Livro inexistente no acervo de quem pediu."""

    code = "book_not_found"
    http_status = 404


class FileUnavailable(SabiaError):
    """Arquivo do livro ausente no armazenamento."""

    code = "file_unavailable"
    http_status = 404


class TextLayerMissing(SabiaError):
    """A fonte não tem camada de texto legível — recusada na validação da ingestão."""

    code = "text_layer_missing"
    http_status = 422


class QuotaExhausted(SabiaError):
    """Cota diária do provedor de embeddings esgotada. Esperar não resolve."""

    code = "quota_exhausted"
    http_status = 429


class ProviderUnavailable(SabiaError):
    """Provedor de embeddings ou de interpretação indisponível."""

    code = "provider_unavailable"
    http_status = 502


class TimedOut(SabiaError):
    """Operação excedeu o orçamento de tempo declarado no contrato."""

    code = "timed_out"
    http_status = 504


class IngestionFailed(SabiaError):
    """Ingestão interrompida. A tarefa é marcada como falhada e o arquivo é reenviado."""

    code = "ingestion_failed"
    http_status = 500


# Códigos do contrato, na ordem em que aparecem no documento. Serve de
# referência para a camada de entrada e para os testes.
CONTRACT_CODES = (
    "unauthorized",
    "invalid_input",
    "book_not_found",
    "file_unavailable",
    "text_layer_missing",
    "quota_exhausted",
    "provider_unavailable",
    "timed_out",
    "ingestion_failed",
    "internal_error",
)
