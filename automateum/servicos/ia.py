"""Qual IA escreve os resumos: o Claude, ou o Copilot, que também entra quando o outro falha.

O motor ativo vem do botão do mapa (cursor `ia:motor`) e, sem ele, de `[ia] motor` no config; o padrão é o Claude.
Se o ativo falha, a pergunta vai para o outro e a rodada registra isso no log.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime

from ..config import Config
from . import claude, copilot

MOTORES = {"claude": claude, "copilot": copilot}
NOMES = {"claude": "Claude", "copilot": "Copilot"}
_CURSOR, _ULTIMO = "ia:motor", "ia:ultimo"


def ativo(config: Config, estado) -> str:
    escolhido = estado.cursor(_CURSOR) or config.secao("ia").get("motor", "claude")
    return escolhido if escolhido in MOTORES else "claude"


def definir(estado, motor: str) -> None:
    if motor not in MOTORES:
        raise ValueError(f"motor desconhecido: {motor}")
    estado.definir_cursor(_CURSOR, motor)


def reserva(motor: str) -> str:
    return "copilot" if motor == "claude" else "claude"


def situacao(config: Config, estado) -> dict:
    """O que o mapa mostra: o motor em uso, o outro, se o outro está instalado e o último uso."""
    a = ativo(config, estado)
    r = reserva(a)
    try:
        ultimo = json.loads(estado.cursor(_ULTIMO) or "null")
    except ValueError:
        ultimo = None
    return {"ativo": a, "ativo_nome": NOMES[a], "reserva": r, "reserva_nome": NOMES[r],
            "reserva_pronta": MOTORES[r].configurado(config) is None, "ultimo": ultimo}


def perguntar(ctx, instrucao: str, dados: str = "") -> str:
    """Pergunta ao motor ativo; se ele falhar (ou não existir), tenta o outro. Só falha se os dois falharem."""
    config, estado = ctx.config, ctx.estado
    principal = ativo(config, estado)
    erros = []
    for motor in (principal, reserva(principal)):
        modulo = MOTORES[motor]
        if falta := modulo.configurado(config):
            erros.append(f"{NOMES[motor]}: {falta}")
            continue
        try:
            texto = modulo.perguntar(config, instrucao, dados)
        except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as e:
            erros.append(f"{NOMES[motor]}: {e}")
            continue
        de_reserva = motor != principal
        estado.definir_cursor(_ULTIMO, json.dumps({
            "motor": motor, "reserva": de_reserva, "quando": datetime.now().isoformat(timespec="seconds"),
            "motivo": erros[0] if de_reserva else ""}, ensure_ascii=False))
        if de_reserva:
            ctx.log(f"{NOMES[principal]} não respondeu ({erros[0]}); o texto foi feito pelo {NOMES[motor]}")
        return texto
    raise RuntimeError("nenhuma IA respondeu: " + " | ".join(erros))
