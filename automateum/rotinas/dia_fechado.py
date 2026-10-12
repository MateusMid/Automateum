from datetime import date

from ..nucleo.registro import rotina
from ..servicos import claude, obsidian
from ._texto import listar, secao, sem_blocos

_PEDIDO = (
    "Escreva o fechamento do meu dia com três partes curtas, cada uma com um título em negrito: "
    "**Andou** (o que foi feito ou avançou hoje), **Ficou aberto** (o que estava previsto e não fechou) "
    "e **Amanhã** (no máximo 3 primeiros passos). Baseie-se só no material; se o dia tiver pouco "
    "registro, diga isso em vez de preencher."
)


@rotina(id="dia_fechado", nome="dia fechado", frente="Notas", quando="cron: 0 19 * * mon-fri",
        usa=["obsidian", "claude"], entrega=["diario"])
def rodar(ctx):
    """Lê o que você anotou hoje, os resumos de mensagens e as tasks, e escreve o fechamento no diário."""
    cfg, hoje = ctx.config, date.today().isoformat()
    pasta_diario = cfg.secao("obsidian").get("pasta_diario", "Diário")
    pasta_propria = cfg.secao("obsidian").get("pasta_automateum", "Automateum")
    material = [
        secao("O que eu anotei hoje no diário", sem_blocos(obsidian.ler_nota(cfg, f"{pasta_diario}/{hoje}.md"))),
        secao("Resumos de mensagens de hoje", obsidian.ler_nota(cfg, f"{pasta_propria}/Mensagens/{hoje}.md")),
        secao("Tasks abertas no cofre", listar(ctx.estado.itens(["obsidian"]))),
        secao("GitHub", listar(ctx.estado.itens(["github"]))),
    ]
    fechamento = claude.perguntar(cfg, _PEDIDO, "\n".join(material))
    caminho = obsidian.escrever_bloco_diario(cfg, "dia_fechado", f"## Dia fechado\n\n{fechamento}")
    ctx.log(f"bloco escrito em {caminho.name}")
    return f"fechamento escrito em {caminho.name}"
