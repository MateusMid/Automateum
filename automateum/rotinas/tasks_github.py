from ..nucleo.registro import ATENCAO, Resultado, rotina
from ..servicos import github


@rotina(id="tasks_github", nome="tasks do GitHub", frente="Tasks", quando="cada 30m", usa=["github"])
def rodar(ctx):
    """Busca issues e PRs abertos atribuídos a você, os seus PRs (CI, revisões, conflito) e PRs esperando a sua revisão."""
    itens = github.pendencias(ctx.config)
    ctx.estado.substituir_itens("github", itens)
    revisoes = sum("revisão pedida" in i["corpo"] for i in itens)
    resumo = f"{len(itens)} abertas · {revisoes} esperando sua revisão"
    if problemas := [i for i in itens if github.precisa_de_voce(i)]:
        # o mapa fica âmbar: um PR seu espera uma ação sua
        return Resultado(ATENCAO, f"{resumo} · seus PRs: " + "; ".join(
            f"{i['origem']} {i['corpo'].rsplit(' · ', 1)[-1]}" for i in problemas))
    return resumo
