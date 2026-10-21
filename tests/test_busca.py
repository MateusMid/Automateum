from fastapi.testclient import TestClient

from automateum.config import Config
from automateum.nucleo import busca
from automateum.nucleo.estado import Estado
from automateum.web.api import criar_app


def _item(chave, titulo, corpo="", origem="", url="", quando="2026-10-20T10:00:00"):
    return {"chave": chave, "titulo": titulo, "corpo": corpo, "origem": origem, "url": url, "quando": quando}


def _estado(caminho):
    estado = Estado(caminho)
    estado.substituir_itens("obsidian", [_item("a:1", "Revisar a proposta da Reunião", origem="Clientes/Ata.md")])
    estado.substituir_itens("github", [_item("7", "Corrigir login", "PR · seu · CI falhou", "d/r", "https://github.com/d/r/pull/7")])
    estado.substituir_itens("slack", [_item(f"m{n}", f"proposta {n}", origem="#geral", quando=f"2026-10-{10 + n}T09:00:00")
                                      for n in range(5)])
    return estado


def test_acha_sem_acento_sem_maiuscula_e_com_todas_as_palavras(tmp_path):
    estado = _estado(tmp_path / "e.db")

    grupos = busca.buscar(estado, "reuniao PROPOSTA")
    assert [(g["fonte"], g["total"]) for g in grupos] == [("obsidian", 1)]
    assert grupos[0]["nome"] == "Tasks do cofre" and grupos[0]["itens"][0]["origem"] == "Clientes/Ata.md"

    assert [g["fonte"] for g in busca.buscar(estado, "ci falhou")] == ["github"]     # procura também no corpo
    assert [g["fonte"] for g in busca.buscar(estado, "#geral")] == ["slack"]         # e na origem


def test_agrupa_por_fonte_com_limite_e_mais_recentes_primeiro(tmp_path):
    estado = _estado(tmp_path / "e.db")
    grupos = busca.buscar(estado, "proposta", por_fonte=2)
    assert [g["fonte"] for g in grupos] == ["obsidian", "slack"]
    slack = grupos[1]
    assert slack["total"] == 5 and [i["titulo"] for i in slack["itens"]] == ["proposta 4", "proposta 3"]


def test_consulta_curta_nao_busca(tmp_path):
    estado = _estado(tmp_path / "e.db")
    assert busca.buscar(estado, "") == [] and busca.buscar(estado, " p ") == []


def test_rota_da_busca_no_computador(tmp_path):
    cfg = Config(dados={}, segredos={}, pasta_dados=tmp_path)
    _estado(cfg.banco)
    c = TestClient(criar_app(cfg))
    c.headers.update({"host": "127.0.0.1:8765"})
    d = c.get("/api/busca", params={"q": "login"}).json()
    assert d["q"] == "login" and d["grupos"][0]["itens"][0]["url"] == "https://github.com/d/r/pull/7"
