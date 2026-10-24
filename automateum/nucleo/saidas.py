"""O resultado de cada rotina numa nota só, em Automateum/Saídas/Rotinas/<rotina>.md no cofre.

A nota é reescrita a cada rodada com o último resultado: estado, resumo, texto gerado, log e itens.
Todo texto novo também é guardado, com a hora, em Rotinas/<rotina>/AAAA-MM-DD.md: o histórico dos dias.
O painel mostra o mesmo e tem um link que abre a nota no Obsidian.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from urllib.parse import quote

from ..config import Config
from ..servicos import obsidian
from .estado import Estado

# De qual fonte de itens cada rotina é dona (a lista que o painel mostra e a nota repete).
FONTES = {"tasks_obsidian": "obsidian", "tasks_github": "github", "coletar_slack": "slack",
          "coletar_gmail": "gmail", "coletar_agenda": "agenda"}
# Mensagens de outras pessoas não são despejadas no cofre: a nota só conta quantas há.
SO_CONTAGEM = {"coletar_slack", "coletar_gmail"}
_ITENS_NA_NOTA = 60
_REESCREVER_APOS_S = 3600  # mesmo resultado: reescreve no máximo de hora em hora, para não agitar o cofre


def _relativo(rotina_id: str) -> str:
    return f"Rotinas/{rotina_id}.md"


def _caminho(config: Config, rotina_id: str):
    pasta = config.cofre / config.secao("obsidian").get("pasta_automateum", "Automateum")
    return pasta / _relativo(rotina_id)


def nota(config: Config, rotina_id: str) -> dict | None:
    """Onde está a nota da rotina e o link para abri-la no Obsidian; None se ainda não existe."""
    if obsidian.configurado(config) or not _caminho(config, rotina_id).exists():
        return None
    pasta = config.secao("obsidian").get("pasta_automateum", "Automateum")
    arquivo = f"{pasta}/{_relativo(rotina_id)}"
    uri = f"obsidian://open?vault={quote(config.cofre.name)}&file={quote(arquivo.removesuffix('.md'), safe='/')}"
    return {"arquivo": arquivo, "obsidian": uri, "rotina": rotina_id}


def _linha_item(i: dict) -> str:
    titulo = " ".join((i.get("titulo") or "").split())[:140]
    titulo = f"[{titulo}]({i['url']})" if i.get("url") else titulo
    detalhe = " · ".join(p for p in (i.get("origem"), (i.get("quando") or "")[:10]) if p)
    return f"- {titulo}" + (f" — {detalhe}" if detalhe else "")


def _pasta_historico(config: Config, rotina_id: str):
    return _caminho(config, rotina_id).with_suffix("")


def _guardar_no_historico(config: Config, rotina, texto: str) -> None:
    """Acrescenta o texto novo ao arquivo do dia (Rotinas/<rotina>/AAAA-MM-DD.md), um bloco por rodada."""
    agora = datetime.now()
    relativo = f"Rotinas/{rotina.id}/{agora:%Y-%m-%d}.md"
    bloco = f"## {agora:%H:%M}\n\n{texto.strip()}"
    if not (_pasta_historico(config, rotina.id) / f"{agora:%Y-%m-%d}.md").exists():
        bloco = f"# {rotina.nome} · {agora:%d/%m/%Y}\n\n" + bloco
    obsidian.escrever_proprio(config, relativo, bloco, acrescentar=True)


def _dias_guardados(config: Config, rotina_id: str, limite: int = 14) -> list[str]:
    pasta = _pasta_historico(config, rotina_id)
    return sorted((a.stem for a in pasta.glob("????-??-??.md")), reverse=True)[:limite] if pasta.is_dir() else []


def _conteudo(config: Config, estado: Estado, rotina, exec_id: int, status: str, resumo: str, texto: str) -> str:
    execucao = estado.execucao(exec_id) or {}
    agora = datetime.now().isoformat(timespec="seconds")
    partes = [f"---\nrotina: {rotina.id}\nestado: {status}\natualizado: {agora}\n---",
              f"# {rotina.nome}", f"**{status}** · {agora[:16].replace('T', ' ')} · {resumo or 'sem resumo'}"]
    if rotina.descricao:
        partes.append(rotina.descricao)
    if texto.strip():
        partes.append(texto.strip())
    elif ultimo := ultimo_texto(estado, rotina.id):
        quando = datetime.fromisoformat(ultimo["quando"]).strftime("%d/%m %H:%M")
        partes.append(f"> Último texto gerado, em {quando}. A rodada de agora não trouxe nada novo.\n\n"
                      + ultimo["conteudo"])
    if dias := _dias_guardados(config, rotina.id):
        base = config.secao("obsidian").get("pasta_automateum", "Automateum")
        partes.append("## Histórico dos dias\n" + "\n".join(f"- [[{base}/Rotinas/{rotina.id}/{d}|{d}]]" for d in dias))
    fonte = FONTES.get(rotina.id)
    if fonte and rotina.id in SO_CONTAGEM:
        partes.append(f"## Itens\n{estado.contar_itens(fonte)} guardados. O conteúdo fica no painel, não no cofre.")
    elif fonte:
        itens = estado.itens([fonte], limite=_ITENS_NA_NOTA + 1)
        if itens:
            linhas = [_linha_item(i) for i in itens[:_ITENS_NA_NOTA]]
            if len(itens) > _ITENS_NA_NOTA:
                linhas.append("- (há mais itens no painel)")
            partes.append("## Itens\n" + "\n".join(linhas))
    if (execucao.get("log") or "").strip():
        partes.append("## Log da última rodada\n```\n" + execucao["log"].strip() + "\n```")
    return "\n\n".join(partes)


def ultimo_texto(estado: Estado, rotina_id: str) -> dict | None:
    """O último texto que a rotina gerou ({quando, conteudo}), mesmo que as rodadas seguintes não tragam nada novo."""
    bruto = estado.cursor(f"texto:{rotina_id}")
    try:
        d = json.loads(bruto) if bruto else None
    except ValueError:
        return None
    return d if isinstance(d, dict) and d.get("conteudo") else None


def gravar(config: Config, estado: Estado, rotina, exec_id: int, status: str, resumo: str, texto: str = "") -> None:
    """Escreve a nota da rotina. Sem cofre configurado não faz nada; erro aqui nunca derruba a rodada."""
    if texto.strip():
        # Rotinas de hora em hora quase sempre voltam com "nada novo": sem guardar, esse resultado vazio
        # apagaria o último resumo de verdade, tanto da nota quanto da gaveta do mapa.
        estado.definir_cursor(f"texto:{rotina.id}", json.dumps(
            {"quando": datetime.now().isoformat(timespec="seconds"), "conteudo": texto.strip()}, ensure_ascii=False))
    if obsidian.configurado(config):
        return
    if texto.strip():
        _guardar_no_historico(config, rotina, texto)
    assinatura = hashlib.sha1(f"{status}|{resumo}|{texto}".encode()).hexdigest()
    chave = f"nota:{rotina.id}"
    anterior, _, quando = estado.cursor(chave).partition("|")
    if anterior == assinatura and quando and time.time() - float(quando) < _REESCREVER_APOS_S:
        return
    obsidian.escrever_proprio(config, _relativo(rotina.id),
                              _conteudo(config, estado, rotina, exec_id, status, resumo, texto))
    estado.definir_cursor(chave, f"{assinatura}|{time.time()}")
