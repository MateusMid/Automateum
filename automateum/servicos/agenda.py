"""Google Agenda, só leitura (escopo calendar.readonly): os eventos de hoje e de amanhã da agenda principal de cada conta.

Usa a mesma autorização do Gmail (`gmail-login`), que passou a pedir também a agenda. Quem não autorizou de novo
recebe a mensagem para refazer o login. Nenhuma função daqui cria, altera ou aceita evento.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta

from ..config import Config
from ..nucleo.registro import ATENCAO, FALHA, OK, Checagem, registrar_servico
from . import gmail

DIAS = 2   # hoje e amanhã
_SEM_AUTORIZACAO = "a autorização não cobre a agenda: rode `python -m automateum gmail-login` de novo"


def _servico(conta: gmail.Conta):
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=gmail._credenciais_validas(conta), cache_discovery=False)


def _local(valor: str) -> str:
    """Um horário com fuso (ou só a data, de evento de dia inteiro) -> ISO no horário desta máquina, sem fuso."""
    if len(valor) == 10:   # dia inteiro: "AAAA-MM-DD"
        return f"{valor}T00:00"
    return datetime.fromisoformat(valor).astimezone().replace(tzinfo=None).isoformat(timespec="minutes")


def _corpo(evento: dict) -> str:
    inicio, fim = evento["start"], evento.get("end", {})
    if "date" in inicio:
        return "dia inteiro"
    a, b = _local(inicio["dateTime"]), _local(fim.get("dateTime", inicio["dateTime"]))
    return f"{a[11:]} às {b[11:]}" + (f" · {evento['location']}" if evento.get("location") else "")


def eventos(config: Config, conta: gmail.Conta, hoje: date | None = None) -> list[dict]:
    """Os eventos de hoje e de amanhã de uma conta (instâncias de eventos recorrentes; cancelados ficam de fora)."""
    hoje = hoje or date.today()
    inicio = datetime.combine(hoje, datetime.min.time()).astimezone().isoformat()
    fim = datetime.combine(hoje + timedelta(days=DIAS), datetime.min.time()).astimezone().isoformat()
    try:
        lista = _servico(conta).events().list(calendarId="primary", timeMin=inicio, timeMax=fim, singleEvents=True,
                                              orderBy="startTime", maxResults=250).execute()
    except Exception as e:
        if getattr(getattr(e, "resp", None), "status", None) == 403:
            raise RuntimeError(_SEM_AUTORIZACAO) from None
        raise
    saida = []
    for ev in lista.get("items", []):
        if ev.get("status") == "cancelled":
            continue
        inicio_ev = ev.get("start", {})
        quando = _local(inicio_ev.get("dateTime") or inicio_ev.get("date", hoje.isoformat()))
        saida.append({"chave": f"{conta.endereco}:{ev['id']}", "titulo": ev.get("summary", "(sem título)"),
                      "corpo": _corpo(ev), "origem": conta.nome, "url": ev.get("htmlLink", ""), "quando": quando})
    return saida


def checar(config: Config) -> Checagem:
    inicio = time.perf_counter()
    lista = gmail.contas(config)
    falhas = []
    for conta in lista:
        try:
            _servico(conta).calendarList().get(calendarId="primary").execute()
        except Exception as e:
            falhas.append(_SEM_AUTORIZACAO if getattr(getattr(e, "resp", None), "status", None) == 403 else gmail.erro(e))
    if falhas:
        return Checagem(ATENCAO if len(falhas) < len(lista) else FALHA, "; ".join(falhas)[:200])
    return Checagem(OK, f"{len(lista)} agenda(s)", round((time.perf_counter() - inicio) * 1000))


def configurado(config: Config) -> str | None:
    return gmail.configurado(config)


registrar_servico("agenda", "Google Agenda", checar, configurado, "Eventos de hoje e amanhã, só leitura.")
