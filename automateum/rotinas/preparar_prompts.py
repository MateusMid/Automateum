import re
import unicodedata

from ..nucleo import projetos
from ..nucleo.registro import Atencao, rotina
from ..servicos import github, orca

_POR_RODADA = 2
_ACEITAS_POR_RODADA = 5


def _nome(numero: int, titulo: str, prefixo: str = "issue") -> str:
    base = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    return f"{prefixo}-{numero}-" + (re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:40].strip("-") or "task")


def _prompt(projeto: dict, issue: dict) -> str:
    modelo = projeto.get("modelo") or projetos.MODELO
    return modelo.format(numero=issue["numero"], titulo=issue["titulo"], url=issue["url"],
                         corpo=(issue["corpo"] or "(sem descrição)").strip())


def _abertos(cfg, seletor) -> list[str]:
    try:
        return orca.terminais(cfg, seletor)
    except RuntimeError:
        return []


def _digitar(ctx, pid, projeto, issue, seletor, guardados, feitos, problemas, vazios=(), tipo="issue", montar=_prompt):
    """Abre o Claude Code na worktree e deixa o prompt digitado. Nunca envia."""
    cfg = ctx.config
    try:
        handle = orca.abrir_agente(cfg, seletor, f"#{issue['numero']}")
        orca.fechar_terminais(cfg, list(vazios))   # o Orca abre um shell vazio na worktree nova; o do Claude fica sozinho
        if not orca.esperar_pronto(cfg, handle):
            problemas.append(f"#{issue['numero']}: o Claude Code demorou para abrir; use Digitar de novo")
            return
        texto = montar(projeto, issue)
        projetos.guardar_texto(cfg, pid, issue["numero"], orca.limpar(texto), tipo)
        orca.digitar(cfg, handle, texto)
        guardados[str(issue["numero"])]["digitado"] = True
        projetos.guardar_preparados(ctx.estado, pid, guardados, tipo)
        feitos.append(f"#{issue['numero']} {issue['titulo']}")
        ctx.log(f"#{issue['numero']}: prompt digitado (sem enviar)")
    except (RuntimeError, OSError, KeyError, IndexError, ValueError) as e:   # inclui `modelo` com chave desconhecida
        problemas.append(f"#{issue['numero']}: {e}")


@rotina(id="preparar_prompts", nome="prompts das tasks", frente="Projetos", quando="cada 15m",
        usa=["github", "orca"])
def rodar(ctx):
    """Deixa pronto no Orca o prompt de cada issue aberta dos projetos ativos. Digitado, nunca enviado."""
    cfg = ctx.config
    ativos = {pid: p for pid, p in projetos.lista(cfg).items() if projetos.ativo(cfg, ctx.estado, pid)}
    if not ativos:
        return "nenhum projeto ativo"
    if not orca.aberto(cfg):
        return orca.FECHADO
    feitos, problemas = [], []
    for pid, projeto in ativos.items():
        repo = orca.repo_id(cfg, projeto["github"])
        if not repo:
            problemas.append(f"{projeto.get('nome', pid)}: o repositório {projeto['github']} não está no Orca")
            continue
        issues = github.issues_abertas(cfg, projeto["github"], projeto.get("rotulo", ""))
        eu = github.meu_login(cfg)
        for i in issues:
            i["minha"] = bool(eu) and eu in i.get("atribuidos", [])
        projetos.guardar_abertas(ctx.estado, pid, issues)   # a gaveta lista as que esperam o "Começar"
        abertas = {str(i["numero"]) for i in issues}
        guardados = {n: d for n, d in projetos.preparados(ctx.estado, pid).items() if n in abertas}  # fechada = libera a vaga
        fora = projetos.dispensadas(ctx.estado, pid)
        if any(n not in abertas for n in fora):   # dispensada que fechou não precisa mais ficar na lista
            projetos.guardar_dispensadas(ctx.estado, pid, {n: d for n, d in fora.items() if n in abertas})
        aceitas = set(projetos.aceitas(ctx.estado, pid))
        vagas = max(0, int(projeto.get("max_pendentes", 3)) - len(guardados))
        livres = [i for i in issues if str(i["numero"]) not in guardados and str(i["numero"]) not in fora]
        # as que você aceitou passam na frente e não gastam vaga; as atribuídas a você entram enquanto houver vaga
        novas = [i for i in livres if i["numero"] in aceitas][:_ACEITAS_POR_RODADA]
        novas += [i for i in livres if i["minha"] and i["numero"] not in aceitas][:min(vagas, _POR_RODADA)]
        # as que você pediu para digitar de novo (fechou o terminal, por exemplo): a worktree já existe, só abre outro terminal
        refazer = [i for i in issues if guardados.get(str(i["numero"]), {}).get("refazer")]
        for issue in refazer:
            reg = guardados[str(issue["numero"])]
            vazios = []
            reg["refazer"] = False   # uma tentativa por pedido: se falhar, é só pedir de novo
            try:
                if orca.worktree_existe(cfg, reg["worktree"]):
                    seletor = f"path:{reg['worktree']}"
                else:   # você removeu a worktree no Orca: cria de novo
                    wt = orca.criar_worktree(cfg, repo, _nome(issue["numero"], issue["titulo"]), issue["numero"],
                                             "Preparado pelo Automateum")
                    reg["worktree"], seletor = wt["path"], f"id:{wt['id']}"
                    vazios = _abertos(cfg, seletor)
                    projetos.guardar_preparados(ctx.estado, pid, guardados)
            except (RuntimeError, OSError, KeyError, IndexError, ValueError) as e:
                problemas.append(f"#{issue['numero']}: {e}")
                continue
            _digitar(ctx, pid, projeto, issue, seletor, guardados, feitos, problemas, vazios)
        for issue in novas:
            nome = _nome(issue["numero"], issue["titulo"])
            try:
                wt = orca.criar_worktree(cfg, repo, nome, issue["numero"], "Preparado pelo Automateum")
                # a worktree já existe: guarda antes de seguir, para uma falha adiante não criar outra na próxima rodada
                guardados[str(issue["numero"])] = {"titulo": issue["titulo"], "url": issue["url"], "worktree": wt["path"],
                                                   "digitado": False}
                projetos.guardar_preparados(ctx.estado, pid, guardados)
                vazios = _abertos(cfg, f"id:{wt['id']}")
            except (RuntimeError, OSError, KeyError, IndexError, ValueError) as e:
                problemas.append(f"#{issue['numero']}: {e}")
                continue
            _digitar(ctx, pid, projeto, issue, f"id:{wt['id']}", guardados, feitos, problemas, vazios)
        projetos.guardar_preparados(ctx.estado, pid, guardados)
    ctx.texto = ("Prompts prontos no Orca, esperando o seu Enter: " + "; ".join(feitos)) if feitos else ""
    resumo = f"{len(feitos)} prompt(s) pronto(s)" if feitos else "nada novo para preparar"
    if problemas:
        raise Atencao(f"{resumo} · " + " | ".join(problemas))
    return resumo
