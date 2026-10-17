"""Resumos via GitHub Copilot CLI (`copilot`), o motor de reserva do `ia.perguntar`.

Roda sem ferramentas liberadas (nenhum --allow-tool), numa pasta vazia, com o texto pela entrada padrão.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ..config import Config
from .claude import _SEM_JANELA, _SISTEMA


def _executavel() -> str | None:
    achado = shutil.which("copilot")
    if achado or sys.platform != "win32":
        return achado
    # O winget põe o programa no PATH do usuário, mas a tarefa agendada só o vê depois do próximo logon:
    # procura nos lugares onde o winget instala.
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet"
    for padrao in ("Links/copilot.exe", "Packages/GitHub.Copilot_*/copilot.exe"):
        for caminho in sorted(base.glob(padrao)):
            return str(caminho)
    return None


def configurado(config: Config) -> str | None:
    return None if _executavel() else "o comando `copilot` não está no PATH"


def perguntar(config: Config, instrucao: str, dados: str = "") -> str:
    """Uma pergunta sem sessão e sem ferramentas; devolve só o texto da resposta."""
    secao = config.secao("copilot")
    # a CLI não tem prompt de sistema à parte: as regras vão no começo do texto
    entrada = f"{_SISTEMA}\n\n{instrucao}" + (f"\n\n<dados>\n{dados}\n</dados>" if dados else "")
    comando = [_executavel(), "-s", "--no-ask-user"]
    if secao.get("modelo"):
        comando += ["--model", secao["modelo"]]
    # Pasta vazia como diretório de trabalho: nenhum projeto entra no contexto.
    with tempfile.TemporaryDirectory(prefix="automateum-") as pasta:
        r = subprocess.run(comando, input=entrada, capture_output=True, text=True, encoding="utf-8",
                           timeout=secao.get("timeout_segundos", 240), cwd=pasta, **_SEM_JANELA)
    if r.returncode != 0:
        raise RuntimeError(f"copilot saiu com código {r.returncode}: {(r.stderr or r.stdout).strip()[:300]}")
    texto = (r.stdout or "").strip()
    if not texto:
        raise RuntimeError("copilot não devolveu texto")
    return texto
