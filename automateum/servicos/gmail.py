"""Gmail, só leitura (escopo gmail.readonly): e-mails não lidos da caixa de entrada."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from ..config import Config
from ..nucleo.registro import FALHA, OK, Checagem, registrar_servico

_ESCOPOS = ["https://www.googleapis.com/auth/gmail.readonly"]


def _credenciais(config: Config) -> Path:
    return config.pasta_dados / "gmail_credentials.json"


def _token(config: Config) -> Path:
    return config.pasta_dados / "gmail_token.json"


def configurado(config: Config) -> str | None:
    if not _credenciais(config).exists():
        return "falta dados/gmail_credentials.json (cliente OAuth do Google Cloud)"
    if not _token(config).exists():
        return "rode `python -m automateum gmail-login` para autorizar"
    return None


def login(config: Config) -> None:
    """Abre o navegador uma vez para autorizar a leitura; o token fica em dados/."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    fluxo = InstalledAppFlow.from_client_secrets_file(str(_credenciais(config)), _ESCOPOS)
    credenciais = fluxo.run_local_server(port=0)
    _token(config).write_text(credenciais.to_json(), encoding="utf-8")


def _servico(config: Config):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from google.auth.exceptions import RefreshError
    credenciais = Credentials.from_authorized_user_file(str(_token(config)), _ESCOPOS)
    if not credenciais.valid:
        try:
            credenciais.refresh(Request())
        except RefreshError:
            # No modo "Testing" do Google Cloud o refresh token vence em 7 dias.
            raise RuntimeError("a autorização do Gmail expirou: rode `python -m automateum gmail-login`") from None
        _token(config).write_text(credenciais.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=credenciais, cache_discovery=False)


def checar(config: Config) -> Checagem:
    inicio = time.perf_counter()
    try:
        perfil = _servico(config).users().getProfile(userId="me").execute()
    except Exception as e:
        # RuntimeError já traz a mensagem pronta para o painel.
        return Checagem(FALHA, (str(e) if type(e) is RuntimeError else f"{type(e).__name__}: {e}")[:200])
    return Checagem(OK, perfil["emailAddress"], round((time.perf_counter() - inicio) * 1000))


def emails(config: Config) -> list[dict]:
    secao = config.secao("gmail")
    api = _servico(config).users().messages()
    lista = api.list(userId="me", q=secao.get("consulta", "in:inbox is:unread newer_than:2d"),
                     maxResults=secao.get("max_emails", 40)).execute()
    itens = []
    for ref in lista.get("messages", []):
        m = api.get(userId="me", id=ref["id"], format="metadata",
                    metadataHeaders=["From", "Subject"]).execute()
        cabecalhos = {h["name"]: h["value"] for h in m["payload"]["headers"]}
        itens.append({
            "chave": m["id"], "titulo": cabecalhos.get("Subject", "(sem assunto)"),
            "corpo": m.get("snippet", ""), "origem": cabecalhos.get("From", ""),
            "url": f"https://mail.google.com/mail/u/0/#inbox/{m['id']}",
            "quando": datetime.fromtimestamp(int(m["internalDate"]) / 1000).isoformat(timespec="seconds")})
    return itens


registrar_servico("gmail", "Gmail", checar, configurado, "E-mails não lidos da caixa de entrada.")
