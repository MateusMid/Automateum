"""Monta o mapa do painel (nós e arestas) a partir do registro e do último estado conhecido."""
from __future__ import annotations

from .agendador import Agendador
from .estado import agora
from .registro import (ATENCAO, ESPERA, FALHA, OK, PARADO, RODANDO, ROTINAS, SERVICOS, quando_texto)

_GRAVIDADE = [PARADO, ESPERA, OK, RODANDO, ATENCAO, FALHA]
_DESTINOS = {"diario": "Diário", "notas": "Notas do Automateum"}


def _pior(estados: list[str]) -> str:
    return max(estados, key=_GRAVIDADE.index) if estados else PARADO


def _hora(iso: str | None) -> str:
    """Hora se for de hoje; senão dia/mês e hora."""
    if not iso:
        return ""
    return iso[11:16] if iso[:10] == agora()[:10] else f"{iso[8:10]}/{iso[5:7]} {iso[11:16]}"


def frentes() -> list[str]:
    return list(dict.fromkeys(r.frente for r in ROTINAS.values()))


def no_servico(sid: str, config, checagens: dict) -> dict:
    s = SERVICOS[sid]
    no = {"id": f"servico:{sid}", "tipo": "servico", "titulo": s.nome, "etiqueta": "", "raiz": False}
    if motivo := s.configurado(config):
        return {**no, "estado": PARADO, "linhas": [motivo]}
    if not (c := checagens.get(sid)):
        return {**no, "estado": ESPERA, "linhas": ["aguardando a primeira checagem"]}
    return {**no, "estado": c["estado"], "linhas": [c["detalhe"]], "raiz": c["estado"] == FALHA,
            "etiqueta": f"{c['ms']} ms" if c["ms"] is not None else ""}


def no_rotina(rid: str, ag: Agendador, ultimas: dict, estados_servico: dict) -> dict:
    r = ROTINAS[rid]
    quando = quando_texto(ag.quando(r))
    no = {"id": f"rotina:{rid}", "tipo": "rotina", "titulo": r.nome, "etiqueta": "", "raiz": False}
    if motivo := ag.motivo_parada(r):
        return {**no, "estado": PARADO, "linhas": [quando, motivo]}
    u = ultimas.get(rid)
    if ag.rodando(rid):
        return {**no, "estado": RODANDO, "linhas": [quando, "rodando agora…"]}
    if not u:
        estado = PARADO if quando == "desligada" else ESPERA
        return {**no, "estado": estado, "linhas": [quando, "ainda não rodou"]}
    # A falha é raiz aqui só se nenhum serviço de que a rotina depende já explica o problema.
    culpados = [SERVICOS[s].nome for s in r.usa if estados_servico.get(s) == FALHA]
    linhas = [f"{_hora(u['fim'] or u['inicio'])} · {quando}", u["resumo"]]
    if u["status"] == FALHA and culpados:
        linhas.append("depende de: " + ", ".join(culpados))
    return {**no, "estado": u["status"], "linhas": [l for l in linhas if l],
            "raiz": u["status"] == FALHA and not culpados}


