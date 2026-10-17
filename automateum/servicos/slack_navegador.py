"""Slack pelo navegador: roda o coletor externo (colher.ps1), que lê o Slack web com a sua conta logada,
e converte o texto que ele gera em itens. É a alternativa ao app com token (`[slack] modo = "navegador"`).

O coletor fica fora do repositório; `[slack] kit` aponta para a pasta dele no config.local.toml.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from ..config import Config
from ..nucleo.registro import FALHA, OK, Checagem
from .claude import _SEM_JANELA

_PERFIL = Path.home() / ".slack-rotina"  # onde o coletor guarda o login (fora do seu Chrome do dia a dia)

_HORA = r"(?:\d{1,2}h(?:\d{2})?)"
_QUANDO = rf"(?P<q>(?:\d{{2}}/\d{{2}} )?{_HORA}?)"
_CORPO = r"\s*(?P<autor>.*?)(?: \[(?P<k>s\d+)\])?: (?P<texto>.*)$"
_MENSAGEM = re.compile(rf"^- (?:\((?:thread de mensagem antiga|thread)\) )?{_QUANDO}{_CORPO}")
_RESPOSTA = re.compile(rf"^ {{4}}> {_QUANDO}{_CORPO}")
_DIA_HORA = re.compile(rf"^(?:(\d{{2}})/(\d{{2}}) )?(?:(\d{{1,2}})h(\d{{2}})?)?$")


def _kit(config: Config) -> Path | None:
    kit = config.secao("slack").get("kit", "")
    return Path(kit) if kit else None


def configurado(config: Config) -> str | None:
    kit = _kit(config)
    if kit is None:
        return "defina `kit` em [slack] no config.local.toml (pasta do coletor de Slack)"
    if not (kit / "colher.ps1").exists():
        return f"não achei colher.ps1 em {kit}"
    if not _PERFIL.exists():
        return "falta entrar no Slack: rode logar.ps1 na pasta do coletor"
    return None


def checar(config: Config) -> Checagem:
    # Não abre o navegador a cada checagem; o login que caiu aparece na própria colheita (código 6).
    if motivo := configurado(config):
        return Checagem(FALHA, motivo)
    return Checagem(OK, "coleta pelo navegador (login guardado)")


def _quando(texto: str, hoje: date) -> str:
    """'17/10 14h05', '9h' ou '' -> ISO. Sem dia, vale o dia da colheita; assim a mesma mensagem tem
    o mesmo horário no dia em que era 'hoje' e no dia seguinte, quando o coletor passa a pôr a data."""
    m = _DIA_HORA.match(texto.strip())
    dia, mes, hora, minuto = m.groups() if m else (None, None, None, None)
    data = hoje
    if dia:
        try:
            data = date(hoje.year, int(mes), int(dia))
            if data > hoje + timedelta(days=1):  # 31/12 lido em janeiro
                data = date(hoje.year - 1, int(mes), int(dia))
        except ValueError:
            data = hoje
    try:
        return datetime(data.year, data.month, data.day, int(hora or 0), int(minuto or 0)).isoformat(
            timespec="seconds")
    except ValueError:
        return datetime(data.year, data.month, data.day).isoformat(timespec="seconds")


def converter(texto: str, links: dict, hoje: date, eu: str = "") -> tuple[list[dict], str | None]:
    """Texto do coletor -> (itens, aviso de fonte incompleta).

    Formato: blocos `## conversa`, linhas `- dia hora autor [sN]: texto` e respostas de thread
    `    > dia hora autor [sN]: texto`. `links` traduz cada `[sN]` no link da mensagem.
    """
    aviso = None
    if m := re.search(r"^ATENCAO:.*$", texto, re.M):
        aviso = m.group(0)[:300]
    itens, conversa, vistos = [], None, set()
    for linha in texto.splitlines():
        if linha.startswith("## "):
            conversa = linha[3:].strip()
            continue
        if conversa is None:
            continue
        m = _MENSAGEM.match(linha) or _RESPOSTA.match(linha)
        if not m:
            continue
        autor, corpo = m["autor"].strip() or "?", m["texto"].strip()
        if not corpo or corpo == "[omitida]" or (eu and autor.lower() == eu.lower()):
            continue
        quando = _quando(m["q"], hoje)
        chave = "nav:" + hashlib.sha1(f"{conversa}|{quando}|{autor}|{corpo[:120]}".encode()).hexdigest()[:16]
        if chave in vistos:
            continue
        vistos.add(chave)
        itens.append({"chave": chave, "titulo": f"{autor}: {corpo}"[:2000], "origem": conversa,
                      "quando": quando, "url": (links.get(m["k"]) or {}).get("link", "") if m["k"] else ""})
    return itens, aviso


def _executar(comando: list[str], env: dict, cwd: Path, limite: int) -> tuple[int, str]:
    """Roda o coletor e, se passar do limite, derruba também o node e o Chrome que ele abriu."""
    processo = subprocess.Popen(comando, env=env, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", **_SEM_JANELA)
    try:
        saida, _ = processo.communicate(timeout=limite)
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(processo.pid), "/T", "/F"], capture_output=True,
                           **_SEM_JANELA)
        else:
            processo.kill()
        processo.communicate()
        raise RuntimeError(f"a colheita do Slack passou de {limite // 60} min e foi interrompida") from None
    return processo.returncode, saida or ""


def _limpar(pasta: Path, dias: int = 14) -> None:
    """Apaga o que a colheita deixa cru (com o texto sem máscara) e os textos antigos."""
    for arquivo in pasta.glob("slack-colheita-*"):
        arquivo.unlink(missing_ok=True)
    corte = time.time() - dias * 86400
    for arquivo in [*pasta.glob("slack-????-??-??.txt"), *pasta.glob("slack-????-??-??.txt.links.json")]:
        if arquivo.stat().st_mtime < corte:
            arquivo.unlink(missing_ok=True)


def colher(config: Config, log=print) -> tuple[list[dict], str | None]:
    """Roda o coletor e devolve (itens, aviso de fonte incompleta). Pode levar de 1 a 25 minutos."""
    if motivo := configurado(config):
        raise RuntimeError(motivo)
    secao = config.secao("slack")
    kit, pasta = _kit(config), config.pasta_dados / "slack"
    env = dict(os.environ)
    if fora := secao.get("fora", []):
        env["SLACK_FORA"] = ",".join(fora)
    if secao.get("time"):
        env["SLACK_TIME"] = str(secao["time"])
    comando = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(kit / "colher.ps1"),
               "-Dias", str(int(secao.get("dias", 1))), "-Pasta", str(pasta)]
    codigo, saida = _executar(comando, env, kit, int(secao.get("timeout_segundos", 2700)))
    if codigo == 6:
        raise RuntimeError("o login do Slack caiu: rode logar.ps1 na pasta do coletor e tente de novo")
    if codigo == 5:
        raise RuntimeError("o perfil do Slack está aberto em outra janela: feche e tente de novo")
    if codigo:
        raise RuntimeError(f"a colheita do Slack falhou (código {codigo}): {saida.strip()[-200:]}")
    try:
        textos = sorted(pasta.glob("slack-????-??-??.txt"), key=lambda p: p.stat().st_mtime)
        arquivo = textos[-1]
        links = json.loads(Path(f"{arquivo}.links.json").read_text(encoding="utf-8"))
        texto = arquivo.read_text(encoding="utf-8")
    except (IndexError, OSError, ValueError):
        raise RuntimeError("a colheita terminou, mas não gerou o texto esperado em dados/slack") from None
    itens, aviso = converter(texto, links, date.today(), secao.get("meu_nome", ""))
    _limpar(pasta)
    log(f"{len(itens)} mensagens lidas do texto do coletor")
    return itens, aviso
