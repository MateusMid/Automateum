from datetime import date

from ..nucleo.registro import ATENCAO, Resultado, rotina
from ..servicos import agenda, gmail


@rotina(id="coletar_agenda", nome="coletar agenda", frente="Agenda", quando="cada 30m",
        usa=["agenda"], entrega=["agenda"])
def rodar(ctx):
    """Atualiza os eventos de hoje e amanhã das agendas autorizadas, sem alterar compromissos."""
    contas = agenda.contas(ctx.config)
    inicio, fim = agenda.intervalo_dias(date.today())
    antigos = ctx.estado.itens(["agenda"], limite=10000)
    itens, falhas = [], []
    for conta in contas:
        try:
            itens.extend(agenda.eventos_conta_periodo(ctx.config, conta, inicio, fim))
        except Exception as e:
            falhas.append(f"{conta.nome}: {gmail.erro(e)}")
            # Uma falha parcial não deve apagar a agenda já coletada para essa conta.
            itens.extend(i for i in antigos if i.get("origem") == conta.nome)

    if falhas and len(falhas) == len(contas):
        raise RuntimeError("; ".join(falhas))

    conhecidos = {i["chave"] for i in antigos}
    ctx.estado.substituir_itens("agenda", itens)
    novos = len({i["chave"] for i in itens} - conhecidos)
    resumo = f"{novos} novos · {len(itens)} eventos" if novos else f"nada novo · {len(itens)} eventos"
    if falhas:
        for falha in falhas:
            ctx.log(falha)
        return Resultado(ATENCAO, f"{resumo} · {'; '.join(falhas)}")
    return resumo
