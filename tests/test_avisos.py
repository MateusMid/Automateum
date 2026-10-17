from datetime import datetime, timedelta

import pytest

from automateum.config import Config
from automateum.nucleo import grafo
from automateum.nucleo.agendador import Agendador
from automateum.nucleo.estado import Estado
from automateum.nucleo.eventos import Barramento
from automateum.nucleo.registro import FALHA, OK


@pytest.fixture
def cfg(tmp_path):
    return Config(dados={}, segredos={}, pasta_dados=tmp_path)


@pytest.fixture
def estado(cfg):
    return Estado(cfg.banco)


def _hora(minutos_atras):
    return (datetime.now() - timedelta(minutes=minutos_atras)).isoformat(timespec="seconds")


def _execucao(estado, rotina, status, minutos_atras):
    inicio = _hora(minutos_atras)
    estado._exec("INSERT INTO execucoes (rotina, inicio, fim, status) VALUES (?,?,?,?)",
                 (rotina, inicio, inicio, status))


def _aviso(estado, rotina, minutos_atras, nivel=FALHA):
    estado._exec("INSERT INTO avisos (quando, rotina, nivel, texto) VALUES (?,?,?,?)",
                 (_hora(minutos_atras), rotina, nivel, f"{rotina} falhou"))


def test_falha_sem_rodada_ok_depois_segue_pendente(estado):
    _execucao(estado, "tasks_github", "falha", 30)
    _aviso(estado, "tasks_github", 30)
    _execucao(estado, "tasks_github", "falha", 15)

    pendentes = estado.avisos(pendentes=True)
    assert len(pendentes) == 1 and not pendentes[0]["resolvido"]


def test_rodada_ok_depois_resolve_mas_o_historico_fica(estado):
    _execucao(estado, "tasks_github", "falha", 30)
    _aviso(estado, "tasks_github", 30)
    _execucao(estado, "tasks_github", "ok", 5)

    assert estado.avisos(pendentes=True) == []
    historico = estado.avisos()
    assert len(historico) == 1 and historico[0]["resolvido"] == 1
    assert historico[0]["texto"] == "tasks_github falhou"


def test_sucesso_de_outra_rotina_nao_resolve(estado):
    _execucao(estado, "tasks_github", "falha", 30)
    _aviso(estado, "tasks_github", 30)
    _execucao(estado, "saude", "ok", 5)

    assert len(estado.avisos(pendentes=True)) == 1


def test_a_rodada_que_gerou_o_aviso_nao_o_resolve(estado):
    # aviso de atenção emitido no meio de uma rodada que termina ok (ex.: mensagens além do teto)
    _execucao(estado, "resumo_mensagens", "ok", 10)
    _aviso(estado, "resumo_mensagens", 9, nivel="atencao")

    assert len(estado.avisos(pendentes=True)) == 1
    _execucao(estado, "resumo_mensagens", "ok", 2)
    assert estado.avisos(pendentes=True) == []


def test_card_de_avisos_fica_verde_apos_o_sucesso(cfg, estado):
    agendador = Agendador(cfg, estado, Barramento())
    _execucao(estado, "tasks_github", "falha", 30)
    _aviso(estado, "tasks_github", 30)

    def card():
        return next(n for c in grafo.montar(cfg, estado, agendador)["colunas"] for n in c["nos"]
                    if n["id"] == "destino:avisos")

    assert card()["estado"] == FALHA
    _execucao(estado, "tasks_github", "ok", 5)
    assert card()["estado"] == OK
    assert card()["linhas"] == ["nenhum aviso nas últimas 24 h"]
