import sqlite3
import time
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from automateum.config import Config
from automateum.nucleo.agendador import Contexto
from automateum.nucleo.estado import Estado
from automateum.nucleo.registro import OK, ROTINAS, Checagem
from automateum.rotinas import dia_fechado, saude
from automateum.servicos import claude, git_local, maquina
from automateum.web.api import criar_app


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
    estado._exec("INSERT INTO medidas (quando, cpu, memoria, disco_livre_gb) VALUES (?,?,?,?)", (antigas, 99, 99, 1))

    assert len(estado.medidas("2000-01-01T00:00:00")) == 2
    hoje = estado.medidas(f"{date.today().isoformat()}T00:00:00")
    assert [(m["cpu"], m["memoria"], m["disco_livre_gb"]) for m in hoje] == [(12, 55, 90)]

    estado.limpar_antigos()
    assert len(estado.medidas("2000-01-01T00:00:00")) == 1          # a de 9 dias saiu


def test_saude_guarda_uma_medida_por_rodada(tmp_path, estado, monkeypatch):
    cfg = Config(dados={}, segredos={}, pasta_dados=tmp_path)
    leitura = Checagem(OK, "ok", meta={"cpu": 20, "memoria": 61, "disco_livre_gb": 85})
    monkeypatch.setattr(maquina, "ler", lambda *a: leitura)
    monkeypatch.setattr(saude, "SERVICOS", {})
    ctx = Contexto(cfg, estado, ROTINAS["saude"], estado.iniciar_execucao("saude"))

    saude.rodar(ctx)
    time.sleep(1.1)  # a chave da medida é o segundo
    saude.rodar(ctx)

    medidas = estado.medidas("2000-01-01T00:00:00")
    assert len(medidas) == 2 and all(m["cpu"] == 20 and m["disco_livre_gb"] == 85 for m in medidas)


def test_saude_sem_meta_nao_quebra(tmp_path, estado, monkeypatch):
    cfg = Config(dados={}, segredos={}, pasta_dados=tmp_path)
    monkeypatch.setattr(maquina, "ler", lambda *a: Checagem(OK, "sem meta"))
    monkeypatch.setattr(saude, "SERVICOS", {})
    ctx = Contexto(cfg, estado, ROTINAS["saude"], estado.iniciar_execucao("saude"))
    saude.rodar(ctx)
    assert estado.medidas("2000-01-01T00:00:00") == []


def test_cartao_da_maquina_no_mapa_mostra_cpu_memoria_e_disco(tmp_path, estado):
    from automateum.nucleo import mapa_leo
    from automateum.nucleo.agendador import Agendador
    from automateum.nucleo.eventos import Barramento

    cfg = Config(dados={}, segredos={}, pasta_dados=tmp_path)
    agendador = Agendador(cfg, estado, Barramento())

    antes = mapa_leo.montar_mapa_leo(cfg, estado, agendador)
    mesa = next(n for n in antes["nos"] if n["id"] == "mesa")
    assert "CPU" not in mesa["frase"]                                  # sem medição, não inventa

    estado.salvar_checagem("maquina", Checagem(OK, "ok", meta={
        "cpu": 7, "memoria": 53, "disco_livre_gb": 85, "ligada_desde": "17/10 08:40"}))
    mesa = next(n for n in mapa_leo.montar_mapa_leo(cfg, estado, agendador)["nos"] if n["id"] == "mesa")
    assert mesa["frase"] == "CPU 7% · memória 53% · 85 GB livres"
    assert mesa["linhas"] == ["ligada desde 17/10 08:40"]


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


# --- vários discos

class _Particao:
    def __init__(self, ponto, opts="rw,fixed"):
        self.mountpoint, self.opts = ponto, opts


class _Uso:
    def __init__(self, livre_gb, total_gb):
        self.free, self.total = livre_gb * 2**30, total_gb * 2**30
        self.percent = 100 * (total_gb - livre_gb) / total_gb


def _discos_falsos(monkeypatch, particoes, usos):
    monkeypatch.setattr(maquina.platform, "system", lambda: "Windows")
    monkeypatch.setattr(maquina.psutil, "disk_partitions", lambda all=False: particoes)

    def uso(ponto):
        if ponto not in usos:
            raise OSError("disco sumiu")
        return usos[ponto]

    monkeypatch.setattr(maquina.psutil, "disk_usage", uso)


@pytest.fixture
def dois_discos(monkeypatch):
    _discos_falsos(monkeypatch, [_Particao("C:\\"), _Particao("D:\\")],
                   {"C:\\": _Uso(85, 237), "D:\\": _Uso(94, 237)})


def test_volumes_lista_so_discos_fixos(monkeypatch):
    _discos_falsos(
        monkeypatch,
        [_Particao("C:\\"), _Particao("D:\\"), _Particao("E:\\", "ro,cdrom"), _Particao("F:\\", "rw,removable")],
        {"C:\\": _Uso(85, 237), "D:\\": _Uso(94, 237), "E:\\": _Uso(0, 1), "F:\\": _Uso(5, 16)})
    assert maquina.volumes() == [
        {"nome": "C:", "livre_gb": 85, "total_gb": 237, "usado_pct": 64},
        {"nome": "D:", "livre_gb": 94, "total_gb": 237, "usado_pct": 60},
    ]


