from datetime import date

from ..nucleo.registro import rotina
from ..servicos import claude, git_local, obsidian
from ._texto import listar, secao, sem_blocos

_PEDIDO = (
    "Escreva o fechamento do meu dia com três partes curtas, cada uma com um título em negrito: "
    "**Andou** (o que foi feito ou avançou hoje, incluindo commits e trabalho nos projetos), "
    "**Ficou aberto** (o que estava previsto e não fechou, arquivos modificados sem commit ou commits pendentes de envio) "
    "e **Amanhã** (no máximo 3 primeiros passos). Baseie-se só no material; se o dia tiver pouco "
    "registro, diga isso em vez de preencher."
)


def _formatar_git(auditoria: list[dict]) -> str:
    linhas = []
    for r in auditoria:
        nome = r["projeto"]
        detalhes = []
        if r["commits"]:
            detalhes.append(f"{len(r['commits'])} commit(s) seu(s): " + "; ".join(r["commits"][:5]))
        if r["sem_subir"]:
            detalhes.append(f"{len(r['sem_subir'])} commit(s) sem subir (push)")
        if r["sujo"]:
            detalhes.append(f"{len(r['sujo'])} arquivo(s) modificado(s) sem commit")
        if r.get("sem_upstream"):
            detalhes.append(f"branch '{r['branch']}' local sem upstream remoto")
        if detalhes:
            linhas.append(f"- **{nome}** ({r['branch']}): " + " | ".join(detalhes))
    return "\n".join(linhas) if linhas else "Nenhum commit ou alteração pendente hoje."


@rotina(id="dia_fechado", nome="dia fechado", frente="Notas", quando="cron: 0 19 * * mon-fri",
        usa=["obsidian", "claude", "git_local"], entrega=["diario"])
def rodar(ctx):
    """Lê o que você anotou hoje, os resumos de mensagens, tasks e repositórios git locais, e escreve o fechamento no diário."""
    cfg, hoje = ctx.config, date.today().isoformat()
    pasta_diario = cfg.secao("obsidian").get("pasta_diario", "Diário")
    pasta_propria = cfg.secao("obsidian").get("pasta_automateum", "Automateum")
    git_info = _formatar_git(git_local.auditar_dia(cfg, dias=0))
    material = [
        secao("O que eu anotei hoje no diário", sem_blocos(obsidian.ler_nota(cfg, f"{pasta_diario}/{hoje}.md"))),
        secao("Resumos de mensagens de hoje", obsidian.ler_nota(cfg, f"{pasta_propria}/Mensagens/{hoje}.md")),
        secao("Tasks abertas no cofre", listar(ctx.estado.itens(["obsidian"]))),
        secao("GitHub remoto", listar(ctx.estado.itens(["github"]))),
        secao("Atividade Git Local / Repositórios", git_info),
    ]
    fechamento = claude.perguntar(cfg, _PEDIDO, "\n".join(material))
    ctx.texto = fechamento
    caminho = obsidian.escrever_bloco_diario(cfg, "dia_fechado", f"## Dia fechado\n\n{fechamento}")
    ctx.log(f"bloco escrito em {caminho.name}")
    return f"fechamento escrito em {caminho.name}"

