import pytest

from automateum.servicos import claude, copilot


@pytest.fixture(autouse=True)
def clis_instalados(monkeypatch):
    """Os testes não dependem de `claude` nem de `copilot` estarem instalados nesta máquina."""
    monkeypatch.setattr(claude, "_executavel", lambda: "claude")
    monkeypatch.setattr(copilot, "_executavel", lambda: "copilot")
