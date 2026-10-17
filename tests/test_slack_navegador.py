import json
import re
from datetime import date

import pytest

from automateum.config import Config
from automateum.nucleo.agendador import Contexto
from automateum.nucleo.estado import Estado
from automateum.nucleo.registro import ATENCAO, FALHA, OK, ROTINAS
from automateum.rotinas import coletar_slack
from automateum.servicos import slack, slack_navegador

HOJE = date(2026, 10, 17)

TEXTO = """Slack de 16/10 00h00 a 17/10 (colhido em 17/10 09:30): 5 mensagens.

ATENCAO: 1 fonte pode estar incompleta nesta janela: #geral (parede de cache).

Cada mensagem traz uma chave entre colchetes depois do autor, como [s12].

## #geral
- 16/10 14h05 Ana Souza [s1]: bom dia pessoal
    > 16/10 14h10 Bruno [s1]: bom dia
- 9h30 Carlos [s2]: [omitida]
- (thread de mensagem antiga) 10/10 11h00 Dani [s3]: thread velha

## DM Eva
- 8h Eu Mesmo [s4]: minha própria mensagem
- 17/10 8h15 Eva: sem chave
"""
LINKS = {"s1": {"link": "https://x.slack.com/archives/C1/p1", "exato": True},
         "s3": {"link": "https://x.slack.com/archives/C1/p3", "exato": False}}


def test_converter_le_mensagens_respostas_e_threads():
    itens, aviso = slack_navegador.converter(TEXTO, LINKS, HOJE)

    assert aviso.startswith("ATENCAO: 1 fonte pode estar incompleta")
    por_titulo = {i["titulo"]: i for i in itens}
    assert "Carlos: [omitida]" not in por_titulo           # linha toda omitida não vira item
    ana = por_titulo["Ana Souza: bom dia pessoal"]
    assert ana["origem"] == "#geral" and ana["quando"] == "2026-10-16T14:05:00"
    assert ana["url"].endswith("/p1")
    assert por_titulo["Bruno: bom dia"]["quando"] == "2026-10-16T14:10:00"   # resposta de thread
    assert por_titulo["Dani: thread velha"]["quando"] == "2026-10-10T11:00:00"
    eva = por_titulo["Eva: sem chave"]
    assert eva["origem"] == "DM Eva" and eva["url"] == ""
    assert len({i["chave"] for i in itens}) == len(itens)


def test_converter_pula_as_proprias_mensagens():
    itens, _ = slack_navegador.converter(TEXTO, LINKS, HOJE, eu="eu mesmo")
    assert not any(i["titulo"].startswith("Eu Mesmo") for i in itens)
    itens, _ = slack_navegador.converter(TEXTO, LINKS, HOJE)
    assert any(i["titulo"].startswith("Eu Mesmo") for i in itens)


def test_chave_nao_muda_quando_a_mensagem_de_hoje_vira_ontem():
    hoje = "## #geral\n- 14h05 Ana [s1]: avisei sobre o deploy\n"
    no_dia_seguinte = "## #geral\n- 17/10 14h05 Ana [s1]: avisei sobre o deploy\n"
    a, _ = slack_navegador.converter(hoje, {}, date(2026, 10, 17))
    b, _ = slack_navegador.converter(no_dia_seguinte, {}, date(2026, 10, 18))
    assert a[0]["chave"] == b[0]["chave"] and a[0]["quando"] == b[0]["quando"]


def test_data_de_dezembro_lida_em_janeiro_cai_no_ano_anterior():
    itens, _ = slack_navegador.converter("## #geral\n- 31/12 10h Ana: feliz ano\n", {}, date(2027, 1, 1))
    assert itens[0]["quando"] == "2026-12-31T10:00:00"


def test_texto_sem_aviso_nem_blocos():
    assert slack_navegador.converter("só um cabeçalho\n", {}, HOJE) == ([], None)


# --- configuração e execução

@pytest.fixture
def cfg(tmp_path, monkeypatch):
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "colher.ps1").write_text("# falso")
    perfil = tmp_path / "perfil"
    monkeypatch.setattr(slack_navegador, "_PERFIL", perfil)
    dados = tmp_path / "dados"
    dados.mkdir()
    return Config(dados={"slack": {"modo": "navegador", "kit": str(kit), "fora": ["Bot", "Avisos"],
                                   "time": "T123", "meu_nome": "Eu Mesmo"}},
                  segredos={}, pasta_dados=dados)


