from ..nucleo.registro import rotina
from ..servicos import github


@rotina(id="tasks_github", nome="tasks do GitHub", frente="Tasks", quando="cada 30m", usa=["github"])
def rodar(ctx):
    """Busca issues e PRs abertos atribuídos a você e PRs esperando a sua revisão."""
    itens = github.pendencias(ctx.config)
    ctx.estado.substituir_itens("github", itens)
    revisoes = sum("revisão" in i["corpo"] for i in itens)
    return f"{len(itens)} abertas · {revisoes} esperando sua revisão"
