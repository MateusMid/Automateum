import json

from ..nucleo.registro import ATENCAO, OK, Resultado, rotina
from ..servicos import slack, slack_navegador


@rotina(id="coletar_slack", nome="coletar Slack", frente="Mensagens", quando="cada 15m", usa=["slack"])
def rodar(ctx):
    """Guarda as mensagens novas das suas conversas no Slack desde a última coleta."""
    if slack.modo(ctx.config) == "navegador":
        return _por_navegador(ctx)
    cursores = json.loads(ctx.estado.cursor("slack:cursores", "{}"))
    itens, cursores = slack.mensagens_novas(ctx.config, cursores, ctx.log)
    novas = ctx.estado.juntar_itens("slack", itens)
    ctx.estado.definir_cursor("slack:cursores", json.dumps(cursores))
    ctx.estado.podar_itens("slack", dias=14)
    conversas = len({i["origem"] for i in itens})
    return f"{novas} novas em {conversas} conversas" if novas else "nada novo"


def _por_navegador(ctx):
    # A colheita lê hoje e ontem de uma vez; o que já foi guardado não entra de novo (chave estável).
    itens, aviso = slack_navegador.colher(ctx.config, ctx.log)
    novas = ctx.estado.juntar_itens("slack", itens)
    ctx.estado.podar_itens("slack", dias=14)
    conversas = len({i["origem"] for i in itens})
    resumo = f"{novas} novas em {conversas} conversas" if novas else "nada novo"
    if aviso:
        ctx.log(aviso)
        return Resultado(ATENCAO, f"{resumo} · fonte incompleta: veja o log")
    return Resultado(OK, resumo)
