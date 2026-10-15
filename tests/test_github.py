from automateum.config import Config
from automateum.servicos import github


def test_pendencias_consulta_por_tipo_sem_misturar(monkeypatch):
    consultas = []

    def falso(config, caminho, **params):
        consultas.append(params["q"])
        return {"items": []}

    monkeypatch.setattr(github, "_get", falso)
    github.pendencias(Config(dados={"github": {"repositorios": ["MateusMid/Automateum"]}}))

    assert len(consultas) == 4
    for q in consultas:
        assert ("is:issue" in q) != ("is:pull-request" in q)  # exatamente um tipo por consulta
        assert "repo:MateusMid/Automateum" in q
