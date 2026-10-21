from ..nucleo import projetos
from ..nucleo.registro import Atencao, rotina
from ..servicos import github, orca
from .preparar_prompts import _POR_RODADA, _abertos, _digitar, _nome


def _prompt(projeto: dict, pr: dict) -> str:
    modelo = projeto.get("modelo_revisao") or projetos.MODELO_REVISAO
    return modelo.format(numero=pr["numero"], titulo=pr["titulo"], url=pr["url"], branch=pr["branch"], base=pr["base"],
                         corpo=(pr["corpo"] or "(sem descrição)").strip())


def _worktree(cfg, repo, info, pr):
    """Cria a worktree no branch do PR (já buscado do GitHub) e devolve o que o Orca respondeu."""
    base = orca.buscar_branch(info, pr["branch"])
    return orca.criar_worktree(cfg, repo, _nome(pr["numero"], pr["titulo"], "pr"), None, "Revisão preparada pelo Automateum",
                               pr=pr["numero"], base=base)


@rotina(id="preparar_revisoes", nome="revisões de PR", frente="Projetos", quando="cada 15m", usa=["github", "orca"])
def rodar(ctx):
    """Deixa pronto no Orca o prompt de revisão de cada PR que pede a sua revisão. Digitado, nunca enviado."""
    cfg = ctx.config
    ativos = {pid: p for pid, p in projetos.lista(cfg).items()
              if projetos.ativo(cfg, ctx.estado, pid) and p.get("revisar", True)}
    if not ativos:
        return "nenhum projeto ativo"
    if not orca.aberto(cfg):
        return orca.FECHADO
    feitos, problemas = [], []
    for pid, projeto in ativos.items():
        info = orca.repo_info(cfg, projeto["github"])
        if not info:
            problemas.append(f"{projeto.get('nome', pid)}: o repositório {projeto['github']} não está no Orca")
            continue
        repo = info["id"]
        prs = [p for p in github.prs_para_revisar(cfg, projeto["github"], projetos.revisar_todos(cfg, ctx.estado, pid)) if not p["de_fork"]]   # fork: sem branch para buscar
        abertos = {str(p["numero"]) for p in prs}
        guardados = {n: d for n, d in projetos.preparados(ctx.estado, pid, "pr").items() if n in abertos}
        vagas = max(0, int(projeto.get("max_revisoes", 3)) - len(guardados))
        novos = [p for p in prs if str(p["numero"]) not in guardados][:min(vagas, _POR_RODADA)]
        refazer = [p for p in prs if guardados.get(str(p["numero"]), {}).get("refazer")]
        for pr in refazer:
            reg = guardados[str(pr["numero"])]
            vazios = []
            reg["refazer"] = False
            try:
                if orca.worktree_existe(cfg, reg["worktree"]):
                    seletor = f"path:{reg['worktree']}"
                else:
                    wt = _worktree(cfg, repo, info, pr)
                    reg["worktree"], seletor = wt["path"], f"id:{wt['id']}"
                    vazios = _abertos(cfg, seletor)
                    projetos.guardar_preparados(ctx.estado, pid, guardados, "pr")
            except (RuntimeError, OSError, KeyError, IndexError, ValueError) as e:
                problemas.append(f"PR #{pr['numero']}: {e}")
                continue
            _digitar(ctx, pid, projeto, pr, seletor, guardados, feitos, problemas, vazios, tipo="pr", montar=_prompt)
        for pr in novos:
            try:
                wt = _worktree(cfg, repo, info, pr)
                guardados[str(pr["numero"])] = {"titulo": pr["titulo"], "url": pr["url"], "worktree": wt["path"], "digitado": False}
                projetos.guardar_preparados(ctx.estado, pid, guardados, "pr")
                vazios = _abertos(cfg, f"id:{wt['id']}")
            except (RuntimeError, OSError, KeyError, IndexError, ValueError) as e:
                problemas.append(f"PR #{pr['numero']}: {e}")
                continue
            _digitar(ctx, pid, projeto, pr, f"id:{wt['id']}", guardados, feitos, problemas, vazios, tipo="pr", montar=_prompt)
        projetos.guardar_preparados(ctx.estado, pid, guardados, "pr")
    ctx.texto = ("Revisões prontas no Orca, esperando o seu Enter: " + "; ".join(feitos)) if feitos else ""
    resumo = f"{len(feitos)} revisão(ões) pronta(s)" if feitos else "nenhum PR novo para revisar"
    if problemas:
        raise Atencao(f"{resumo} · " + " | ".join(problemas))
    return resumo
