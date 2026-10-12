from ..nucleo.registro import rotina
from ..servicos import gmail


@rotina(id="coletar_gmail", nome="coletar Gmail", frente="Mensagens", quando="cada 15m", usa=["gmail"])
def rodar(ctx):
    """Guarda os e-mails não lidos da caixa de entrada que ainda não tinham sido vistos."""
    itens = gmail.emails(ctx.config)
    novos = ctx.estado.juntar_itens("gmail", itens)
    ctx.estado.podar_itens("gmail", dias=14)
    return f"{novos} novos · {len(itens)} não lidos" if novos else f"nada novo · {len(itens)} não lidos"
