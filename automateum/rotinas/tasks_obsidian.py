from ..nucleo.registro import rotina
from ..servicos import obsidian


@rotina(id="tasks_obsidian", nome="tasks do cofre", frente="Tasks", quando="cada 30m", usa=["obsidian"])
def rodar(ctx):
    """Varre o cofre atrás de checkboxes abertos (`- [ ]`) e guarda a lista com nota e linha."""
    tasks = obsidian.tasks_abertas(ctx.config)
    ctx.estado.substituir_itens("obsidian", tasks)
    notas = len({t["origem"] for t in tasks})
    return f"{len(tasks)} abertas em {notas} notas"
