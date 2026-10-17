from datetime import date, datetime

from ..nucleo.estado import agora
from ..nucleo.registro import rotina
from ..servicos import claude, obsidian
from ._texto import listar

_MAXIMO_NO_RESUMO = 300
_MAXIMO_LIDO = 1000  # lê além do teto só para saber quantas ficaram de fora

_PEDIDO = (
    "Resuma as mensagens novas abaixo em no máximo 12 linhas. Comece pelo que pede resposta ou ação "
    "minha, com o nome de quem pediu; depois o resto, agrupado por conversa. Se nada for importante, "
    "diga isso em uma linha."
)


@rotina(id="resumo_mensagens", nome="resumo das mensagens", frente="Mensagens",
        quando="cron: 0 9-18 * * mon-fri", usa=["claude", "obsidian"], entrega=["notas"])
def rodar(ctx):
    """Resume o que chegou no Slack e no Gmail desde o último resumo e anota no cofre."""
    inicio = agora()
    itens = ctx.estado.itens(["slack", "gmail"], coletado_apos=ctx.estado.cursor("resumo_mensagens:ate"),
                             limite=_MAXIMO_LIDO)
    if not itens:
        return "nada novo para resumir"
    ctx.log(f"{len(itens)} mensagens para resumir")
    resumo = claude.perguntar(ctx.config, _PEDIDO, listar(itens, limite=_MAXIMO_NO_RESUMO))
    ctx.texto = resumo
    # O cursor avança até o fim da rodada: o que passou do teto não entra em resumo nenhum. Deixa registro.
    if fora := max(0, len(itens) - _MAXIMO_NO_RESUMO):
        ctx.avisar(f"resumo das mensagens: {fora} mensagens ficaram de fora (o teto é {_MAXIMO_NO_RESUMO} por resumo)")
        ctx.log(f"{fora} mensagens passaram do teto e não foram resumidas")
    caminho = obsidian.escrever_proprio(ctx.config, f"Mensagens/{date.today().isoformat()}.md",
                                        f"## {datetime.now():%H:%M}\n\n{resumo}", acrescentar=True)
    ctx.estado.definir_cursor("resumo_mensagens:ate", inicio)
    ctx.log(f"anotado em {caminho.name}")
    return f"{len(itens)} mensagens resumidas"
