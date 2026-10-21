from datetime import date

from ..nucleo.registro import rotina
from ..servicos import git_local, ia, maquina, obsidian
from ._texto import formatar_git, listar, secao, sem_blocos

_PEDIDO = (
    "Escreva o fechamento do meu dia com três partes curtas, cada uma com um título em negrito: "
    "**Andou** (o que foi feito ou avançou hoje, incluindo commits e trabalho nos projetos), "
    "**Ficou aberto** (o que estava previsto e não fechou, arquivos modificados sem commit ou commits pendentes de envio) "
    "e **Amanhã** (no máximo 3 primeiros passos). Baseie-se só no material; se o dia tiver pouco "
    "registro, diga isso em vez de preencher."
)



@rotina(id="dia_fechado", nome="dia fechado", frente="Notas", quando="cron: 0 19 * * mon-fri",
        usa=["obsidian", "claude", "git_local"], entrega=["diario"])
def rodar(ctx):
    """Lê o que você anotou hoje, os resumos de mensagens, tasks e repositórios git locais, e escreve o fechamento no diário."""
    cfg, hoje = ctx.config, date.today().isoformat()
    pasta_diario = cfg.secao("obsidian").get("pasta_diario", "Diário")
    pasta_propria = cfg.secao("obsidian").get("pasta_automateum", "Automateum")
    git_info = formatar_git(git_local.auditar_dia(cfg, dias=0))
    material = [
        secao("O que eu anotei hoje no diário", sem_blocos(obsidian.ler_nota(cfg, f"{pasta_diario}/{hoje}.md"))),
        secao("Resumos de mensagens de hoje", obsidian.ler_nota(cfg, f"{pasta_propria}/Mensagens/{hoje}.md")),
        secao("Tasks abertas no cofre", listar(ctx.estado.itens(["obsidian"]))),
        secao("GitHub remoto", listar(ctx.estado.itens(["github"]))),
        secao("Atividade Git Local / Repositórios", git_info),
    ]
    fechamento = ia.perguntar(ctx, _PEDIDO, "\n".join(material))
    # A linha da máquina sai das medições, não do Claude: é um número, e não deve ser reescrito.
    ligada_desde = ((ctx.estado.checagens().get("maquina") or {}).get("meta") or {}).get("ligada_desde", "")
    linha_maquina = maquina.resumo_do_dia(ctx.estado.medidas(f"{hoje}T00:00:00"), ligada_desde)
    texto = fechamento + (f"\n\n{linha_maquina}" if linha_maquina else "")
    ctx.texto = texto
    caminho = obsidian.escrever_bloco_diario(cfg, "dia_fechado", f"## Dia fechado\n\n{texto}")
    ctx.log(f"bloco escrito em {caminho.name}")
    return f"fechamento escrito em {caminho.name}"

