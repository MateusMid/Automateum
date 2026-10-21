from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from automateum.config import Config
from automateum.nucleo import mapa_leo, pausa
from automateum.nucleo.estado import Estado
from automateum.nucleo.registro import ROTINAS
from automateum.web.api import criar_app

HOJE = date.today()


def test_pausa_vale_ate_o_dia_inclusive_e_acaba_sozinha(tmp_path):
    estado = Estado(tmp_path / "e.db")
    assert pausa.ate(estado) is None
    pausa.pausar(estado, HOJE + timedelta(days=3))

    assert pausa.ate(estado) == HOJE + timedelta(days=3)
    assert pausa.ate(estado, hoje=HOJE + timedelta(days=3)) == HOJE + timedelta(days=3)    # o último dia ainda pausa
    assert pausa.ate(estado, hoje=HOJE + timedelta(days=4)) is None                        # no dia seguinte volta
    pausa.retomar(estado)
    assert pausa.ate(estado) is None


def test_so_as_rotinas_de_resumo_param(tmp_path):
    estado = Estado(tmp_path / "e.db")
    pausa.pausar(estado, HOJE)
    for rid in pausa.RESUMOS:
        assert rid in ROTINAS and f"voltam no dia {HOJE + timedelta(days=1):%d/%m}" in pausa.motivo(estado, rid)
    assert pausa.motivo(estado, "coletar_slack") is None and pausa.motivo(estado, "tasks_obsidian") is None


@pytest.mark.parametrize("dia", [HOJE - timedelta(days=1), HOJE + timedelta(days=pausa.MAXIMO_DIAS + 1)])
def test_data_fora_do_intervalo_nao_pausa(tmp_path, dia):
    estado = Estado(tmp_path / "e.db")
    with pytest.raises(ValueError):
        pausa.pausar(estado, dia)
    assert pausa.ate(estado) is None


# --- pelo painel

LOCAL = {"host": "127.0.0.1:8765"}
ORIGEM = {"origin": "http://127.0.0.1:8765"}


@pytest.fixture
def app(tmp_path):
    cofre = tmp_path / "cofre"
    cofre.mkdir()
    cfg = Config(dados={"painel": {"porta": 8765}, "obsidian": {"cofre": str(cofre)}}, segredos={},
                 pasta_dados=tmp_path)
    return criar_app(cfg)


def _pedir(app, acao):
    c = TestClient(app)
    c.headers.update(LOCAL)
    token = c.get("/dados/acoes.js").text.split('"token": "', 1)[1].split('"', 1)[0]
    return c.post("/acao", json={"acao": acao}, headers={"X-Mapa-Token": token, **ORIGEM})


def test_botao_pausa_e_retoma_e_o_agendador_respeita(app):
    agendador, estado = app.state.agendador, app.state.estado
    fim = HOJE + timedelta(days=2)

    assert _pedir(app, f"pausar:{fim.isoformat()}").status_code == 200
    assert "resumos pausados" in agendador.motivo_parada(ROTINAS["meu_dia"])
    assert agendador.comecar("meu_dia") is None                          # o horário chega e não roda
    assert agendador.motivo_parada(ROTINAS["tasks_obsidian"]) is None    # as coletas seguem

    nos = mapa_leo.montar_mapa_leo(agendador.config, estado, agendador)["nos"]
    no = next(n for n in nos if n["id"] == "rot-meu_dia")
    assert no["passo"] == "pausada" and no["estado"] == "desligado" and no["pausa"]["ate"] == fim.isoformat()

    assert _pedir(app, "retomar").status_code == 200
    assert agendador.motivo_parada(ROTINAS["meu_dia"]) is None


def test_data_invalida_volta_erro(app):
    assert _pedir(app, "pausar:amanha").status_code == 400
    assert _pedir(app, f"pausar:{(HOJE - timedelta(days=1)).isoformat()}").status_code == 400
