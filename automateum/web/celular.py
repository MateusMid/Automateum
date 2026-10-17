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
import re
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


def descrever(user_agent: str, modelo_dica: str = "") -> tuple[str, str]:
    """(nome, detalhe) do aparelho pelo que o navegador conta de si.

    O Chrome do Android esconde o modelo ("Android 10; K") e o iPhone nunca o diz, e a dica de modelo
    (Sec-CH-UA-Model) só vem em HTTPS: nesses casos o nome cai para "Celular Android" ou "iPhone".
    """
    ua = user_agent or ""
    modelo = (modelo_dica or "").strip().strip('"')
    navegador = next((n for t, n in (("SamsungBrowser", "Samsung Internet"), ("EdgA", "Edge"), ("Firefox", "Firefox"),
                                     ("FxiOS", "Firefox"), ("CriOS", "Chrome"), ("Chrome", "Chrome"),
                                     ("Safari", "Safari")) if t in ua), "")
    if (m := re.search(r"iPhone|iPad", ua)):
        versao = re.search(r"OS (\d+)[_.](\d+)", ua)
        return m.group(0), " · ".join(x for x in (f"iOS {versao.group(1)}.{versao.group(2)}" if versao else "iOS", navegador) if x)
    if (a := re.search(r"Android ([\d.]+)(?:; ([^;)]+))?", ua)):
        achado = a.group(2) or ""
        if not modelo and achado.strip() not in ("", "K", "Mobile", "wv"):
            modelo = achado.strip()
        return modelo or "Celular Android", " · ".join(x for x in (f"Android {a.group(1)}", navegador) if x)
    return modelo or "Aparelho na rede", navegador


class Celular:
    def __init__(self, pasta_dados: Path):
        self._arquivo = pasta_dados / "celular.chave"
        self._falhas: dict[str, list[float]] = {}
        self._vistos: dict[str, dict] = {}

    def visto(self, ip: str, user_agent: str, modelo_dica: str = "") -> None:
        """Anota um aparelho que acabou de pedir o painel (já autenticado)."""
        id_ = hashlib.sha1(f"{ip}|{user_agent}".encode()).hexdigest()[:8]
        nome, detalhe = descrever(user_agent, modelo_dica)
        self._vistos[id_] = {"id": id_, "ip": ip, "nome": nome, "detalhe": detalhe, "visto": time.time()}

    def conectados(self, agora: float | None = None, janela_s: int = 900) -> list[dict]:
        """Aparelhos vistos nos últimos `janela_s` segundos, o mais recente primeiro (no máximo 3)."""
        agora = time.time() if agora is None else agora
        vivos = [v for v in self._vistos.values() if agora - v["visto"] <= janela_s]
        return sorted(vivos, key=lambda v: -v["visto"])[:3]

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
