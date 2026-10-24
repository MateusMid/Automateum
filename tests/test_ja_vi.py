from fastapi.testclient import TestClient

from automateum.config import Config
from automateum.nucleo.estado import Estado
from automateum.web.api import criar_app

LOCAL = {"host": "127.0.0.1:8765"}
ORIGEM = {"origin": "http://127.0.0.1:8765"}


def _msg(chave, origem, quando, fonte="slack"):
    return {"chave": chave, "titulo": f"msg {chave}", "corpo": "", "origem": origem, "url": "", "quando": quando}


def _estado(caminho):
    estado = Estado(caminho)
    estado.juntar_itens("slack", [
        _msg("a1", "#geral", "2026-10-20T09:00:00"),
        _msg("a2", "#geral", "2026-10-20T10:00:00"),
        _msg("a3", "#geral", "2026-10-20T11:00:00"),
        _msg("b1", "Fulano", "2026-10-20T09:30:00"),
    ])
    return estado


def _chaves(estado):
    return sorted(i["chave"] for i in estado.itens_nao_vistos(["slack"]))


def test_ver_ate_esconde_a_conversa_ate_a_mensagem_marcada_inclusive(tmp_path):
    estado = _estado(tmp_path / "e.db")
    estado.ver_ate("slack", "#geral", "2026-10-20T10:00:00")

    assert _chaves(estado) == ["a3", "b1"]          # a1 e a2 saem; a outra conversa segue igual


def test_mensagem_nova_na_conversa_volta(tmp_path):
    estado = _estado(tmp_path / "e.db")
    estado.ver_ate("slack", "#geral", "2026-10-20T10:00:00")
    estado.juntar_itens("slack", [_msg("a4", "#geral", "2026-10-20T12:00:00")])

    assert "a4" in _chaves(estado) and "a1" not in _chaves(estado)


def test_marca_nao_volta_atras(tmp_path):
    estado = _estado(tmp_path / "e.db")
    estado.ver_ate("slack", "#geral", "2026-10-20T11:00:00")
    estado.ver_ate("slack", "#geral", "2026-10-20T09:00:00")     # uma marca mais antiga não desfaz a nova

    assert "a3" not in _chaves(estado)


def test_limite_vale_depois_de_filtrar(tmp_path):
    estado = _estado(tmp_path / "e.db")
    estado.ver_ate("slack", "#geral", "2026-10-20T11:00:00")
    assert [i["chave"] for i in estado.itens_nao_vistos(["slack"], limite=1)] == ["b1"]


def test_acao_ver_marca_pelo_painel_e_recusa_mensagem_inexistente(tmp_path):
    cfg = Config(dados={"painel": {"porta": 8765}}, segredos={}, pasta_dados=tmp_path)
    _estado(cfg.banco)
    c = TestClient(criar_app(cfg))
    c.headers.update(LOCAL)
    token = c.get("/dados/acoes.js").text.split('"token": "', 1)[1].split('"', 1)[0]
    cabecalhos = {"X-Mapa-Token": token, **ORIGEM}

    assert c.post("/acao", json={"acao": "ver:slack:a2"}, headers=cabecalhos).status_code == 200
    assert "a1" not in _chaves(c.app.state.estado) and "a3" in _chaves(c.app.state.estado)
    assert c.post("/acao", json={"acao": "ver:slack:nao-existe"}, headers=cabecalhos).status_code == 404
