import json

from ..nucleo.registro import rotina
from ..servicos import slack


@rotina(id="coletar_slack", nome="coletar Slack", frente="Mensagens", quando="cada 15m", usa=["slack"])
def rodar(ctx):
    """Guarda as mensagens novas das suas conversas no Slack desde a última coleta."""
    cursores = json.loads(ctx.estado.cursor("slack:cursores", "{}"))
    itens, cursores = slack.mensagens_novas(ctx.config, cursores, ctx.log)
    novas = ctx.estado.juntar_itens("slack", itens)
    ctx.estado.definir_cursor("slack:cursores", json.dumps(cursores))
    ctx.estado.podar_itens("slack", dias=14)
    conversas = len({i["origem"] for i in itens})
    return f"{novas} novas em {conversas} conversas" if novas else "nada novo"
