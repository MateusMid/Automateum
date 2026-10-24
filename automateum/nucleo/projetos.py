"""Os projetos em que você está trabalhando: quais estão ativos e que prompts já foram deixados prontos.

Só as issues atribuídas a você viram prompt sozinhas; as outras esperam o "Começar" da gaveta. Uma issue dispensada
(cursor `dispensadas:<id>`) sai da lista e libera a vaga, e só volta pelo "Reativar".
Cada projeto vem do config (`[projetos.<id>]`: nome, github, ativo, rotulo, max_pendentes, modelo). O ativar/desativar
do mapa fica guardado no estado (cursor `projeto:<id>:ativo`) e vale mais que o `ativo` do config.
"""
from __future__ import annotations

import json

from ..config import Config
from ..servicos import orca

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


MODELO_REVISAO = (
    "Revisão do PR #{numero}: {titulo}\n{url}\nBranch: {branch} (base: {base})\n\n{corpo}\n\n---\n"
    "Leia o diff deste PR (git diff {base}...HEAD) e o que mais precisar do código. Aponte bugs, riscos, "
    "problemas de segurança e testes que faltam, e proponha as correções em texto. "
    "Não altere arquivos, não faça commit nem push, e não comente, aprove nem peça mudanças no GitHub sem eu pedir."
)

# o registro de prompts prontos é um por tipo: issue ("prompts:<id>") e revisão de PR ("revisoes:<id>")
_CURSOR = {"issue": "prompts", "pr": "revisoes"}


def revisar_todos(config: Config, estado, pid: str) -> bool:
    """A chave "todos os PRs" do projeto: ligada, a revisão pega todo PR aberto (inclusive os seus), não só os que pedem a sua."""
    guardado = estado.cursor(f"projeto:{pid}:revisar_todos")
    if guardado:
        return guardado == "1"
    return lista(config).get(pid, {}).get("revisar_quais") == "todos"


def definir_revisar_todos(config: Config, estado, pid: str, ligado: bool) -> None:
    if pid not in lista(config):
        raise ValueError(f"projeto desconhecido: {pid}")
    estado.definir_cursor(f"projeto:{pid}:revisar_todos", "1" if ligado else "0")


def preparados(estado, pid: str, tipo: str = "issue") -> dict[str, dict]:
    try:
        return json.loads(estado.cursor(f"{_CURSOR[tipo]}:{pid}") or "{}")
    except ValueError:
        return {}


def guardar_preparados(estado, pid: str, dados: dict[str, dict], tipo: str = "issue") -> None:
    if tipo == "issue":   # dispensada no meio de uma rodada: a rodada não a traz de volta ao guardar
        fora = dispensadas(estado, pid)
        dados = {n: d for n, d in dados.items() if n not in fora}
    estado.definir_cursor(f"{_CURSOR[tipo]}:{pid}", json.dumps(dados, ensure_ascii=False))


def dispensadas(estado, pid: str) -> dict[str, dict]:
    """Issues que você tirou da lista: número -> título, link e a worktree, se o prompt já estava pronto."""
    try:
        return json.loads(estado.cursor(f"dispensadas:{pid}") or "{}")
    except ValueError:
        return {}


def guardar_dispensadas(estado, pid: str, dados: dict[str, dict]) -> None:
    estado.definir_cursor(f"dispensadas:{pid}", json.dumps(dados, ensure_ascii=False))


def dispensar(config: Config, estado, pid: str, numero: int) -> None:
    """Tira a issue da lista e libera a vaga; ela não volta sozinha. A worktree do Orca fica onde está."""
    if pid not in lista(config):
        raise ValueError(f"projeto desconhecido: {pid}")
    chave = str(numero)
    prontos = preparados(estado, pid)
    aberta = next((i for i in abertas(estado, pid) if i["numero"] == numero), None)
    if chave not in prontos and aberta is None:
        raise ValueError(f"issue desconhecida: {pid} #{numero}")
    registro = prontos.pop(chave, None) or {"titulo": aberta["titulo"], "url": aberta["url"]}
    registro.pop("refazer", None)
    fora = dispensadas(estado, pid)
    fora[chave] = registro
    guardar_dispensadas(estado, pid, fora)
    guardar_preparados(estado, pid, prontos)
    # senão o "Começar" de antes a faria voltar na próxima rodada
    estado.definir_cursor(f"aceitas:{pid}", json.dumps([n for n in aceitas(estado, pid) if n != numero]))


def reativar(config: Config, estado, pid: str, numero: int) -> None:
    """Devolve a issue: com o prompt já pronto antes, ele é digitado de novo na mesma worktree (ou numa nova)."""
    fora = dispensadas(estado, pid)
    if pid not in lista(config) or str(numero) not in fora:
        raise ValueError(f"issue não dispensada: {pid} #{numero}")
    registro = fora.pop(str(numero))
    guardar_dispensadas(estado, pid, fora)
    if registro.get("worktree"):
        prontos = preparados(estado, pid)
        prontos[str(numero)] = {**registro, "refazer": True}
        guardar_preparados(estado, pid, prontos)
    else:
        aceitar(config, estado, pid, numero)


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


