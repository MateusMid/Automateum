"""Google Calendar (Agenda) para leitura de reuniões e eventos.

Utiliza as credenciais OAuth e tokens salvos da conta Google.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from ..config import Config
from ..nucleo.registro import ATENCAO, FALHA, OK, Checagem, registrar_servico
from . import gmail


def configurado(config: Config) -> str | None:
    return gmail.configurado(config)


def contas(config: Config) -> list[gmail.Conta]:
    return gmail.contas(config)


def _servico(conta: gmail.Conta):
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=gmail._credenciais_validas(conta), cache_discovery=False)


def checar(config: Config) -> Checagem:
    inicio = time.perf_counter()
    lista = contas(config)
    enderecos, falhas = [], []
    for conta in lista:
        try:
            cal = _servico(conta)
            meta = cal.calendars().get(calendarId="primary").execute()
            enderecos.append(meta.get("id") or conta.nome)
        except Exception as e:
            falhas.append(f"{conta.nome}: {gmail.erro(e)}" if len(lista) > 1 else gmail.erro(e))
    if falhas:
        return Checagem(ATENCAO if enderecos else FALHA, "; ".join(falhas)[:200], meta={"contas": enderecos})
    return Checagem(OK, ", ".join(enderecos), round((time.perf_counter() - inicio) * 1000), {"contas": enderecos})


def eventos_periodo(config: Config, inicio_iso: str, fim_iso: str) -> list[dict]:
    """Lista eventos da agenda entre `inicio_iso` e `fim_iso` (strings ISO 8601)."""
    resultado = []
    for conta in contas(config):
        try:
            cal = _servico(conta)
            res = cal.events().list(
                calendarId="primary",
                timeMin=inicio_iso,
                timeMax=fim_iso,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            for ev in res.get("items", []):
                inicio_info = ev.get("start", {})
                fim_info = ev.get("end", {})
                inicio_str = inicio_info.get("dateTime") or inicio_info.get("date")
                fim_str = fim_info.get("dateTime") or fim_info.get("date")
                
                # Links de videoconferência (Google Meet / Hangouts / Zoom)
                meet_url = ev.get("hangoutLink")
                if not meet_url and "conferenceData" in ev:
                    for ep in ev["conferenceData"].get("entryPoints", []):
                        if ep.get("entryPointType") == "video":
                            meet_url = ep.get("uri")
                            break
                            
                participantes = [
                    p.get("displayName") or p.get("email")
                    for p in ev.get("attendees", [])
                    if not p.get("resource")
                ]

                resultado.append({
                    "id": ev.get("id"),
                    "conta": conta.nome,
                    "titulo": ev.get("summary", "(Sem título)"),
                    "descricao": ev.get("description", ""),
                    "inicio": inicio_str,
                    "fim": fim_str,
                    "dia_inteiro": "date" in inicio_info,
                    "meet_url": meet_url,
                    "html_link": ev.get("htmlLink"),
                    "participantes": participantes,
                    "status": ev.get("status"),
                })
        except Exception:
            continue
            
    resultado.sort(key=lambda x: x["inicio"] or "")
    return resultado


registrar_servico("agenda", "Google Agenda", checar, configurado, "Eventos e reuniões do Google Calendar.")
