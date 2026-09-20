"""Sobe o motor e o cliente com um comando.

    python scripts/dev.py              motor (:8000) e cliente (:5173)
    python scripts/dev.py --engine     só o motor
    python scripts/dev.py --client     só o cliente
    python scripts/dev.py --no-lan     sem expor o cliente na rede local

Ctrl+C derruba os dois — e fecha a porta que tiver sido exposta na rede.

Quando o cliente sobe, a porta do Vite é exposta na rede local pelo atalho
`expose` (ver wsl-expose.ps1), para o celular na mesma Wi-Fi alcançar o app.
A exposição é fechada junto: abrir uma porta e deixá-la aberta depois seria
pior que não abrir. Sem o atalho instalado, ou fora do WSL, o script avisa e
segue — nada aqui é obrigatório.

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
import shutil
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
LAN_TOOL = shutil.which("expose")  # atalho do WSL que expõe a porta na rede local

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


def _rede_local(acao: str, porta: int) -> bool:
    """Pede ao atalho do WSL que exponha (add) ou feche (remove) a porta."""
    resultado = subprocess.run(  # noqa: S603 - comando fixo, com o atalho do PATH
        [LAN_TOOL, "-Auto", acao, str(porta)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if resultado.returncode != 0:
        motivo = resultado.stderr.strip() or "falhou"
        print(_pinta(f"  rede local: {motivo}", CINZA))
        return False
    return True


def _endereco_do_celular(porta: int) -> str | None:
    """O endereço que o celular usa, lido do próprio atalho: fonte única."""
    resultado = subprocess.run(  # noqa: S603 - comando fixo, com o atalho do PATH
        [LAN_TOOL, "-List"], capture_output=True, text=True, timeout=60
    )
    for linha in resultado.stdout.splitlines():
        linha = linha.strip()
        if linha.startswith("http://") and linha.endswith(f":{porta}"):
            return linha
    return None


def _expor(porta: int) -> None:
    """Expõe a porta e espera ela aparecer: quem age é a tarefa, em segundo plano."""
    if not _rede_local("add", porta):
        return
    for _ in range(5):
        endereco = _endereco_do_celular(porta)
        if endereco:
            print(_pinta(f"  celular {endereco}", VERDE))
            return
        time.sleep(1)
    print(_pinta("  rede local: a porta não apareceu — confira com `expose -List`", CINZA))


def _fechar(porta: int) -> None:
    """Fecha a exposição da porta."""
    if _rede_local("remove", porta):
        print(_pinta("  rede local: porta fechada", CINZA))


def main() -> int:
    parser = argparse.ArgumentParser(description="Sobe o motor e o cliente do Sabiá.")
    parser.add_argument("--engine", action="store_true", help="só o motor")
    parser.add_argument("--client", action="store_true", help="só o cliente")
    parser.add_argument("--no-lan", action="store_true", help="não expor o cliente na rede local")
    argumentos = parser.parse_args()
    so_motor = argumentos.engine and not argumentos.client
    so_cliente = argumentos.client and not argumentos.engine

    _conferir()

    # A exposição na rede é a única parte daqui que sai desta máquina. Fica
    # ligada por padrão porque é no celular que a tela precisa ser olhada, e
    # desligada por --no-lan ou pela ausência do atalho.
    expor = False
    if not so_motor:
        if argumentos.no_lan:
            pass
        elif LAN_TOOL is None:
            aviso = "  rede local: sem o atalho `expose` — o app fica só nesta máquina"
            print(_pinta(aviso, CINZA))
        else:
            expor = True

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

    if expor:
        _expor(CLIENT_PORT)

    def encerrar(*_: object) -> None:
        print(_pinta("\ndesligando...", CINZA))
        _derrubar(processos)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, encerrar)
    signal.signal(signal.SIGTERM, encerrar)

    try:
        # Se um dos dois cair sozinho, o outro não fica órfão.
        while True:
            for processo in processos:
                if processo.poll() is not None:
                    print(_pinta(f"\num dos processos saiu ({processo.returncode})", CINZA))
                    _derrubar(processos)
                    return int(processo.returncode or 0)
            time.sleep(0.5)
    finally:
        # Fecha a porta por qualquer saída: Ctrl+C, erro, ou filho que morreu.
        if expor:
            _fechar(CLIENT_PORT)


if __name__ == "__main__":
    raise SystemExit(main())
