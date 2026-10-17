import dataclasses
import time

import pytest
from fastapi.testclient import TestClient

from automateum.config import Config
from automateum.nucleo.registro import OK, ROTINAS
from automateum.web.api import criar_app

LOCAL = {"host": "127.0.0.1:8765"}
ORIGEM = {"origin": "http://127.0.0.1:8765"}


@pytest.fixture
def app(tmp_path):
    pasta_dados = tmp_path / "dados"
    pasta_dados.mkdir()
    cfg = Config(dados={"painel": {"porta": 8765}}, segredos={}, pasta_dados=pasta_dados)
    return criar_app(cfg)


@pytest.fixture
def cliente(app):
    # sem "with": o agendador não sobe, então nenhuma rotina roda sozinha durante o teste
    c = TestClient(app)
    c.headers.update(LOCAL)
    return c


def _token(cliente) -> str:
    texto = cliente.get("/dados/acoes.js").text
    return texto.split('"token": "', 1)[1].split('"', 1)[0]


def _pedir(cliente, acao, token=None, origem=True):
    cabecalhos = {"X-Mapa-Token": token or _token(cliente)}
    if origem:
        cabecalhos.update(ORIGEM)
    return cliente.post("/acao", json={"acao": acao}, headers=cabecalhos)


# --- Ações do mapa

def test_acao_exige_token_e_origem_local(cliente):
    assert _pedir(cliente, "medir-agora", token="errado").status_code == 403
    assert _pedir(cliente, "medir-agora", origem=False).status_code == 403


def test_acao_desconhecida_e_pedido_invalido(cliente):
    assert _pedir(cliente, "provar-mapa").status_code == 400
    assert _pedir(cliente, "rodar:nao_existe").status_code == 400


def test_acao_aceita_id_do_no_do_mapa(cliente, monkeypatch):
    monkeypatch.setitem(ROTINAS, "saude", dataclasses.replace(ROTINAS["saude"], func=lambda ctx: "ok"))
    assert _pedir(cliente, "rodar:rot-saude").status_code == 200
    assert _pedir(cliente, "desligar:rot-saude").json() == {"id": 0}


def test_rodar_devolve_id_e_estado_chega_ao_fim(cliente, monkeypatch):
    monkeypatch.setitem(ROTINAS, "saude", dataclasses.replace(ROTINAS["saude"], func=lambda ctx: "tudo certo"))

    r = _pedir(cliente, "medir-agora")
    assert r.status_code == 200
    eid = r.json()["id"]

    for _ in range(100):
        estado = cliente.get(f"/estado/{eid}", headers={"X-Mapa-Token": _token(cliente)}).json()
        if estado["fim"]:
            break
        time.sleep(0.05)
    assert estado["codigo"] == 0
    assert estado["texto"] == "tudo certo"


def test_estado_de_execucao_inexistente(cliente):
    r = cliente.get("/estado/999999", headers={"X-Mapa-Token": _token(cliente)})
    assert r.status_code == 404
    assert r.json()["erro"]


def test_desligar_e_ligar_persistem_na_agenda(app, cliente):
    agendador = app.state.agendador
    assert _pedir(cliente, "desligar:saude").json() == {"id": 0}
    assert agendador.quando(ROTINAS["saude"]) == "nunca"
    assert agendador._sched.get_job("saude") is None

    assert _pedir(cliente, "ligar:saude").json() == {"id": 0}
    assert agendador.quando(ROTINAS["saude"]) == ROTINAS["saude"].quando
    assert agendador._sched.get_job("saude") is not None