def montar(config, estado, ag: Agendador) -> dict:
    checagens, ultimas = estado.checagens(), estado.ultimas_execucoes()
    avisos = estado.avisos(limite=3, horas=24, pendentes=True)

    m = checagens.get("maquina")
    meta = m["meta"] if m else {}
    maquina = {"id": "maquina", "tipo": "maquina", "titulo": meta.get("nome", "esta máquina"), "etiqueta": "",
               "estado": m["estado"] if m else ESPERA, "raiz": bool(m) and m["estado"] != OK,
               "linhas": [meta.get("sistema", ""), meta.get("ip", ""),
                          f"ligada desde {meta['ligada_desde']}" if meta else "", m["detalhe"] if m else ""]}
    maquina["linhas"] = [l for l in maquina["linhas"] if l]

    servicos = [no_servico(sid, config, checagens) for sid in SERVICOS]
    estados_servico = {s["id"].split(":")[1]: s["estado"] for s in servicos}
    rotinas = [no_rotina(rid, ag, ultimas, estados_servico) for rid in ROTINAS]
    por_id = {n["id"]: n for n in rotinas}

    nos_frente, arestas = [], []
    for s in servicos:
        arestas.append({"de": "maquina", "para": s["id"], "estado": s["estado"]})
    for f in frentes():
        membros = [r for r in ROTINAS.values() if r.frente == f]
        nos = [por_id[f"rotina:{r.id}"] for r in membros]
        ativos = [n["estado"] for n in nos if n["estado"] != PARADO]
        estado_frente = _pior(ativos)
        problema = next((n for n in nos if n["estado"] in (FALHA, ATENCAO)), None)
        paradas = sum(n["estado"] == PARADO for n in nos)
        linhas = [f"{len(nos)} rotina{'s' if len(nos) != 1 else ''}"
                  + (f" · {paradas} parada{'s' if paradas != 1 else ''}" if paradas else "")]
        if problema:
            linhas.append(f"{problema['titulo']}: {problema['linhas'][-1] if problema['linhas'] else ''}")
        fid = f"frente:{f}"
        nos_frente.append({"id": fid, "tipo": "frente", "titulo": f, "estado": estado_frente,
                           "linhas": linhas, "etiqueta": "", "raiz": False})
        usados = list(dict.fromkeys(s for r in membros for s in r.usa))
        for sid in usados:
            arestas.append({"de": f"servico:{sid}", "para": fid, "estado": estados_servico[sid]})
        if not usados:
            arestas.append({"de": "maquina", "para": fid, "estado": estado_frente})
        for n in nos:
            arestas.append({"de": fid, "para": n["id"], "estado": n["estado"]})

    destinos = []
    for did, titulo in _DESTINOS.items():
        fontes = [r for r in ROTINAS.values() if did in r.entrega]
        if not fontes:
            continue
        feitas = [ultimas[r.id] for r in fontes if r.id in ultimas and ultimas[r.id]["status"] == OK]
        ultima = max(feitas, key=lambda u: u["fim"] or "", default=None)
        destinos.append({"id": f"destino:{did}", "tipo": "destino", "titulo": titulo, "etiqueta": "Obsidian",
                         "estado": OK if ultima else ESPERA, "raiz": False,
                         "linhas": [f"{_hora(ultima['fim'])} · {ultima['resumo']}"] if ultima
                         else ["nada escrito ainda"]})
        for r in fontes:
            arestas.append({"de": f"rotina:{r.id}", "para": f"destino:{did}",
                            "estado": por_id[f"rotina:{r.id}"]["estado"]})
    destinos.append({"id": "destino:avisos", "tipo": "destino", "titulo": "Avisos", "etiqueta": "24 h",
                     "estado": _pior([a["nivel"] for a in avisos]) if avisos else OK, "raiz": False,
                     "linhas": [f"{_hora(a['quando'])} · {a['texto']}" for a in avisos]
                     or ["nenhum aviso nas últimas 24 h"]})
    for rid in dict.fromkeys(a["rotina"] for a in avisos if a["rotina"] in ROTINAS):
        nivel = _pior([a["nivel"] for a in avisos if a["rotina"] == rid])
        arestas.append({"de": f"rotina:{rid}", "para": "destino:avisos", "estado": nivel})

    return {
        "gerado": agora(),
        "colunas": [
            {"titulo": "MÁQUINA", "nos": [maquina]},
            {"titulo": "SERVIÇOS", "nos": servicos},
            {"titulo": "FRENTES", "nos": nos_frente},
            {"titulo": "ROTINAS", "nos": rotinas},
            {"titulo": "COM VOCÊ", "nos": destinos},
        ],
        "arestas": arestas,
    }
