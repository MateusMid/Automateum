import logging
import socket
import sys

from automateum.nucleo import log


def _limpar(logger):
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()


def test_configurar_grava_arquivo(tmp_path):
    logger = log.configurar(tmp_path)
    try:
        logger.info("olá")
        for h in logger.handlers:
            h.flush()
        assert "olá" in (tmp_path / log.NOME).read_text(encoding="utf-8")
    finally:
        _limpar(logger)


def test_sem_console_stdout_vai_para_o_log(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    logger = log.configurar(tmp_path)
    try:
        print("sem janela")
        sys.stdout.reconfigure(encoding="utf-8")  # não pode quebrar
        for h in logger.handlers:
            h.flush()
        assert "sem janela" in (tmp_path / log.NOME).read_text(encoding="utf-8")
    finally:
        _limpar(logger)
        logging.getLogger("automateum").handlers.clear()


def test_porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        porta = s.getsockname()[1]
        assert not log.porta_livre("127.0.0.1", porta)
    assert log.porta_livre("127.0.0.1", porta)
