import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from automateum.config import Config
from automateum.nucleo.registro import OK, Checagem
from automateum.servicos import maquina
from automateum.web.api import criar_app


@pytest.fixture
def app(tmp_path):
    cofre = tmp_path / "cofre"
    cofre.mkdir()
    pasta_dados = tmp_path / "dados"
    pasta_dados.mkdir()
    cfg = Config(dados={"obsidian": {"cofre": str(cofre), "pasta_automateum": "Automateum/Saídas"}},
                 segredos={}, pasta_dados=pasta_dados)
    return criar_app(cfg)


@pytest.fixture
def cliente(app):
    c = TestClient(app)
    c.headers.update({"host": "127.0.0.1:8765"})
    return c


def _texto(estado, rotina, conteudo, quando="2026-10-17T11:00:00"):
    estado.definir_cursor(f"texto:{rotina}", json.dumps({"quando": quando, "conteudo": conteudo}))


# --- /api/no/servico

def test_servico_sem_tempo_medido_nao_mostra_latencia(cliente, app):
    app.state.estado.salvar_checagem("obsidian", Checagem(OK, "3 notas"))
    campos = dict(cliente.get("/api/no/servico/obsidian").json()["campos"])
    assert campos["estado"] == "3 notas" and "latência" not in campos
    app.state.estado.salvar_checagem("obsidian", Checagem(OK, "3 notas", 12))
    assert dict(cliente.get("/api/no/servico/obsidian").json()["campos"])["latência"] == "12 ms"


# --- /api/hoje

def test_hoje_sem_nenhum_texto_devolve_lista_vazia(cliente):
    d = cliente.get("/api/hoje").json()
    assert d["textos"] == [] and d["gerado"]


def test_hoje_traz_os_textos_na_ordem_do_dia(cliente, app):
    estado = app.state.estado
    _texto(estado, "dia_fechado", "Fechei o dia.")
    _texto(estado, "resumo_mensagens", "**Pede ação**\n- responder o contrato", "2026-10-17T12:00:00")
    _texto(estado, "meu_dia", "Prioridades de hoje.", "2026-10-17T08:30:00")

    textos = cliente.get("/api/hoje").json()["textos"]

    assert [t["id"] for t in textos] == ["meu_dia", "resumo_mensagens", "dia_fechado"]
    assert [t["titulo"] for t in textos] == ["Briefing do dia", "Resumo das mensagens", "Fechamento do dia"]
    assert textos[1]["conteudo"].startswith("**Pede ação**") and textos[1]["quando"] == "2026-10-17T12:00:00"
    assert textos[0]["nota"] is None                  # a nota da rotina ainda não foi escrita no cofre


def test_hoje_traz_o_fechamento_da_semana_depois_do_dia(cliente, app):
    _texto(app.state.estado, "semana_fechada", "Semana boa.", "2026-10-16T19:30:00")
    _texto(app.state.estado, "dia_fechado", "Fechei o dia.", "2026-10-16T19:00:00")
    textos = cliente.get("/api/hoje").json()["textos"]
    assert [t["titulo"] for t in textos] == ["Fechamento do dia", "Fechamento da semana"]


def test_hoje_ignora_rotinas_que_nao_geram_texto(cliente, app):
    _texto(app.state.estado, "tasks_github", "isto não é um dos textos do dia")
    assert cliente.get("/api/hoje").json()["textos"] == []


# --- /api/maquina/historico

def _medida(estado, minutos_atras, cpu, memoria):
    quando = (datetime.now() - timedelta(minutes=minutos_atras)).isoformat(timespec="seconds")
    estado._exec("INSERT INTO medidas (quando, cpu, memoria, disco_livre_gb, discos) VALUES (?,?,?,?,?)",
                 (quando, cpu, memoria, 85, json.dumps({"C:": 85, "D:": 94})))


def test_historico_filtra_pelas_horas_pedidas(cliente, app):
    estado = app.state.estado
    _medida(estado, 30, 10, 50)
    _medida(estado, 90, 20, 60)
    _medida(estado, 60 * 30, 99, 99)                  # 30 h atrás: fora da janela de 24 h

    d = cliente.get("/api/maquina/historico").json()
    assert [m["cpu"] for m in d["medidas"]] == [20, 10]                       # do mais antigo ao mais novo
    assert d["medidas"][0]["discos"] == {"C:": 85, "D:": 94}

    so_uma_hora = cliente.get("/api/maquina/historico?horas=1").json()["medidas"]
    assert [m["cpu"] for m in so_uma_hora] == [10]


def test_historico_limita_as_horas(cliente, app):
    _medida(app.state.estado, 60 * 200, 5, 5)         # 200 h atrás: além do teto de 168 h
    assert cliente.get("/api/maquina/historico?horas=100000").json()["medidas"] == []
    assert cliente.get("/api/maquina/historico?horas=0").status_code == 200   # vira 1 h, sem erro


# --- reduzir_medidas

def _lote(n):
    return [{"quando": f"2026-10-17T{i // 60:02d}:{i % 60:02d}:00", "cpu": i % 100, "memoria": 50,
             "disco_livre_gb": 90 - i // 100, "discos": {"C:": 90 - i // 100}} for i in range(n)]


def test_reduzir_nao_mexe_no_que_ja_cabe():
    medidas = _lote(100)
    assert maquina.reduzir_medidas(medidas, 240) is medidas


def test_reduzir_agrupa_com_pico_de_cpu_e_media_de_memoria():
    medidas = _lote(600)
    for i, m in enumerate(medidas):
        m["memoria"] = 40 if i % 2 == 0 else 60
    reduzidas = maquina.reduzir_medidas(medidas, 60)

    assert 55 <= len(reduzidas) <= 60
    assert all(r["memoria"] == 50 for r in reduzidas)                    # média de 40 e 60
    assert reduzidas[0]["cpu"] == max(m["cpu"] for m in medidas[:10])    # pico da faixa, não a média
    assert reduzidas[-1]["disco_livre_gb"] == medidas[-1]["disco_livre_gb"]   # disco: o último da faixa
    assert reduzidas == sorted(reduzidas, key=lambda r: r["quando"])