def test_volumes_filtra_pela_config_e_aceita_varias_grafias(dois_discos):
    assert [d["nome"] for d in maquina.volumes(["d", "C:\\"])] == ["C:", "D:"]
    assert [d["nome"] for d in maquina.volumes(["D:"])] == ["D:"]


def test_disco_que_sumiu_nao_derruba_a_leitura(monkeypatch):
    _discos_falsos(monkeypatch, [_Particao("C:\\"), _Particao("G:\\")], {"C:\\": _Uso(85, 237)})
    assert [d["nome"] for d in maquina.volumes()] == ["C:"]


def test_ler_traz_os_dois_discos(dois_discos):
    leitura = maquina.ler()
    assert leitura.estado == OK
    assert [d["nome"] for d in leitura.meta["discos"]] == ["C:", "D:"]
    assert leitura.meta["disco_livre_gb"] == 85                       # o primeiro, para quem só conhece um
    assert "C: 85 GB · D: 94 GB livres" in leitura.detalhe


def test_ler_com_config_errada_cai_para_todos_os_discos(dois_discos):
    assert [d["nome"] for d in maquina.ler(["Z:"]).meta["discos"]] == ["C:", "D:"]


def test_ler_avisa_do_disco_que_encheu(monkeypatch):
    _discos_falsos(monkeypatch, [_Particao("C:\\"), _Particao("D:\\")],
                   {"C:\\": _Uso(85, 237), "D:\\": _Uso(10, 237)})
    leitura = maquina.ler()
    assert leitura.estado != OK and "disco D: com só 10 GB livres" in leitura.detalhe


def test_resumo_do_dia_por_disco():
    def m(hora, c, d):
        return {"quando": f"2026-10-17T{hora}:00", "cpu": 10, "memoria": 50, "disco_livre_gb": c,
                "discos": {"C:": c, "D:": d}}

    linha = maquina.resumo_do_dia([m("09:00", 85, 94), m("12:00", 85, 90), m("18:00", 85, 93)])
    assert "disco livre C: 85 GB · D: 93 GB (mínimo do dia 90 GB)" in linha


def test_estado_migra_um_banco_de_um_disco_so(tmp_path):
    caminho = tmp_path / "antigo.db"
    antigo = sqlite3.connect(str(caminho))
    antigo.execute("CREATE TABLE medidas (quando TEXT PRIMARY KEY, cpu INTEGER, memoria INTEGER, disco_livre_gb INTEGER)")
    antigo.execute("INSERT INTO medidas VALUES ('2026-10-17T09:00:00', 10, 50, 85)")
    antigo.commit()
    antigo.close()

    estado = Estado(caminho)                                          # não pode quebrar nem perder a linha antiga
    estado.salvar_medida(12, 55, 85, {"C:": 85, "D:": 94})
    medidas = estado.medidas("2000-01-01T00:00:00")
    assert medidas[0]["discos"] == {} and medidas[0]["disco_livre_gb"] == 85
    assert medidas[1]["discos"] == {"C:": 85, "D:": 94}


def test_cartao_da_maquina_mostra_os_dois_discos(tmp_path, estado):
    from automateum.nucleo import mapa_leo
    from automateum.nucleo.agendador import Agendador
    from automateum.nucleo.eventos import Barramento

    cfg = Config(dados={}, segredos={}, pasta_dados=tmp_path)
    discos = [{"nome": "C:", "livre_gb": 85, "total_gb": 237, "usado_pct": 64},
              {"nome": "D:", "livre_gb": 94, "total_gb": 237, "usado_pct": 60}]
    estado.salvar_checagem("maquina", Checagem(OK, "ok", meta={
        "cpu": 7, "memoria": 53, "disco_livre_gb": 85, "discos": discos, "ligada_desde": "17/10 08:40"}))
    mesa = next(n for n in mapa_leo.montar_mapa_leo(cfg, estado, Agendador(cfg, estado, Barramento()))["nos"]
                if n["id"] == "mesa")
    assert mesa["frase"].replace(" ", " ") == "CPU 7% · memória 53% · C: 85 GB · D: 94 GB livres"
    assert "94 GB" in mesa["frase"]                              # cada item não quebra no meio
    assert mesa["linhas"] == ["C: 85 GB livres de 237 GB (64% usado)", "D: 94 GB livres de 237 GB (60% usado)",
                              "ligada desde 17/10 08:40"]


def test_api_da_maquina_traz_um_campo_por_disco(tmp_path):
    cfg = Config(dados={}, segredos={}, pasta_dados=tmp_path)
    app = criar_app(cfg)
    discos = [{"nome": "C:", "livre_gb": 85, "total_gb": 237, "usado_pct": 64},
              {"nome": "D:", "livre_gb": 94, "total_gb": 237, "usado_pct": 60}]
    app.state.estado.salvar_checagem("maquina", Checagem(OK, "ok", meta={"cpu": 7, "memoria": 53, "discos": discos}))
    cliente = TestClient(app)
    cliente.headers.update({"host": "127.0.0.1:8765"})

    campos = dict(map(tuple, cliente.get("/api/no/maquina/maquina").json()["campos"]))
    assert campos["disco C:"] == "85 GB livres de 237 GB" and campos["disco D:"] == "94 GB livres de 237 GB"
