import pytest

from automateum.config import Config
from automateum.nucleo.agendador import Contexto
from automateum.nucleo.estado import Estado
from automateum.nucleo.registro import ATENCAO, ROTINAS
from automateum.rotinas import tasks_github
from automateum.servicos import github


def test_pendencias_consulta_por_tipo_sem_misturar(monkeypatch):
    consultas = []

    def falso(config, caminho, **params):
        consultas.append(params["q"])
        return {"items": []}

    monkeypatch.setattr(github, "_get", falso)
    github.pendencias(Config(dados={"github": {"repositorios": ["MateusMid/Automateum"]}}))

    assert len(consultas) == 5
    assert sum("author:@me" in q for q in consultas) == 1 and "is:pull-request" in next(q for q in consultas if "author" in q)
    for q in consultas:
        assert ("is:issue" in q) != ("is:pull-request" in q)  # exatamente um tipo por consulta
        assert "repo:MateusMid/Automateum" in q


def test_pr_seu_que_pede_sua_revisao_guarda_os_dois_papeis(monkeypatch):
    def falso(config, caminho, **params):
        q = params["q"]
        if "is:issue" in q:
            return {"items": [_item(3, "issue", "Minha issue")] if "assignee" in q else []}
        return {"items": [_item(7, "PR", "Revisar parser")]}  # o mesmo PR vem como seu e como revisão

    monkeypatch.setattr(github, "_get", falso)
    monkeypatch.setattr(github, "situacao_do_pr", lambda config, repo, numero: "aprovado")
    itens = github.pendencias(Config(dados={}))

    por_titulo = {i["titulo"]: i for i in itens}
    assert len(itens) == 2
    assert por_titulo["Minha issue"]["corpo"] == "issue · atribuído"
    assert por_titulo["Revisar parser"]["corpo"] == "PR · atribuído, seu, revisão pedida · aprovado"
    assert set(itens[0]) == {"chave", "titulo", "origem", "url", "quando", "corpo"}


def _item(numero, tipo, titulo):
    item = {"html_url": f"https://github.com/d/r/{tipo}s/{numero}", "title": titulo, "number": numero,
            "repository_url": "https://api.github.com/repos/d/r", "updated_at": "2026-10-16T10:00:00Z"}
    if tipo == "PR":
        item["pull_request"] = {}
    return item


def _api(pr=None, runs=(), status=None, revisoes=()):
    """Imita as respostas do GitHub para um PR: detalhes, check-runs, status combinado e revisões."""
    def falso(config, caminho, **params):
        if caminho.endswith("/check-runs"):
            if runs is None:
                raise RuntimeError("GitHub respondeu 403: Resource not accessible")
            return {"check_runs": [{"status": s, "conclusion": c} for s, c in runs]}
        if caminho.endswith("/status"):
            return status or {"state": "pending", "total_count": 0}
        if caminho.endswith("/reviews"):
            return [{"user": {"login": u}, "state": e} for u, e in revisoes]
        return {"head": {"sha": "abc"}, "draft": False, "mergeable_state": "clean", **(pr or {})}
    return falso


@pytest.mark.parametrize("api, esperado", [
    (_api(runs=[("completed", "success"), ("completed", "failure")]), "CI falhou"),
    (_api(status={"state": "failure", "total_count": 1}), "CI falhou"),
    (_api(runs=[("completed", "success")], revisoes=[("ana", "APPROVED"), ("bia", "CHANGES_REQUESTED")]), "mudanças pedidas"),
    (_api(revisoes=[("ana", "CHANGES_REQUESTED"), ("ana", "APPROVED")]), "aprovado"),       # vale a última da Ana
    (_api(pr={"mergeable_state": "dirty"}), "conflito"),
    (_api(runs=[("in_progress", None)]), "CI rodando"),
    (_api(), "esperando revisão"),                                   # sem status nenhum não é "pending"
    (_api(runs=None, revisoes=[("ana", "APPROVED")]), "aprovado"),   # token sem permissão de ler o CI
    (_api(pr={"draft": True}), "rascunho"),
])
def test_situacao_do_pr(monkeypatch, api, esperado):
    monkeypatch.setattr(github, "_get", api)
    assert github.situacao_do_pr(Config(dados={}), "d/r", 7) == esperado


def test_pr_seu_com_problema_deixa_a_rotina_em_atencao(tmp_path, monkeypatch):
    def busca(config, caminho, **params):
        q = params["q"]
        if "author:@me" in q:
            return {"items": [_item(7, "PR", "Meu PR"), _item(8, "PR", "Outro meu")]}
        if "review-requested" in q and "is:pull-request" in q:
            return {"items": [_item(9, "PR", "De um colega")]}
        return {"items": []}
    situacoes = {7: "CI falhou", 8: "aprovado"}
    monkeypatch.setattr(github, "_get", busca)
    monkeypatch.setattr(github, "situacao_do_pr", lambda config, repo, numero: situacoes[numero])
    estado = Estado(tmp_path / "e.db")

    r = tasks_github.rodar(Contexto(Config(dados={}), estado, ROTINAS["tasks_github"], estado.iniciar_execucao("tasks_github")))

    assert r.estado == ATENCAO
    assert r.resumo == "3 abertas · 1 esperando sua revisão · seus PRs: d/r #7 CI falhou"
    corpos = {i["titulo"]: i["corpo"] for i in estado.itens(["github"])}
    assert corpos == {"Meu PR": "PR · seu · CI falhou", "Outro meu": "PR · seu · aprovado",
                      "De um colega": "PR · revisão pedida"}
