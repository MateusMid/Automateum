"""Catálogo de serviços e rotinas. O painel é desenhado a partir do que está registrado aqui."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# Estados usados em todo o sistema.
OK, ATENCAO, FALHA, PARADO, RODANDO, ESPERA = "ok", "atencao", "falha", "parado", "rodando", "espera"


@dataclass
class Checagem:
    estado: str
    detalhe: str = ""
    ms: int | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class Resultado:
    """Retorno opcional de uma rotina; devolver só uma string equivale a Resultado(OK, texto)."""
    estado: str
    resumo: str = ""


class Atencao(Exception):
    """A rotina terminou, mas algo merece atenção."""


@dataclass
class Servico:
    id: str
    nome: str
    descricao: str
    checar: Callable
    # Devolve o motivo quando falta configuração; None quando está pronto.
    configurado: Callable


@dataclass
class Rotina:
    id: str
    nome: str
    frente: str
    quando: str
    func: Callable
    usa: list[str] = field(default_factory=list)
    entrega: list[str] = field(default_factory=list)
    descricao: str = ""


SERVICOS: dict[str, Servico] = {}
ROTINAS: dict[str, Rotina] = {}


def registrar_servico(id: str, nome: str, checar: Callable, configurado: Callable, descricao: str = "") -> None:
    SERVICOS[id] = Servico(id, nome, descricao, checar, configurado)


def rotina(id: str, nome: str, frente: str, quando: str, usa: list[str] | None = None,
           entrega: list[str] | None = None):
    """Registra uma rotina. `quando`: "cada 15m", "cron: 30 8 * * mon-fri" ou "nunca"."""
    def decorador(func: Callable) -> Callable:
        ROTINAS[id] = Rotina(id, nome, frente, quando, func, usa or [], entrega or [],
                             (func.__doc__ or "").strip())
        return func
    return decorador


_UNIDADES = {"s": "seconds", "m": "minutes", "h": "hours"}
_CADA = re.compile(r"^cada\s+(\d+)\s*([smh])$")


def gatilho(quando: str):
    """Converte o texto de horário num gatilho do APScheduler; None para "nunca"."""
    quando = quando.strip().lower()
    if quando == "nunca":
        return None
    if m := _CADA.match(quando):
        return IntervalTrigger(**{_UNIDADES[m[2]]: int(m[1])})
    if quando.startswith("cron:"):
        # Dias da semana por nome (mon-fri): no APScheduler o número 0 é segunda, não domingo.
        return CronTrigger.from_crontab(quando[5:].strip())
    raise ValueError(f"horário inválido: {quando!r}")


_DIAS = {"mon-fri": "seg a sex", "*": "", "sun": "domingo", "mon": "segunda", "sat": "sábado"}


def quando_texto(quando: str) -> str:
    quando = quando.strip().lower()
    if quando == "nunca":
        return "desligada"
    if m := _CADA.match(quando):
        n, u = int(m[1]), m[2]
        nomes = {"s": ("segundo", "segundos"), "m": ("min", "min"), "h": ("hora", "horas")}[u]
        return f"a cada {n} {nomes[0] if n == 1 else nomes[1]}"
    if quando.startswith("cron:"):
        partes = quando[5:].split()
        if len(partes) == 5:
            minuto, hora, _, _, dia = partes
            dias = _DIAS.get(dia, dia)
            if minuto.isdigit() and hora.isdigit():
                texto = f"{int(hora):02d}:{int(minuto):02d}"
            elif minuto.isdigit() and re.fullmatch(r"\d+-\d+", hora):
                ini, fim = hora.split("-")
                texto = "de hora em hora" if minuto == "0" else f"todo minuto {minuto}"
                texto += f", {ini}h às {fim}h"
            else:
                return quando[5:].strip()
            return f"{texto}, {dias}" if dias else texto
    return quando
