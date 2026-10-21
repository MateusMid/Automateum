from datetime import date, timedelta

from ..nucleo.registro import rotina
from ..servicos import git_local, ia, obsidian
from ._texto import bloco, formatar_git, listar, notas_editadas, secao, sem_blocos

_PEDIDO = (
    "Escreva o fechamento da minha semana com três partes curtas, cada uma com um título em negrito: "
    "**Andou** (o que foi feito ou avançou na semana, agrupado por projeto ou assunto), "
    "**Ficou aberto** (o que se arrastou pela semana ou não fechou) e **Próxima semana** (no máximo 3 focos). "
    "No máximo 25 linhas no total. Baseie-se só no material; se a semana tiver pouco registro, diga isso "
    "em vez de preencher."
)
_DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def dias_da_semana(hoje: date) -> list[date]:
    """De segunda até `hoje`."""
    return [hoje - timedelta(days=d) for d in range(hoje.weekday(), -1, -1)]


@rotina(id="semana_fechada", nome="semana fechada", frente="Notas", quando="cron: 30 19 * * fri",
        usa=["obsidian", "claude", "git_local"], entrega=["diario"])
def rodar(ctx):
    """Junta os fechamentos e as anotações dos dias da semana e escreve o fechamento da semana no diário de hoje."""
    cfg, hoje = ctx.config, date.today()
    pasta_diario = cfg.secao("obsidian").get("pasta_diario", "Diário")
    material, com_diario = [], 0
    for dia in dias_da_semana(hoje):
        nota = obsidian.ler_nota(cfg, f"{pasta_diario}/{dia.isoformat()}.md")
        if not nota.strip():
            continue
        com_diario += 1
        nome = f"{_DIAS[dia.weekday()]} {dia:%d/%m}"
        material.append(secao(f"Fechamento de {nome}", bloco(nota, "dia_fechado"), 4000))
        material.append(secao(f"Anotações de {nome}", sem_blocos(nota), 3000))
    if not com_diario:
        return "nenhum diário nesta semana: nada para fechar"
    segunda = dias_da_semana(hoje)[0]
    material.append(secao("Notas do cofre editadas na semana",
                          notas_editadas(obsidian.notas_editadas(cfg, segunda), total=12000), 14000))
    material.append(secao("Tasks abertas no cofre", listar(ctx.estado.itens(["obsidian"]))))
    # dias = quantos dias desde segunda: os commits da semana toda, não só os de hoje
    material.append(secao("Atividade Git Local / Repositórios",
                          formatar_git(git_local.auditar_dia(cfg, dias=hoje.weekday()))))

    texto = ia.perguntar(ctx, _PEDIDO, "\n".join(material))
    ctx.texto = texto
    caminho = obsidian.escrever_bloco_diario(cfg, "semana_fechada", f"## Semana fechada\n\n{texto}", hoje)
    ctx.log(f"bloco escrito em {caminho.name}, a partir de {com_diario} dia(s) com diário")
    return f"fechamento da semana escrito em {caminho.name}"
