"""Log em arquivo com rotação, para quando não há terminal (pythonw.exe, tarefa do Windows)."""
from __future__ import annotations

import logging
import socket
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

NOME = "automateum.log"


def configurar(pasta_dados: Path) -> logging.Logger:
    """Grava em `<dados>/automateum.log` (1 MB x 3 arquivos). Sem console, stdout e stderr vão para o mesmo arquivo."""
    pasta_dados.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("automateum")
    logger.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        arquivo = RotatingFileHandler(pasta_dados / NOME, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        arquivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(arquivo)
    if sys.stdout is None or sys.stderr is None:
        fluxo = _Fluxo(logger)
        sys.stdout = sys.stdout or fluxo
        sys.stderr = sys.stderr or fluxo
    return logger


def config_uvicorn(pasta_dados: Path) -> dict:
    """Manda os logs do uvicorn para o mesmo arquivo."""
    return {
        "version": 1, "disable_existing_loggers": False,
        "formatters": {"padrao": {"format": "%(asctime)s %(levelname)s %(message)s"}},
        "handlers": {"arquivo": {"class": "logging.handlers.RotatingFileHandler", "formatter": "padrao",
                                 "filename": str(pasta_dados / NOME), "maxBytes": 1_000_000,
                                 "backupCount": 3, "encoding": "utf-8"}},
        "loggers": {n: {"handlers": ["arquivo"], "level": "WARNING", "propagate": False}
                    for n in ("uvicorn", "uvicorn.error", "uvicorn.access")},
    }


def tem_console() -> bool:
    """False quando stdout é o redirecionamento para o log (evita gravar a mesma linha duas vezes)."""
    return not isinstance(sys.stdout, _Fluxo)


def porta_livre(host: str, porta: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, porta)) != 0


class _Fluxo:
    """Substitui stdout/stderr quando não existem (pythonw.exe): o que seria impresso vai para o log."""

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def write(self, texto: str) -> int:
        if texto.strip():
            self._logger.info(texto.rstrip())
        return len(texto)

    def flush(self) -> None:
        pass

    def reconfigure(self, **_) -> None:
        pass
