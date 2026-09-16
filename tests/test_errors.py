"""Testes dos erros tipados e da correspondência com o contrato."""

from engine.core import errors


def _module_errors():
    found = []
    for name in dir(errors):
        obj = getattr(errors, name)
        if isinstance(obj, type) and issubclass(obj, errors.SabiaError):
            found.append(obj)
    return found


def _concrete_errors():
    """Todos os erros definidos, exceto a base."""
    return [e for e in _module_errors() if e is not errors.SabiaError]


def test_every_error_has_contract_code_and_status():
    concrete = _concrete_errors()
    assert concrete, "no concrete error defined"
    for error in concrete:
        assert error.code in errors.CONTRACT_CODES, f"{error.__name__} is not a contract code"
        assert 400 <= error.http_status <= 599, f"{error.__name__} has an invalid HTTP status"


def test_codes_are_unique():
    codes = [e.code for e in _module_errors()]
    assert len(codes) == len(set(codes)), "two errors share the same code"


def test_error_payload_shape():
    error = errors.BookNotFound("livro não encontrado")
    payload = error.to_payload()
    assert payload == {"code": "book_not_found", "message": "livro não encontrado"}
    assert "[book_not_found]" in str(error)


def test_optional_detail_in_payload():
    error = errors.QuotaExhausted("cota do dia esgotada", detail="volta por volta de 05h")
    payload = error.to_payload()
    assert payload["detail"] == "volta por volta de 05h"
    assert payload["code"] == "quota_exhausted"


def test_base_error_is_internal():
    assert errors.SabiaError("falha inesperada").to_payload()["code"] == "internal_error"
    assert errors.SabiaError.http_status == 500
