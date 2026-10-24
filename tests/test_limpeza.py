import subprocess

import pytest

from automateum.config import Config
from automateum.nucleo import projetos
from automateum.nucleo.estado import Estado
from automateum.servicos import orca


def _git(caminho, *args):
    return subprocess.run(["git", "-C", str(caminho), *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    """Um clone com remoto (um repositório vazio fazendo papel de GitHub), como uma worktree de verdade."""
    origem = tmp_path / "remoto.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origem)], check=True)
    clone = tmp_path / "wt"
    subprocess.run(["git", "clone", "-q", str(origem), str(clone)], check=True, capture_output=True)
    _git(clone, "config", "user.email", "t@t.t")
    _git(clone, "config", "user.name", "t")
    (clone / "a.txt").write_text("1", encoding="utf-8")
    _git(clone, "add", "a.txt")
    _git(clone, "commit", "-q", "-m", "inicial")
    _git(clone, "push", "-q", "-u", "origin", "HEAD")
    return clone


def test_pendencias_recusa_arquivo_modificado_commit_sem_enviar_e_branch_sem_remoto(repo, tmp_path):
    assert orca.pendencias(str(repo)) is None                       # limpa e enviada

    (repo / "a.txt").write_text("2", encoding="utf-8")
    assert "sem commit" in orca.pendencias(str(repo))
    _git(repo, "checkout", "-q", "--", "a.txt")

    (repo / "novo.txt").write_text("x", encoding="utf-8")            # arquivo novo também conta
    assert "sem commit" in orca.pendencias(str(repo))
    (repo / "novo.txt").unlink()

    _git(repo, "commit", "-q", "--allow-empty", "-m", "local")
    assert "1 commit(s) sem enviar" in orca.pendencias(str(repo))
    _git(repo, "push", "-q")
    assert orca.pendencias(str(repo)) is None

    _git(repo, "checkout", "-q", "-b", "sem-remoto")
    assert "não tem remoto" in orca.pendencias(str(repo))


def test_caminho_que_nao_existe_nao_tem_pendencia(tmp_path):
    assert orca.pendencias(str(tmp_path / "sumiu")) is None


def _config(tmp_path):
    return Config(dados={"projetos": {"x": {"github": "d/r", "nome": "X"}}}, segredos={}, pasta_dados=tmp_path)


def test_lista_so_o_que_fechou_ou_foi_dispensado(tmp_path):
    estado = Estado(tmp_path / "e.db")
    projetos.guardar_abertas(estado, "x", [{"numero": 1, "titulo": "Aberta", "url": ""}])
    projetos.guardar_preparados(estado, "x", {
        "1": {"titulo": "Aberta", "worktree": "C:/wt/1"},
        "2": {"titulo": "Fechou", "worktree": "C:/wt/2"},
        "3": {"titulo": "Sem worktree", "worktree": ""},
    })
    projetos.guardar_dispensadas(estado, "x", {"4": {"titulo": "Dispensada", "worktree": "C:/wt/4"}})

    assert [(c["numero"], c["motivo"]) for c in projetos.limpaveis(estado, "x")] == [(2, "issue fechada"), (4, "dispensada")]
    assert projetos.situacao(_config(tmp_path), estado)[0]["limpar"] == projetos.limpaveis(estado, "x")


def test_sem_leitura_de_issues_nao_chuta_fechada(tmp_path):
    estado = Estado(tmp_path / "e.db")
    projetos.guardar_preparados(estado, "x", {"2": {"titulo": "Talvez", "worktree": "C:/wt/2"}})
    assert projetos.limpaveis(estado, "x") == []


def test_apagar_so_com_worktree_limpa_e_tira_o_registro(tmp_path, monkeypatch):
    cfg, estado = _config(tmp_path), Estado(tmp_path / "e.db")
    projetos.guardar_abertas(estado, "x", [{"numero": 1, "titulo": "Aberta", "url": ""}])
    projetos.guardar_preparados(estado, "x", {"2": {"titulo": "Fechou", "worktree": "C:/wt/2"}})
    removidas = []
    monkeypatch.setattr(orca, "pendencias", lambda caminho: None)
    monkeypatch.setattr(orca, "worktree_existe", lambda config, caminho: True)
    monkeypatch.setattr(orca, "remover_worktree", lambda config, caminho: removidas.append(caminho))

    projetos.apagar_worktree(cfg, estado, "x", 2)

    assert removidas == ["C:/wt/2"]
    assert projetos.preparados(estado, "x") == {}


def test_apagar_recusa_com_pendencia_e_nao_mexe_em_nada(tmp_path, monkeypatch):
    cfg, estado = _config(tmp_path), Estado(tmp_path / "e.db")
    projetos.guardar_abertas(estado, "x", [{"numero": 1, "titulo": "Aberta", "url": ""}])
    projetos.guardar_preparados(estado, "x", {"2": {"titulo": "Fechou", "worktree": "C:/wt/2"}})
    removidas = []
    monkeypatch.setattr(orca, "pendencias", lambda caminho: "2 commit(s) sem enviar")
    monkeypatch.setattr(orca, "remover_worktree", lambda config, caminho: removidas.append(caminho))

    with pytest.raises(ValueError, match="2 commit"):
        projetos.apagar_worktree(cfg, estado, "x", 2)
    assert removidas == [] and "2" in projetos.preparados(estado, "x")


def test_apagar_so_aceita_o_que_esta_na_lista(tmp_path):
    cfg, estado = _config(tmp_path), Estado(tmp_path / "e.db")
    projetos.guardar_abertas(estado, "x", [{"numero": 1, "titulo": "Aberta", "url": ""}])
    projetos.guardar_preparados(estado, "x", {"1": {"titulo": "Aberta", "worktree": "C:/wt/1"}})
    with pytest.raises(ValueError, match="não está na lista"):
        projetos.apagar_worktree(cfg, estado, "x", 1)
