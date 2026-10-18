import dataclasses
import threading
import time

import pytest
from fastapi.testclient import TestClient

from automateum.config import Config
from automateum.nucleo import saidas
from automateum.nucleo.agendador import Agendador
from automateum.nucleo.estado import Estado
from automateum.nucleo.eventos import Barramento
from automateum.nucleo.registro import FALHA, ROTINAS, Rotina
from automateum.web.api import criar_app


@pytest.fixture
def cfg(tmp_path):
    cofre = tmp_path / "Meu Cofre"
    cofre.mkdir()
    dados = tmp_path / "dados"
    dados.mkdir()
    return Config(dados={"obsidian": {"cofre": str(cofre), "pasta_automateum": "Automateum/Saídas"},
                         "painel": {"porta": 8765}}, segredos={}, pasta_dados=dados)


def _agendador(cfg, monkeypatch, func, rotina_id="rotina_teste", **extra):
    base = Rotina(rotina_id, "rotina de teste", "Teste", "nunca", func, [], [], "Faz uma coisa de teste.")
    monkeypatch.setitem(ROTINAS, rotina_id, dataclasses.replace(base, **extra))
    estado = Estado(cfg.banco)
    return Agendador(cfg, estado, Barramento()), estado


def _nota(cfg, rotina_id="rotina_teste"):
    return (cfg.cofre / "Automateum/Saídas/Rotinas" / f"{rotina_id}.md")


def test_rodada_grava_a_nota_com_resultado_texto_e_log(cfg, monkeypatch):
    def rotina(ctx):
        ctx.log("passo um")
        ctx.texto = "Este é o texto gerado."
        return "feito: 3 coisas"

    agendador, _ = _agendador(cfg, monkeypatch, rotina)
    agendador.executar("rotina_teste")

    texto = _nota(cfg).read_text(encoding="utf-8")
    assert "rotina: rotina_teste" in texto and "estado: ok" in texto
    assert "# rotina de teste" in texto and "feito: 3 coisas" in texto
    assert "Faz uma coisa de teste." in texto and "Este é o texto gerado." in texto
    assert "passo um" in texto


def test_falha_tambem_grava_a_nota(cfg, monkeypatch):
    def rotina(ctx):
        raise RuntimeError("serviço fora do ar")

    agendador, _ = _agendador(cfg, monkeypatch, rotina)
    agendador.executar("rotina_teste")
    texto = _nota(cfg).read_text(encoding="utf-8")
    assert f"estado: {FALHA}" in texto and "serviço fora do ar" in texto


def test_mesmo_resultado_nao_reescreve_mas_mudanca_sim(cfg, monkeypatch):
    resultado = {"v": "igual"}
    agendador, _ = _agendador(cfg, monkeypatch, lambda ctx: resultado["v"])
    agendador.executar("rotina_teste")
    nota = _nota(cfg)
    primeira = nota.read_text(encoding="utf-8")

    time.sleep(1.1)  # o carimbo da nota tem resolução de segundos
    agendador.executar("rotina_teste")
    assert nota.read_text(encoding="utf-8") == primeira          # igual: não mexe no cofre

    resultado["v"] = "outro"
    agendador.executar("rotina_teste")
    assert "outro" in nota.read_text(encoding="utf-8")


def test_rodada_sem_novidade_nao_apaga_o_ultimo_texto(cfg, monkeypatch):
    def rotina(ctx):
        if ctx.estado.cursor("tem_novidade") == "1":
            ctx.texto = "**Precisa de ação:** responder o contrato."
            return "3 mensagens resumidas"
        return "nada novo para resumir"

    agendador, estado = _agendador(cfg, monkeypatch, rotina)
    estado.definir_cursor("tem_novidade", "1")
    agendador.executar("rotina_teste")
    estado.definir_cursor("tem_novidade", "0")
    estado._exec("UPDATE cursores SET valor = '' WHERE chave = 'nota:rotina_teste'")  # força reescrever a nota
    agendador.executar("rotina_teste")

    texto = _nota(cfg).read_text(encoding="utf-8")
    assert "nada novo para resumir" in texto                       # o resultado de agora aparece
    assert "responder o contrato" in texto                         # e o último texto de verdade continua
    assert "Último texto gerado, em" in texto
    ultimo = saidas.ultimo_texto(estado, "rotina_teste")
    assert ultimo["conteudo"].startswith("**Precisa de ação:**") and ultimo["quando"]


def test_ultimo_texto_sem_nada_gerado_ou_corrompido(cfg, monkeypatch):
    _, estado = _agendador(cfg, monkeypatch, lambda ctx: "ok")
    assert saidas.ultimo_texto(estado, "rotina_teste") is None
    estado.definir_cursor("texto:rotina_teste", "{isto não é json")
    assert saidas.ultimo_texto(estado, "rotina_teste") is None


def test_texto_fica_guardado_mesmo_sem_cofre(tmp_path, monkeypatch):
    cfg = Config(dados={}, segredos={}, pasta_dados=tmp_path)

    def rotina(ctx):
        ctx.texto = "briefing do dia"
        return "ok"

    agendador, estado = _agendador(cfg, monkeypatch, rotina)
    agendador.executar("rotina_teste")
    assert saidas.ultimo_texto(estado, "rotina_teste")["conteudo"] == "briefing do dia"


def test_coletores_nao_despejam_mensagens_no_cofre(cfg, monkeypatch):
    agendador, estado = _agendador(cfg, monkeypatch, lambda ctx: "ok", "coletar_slack")
    estado.juntar_itens("slack", [{"chave": "a", "titulo": "Ana: conversa reservada", "origem": "DM Ana"}])
    agendador.executar("coletar_slack")
    texto = _nota(cfg, "coletar_slack").read_text(encoding="utf-8")
    assert "1 guardados" in texto and "conversa reservada" not in texto


