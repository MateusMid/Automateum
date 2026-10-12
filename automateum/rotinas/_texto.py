"""Montagem do material que vai para o Claude nas rotinas de resumo."""
import re

_BLOCO = re.compile(r"%% automateum:(\w+):inicio %%.*?%% automateum:\1:fim %%", re.S)


def sem_blocos(texto: str) -> str:
    """O texto da nota sem o que o próprio Automateum escreveu nela."""
    return _BLOCO.sub("", texto).strip()


def listar(itens: list[dict], limite: int = 150, corte: int = 400) -> str:
    linhas = []
    for i in itens[:limite]:
        extra = f" — {i['corpo']}" if i.get("corpo") else ""
        linhas.append(f"- [{i['origem']}] {i['titulo']}{extra}"[:corte])
    if len(itens) > limite:
        linhas.append(f"- (mais {len(itens) - limite} itens não listados)")
    return "\n".join(linhas) or "(nada)"


def secao(titulo: str, corpo: str, limite: int = 12000) -> str:
    corpo = corpo.strip() or "(vazio)"
    if len(corpo) > limite:
        corpo = corpo[:limite] + "\n(cortado)"
    return f"### {titulo}\n{corpo}\n"