def pedir_de_novo(config: Config, estado, pid: str, numero: int, tipo: str = "issue") -> None:
    """Marca o prompt para ser digitado outra vez (a worktree já existe)."""
    guardados = preparados(estado, pid, tipo)
    if pid not in lista(config) or str(numero) not in guardados:
        raise ValueError(f"prompt desconhecido: {pid} #{numero}")
    guardados[str(numero)]["refazer"] = True
    guardar_preparados(estado, pid, guardados, tipo)


def guardar_abertas(estado, pid: str, issues: list[dict]) -> None:
    """Só número, título, link e se é sua: o corpo da issue não fica no estado do mapa."""
    enxutas = [{"numero": i["numero"], "titulo": i["titulo"], "url": i["url"], "minha": bool(i.get("minha"))} for i in issues]
    estado.definir_cursor(f"abertas:{pid}", json.dumps(enxutas, ensure_ascii=False))


def abertas(estado, pid: str) -> list[dict]:
    try:
        return json.loads(estado.cursor(f"abertas:{pid}") or "[]")
    except ValueError:
        return []


def _arquivo(config: Config, pid: str, numero: int, tipo: str = "issue"):
    return config.pasta_dados / "prompts" / f"{pid}-{'pr' if tipo == 'pr' else ''}{int(numero)}.md"


def guardar_texto(config: Config, pid: str, numero: int, texto: str, tipo: str = "issue") -> None:
    """O prompt inteiro fica só neste computador, para a gaveta mostrar; o estado do mapa leva só o título."""
    arq = _arquivo(config, pid, numero, tipo)
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(texto, encoding="utf-8")


def ler_texto(config: Config, pid: str, numero: int, tipo: str = "issue") -> str | None:
    if pid not in lista(config):
        return None
    arq = _arquivo(config, pid, numero, tipo)
    return arq.read_text(encoding="utf-8") if arq.is_file() else None


def situacao(config: Config, estado) -> list[dict]:
    """O que o mapa mostra de cada projeto: se está ativo e os prompts que já ficaram prontos."""
    saida = []
    for pid, p in lista(config).items():
        prontos = [{"numero": int(n), **d} for n, d in sorted(preparados(estado, pid).items(), key=lambda kv: int(kv[0]))]
        fora = [{"numero": int(n), **d} for n, d in sorted(dispensadas(estado, pid).items(), key=lambda kv: int(kv[0]))]
        feitos = {d["numero"] for d in prontos + fora}
        saida.append({"id": pid, "nome": p.get("nome", pid), "github": p["github"], "ativo": ativo(config, estado, pid),
                      "revisar_todos": revisar_todos(config, estado, pid),
                      "revisoes": [{"numero": int(n), **d} for n, d in sorted(preparados(estado, pid, "pr").items(), key=lambda kv: int(kv[0]))],
                      "prontos": prontos, "dispensados": fora, "limpar": limpaveis(estado, pid),
                      "disponiveis": [i for i in abertas(estado, pid) if i["numero"] not in feitos]})
    return saida


def limpaveis(estado, pid: str) -> list[dict]:
    """Worktrees de issues que fecharam ou que você dispensou. Só a lista: quem apaga confere se estão limpas."""
    abertas_ = {i["numero"] for i in abertas(estado, pid)}
    saida = []
    for n, d in sorted(preparados(estado, pid).items(), key=lambda kv: int(kv[0])):
        # sem nenhuma issue aberta na última leitura, não dá para dizer que alguma fechou: não lista nada
        if d.get("worktree") and abertas_ and int(n) not in abertas_:
            saida.append({"numero": int(n), "titulo": d.get("titulo", ""), "worktree": d["worktree"], "motivo": "issue fechada"})
    for n, d in sorted(dispensadas(estado, pid).items(), key=lambda kv: int(kv[0])):
        if d.get("worktree"):
            saida.append({"numero": int(n), "titulo": d.get("titulo", ""), "worktree": d["worktree"], "motivo": "dispensada"})
    return saida


def apagar_worktree(config: Config, estado, pid: str, numero: int) -> None:
    """Apaga a worktree no Orca e tira o registro dela. Recusa se tiver alteração ou commit sem enviar."""
    if pid not in lista(config):
        raise ValueError(f"projeto desconhecido: {pid}")
    alvo = next((c for c in limpaveis(estado, pid) if c["numero"] == numero), None)
    if alvo is None:
        raise ValueError(f"a worktree da issue #{numero} não está na lista de limpeza")
    if motivo := orca.pendencias(alvo["worktree"]):
        raise ValueError(f"não apaguei a worktree da #{numero}: {motivo}")
    if orca.worktree_existe(config, alvo["worktree"]):
        orca.remover_worktree(config, alvo["worktree"])
    chave = str(numero)
    prontos = preparados(estado, pid)
    if prontos.pop(chave, None) is not None:
        guardar_preparados(estado, pid, prontos)
    fora = dispensadas(estado, pid)
    if fora.pop(chave, None) is not None:
        guardar_dispensadas(estado, pid, fora)


def resumo(sit: list[dict]) -> str:
    ativos = [p["nome"] for p in sit if p["ativo"]]
    if not sit:
        return "nenhum projeto configurado"
    if not ativos:
        return "nenhum projeto ativo: ative um na gaveta"
    return "ativo: " + ", ".join(ativos)
