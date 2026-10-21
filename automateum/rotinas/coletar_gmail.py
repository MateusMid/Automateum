from ..nucleo.registro import ATENCAO, OK, Resultado, rotina
from ..servicos import gmail


@rotina(id="coletar_gmail", nome="coletar Gmail", frente="Mensagens", quando="cada 15m", usa=["gmail"])
def rodar(ctx):
    """Guarda os e-mails não lidos da caixa de entrada que ainda não tinham sido vistos, de cada conta autorizada."""
    contas = gmail.contas(ctx.config)
    itens, falhas = [], []
    for conta in contas:
        try:
            itens += gmail.emails(ctx.config, conta, varias=len(contas) > 1)
        except Exception as e:
            # uma conta vencida não impede de guardar as outras
            falhas.append(f"{conta.nome}: {gmail.erro(e)}")
    if falhas and len(falhas) == len(contas):
        raise RuntimeError("; ".join(falhas))
    novos = ctx.estado.juntar_itens("gmail", itens)
    ctx.estado.podar_itens("gmail", dias=14)
    resumo = f"{novos} novos · {len(itens)} não lidos" if novos else f"nada novo · {len(itens)} não lidos"
    if falhas:
        for f in falhas:
            ctx.log(f)
        return Resultado(ATENCAO, f"{resumo} · {'; '.join(falhas)}")
    return Resultado(OK, resumo)
