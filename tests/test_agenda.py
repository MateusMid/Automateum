from datetime import date, datetime

import pytest

from automateum.config import Config
from automateum.nucleo.agendador import Contexto
from automateum.nucleo.estado import Estado
from automateum.nucleo.registro import ATENCAO, ROTINAS
from automateum.rotinas import coletar_agenda, dia_fechado, meu_dia
from automateum.rotinas._texto import agenda_do_dia
from automateum.servicos import agenda, git_local, gmail, ia, maquina


class _Requisicao:
    def __init__(self, resposta):
        self.resposta = resposta

    def execute(self):
        return self.resposta


class _Eventos:
    def __init__(self, paginas):
        self.paginas = paginas
        self.parametros = []

    def list(self, **parametros):
        self.parametros.append(parametros)
        return _Requisicao(self.paginas.pop(0))


class _Calendario:
    def __init__(self, eventos):
        self._eventos = eventos

    def events(self):
        return self._eventos

    def calendars(self):
        return self

    def get(self, **parametros):
        return _Requisicao({"id": "fulano@example.com"})


class _403(Exception):
    resp = type("Resposta", (), {"status": 403})()


class _Erro:
    def execute(self):
        raise _403("forbidden")


class _EventosNegados:
    def list(self, **parametros):
        return _Erro()


def _evento(id, inicio, fim, **extra):
    return {"id": id, "summary": id, "start": inicio, "end": fim, **extra}


def test_intervalo_dias_envia_limites_locais_com_fuso():
    inicio, fim = agenda.intervalo_dias(date(2026, 11, 6))
    inicio, fim = datetime.fromisoformat(inicio), datetime.fromisoformat(fim)
    assert inicio.tzinfo is not None and fim.tzinfo is not None
    assert inicio.date() == date(2026, 11, 6)
    assert fim.date() == date(2026, 11, 8)


def test_eventos_da_conta_paginam_e_normalizam_horarios(monkeypatch):
    conta = gmail.Conta("fulano@example.com", None)
    eventos = _Eventos([
        {"items": [
            _evento("reuniao", {"dateTime": "2026-11-06T10:00:00-03:00"},
                    {"dateTime": "2026-11-06T10:30:00-03:00"}, htmlLink="https://calendar/evento",
                    attendees=[{"displayName": "Fulano"}, {"email": "sala@example.com", "resource": True}],
                    hangoutLink="https://meet.google.com/abc"),
            _evento("dia-inteiro", {"date": "2026-11-06"}, {"date": "2026-11-07"}),
            {**_evento("cancelado", {"date": "2026-11-06T12:00:00-03:00"},
                       {"dateTime": "2026-11-06T12:30:00-03:00"}), "status": "cancelled"},
        ], "nextPageToken": "pagina-2"},
        {"items": [_evento("recorrente-2", {"dateTime": "2026-11-07T09:00:00-03:00"},
                            {"dateTime": "2026-11-07T10:00:00-03:00"})]},
    ])
    monkeypatch.setattr(agenda, "_servico", lambda _: _Calendario(eventos))

    resultado = agenda.eventos_conta_periodo(Config(), conta, "inicio", "fim")

    assert [e["id"] for e in resultado] == ["reuniao", "dia-inteiro", "recorrente-2"]
    assert resultado[0]["corpo"] == "10:00–10:30"
    assert resultado[0]["chave"] == "fulano@example.com:reuniao"
    assert resultado[0]["participantes"] == ["Fulano"]
    assert resultado[0]["meet_url"] == "https://meet.google.com/abc"
    assert resultado[1]["corpo"] == "dia inteiro"
    assert resultado[1]["quando"].startswith("2026-11-06T00:00:00")
    assert eventos.parametros[0]["singleEvents"] is True
    assert eventos.parametros[0]["orderBy"] == "startTime"
    assert eventos.parametros[1]["pageToken"] == "pagina-2"


def test_permissao_negada_pede_nova_autorizacao(monkeypatch):
    monkeypatch.setattr(agenda, "_servico", lambda _: _Calendario(_EventosNegados()))

    with pytest.raises(RuntimeError, match="gmail-login"):
        agenda.eventos_conta_periodo(Config(), gmail.Conta("fulano@example.com", None), "inicio", "fim")


def test_checagem_do_servico_agenda_mede_latencia(monkeypatch):
    monkeypatch.setattr(agenda, "contas", lambda _: [gmail.Conta("fulano@example.com", None)])
    monkeypatch.setattr(agenda, "_servico", lambda _: _Calendario(None))

    resultado = agenda.checar(Config())

    assert resultado.estado == "ok"
    assert resultado.ms is not None


@pytest.fixture
def contexto(tmp_path):
    cfg = Config(dados={}, segredos={}, pasta_dados=tmp_path)
    estado = Estado(cfg.banco)
    ctx = Contexto(cfg, estado, ROTINAS["coletar_agenda"], estado.iniciar_execucao("coletar_agenda"))
    return cfg, estado, ctx


def _item(chave, titulo, quando, origem="fulano@example.com"):
    return {"chave": chave, "titulo": titulo, "corpo": "10:00–11:00", "origem": origem,
            "url": "", "quando": quando}


