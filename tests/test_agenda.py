from datetime import date, datetime

import pytest

from automateum.config import Config
from automateum.nucleo.agendador import Contexto
from automateum.nucleo.estado import Estado
from automateum.nucleo.registro import ROTINAS
from automateum.rotinas import coletar_agenda
from automateum.servicos import agenda, gmail

HOJE = date(2026, 10, 24)


class _Resposta:
    def __init__(self, dados):
        self.dados = dados

    def execute(self):
        return self.dados


class _Eventos:
    def __init__(self, itens=None, erro=None):
        self.itens, self.erro = itens or [], erro

    def list(self, **kwargs):
        if self.erro:
            raise self.erro
        return _Resposta({"items": self.itens})


class _Calendario:
    def __init__(self, eventos):
        self._eventos = eventos

    def events(self):
        return self._eventos

    def calendarList(self):
        return self

    def get(self, **kwargs):
        return _Resposta({})


def _local(texto):
    return datetime.fromisoformat(texto).astimezone().replace(tzinfo=None)


def _conta():
    return gmail.Conta("ana@exemplo.com", None)


def _config(tmp_path):
    return Config(dados={}, segredos={}, pasta_dados=tmp_path)


def test_evento_com_horario_sai_no_fuso_desta_maquina(monkeypatch):
    evento = {"id": "e1", "summary": "Reunião de alinhamento", "location": "Sala 2",
              "start": {"dateTime": "2026-10-24T09:00:00-03:00"}, "end": {"dateTime": "2026-10-24T10:30:00-03:00"},
              "htmlLink": "https://calendar.google.com/e1"}
    monkeypatch.setattr(agenda, "_servico", lambda conta: _Calendario(_Eventos([evento])))

    [item] = agenda.eventos(_config(None), _conta(), HOJE)

    inicio, fim = _local("2026-10-24T09:00:00-03:00"), _local("2026-10-24T10:30:00-03:00")
    assert item["quando"] == inicio.isoformat(timespec="minutes")
    assert item["corpo"] == f"{inicio:%H:%M} às {fim:%H:%M} · Sala 2"
    assert item["titulo"] == "Reunião de alinhamento" and item["origem"] == "ana@exemplo.com"
    assert item["chave"] == "ana@exemplo.com:e1"


def test_dia_inteiro_e_cancelado(monkeypatch):
    eventos = [{"id": "d1", "summary": "Feriado", "start": {"date": "2026-10-24"}, "end": {"date": "2026-10-25"}},
               {"id": "c1", "summary": "Cancelada", "status": "cancelled",
                "start": {"dateTime": "2026-10-24T09:00:00-03:00"}, "end": {"dateTime": "2026-10-24T10:00:00-03:00"}}]
    monkeypatch.setattr(agenda, "_servico", lambda conta: _Calendario(_Eventos(eventos)))

    itens = agenda.eventos(_config(None), _conta(), HOJE)

    assert [(i["titulo"], i["corpo"], i["quando"]) for i in itens] == [("Feriado", "dia inteiro", "2026-10-24T00:00")]


def test_sem_autorizacao_da_agenda_pede_o_login_de_novo(monkeypatch):
    class _Negado(Exception):
        resp = type("R", (), {"status": 403})()

    monkeypatch.setattr(agenda, "_servico", lambda conta: _Calendario(_Eventos(erro=_Negado())))
    with pytest.raises(RuntimeError, match="gmail-login"):
        agenda.eventos(_config(None), _conta(), HOJE)


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    estado = Estado(tmp_path / "e.db")
    monkeypatch.setattr(gmail, "contas", lambda config: [_conta()])
    return Contexto(_config(tmp_path), estado, ROTINAS["coletar_agenda"], estado.iniciar_execucao("coletar_agenda"))


def _evento(id_, quando="2026-10-24T09:00:00-03:00"):
    return {"id": id_, "summary": f"Evento {id_}", "start": {"dateTime": quando},
            "end": {"dateTime": quando}}


def test_segunda_rodada_sem_evento_novo_diz_nada_novo(ctx, monkeypatch):
    monkeypatch.setattr(agenda, "_servico", lambda conta: _Calendario(_Eventos([_evento("1")])))
    assert coletar_agenda.rodar(ctx) == "1 novos · 1 eventos"
    assert coletar_agenda.rodar(ctx) == "nada novo · 1 eventos"

    monkeypatch.setattr(agenda, "_servico", lambda conta: _Calendario(_Eventos([_evento("1"), _evento("2")])))
    assert coletar_agenda.rodar(ctx) == "1 novos · 2 eventos"


def test_conta_que_falha_mantem_o_que_ja_tinha(ctx, monkeypatch):
    ana, beto = gmail.Conta("ana@exemplo.com", None), gmail.Conta("beto@exemplo.com", None)
    monkeypatch.setattr(gmail, "contas", lambda config: [ana, beto])

    class _Negado(Exception):
        resp = type("R", (), {"status": 403})()

    def ok_so_para_ana(conta):
        if conta is ana:
            return _Calendario(_Eventos([_evento("1")]))
        return _Calendario(_Eventos(erro=_Negado()))

    monkeypatch.setattr(agenda, "_servico", ok_so_para_ana)
    estado = ctx.estado
    estado.substituir_itens("agenda", [{"chave": "beto@exemplo.com:9", "titulo": "Do Beto", "corpo": "", "origem": "beto@exemplo.com",
                                        "url": "", "quando": "2026-10-24T11:00"}])
    resultado = coletar_agenda.rodar(ctx)

    assert "gmail-login" in resultado.resumo and resultado.estado == "atencao"
    assert sorted(i["titulo"] for i in estado.itens(["agenda"])) == ["Do Beto", "Evento 1"]