def test_rotinas_de_tasks_listam_os_itens_com_link(cfg, monkeypatch):
    agendador, estado = _agendador(cfg, monkeypatch, lambda ctx: "ok", "tasks_github")
    estado.substituir_itens("github", [{"chave": "k", "titulo": "Corrigir o mapa", "origem": "d/r #3",
                                        "url": "https://github.com/d/r/issues/3", "quando": "2026-10-16"}])
    agendador.executar("tasks_github")
    texto = _nota(cfg, "tasks_github").read_text(encoding="utf-8")
    assert "- [Corrigir o mapa](https://github.com/d/r/issues/3) — d/r #3 · 2026-10-16" in texto


def test_erro_ao_gravar_a_nota_nao_derruba_a_rodada(cfg, monkeypatch):
    def quebra(*a, **k):
        raise PermissionError("cofre somente leitura")

    monkeypatch.setattr(saidas.obsidian, "escrever_proprio", quebra)
    agendador, estado = _agendador(cfg, monkeypatch, lambda ctx: "deu certo")
    agendador.executar("rotina_teste")

    execucao = estado.execucoes("rotina_teste")[0]
    assert execucao["status"] == "ok" and execucao["resumo"] == "deu certo"
    assert "não consegui gravar a nota" in execucao["log"]


def test_sem_cofre_configurado_nao_faz_nada(tmp_path, monkeypatch):
    cfg = Config(dados={}, segredos={}, pasta_dados=tmp_path)
    agendador, estado = _agendador(cfg, monkeypatch, lambda ctx: "ok")
    agendador.executar("rotina_teste")
    assert estado.execucoes("rotina_teste")[0]["status"] == "ok"
    assert saidas.nota(cfg, "rotina_teste") is None


def test_nota_devolve_o_link_do_obsidian(cfg, monkeypatch):
    assert saidas.nota(cfg, "rotina_teste") is None              # ainda não existe
    agendador, _ = _agendador(cfg, monkeypatch, lambda ctx: "ok")
    agendador.executar("rotina_teste")

    n = saidas.nota(cfg, "rotina_teste")
    assert n["arquivo"] == "Automateum/Saídas/Rotinas/rotina_teste.md"
    assert n["obsidian"] == ("obsidian://open?vault=Meu%20Cofre"
                             "&file=Automateum/Sa%C3%ADdas/Rotinas/rotina_teste")


def test_arquivos_estaticos_sao_revalidados_pelo_navegador(cfg):
    cliente = TestClient(criar_app(cfg))
    cliente.headers.update({"host": "127.0.0.1:8765"})
    r = cliente.get("/static/gaveta.js")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache" and r.headers.get("etag")
    assert cliente.get("/static/gaveta.js", headers={"if-none-match": r.headers["etag"]}).status_code == 304


def test_api_da_rotina_traz_a_nota_e_o_log(cfg, monkeypatch):
    cliente = TestClient(criar_app(cfg))
    cliente.headers.update({"host": "127.0.0.1:8765"})
    base = Rotina("saude_x", "saúde x", "Teste", "nunca", lambda ctx: "ok")
    monkeypatch.setitem(ROTINAS, "saude_x", base)
    app = cliente.app
    app.state.agendador._travas["saude_x"] = threading.Lock()
    app.state.agendador.executar("saude_x")

    d = cliente.get("/api/no/rotina/saude_x").json()
    assert d["nota"]["obsidian"].startswith("obsidian://open?vault=")
    assert d["execucoes"][0]["status"] == "ok"
    assert d["texto"] is None                                      # esta rotina não gerou texto


def test_api_da_rotina_traz_o_ultimo_texto(cfg, monkeypatch):
    def rotina(ctx):
        ctx.texto = "Resumo do dia"
        return "ok"

    cliente = TestClient(criar_app(cfg))
    cliente.headers.update({"host": "127.0.0.1:8765"})
    monkeypatch.setitem(ROTINAS, "resumo_x", Rotina("resumo_x", "resumo x", "Teste", "nunca", rotina))
    cliente.app.state.agendador._travas["resumo_x"] = threading.Lock()
    cliente.app.state.agendador.executar("resumo_x")

    d = cliente.get("/api/no/rotina/resumo_x").json()
    assert d["texto"]["conteudo"] == "Resumo do dia" and d["texto"]["quando"]


def test_botao_abre_a_nota_no_obsidian_pelo_servidor(cfg, monkeypatch):
    from automateum.web import api
    abertos = []
    monkeypatch.setattr(api, "_abrir_no_sistema", abertos.append)
    cliente = TestClient(criar_app(cfg))
    cliente.headers.update({"host": "127.0.0.1:8765"})
    monkeypatch.setitem(ROTINAS, "saude_x", Rotina("saude_x", "saúde x", "Teste", "nunca", lambda ctx: "ok"))
    cliente.app.state.agendador._travas["saude_x"] = threading.Lock()
    token = cliente.get("/dados/acoes.js").text.split('"token": "', 1)[1].split('"', 1)[0]
    cab = {"X-Mapa-Token": token, "Origin": "http://127.0.0.1:8765"}
    assert cliente.post("/acao", json={"acao": "abrir-nota:saude_x"}, headers=cab).status_code == 404   # ainda sem nota
    cliente.app.state.agendador.executar("saude_x")
    assert cliente.post("/acao", json={"acao": "abrir-nota:saude_x"}, headers=cab).json() == {"id": 0}
    assert len(abertos) == 1 and abertos[0].startswith("obsidian://open?vault=")
    assert cliente.post("/acao", json={"acao": "abrir-nota:saude_x"}).status_code == 403             # sem token, nada abre
    assert len(abertos) == 1
