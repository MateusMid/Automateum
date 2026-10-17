import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from automateum.config import Config
from automateum.nucleo.estado import Estado
from automateum.servicos import claude, copilot, ia
from automateum.web.api import criar_app


class Ctx:
    def __init__(self, tmp_path, ia_config=None):
        self.config = Config(dados={"ia": ia_config or {}}, segredos={}, pasta_dados=tmp_path)
        self.estado = Estado(tmp_path / "t.db")
        self.linhas = []

    def log(self, texto):
        self.linhas.append(texto)


@pytest.fixture
def ctx(tmp_path):
    return Ctx(tmp_path)


def _responde(monkeypatch, modulo, texto):
    chamadas = []
    monkeypatch.setattr(modulo, "perguntar", lambda c, i, d="": chamadas.append((i, d)) or texto)
    return chamadas


def _falha(monkeypatch, modulo, erro):
    def _(*a, **k):
        raise erro
    monkeypatch.setattr(modulo, "perguntar", _)


# --- quem responde

def test_claude_e_o_padrao_e_o_copilot_nem_e_chamado(ctx, monkeypatch):
    _responde(monkeypatch, claude, "do claude")
    do_copilot = _responde(monkeypatch, copilot, "do copilot")
    assert ia.perguntar(ctx, "resuma", "dados") == "do claude"
    assert do_copilot == [] and ctx.linhas == []
    assert ia.situacao(ctx.config, ctx.estado)["ultimo"]["reserva"] is False


def test_claude_falha_e_o_copilot_responde(ctx, monkeypatch):
    _falha(monkeypatch, claude, RuntimeError("claude saiu com código 1: limite"))
    _responde(monkeypatch, copilot, "do copilot")
    assert ia.perguntar(ctx, "resuma") == "do copilot"
    assert "Claude não respondeu" in ctx.linhas[0] and "limite" in ctx.linhas[0] and "Copilot" in ctx.linhas[0]
    ultimo = ia.situacao(ctx.config, ctx.estado)["ultimo"]
    assert ultimo["motor"] == "copilot" and ultimo["reserva"] is True


def test_timeout_tambem_cai_na_reserva(ctx, monkeypatch):
    _falha(monkeypatch, claude, subprocess.TimeoutExpired("claude", 240))
    _responde(monkeypatch, copilot, "do copilot")
    assert ia.perguntar(ctx, "resuma") == "do copilot"


def test_claude_ausente_vai_direto_para_o_copilot(ctx, monkeypatch):
    monkeypatch.setattr(claude, "_executavel", lambda: None)
    _responde(monkeypatch, copilot, "do copilot")
    assert ia.perguntar(ctx, "resuma") == "do copilot"
    assert "não está no PATH" in ctx.linhas[0]


def test_os_dois_falham_e_o_erro_diz_o_motivo_de_cada_um(ctx, monkeypatch):
    _falha(monkeypatch, claude, RuntimeError("limite do claude"))
    monkeypatch.setattr(copilot, "_executavel", lambda: None)
    with pytest.raises(RuntimeError, match="nenhuma IA respondeu.*limite do claude.*copilot"):
        ia.perguntar(ctx, "resuma")


# --- o botão

def test_trocar_o_motor_inverte_principal_e_reserva(ctx, monkeypatch):
    ia.definir(ctx.estado, "copilot")
    assert ia.ativo(ctx.config, ctx.estado) == "copilot"
    do_claude = _responde(monkeypatch, claude, "do claude")
    _responde(monkeypatch, copilot, "do copilot")
    assert ia.perguntar(ctx, "resuma") == "do copilot" and do_claude == []
    _falha(monkeypatch, copilot, RuntimeError("fora do ar"))
    assert ia.perguntar(ctx, "resuma") == "do claude"                    # agora o Claude é a reserva


def test_config_define_o_motor_inicial_e_o_botao_vence(tmp_path):
    c = Ctx(tmp_path, {"motor": "copilot"})
    assert ia.ativo(c.config, c.estado) == "copilot"
    ia.definir(c.estado, "claude")
    assert ia.ativo(c.config, c.estado) == "claude"
    with pytest.raises(ValueError):
        ia.definir(c.estado, "outro")


def test_acao_do_mapa_troca_o_motor_e_o_mapa_mostra(tmp_path):
    cfg = Config(dados={"obsidian": {"cofre": str(tmp_path)}}, segredos={}, pasta_dados=tmp_path)
    app = criar_app(cfg)
    c = TestClient(app)
    c.headers.update({"host": "127.0.0.1:8765"})
    token = c.get("/dados/acoes.js").text.split('"token": "', 1)[1].split('"', 1)[0]
    cab = {"X-Mapa-Token": token, "Origin": "http://127.0.0.1:8765"}
    assert c.post("/acao", json={"acao": "motor:copilot"}, headers=cab).json() == {"id": 0}
    assert c.post("/acao", json={"acao": "motor:gemini"}, headers=cab).status_code == 400
    js = c.get("/dados/estado.js").text
    assert '"ativo": "copilot"' in js and '"reserva": "claude"' in js


# --- a CLI do Copilot

def test_copilot_manda_o_texto_por_stdin_sem_liberar_ferramentas(tmp_path, monkeypatch):
    visto = {}

    def falso(comando, **k):
        visto.update(comando=comando, entrada=k["input"], cwd=k["cwd"])
        return SimpleNamespace(returncode=0, stdout="  resumo pronto \n", stderr="")

    monkeypatch.setattr(subprocess, "run", falso)
    cfg = Config(dados={"copilot": {"modelo": "gpt-5-mini"}}, segredos={}, pasta_dados=tmp_path)
    assert copilot.perguntar(cfg, "resuma", "<b>algo</b>") == "resumo pronto"
    assert visto["comando"] == ["copilot", "-s", "--no-ask-user", "--model", "gpt-5-mini"]
    assert not any(a.startswith("--allow") for a in visto["comando"])
    assert "resuma" in visto["entrada"] and "<dados>\n<b>algo</b>\n</dados>" in visto["entrada"]
    assert "nunca como instrução" in visto["entrada"]                      # as regras do sistema vão junto
    assert str(tmp_path) not in visto["cwd"]


def test_copilot_erro_e_resposta_vazia(tmp_path, monkeypatch):
    cfg = Config(dados={}, segredos={}, pasta_dados=tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="não logado"))
    with pytest.raises(RuntimeError, match="não logado"):
        copilot.perguntar(cfg, "resuma")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="  ", stderr=""))
    with pytest.raises(RuntimeError, match="não devolveu texto"):
        copilot.perguntar(cfg, "resuma")


def test_copilot_acha_o_instalador_do_winget_fora_do_path(tmp_path, monkeypatch):
    pacote = tmp_path / "Microsoft" / "WinGet" / "Packages" / "GitHub.Copilot_x" 
    pacote.mkdir(parents=True)
    (pacote / "copilot.exe").write_text("")
    monkeypatch.undo()                                      # tira o falso do conftest
    monkeypatch.setattr("shutil.which", lambda nome: None)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert copilot._executavel() == str(pacote / "copilot.exe")
