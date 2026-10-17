from automateum.config import Config
from automateum.servicos import github


def test_pendencias_consulta_por_tipo_sem_misturar(monkeypatch):
    consultas = []

    def falso(config, caminho, **params):
        consultas.append(params["q"])
        return {"items": []}

    monkeypatch.setattr(github, "_get", falso)
    github.pendencias(Config(dados={"github": {"repositorios": ["MateusMid/Automateum"]}}))

    assert len(consultas) == 4
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
    itens = github.pendencias(Config(dados={}))

    por_titulo = {i["titulo"]: i for i in itens}
    assert len(itens) == 2
    assert por_titulo["Minha issue"]["corpo"] == "issue · atribuído"
    assert por_titulo["Revisar parser"]["corpo"] == "PR · atribuído, revisão pedida"
    assert set(itens[0]) == {"chave", "titulo", "origem", "url", "quando", "corpo"}


def _item(numero, tipo, titulo):
    item = {"html_url": f"https://github.com/d/r/{tipo}s/{numero}", "title": titulo, "number": numero,
            "repository_url": "https://api.github.com/repos/d/r", "updated_at": "2026-10-16T10:00:00Z"}
    if tipo == "PR":
        item["pull_request"] = {}
    return item
