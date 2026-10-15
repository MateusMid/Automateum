from datetime import date
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from automateum.config import Config
from automateum.nucleo import grafo
from automateum.nucleo.agendador import Agendador
from automateum.nucleo.estado import Estado
from automateum.nucleo.eventos import Barramento
from automateum.nucleo.registro import ATENCAO, FALHA, OK, PARADO, ROTINAS, SERVICOS, Checagem, rotina
from automateum.servicos import github, slack
from automateum.web.api import criar_app


@pytest.fixture
def ambiente(tmp_path):
    cofre = tmp_path / "cofre"
    (cofre / "Diário").mkdir(parents=True)
    pasta_dados = tmp_path / "dados"
    pasta_dados.mkdir(parents=True, exist_ok=True)
    cfg = Config(
        dados={
            "obsidian": {"cofre": str(cofre), "pasta_diario": "Diário", "pasta_automateum": "Automateum/Saídas"},
            "painel": {"host": "127.0.0.1", "porta": 8765},
            "github": {"repositorios": ["dono/repo"]},
            "slack": {"canais": ["geral"]},
        },
        segredos={"GITHUB_TOKEN": "token_teste", "SLACK_TOKEN": "xoxp-teste"},
        pasta_dados=pasta_dados,
    )
    estado = Estado(cfg.banco)
    barramento = Barramento()
    agendador = Agendador(cfg, estado, barramento)
    return cfg, estado, agendador, barramento


# --- Testes do Grafo (grafo.py)

def test_grafo_montar_estrutura_e_arestas(ambiente):
    cfg, estado, agendador, _ = ambiente
    dados_grafo = grafo.montar(cfg, estado, agendador)

    colunas = [c["titulo"] for c in dados_grafo["colunas"]]
    assert colunas == ["MÁQUINA", "SERVIÇOS", "FRENTES", "ROTINAS", "COM VOCÊ"]

    todos_nos = {no["id"] for col in dados_grafo["colunas"] for no in col["nos"]}
    assert "maquina" in todos_nos
    for aresta in dados_grafo["arestas"]:
        assert aresta["de"] in todos_nos, f"Nó de origem não existe: {aresta['de']}"
        assert aresta["para"] in todos_nos, f"Nó de destino não existe: {aresta['para']}"


def test_grafo_servico_em_falha_vira_raiz_e_avisa_rotina_dependente(ambiente):
    cfg, estado, agendador, _ = ambiente

    # Grava falha no serviço obsidian
    estado.salvar_checagem("obsidian", Checagem(FALHA, "erro de conexão ou cofre inacessível", ms=12))
    # Grava execução com falha na rotina dependente tasks_obsidian
    e_id = estado.iniciar_execucao("tasks_obsidian")
    estado.finalizar_execucao(e_id, FALHA, "falha de leitura")

    dados = grafo.montar(cfg, estado, agendador)
    nos = {no["id"]: no for col in dados["colunas"] for no in col["nos"]}

    servico_obs = nos["servico:obsidian"]
    assert servico_obs["estado"] == FALHA
    assert servico_obs["raiz"] is True

    rotina_obs = nos["rotina:tasks_obsidian"]
    assert rotina_obs["estado"] == FALHA
    assert rotina_obs["raiz"] is False  # não é raiz porque o serviço obsidian já explica
    assert any("depende de: Obsidian" in l for l in rotina_obs["linhas"])


def test_grafo_rotina_falha_sem_servico_culpado_vira_raiz(ambiente):
    cfg, estado, agendador, _ = ambiente

    # Todos os serviços OK
    for sid in SERVICOS:
        estado.salvar_checagem(sid, Checagem(OK, "operacional", ms=5))

    # Rotina saude falha (só usa máquina)
    e_id = estado.iniciar_execucao("saude")
    estado.finalizar_execucao(e_id, FALHA, "erro interno")

    dados = grafo.montar(cfg, estado, agendador)
    nos = {no["id"]: no for col in dados["colunas"] for no in col["nos"]}
    rotina_saude = nos["rotina:saude"]
    assert rotina_saude["estado"] == FALHA
    assert rotina_saude["raiz"] is True


def test_grafo_frente_pior_estado_ignora_parados(ambiente):
    cfg, estado, agendador, _ = ambiente

    # Cria rotinas de teste numa frente específica
    @rotina(id="_rot_ok", nome="ok", frente="FrenteTeste", quando="cada 1m")
    def r_ok(ctx): return "ok"

    @rotina(id="_rot_atencao", nome="atencao", frente="FrenteTeste", quando="cada 1m")
    def r_atencao(ctx): return "atencao"

    @rotina(id="_rot_parada", nome="parada", frente="FrenteTeste", quando="nunca")
    def r_parada(ctx): return "parada"

    try:
        e1 = estado.iniciar_execucao("_rot_ok")
        estado.finalizar_execucao(e1, OK, "tudo bem")
        e2 = estado.iniciar_execucao("_rot_atencao")
        estado.finalizar_execucao(e2, ATENCAO, "cuidado")

        dados = grafo.montar(cfg, estado, agendador)
        nos = {no["id"]: no for col in dados["colunas"] for no in col["nos"]}
        frente = nos["frente:FrenteTeste"]
        assert frente["estado"] == ATENCAO
    finally:
        del ROTINAS["_rot_ok"]
        del ROTINAS["_rot_atencao"]
        del ROTINAS["_rot_parada"]


# --- Testes da API Web (api.py)

