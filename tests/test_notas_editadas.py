import os
from datetime import date, datetime, timedelta

from automateum.config import Config
from automateum.nucleo.agendador import Contexto
from automateum.nucleo.estado import Estado
from automateum.nucleo.registro import ROTINAS
from automateum.rotinas import dia_fechado
from automateum.rotinas._texto import notas_editadas
from automateum.servicos import claude, git_local, obsidian


def _cofre(tmp_path):
    cofre = tmp_path / "cofre"
    cfg = Config(dados={"obsidian": {"cofre": str(cofre), "pasta_diario": "Diário"}}, segredos={},
                 pasta_dados=tmp_path)
    return cfg, cofre


def _nota(cofre, relativo, texto, quando=None):
    caminho = cofre / relativo
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    if quando:
        os.utime(caminho, (quando.timestamp(), quando.timestamp()))


def test_so_as_notas_editadas_desde_o_dia_fora_o_diario_e_as_saidas(tmp_path):
    cfg, cofre = _cofre(tmp_path)
    agora = datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=11)   # não cruza a meia-noite
    _nota(cofre, "Projetos/Plano.md", "plano novo", agora - timedelta(hours=1))
    _nota(cofre, "Clientes/Ata.md", "ata de agora", agora)
    _nota(cofre, "Projetos/Antiga.md", "de três dias atrás", agora - timedelta(days=3))
    _nota(cofre, f"Diário/{date.today().isoformat()}.md", "o diário já entra por outro caminho")
    _nota(cofre, "Automateum/Saídas/Reuniões/x.md", "escrita pelo Automateum")
    _nota(cofre, ".obsidian/workspace.md", "config do app")

    editadas = obsidian.notas_editadas(cfg, date.today())

    assert editadas == [("Clientes/Ata.md", "ata de agora"), ("Projetos/Plano.md", "plano novo")]   # mais recente primeiro
    assert [r for r, _ in obsidian.notas_editadas(cfg, date.today() - timedelta(days=3))][-1] == "Projetos/Antiga.md"


def test_material_corta_cada_nota_e_passa_o_resto_so_pelo_nome():
    so_bloco = obsidian.com_bloco("", "reunioes", "resumo escrito pelo Automateum")
    texto = notas_editadas([("A.md", "a" * 50), ("Meets/20-10.md", so_bloco), ("B.md", "b" * 50),
                            ("C.md", "c" * 50)], por_nota=40, total=100)

    assert texto.startswith("#### A.md\n" + "a" * 40 + " (...)")
    assert "#### B.md" in texto and "Meets/20-10.md" not in texto     # só tinha o bloco do Automateum
    assert texto.endswith("Também editadas (só o nome): C.md")
    assert notas_editadas([]) == ""


def test_dia_fechado_manda_as_notas_editadas_hoje(tmp_path, monkeypatch):
    cfg, cofre = _cofre(tmp_path)
    (cofre / "Diário").mkdir(parents=True)
    _nota(cofre, "Clientes/Ata.md", "combinamos a entrega na sexta")
    estado = Estado(cfg.banco)
    material = []
    monkeypatch.setattr(claude, "perguntar", lambda config, instrucao, dados="": material.append(dados) or "Dia.")
    monkeypatch.setattr(git_local, "auditar_dia", lambda *a, **k: [])

    dia_fechado.rodar(Contexto(cfg, estado, ROTINAS["dia_fechado"], estado.iniciar_execucao("dia_fechado")))

    assert "### Notas do cofre editadas hoje\n#### Clientes/Ata.md\ncombinamos a entrega na sexta" in material[0]
