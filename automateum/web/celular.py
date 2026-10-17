"""Acesso de leitura pelo celular, dentro da rede local (opt-in: `[painel] celular = true`).

O painel continua mandando em 127.0.0.1. Com o acesso ligado, ele também escuta na rede, mas só atende:
- clientes e endereços de rede privada (um nome de domínio no Host é recusado: barra DNS rebinding);
- quem trouxe a chave do celular (dados/celular.chave), na primeira visita por ?chave=, depois por cookie;
- pedidos GET de uma lista curta de caminhos de leitura. Nada que roda, liga ou desliga.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
import socket
import time
from pathlib import Path

COOKIE = "mapa_celular"
_LEITURA_EXATA = {"/", "/vivo", "/dados/estado.js", "/api/hoje", "/api/maquina/historico", "/api/grafo", "/favicon.ico"}
_LEITURA_PREFIXO = ("/static/", "/api/no/")
_TENTATIVAS, _JANELA_S = 8, 300


def privado(texto: str) -> bool:
    try:
        ip = ipaddress.ip_address(texto.strip("[]"))
    except ValueError:
        return False
    return ip.is_private and not ip.is_unspecified


def caminho_de_leitura(caminho: str) -> bool:
    return caminho in _LEITURA_EXATA or caminho.startswith(_LEITURA_PREFIXO)


def ips_da_maquina() -> list[str]:
    """Os endereços de rede privada desta máquina (o que o celular digita), sem repetir."""
    achados: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if privado(ip) and not ip.startswith("127.") and not ip.startswith("169.254.") and ip not in achados:
                achados.append(ip)
    except OSError:
        pass
    return achados


class Celular:
    def __init__(self, pasta_dados: Path):
        self._arquivo = pasta_dados / "celular.chave"
        self._falhas: dict[str, list[float]] = {}

    def chave(self) -> str:
        if self._arquivo.exists():
            valor = self._arquivo.read_text(encoding="utf-8").strip()
            if valor:
                return valor
        valor = secrets.token_urlsafe(18)
        self._arquivo.parent.mkdir(parents=True, exist_ok=True)
        self._arquivo.write_text(valor, encoding="utf-8")
        return valor

    def trocar_chave(self) -> str:
        self._arquivo.unlink(missing_ok=True)
        return self.chave()

    def _selo(self) -> str:
        # o cookie guarda um derivado da chave, não a chave
        return hashlib.sha256(b"mapa-celular|" + self.chave().encode()).hexdigest()

    def cookie_ok(self, valor: str) -> bool:
        return hmac.compare_digest(valor or "", self._selo())

    def selo(self) -> str:
        return self._selo()

    def chave_ok(self, tentativa: str) -> bool:
        return hmac.compare_digest(tentativa or "", self.chave())

    def bloqueado(self, ip: str) -> bool:
        agora = time.monotonic()
        recentes = [t for t in self._falhas.get(ip, []) if agora - t < _JANELA_S]
        self._falhas[ip] = recentes
        return len(recentes) >= _TENTATIVAS

    def falhou(self, ip: str) -> None:
        self._falhas.setdefault(ip, []).append(time.monotonic())
