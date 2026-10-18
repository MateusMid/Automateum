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
        self.worktrees = []
        monkeypatch.setattr(subprocess, "run", self._run)

    def _run(self, comando, **k):
        a = comando[1:]
        self.chamadas.append(a)
        if a[:2] == ["repo", "list"]:
            r = {"repos": [{"id": "r1", "gitRemoteIdentity": {"canonicalKey": "github.com/Dono/Demo"}}]}
        elif a[:2] == ["worktree", "create"]:
            nome = a[a.index("--name") + 1]
            r = {"worktree": {"id": f"r1::C:/wt/{nome}", "path": f"C:/wt/{nome}"}}
            self.worktrees.append(r["worktree"]["path"])
        elif a[:2] == ["worktree", "list"]:
            r = {"worktrees": [{"path": p} for p in self.worktrees]}
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


def _issues(monkeypatch, *itens, de=("eu",)):
    """Issues abertas; por padrão todas atribuídas ao dono do token (`eu`)."""
    monkeypatch.setattr(github, "meu_login", lambda cfg: "eu")
    monkeypatch.setattr(github, "issues_abertas", lambda cfg, repo, rotulo="": [
        {"numero": n, "titulo": t, "corpo": c, "url": f"https://github.com/dono/demo/issues/{n}", "atribuidos": list(de)}
        for n, t, c in itens])


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


def test_issue_de_outra_pessoa_espera_o_comecar(tmp_path, monkeypatch):
    falso = OrcaFalso(monkeypatch)
    _issues(monkeypatch, (7, "Alheia", ""), (8, "Sem dono", ""), de=("outra",))
    ctx = Ctx(tmp_path)
    assert ROTINAS["preparar_prompts"].func(ctx) == "nada novo para preparar"
    assert falso.com("worktree", "create") == []
    sit = projetos.situacao(ctx.config, ctx.estado)[0]
    assert [i["numero"] for i in sit["disponiveis"]] == [7, 8] and not any(i["minha"] for i in sit["disponiveis"])
    projetos.aceitar(ctx.config, ctx.estado, "demo", 8)
    ROTINAS["preparar_prompts"].func(ctx)
    criar = falso.com("worktree", "create")
    assert len(criar) == 1 and criar[0][criar[0].index("--issue") + 1] == "8"
    assert [i["numero"] for i in projetos.situacao(ctx.config, ctx.estado)[0]["disponiveis"]] == [7]


def test_aceita_nao_gasta_vaga__e_as_atribuidas_respeitam_o_limite(tmp_path, monkeypatch):
    falso = OrcaFalso(monkeypatch)
    _issues(monkeypatch, *[(n, f"Task {n}", "") for n in range(1, 6)], de=("outra",))
    ctx = Ctx(tmp_path)
    for n in (1, 2, 3, 4):
        projetos.aceitar(ctx.config, ctx.estado, "demo", n)
    ROTINAS["preparar_prompts"].func(ctx)
    assert len(falso.com("worktree", "create")) == 4        # as aceitas passam do limite de 3 e de 2 por rodada


def test_acao_comecar_registra_e_dispara_a_rotina(tmp_path):
    from fastapi.testclient import TestClient
    from automateum.web.api import criar_app
    cfg = _cfg(tmp_path, projetos={"demo": {"nome": "Demo", "github": "dono/demo", "ativo": True}},
               obsidian={"cofre": str(tmp_path)})
    c = TestClient(criar_app(cfg))
    c.headers.update({"host": "127.0.0.1:8765"})
    token = c.get("/dados/acoes.js").text.split('"token": "', 1)[1].split('"', 1)[0]
    cab = {"X-Mapa-Token": token, "Origin": "http://127.0.0.1:8765"}
    assert c.post("/acao", json={"acao": "projeto-comecar:demo:abc"}, headers=cab).status_code == 400
    assert c.post("/acao", json={"acao": "projeto-comecar:x:7"}, headers=cab).status_code == 400
    assert c.post("/acao", json={"acao": "projeto-comecar:demo:7"}, headers=cab).status_code == 200


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


