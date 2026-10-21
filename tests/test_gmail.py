from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.auth.exceptions import RefreshError

from automateum.config import Config
from automateum.nucleo.registro import ATENCAO, FALHA, OK
from automateum.rotinas import coletar_gmail
from automateum.servicos import gmail


@pytest.fixture
def cfg(tmp_path):
    return Config(dados={"gmail": {"consulta": "in:inbox is:unread", "max_emails": 5}}, segredos={},
                  pasta_dados=tmp_path)


def _autorizar(cfg, *enderecos):
    (cfg.pasta_dados / "gmail").mkdir(exist_ok=True)
    for e in enderecos:
        (cfg.pasta_dados / "gmail" / f"{e}.json").write_text("{}")


def _api_falsa(mensagens):
    """Imita users().messages(): list devolve as referências e get devolve cada mensagem."""
    api = MagicMock()
    api.list.return_value.execute.return_value = {"messages": [{"id": m["id"]} for m in mensagens]}
    api.get.side_effect = lambda userId, id, **kw: MagicMock(
        execute=MagicMock(return_value=next(m for m in mensagens if m["id"] == id)))
    servico = MagicMock()
    servico.users.return_value.messages.return_value = api
    return servico, api


def _perfil(endereco):
    servico = MagicMock()
    servico.users.return_value.getProfile.return_value.execute.return_value = {"emailAddress": endereco}
    return servico


def _mensagem(id, assunto="Olá"):
    return {"id": id, "snippet": "oi", "internalDate": "1760000000000",
            "payload": {"headers": [{"name": "From", "value": "x@y.com"}, {"name": "Subject", "value": assunto}]}}


def test_configurado_pede_credenciais_depois_login(cfg):
    assert "gmail_credentials.json" in gmail.configurado(cfg)
    (cfg.pasta_dados / "gmail_credentials.json").write_text("{}")
    assert "gmail-login" in gmail.configurado(cfg)
    _autorizar(cfg, "eu@exemplo.com")
    assert gmail.configurado(cfg) is None


def test_token_antigo_ainda_conta_como_uma_conta(cfg):
    (cfg.pasta_dados / "gmail_credentials.json").write_text("{}")
    (cfg.pasta_dados / "gmail_token.json").write_text("{}")
    assert gmail.configurado(cfg) is None
    assert [c.nome for c in gmail.contas(cfg)] == ["conta antiga"]
    _autorizar(cfg, "b@exemplo.com", "a@exemplo.com")
    assert [c.nome for c in gmail.contas(cfg)] == ["a@exemplo.com", "b@exemplo.com", "conta antiga"]


def test_emails_le_cabecalhos_e_respeita_config(cfg, monkeypatch):
    servico, api = _api_falsa([
        _mensagem("a1"),
        {"id": "b2", "internalDate": "1760000100000", "payload": {"headers": []}},
    ])
    monkeypatch.setattr(gmail, "_servico", lambda conta: servico)
    _autorizar(cfg, "eu@exemplo.com")

    itens = gmail.emails(cfg, gmail.contas(cfg)[0])

    api.list.assert_called_once_with(userId="me", q="in:inbox is:unread", maxResults=5)
    assert [i["chave"] for i in itens] == ["a1", "b2"]
    assert itens[0]["titulo"] == "Olá" and itens[0]["origem"] == "x@y.com" and itens[0]["corpo"] == "oi"
    assert itens[1]["titulo"] == "(sem assunto)" and itens[1]["corpo"] == ""
    assert itens[0]["url"] == "https://mail.google.com/mail/u/eu@exemplo.com/#inbox/a1"


def test_com_varias_contas_a_origem_diz_a_conta(cfg, monkeypatch):
    servico, _ = _api_falsa([_mensagem("a1")])
    monkeypatch.setattr(gmail, "_servico", lambda conta: servico)
    itens = gmail.emails(cfg, gmail.Conta("eu@trabalho.com", cfg.pasta_dados / "x.json"), varias=True)
    assert itens[0]["origem"] == "x@y.com · para eu@trabalho.com"
    antigo = gmail.emails(cfg, gmail.Conta("", cfg.pasta_dados / "gmail_token.json"))
    assert antigo[0]["url"].startswith("https://mail.google.com/mail/u/0/")


def test_checar_mostra_o_endereco_de_cada_conta(cfg, monkeypatch):
    _autorizar(cfg, "a@exemplo.com", "b@exemplo.com")
    monkeypatch.setattr(gmail, "_servico", lambda conta: _perfil(conta.endereco))
    c = gmail.checar(cfg)
    assert c.estado == OK and c.detalhe == "a@exemplo.com, b@exemplo.com"
    assert c.meta == {"contas": ["a@exemplo.com", "b@exemplo.com"]}