def test_api_so_local_bloqueia_origem_externa(ambiente):
    cfg, _, _, _ = ambiente
    app = criar_app(cfg)
    with TestClient(app) as client:
        # Host externo
        resp = client.get("/api/grafo", headers={"Host": "evil.com"})
        assert resp.status_code == 403
        assert resp.json() == {"detail": "origem não permitida"}

        # Origin externa (CSRF)
        resp = client.get("/api/grafo", headers={"Host": "127.0.0.1:8765", "Origin": "http://evil.com"})
        assert resp.status_code == 403

        # Requisição local válida
        resp = client.get("/api/grafo", headers={"Host": "127.0.0.1:8765"})
        assert resp.status_code == 200
        assert "colunas" in resp.json()


def test_api_rotas_principais_e_detalhes_de_nos(ambiente):
    cfg, estado, _, _ = ambiente
    app = criar_app(cfg)
    with TestClient(app, headers={"Host": "localhost:8765"}) as client:
        # GET raiz serve o HTML do painel
        r = client.get("/")
        assert r.status_code == 200
        assert "Automateum" in r.text

        # GET /api/no/maquina
        r = client.get("/api/no/maquina/maquina")
        assert r.status_code == 200
        assert r.json()["tipo"] == "maquina"

        # GET /api/no/servico/github
        r = client.get("/api/no/servico/github")
        assert r.status_code == 200
        assert r.json()["titulo"] == "GitHub"

        # GET /api/no/rotina/tasks_obsidian
        r = client.get("/api/no/rotina/tasks_obsidian")
        assert r.status_code == 200
        assert r.json()["titulo"] == "tasks do cofre"

        # GET /api/no/frente/Tasks
        r = client.get("/api/no/frente/Tasks")
        assert r.status_code == 200

        # GET /api/no/destino/avisos
        r = client.get("/api/no/destino/avisos")
        assert r.status_code == 200

        # GET /api/no de nó desconhecido
        r = client.get("/api/no/rotina/rotina_inexistente")
        assert r.status_code == 404


def test_api_rodar_rotina_status_codes(ambiente):
    cfg, _, _, _ = ambiente
    app = criar_app(cfg)
    with TestClient(app, headers={"Host": "localhost:8765"}) as client:
        # Rotina inexistente -> 404
        r = client.post("/api/rotinas/inexistente/rodar")
        assert r.status_code == 404

        # Rotina válida sem credencial no config -> 409
        cfg_sem_segredo = Config(dados=cfg.dados, segredos={}, pasta_dados=cfg.pasta_dados)
        app_sem_cred = criar_app(cfg_sem_segredo)
        with TestClient(app_sem_cred, headers={"Host": "localhost:8765"}) as c2:
            r = c2.post("/api/rotinas/tasks_github/rodar")
            assert r.status_code == 409
            assert "GITHUB_TOKEN" in r.json()["detail"]


# --- Testes de Clientes com Respostas Simuladas

def test_github_pendencias_com_mock(ambiente, monkeypatch):
    cfg, _, _, _ = ambiente

    def mock_get(config, caminho, **parametros):
        if caminho == "/search/issues" and "assignee:@me" in parametros.get("q", ""):
            return {
                "items": [
                    {
                        "html_url": "https://github.com/dono/repo/issues/10",
                        "title": "Bug critico",
                        "repository_url": "https://api.github.com/repos/dono/repo",
                        "number": 10,
                        "updated_at": "2026-10-14T09:00:00Z",
                    }
                ]
            }
        if caminho == "/search/issues" and "review-requested:@me" in parametros.get("q", ""):
            return {
                "items": [
                    {
                        "html_url": "https://github.com/dono/repo/pull/20",
                        "title": "Novo endpoint",
                        "repository_url": "https://api.github.com/repos/dono/repo",
                        "number": 20,
                        "pull_request": {},
                        "updated_at": "2026-10-14T09:30:00Z",
                    }
                ]
            }
        return {"items": []}

    monkeypatch.setattr(github, "_get", mock_get)

    itens = github.pendencias(cfg)
    assert len(itens) == 2
    chaves = {i["chave"] for i in itens}
    assert "https://github.com/dono/repo/issues/10" in chaves
    assert "https://github.com/dono/repo/pull/20" in chaves


def test_slack_mensagens_novas_e_cursor_com_mock(ambiente, monkeypatch):
    cfg, _, _, _ = ambiente

    mock_client = MagicMock()
    mock_client.auth_test.return_value = {"user_id": "U_EU", "user": "eu", "team": "Time"}
    mock_client.users_conversations.return_value = {
        "channels": [{"id": "C123", "name": "geral"}],
        "response_metadata": {"next_cursor": None},
    }
    mock_client.users_info.return_value = {"user": {"real_name": "Colega Dev"}}
    mock_client.conversations_history.return_value = {
        "messages": [
            {"ts": "1700000001.000100", "user": "U_COLEGA", "text": "Alguem viu o deploy?"},
            {"ts": "1700000002.000200", "user": "U_EU", "text": "Mensagem minha (deve ser ignorada)"},
        ]
    }

    monkeypatch.setattr(slack, "_cliente", lambda c: mock_client)

    itens, cursores = slack.mensagens_novas(cfg, cursores={})
    assert len(itens) == 1
    assert itens[0]["chave"] == "C123:1700000001.000100"
    assert "Colega Dev: Alguem viu o deploy?" in itens[0]["titulo"]
    assert cursores["C123"] == "1700000002.000200"  # cursor avanca para a mensagem mais recente
