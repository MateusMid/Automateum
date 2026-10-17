from unittest.mock import MagicMock

import pytest
from google.auth.exceptions import RefreshError

from automateum.config import Config
from automateum.nucleo.registro import FALHA, OK
from automateum.servicos import gmail


@pytest.fixture
def cfg(tmp_path):
    return Config(dados={"gmail": {"consulta": "in:inbox is:unread", "max_emails": 5}}, segredos={},
                  pasta_dados=tmp_path)


def _api_falsa(mensagens):
    """Imita users().messages(): list devolve as referências e get devolve cada mensagem."""
    api = MagicMock()
    api.list.return_value.execute.return_value = {"messages": [{"id": m["id"]} for m in mensagens]}
    api.get.side_effect = lambda userId, id, **kw: MagicMock(
        execute=MagicMock(return_value=next(m for m in mensagens if m["id"] == id)))
    servico = MagicMock()
    servico.users.return_value.messages.return_value = api
    return servico, api


def test_configurado_pede_credenciais_depois_login(cfg):
    assert "gmail_credentials.json" in gmail.configurado(cfg)
    (cfg.pasta_dados / "gmail_credentials.json").write_text("{}")
    assert "gmail-login" in gmail.configurado(cfg)
    (cfg.pasta_dados / "gmail_token.json").write_text("{}")
    assert gmail.configurado(cfg) is None


def test_emails_le_cabecalhos_e_respeita_config(cfg, monkeypatch):
    servico, api = _api_falsa([
        {"id": "a1", "snippet": "oi", "internalDate": "1760000000000",
         "payload": {"headers": [{"name": "From", "value": "x@y.com"}, {"name": "Subject", "value": "Olá"}]}},
        {"id": "b2", "internalDate": "1760000100000", "payload": {"headers": []}},
    ])
    monkeypatch.setattr(gmail, "_servico", lambda config: servico)

    itens = gmail.emails(cfg)

    api.list.assert_called_once_with(userId="me", q="in:inbox is:unread", maxResults=5)
    assert [i["chave"] for i in itens] == ["a1", "b2"]
    assert itens[0]["titulo"] == "Olá" and itens[0]["origem"] == "x@y.com" and itens[0]["corpo"] == "oi"
    assert itens[1]["titulo"] == "(sem assunto)" and itens[1]["corpo"] == ""
    assert itens[0]["url"].endswith("#inbox/a1")


def test_checar_mostra_o_endereco_da_conta(cfg, monkeypatch):
    servico = MagicMock()
    servico.users.return_value.getProfile.return_value.execute.return_value = {"emailAddress": "eu@exemplo.com"}
    monkeypatch.setattr(gmail, "_servico", lambda config: servico)
    c = gmail.checar(cfg)
    assert c.estado == OK and c.detalhe == "eu@exemplo.com"


def test_token_expirado_vira_mensagem_clara(cfg, monkeypatch):
    credenciais = MagicMock(valid=False)
    credenciais.refresh.side_effect = RefreshError("invalid_grant")
    monkeypatch.setattr("google.oauth2.credentials.Credentials.from_authorized_user_file",
                        lambda *a, **k: credenciais)
    c = gmail.checar(cfg)
    assert c.estado == FALHA
    assert "expirou" in c.detalhe and "gmail-login" in c.detalhe
    assert "RefreshError" not in c.detalhe
