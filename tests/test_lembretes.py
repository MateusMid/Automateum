from datetime import datetime, timedelta
import re

import pytest
from fastapi.testclient import TestClient

from automateum.config import Config
from automateum.nucleo.estado import Estado
from automateum.servicos import lembretes
from automateum.web.api import criar_app


def _estado(tmp_path):
    dados = tmp_path / "dados"
    dados.mkdir(exist_ok=True)
    cfg = Config(dados={"painel": {"porta": 8765}}, segredos={}, pasta_dados=dados)
    return cfg, Estado(cfg.banco)


def _cliente(cfg):
    cliente = TestClient(criar_app(cfg))
    cliente.headers.update({"host": "127.0.0.1:8765"})
    token = re.search(r'"token": "([^"]+)"', cliente.get("/dados/acoes.js").text)[1]
    return cliente, token


def _acao(cliente, token, dados, origem=True):
    cabecalhos = {"X-Mapa-Token": token}
    if origem:
        cabecalhos["Origin"] = "http://127.0.0.1:8765"
    return cliente.post("/acao", json=dados, headers=cabecalhos)


def test_criar_lembrete_normaliza_horario_local_e_valida_titulo(tmp_path):
    _, estado = _estado(tmp_path)
    horario = (datetime.now().astimezone() + timedelta(minutes=20)).isoformat(timespec="minutes")

    lembrete = lembretes.criar(estado, "  Revisar proposta  ", horario)

    assert lembrete["titulo"] == "Revisar proposta"
    assert datetime.fromisoformat(lembrete["quando"]).tzinfo is not None
    with pytest.raises(ValueError, match="escreva"):
        lembretes.criar(estado, "   ", horario)
    with pytest.raises(ValueError, match="data e hora"):
        lembretes.criar(estado, "Tarefa", "inválido")


def test_lembrete_vencido_persiste_apos_reabrir_banco(tmp_path):
    cfg, estado = _estado(tmp_path)
    horario = (datetime.now().astimezone() - timedelta(minutes=2)).isoformat(timespec="seconds")
    criado = estado.criar_lembrete("Ligar para o cliente", horario)
    estado._db.close()
    reaberto = Estado(cfg.banco)

    avisos = lembretes.notificacoes(reaberto)

    assert len(avisos) == 1
    assert avisos[0]["lembrete_id"] == criado["id"]
    assert avisos[0]["vencido"] is True
    assert avisos[0]["conteudo"] == "Está na hora."


def test_adiar_move_horario_e_exige_intervalo_predefinido(tmp_path):
    _, estado = _estado(tmp_path)
    criado = estado.criar_lembrete("Enviar relatório", datetime.now().astimezone().isoformat())

    assert lembretes.adiar(estado, criado["id"], 15)
    atualizado = estado.lembretes()[0]
    assert datetime.fromisoformat(atualizado["quando"]) >= datetime.now().astimezone() + timedelta(minutes=14)
    with pytest.raises(ValueError, match="5, 15 ou 30"):
        lembretes.adiar(estado, criado["id"], 10)


def test_concluir_remove_lembrete_das_notificacoes(tmp_path):
    _, estado = _estado(tmp_path)
    criado = estado.criar_lembrete("Separar documentos", datetime.now().astimezone().isoformat())

    assert estado.concluir_lembrete(criado["id"])
    assert estado.lembretes() == []
    assert lembretes.notificacoes(estado) == []
    assert not estado.concluir_lembrete(criado["id"])


def test_criar_lembrete_pelo_painel_exige_token_e_origem(tmp_path):
    cfg, _ = _estado(tmp_path)
    cliente, token = _cliente(cfg)
    horario = (datetime.now().astimezone() + timedelta(minutes=30)).isoformat(timespec="minutes")
    dados = {"acao": "lembrete-criar", "titulo": "Revisar pauta", "quando": horario}

    sem_token = _acao(cliente, "errado", dados)
    sem_origem = _acao(cliente, token, dados, origem=False)

    assert sem_token.status_code == 403
    assert sem_origem.status_code == 403


def test_painel_cria_adia_e_conclui_lembrete(tmp_path):
    cfg, _ = _estado(tmp_path)
    cliente, token = _cliente(cfg)
    horario = (datetime.now().astimezone() + timedelta(minutes=30)).isoformat(timespec="minutes")
    criado = _acao(cliente, token, {"acao": "lembrete-criar", "titulo": "Preparar reunião", "quando": horario})
    item = criado.json()["lembrete"]

    assert criado.status_code == 200
    avisos = cliente.get("/api/hoje").json()["textos"]
    lembrete = next(t for t in avisos if t.get("lembrete_id") == item["id"])
    assert lembrete["vencido"] is False
    assert lembrete["titulo"] == "Preparar reunião"

    adiado = _acao(cliente, token, {"acao": f"lembrete-adiar:{item['id']}:15"})
    assert adiado.status_code == 200
    depois = next(t for t in cliente.get("/api/hoje").json()["textos"] if t.get("lembrete_id") == item["id"])
    assert datetime.fromisoformat(depois["quando"]) >= datetime.now().astimezone() + timedelta(minutes=14)

    concluido = _acao(cliente, token, {"acao": f"lembrete-concluir:{item['id']}"})
    assert concluido.status_code == 200
    assert all(t.get("lembrete_id") != item["id"] for t in cliente.get("/api/hoje").json()["textos"])