# --- o cartão de cada projeto e o "Ver prompt"

def test_prompt_fica_guardado_e_a_gaveta_le_pela_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from automateum.web.api import criar_app
    OrcaFalso(monkeypatch)
    _issues(monkeypatch, (7, "Corrigir o login", "Ao clicar nada acontece"))
    cfg = _cfg(tmp_path, obsidian={"cofre": str(tmp_path)})
    ctx = SimpleNamespace(config=cfg, estado=Estado(tmp_path / "t.db"), log=lambda t: None, texto="")
    ROTINAS["preparar_prompts"].func(ctx)
    c = TestClient(criar_app(cfg))
    c.headers.update({"host": "127.0.0.1:8765"})
    texto = c.get("/api/projeto/demo/prompt/7").json()["texto"]
    assert texto.startswith("Task #7: Corrigir o login") and "Ao clicar nada acontece" in texto
    assert c.get("/api/projeto/demo/prompt/8").status_code == 404
    assert c.get("/api/projeto/../prompt/7").status_code in (404, 422)


def test_cada_projeto_vira_um_cartao_no_mapa_sem_o_texto(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from automateum.web.api import criar_app
    cfg = _cfg(tmp_path, obsidian={"cofre": str(tmp_path)})
    c = TestClient(criar_app(cfg))
    c.headers.update({"host": "127.0.0.1:8765"})
    js = c.get("/dados/estado.js").text
    assert '"id": "proj-demo"' in js and '"id": "frente-projetos~proj-demo"' in js
    assert "Ao clicar" not in js


def test_digitar_de_novo_abre_outro_terminal_na_mesma_worktree(tmp_path, monkeypatch):
    falso = OrcaFalso(monkeypatch)
    _issues(monkeypatch, (7, "Corrigir o login", "Ao clicar nada acontece"))
    ctx = Ctx(tmp_path)
    ROTINAS["preparar_prompts"].func(ctx)                    # você fechou o terminal depois disso
    projetos.pedir_de_novo(ctx.config, ctx.estado, "demo", 7)
    assert ROTINAS["preparar_prompts"].func(ctx) == "1 prompt(s) pronto(s)"
    assert len(falso.com("worktree", "create")) == 1         # não cria outra worktree
    terminais = falso.com("terminal", "create")
    assert len(terminais) == 2 and terminais[1][terminais[1].index("--worktree") + 1] == "path:C:/wt/issue-7-corrigir-o-login"
    envios = falso.com("terminal", "send")
    assert len(envios) == 2 and all("--enter" not in e for e in envios)
    assert not projetos.preparados(ctx.estado, "demo")["7"].get("refazer")
    ROTINAS["preparar_prompts"].func(ctx)                    # sem novo pedido, nada se repete
    assert len(falso.com("terminal", "create")) == 2
    with pytest.raises(ValueError):
        projetos.pedir_de_novo(ctx.config, ctx.estado, "demo", 99)


def test_digitar_de_novo_recria_a_worktree_que_foi_removida(tmp_path, monkeypatch):
    falso = OrcaFalso(monkeypatch)
    _issues(monkeypatch, (7, "Corrigir o login", ""))
    ctx = Ctx(tmp_path)
    ROTINAS["preparar_prompts"].func(ctx)
    falso.worktrees.clear()                                  # você removeu a worktree no Orca
    projetos.pedir_de_novo(ctx.config, ctx.estado, "demo", 7)
    assert ROTINAS["preparar_prompts"].func(ctx) == "1 prompt(s) pronto(s)"
    assert len(falso.com("worktree", "create")) == 2
    ultimo = falso.com("terminal", "create")[-1]
    assert ultimo[ultimo.index("--worktree") + 1] == "id:r1::C:/wt/issue-7-corrigir-o-login"
    assert all("--enter" not in e for e in falso.com("terminal", "send"))
