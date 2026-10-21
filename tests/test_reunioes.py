import os
import time

import pytest

from automateum.config import Config
from automateum.nucleo.agendador import Contexto
from automateum.nucleo.estado import Estado
from automateum.nucleo.registro import ROTINAS
from automateum.rotinas import resumir_reunioes
from automateum.servicos import claude, copilot, reunioes


@pytest.fixture
def cfg(tmp_path):
    cofre = tmp_path / "cofre"
    (cofre / "Diário").mkdir(parents=True)
    dados = tmp_path / "dados"
    dados.mkdir()
    return Config(dados={"obsidian": {"cofre": str(cofre), "pasta_diario": "Diário",
                                      "pasta_automateum": "Automateum/Saídas"},
                         "reunioes": {"pasta": str(tmp_path / "Transcricoes"),
                                      "entrada": str(tmp_path / "Downloads" / "Gutenberg")}},
                  segredos={}, pasta_dados=dados)


def _transcricao(falas, codigo="abc-defg-hij"):
    linhas = [f"# Reunião 20/10/2026 — {codigo}", "", f"{len(falas)} falas", "", "---", ""]
    linhas += [f"**10:0{i}:00 — {quem}:** {texto}\n" for i, (quem, texto) in enumerate(falas)]
    return "\n".join(linhas)


def _baixar(cfg, nome, texto, dia="2026-10/20", antigo=True):
    caminho = reunioes.entrada(cfg) / dia / nome
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    if antigo:                                           # parado há mais de um minuto: o Chrome já terminou
        os.utime(caminho, (time.time() - 300, time.time() - 300))
    return caminho


_REUNIAO = [("Eu", "vamos fechar o escopo"), ("Ana", "eu mando o orçamento"), ("Eu", "combinado"),
            ("Ana", "até sexta")]


def _perguntas(monkeypatch, resposta="**Decisões**\n- fechar o escopo"):
    chamadas = []

    def falso(config, instrucao, dados=""):
        chamadas.append(dados)
        return resposta
    monkeypatch.setattr(claude, "perguntar", falso)
    monkeypatch.setattr(copilot, "perguntar", falso)
    return chamadas


def _rodar(cfg, estado):
    return resumir_reunioes.rodar(Contexto(cfg, estado, ROTINAS["resumir_reunioes"],
                                           estado.iniciar_execucao("resumir_reunioes")))


def test_configurado_pede_a_pasta():
    assert "reunioes.pasta" in reunioes.configurado(Config(dados={}, segredos={}))


def test_trazer_mantem_as_subpastas_e_nao_duplica(cfg):
    _baixar(cfg, "meet-a.md", "um")
    _baixar(cfg, "meet-a (1).md", "um")
    assert [p.relative_to(reunioes.pasta(cfg)).as_posix() for p in reunioes.trazer(cfg)] == \
        ["2026-10/20/meet-a (1).md", "2026-10/20/meet-a.md"]
    _baixar(cfg, "meet-a.md", "um")                     # baixou de novo, igual: só some de Downloads
    _baixar(cfg, "meet-b.md", "dois")
    _baixar(cfg, "meet-a (1).md", "diferente")          # mesmo nome, outro conteúdo: não sobrescreve
    movidas = reunioes.trazer(cfg)
    assert sorted(p.name for p in movidas) == ["meet-a (1) (2).md", "meet-b.md"]
    assert not list(reunioes.entrada(cfg).rglob("*.md"))
    assert (reunioes.pasta(cfg) / "2026-10/20/meet-a (1).md").read_text() == "um"


def test_copias_da_mesma_reuniao_contam_uma_vez_pela_maior(cfg):
    _baixar(cfg, "meet-a.md", "curta")
    _baixar(cfg, "meet-a (1).md", "a versão mais longa")
    _baixar(cfg, "teams-b.md", "outra", dia="2026-10/21")
    reunioes.trazer(cfg)
    lista = reunioes.transcricoes(cfg)
    assert [(t["chave"], t["arquivo"].name, t["dia"]) for t in lista] == [
        ("2026-10/20/meet-a", "meet-a (1).md", "2026-10-20"), ("2026-10/21/teams-b", "teams-b.md", "2026-10-21")]


def test_ler_conta_as_falas_e_quem_falou(cfg):
    caminho = _baixar(cfg, "meet-a.md", _transcricao(_REUNIAO))
    dados = reunioes.ler(caminho)
    assert dados["titulo"] == "Reunião 20/10/2026 — abc-defg-hij"
    assert dados["falas"] == 4 and dados["quem"] == ["Ana", "Eu"] and dados["inicio"] == "10:00"


def test_resume_no_cofre_e_no_diario_do_dia_e_nao_repete(cfg, monkeypatch):
    estado = Estado(cfg.banco)
    chamadas = _perguntas(monkeypatch)
    _baixar(cfg, "meet-abc.md", _transcricao(_REUNIAO))

    assert _rodar(cfg, estado) == "1 trazidas de Downloads · 1 reuniões resumidas"

    assert "eu mando o orçamento" in chamadas[0]
    nota = cfg.cofre / "Automateum/Saídas/Reuniões/2026-10-20 10h00 meet-abc.md"
    assert "fechar o escopo" in nota.read_text(encoding="utf-8")
    diario = (cfg.cofre / "Diário/2026-10-20.md").read_text(encoding="utf-8")
    assert "## Reuniões" in diario and "[[Automateum/Saídas/Reuniões/2026-10-20 10h00 meet-abc|" in diario
    assert _rodar(cfg, estado) == "nenhuma reunião nova" and len(chamadas) == 1


