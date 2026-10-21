import os
import time
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from automateum.config import Config
from automateum.nucleo.agendador import Contexto
from automateum.nucleo.estado import Estado
from automateum.nucleo.registro import ROTINAS
from automateum.rotinas import tasks_obsidian
from automateum.web.api import criar_app


@pytest.fixture
def cfg(tmp_path):
    cofre = tmp_path / "cofre"
    cofre.mkdir()
    dados = tmp_path / "dados"
    dados.mkdir()
    return Config(dados={"obsidian": {"cofre": str(cofre), "dias_envelhecida": 10}}, segredos={}, pasta_dados=dados)


def _nota(cfg, nome, texto, dias_atras=0):
    caminho = cfg.cofre / nome
    caminho.write_text(texto, encoding="utf-8")
    quando = time.time() - dias_atras * 86400
    os.utime(caminho, (quando, quando))


def _rodar(cfg, estado):
    return tasks_obsidian.rodar(Contexto(cfg, estado, ROTINAS["tasks_obsidian"], estado.iniciar_execucao("tasks_obsidian")))


def _antes(dias):
    return (date.today() - timedelta(days=dias)).isoformat()


def test_datas_das_tasks_guarda_a_menor_e_esquece_as_que_sumiram(tmp_path):
    estado = Estado(tmp_path / "e.db")
    assert estado.datas_das_tasks({"a": "2026-10-10", "b": "2026-10-12"}) == {"a": "2026-10-10", "b": "2026-10-12"}
    assert estado.datas_das_tasks({"a": "2026-10-15", "c": "2026-10-01"}) == {"a": "2026-10-10", "c": "2026-10-01"}
    assert estado.datas_das_tasks({"b": "2026-10-20"}) == {"b": "2026-10-20"}   # b sumiu e voltou: conta de novo


def test_nota_antiga_ja_entra_envelhecida_e_a_nova_nao(cfg):
    estado = Estado(cfg.banco)
    _nota(cfg, "velha.md", "- [ ] renovar o domínio\n- [x] feita\n", dias_atras=30)
    _nota(cfg, "nova.md", "- [ ] ligar para o banco\n")

    assert _rodar(cfg, estado) == "2 abertas em 2 notas · 1 há mais de 10 dias"

    velhas = tasks_obsidian.envelhecidas(cfg, estado.itens(["obsidian"]))
    assert [(v["titulo"], v["dias"]) for v in velhas] == [("renovar o domínio", 30)]
    assert {i["corpo"] for i in estado.itens(["obsidian"])} == {f"aberta desde {_antes(30)}", f"aberta desde {_antes(0)}"}


def test_editar_a_nota_nao_zera_a_idade_da_task(cfg):
    estado = Estado(cfg.banco)
    _nota(cfg, "a.md", "- [ ] revisar contrato\n", dias_atras=20)
    _rodar(cfg, estado)
    _nota(cfg, "a.md", "linha nova em cima\n\n- [ ] revisar contrato\n- [ ] outra\n")   # mudou de linha e a nota é de hoje

    _rodar(cfg, estado)

    idade = {i["titulo"]: i["corpo"] for i in estado.itens(["obsidian"])}
    assert idade == {"revisar contrato": f"aberta desde {_antes(20)}", "outra": f"aberta desde {_antes(0)}"}


def test_a_gaveta_das_tasks_traz_as_envelhecidas(cfg):
    _nota(cfg, "velha.md", "- [ ] renovar o domínio\n", dias_atras=12)
    cliente = TestClient(criar_app(cfg))
    cliente.headers.update({"host": "127.0.0.1:8765"})
    _rodar(cfg, cliente.app.state.estado)

    d = cliente.get("/api/no/rotina/tasks_obsidian").json()

    assert d["envelhecidas"]["dias"] == 10
    assert [(v["titulo"], v["origem"], v["dias"]) for v in d["envelhecidas"]["lista"]] == [("renovar o domínio", "velha.md", 12)]
    assert "envelhecidas" not in cliente.get("/api/no/rotina/meu_dia").json()
