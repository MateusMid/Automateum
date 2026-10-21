"""Qual IA escreve os resumos: o Claude, ou o Copilot, que também entra quando o outro falha.

O motor ativo vem do botão do mapa (cursor `ia:motor`) e, sem ele, de `[ia] motor` no config; o padrão é o Claude.
Se o ativo falha, a pergunta vai para o outro e a rodada registra isso no log.
Cada tentativa fica registrada no banco (motor, rotina, tempo, se respondeu, se foi pela reserva), sem o texto.
"""
from __future__ import annotations

import json
import subprocess
import time
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
            "reserva_pronta": MOTORES[r].configurado(config) is None, "ultimo": ultimo, "uso": estado.uso_da_ia()}


def reserva_seguidas_para_avisar(config: Config) -> int:
    return int(config.secao("ia").get("aviso_reserva_seguidas", 3))


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
        de_reserva = motor != principal
        inicio = time.perf_counter()
        try:
            texto = modulo.perguntar(config, instrucao, dados)
        except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as e:
            erros.append(f"{NOMES[motor]}: {e}")
            estado.registrar_chamada_ia(ctx.rotina.id, motor, _ms(inicio), False, de_reserva)
            continue
        estado.registrar_chamada_ia(ctx.rotina.id, motor, _ms(inicio), True, de_reserva)
        estado.definir_cursor(_ULTIMO, json.dumps({
            "motor": motor, "reserva": de_reserva, "quando": datetime.now().isoformat(timespec="seconds"),
            "motivo": erros[0] if de_reserva else ""}, ensure_ascii=False))
        if de_reserva:
            ctx.log(f"{NOMES[principal]} não respondeu ({erros[0]}); o texto foi feito pelo {NOMES[motor]}")
            # avisa uma vez, quando a sequência chega no limite, e não a cada resposta depois dele
            if (n := estado.reserva_seguidas()) == reserva_seguidas_para_avisar(config):
                ctx.avisar(f"o {NOMES[motor]} respondeu no lugar do {NOMES[principal]} {n} vezes seguidas: "
                           f"veja o {NOMES[principal]} ({erros[0]})")
        return texto
    raise RuntimeError("nenhuma IA respondeu: " + " | ".join(erros))


def _ms(inicio: float) -> int:
    return round((time.perf_counter() - inicio) * 1000)
