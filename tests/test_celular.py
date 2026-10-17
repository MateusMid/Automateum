import pytest
from fastapi.testclient import TestClient

from automateum.config import Config
from automateum.web.api import criar_app

REDE = "192.168.0.20"


def _app(tmp_path, celular=True):
    cofre = tmp_path / "cofre"
    cofre.mkdir(exist_ok=True)
    pasta = tmp_path / "dados"
    pasta.mkdir(exist_ok=True)
    painel = {"celular": True} if celular else {}
    cfg = Config(dados={"obsidian": {"cofre": str(cofre), "pasta_automateum": "Automateum/Saídas"}, "painel": painel},
                 segredos={}, pasta_dados=pasta)
    return criar_app(cfg), pasta


def _celular(app, ip="192.168.0.50", host=f"{REDE}:8765"):
    c = TestClient(app, client=(ip, 50000), follow_redirects=False)
    c.headers.update({"host": host})
    return c


def _chave(pasta):
    return (pasta / "celular.chave").read_text(encoding="utf-8").strip()


@pytest.fixture
def ambiente(tmp_path):
    app, pasta = _app(tmp_path)
    # a página /celular, aberta no próprio computador, é quem cria a chave
    local = TestClient(app)
    local.headers.update({"host": "127.0.0.1:8765"})
    assert local.get("/celular").status_code == 200
    return app, pasta, local


def test_desligado_por_padrao_recusa_a_rede(tmp_path):
    app, _ = _app(tmp_path, celular=False)
    c = _celular(app)
    assert c.get("/").status_code == 403
    local = TestClient(app)
    local.headers.update({"host": "127.0.0.1:8765"})
    assert "desligado" in local.get("/celular").text


def test_sem_chave_nao_entra(ambiente):
    app, _, _ = ambiente
    r = _celular(app).get("/")
    assert r.status_code == 401 and "celular" in r.text


def test_chave_certa_vira_cookie_e_libera_a_leitura(ambiente):
    app, pasta, _ = ambiente
    c = _celular(app)
    r = c.get(f"/?chave={_chave(pasta)}")
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=strict" in r.headers["set-cookie"].lower()
    assert _chave(pasta) not in r.headers["set-cookie"]               # o cookie não carrega a chave
    assert c.get("/api/hoje").status_code == 200                      # o cliente guardou o cookie
    assert c.get("/dados/estado.js").status_code == 200
    assert c.get("/api/maquina/historico").status_code == 200


def test_chave_errada_e_bloqueio_por_tentativas(ambiente):
    app, _, _ = ambiente
    c = _celular(app)
    for _ in range(8):
        assert c.get("/?chave=errada").status_code == 401
    assert c.get("/?chave=errada").status_code == 429


def test_celular_nao_executa_nada(ambiente):
    app, pasta, _ = ambiente
    c = _celular(app)
    c.get(f"/?chave={_chave(pasta)}")
    assert c.post("/acao", json={"acao": "rodar:saude"}, headers={"X-Mapa-Token": "x"}).status_code == 403
    assert c.post("/api/rotinas/saude/rodar").status_code == 403
    assert c.get("/dados/acoes.js").status_code == 403                # a chave dos botões não sai do computador
    assert c.get("/estado/1").status_code == 403
    assert c.get("/celular").status_code == 403                       # o QR só aparece no computador


def test_so_rede_privada_e_so_ip_no_host(ambiente):
    app, pasta, _ = ambiente
    chave = _chave(pasta)
    assert _celular(app, ip="8.8.8.8").get(f"/?chave={chave}").status_code == 403            # cliente de fora da rede
    assert _celular(app, host="meu-pc.exemplo.com:8765").get(f"/?chave={chave}").status_code == 403   # nome: rebinding
    assert _celular(app, host="8.8.8.8:8765").get(f"/?chave={chave}").status_code == 403


def test_origem_de_outro_site_e_recusada(ambiente):
    app, pasta, _ = ambiente
    c = _celular(app)
    c.get(f"/?chave={_chave(pasta)}")
    assert c.get("/api/hoje", headers={"origin": "http://evil.example"}).status_code == 403


def test_host_local_vindo_de_outro_aparelho_nao_vale(ambiente):
    app, _, _ = ambiente
    c = _celular(app, host="127.0.0.1:8765")                          # aparelho da rede fingindo ser o próprio PC
    assert c.get("/dados/acoes.js").status_code == 403
    assert c.post("/acao", json={"acao": "rodar:saude"}).status_code == 403


def test_pagina_do_computador_mostra_o_link_com_a_chave(ambiente):
    _, pasta, local = ambiente
    r = local.get("/celular")
    assert "chave=" + _chave(pasta) in r.text or "Não achei o endereço" in r.text
