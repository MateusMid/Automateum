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
    # canal que saiu da lista permitida: some também o que já estava guardado, para não entrar nos resumos
    secao = ctx.config.secao("slack")
    canais, marcados, dms = secao.get("canais", []), secao.get("canais_marcados", []), bool(secao.get("dms", True))
    fora = [o for o in ctx.estado.origens("slack") if slack_navegador.modo_da_conversa(o, canais, marcados, dms) is None]
    if fora:
        ctx.log(f"{ctx.estado.remover_origens('slack', fora)} mensagens guardadas de canais fora da lista foram apagadas")
    for o in ctx.estado.origens("slack"):   # canal "só o que me marcar": o que já estava guardado sem citar você sai
        if slack_navegador.modo_da_conversa(o, canais, marcados, dms) == "marcado":
            ctx.estado.remover_sem_marca("slack", o, slack_navegador.marcas(secao))
    conversas = len({i["origem"] for i in itens})
    resumo = f"{novas} novas em {conversas} conversas" if novas else "nada novo"
    if aviso:
        ctx.log(aviso)
        return Resultado(ATENCAO, f"{resumo} · fonte incompleta: veja o log")
    return Resultado(OK, resumo)
