import json
import subprocess
from types import SimpleNamespace

import pytest

from automateum import rotinas, servicos  # noqa: F401  (registram rotinas e serviços)
from automateum.config import Config
from automateum.nucleo import projetos
from automateum.nucleo.estado import Estado
from automateum.nucleo.registro import ROTINAS, Atencao
from automateum.servicos import github, orca


def _cfg(tmp_path, **secoes):
    base = {"projetos": {"demo": {"nome": "Demo", "github": "dono/demo", "ativo": True, "max_pendentes": 3}}}
    base.update(secoes)
    return Config(dados=base, segredos={}, pasta_dados=tmp_path)


class Ctx:
    def __init__(self, tmp_path, **secoes):
        self.config, self.estado = _cfg(tmp_path, **secoes), Estado(tmp_path / "t.db")
        self.linhas, self.texto = [], ""

    def log(self, t):
        self.linhas.append(t)


@pytest.fixture(autouse=True)
def orca_instalado(monkeypatch):
    monkeypatch.setattr(orca, "_executavel", lambda config=None: "orca")


class OrcaFalso:
    """Registra cada chamada à CLI e responde no formato do Orca."""

    def __init__(self, monkeypatch, esperar=True):
        self.chamadas = []
        self.esperar = esperar
        monkeypatch.setattr(subprocess, "run", self._run)

    def _run(self, comando, **k):
        a = comando[1:]
        self.chamadas.append(a)
        if a[:2] == ["repo", "list"]:
            r = {"repos": [{"id": "r1", "gitRemoteIdentity": {"canonicalKey": "github.com/Dono/Demo"}}]}
        elif a[:2] == ["worktree", "create"]:
            nome = a[a.index("--name") + 1]
            r = {"worktree": {"id": f"r1::C:/wt/{nome}", "path": f"C:/wt/{nome}"}}
        elif a[:2] == ["terminal", "create"]:
            r = {"terminal": {"handle": "term_1"}}
        elif a[:2] == ["terminal", "wait"]:
            r = {"wait": {"satisfied": self.esperar}}
        elif a[:2] == ["terminal", "send"]:
            r = {"send": {"accepted": True, "bytesWritten": 1}}
        else:
            raise AssertionError(f"chamada inesperada: {a}")
        return SimpleNamespace(returncode=0, stdout=json.dumps({"ok": True, "result": r}), stderr="")

    def com(self, *inicio):
        return [c for c in self.chamadas if c[:len(inicio)] == list(inicio)]


def _issues(monkeypatch, *itens):
    monkeypatch.setattr(github, "issues_abertas", lambda cfg, repo, rotulo="": [
        {"numero": n, "titulo": t, "corpo": c, "url": f"https://github.com/dono/demo/issues/{n}"} for n, t, c in itens])


# --- a regra: nunca enviar

def test_nunca_envia_o_enter(tmp_path, monkeypatch):
    falso = OrcaFalso(monkeypatch)
    orca.digitar(_cfg(tmp_path), "term_1", "um prompt\ncom duas linhas")
    envios = falso.com("terminal", "send")
    assert len(envios) == 1 and "--enter" not in envios[0]


def test_rotina_nunca_usa_enter_nem_agente_com_prompt(tmp_path, monkeypatch):
    falso = OrcaFalso(monkeypatch)
    _issues(monkeypatch, (7, "Corrigir o login", "Ao clicar nada acontece"))
    ROTINAS["preparar_prompts"].func(Ctx(tmp_path))
    assert falso.chamadas
    for c in falso.chamadas:   # --agent com --prompt enviaria sozinho; --enter também
        assert "--enter" not in c and "--prompt" not in c and "--agent" not in c


def test_limpar_tira_controles_e_limita_o_tamanho():
    limpo = orca.limpar("oi\x1b[2Jxx\r\ny\x07z\x03")
    assert "\x1b" not in limpo and "\r" not in limpo and "\x07" not in limpo and "\x03" not in limpo
    assert limpo == "oi[2Jxx\nyz"
    assert orca.limpar("a\tb\nc") == "a\tb\nc"
    longo = orca.limpar("x" * 9000)
    assert longo.endswith("[texto cortado]") and len(longo) < 6100


# --- a rotina

def test_prepara_worktree_abre_claude_e_digita_o_prompt(tmp_path, monkeypatch):
    falso = OrcaFalso(monkeypatch)
    _issues(monkeypatch, (7, "Corrigir o login", "Ao clicar nada acontece"))
    ctx = Ctx(tmp_path)
    resumo = ROTINAS["preparar_prompts"].func(ctx)

    assert resumo == "1 prompt(s) pronto(s)"
    criar = falso.com("worktree", "create")[0]
    assert criar[criar.index("--name") + 1] == "issue-7-corrigir-o-login" and criar[criar.index("--issue") + 1] == "7"
    assert criar[criar.index("--repo") + 1] == "id:r1" and criar[criar.index("--setup") + 1] == "skip"
    abrir = falso.com("terminal", "create")[0]
    assert abrir[abrir.index("--command") + 1] == "claude"
    envio = falso.com("terminal", "send")[0]
    prompt = envio[envio.index("--text") + 1]
    assert prompt.startswith("Task #7: Corrigir o login") and "Ao clicar nada acontece" in prompt
    assert "issues/7" in prompt and "me proponha um plano" in prompt
    assert "Prompts prontos no Orca" in ctx.texto and "Ao clicar" not in ctx.texto   # o corpo da issue não vai para o cofre
    assert projetos.preparados(ctx.estado, "demo")["7"]["digitado"] is True


