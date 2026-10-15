"""Lê o config.toml, config.local.toml e o .env.

AUTOMATEUM_CONFIG, AUTOMATEUM_CONFIG_LOCAL e AUTOMATEUM_DADOS trocam os caminhos (usado nos testes).
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _ler_env(caminho: Path) -> dict[str, str]:
    valores: dict[str, str] = {}
    if not caminho.exists():
        return valores
    for linha in caminho.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


@dataclass
class Config:
    dados: dict = field(default_factory=dict)
    segredos: dict[str, str] = field(default_factory=dict)
    pasta_dados: Path = RAIZ / "dados"

    def secao(self, nome: str) -> dict:
        return self.dados.get(nome, {})

    def segredo(self, nome: str) -> str:
        return os.environ.get(nome) or self.segredos.get(nome, "")

    @property
    def cofre(self) -> Path:
        return Path(self.secao("obsidian").get("cofre", ""))

    @property
    def banco(self) -> Path:
        return self.pasta_dados / "automateum.db"


def _mesclar(base: dict, sobre: dict) -> dict:
    resultado = dict(base)
    for k, v in sobre.items():
        if k in resultado and isinstance(resultado[k], dict) and isinstance(v, dict):
            resultado[k] = _mesclar(resultado[k], v)
        else:
            resultado[k] = v
    return resultado


def carregar() -> Config:
    caminho = Path(os.environ.get("AUTOMATEUM_CONFIG") or RAIZ / "config.toml")
    dados = tomllib.loads(caminho.read_text(encoding="utf-8-sig")) if caminho.exists() else {}

    caminho_local = Path(os.environ.get("AUTOMATEUM_CONFIG_LOCAL") or RAIZ / "config.local.toml")
    if caminho_local.exists():
        dados_local = tomllib.loads(caminho_local.read_text(encoding="utf-8-sig"))
        dados = _mesclar(dados, dados_local)

    pasta_dados = Path(os.environ.get("AUTOMATEUM_DADOS") or RAIZ / "dados")
    pasta_dados.mkdir(parents=True, exist_ok=True)
    return Config(dados=dados, segredos=_ler_env(RAIZ / ".env"), pasta_dados=pasta_dados)

