"""Os projetos em que você está trabalhando: quais estão ativos e que prompts já foram deixados prontos.

Cada projeto vem do config (`[projetos.<id>]`: nome, github, ativo, rotulo, max_pendentes, modelo). O ativar/desativar
do mapa fica guardado no estado (cursor `projeto:<id>:ativo`) e vale mais que o `ativo` do config.
"""
from __future__ import annotations

import json

from ..config import Config

MODELO = (
    "Task #{numero}: {titulo}\n{url}\n\n{corpo}\n\n---\n"
    "Antes de alterar qualquer arquivo, leia o que for preciso e me proponha um plano. "
    "Não faça commit, push nem abra PR sem eu pedir."
)


def lista(config: Config) -> dict[str, dict]:
    return {pid: p for pid, p in config.secao("projetos").items() if isinstance(p, dict) and p.get("github")}


def ativo(config: Config, estado, pid: str) -> bool:
    guardado = estado.cursor(f"projeto:{pid}:ativo")
    if guardado:
        return guardado == "1"
    return bool(lista(config).get(pid, {}).get("ativo", False))


def definir(config: Config, estado, pid: str, ligado: bool) -> None:
    if pid not in lista(config):
        raise ValueError(f"projeto desconhecido: {pid}")
    estado.definir_cursor(f"projeto:{pid}:ativo", "1" if ligado else "0")


def preparados(estado, pid: str) -> dict[str, dict]:
    try:
        return json.loads(estado.cursor(f"prompts:{pid}") or "{}")
    except ValueError:
        return {}


def guardar_preparados(estado, pid: str, dados: dict[str, dict]) -> None:
    estado.definir_cursor(f"prompts:{pid}", json.dumps(dados, ensure_ascii=False))


def situacao(config: Config, estado) -> list[dict]:
    """O que o mapa mostra de cada projeto: se está ativo e os prompts que já ficaram prontos."""
    saida = []
    for pid, p in lista(config).items():
        prontos = [{"numero": int(n), **d} for n, d in sorted(preparados(estado, pid).items(), key=lambda kv: int(kv[0]))]
        saida.append({"id": pid, "nome": p.get("nome", pid), "github": p["github"], "ativo": ativo(config, estado, pid),
                      "prontos": prontos})
    return saida


def resumo(sit: list[dict]) -> str:
    ativos = [p["nome"] for p in sit if p["ativo"]]
    if not sit:
        return "nenhum projeto configurado"
    if not ativos:
        return "nenhum projeto ativo: ative um na gaveta"
    return "ativo: " + ", ".join(ativos)
