import time
from datetime import date, datetime, timedelta

import pytest

from automateum.config import Config
from automateum.nucleo.agendador import Contexto
from automateum.nucleo.estado import Estado
from automateum.nucleo.registro import OK, ROTINAS, Checagem
from automateum.rotinas import dia_fechado, saude
from automateum.servicos import claude, git_local, maquina


def _medida(hora, cpu, memoria, livre):
    return {"quando": f"2026-10-17T{hora}:00", "cpu": cpu, "memoria": memoria, "disco_livre_gb": livre}


def test_resumo_do_dia_traz_media_pico_e_disco():
    medidas = [_medida("09:00", 10, 50, 90), _medida("14:20", 70, 80, 88), _medida("18:00", 10, 50, 89)]
    linha = maquina.resumo_do_dia(medidas, "17/10 08:40")

    assert linha.startswith("**Máquina:**")
    assert "CPU média 30% (pico 70% às 14:20)" in linha
    assert "memória média 60% (pico 80% às 14:20)" in linha
    assert "disco livre 89 GB (mínimo do dia 88 GB)" in linha
    assert "ligada desde 17/10 08:40" in linha and "(3 medições)" in linha


def test_resumo_do_dia_sem_variacao_de_disco_e_sem_ligada_desde():
    linha = maquina.resumo_do_dia([_medida("09:00", 5, 40, 90), _medida("09:02", 7, 42, 90)])
    assert "disco livre 90 GB" in linha and "mínimo" not in linha and "ligada desde" not in linha


def test_resumo_do_dia_sem_medicoes_e_vazio():
    assert maquina.resumo_do_dia([]) == ""


@pytest.fixture
def estado(tmp_path):
    return Estado(tmp_path / "estado.db")


def test_estado_guarda_filtra_e_poda_as_medidas(estado):
    estado.salvar_medida(12, 55, 90)
    antigas = (datetime.now() - timedelta(days=9)).isoformat(timespec="seconds")
    estado._exec("INSERT INTO medidas VALUES (?,?,?,?)", (antigas, 99, 99, 1))

    assert len(estado.medidas("2000-01-01T00:00:00")) == 2
    hoje = estado.medidas(f"{date.today().isoformat()}T00:00:00")
    assert [(m["cpu"], m["memoria"], m["disco_livre_gb"]) for m in hoje] == [(12, 55, 90)]

    estado.limpar_antigos()
    assert len(estado.medidas("2000-01-01T00:00:00")) == 1          # a de 9 dias saiu


def test_saude_guarda_uma_medida_por_rodada(tmp_path, estado, monkeypatch):
    cfg = Config(dados={}, segredos={}, pasta_dados=tmp_path)
    leitura = Checagem(OK, "ok", meta={"cpu": 20, "memoria": 61, "disco_livre_gb": 85})
    monkeypatch.setattr(maquina, "ler", lambda: leitura)
    monkeypatch.setattr(saude, "SERVICOS", {})
    ctx = Contexto(cfg, estado, ROTINAS["saude"], estado.iniciar_execucao("saude"))

    saude.rodar(ctx)
    time.sleep(1.1)  # a chave da medida é o segundo
    saude.rodar(ctx)

    medidas = estado.medidas("2000-01-01T00:00:00")
    assert len(medidas) == 2 and all(m["cpu"] == 20 and m["disco_livre_gb"] == 85 for m in medidas)


def test_saude_sem_meta_nao_quebra(tmp_path, estado, monkeypatch):
    cfg = Config(dados={}, segredos={}, pasta_dados=tmp_path)
    monkeypatch.setattr(maquina, "ler", lambda: Checagem(OK, "sem meta"))
    monkeypatch.setattr(saude, "SERVICOS", {})
    ctx = Contexto(cfg, estado, ROTINAS["saude"], estado.iniciar_execucao("saude"))
    saude.rodar(ctx)
    assert estado.medidas("2000-01-01T00:00:00") == []


def test_fechamento_do_dia_traz_a_linha_da_maquina(tmp_path, estado, monkeypatch):
    cofre = tmp_path / "cofre"
    (cofre / "Diário").mkdir(parents=True)
    cfg = Config(dados={"obsidian": {"cofre": str(cofre), "pasta_diario": "Diário"}}, segredos={},
                 pasta_dados=tmp_path)
    monkeypatch.setattr(claude, "perguntar", lambda *a, **k: "**Andou** o mapa.")
    monkeypatch.setattr(git_local, "auditar_dia", lambda *a, **k: [])
    estado.salvar_medida(30, 60, 80)
    ctx = Contexto(cfg, estado, ROTINAS["dia_fechado"], estado.iniciar_execucao("dia_fechado"))

    dia_fechado.rodar(ctx)

    diario = (cofre / "Diário" / f"{date.today().isoformat()}.md").read_text(encoding="utf-8")
    assert "**Andou** o mapa." in diario and "**Máquina:** CPU média 30%" in diario
    assert ctx.texto.endswith("(1 medição).")                        # a nota da rotina repete a linha


def test_fechamento_sem_medicoes_nao_inventa_a_linha(tmp_path, estado, monkeypatch):
    cofre = tmp_path / "cofre"
    (cofre / "Diário").mkdir(parents=True)
    cfg = Config(dados={"obsidian": {"cofre": str(cofre), "pasta_diario": "Diário"}}, segredos={},
                 pasta_dados=tmp_path)
    monkeypatch.setattr(claude, "perguntar", lambda *a, **k: "Dia calmo.")
    monkeypatch.setattr(git_local, "auditar_dia", lambda *a, **k: [])
    ctx = Contexto(cfg, estado, ROTINAS["dia_fechado"], estado.iniciar_execucao("dia_fechado"))

    dia_fechado.rodar(ctx)
    assert ctx.texto == "Dia calmo."
