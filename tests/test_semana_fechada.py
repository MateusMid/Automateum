import os
from datetime import date, datetime

import pytest

from automateum.config import Config
from automateum.nucleo.agendador import Contexto
from automateum.nucleo.estado import Estado
from automateum.nucleo.registro import ROTINAS
from automateum.rotinas import semana_fechada
from automateum.rotinas._texto import bloco
from automateum.servicos import claude, copilot, git_local, obsidian


class _Sexta(date):
    @classmethod
    def today(cls):
        return date(2026, 10, 16)


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    cofre = tmp_path / "cofre"
    (cofre / "Diário").mkdir(parents=True)
    cfg = Config(dados={"obsidian": {"cofre": str(cofre), "pasta_diario": "Diário"}}, segredos={},
                 pasta_dados=tmp_path)
    estado = Estado(cfg.banco)
    monkeypatch.setattr(semana_fechada, "date", _Sexta)
    pedidos = []
    monkeypatch.setattr(git_local, "auditar_dia", lambda config, dias=0: pedidos.append(dias) or [])
    ctx = Contexto(cfg, estado, ROTINAS["semana_fechada"], estado.iniciar_execucao("semana_fechada"))
    return cfg, ctx, pedidos


def _perguntas(monkeypatch, resposta="**Andou** o mapa."):
    chamadas = []

    def falso(config, instrucao, dados=""):
        chamadas.append(dados)
        return resposta
    monkeypatch.setattr(claude, "perguntar", falso)
    monkeypatch.setattr(copilot, "perguntar", falso)
    return chamadas


def _diario(cfg, dia, anotacao, fechamento=None):
    texto = anotacao + "\n"
    if fechamento:
        texto = obsidian.com_bloco(texto, "dia_fechado", f"## Dia fechado\n\n{fechamento}")
    (cfg.cofre / "Diário" / f"{dia}.md").write_text(texto, encoding="utf-8")


def test_dias_da_semana_vao_de_segunda_ate_hoje():
    assert semana_fechada.dias_da_semana(date(2026, 10, 16)) == [date(2026, 10, d) for d in range(12, 17)]
    assert semana_fechada.dias_da_semana(date(2026, 10, 12)) == [date(2026, 10, 12)]


def test_bloco_devolve_so_o_conteudo_do_bloco_pedido():
    texto = obsidian.com_bloco("nota\n", "meu_dia", "manhã")
    texto = obsidian.com_bloco(texto, "dia_fechado", "## Dia fechado\n\nnoite")
    assert bloco(texto, "dia_fechado") == "## Dia fechado\n\nnoite"
    assert bloco(texto, "semana_fechada") == ""


def test_junta_os_dias_da_semana_e_escreve_no_diario_de_sexta(ambiente, monkeypatch):
    cfg, ctx, dias = ambiente
    chamadas = _perguntas(monkeypatch)
    _diario(cfg, "2026-10-09", "semana passada, não entra", "fechamento antigo")
    _diario(cfg, "2026-10-13", "reunião com o time", "terminei o login")
    _diario(cfg, "2026-10-15", "só anotei, sem fechamento")

    assert semana_fechada.rodar(ctx) == "fechamento da semana escrito em 2026-10-16.md"

    material = chamadas[0]
    assert "Fechamento de terça 13/10" in material and "terminei o login" in material
    assert "reunião com o time" in material and "só anotei, sem fechamento" in material
    assert "semana passada" not in material and "fechamento antigo" not in material
    assert dias == [4]                                  # os commits desde segunda
    sexta = (cfg.cofre / "Diário" / "2026-10-16.md").read_text(encoding="utf-8")
    assert "## Semana fechada" in sexta and "**Andou** o mapa." in sexta
    assert ctx.texto == "**Andou** o mapa."


def test_rodar_de_novo_nao_manda_o_proprio_fechamento_da_semana(ambiente, monkeypatch):
    cfg, ctx, _ = ambiente
    chamadas = _perguntas(monkeypatch, "texto da semana")
    _diario(cfg, "2026-10-16", "sexta")
    semana_fechada.rodar(ctx)
    semana_fechada.rodar(ctx)
    assert "texto da semana" not in chamadas[1]


def test_semana_sem_diario_nao_chama_a_ia(ambiente, monkeypatch):
    _, ctx, _ = ambiente
    chamadas = _perguntas(monkeypatch)
    assert "nenhum diário" in semana_fechada.rodar(ctx)
    assert chamadas == []


def test_manda_as_notas_editadas_desde_segunda(ambiente, monkeypatch):
    cfg, ctx, _ = ambiente
    chamadas = _perguntas(monkeypatch)
    _diario(cfg, "2026-10-16", "sexta")
    for nome, dia in (("Plano da semana", 13), ("Da semana passada", 9)):
        nota = cfg.cofre / "Projetos" / f"{nome}.md"
        nota.parent.mkdir(exist_ok=True)
        nota.write_text(f"conteúdo de {nome}", encoding="utf-8")
        quando = datetime(2026, 10, dia, 10).timestamp()
        os.utime(nota, (quando, quando))

    semana_fechada.rodar(ctx)

    assert "### Notas do cofre editadas na semana\n#### Projetos/Plano da semana.md" in chamadas[0]
    assert "Da semana passada" not in chamadas[0]
