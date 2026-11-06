"""Google Calendar (Agenda) para leitura de reuniões e eventos.

Utiliza as credenciais OAuth e tokens salvos da conta Google.
"""
from __future__ import annotations

import re
import time
import unicodedata
from datetime import date, datetime, time as hora, timedelta
from pathlib import Path

from ..config import Config
from ..nucleo.registro import ATENCAO, FALHA, OK, Checagem, registrar_servico
from . import gmail

_SEM_AUTORIZACAO = (
    "sem autorização para ler a agenda: rode `python -m automateum gmail-login` de novo "
    "e confira se a Google Calendar API está ativada"
)


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
            erro = _SEM_AUTORIZACAO if getattr(getattr(e, "resp", None), "status", None) == 403 else gmail.erro(e)
            falhas.append(f"{conta.nome}: {erro}" if len(lista) > 1 else erro)
    if falhas:
        return Checagem(ATENCAO if enderecos else FALHA, "; ".join(falhas)[:200], meta={"contas": enderecos})
    return Checagem(OK, ", ".join(enderecos), round((time.perf_counter() - inicio) * 1000), {"contas": enderecos})


def intervalo_dias(hoje: date | None = None, dias: int = 2) -> tuple[str, str]:
    """Retorna limites ISO 8601 locais, com fuso, para hoje até o início de `dias` dias depois."""
    hoje = hoje or datetime.now().date()
    inicio = datetime.combine(hoje, hora.min).astimezone()
    fim = datetime.combine(hoje + timedelta(days=dias), hora.min).astimezone()
    return inicio.isoformat(), fim.isoformat()


def _local_iso(valor: str) -> str:
    """Normaliza início/fim do Calendar para o horário local, mantendo datas de evento integral."""
    if len(valor) == 10:
        return f"{valor}T00:00:00"
    return datetime.fromisoformat(valor.replace("Z", "+00:00")).astimezone().replace(tzinfo=None).isoformat(
        timespec="seconds")


def _evento(conta: gmail.Conta, ev: dict) -> dict | None:
    if ev.get("status") == "cancelled":
        return None
    inicio_info, fim_info = ev.get("start", {}), ev.get("end", {})
    inicio_str = inicio_info.get("dateTime") or inicio_info.get("date")
    fim_str = fim_info.get("dateTime") or fim_info.get("date") or inicio_str
    if not inicio_str:
        return None

    dia_inteiro = "date" in inicio_info
    inicio_local, fim_local = _local_iso(inicio_str), _local_iso(fim_str)
    meet_url = ev.get("hangoutLink")
    if not meet_url:
        meet_url = next((ep.get("uri") for ep in ev.get("conferenceData", {}).get("entryPoints", [])
                         if ep.get("entryPointType") == "video"), None)
    participantes = [p.get("displayName") or p.get("email") for p in ev.get("attendees", []) if not p.get("resource")]
    titulo = ev.get("summary") or "(Sem título)"
    horario = "dia inteiro" if dia_inteiro else f"{inicio_local[11:16]}–{fim_local[11:16]}"
    if ev.get("location"):
        horario += f" · {ev['location']}"
    chave = f"{conta.endereco or conta.nome}:{ev.get('id', '')}"
    return {
        "id": ev.get("id"), "chave": chave, "conta": conta.nome, "titulo": titulo,
        "descricao": ev.get("description", ""), "inicio": inicio_str, "fim": fim_str,
        "dia_inteiro": dia_inteiro, "meet_url": meet_url, "html_link": ev.get("htmlLink"),
        "participantes": participantes, "status": ev.get("status"),
        "corpo": horario, "origem": conta.nome, "url": ev.get("htmlLink"), "quando": inicio_local,
    }


def eventos_conta_periodo(config: Config, conta: gmail.Conta, inicio_iso: str, fim_iso: str) -> list[dict]:
    """Lista e normaliza todos os eventos de uma conta, incluindo cada instância recorrente."""
    cal = _servico(conta)
    resultado, pagina = [], None
    while True:
        parametros = {"calendarId": "primary", "timeMin": inicio_iso, "timeMax": fim_iso,
                      "singleEvents": True, "orderBy": "startTime", "maxResults": 2500}
        if pagina:
            parametros["pageToken"] = pagina
        try:
            resposta = cal.events().list(**parametros).execute()
        except Exception as e:
            if getattr(getattr(e, "resp", None), "status", None) == 403:
                raise RuntimeError(_SEM_AUTORIZACAO) from None
            raise
        resultado.extend(evento for ev in resposta.get("items", []) if (evento := _evento(conta, ev)))
        pagina = resposta.get("nextPageToken")
        if not pagina:
            break
    return resultado


def eventos_periodo(config: Config, inicio_iso: str, fim_iso: str) -> list[dict]:
    """Lista eventos da agenda entre `inicio_iso` e `fim_iso` (strings ISO 8601)."""
    resultado = []
    for conta in contas(config):
        try:
            resultado.extend(eventos_conta_periodo(config, conta, inicio_iso, fim_iso))
        except Exception:
            continue
    resultado.sort(key=lambda x: x["quando"] or "")
    return resultado


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", texto))


