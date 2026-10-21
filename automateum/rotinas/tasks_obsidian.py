from datetime import date

from ..config import Config
from ..nucleo.registro import rotina
from ..servicos import obsidian

DESDE = "aberta desde "


def _ident(task: dict) -> str:
    """A task pela nota e pelo texto: o número da linha muda quando se escreve acima dela."""
    return task["origem"] + "\n" + " ".join(task["titulo"].split())


def dias_limite(config: Config) -> int:
    return int(config.secao("obsidian").get("dias_envelhecida", 14))


def envelhecidas(config: Config, itens: list[dict]) -> list[dict]:
    """As tasks abertas há mais de `dias_envelhecida` dias, da mais antiga para a mais nova, com os `dias`."""
    hoje, limite, saida = date.today(), dias_limite(config), []
    for i in itens:
        if not (i.get("corpo") or "").startswith(DESDE):
            continue
        dias = (hoje - date.fromisoformat(i["corpo"].removeprefix(DESDE))).days
        if dias > limite:
            saida.append({**i, "dias": dias})
    return sorted(saida, key=lambda i: -i["dias"])


@rotina(id="tasks_obsidian", nome="tasks do cofre", frente="Tasks", quando="cada 30m", usa=["obsidian"])
def rodar(ctx):
    """Varre o cofre atrás de checkboxes abertos (`- [ ]`) e guarda a lista com nota, linha e desde quando está aberta."""
    tasks = obsidian.tasks_abertas(ctx.config)
    # uma task vista pela primeira vez já existia na última edição da nota: a data dessa edição é o ponto de partida
    desde = ctx.estado.datas_das_tasks({_ident(t): t["quando"] for t in tasks})
    for t in tasks:
        t["corpo"] = DESDE + desde[_ident(t)]
    ctx.estado.substituir_itens("obsidian", tasks)
    notas = len({t["origem"] for t in tasks})
    velhas = len(envelhecidas(ctx.config, tasks))
    return f"{len(tasks)} abertas em {notas} notas" + (f" · {velhas} há mais de {dias_limite(ctx.config)} dias" if velhas else "")
