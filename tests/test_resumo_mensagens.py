import pytest

from automateum.config import Config
from automateum.nucleo.agendador import Contexto
from automateum.nucleo.estado import Estado
from automateum.nucleo.registro import ROTINAS
from automateum.rotinas import resumo_mensagens
from automateum.servicos import claude, copilot

CURSOR = "resumo_mensagens:ate"


@pytest.fixture
def ambiente(tmp_path):
    cofre = tmp_path / "cofre"
    cofre.mkdir()
    cfg = Config(dados={"obsidian": {"cofre": str(cofre), "pasta_automateum": "Automateum/Saídas"}},
                 segredos={}, pasta_dados=tmp_path)
    estado = Estado(cfg.banco)
    rotina = ROTINAS["resumo_mensagens"]
    ctx = Contexto(cfg, estado, rotina, estado.iniciar_execucao("resumo_mensagens"))
    return cfg, estado, ctx


def _mensagens(n):
    return [{"chave": f"m{i}", "titulo": f"assunto {i}", "corpo": "texto", "origem": "alguem@x.com"}
            for i in range(n)]


def _perguntas(monkeypatch, resposta="resumo pronto"):
    chamadas = []

    def falso(config, instrucao, dados=""):
        chamadas.append(dados)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    monkeypatch.setattr(claude, "perguntar", falso)
    monkeypatch.setattr(copilot, "perguntar", falso)   # o reserva também: senão o teste chamaria o Copilot de verdade
    return chamadas


def test_sem_mensagens_novas_nao_chama_o_claude(ambiente, monkeypatch):
    _, _, ctx = ambiente
    chamadas = _perguntas(monkeypatch)
    assert resumo_mensagens.rodar(ctx) == "nada novo para resumir"
    assert chamadas == []


def test_resume_anota_no_cofre_e_na_segunda_vez_nao_repete(ambiente, monkeypatch):
    cfg, estado, ctx = ambiente
    estado.juntar_itens("gmail", _mensagens(3))
    chamadas = _perguntas(monkeypatch)

    assert resumo_mensagens.rodar(ctx) == "3 mensagens resumidas"
    nota = next((cfg.cofre / "Automateum/Saídas/Mensagens").glob("*.md"))
    assert "resumo pronto" in nota.read_text(encoding="utf-8")
    assert estado.cursor(CURSOR)

    assert resumo_mensagens.rodar(ctx) == "nada novo para resumir"
    assert len(chamadas) == 1
    assert estado.avisos() == []


def test_falha_do_claude_nao_avanca_o_cursor(ambiente, monkeypatch):
    _, estado, ctx = ambiente
    estado.juntar_itens("gmail", _mensagens(2))
    _perguntas(monkeypatch, RuntimeError("claude saiu com código 1"))

    with pytest.raises(RuntimeError):
        resumo_mensagens.rodar(ctx)
    assert estado.cursor(CURSOR) == ""

    # na rodada seguinte as mesmas mensagens entram de novo
    _perguntas(monkeypatch)
    assert resumo_mensagens.rodar(ctx) == "2 mensagens resumidas"


def test_passar_do_teto_deixa_aviso(ambiente, monkeypatch):
    _, estado, ctx = ambiente
    estado.juntar_itens("gmail", _mensagens(resumo_mensagens._MAXIMO_NO_RESUMO + 25))
    chamadas = _perguntas(monkeypatch)

    resumo_mensagens.rodar(ctx)

    assert "mais 25 itens não listados" in chamadas[0]
    avisos = estado.avisos()
    assert len(avisos) == 1 and "25 mensagens ficaram de fora" in avisos[0]["texto"]


def test_dentro_do_teto_nao_avisa(ambiente, monkeypatch):
    _, estado, ctx = ambiente
    estado.juntar_itens("gmail", _mensagens(resumo_mensagens._MAXIMO_NO_RESUMO))
    _perguntas(monkeypatch)
    resumo_mensagens.rodar(ctx)
    assert estado.avisos() == []