def _nomes_em_comum(falas: list[str], participantes: list[str]) -> int:
    pessoas = [_normalizar(p) for p in falas if _normalizar(p) not in ("eu", "")]
    convidados = [_normalizar(p.split("@", 1)[0]) for p in participantes]
    return sum(1 for pessoa in pessoas if any(
        pessoa == convidado or (min(len(pessoa), len(convidado)) >= 4 and
                                (pessoa in convidado or convidado in pessoa))
        for convidado in convidados if convidado
    ))


def _similaridade_titulos(a: str, b: str) -> float:
    ignorar = {"com", "para", "por", "uma", "the", "and", "meeting", "reuniao"}
    palavras_a = {p for p in _normalizar(a).split() if len(p) > 2 and p not in ignorar}
    palavras_b = {p for p in _normalizar(b).split() if len(p) > 2 and p not in ignorar}
    return len(palavras_a & palavras_b) / len(palavras_a | palavras_b) if palavras_a | palavras_b else 0.0


def vincular_transcricoes(config: Config, eventos: list[dict], *, incluir_texto: bool = False) -> list[dict]:
    """Relaciona eventos a transcrições do mesmo dia, início próximo e participantes/título compatíveis."""
    from . import obsidian, reunioes

    resultado = [dict(evento) for evento in eventos]
    datas = set()
    inicios = []
    for indice, evento in enumerate(resultado):
        try:
            inicio = datetime.fromisoformat(evento["inicio"])
        except (KeyError, TypeError, ValueError):
            inicios.append(None)
            continue
        if evento.get("dia_inteiro") or evento.get("status") == "cancelled":
            inicios.append(None)
            continue
        inicios.append(inicio)
        datas.add(inicio.astimezone().date().isoformat())

    transcricoes = []
    for transcricao in reunioes.transcricoes(config):
        if transcricao["dia"] not in datas:
            continue
        dados = reunioes.ler(transcricao["arquivo"])
        if not dados["inicio"]:
            continue
        inicio = datetime.combine(datetime.fromisoformat(transcricao["dia"]).date(),
                                  datetime.strptime(dados["inicio"], "%H:%M").time())
        transcricoes.append({**transcricao, "dados": dados, "inicio_local": inicio})

    candidatos_por_evento: dict[int, list[tuple[tuple[int, float, int], int]]] = {}
    candidatos_por_transcricao: dict[int, list[tuple[tuple[int, float, int], int]]] = {}
    for i, (evento, inicio) in enumerate(zip(resultado, inicios)):
        if inicio is None:
            continue
        dia = inicio.astimezone().date()
        for j, transcricao in enumerate(transcricoes):
            if transcricao["dia"] != dia.isoformat():
                continue
            minutos = abs((inicio.astimezone().replace(tzinfo=None) - transcricao["inicio_local"]).total_seconds()) / 60
            if minutos > 15:
                continue
            dados = transcricao["dados"]
            rank = (_nomes_em_comum(dados["quem"], evento.get("participantes", [])),
                    _similaridade_titulos(dados["titulo"], evento.get("titulo", "")), -round(minutos * 1000))
            candidatos_por_evento.setdefault(i, []).append((rank, j))
            candidatos_por_transcricao.setdefault(j, []).append((rank, i))

    def unico_melhor(opcoes):
        if not opcoes:
            return None
        ordenadas = sorted(opcoes, key=lambda x: x[0], reverse=True)
        if len(ordenadas) > 1 and ordenadas[0][0] == ordenadas[1][0]:
            return None
        return ordenadas[0]

    melhores_evento = {i: unico_melhor(opcoes) for i, opcoes in candidatos_por_evento.items()}
    melhores_transcricao = {j: unico_melhor(opcoes) for j, opcoes in candidatos_por_transcricao.items()}
    pasta_propria = config.secao("obsidian").get("pasta_automateum", "Automateum")
    for i, melhor in melhores_evento.items():
        if melhor is None:
            continue
        rank, j = melhor
        outro = melhores_transcricao.get(j)
        if outro is None or outro[1] != i:
            continue
        transcricao, dados = transcricoes[j], transcricoes[j]["dados"]
        hora = dados["inicio"].replace(":", "h")
        nome = " ".join(p for p in (transcricao["dia"], hora,
                                      transcricao["chave"].rsplit("/", 1)[-1]) if p)
        relativa = f"{pasta_propria}/Reuniões/{nome}.md"
        nota = obsidian.ler_nota(config, relativa)
        partes = nota.split("\n\n", 2)
        resumo = partes[2].strip() if len(partes) == 3 else ""
        vinculada = {"titulo": dados["titulo"], "arquivo": transcricao["arquivo"].name,
                     "falas": dados["falas"], "nota": relativa if nota else None,
                     "resumo": resumo}
        if incluir_texto:
            vinculada["texto"] = dados["texto"]
        resultado[i]["transcricao"] = vinculada
    return resultado


registrar_servico("agenda", "Google Agenda", checar, configurado, "Eventos e reuniões do Google Calendar.")
