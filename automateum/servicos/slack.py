"""Slack, só leitura: mensagens novas das conversas em que você está."""
from __future__ import annotations

import time
from datetime import datetime

from ..config import Config
from ..nucleo.registro import FALHA, OK, Checagem, registrar_servico


def configurado(config: Config) -> str | None:
    return None if config.segredo("SLACK_TOKEN") else "falta SLACK_TOKEN no .env"


def _cliente(config: Config):
    from slack_sdk import WebClient
    from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler
    cliente = WebClient(token=config.segredo("SLACK_TOKEN"), timeout=30)
    cliente.retry_handlers.append(RateLimitErrorRetryHandler(max_retry_count=2))
    return cliente


def checar(config: Config) -> Checagem:
    inicio = time.perf_counter()
    try:
        quem = _cliente(config).auth_test()
    except Exception as e:
        return Checagem(FALHA, f"{type(e).__name__}: {e}"[:200])
    return Checagem(OK, f"{quem['user']} em {quem['team']}", round((time.perf_counter() - inicio) * 1000))


def mensagens_novas(config: Config, cursores: dict[str, str], log=print) -> tuple[list[dict], dict[str, str]]:
    """Mensagens de outras pessoas desde o cursor de cada conversa (ou das últimas 24h na primeira vez).

    Devolve (itens, cursores atualizados); o cursor é o `ts` da última mensagem vista.
    """
    secao = config.secao("slack")
    cliente = _cliente(config)
    eu = cliente.auth_test()["user_id"]
    quero = {c.lstrip("#").lower() for c in secao.get("canais", [])}

    conversas, pagina = [], None
    while True:
        r = cliente.users_conversations(types=",".join(secao.get("tipos", ["public_channel", "im"])),
                                        exclude_archived=True, limit=200, cursor=pagina)
        conversas += r["channels"]
        pagina = (r.get("response_metadata") or {}).get("next_cursor")
        if not pagina:
            break
    if quero:
        conversas = [c for c in conversas if (c.get("name") or "").lower() in quero]
    conversas = conversas[: secao.get("max_conversas", 60)]

    nomes: dict[str, str] = {}

    def nome(usuario: str) -> str:
        if usuario and usuario not in nomes:
            try:
                u = cliente.users_info(user=usuario)["user"]
                nomes[usuario] = u.get("real_name") or u.get("name") or usuario
            except Exception:
                nomes[usuario] = usuario
        return nomes.get(usuario, "alguém")

    itens, novos = [], dict(cursores)
    ontem = f"{time.time() - 86400:.6f}"
    for c in conversas:
        titulo = f"#{c['name']}" if c.get("name") else f"DM {nome(c.get('user', ''))}"
        try:
            r = cliente.conversations_history(channel=c["id"], oldest=cursores.get(c["id"], ontem), limit=100)
        except Exception as e:
            log(f"{titulo}: {type(e).__name__}: {e}")
            continue
        mensagens = r.get("messages", [])
        if mensagens:
            novos[c["id"]] = max(m["ts"] for m in mensagens)
        for m in mensagens:
            if m.get("user") == eu or m.get("subtype") or not m.get("text"):
                continue
            itens.append({"chave": f"{c['id']}:{m['ts']}", "titulo": f"{nome(m.get('user', ''))}: {m['text']}"[:2000],
                          "origem": titulo,
                          "quando": datetime.fromtimestamp(float(m["ts"])).isoformat(timespec="seconds")})
    return itens, novos


registrar_servico("slack", "Slack", checar, configurado, "Mensagens dos canais e DMs em que você está.")
