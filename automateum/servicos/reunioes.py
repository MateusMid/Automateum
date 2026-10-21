"""Transcrições de reunião do Gutenberg, a extensão do Chrome que salva a legenda da reunião em .md.

O Chrome só deixa a extensão salvar dentro de Downloads (em `Downloads/Gutenberg/AAAA-MM/DD/`). O Automateum
traz cada arquivo de lá para a pasta fixa `[reunioes] pasta`, com as mesmas subpastas, e lê dali.
Um arquivo repetido (o "Baixar" no meio da reunião vira "nome (1).md") é a mesma reunião: vale o maior.
Os grupos (`[reunioes.grupos.<id>]`, com `pessoas` e `pasta`) dizem de quem é a reunião pelos nomes de quem falou.
"""
from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

from ..config import Config
from ..nucleo.registro import FALHA, OK, Checagem, registrar_servico

_FALA = re.compile(r"^\*\*(\d{2}:\d{2})(?::\d{2})? — (.+?):\*\*", re.M)
_COPIA = re.compile(r" \(\d+\)$")
_DIA = re.compile(r"(\d{4}-\d{2})[\\/](\d{2})$")


def _secao(config: Config) -> dict:
    return config.secao("reunioes")


def pasta(config: Config) -> Path:
    return Path(_secao(config).get("pasta", ""))


def entrada(config: Config) -> Path:
    return Path(_secao(config).get("entrada") or Path.home() / "Downloads" / "Gutenberg")


def configurado(config: Config) -> str | None:
    if not _secao(config).get("pasta"):
        return "defina reunioes.pasta no config.local.toml (a pasta fixa das transcrições)"
    return None


def checar(config: Config) -> Checagem:
    try:
        pasta(config).mkdir(parents=True, exist_ok=True)
        total = len(transcricoes(config))
    except OSError as e:
        return Checagem(FALHA, f"não consegui usar {pasta(config)}: {e}")
    return Checagem(OK, f"{total} reuniões em {pasta(config)}")


def trazer(config: Config) -> list[Path]:
    """Move as transcrições de Downloads para a pasta fixa. Igual a uma que já está lá: só apaga a de Downloads."""
    origem, destino_base, movidas = entrada(config), pasta(config), []
    if not origem.is_dir():
        return movidas
    for arquivo in sorted(origem.rglob("*.md")):
        destino = destino_base / arquivo.relative_to(origem)
        if destino.exists() and destino.read_bytes() == arquivo.read_bytes():
            arquivo.unlink()
            continue
        n = 2
        while destino.exists():
            destino = destino.with_name(f"{arquivo.stem} ({n}){arquivo.suffix}")
            n += 1
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(arquivo, destino)
        movidas.append(destino)
    return movidas


def ler(arquivo: Path) -> dict:
    texto = arquivo.read_text(encoding="utf-8", errors="replace")
    falas = _FALA.findall(texto)
    titulo = next((l[2:].strip() for l in texto.splitlines() if l.startswith("# ")), arquivo.stem)
    return {"texto": texto, "titulo": titulo, "falas": len(falas), "inicio": falas[0][0] if falas else "",
            "quem": sorted({q for _, q in falas})}


def _palavra(termo: str) -> re.Pattern:
    return re.compile(rf"\b{re.escape(termo.casefold())}\b")


def grupo(config: Config, quem: list[str], texto: str = "", inicio: str = "") -> tuple[str, dict] | None:
    """O primeiro grupo da reunião. É dele quando todos que falaram (fora "Eu") estão em `pessoas`, pelo nome
    inteiro ou por uma palavra dele; ou quando o texto cita os termos de `palavras` pelo menos `mencoes` vezes.
    Nunca é dele se a reunião começou (`inicio`, "HH:MM") numa das `horas_fora`."""
    outros = [q.casefold() for q in quem if q.casefold() != "eu"]
    texto = texto.casefold()
    for gid, g in (_secao(config).get("grupos") or {}).items():
        if inicio and int(inicio[:2]) in g.get("horas_fora", []):
            continue
        pessoas = [_palavra(p) for p in g.get("pessoas", [])]
        if outros and all(any(p.search(f) for p in pessoas) for f in outros):
            return gid, g
        citacoes = sum(len(_palavra(t).findall(texto)) for t in g.get("palavras", []))
        if citacoes and citacoes >= int(g.get("mencoes", 2)):
            return gid, g
    return None


def transcricoes(config: Config, parada_ha: float = 0) -> list[dict]:
    """Uma por reunião, a do maior arquivo: chave, arquivo, dia (AAAA-MM-DD) e tamanho.
    `parada_ha`: ignora o que mudou há menos desses segundos (o Chrome ainda pode estar gravando)."""
    base, grupos = pasta(config), {}
    if not base.is_dir():
        return []
    for arquivo in base.rglob("*.md"):
        if parada_ha and time.time() - arquivo.stat().st_mtime < parada_ha:
            continue
        relativo = arquivo.relative_to(base).with_suffix("")
        chave = (relativo.parent / _COPIA.sub("", relativo.name)).as_posix()
        if chave not in grupos or arquivo.stat().st_size > grupos[chave].stat().st_size:
            grupos[chave] = arquivo
    saida = []
    for chave, arquivo in sorted(grupos.items()):
        dia = _DIA.search(arquivo.parent.as_posix())
        saida.append({"chave": chave, "arquivo": arquivo, "tamanho": arquivo.stat().st_size,
                      "dia": f"{dia[1]}-{dia[2]}" if dia else time.strftime("%Y-%m-%d", time.localtime(arquivo.stat().st_mtime))})
    return saida


registrar_servico("reunioes", "Reuniões (Gutenberg)", checar, configurado,
                  "Transcrições salvas pela extensão Gutenberg, trazidas de Downloads para uma pasta fixa.")
