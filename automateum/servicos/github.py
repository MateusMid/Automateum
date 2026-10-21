"""GitHub, só leitura: issues e PRs atribuídos a você, os seus PRs e em que pé estão, e revisões pedidas."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from ..config import Config
from ..nucleo.registro import FALHA, OK, Checagem, registrar_servico

_API = "https://api.github.com"
# Em que pé está um PR seu. Os três primeiros pedem uma ação sua.
PROBLEMAS = ("CI falhou", "mudanças pedidas", "conflito")
_CI_RUIM = ("failure", "timed_out", "action_required", "startup_failure")
_MAX_SITUACOES = 20       # cada PR custa quatro chamadas à API
_CONSULTAS = {
    "is:issue": (("assignee:@me", "atribuído"), ("review-requested:@me", "revisão pedida")),
    "is:pull-request": (("assignee:@me", "atribuído"), ("author:@me", "seu"), ("review-requested:@me", "revisão pedida")),
}


def configurado(config: Config) -> str | None:
    return None if config.segredo("GITHUB_TOKEN") else "falta GITHUB_TOKEN no .env"


def _get(config: Config, caminho: str, **parametros) -> dict:
    url = f"{_API}{caminho}" + (f"?{urllib.parse.urlencode(parametros)}" if parametros else "")
    pedido = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {config.segredo('GITHUB_TOKEN')}",
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "automateum"})
    try:
        with urllib.request.urlopen(pedido, timeout=30) as resposta:
            return json.load(resposta)
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", "replace")
        try:
            motivo = json.loads(corpo)["message"]
        except (ValueError, KeyError, TypeError):
            motivo = corpo[:200]
        raise RuntimeError(f"GitHub respondeu {e.code}: {motivo}") from None


def checar(config: Config) -> Checagem:
    inicio = time.perf_counter()
    try:
        usuario = _get(config, "/user")
    except (RuntimeError, OSError) as e:
        return Checagem(FALHA, str(e))
    return Checagem(OK, f"logado como {usuario['login']}", round((time.perf_counter() - inicio) * 1000))


def situacao_do_pr(config: Config, repo: str, numero: int) -> str:
    """Em que pé está o PR: CI falhou, mudanças pedidas, conflito, CI rodando, aprovado, rascunho ou esperando revisão."""
    pr = _get(config, f"/repos/{repo}/pulls/{numero}")
    if pr.get("draft"):
        return "rascunho"
    sha = pr["head"]["sha"]
    # Ler o CI pede as permissões "Checks" e "Commit statuses" no token; sem elas, segue só com as revisões.
    try:
        runs = _get(config, f"/repos/{repo}/commits/{sha}/check-runs", per_page=100).get("check_runs", [])
    except RuntimeError:
        runs = []
    try:
        combinado = _get(config, f"/repos/{repo}/commits/{sha}/status")
    except RuntimeError:
        combinado = {}
    # sem nenhum status, o GitHub responde "pending" mesmo assim: só vale com total_count
    status = combinado.get("state", "") if combinado.get("total_count") else ""
    terminados = [r.get("conclusion") for r in runs if r.get("status") == "completed"]
    ultima: dict[str, str] = {}
    for r in _get(config, f"/repos/{repo}/pulls/{numero}/reviews", per_page=100):
        if r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            ultima[(r.get("user") or {}).get("login", "")] = r["state"]   # vale a última de cada revisor
    if any(c in _CI_RUIM for c in terminados) or status in ("failure", "error"):
        return "CI falhou"
    if "CHANGES_REQUESTED" in ultima.values():
        return "mudanças pedidas"
    if pr.get("mergeable_state") == "dirty":
        return "conflito"
    if len(terminados) < len(runs) or status == "pending":
        return "CI rodando"
    return "aprovado" if "APPROVED" in ultima.values() else "esperando revisão"


def pendencias(config: Config) -> list[dict]:
    """Issues e PRs abertos atribuídos a você, os seus PRs (com em que pé estão) e PRs esperando a sua revisão."""
    repos = config.secao("github").get("repositorios", [])
    filtro = " ".join(f"repo:{r}" for r in repos)
    itens: dict[str, dict] = {}
    # A busca do GitHub exige is:issue ou is:pull-request e não aceita os dois juntos: uma consulta por tipo.
    for tipo_busca, consultas in _CONSULTAS.items():
        for consulta, papel in consultas:
            dados = _get(config, "/search/issues", q=f"is:open {tipo_busca} {consulta} {filtro}".strip(),
                         per_page=100, sort="updated")
            for i in dados.get("items", []):
                repo = i["repository_url"].split("/repos/")[-1]
                tipo = "PR" if "pull_request" in i else "issue"
                item = itens.setdefault(i["html_url"], {
                    "chave": i["html_url"], "titulo": i["title"], "origem": f"{repo} #{i['number']}",
                    "papeis": [], "tipo": tipo, "url": i["html_url"], "quando": i["updated_at"][:10],
                    "repo": repo, "numero": i["number"], "situacao": ""})
                # Um PR pode ser seu e pedir sua revisão ao mesmo tempo: guarda os dois papéis.
                if papel not in item["papeis"]:
                    item["papeis"].append(papel)
    meus = [i for i in itens.values() if i["tipo"] == "PR" and {"seu", "atribuído"} & set(i["papeis"])]
    for i in sorted(meus, key=lambda i: i["quando"], reverse=True)[:_MAX_SITUACOES]:
        i["situacao"] = situacao_do_pr(config, i["repo"], i["numero"])
    return [{"chave": i["chave"], "titulo": i["titulo"], "origem": i["origem"], "url": i["url"], "quando": i["quando"],
             "corpo": " · ".join(p for p in (i["tipo"], ", ".join(i["papeis"]), i["situacao"]) if p)}
            for i in itens.values()]


def precisa_de_voce(item: dict) -> bool:
    """O item é um PR seu com CI falhou, mudanças pedidas ou conflito."""
    return any(item.get("corpo", "").endswith(f" · {p}") for p in PROBLEMAS)


def issues_abertas(config: Config, repo: str, rotulo: str = "") -> list[dict]:
    """Issues abertas de `dono/nome` (sem PRs), da mais antiga para a mais nova; `rotulo` filtra por etiqueta."""
    parametros = {"state": "open", "per_page": 100, "sort": "created", "direction": "asc"}
    if rotulo:
        parametros["labels"] = rotulo
    return [{"numero": i["number"], "titulo": i["title"], "corpo": i.get("body") or "", "url": i["html_url"],
             "atribuidos": [a["login"].lower() for a in i.get("assignees") or []]}
            for i in _get(config, f"/repos/{repo}/issues", **parametros) if "pull_request" not in i]


def prs_para_revisar(config: Config, repo: str, todos: bool = False) -> list[dict]:
    """PRs abertos de `dono/nome` que pedem a sua revisão (ou todos, com `todos`), com o branch e a base de cada um."""
    filtro = "is:pr is:open" + ("" if todos else " review-requested:@me")
    achados = _get(config, "/search/issues", q=f"{filtro} repo:{repo}", per_page=30, sort="updated")
    saida = []
    for i in achados.get("items", []):
        pr = _get(config, f"/repos/{repo}/pulls/{i['number']}")
        saida.append({"numero": pr["number"], "titulo": pr["title"], "corpo": pr.get("body") or "", "url": pr["html_url"],
                      "branch": pr["head"]["ref"], "base": pr["base"]["ref"], "rascunho": bool(pr.get("draft")),
                      "de_fork": (pr["head"].get("repo") or {}).get("full_name", "").lower() != repo.lower()})
    return saida


def meu_login(config: Config) -> str:
    """O login dono do token, em minúsculas: serve para achar as issues atribuídas a você."""
    return str(_get(config, "/user").get("login", "")).lower()


registrar_servico("github", "GitHub", checar, configurado, "Issues e pull requests atribuídos a você.")
