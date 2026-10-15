"""GitHub, só leitura: issues e PRs atribuídos a você e revisões pedidas."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from ..config import Config
from ..nucleo.registro import FALHA, OK, Checagem, registrar_servico

_API = "https://api.github.com"


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


def pendencias(config: Config) -> list[dict]:
    """Issues e PRs abertos atribuídos a você, mais PRs esperando a sua revisão."""
    repos = config.secao("github").get("repositorios", [])
    filtro = " ".join(f"repo:{r}" for r in repos)
    itens: dict[str, dict] = {}
    # A busca do GitHub exige is:issue ou is:pull-request e não aceita os dois juntos: uma consulta por tipo.
    for tipo_busca in ("is:issue", "is:pull-request"):
        for consulta, papel in (("assignee:@me", "atribuído"), ("review-requested:@me", "revisão pedida")):
            dados = _get(config, "/search/issues", q=f"is:open {tipo_busca} {consulta} {filtro}".strip(),
                         per_page=100, sort="updated")
            for i in dados.get("items", []):
                repo = i["repository_url"].split("/repos/")[-1]
                tipo = "PR" if "pull_request" in i else "issue"
                itens.setdefault(i["html_url"], {
                    "chave": i["html_url"], "titulo": i["title"], "origem": f"{repo} #{i['number']}",
                    "corpo": f"{tipo} · {papel}", "url": i["html_url"], "quando": i["updated_at"][:10]})
    return list(itens.values())


registrar_servico("github", "GitHub", checar, configurado, "Issues e pull requests atribuídos a você.")