def test_uma_conta_vencida_deixa_o_servico_em_atencao(cfg, monkeypatch):
    _autorizar(cfg, "a@exemplo.com", "b@exemplo.com")

    def servico(conta):
        if conta.endereco == "b@exemplo.com":
            raise RuntimeError("a autorização de b@exemplo.com expirou: rode `python -m automateum gmail-login`")
        return _perfil(conta.endereco)
    monkeypatch.setattr(gmail, "_servico", servico)

    c = gmail.checar(cfg)
    assert c.estado == ATENCAO
    assert c.detalhe.startswith("b@exemplo.com: a autorização de b@exemplo.com expirou")
    assert c.meta == {"contas": ["a@exemplo.com"]}


def test_token_expirado_vira_mensagem_clara(cfg, monkeypatch):
    credenciais = MagicMock(valid=False)
    credenciais.refresh.side_effect = RefreshError("invalid_grant")
    monkeypatch.setattr("google.oauth2.credentials.Credentials.from_authorized_user_file",
                        lambda *a, **k: credenciais)
    _autorizar(cfg, "eu@exemplo.com")
    c = gmail.checar(cfg)
    assert c.estado == FALHA
    assert "eu@exemplo.com expirou" in c.detalhe and "gmail-login" in c.detalhe
    assert "RefreshError" not in c.detalhe


def test_login_guarda_a_conta_e_muda_o_token_antigo(cfg, monkeypatch):
    fluxo = MagicMock()
    fluxo.run_local_server.return_value.to_json.return_value = '{"novo": 1}'
    monkeypatch.setattr("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
                        lambda *a, **k: fluxo)
    monkeypatch.setattr(gmail, "_credenciais_validas", lambda conta: "antigas")
    monkeypatch.setattr(gmail, "_endereco", lambda credenciais: "velha@exemplo.com" if credenciais == "antigas"
                        else "nova@exemplo.com")
    (cfg.pasta_dados / "gmail_token.json").write_text('{"antigo": 1}')

    saida = gmail.login(cfg)

    assert fluxo.run_local_server.call_args.kwargs["prompt"] == "select_account"
    assert saida[0] == "nova@exemplo.com autorizada."
    assert not (cfg.pasta_dados / "gmail_token.json").exists()
    assert (cfg.pasta_dados / "gmail" / "velha@exemplo.com.json").read_text() == '{"antigo": 1}'
    assert [c.nome for c in gmail.contas(cfg)] == ["nova@exemplo.com", "velha@exemplo.com"]


def test_login_apaga_o_token_antigo_vencido(cfg, monkeypatch):
    def vencido(conta):
        raise RuntimeError("expirou")
    monkeypatch.setattr(gmail, "_credenciais_validas", vencido)
    (cfg.pasta_dados / "gmail_token.json").write_text("{}")
    assert "vencido" in gmail._mudar_token_antigo(cfg)[0]
    assert not (cfg.pasta_dados / "gmail_token.json").exists()


def test_sair_apaga_so_o_token_da_conta(cfg):
    _autorizar(cfg, "a@exemplo.com", "b@exemplo.com")
    assert gmail.sair(cfg, "a@exemplo.com")
    assert not gmail.sair(cfg, "c@exemplo.com")
    assert [c.nome for c in gmail.contas(cfg)] == ["b@exemplo.com"]


def _ctx(cfg):
    estado = MagicMock()
    estado.juntar_itens.side_effect = lambda fonte, itens: len(itens)
    return SimpleNamespace(config=cfg, estado=estado, log=MagicMock())


def test_coleta_guarda_as_contas_boas_quando_uma_falha(cfg, monkeypatch):
    _autorizar(cfg, "a@exemplo.com", "b@exemplo.com")

    def emails(config, conta, varias=False):
        assert varias
        if conta.endereco == "b@exemplo.com":
            raise RuntimeError("a autorização de b@exemplo.com expirou")
        return [{"chave": "a1"}]
    monkeypatch.setattr(gmail, "emails", emails)
    ctx = _ctx(cfg)

    r = coletar_gmail.rodar(ctx)

    assert r.estado == ATENCAO and r.resumo.startswith("1 novos · 1 não lidos · b@exemplo.com:")
    ctx.estado.juntar_itens.assert_called_once_with("gmail", [{"chave": "a1"}])


def test_coleta_falha_quando_todas_as_contas_falham(cfg, monkeypatch):
    _autorizar(cfg, "a@exemplo.com")

    def emails(config, conta, varias=False):
        raise RuntimeError("a autorização de a@exemplo.com expirou")
    monkeypatch.setattr(gmail, "emails", emails)

    with pytest.raises(RuntimeError, match="a@exemplo.com"):
        coletar_gmail.rodar(_ctx(cfg))
