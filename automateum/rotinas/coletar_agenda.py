from ..nucleo.registro import ATENCAO, Resultado, rotina
from ..servicos import agenda, gmail


@rotina(id="coletar_agenda", nome="coletar agenda", frente="Agenda", quando="cada 30m", usa=["agenda"])
def rodar(ctx):
    """Guarda os eventos de hoje e de amanhã de cada conta autorizada. Só lê: nada é criado nem alterado."""
    contas = gmail.contas(ctx.config)
    antigos = ctx.estado.itens(["agenda"], limite=10000)
    itens, falhas = [], []
    for conta in contas:
        try:
            itens += agenda.eventos(ctx.config, conta)
        except Exception as e:
            falhas.append(f"{conta.nome}: {gmail.erro(e)}")
            # a conta que falhou mantém os eventos que já tinha, em vez de sumir da tela
            itens += [i for i in antigos if i["origem"] == conta.nome]
    if falhas and len(falhas) == len(contas):
        raise RuntimeError("; ".join(falhas))
    conhecidas = {i["chave"] for i in antigos}
    ctx.estado.substituir_itens("agenda", itens)
    novos = len({i["chave"] for i in itens} - conhecidas)
    resumo = f"{novos} novos · {len(itens)} eventos" if novos else f"nada novo · {len(itens)} eventos"
    if falhas:
        for f in falhas:
            ctx.log(f)
        return Resultado(ATENCAO, f"{resumo} · {'; '.join(falhas)}")
    return resumo
