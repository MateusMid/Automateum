"""Montagem do material que vai para o Claude nas rotinas de resumo."""
import re

_BLOCO = re.compile(r"%% automateum:(\w+):inicio %%.*?%% automateum:\1:fim %%", re.S)


def sem_blocos(texto: str) -> str:
    """O texto da nota sem o que o próprio Automateum escreveu nela."""
    return _BLOCO.sub("", texto).strip()


def bloco(texto: str, nome: str) -> str:
    """Só o que o Automateum escreveu no bloco `nome` da nota, sem os marcadores; "" se não houver."""
    achado = re.search(rf"%% automateum:{re.escape(nome)}:inicio %%(.*?)%% automateum:{re.escape(nome)}:fim %%",
                       texto, re.S)
    return achado.group(1).strip() if achado else ""


def formatar_git(auditoria: list[dict]) -> str:
    linhas = []
    for r in auditoria:
        nome = r["projeto"]
        detalhes = []
        if r["commits"]:
            detalhes.append(f"{len(r['commits'])} commit(s) seu(s): " + "; ".join(r["commits"][:5]))
        if r["sem_subir"]:
            detalhes.append(f"{len(r['sem_subir'])} commit(s) sem subir (push)")
        if r["sujo"]:
            detalhes.append(f"{len(r['sujo'])} arquivo(s) modificado(s) sem commit")
        if r.get("sem_upstream"):
            detalhes.append(f"branch '{r['branch']}' local sem upstream remoto")
        if detalhes:
            linhas.append(f"- **{nome}** ({r['branch']}): " + " | ".join(detalhes))
    return "\n".join(linhas) if linhas else "Nenhum commit ou alteração pendente."


def listar(itens: list[dict], limite: int = 150, corte: int = 400) -> str:
    linhas = []
    for i in itens[:limite]:
        extra = f" — {i['corpo']}" if i.get("corpo") else ""
        linhas.append(f"- [{i['origem']}] {i['titulo']}{extra}"[:corte])
    if len(itens) > limite:
        linhas.append(f"- (mais {len(itens) - limite} itens não listados)")
    return "\n".join(linhas) or "(nada)"


def notas_editadas(notas: list[tuple[str, str]], por_nota: int = 1200, total: int = 8000) -> str:
    """Nome e começo de cada nota editada; passando de `total`, as que sobram entram só pelo nome."""
    partes, so_nome, usado = [], [], 0
    for relativo, texto in notas:
        trecho = sem_blocos(texto)
        if not trecho:
            continue        # só tinha o que o Automateum escreveu
        if len(trecho) > por_nota:
            trecho = trecho[:por_nota] + " (...)"
        if usado + len(trecho) > total:
            so_nome.append(relativo)
            continue
        usado += len(trecho)
        partes.append(f"#### {relativo}\n{trecho}")
    if so_nome:
        partes.append("Também editadas (só o nome): " + ", ".join(so_nome[:40])
                      + (f" e mais {len(so_nome) - 40}" if len(so_nome) > 40 else ""))
    return "\n\n".join(partes)


def secao(titulo: str, corpo: str, limite: int = 12000) -> str:
    corpo = corpo.strip() or "(vazio)"
    if len(corpo) > limite:
        corpo = corpo[:limite] + "\n(cortado)"
    return f"### {titulo}\n{corpo}\n"
