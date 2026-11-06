from datetime import datetime, timedelta
from types import SimpleNamespace

from automateum.config import Config
from automateum.rotinas import pauta_reuniao
from automateum.servicos import ia, obsidian


def _contexto(tmp_path):
    cofre = tmp_path / "cofre"
    cofre.mkdir()
    config = Config(dados={"obsidian": {"cofre": str(cofre), "pasta_automateum": "Automateum"}},
                   segredos={}, pasta_dados=tmp_path)
    return SimpleNamespace(config=config)


def test_contexto_anterior_prioriza_o_resumo_relacionado_mais_recente(monkeypatch, tmp_path):
    ctx = _contexto(tmp_path)
    notas = [
        ("2026-10-30 10h00 Projeto Atlas", "Fulano discutiu projeto Atlas e decisões de produto."),
        ("2026-10-23 10h00 Projeto Atlas", "Fulano revisou o projeto Atlas e várias tarefas."),
        ("2026-11-06 10h00 Status", "Fulano pediu retorno sobre o cliente."),
    ]
    monkeypatch.setattr(obsidian, "notas_recentes", lambda *args: notas)

    resultado = pauta_reuniao._contexto_anterior(ctx, ["Fulano"], {"projeto", "atlas"})

    assert [nota["titulo"] for nota in resultado] == [notas[2][0], notas[0][0], notas[1][0]]
    assert resultado[0]["papel"] == "base principal: resumo mais recente relacionado"
    assert resultado[0]["origem"] == f"Automateum/Reuniões/{notas[2][0]}.md"
    assert all(nota["papel"] == "contexto anterior" for nota in resultado[1:])


def test_contexto_anterior_ignora_notas_sem_relacao(monkeypatch, tmp_path):
    ctx = _contexto(tmp_path)
    monkeypatch.setattr(obsidian, "notas_recentes", lambda *args: [
        ("2026-11-06 Saúde", "Consulta e exames"),
    ])

    assert pauta_reuniao._contexto_anterior(ctx, ["Fulano"], {"projeto", "atlas"}) == []


def test_data_reuniao_le_data_e_hora_do_nome_da_nota():
    assert pauta_reuniao._data_reuniao("2026-11-06 10h30 Projeto Atlas") == datetime(2026, 11, 6, 10, 30)
    assert pauta_reuniao._data_reuniao("Resumo antigo") is None


def test_roteiro_recebe_transcricao_recente_como_base_principal(monkeypatch, tmp_path):
    ctx = _contexto(tmp_path)
    notas = [("2026-11-06 10h00 Status", "**Próximos passos**: Fulano confirma o prazo do projeto Atlas.")]
    monkeypatch.setattr(obsidian, "notas_recentes", lambda *args: notas)
    monkeypatch.setattr(pauta_reuniao, "_tarefas", lambda *args: [])
    monkeypatch.setattr(pauta_reuniao, "_mensagens", lambda *args: [])
    chamadas = []
    monkeypatch.setattr(ia, "perguntar", lambda ctx, pedido, material: chamadas.append((pedido, material)) or
                        "Abertura: vamos conferir o prazo combinado.")
    inicio = datetime.now().astimezone() + timedelta(minutes=10)
    evento = {"id": "reuniao-1", "conta": "conta", "titulo": "Projeto Atlas", "inicio": inicio.isoformat(),
              "participantes": ["Fulano"], "descricao": "Revisar andamento"}

    pauta, _ = pauta_reuniao._preparar(ctx, evento, datetime.now().astimezone())

    pedido, material = chamadas[0]
    assert "abertura natural" in pedido
    assert "Retome ações e decisões da última transcrição" in pedido
    assert "resumo mais recente relacionado" in material
    assert "Fulano confirma o prazo do projeto Atlas" in material
    assert "Abertura: vamos conferir o prazo combinado." in pauta["conteudo"]
    arquivo = ctx.config.cofre / "Automateum" / "Reuniões" / pauta["nota"]
    assert arquivo.is_file()
    assert "Abertura: vamos conferir o prazo combinado." in arquivo.read_text(encoding="utf-8")