def test_coleta_substitui_a_fotografia_e_nao_duplica_eventos(contexto, monkeypatch):
    _, estado, ctx = contexto
    contas = [gmail.Conta("fulano@example.com", None)]
    monkeypatch.setattr(agenda, "contas", lambda _: contas)
    monkeypatch.setattr(agenda, "intervalo_dias", lambda _: ("inicio", "fim"))
    eventos = [_item("cal:1", "Reunião", "2026-11-06T10:00:00"),
               _item("cal:2", "Planejamento", "2026-11-07T09:00:00")]
    monkeypatch.setattr(agenda, "eventos_conta_periodo", lambda *args: eventos)
    estado.juntar_itens("agenda", [_item("antigo", "Evento antigo", "2026-11-01T10:00:00")])

    assert coletar_agenda.rodar(ctx) == "2 novos · 2 eventos"
    assert coletar_agenda.rodar(ctx) == "nada novo · 2 eventos"
    assert {i["chave"] for i in estado.itens(["agenda"], limite=10000)} == {"cal:1", "cal:2"}


def test_falha_de_uma_conta_preserva_eventos_existentes(contexto, monkeypatch):
    _, estado, ctx = contexto
    contas = [gmail.Conta("fulano@example.com", None), gmail.Conta("beltrana@example.com", None)]
    monkeypatch.setattr(agenda, "contas", lambda _: contas)
    monkeypatch.setattr(agenda, "intervalo_dias", lambda _: ("inicio", "fim"))
    antigo = _item("fulano:1", "Não perder", "2026-11-06T10:00:00")
    estado.juntar_itens("agenda", [antigo])

    def buscar(_, conta, inicio, fim):
        if conta.endereco == "fulano@example.com":
            raise RuntimeError("credencial temporariamente indisponível")
        return [_item("beltrana:2", "Nova reunião", "2026-11-06T11:00:00", conta.nome)]
    monkeypatch.setattr(agenda, "eventos_conta_periodo", buscar)

    resultado = coletar_agenda.rodar(ctx)
    assert resultado.estado == ATENCAO
    assert "credencial temporariamente indisponível" in resultado.resumo
    assert {i["chave"] for i in estado.itens(["agenda"], limite=10000)} == {"fulano:1", "beltrana:2"}


def test_agenda_do_dia_filtra_e_ordena_por_hora(contexto):
    _, estado, _ = contexto
    estado.juntar_itens("agenda", [
        _item("tarde", "À tarde", "2026-11-06T15:00:00"),
        _item("amanha", "Amanhã", "2026-11-07T09:00:00"),
        _item("manha", "De manhã", "2026-11-06T09:00:00"),
    ])

    texto = agenda_do_dia(estado, date(2026, 11, 6))

    assert texto.index("De manhã") < texto.index("À tarde")
    assert "Amanhã" not in texto


class _Hoje(date):
    @classmethod
    def today(cls):
        return date(2026, 11, 6)


def test_meu_dia_inclui_os_eventos_de_hoje_e_omite_os_de_amanha(contexto, monkeypatch, tmp_path):
    cfg, estado, _ = contexto
    cofre = tmp_path / "cofre"
    (cofre / "Diário").mkdir(parents=True)
    cfg.dados["obsidian"] = {"cofre": str(cofre), "pasta_diario": "Diário"}
    estado.juntar_itens("agenda", [
        _item("hoje", "Daily de hoje", "2026-11-06T09:00:00"),
        _item("amanha", "Reunião de amanhã", "2026-11-07T09:00:00"),
    ])
    ctx = Contexto(cfg, estado, ROTINAS["meu_dia"], estado.iniciar_execucao("meu_dia"))
    materiais = []
    monkeypatch.setattr(meu_dia, "date", _Hoje)
    monkeypatch.setattr(ia, "perguntar", lambda ctx, pedido, material: materiais.append(material) or "briefing")

    meu_dia.rodar(ctx)

    assert "Daily de hoje" in materiais[0]
    assert "Reunião de amanhã" not in materiais[0]


def test_dia_fechado_inclui_a_agenda_de_amanha(contexto, monkeypatch, tmp_path):
    cfg, estado, _ = contexto
    cofre = tmp_path / "cofre"
    (cofre / "Diário").mkdir(parents=True)
    cfg.dados["obsidian"] = {"cofre": str(cofre), "pasta_diario": "Diário"}
    estado.juntar_itens("agenda", [_item("amanha", "Reunião de amanhã", "2026-11-07T09:00:00")])
    ctx = Contexto(cfg, estado, ROTINAS["dia_fechado"], estado.iniciar_execucao("dia_fechado"))
    materiais = []
    monkeypatch.setattr(dia_fechado, "date", _Hoje)
    monkeypatch.setattr(git_local, "auditar_dia", lambda *args, **kwargs: [])
    monkeypatch.setattr(maquina, "resumo_do_dia", lambda *args: "")
    monkeypatch.setattr(ia, "perguntar", lambda ctx, pedido, material: materiais.append(material) or "fechamento")

    dia_fechado.rodar(ctx)

    assert "### Agenda de amanhã" in materiais[0]
    assert "Reunião de amanhã" in materiais[0]
