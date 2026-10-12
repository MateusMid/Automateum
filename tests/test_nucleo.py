from datetime import date

import pytest

from automateum.config import Config
from automateum.nucleo.agendador import Agendador
from automateum.nucleo.estado import Estado
from automateum.nucleo.eventos import Barramento
from automateum.nucleo.registro import ROTINAS, Atencao, gatilho, quando_texto, rotina
from automateum.servicos import obsidian


@pytest.fixture
def config(tmp_path):
    cofre = tmp_path / "cofre"
    (cofre / "Diário").mkdir(parents=True)
    return Config(dados={"obsidian": {"cofre": str(cofre), "pasta_diario": "Diário",
                                      "pasta_automateum": "Automateum/Saídas",
                                      "ignorar": [".obsidian", "Automateum/Saídas"]}},
                  pasta_dados=tmp_path)


# --- horários

def test_quando_texto():
    assert quando_texto("cada 2m") == "a cada 2 min"
    assert quando_texto("cada 1h") == "a cada 1 hora"
    assert quando_texto("cron: 30 8 * * mon-fri") == "08:30, seg a sex"
    assert quando_texto("cron: 0 9-18 * * mon-fri") == "de hora em hora, 9h às 18h, seg a sex"
    assert quando_texto("nunca") == "desligada"


def test_gatilho():
    assert gatilho("nunca") is None
    assert gatilho("cada 15m").interval.total_seconds() == 900
    assert gatilho("cron: 30 8 * * mon-fri") is not None
    with pytest.raises(ValueError):
        gatilho("de vez em quando")


# --- tasks do cofre

def test_extrair_tasks():
    texto = "\n".join([
        "- [ ] primeira",
        "- [x] feita",
        "  * [ ] aninhada",
        "1. [ ] numerada",
        "- [ ]",                     # vazia: não conta
        "```",
        "- [ ] dentro de código",
        "```",
        "texto - [ ] no meio da linha",
    ])
    assert obsidian.extrair_tasks(texto) == [(1, "primeira"), (3, "aninhada"), (4, "numerada")]


def test_tasks_abertas_ignora_pastas(config):
    (config.cofre / "a.md").write_text("- [ ] visível", encoding="utf-8")
    for pasta in (".obsidian", "Automateum/Saídas"):
        (config.cofre / pasta).mkdir(parents=True)
        (config.cofre / pasta / "x.md").write_text("- [ ] escondida", encoding="utf-8")
    (config.cofre / "Automateum" / "Roadmap.md").write_text("- [ ] do projeto", encoding="utf-8")
    assert sorted(t["chave"] for t in obsidian.tasks_abertas(config)) == ["Automateum/Roadmap.md:1", "a.md:1"]


# --- escrita em bloco

def test_bloco_no_fim_preserva_o_resto():
    original = "Reunião FH\r\natts Legis pilot"
    novo = obsidian.com_bloco(original, "meu_dia", "## Meu dia\n\nfoco")
    assert novo.startswith(original)
    assert novo == (original + "\r\n\r\n%% automateum:meu_dia:inicio %%\r\n## Meu dia\r\n\r\nfoco\r\n"
                    "%% automateum:meu_dia:fim %%\r\n")


def test_bloco_reescrito_nao_toca_no_entorno():
    um = obsidian.com_bloco("antes\n", "meu_dia", "v1")
    um += "escrito depois por mim\n"
    dois = obsidian.com_bloco(um, "meu_dia", "v2 mais longa")
    assert dois == um.replace("v1", "v2 mais longa")
    assert obsidian.com_bloco(dois, "meu_dia", "v2 mais longa") == dois


def test_blocos_diferentes_convivem():
    texto = obsidian.com_bloco("nota\n", "meu_dia", "manhã")
    texto = obsidian.com_bloco(texto, "dia_fechado", "noite")
    texto = obsidian.com_bloco(texto, "meu_dia", "manhã 2")
    assert "manhã 2" in texto and "noite" in texto and "manhã\n" not in texto
    assert texto.startswith("nota\n")


def test_escrever_bloco_diario_em_disco(config):
    nota = config.cofre / "Diário" / "2026-10-12.md"
    nota.write_bytes("linha minha\r\noutra\r\n".encode("utf-8"))
    obsidian.escrever_bloco_diario(config, "meu_dia", "## Meu dia\n\noi", date(2026, 10, 12))
    dados = nota.read_bytes()
    assert dados.startswith("linha minha\r\noutra\r\n".encode("utf-8"))
    assert b"\n" not in dados.replace(b"\r\n", b"")      # nenhuma quebra de linha trocada
    assert not list(nota.parent.glob("*.tmp"))


def test_escrita_nao_sai_da_pasta(config):
    with pytest.raises(PermissionError):
        obsidian.escrever_proprio(config, "../../fora.md", "x")
    with pytest.raises(PermissionError):
        obsidian.ler_nota(config, "../segredo.md")
    caminho = obsidian.escrever_proprio(config, "Mensagens/2026-10-12.md", "## 09:00\n\num")
    obsidian.escrever_proprio(config, "Mensagens/2026-10-12.md", "## 10:00\n\ndois", acrescentar=True)
    assert caminho.read_text(encoding="utf-8") == "## 09:00\n\num\n\n## 10:00\n\ndois\n"


# --- estado e execução

def test_itens_substituir_e_juntar(tmp_path):
    e = Estado(tmp_path / "t.db")
    e.substituir_itens("obsidian", [{"chave": "a", "titulo": "A"}, {"chave": "b", "titulo": "B"}])
    e.substituir_itens("obsidian", [{"chave": "b", "titulo": "B2"}])
    assert [i["titulo"] for i in e.itens(["obsidian"])] == ["B2"]
    assert e.juntar_itens("slack", [{"chave": "1", "titulo": "x"}, {"chave": "2", "titulo": "y"}]) == 2
    assert e.juntar_itens("slack", [{"chave": "2", "titulo": "y"}, {"chave": "3", "titulo": "z"}]) == 1
    assert e.contar_itens("slack") == 3


def test_execucao_registra_resultado_e_avisa_so_na_virada(config, tmp_path):
    e = Estado(tmp_path / "t.db")
    resultado = {"modo": "ok"}

    @rotina(id="_teste", nome="teste", frente="Teste", quando="nunca")
    def rodar(ctx):
        ctx.log("uma linha")
        if resultado["modo"] == "erro":
            raise RuntimeError("quebrou")
        if resultado["modo"] == "atencao":
            raise Atencao("olhe isto")
        return "tudo certo"

    try:
        ag = Agendador(config, e, Barramento())
        for modo in ("ok", "atencao", "erro", "erro"):
            resultado["modo"] = modo
            ag.executar("_teste")
        status = [(x["status"], x["resumo"]) for x in reversed(e.execucoes("_teste"))]
        assert status == [("ok", "tudo certo"), ("atencao", "olhe isto"),
                          ("falha", "quebrou"), ("falha", "quebrou")]
        assert "uma linha" in e.execucoes("_teste")[0]["log"]
        assert "Traceback" in e.execucoes("_teste")[0]["log"]
        assert len(e.avisos()) == 1     # duas falhas seguidas, um aviso só
    finally:
        del ROTINAS["_teste"]


def test_rotina_sem_credencial_nao_roda(config, tmp_path):
    from automateum import rotinas, servicos  # noqa: F401
    e = Estado(tmp_path / "t.db")
    ag = Agendador(config, e, Barramento())
    assert "GITHUB_TOKEN" in ag.motivo_parada(ROTINAS["tasks_github"])
    ag.executar("tasks_github")
    assert e.execucoes("tasks_github") == []
