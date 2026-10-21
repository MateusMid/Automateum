"""Gmail, só leitura (escopo gmail.readonly): e-mails não lidos da caixa de entrada, de uma ou mais contas.

Cada conta autorizada tem o próprio token em `dados/gmail/<endereço>.json`. O `dados/gmail_token.json` de antes
continua valendo como uma conta até o próximo `gmail-login`, que o muda para a pasta nova.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..config import Config
from ..nucleo.registro import ATENCAO, FALHA, OK, Checagem, registrar_servico

_ESCOPOS = ["https://www.googleapis.com/auth/gmail.readonly"]


@dataclass(frozen=True)
class Conta:
    endereco: str   # vazio no token antigo, do tempo em que só havia uma conta
    token: Path

    @property
    def nome(self) -> str:
        return self.endereco or "conta antiga"


def _credenciais(config: Config) -> Path:
    return config.pasta_dados / "gmail_credentials.json"


def _pasta_contas(config: Config) -> Path:
    return config.pasta_dados / "gmail"


def _token_antigo(config: Config) -> Path:
    return config.pasta_dados / "gmail_token.json"


def contas(config: Config) -> list[Conta]:
    pasta = _pasta_contas(config)
    lista = [Conta(p.stem, p) for p in sorted(pasta.glob("*.json"))] if pasta.is_dir() else []
    if _token_antigo(config).exists():
        lista.append(Conta("", _token_antigo(config)))
    return lista


def configurado(config: Config) -> str | None:
    if not _credenciais(config).exists():
        return "falta dados/gmail_credentials.json (cliente OAuth do Google Cloud)"
    if not contas(config):
        return "rode `python -m automateum gmail-login` para autorizar"
    return None


def _endereco(credenciais) -> str:
    from googleapiclient.discovery import build
    servico = build("gmail", "v1", credentials=credenciais, cache_discovery=False)
    return servico.users().getProfile(userId="me").execute()["emailAddress"]


def login(config: Config) -> list[str]:
    """Abre o navegador para autorizar mais uma conta (ou renovar uma); devolve o que foi feito, para o terminal."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    fluxo = InstalledAppFlow.from_client_secrets_file(str(_credenciais(config)), _ESCOPOS)
    # select_account: o Google pergunta qual conta, em vez de seguir com a que está aberta no navegador
    credenciais = fluxo.run_local_server(port=0, prompt="select_account")
    endereco = _endereco(credenciais)
    _pasta_contas(config).mkdir(parents=True, exist_ok=True)
    (_pasta_contas(config) / f"{endereco}.json").write_text(credenciais.to_json(), encoding="utf-8")
    return [f"{endereco} autorizada."] + _mudar_token_antigo(config)


def _mudar_token_antigo(config: Config) -> list[str]:
    """Leva o `gmail_token.json` para `gmail/<endereço>.json`; vencido, ele não serve para mais nada e sai."""
    antigo = _token_antigo(config)
    if not antigo.exists():
        return []
    try:
        endereco = _endereco(_credenciais_validas(Conta("", antigo)))
    except RuntimeError:
        antigo.unlink()
        return ["O token antigo (gmail_token.json) estava vencido e foi apagado."]
    except Exception as e:
        return [f"O token antigo (gmail_token.json) ficou onde estava: {type(e).__name__}: {e}"]
    novo = _pasta_contas(config) / f"{endereco}.json"
    if novo.exists():
        antigo.unlink()  # a mesma conta acabou de ser autorizada; o token novo vale mais
    else:
        antigo.replace(novo)
    return [f"O token antigo era de {endereco} e foi para dados/gmail/."]


def sair(config: Config, endereco: str) -> bool:
    """Esquece a autorização de uma conta (só apaga o token local). False quando a conta não existe."""
    for conta in contas(config):
        if endereco in (conta.endereco, conta.nome):
            conta.token.unlink()
            return True
    return False


def _credenciais_validas(conta: Conta):
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    credenciais = Credentials.from_authorized_user_file(str(conta.token), _ESCOPOS)
    if not credenciais.valid:
        try:
            credenciais.refresh(Request())
        except RefreshError:
            # No modo "Testing" do Google Cloud o refresh token vence em 7 dias.
            de = f" de {conta.endereco}" if conta.endereco else " do Gmail"
            raise RuntimeError(f"a autorização{de} expirou: rode `python -m automateum gmail-login`") from None
        conta.token.write_text(credenciais.to_json(), encoding="utf-8")
    return credenciais


def _servico(conta: Conta):
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=_credenciais_validas(conta), cache_discovery=False)


def erro(e: Exception) -> str:
    # RuntimeError já traz a mensagem pronta para o painel.
    return str(e) if type(e) is RuntimeError else f"{type(e).__name__}: {e}"


def checar(config: Config) -> Checagem:
    inicio = time.perf_counter()
    lista = contas(config)
    enderecos, falhas = [], []
    for conta in lista:
        try:
            enderecos.append(_servico(conta).users().getProfile(userId="me").execute()["emailAddress"])
        except Exception as e:
            falhas.append(f"{conta.nome}: {erro(e)}" if len(lista) > 1 else erro(e))
    if falhas:
        # uma conta com problema não derruba as outras: o mapa fica amarelo e diz qual é
        return Checagem(ATENCAO if enderecos else FALHA, "; ".join(falhas)[:200], meta={"contas": enderecos})
    return Checagem(OK, ", ".join(enderecos), round((time.perf_counter() - inicio) * 1000), {"contas": enderecos})


def emails(config: Config, conta: Conta, varias: bool = False) -> list[dict]:
    """Não lidos de uma conta. Com `varias`, a origem diz para qual conta veio, para o resumo saber separar."""
    secao = config.secao("gmail")
    api = _servico(conta).users().messages()
    lista = api.list(userId="me", q=secao.get("consulta", "in:inbox is:unread newer_than:2d"),
                     maxResults=secao.get("max_emails", 40)).execute()
    # o endereço no lugar do número abre a caixa certa mesmo com várias contas logadas no navegador
    caixa = f"https://mail.google.com/mail/u/{conta.endereco or 0}/#inbox/"
    itens = []
    for ref in lista.get("messages", []):
        m = api.get(userId="me", id=ref["id"], format="metadata",
                    metadataHeaders=["From", "Subject"]).execute()
        cabecalhos = {h["name"]: h["value"] for h in m["payload"]["headers"]}
        origem = cabecalhos.get("From", "")
        itens.append({
            "chave": m["id"], "titulo": cabecalhos.get("Subject", "(sem assunto)"),
            "corpo": m.get("snippet", ""), "origem": f"{origem} · para {conta.nome}" if varias else origem,
            "url": caixa + m["id"],
            "quando": datetime.fromtimestamp(int(m["internalDate"]) / 1000).isoformat(timespec="seconds")})
    return itens


registrar_servico("gmail", "Gmail", checar, configurado, "E-mails não lidos da caixa de entrada.")