def test_copia_maior_resume_de_novo_sem_duplicar_no_diario(cfg, monkeypatch):
    estado = Estado(cfg.banco)
    _perguntas(monkeypatch, "primeira versão")
    _baixar(cfg, "meet-abc.md", _transcricao(_REUNIAO[:3]))
    _rodar(cfg, estado)
    _perguntas(monkeypatch, "versão final")
    _baixar(cfg, "meet-abc (1).md", _transcricao(_REUNIAO))

    _rodar(cfg, estado)

    diario = (cfg.cofre / "Diário/2026-10-20.md").read_text(encoding="utf-8")
    assert "versão final" in diario and "primeira versão" not in diario


def test_grupo_quando_so_falou_gente_do_grupo(cfg):
    cfg.dados["reunioes"]["grupos"] = {"cliente": {"pasta": "Cliente/Meets", "pessoas": ["Ana", "Bruno Lima"]}}
    assert reunioes.grupo(cfg, ["Eu", "ana souza"])[0] == "cliente"
    assert reunioes.grupo(cfg, ["Bruno Lima", "Ana"])[0] == "cliente"
    assert reunioes.grupo(cfg, ["Eu", "Ana", "Carla"]) is None              # alguém de fora: provavelmente não é
    assert reunioes.grupo(cfg, ["Eu", "Bruno Costa"]) is None               # "Bruno" sozinho não basta
    assert reunioes.grupo(cfg, ["Eu"]) is None                              # só eu: não dá para saber pelas pessoas


def test_grupo_pelo_assunto_quando_cita_os_termos(cfg):
    cfg.dados["reunioes"]["grupos"] = {"cliente": {"pasta": "Cliente/Meets", "pessoas": ["Ana"],
                                                   "palavras": ["ACME", "WT"]}}
    assert reunioes.grupo(cfg, ["Eu", "Carla"], "a WT-1836 subiu; a acme pediu revisão")[0] == "cliente"
    assert reunioes.grupo(cfg, ["Eu", "Carla"], "falamos da acme de passagem") is None   # uma citação só
    assert reunioes.grupo(cfg, ["Eu", "Carla"], "o NEWT e o awt não contam") is None


def test_reuniao_do_cliente_vai_tambem_para_a_nota_do_dia_dele(cfg, monkeypatch):
    cfg.dados["reunioes"]["grupos"] = {"cliente": {"pasta": "Cliente/Meets", "pessoas": ["Ana"]}}
    (cfg.cofre / "Cliente/Meets").mkdir(parents=True)
    (cfg.cofre / "Cliente/Meets/20-10.md").write_text("1. minhas anotações\n", encoding="utf-8")
    _perguntas(monkeypatch)
    _baixar(cfg, "meet-abc.md", _transcricao(_REUNIAO))
    _baixar(cfg, "meet-interna.md", _transcricao([("Eu", "a"), ("Carla", "b"), ("Ana", "c")], "xyz"))

    _rodar(cfg, Estado(cfg.banco))

    nota = (cfg.cofre / "Cliente/Meets/20-10.md").read_text(encoding="utf-8")
    assert nota.startswith("1. minhas anotações") and "## Reuniões" in nota and "fechar o escopo" in nota
    assert "xyz" not in nota                                        # a interna fica só no diário
    diario = (cfg.cofre / "Diário/2026-10-20.md").read_text(encoding="utf-8")
    assert "abc-defg-hij" in diario and "xyz" in diario
    assert len(list((cfg.cofre / "Automateum/Saídas/Reuniões").glob("*.md"))) == 2


def test_nota_do_grupo_usa_a_que_ja_existe_sem_zero(cfg):
    (cfg.cofre / "Cliente/Meets").mkdir(parents=True)
    assert resumir_reunioes.nota_do_grupo(cfg, "Cliente/Meets", "2026-10-05") == "Cliente/Meets/05-10.md"
    (cfg.cofre / "Cliente/Meets/5-10.md").write_text("x", encoding="utf-8")
    assert resumir_reunioes.nota_do_grupo(cfg, "Cliente/Meets", "2026-10-05") == "Cliente/Meets/5-10.md"


def test_teste_de_microfone_e_arquivo_recente_nao_vao_para_a_ia(cfg, monkeypatch):
    estado = Estado(cfg.banco)
    chamadas = _perguntas(monkeypatch)
    _baixar(cfg, "meet-teste.md", _transcricao(_REUNIAO[:2]))
    _baixar(cfg, "meet-agora.md", _transcricao(_REUNIAO), antigo=False)

    assert _rodar(cfg, estado) == "2 trazidas de Downloads · 1 curtas demais (menos de 3 falas)"
    assert chamadas == []
