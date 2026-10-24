"""Pausa dos resumos (folga, feriado, férias): as rotinas que escrevem os textos do dia não rodam até uma data.

As coletas seguem guardando o que chega, e na volta o briefing já tem tudo. A data fica no banco
e sobrevive a um reinício; passado o dia, a pausa acaba sozinha.
"""
from __future__ import annotations

from datetime import date, timedelta

RESUMOS = ("meu_dia", "dia_fechado", "semana_fechada", "resumo_mensagens")
MAXIMO_DIAS = 90
_CURSOR = "pausa:ate"


def ate(estado, hoje: date | None = None) -> date | None:
    """O último dia da pausa, ou None se não há pausa (ou se ela já passou)."""
    try:
        dia = date.fromisoformat(estado.cursor(_CURSOR) or "")
    except ValueError:
        return None
    return dia if dia >= (hoje or date.today()) else None


def pausar(estado, dia: date, hoje: date | None = None) -> None:
    """Pausa até `dia`, inclusive."""
    hoje = hoje or date.today()
    if dia < hoje:
        raise ValueError("essa data já passou")
    if dia > hoje + timedelta(days=MAXIMO_DIAS):
        raise ValueError(f"no máximo {MAXIMO_DIAS} dias de pausa")
    estado.definir_cursor(_CURSOR, dia.isoformat())


def retomar(estado) -> None:
    estado.definir_cursor(_CURSOR, "")


def motivo(estado, rotina_id: str) -> str | None:
    if rotina_id in RESUMOS and (dia := ate(estado)):
        return f"resumos pausados até {dia:%d/%m}; voltam no dia {dia + timedelta(days=1):%d/%m}"
    return None


def situacao(estado) -> dict:
    """O que a gaveta das rotinas de resumo mostra."""
    dia = ate(estado)
    return {"ate": dia.isoformat() if dia else "", "hoje": date.today().isoformat(), "maximo_dias": MAXIMO_DIAS}
