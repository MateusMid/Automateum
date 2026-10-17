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


def resumo_do_dia(medidas: list[dict], ligada_desde: str = "") -> str:
    """Uma linha para o fechamento do dia: média e pico de CPU e memória, e o disco livre. Vazio sem medições."""
    if not medidas:
        return ""

    def media_e_pico(campo: str) -> str:
        pico = max(medidas, key=lambda m: m[campo])
        media = round(sum(m[campo] for m in medidas) / len(medidas))
        return f"média {media}% (pico {pico[campo]}% às {pico['quando'][11:16]})"

    def livre_e_minimo(livres: list[int]) -> str:
        return f"{livres[-1]} GB" + (f" (mínimo do dia {min(livres)} GB)" if min(livres) != livres[-1] else "")

    nomes = sorted({n for m in medidas for n in (m.get("discos") or {})})
    if nomes:  # um item por disco; medições antigas, de um disco só, caem no ramo de baixo
        disco = "disco livre " + " · ".join(
            f"{n} {livre_e_minimo([m['discos'][n] for m in medidas if n in (m.get('discos') or {})])}"
            for n in nomes)
    else:
        disco = "disco livre " + livre_e_minimo([m["disco_livre_gb"] for m in medidas])
    partes = [f"CPU {media_e_pico('cpu')}", f"memória {media_e_pico('memoria')}", disco]
    if ligada_desde:
        partes.append(f"ligada desde {ligada_desde}")
    n = len(medidas)
    return f"**Máquina:** {' · '.join(partes)} ({n} medição)." if n == 1 else \
        f"**Máquina:** {' · '.join(partes)} ({n} medições)."


def _nome_do_disco(texto: str) -> str:
    """'c', 'C:' ou 'C:\\' -> 'C:'; '/' continua '/'."""
    texto = texto.strip().rstrip("\\/")
    return texto.upper().rstrip(":") + ":" if texto else "/"


def volumes(permitidos: list[str] | None = None) -> list[dict]:
    """Os discos fixos da máquina (sem CD, pendrive ou rede), ou só os de `permitidos` (['C:', 'D:'])."""
    if platform.system() == "Windows":
        pontos = [p.mountpoint for p in psutil.disk_partitions(all=False) if "fixed" in p.opts]
    else:
        pontos = ["/"]
    quer = {_nome_do_disco(d) for d in permitidos} if permitidos else None
    itens = []
    for ponto in pontos:
        nome = _nome_do_disco(ponto) if platform.system() == "Windows" else "/"
        if quer and nome not in quer:
            continue
        try:
            uso = psutil.disk_usage(ponto)
        except OSError:  # disco que sumiu ou sem permissão: não derruba a leitura da máquina
            continue
        itens.append({"nome": nome, "livre_gb": round(uso.free / 2**30), "total_gb": round(uso.total / 2**30),
                      "usado_pct": round(uso.percent)})
    return itens


def ler(discos: list[str] | None = None) -> Checagem:
    cpu = psutil.cpu_percent(interval=0.3)
    memoria = psutil.virtual_memory().percent
    # Lista errada em [maquina] discos não pode deixar a máquina sem disco nenhum: cai para todos os fixos.
    lista = volumes(discos) or volumes()
    principal = lista[0]["livre_gb"] if lista else 0
    meta = {
        "nome": platform.node(),
        "sistema": f"{platform.system()} {platform.release()}",
        "ip": _ip_local(),
        "ligada_desde": datetime.fromtimestamp(psutil.boot_time()).strftime("%d/%m %H:%M"),
        "cpu": round(cpu), "memoria": round(memoria),
        "disco_livre_gb": principal,  # o primeiro disco; os painéis antigos só conhecem este campo
        "discos": lista,
    }
    problemas = []
    if memoria >= 90:
        problemas.append(f"memória em {memoria:.0f}%")
    for d in lista:
        if d["usado_pct"] >= 92:
            problemas.append(f"disco {d['nome']} com só {d['livre_gb']} GB livres")
    if problemas:
        return Checagem(ATENCAO, "; ".join(problemas), meta=meta)
    livres = " · ".join(f"{d['nome']} {d['livre_gb']} GB" for d in lista)
    return Checagem(OK, f"CPU {cpu:.0f}% · memória {memoria:.0f}%" + (f" · {livres} livres" if livres else ""), meta=meta)