def test_projeto_desativado_nao_faz_nada(tmp_path, monkeypatch):
    falso = OrcaFalso(monkeypatch)
    _issues(monkeypatch, (7, "x", ""))
    ctx = Ctx(tmp_path)
    projetos.definir(ctx.config, ctx.estado, "demo", False)
    assert ROTINAS["preparar_prompts"].func(ctx) == "nenhum projeto ativo"
    assert falso.chamadas == []


def test_nao_repete_a_mesma_issue_e_respeita_o_limite_de_vagas(tmp_path, monkeypatch):
    falso = OrcaFalso(monkeypatch)
    _issues(monkeypatch, *[(n, f"Task {n}", "") for n in range(1, 8)])
    ctx = Ctx(tmp_path)
    ROTINAS["preparar_prompts"].func(ctx)
    assert len(falso.com("worktree", "create")) == 2        # no máximo 2 por rodada
    ROTINAS["preparar_prompts"].func(ctx)
    assert len(falso.com("worktree", "create")) == 3        # sobra 1 vaga das 3
    ROTINAS["preparar_prompts"].func(ctx)
    assert len(falso.com("worktree", "create")) == 3        # cheio: nada novo
    nomes = [c[c.index("--name") + 1] for c in falso.com("worktree", "create")]
    assert len(set(nomes)) == 3


def test_issue_fechada_libera_a_vaga(tmp_path, monkeypatch):
    falso = OrcaFalso(monkeypatch)
    _issues(monkeypatch, *[(n, f"Task {n}", "") for n in range(1, 8)])
    ctx = Ctx(tmp_path)
    for _ in range(2):
        ROTINAS["preparar_prompts"].func(ctx)
    _issues(monkeypatch, *[(n, f"Task {n}", "") for n in range(3, 8)])   # #1 e #2 foram fechadas
    ROTINAS["preparar_prompts"].func(ctx)
    assert len(falso.com("worktree", "create")) == 5        # 3 + 2 novas (o limite por rodada)


def test_claude_demora_nao_digita_e_avisa(tmp_path, monkeypatch):
    falso = OrcaFalso(monkeypatch, esperar=False)
    _issues(monkeypatch, (7, "Corrigir o login", ""))
    ctx = Ctx(tmp_path)
    with pytest.raises(Atencao, match="demorou para abrir"):
        ROTINAS["preparar_prompts"].func(ctx)
    assert falso.com("terminal", "send") == []
    assert projetos.preparados(ctx.estado, "demo")["7"]["digitado"] is False
    ROTINAS["preparar_prompts"].func(ctx)                   # a worktree existe: não cria outra
    assert len(falso.com("worktree", "create")) == 1


def test_repositorio_fora_do_orca_vira_aviso(tmp_path, monkeypatch):
    OrcaFalso(monkeypatch)
    _issues(monkeypatch, (7, "x", ""))
    ctx = Ctx(tmp_path, projetos={"demo": {"nome": "Demo", "github": "outro/repo", "ativo": True}})
    with pytest.raises(Atencao, match="não está no Orca"):
        ROTINAS["preparar_prompts"].func(ctx)


# --- projetos e o botão

def test_botao_vence_o_config_e_resume(tmp_path):
    ctx = Ctx(tmp_path, projetos={"demo": {"nome": "Demo", "github": "dono/demo", "ativo": False}})
    assert projetos.ativo(ctx.config, ctx.estado, "demo") is False
    assert projetos.resumo(projetos.situacao(ctx.config, ctx.estado)) == "nenhum projeto ativo: ative um na gaveta"
    projetos.definir(ctx.config, ctx.estado, "demo", True)
    assert projetos.resumo(projetos.situacao(ctx.config, ctx.estado)) == "ativo: Demo"
    with pytest.raises(ValueError):
        projetos.definir(ctx.config, ctx.estado, "nao_existe", True)


def test_acao_do_mapa_liga_o_projeto_e_o_cartao_mostra(tmp_path):
    from fastapi.testclient import TestClient
    from automateum.web.api import criar_app
    cfg = _cfg(tmp_path, projetos={"demo": {"nome": "Demo", "github": "dono/demo", "ativo": False}},
               obsidian={"cofre": str(tmp_path)})
    c = TestClient(criar_app(cfg))
    c.headers.update({"host": "127.0.0.1:8765"})
    token = c.get("/dados/acoes.js").text.split('"token": "', 1)[1].split('"', 1)[0]
    cab = {"X-Mapa-Token": token, "Origin": "http://127.0.0.1:8765"}
    assert c.post("/acao", json={"acao": "projeto-ligar:demo"}, headers=cab).json() == {"id": 0}
    assert c.post("/acao", json={"acao": "projeto-ligar:nao_existe"}, headers=cab).status_code == 400
    js = c.get("/dados/estado.js").text
    assert '"projetos": [{"id": "demo", "nome": "Demo", "github": "dono/demo", "ativo": true' in js


# --- a CLI

def test_repo_id_casa_pelo_remote_sem_diferenciar_maiusculas(tmp_path, monkeypatch):
    OrcaFalso(monkeypatch)
    assert orca.repo_id(_cfg(tmp_path), "dono/demo") == "r1"
    assert orca.repo_id(_cfg(tmp_path), "dono/outro") is None


def test_erro_da_cli_vira_runtime_error(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=1, stdout=json.dumps({"ok": False, "error": {"message": "repo desconhecido"}}), stderr=""))
    with pytest.raises(RuntimeError, match="repo desconhecido"):
        orca.repo_id(_cfg(tmp_path), "dono/demo")
