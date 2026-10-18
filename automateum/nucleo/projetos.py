"""Os projetos em que você está trabalhando: quais estão ativos e que prompts já foram deixados prontos.

Só as issues atribuídas a você viram prompt sozinhas; as outras esperam o "Começar" da gaveta.
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


def aceitas(estado, pid: str) -> list[int]:
    """Issues em que você clicou "Começar": viram prompt mesmo sem estar atribuídas a você."""
    try:
        return [int(n) for n in json.loads(estado.cursor(f"aceitas:{pid}") or "[]")]
    except (ValueError, TypeError):
        return []


def aceitar(config: Config, estado, pid: str, numero: int) -> None:
    if pid not in lista(config):
        raise ValueError(f"projeto desconhecido: {pid}")
    atuais = aceitas(estado, pid)
    if numero not in atuais:
        estado.definir_cursor(f"aceitas:{pid}", json.dumps(atuais + [numero]))


def pedir_de_novo(config: Config, estado, pid: str, numero: int) -> None:
    """Marca o prompt para ser digitado outra vez (a worktree já existe)."""
    guardados = preparados(estado, pid)
    if pid not in lista(config) or str(numero) not in guardados:
        raise ValueError(f"prompt desconhecido: {pid} #{numero}")
    guardados[str(numero)]["refazer"] = True
    guardar_preparados(estado, pid, guardados)


def guardar_abertas(estado, pid: str, issues: list[dict]) -> None:
    """Só número, título, link e se é sua: o corpo da issue não fica no estado do mapa."""
    enxutas = [{"numero": i["numero"], "titulo": i["titulo"], "url": i["url"], "minha": bool(i.get("minha"))} for i in issues]
    estado.definir_cursor(f"abertas:{pid}", json.dumps(enxutas, ensure_ascii=False))


def abertas(estado, pid: str) -> list[dict]:
    try:
        return json.loads(estado.cursor(f"abertas:{pid}") or "[]")
    except ValueError:
        return []


def _arquivo(config: Config, pid: str, numero: int):
    return config.pasta_dados / "prompts" / f"{pid}-{int(numero)}.md"


def guardar_texto(config: Config, pid: str, numero: int, texto: str) -> None:
    """O prompt inteiro fica só neste computador, para a gaveta mostrar; o estado do mapa leva só o título."""
    arq = _arquivo(config, pid, numero)
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(texto, encoding="utf-8")


def ler_texto(config: Config, pid: str, numero: int) -> str | None:
    if pid not in lista(config):
        return None
    arq = _arquivo(config, pid, numero)
    return arq.read_text(encoding="utf-8") if arq.is_file() else None


def situacao(config: Config, estado) -> list[dict]:
    """O que o mapa mostra de cada projeto: se está ativo e os prompts que já ficaram prontos."""
    saida = []
    for pid, p in lista(config).items():
        prontos = [{"numero": int(n), **d} for n, d in sorted(preparados(estado, pid).items(), key=lambda kv: int(kv[0]))]
        feitos = {d["numero"] for d in prontos}
        saida.append({"id": pid, "nome": p.get("nome", pid), "github": p["github"], "ativo": ativo(config, estado, pid),
                      "prontos": prontos, "disponiveis": [i for i in abertas(estado, pid) if i["numero"] not in feitos]})
    return saida


def resumo(sit: list[dict]) -> str:
    ativos = [p["nome"] for p in sit if p["ativo"]]
    if not sit:
        return "nenhum projeto configurado"
    if not ativos:
        return "nenhum projeto ativo: ative um na gaveta"
    return "ativo: " + ", ".join(ativos)