def test_configurado_em_etapas(cfg, tmp_path):
    assert "entrar no Slack" in slack.configurado(cfg)
    (tmp_path / "perfil").mkdir()
    assert slack.configurado(cfg) is None
    assert slack.checar(cfg).estado == OK

    sem_kit = Config(dados={"slack": {"modo": "navegador"}}, segredos={}, pasta_dados=tmp_path)
    assert "kit" in slack.configurado(sem_kit)
    assert slack.checar(sem_kit).estado == FALHA


def test_modo_app_continua_pedindo_o_token(tmp_path):
    c = Config(dados={}, segredos={}, pasta_dados=tmp_path)
    assert slack.configurado(c) == "falta SLACK_TOKEN no .env"


def _falso_executar(cfg, monkeypatch, codigo=0, saida="", escrever=True):
    chamadas = []

    def falso(comando, env, cwd, limite):
        chamadas.append((comando, env, limite))
        pasta = cfg.pasta_dados / "slack"
        pasta.mkdir(exist_ok=True)
        (pasta / "slack-colheita-2026-10-17.json").write_text("cru, sem máscara")
        if escrever and not codigo:
            (pasta / "slack-2026-10-17.txt").write_text(TEXTO, encoding="utf-8")
            (pasta / "slack-2026-10-17.txt.links.json").write_text(json.dumps(LINKS), encoding="utf-8")
        return codigo, saida

    monkeypatch.setattr(slack_navegador, "_executar", falso)
    return chamadas


def test_colher_passa_o_ambiente_converte_e_apaga_o_cru(cfg, tmp_path, monkeypatch):
    (tmp_path / "perfil").mkdir()
    chamadas = _falso_executar(cfg, monkeypatch)

    itens, aviso = slack_navegador.colher(cfg)

    comando, env, limite = chamadas[0]
    assert "colher.ps1" in " ".join(comando) and comando[-2:] == ["-Pasta", str(cfg.pasta_dados / "slack")]
    assert env["SLACK_FORA"] == "Bot,Avisos" and env["SLACK_TIME"] == "T123"
    assert limite == 2700
    assert itens and aviso
    assert not any(i["titulo"].startswith("Eu Mesmo") for i in itens)
    assert not list((cfg.pasta_dados / "slack").glob("slack-colheita-*"))   # o texto sem máscara não fica


@pytest.mark.parametrize("codigo, trecho", [(6, "login do Slack caiu"), (5, "aberto em outra janela"),
                                            (1, "falhou (código 1)")])
def test_colher_traduz_os_codigos_de_saida(cfg, tmp_path, monkeypatch, codigo, trecho):
    (tmp_path / "perfil").mkdir()
    _falso_executar(cfg, monkeypatch, codigo=codigo, saida="detalhe do erro")
    with pytest.raises(RuntimeError, match=re.escape(trecho)):
        slack_navegador.colher(cfg)


def test_colher_sem_o_texto_gerado(cfg, tmp_path, monkeypatch):
    (tmp_path / "perfil").mkdir()
    _falso_executar(cfg, monkeypatch, escrever=False)
    with pytest.raises(RuntimeError, match="não gerou o texto"):
        slack_navegador.colher(cfg)


def test_rotina_guarda_itens_sem_duplicar_e_marca_atencao(cfg, tmp_path, monkeypatch):
    (tmp_path / "perfil").mkdir()
    _falso_executar(cfg, monkeypatch)
    estado = Estado(cfg.banco)
    ctx = Contexto(cfg, estado, ROTINAS["coletar_slack"], estado.iniciar_execucao("coletar_slack"))

    r = coletar_slack.rodar(ctx)
    assert r.estado == ATENCAO and "fonte incompleta" in r.resumo
    guardados = estado.contar_itens("slack")
    assert guardados == 4 and r.resumo.startswith("4 novas")

    r2 = coletar_slack.rodar(ctx)
    assert estado.contar_itens("slack") == guardados and r2.resumo.startswith("nada novo")
