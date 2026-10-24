from datetime import date, datetime, timedelta

from ..nucleo.registro import rotina
from ..servicos import ia, obsidian
from ._texto import listar, secao, sem_blocos

_PEDIDO = (
    "Monte o meu briefing de hoje com três partes curtas, cada uma com um título em negrito: "
    "**Prioridades** (no máximo 5, pela ordem em que eu deveria atacar, citando a nota ou o repositório "
    "de origem), **Envelhecendo** (pendências antigas que merecem decisão: fazer, delegar ou apagar) e "
    "**Responder** (mensagens que esperam resposta minha e PRs meus com CI falhou, mudanças pedidas ou conflito). Omita a parte que não tiver nada. "
    "No máximo 5 itens por parte, uma linha cada, e 20 linhas no total: escolha o que mais pesa em vez "
    "de listar tudo. Baseie-se só no material; não invente tarefa."
)


@rotina(id="meu_dia", nome="meu dia", frente="Notas", quando="cron: 30 8 * * mon-fri",
        usa=["obsidian", "claude"], entrega=["diario"])
def rodar(ctx):
    """Junta tasks, mensagens da noite e as últimas notas e escreve o briefing do dia no diário."""
    cfg, secao_obsidian = ctx.config, ctx.config.secao("obsidian")
    desde = (datetime.now() - timedelta(hours=16)).isoformat(timespec="seconds")
    material = [
        secao("Tasks abertas no cofre (origem = nota; depois do traço, desde quando está aberta e a última edição da nota)",
              listar([{**t, "corpo": f"{t['corpo']}, nota editada em {t['quando']}"} for t in ctx.estado.itens(["obsidian"])])),
        secao("GitHub", listar(ctx.estado.itens(["github"]))),
        secao("Mensagens desde ontem à tarde", listar(ctx.estado.itens_nao_vistos(["slack", "gmail"], desde))),
    ]
    for nome, texto in obsidian.notas_recentes(cfg, secao_obsidian.get("pasta_diario", "Diário"), 4):
        if nome != date.today().isoformat():
            material.append(secao(f"Diário de {nome}", sem_blocos(texto), 3000))
    for pasta in secao_obsidian.get("pastas_contexto", []):
        for nome, texto in obsidian.notas_recentes(cfg, pasta, 2):
            material.append(secao(f"Nota recente: {pasta}/{nome}", texto, 4000))

    briefing = ia.perguntar(ctx, _PEDIDO, "\n".join(material))
    ctx.texto = briefing
    caminho = obsidian.escrever_bloco_diario(cfg, "meu_dia", f"## Meu dia\n\n{briefing}")
    ctx.log(f"bloco escrito em {caminho.name}")
    return f"briefing escrito em {caminho.name}"
