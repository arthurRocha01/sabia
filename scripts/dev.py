"""Sobe o motor e o cliente com um comando.

    python scripts/dev.py              motor (:8000) e cliente (:5173)
    python scripts/dev.py --engine     só o motor
    python scripts/dev.py --client     só o cliente

Ctrl+C derruba os dois.

O cuidado que justifica este script existir: `npm run dev` cria o servidor do
Vite como processo **filho**, e o `uvicorn --reload` cria o próprio
recarregador. Matar apenas o processo direto deixaria os netos vivos segurando
as portas — e o sintoma é "a porta 8000 já está em uso" no dia seguinte. Por
isso cada filho nasce numa sessão própria e é morto pelo **grupo** de
processos.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess  # noqa: S404 - é um script de desenvolvimento
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CLIENTE = RAIZ / "web"
ENGINE_PORT = 8000
CLIENT_PORT = 5173

AZUL = "\033[38;5;68m"
VERDE = "\033[38;5;71m"
CINZA = "\033[38;5;244m"
FIM = "\033[0m"


def _pinta(texto: str, cor: str) -> str:
    """Cor só quando a saída é um terminal: em log ou arquivo, sai limpo."""
    return f"{cor}{texto}{FIM}" if sys.stdout.isatty() else texto


def _porta_livre(porta: int) -> bool:
    """A porta está livre? O teste é tentar ocupá-la."""
    import socket

    with socket.socket() as teste:
        teste.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            teste.bind(("127.0.0.1", porta))
        except OSError:
            return False
    return True


def _conferir() -> None:
    """Falha cedo, com mensagem útil, em vez de dar erro obscuro no meio."""
    for porta, nome in ((ENGINE_PORT, "motor"), (CLIENT_PORT, "cliente")):
        if not _porta_livre(porta):
            raise SystemExit(
                f"a porta {porta} já está em uso — o {nome} já está no ar? "
                f"encerre-o antes, ou use outro comando para não subir duas vezes"
            )
    if not (RAIZ / ".env").exists():
        raise SystemExit("falta o .env na raiz (motor): copie de .env.example")
    if not (CLIENTE / "node_modules").exists():
        raise SystemExit("falta instalar o cliente: cd web && npm install")
    if not (CLIENTE / ".env").exists():
        raise SystemExit("falta o web/.env (cliente): copie de web/.env.example")


def _eco(fluxo, prefixo: str) -> None:
    """Repassa a saída de um filho, linha a linha, com o dono na frente."""
    for linha in iter(fluxo.readline, ""):
        print(f"{prefixo}{linha.rstrip()}", flush=True)


def _subir(nome: str, comando: list[str], onde: Path, cor: str) -> subprocess.Popen:
    processo = subprocess.Popen(  # noqa: S603 - comando fixo, definido aqui
        comando,
        cwd=onde,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,  # sessão própria: dá para matar o grupo inteiro
    )
    prefixo = _pinta(f"{nome:>7} | ", cor)
    threading.Thread(target=_eco, args=(processo.stdout, prefixo), daemon=True).start()
    return processo


def _derrubar(processos: list[subprocess.Popen]) -> None:
    """Mata o grupo de cada filho; se algum resistir, mata de vez."""
    for processo in processos:
        if processo.poll() is None:
            try:
                os.killpg(os.getpgid(processo.pid), signal.SIGTERM)
            except ProcessLookupError:
                continue
    limite = time.monotonic() + 5
    for processo in processos:
        if processo.poll() is None:
            try:
                processo.wait(timeout=max(0.1, limite - time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(processo.pid), signal.SIGKILL)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sobe o motor e o cliente do Sabiá.")
    parser.add_argument("--engine", action="store_true", help="só o motor")
    parser.add_argument("--client", action="store_true", help="só o cliente")
    argumentos = parser.parse_args()
    so_motor = argumentos.engine and not argumentos.client
    so_cliente = argumentos.client and not argumentos.engine

    _conferir()

    processos: list[subprocess.Popen] = []
    if not so_cliente:
        processos.append(
            _subir(
                "motor",
                [
                    str(RAIZ / ".venv" / "bin" / "uvicorn"),
                    "api.index:app",
                    "--reload",
                    "--port",
                    str(ENGINE_PORT),
                ],
                RAIZ,
                AZUL,
            )
        )
    if not so_motor:
        processos.append(
            _subir(
                "cliente",
                ["npm", "run", "dev", "--", "--port", str(CLIENT_PORT)],
                CLIENTE,
                VERDE,
            )
        )

    print(_pinta(f"\n  motor   http://localhost:{ENGINE_PORT}", AZUL))
    if not so_motor:
        print(_pinta(f"  cliente http://localhost:{CLIENT_PORT}", VERDE))
    print(_pinta("  Ctrl+C derruba os dois\n", CINZA))

    def encerrar(*_: object) -> None:
        print(_pinta("\ndesligando...", CINZA))
        _derrubar(processos)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, encerrar)
    signal.signal(signal.SIGTERM, encerrar)

    # Se um dos dois cair sozinho, o outro não fica órfão.
    while True:
        for processo in processos:
            if processo.poll() is not None:
                print(_pinta(f"\num dos processos saiu ({processo.returncode})", CINZA))
                _derrubar(processos)
                return int(processo.returncode or 0)
        time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
