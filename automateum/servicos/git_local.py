"""Serviço de auditoria e monitoramento de repositórios Git locais."""
from __future__ import annotations

import os
import subprocess
import time
from datetime import date, timedelta
from pathlib import Path

from ..config import Config
from ..nucleo.registro import FALHA, OK, Checagem, registrar_servico

PULAR = {
    "node_modules", "AppData", "Library", ".venv", "venv", "__pycache__",
    ".cache", "dist", "build", "target", ".next", ".gradle", ".m2",
    "Downloads", "OneDrive", "Dropbox", ".git"
}
FUNDO = 4


def _git(*argumentos: str, cwd: Path) -> str:
    try:
        pronto = subprocess.run(
            ["git", *argumentos],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=25,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return pronto.stdout.strip() if pronto.returncode == 0 else ""


def _git_deu_certo(*argumentos: str, cwd: Path) -> bool:
    try:
        pronto = subprocess.run(
            ["git", *argumentos],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return pronto.returncode == 0


def raizes_configuradas(config: Config) -> list[str]:
    cfg = config.secao("git_local")
    if cfg.get("raizes"):
        return cfg.get("raizes")
    # Alternativa padrão inteligente
    padrao = Path.home() / "orca" / "workspaces"
    if padrao.is_dir():
        return [str(padrao)]
    return [str(Path.home())]


def configurado(config: Config) -> str | None:
    raizes = raizes_configuradas(config)
    for r in raizes:
        if Path(r).expanduser().is_dir():
            return None
    return "nenhuma pasta de repositórios válida encontrada"


def listar_repositorios(raizes: list[str]) -> list[Path]:
    achados: list[Path] = []
    for raiz in raizes:
        base = Path(raiz).expanduser()
        if not base.is_dir():
            continue
        fundo_da_base = len(base.parts)
        for pasta, subpastas, _ in os.walk(base):
            aqui = Path(pasta)
            if len(aqui.parts) - fundo_da_base > FUNDO:
                subpastas[:] = []
                continue
            if ".git" in subpastas or (aqui / ".git").is_file():
                achados.append(aqui)
                subpastas[:] = []
                continue
            subpastas[:] = [p for p in subpastas if p not in PULAR and not p.startswith(".")]
    return sorted(set(achados))


def checar(config: Config) -> Checagem:
    inicio = time.perf_counter()
    raizes = raizes_configuradas(config)
    try:
        repos = listar_repositorios(raizes)
    except OSError as e:
        return Checagem(FALHA, f"erro ao varrer repositórios: {e}")
    ms = round((time.perf_counter() - inicio) * 1000)
    return Checagem(OK, f"{len(repos)} repositório(s) monitorado(s)", ms)


def olhar_repositorio(repo: Path, desde: str) -> dict:
    eu = _git("config", "user.email", cwd=repo)
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo)
    refs_velhas = not _git_deu_certo("fetch", "--all", "--prune", "--quiet", cwd=repo)

    bruto = [
        linha for linha in
        _git("log", "--all", f"--since={desde}", "--pretty=%h%x09%an%x09%ae%x09%s", cwd=repo).splitlines()
        if linha.strip()
    ]

    def _meu(linha: str) -> bool:
        pedacos = linha.split("\t")
        return bool(eu) and len(pedacos) > 2 and pedacos[2].lower() == eu.lower()

    def _enxuto(linha: str) -> str:
        pedacos = linha.split("\t")
        return "\t".join(pedacos[:2] + pedacos[3:]) if len(pedacos) > 3 else linha

    commits = [_enxuto(l) for l in bruto if _meu(l)]
    commits_de_outros = [_enxuto(l) for l in bruto if not _meu(l)]

    sujo = [
        linha for linha in _git("status", "--porcelain", cwd=repo).splitlines()
        if linha.strip()
    ]

    tem_upstream = bool(_git("rev-parse", "--abbrev-ref", "@{u}", cwd=repo))
    if tem_upstream:
        sem_subir = [
            l for l in _git("log", "@{u}..HEAD", "--pretty=%h%x09%s", cwd=repo).splitlines()
            if l.strip()
        ]
    else:
        sem_subir = []

    return {
        "projeto": repo.name,
        "caminho": str(repo),
        "branch": branch,
        "commits": commits,
        "commits_de_outros": commits_de_outros,
        "refs_velhas": refs_velhas,
        "sujo": sujo,
        "sem_subir": sem_subir,
        "sem_upstream": (not tem_upstream) and bool(branch),
    }


def auditar_dia(config: Config, dias: int = 0) -> list[dict]:
    desde = (date.today() - timedelta(days=max(0, dias))).strftime("%Y-%m-%d")
    raizes = raizes_configuradas(config)
    return [olhar_repositorio(repo, desde) for repo in listar_repositorios(raizes)]


registrar_servico(
    "git_local",
    "Git Local",
    checar,
    configurado,
    "Auditoria e monitoramento dos repositórios git locais (commits, pendências e pushs)."
)
