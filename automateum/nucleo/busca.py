"""Busca no que já foi coletado (a tabela `itens`): só lê o banco, não chama nenhum serviço."""
from __future__ import annotations

import unicodedata

from .saidas import FONTES

NOMES = {"obsidian": "Tasks do cofre", "github": "GitHub", "slack": "Slack", "gmail": "Gmail"}
_POR_FONTE = 20


def _normal(texto: str) -> str:
    """Sem acento e sem diferença de maiúscula: "reunião" acha "Reuniao"."""
    return "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c)).casefold()


def buscar(estado, consulta: str, por_fonte: int = _POR_FONTE) -> list[dict]:
    """Os itens que têm todas as palavras da consulta no título, no corpo ou na origem, agrupados por fonte,
    os mais recentes primeiro. Cada grupo traz no máximo `por_fonte` itens e o total achado."""
    palavras = _normal(consulta).split()
    if len("".join(palavras)) < 2:
        return []
    fontes = [f for f in NOMES if f in FONTES.values()]
    grupos: dict[str, list[dict]] = {}
    for item in estado.itens(fontes, limite=100_000):
        texto = _normal(" ".join(item.get(c) or "" for c in ("titulo", "corpo", "origem")))
        if all(p in texto for p in palavras):
            grupos.setdefault(item["fonte"], []).append(item)
    return [{"fonte": f, "nome": NOMES[f], "total": len(grupos[f]),
             "itens": [{c: i.get(c) or "" for c in ("titulo", "corpo", "origem", "url", "quando")}
                       for i in grupos[f][:por_fonte]]}
            for f in fontes if f in grupos]
