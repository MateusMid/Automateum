"""Orca (o app que organiza os projetos e as worktrees nesta máquina), pela CLI dele.

Regra deste módulo: o Automateum só ESCREVE texto na caixa de entrada de um agente. Nunca envia: a única
função que digita (`digitar`) não tem como passar Enter, e quem aperta Enter, e assim autoriza, é você.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ..config import Config
from ..nucleo.registro import FALHA, OK, PARADO, Checagem, registrar_servico
from .claude import _SEM_JANELA

_LIMITE_PROMPT = 6000
# Orca fechado não é problema: o resto do Automateum funciona sem ele, e os prompts esperam ele abrir.
FECHADO = "Orca fechado: os prompts esperam ele abrir"
_CONTROLE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")  # tudo que é controle, menos \n (0x0a) e \t (0x09)


def _executavel(config: Config | None = None) -> str | None:
    manual = (config.secao("orca").get("caminho") if config else "") or ""
    if manual and Path(manual).exists():
        return manual
    achado = shutil.which("orca")
    if achado or sys.platform != "win32":
        return achado
    # o instalador do Orca não põe a CLI no PATH da tarefa agendada: procura onde ele instala
    padrao = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "orca" / "resources" / "bin" / "orca.exe"
    return str(padrao) if padrao.exists() else None


def configurado(config: Config) -> str | None:
    return None if _executavel(config) else "a CLI do Orca (`orca`) não foi encontrada"


def _rodar(config: Config, *args: str, timeout: int = 60, json_: bool = True) -> dict | str:
    comando = [_executavel(config), *args] + (["--json"] if json_ else [])
    r = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", timeout=timeout, **_SEM_JANELA)
    if not json_:
        if r.returncode != 0:
            raise RuntimeError(f"orca {args[0]} saiu com código {r.returncode}: {(r.stderr or r.stdout).strip()[:300]}")
        return r.stdout
    try:
        saida = json.loads(r.stdout)
    except ValueError:
        raise RuntimeError(f"orca {args[0]} devolveu algo ilegível: {(r.stderr or r.stdout).strip()[:300]}") from None
    if not saida.get("ok"):
        erro = saida.get("error") or {}
        raise RuntimeError(f"orca {args[0]}: {(erro.get('message') if isinstance(erro, dict) else erro) or saida}"[:300])
    return saida["result"]


def _status(config: Config) -> str:
    try:
        return _rodar(config, "status", json_=False, timeout=30)
    except RuntimeError:
        return ""   # com o app fechado a CLI sai com erro ("Could not read Orca runtime metadata")


def aberto(config: Config) -> bool:
    """O app do Orca está aberto e respondendo (a CLI só cria worktree e digita com ele aberto)."""
    return "runtimeReachable: true" in _status(config)


def checar(config: Config) -> Checagem:
    inicio = time.perf_counter()
    try:
        texto = _status(config)
    except (OSError, subprocess.TimeoutExpired) as e:
        return Checagem(FALHA, f"o Orca não respondeu: {e}")
    ms = round((time.perf_counter() - inicio) * 1000)
    if "runtimeReachable: true" not in texto:
        return Checagem(PARADO, FECHADO, ms)   # cinza no mapa, sem contar como problema
    return Checagem(OK, "Orca aberto e respondendo", ms)


def limpar(texto: str) -> str:
    """O texto que vai para a caixa de entrada: sem controles (escape, retorno de carro...), com tamanho limitado.

    Só \\n e \\t sobrevivem. Mesmo assim o texto nunca é enviado daqui.
    """
    texto = _CONTROLE.sub("", texto.replace("\r\n", "\n").replace("\r", "\n"))
    if len(texto) > _LIMITE_PROMPT:
        texto = texto[:_LIMITE_PROMPT].rstrip() + "\n[texto cortado]"
    return texto


def repo_info(config: Config, github: str) -> dict | None:
    """O repositório `dono/nome` do GitHub como o Orca o conhece (id, pasta, nome do remote), ou None se não estiver nele."""
    chave = f"github.com/{github}".lower()
    for repo in _rodar(config, "repo", "list").get("repos", []):
        if str((repo.get("gitRemoteIdentity") or {}).get("canonicalKey", "")).lower() == chave:
            return repo
    return None


def repo_id(config: Config, github: str) -> str | None:
    """O id que o Orca deu ao repositório, ou None se não estiver no Orca."""
    repo = repo_info(config, github)
    return repo["id"] if repo else None


def buscar_branch(repo: dict, branch: str) -> str:
    """Traz do GitHub o branch de um PR para o clone do Orca (só leitura) e devolve o nome para usar de base."""
    remoto = (repo.get("gitRemoteIdentity") or {}).get("remoteName") or "origin"
    r = subprocess.run(["git", "-C", repo["path"], "fetch", "--quiet", remoto, branch], capture_output=True, text=True,
                       encoding="utf-8", timeout=120, **_SEM_JANELA)
    if r.returncode != 0:
        raise RuntimeError(f"não consegui buscar o branch {branch}: {(r.stderr or r.stdout).strip()[:200]}")
    return f"{remoto}/{branch}"


def worktree_existe(config: Config, caminho: str) -> bool:
    """Se o Orca ainda tem uma worktree nesse caminho (quem remove a worktree no Orca a faz sumir daqui também)."""
    alvo = caminho.replace("\\", "/").rstrip("/").lower()
    return any(str(w.get("path", "")).replace("\\", "/").rstrip("/").lower() == alvo
               for w in _rodar(config, "worktree", "list").get("worktrees", []))


def pendencias(caminho: str) -> str | None:
    """O que impede apagar a worktree: arquivo modificado ou novo, ou commit que não foi enviado. None se pode apagar.

    Sem remoto a branch não tem como provar que foi enviada, então não se apaga."""
    if not Path(caminho).is_dir():
        return None
    try:
        sujo = subprocess.run(["git", "-C", caminho, "status", "--porcelain"], capture_output=True, text=True,
                              encoding="utf-8", timeout=60, **_SEM_JANELA)
        sem_enviar = subprocess.run(["git", "-C", caminho, "rev-list", "--count", "@{u}..HEAD"], capture_output=True,
                                    text=True, encoding="utf-8", timeout=60, **_SEM_JANELA)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"não consegui conferir o git: {e}"
    if sujo.returncode != 0:
        return "não consegui conferir o git"
    if sujo.stdout.strip():
        return "tem arquivos modificados ou novos sem commit"
    if sem_enviar.returncode != 0:
        return "a branch não tem remoto, então não dá para provar que foi enviada"
    if sem_enviar.stdout.strip() != "0":
        return f"{sem_enviar.stdout.strip()} commit(s) sem enviar"
    return None


def remover_worktree(config: Config, caminho: str) -> None:
    _rodar(config, "worktree", "rm", "--worktree", f"path:{caminho}", timeout=120)


def criar_worktree(config: Config, repo: str, nome: str, issue: int | None, comentario: str = "", *,
                   pr: int | None = None, base: str = "") -> dict:
    args = ["worktree", "create", "--name", nome, "--repo", f"id:{repo}", "--setup", "skip"]
    if issue:
        args += ["--issue", str(issue)]
    if pr:   # `--pr` só liga a worktree ao PR; o código vem da base, que é o branch do PR
        args += ["--pr", str(pr)]
    if base:
        args += ["--base-branch", base]
    if comentario:
        args += ["--comment", comentario]
    return _rodar(config, *args, timeout=120)["worktree"]


def terminais(config: Config, seletor: str) -> list[str]:
    """Os handles dos terminais abertos numa worktree."""
    return [t["handle"] for t in _rodar(config, "terminal", "list", "--worktree", seletor).get("terminals", [])]


def fechar_terminais(config: Config, handles: list[str]) -> None:
    """Fecha as abas desses terminais (o shell vazio que o Orca abre sozinho numa worktree nova)."""
    for h in handles:
        try:
            _rodar(config, "terminal", "close", "--terminal", h, "--tab")
        except RuntimeError:
            pass   # já fechado: tanto faz


def abrir_agente(config: Config, seletor: str, titulo: str, comando: str = "claude") -> str:
    """Abre um terminal com o agente na worktree (`id:...` ou `path:...`) e devolve o handle do terminal."""
    r = _rodar(config, "terminal", "create", "--worktree", seletor, "--title", titulo,
               "--command", comando)
    return r["terminal"]["handle"]


def esperar_pronto(config: Config, handle: str, timeout_s: int = 90) -> bool:
    """Espera o agente terminar de subir e ficar parado esperando texto."""
    try:
        r = _rodar(config, "terminal", "wait", "--terminal", handle, "--for", "tui-idle",
                   "--timeout-ms", str(timeout_s * 1000), timeout=timeout_s + 30)
    except RuntimeError:
        return False
    return bool(r.get("wait", {}).get("satisfied"))


def digitar(config: Config, handle: str, texto: str) -> None:
    """Escreve o texto na caixa de entrada do terminal. NÃO envia: não existe parâmetro para Enter aqui."""
    r = _rodar(config, "terminal", "send", "--terminal", handle, "--text", limpar(texto))
    if not r.get("send", {}).get("accepted"):
        raise RuntimeError("o Orca não aceitou o texto")


registrar_servico("orca", "Orca", checar, configurado,
                  "App que organiza os projetos e as worktrees: o Automateum deixa o prompt de cada task digitado nele.")
