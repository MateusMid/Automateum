from automateum.config import Config
from automateum.servicos import github


def test_pendencias_usa_qualificador_de_tipo_e_junta_papeis(monkeypatch):
    consultas = []

    def falso_get(config, caminho, **params):
        consultas.append(params["q"])
        if "review-requested" in params["q"]:
            return {"items": [_item(7, "PR", "Revisar parser")]}
        if "is:pr assignee" in params["q"]:
            return {"items": [_item(7, "PR", "Revisar parser")]}
        return {"items": [_item(3, "issue", "Minha issue")]}

    monkeypatch.setattr(github, "_get", falso_get)
    itens = github.pendencias(Config(dados={}, segredos={}, pasta_dados=None))

    assert all("is:issue" in q or "is:pr" in q for q in consultas)
    por_titulo = {i["titulo"]: i for i in itens}
    assert por_titulo["Minha issue"]["corpo"] == "issue · atribuído"
    assert por_titulo["Revisar parser"]["corpo"] == "PR · atribuído, revisão pedida"
    assert set(itens[0]) == {"chave", "titulo", "origem", "url", "quando", "corpo"}


def _item(numero, tipo, titulo):
    item = {"html_url": f"https://github.com/d/r/{tipo}s/{numero}", "title": titulo, "number": numero,
            "repository_url": "https://api.github.com/repos/d/r", "updated_at": "2026-10-16T10:00:00Z"}
    if tipo == "PR":
        item["pull_request"] = {}
    return item
