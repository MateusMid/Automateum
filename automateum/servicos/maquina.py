"""Leitura da máquina local (coluna 01 do painel)."""
from __future__ import annotations

import platform
import socket
from datetime import datetime

import psutil

from ..nucleo.registro import ATENCAO, OK, Checagem


def _ip_local() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # UDP: não envia nada, só escolhe a interface
            return s.getsockname()[0]
    except OSError:
        return "sem rede"


def ler() -> Checagem:
    cpu = psutil.cpu_percent(interval=0.3)
    memoria = psutil.virtual_memory().percent
    disco = psutil.disk_usage("C:\\" if platform.system() == "Windows" else "/")
    livre_gb = disco.free / 2**30
    meta = {
        "nome": platform.node(),
        "sistema": f"{platform.system()} {platform.release()}",
        "ip": _ip_local(),
        "ligada_desde": datetime.fromtimestamp(psutil.boot_time()).strftime("%d/%m %H:%M"),
        "cpu": round(cpu), "memoria": round(memoria), "disco_livre_gb": round(livre_gb),
    }
    problemas = []
    if memoria >= 90:
        problemas.append(f"memória em {memoria:.0f}%")
    if disco.percent >= 92:
        problemas.append(f"disco com só {livre_gb:.0f} GB livres")
    if problemas:
        return Checagem(ATENCAO, "; ".join(problemas), meta=meta)
    return Checagem(OK, f"CPU {cpu:.0f}% · memória {memoria:.0f}% · {livre_gb:.0f} GB livres", meta=meta)
