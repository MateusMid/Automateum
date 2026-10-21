"""Leitura e escrita no cofre do Obsidian.

A escrita é restrita à pasta própria do Automateum e a blocos delimitados dentro das notas do diário e das
notas do dia das pastas de reunião configuradas (`[reunioes.grupos]`). O que estiver fora do bloco nunca é alterado.
"""
from __future__ import annotations

import os
import re
import time
from datetime import date
from pathlib import Path

from ..config import Config
from ..nucleo.registro import FALHA, OK, Checagem, registrar_servico

_TASK = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\[ \]\s+(.*\S)")
_CERCA = re.compile(r"^\s*(```|~~~)")


def _secao(config: Config) -> dict:
    return config.secao("obsidian")


def configurado(config: Config) -> str | None:
    if not _secao(config).get("cofre"):
        return "defina obsidian.cofre no config.toml"
    if not config.cofre.is_dir():
        return f"cofre não encontrado em {config.cofre}"
    return None


def notas(config: Config) -> list[Path]:
    ignorar = set(_secao(config).get("ignorar", [".obsidian", ".trash"]))
    saida = []
    for raiz, pastas, arquivos in os.walk(config.cofre):
        relativo = Path(raiz).relative_to(config.cofre)
        pastas[:] = [p for p in pastas if p not in ignorar and (relativo / p).as_posix() not in ignorar]
        saida += [Path(raiz) / a for a in arquivos if a.lower().endswith(".md")]
    return saida


def checar(config: Config) -> Checagem:
    inicio = time.perf_counter()
    try:
        total = len(notas(config))
    except OSError as e:
        return Checagem(FALHA, f"não consegui ler o cofre: {e}")
    return Checagem(OK, f"{total} notas em {config.cofre.name}", round((time.perf_counter() - inicio) * 1000))


def extrair_tasks(texto: str) -> list[tuple[int, str]]:
    """Checkboxes abertos de uma nota, como (número da linha, texto). Ignora blocos de código."""
    saida, em_codigo = [], False
    for n, linha in enumerate(texto.splitlines(), 1):
        if _CERCA.match(linha):
            em_codigo = not em_codigo
        elif not em_codigo and (m := _TASK.match(linha)):
            saida.append((n, m[1]))
    return saida


def tasks_abertas(config: Config) -> list[dict]:
    saida = []
    for nota in notas(config):
        relativo = nota.relative_to(config.cofre).as_posix()
        for linha, texto in extrair_tasks(nota.read_text(encoding="utf-8", errors="replace")):
            saida.append({"chave": f"{relativo}:{linha}", "titulo": texto, "origem": relativo,
                          "quando": date.fromtimestamp(nota.stat().st_mtime).isoformat()})
    return saida


def ler_nota(config: Config, relativo: str) -> str:
    caminho = _dentro(config.cofre, config.cofre / relativo)
    return caminho.read_text(encoding="utf-8", errors="replace") if caminho.is_file() else ""


def notas_recentes(config: Config, pasta: str, quantas: int = 3) -> list[tuple[str, str]]:
    """As notas modificadas por último numa pasta do cofre, como (nome, texto)."""
    base = _dentro(config.cofre, config.cofre / pasta)
    if not base.is_dir():
        return []
    arquivos = sorted(base.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:quantas]
    return [(a.stem, a.read_text(encoding="utf-8", errors="replace")) for a in arquivos]


# --- escrita

def _dentro(base: Path, caminho: Path) -> Path:
    base, caminho = base.resolve(), caminho.resolve()
    if base != caminho and base not in caminho.parents:
        raise PermissionError(f"{caminho} está fora de {base}")
    return caminho


def _gravar(caminho: Path, dados: bytes) -> None:
    """Grava num temporário e renomeia, para a sincronização do cofre nunca ver um arquivo pela metade."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(f".automateum-{os.getpid()}-{caminho.name}.tmp")
    temporario.write_bytes(dados)
    os.replace(temporario, caminho)


def com_bloco(original: str, nome: str, conteudo: str) -> str:
    """Devolve `original` com o bloco `nome` criado ou substituído; o resto fica intacto."""
    quebra = "\r\n" if "\r\n" in original else "\n"
    inicio, fim = f"%% automateum:{nome}:inicio %%", f"%% automateum:{nome}:fim %%"
    corpo = quebra.join(conteudo.strip().splitlines())
    bloco = f"{inicio}{quebra}{corpo}{quebra}{fim}"
    i, f = original.find(inicio), original.find(fim)
    if i != -1 and f > i:
        return original[:i] + bloco + original[f + len(fim):]
    if not original.strip():
        return bloco + quebra
    separador = quebra if original.endswith(("\n", "\r\n")) else quebra * 2
    return original + separador + bloco + quebra


def escrever_bloco(config: Config, relativo: str, nome: str, conteudo: str) -> Path:
    """Cria ou atualiza o bloco `nome` na nota `relativo` do cofre (que é criada, se não existir)."""
    caminho = _dentro(config.cofre, config.cofre / relativo)
    # newline="" preserva as quebras de linha originais na leitura.
    original = caminho.open(encoding="utf-8", newline="").read() if caminho.exists() else ""
    _gravar(caminho, com_bloco(original, nome, conteudo).encode("utf-8"))
    return caminho


def escrever_bloco_diario(config: Config, nome: str, conteudo: str, dia: date | None = None) -> Path:
    """Cria ou atualiza o bloco `nome` na nota do diário de `dia` (hoje, se omitido)."""
    pasta = _secao(config).get("pasta_diario", "Diário")
    return escrever_bloco(config, f"{pasta}/{(dia or date.today()).isoformat()}.md", nome, conteudo)


def escrever_proprio(config: Config, relativo: str, conteudo: str, acrescentar: bool = False) -> Path:
    """Grava um arquivo dentro da pasta do Automateum no cofre."""
    pasta = config.cofre / _secao(config).get("pasta_automateum", "Automateum")
    caminho = _dentro(pasta, pasta / relativo)
    if acrescentar and caminho.exists():
        conteudo = caminho.read_text(encoding="utf-8").rstrip() + "\n\n" + conteudo
    _gravar(caminho, conteudo.rstrip().encode("utf-8") + b"\n")
    return caminho


registrar_servico("obsidian", "Obsidian", checar, configurado, "Cofre local de notas: tasks, diário e reuniões.")
