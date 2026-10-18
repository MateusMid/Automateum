"""Gera a estrutura de dados no formato exato que a interface visual do Léo espera (window.MAPA)."""
from __future__ import annotations

import time
from datetime import datetime

from . import projetos
from .agendador import Agendador
from .estado import Estado, agora
from ..servicos import ia
from .registro import ATENCAO, ESPERA, FALHA, OK, PARADO, RODANDO, ROTINAS, SERVICOS, quando_texto

# Mapeia estados internos do Automateum para os estados da interface do Léo
_MAPA_ESTADO = {
    OK: "bom",
    RODANDO: "bom",
    ESPERA: "duvida",
    ATENCAO: "atencao",
    FALHA: "ruim",
    PARADO: "desligado",
}

_ICONES = {
    "github": "github",
    "slack": "slack",
    "gmail": "gmail",
    "obsidian": "obsidian",
    "claude": "claude",
    "git_local": "git",
}


def montar_mapa_leo(config, estado: Estado, ag: Agendador, celulares: list[dict] | None = None) -> dict:
    checagens = estado.checagens()
    ultimas = estado.ultimas_execucoes()
    avisos = estado.avisos(limite=5, horas=24, pendentes=True)

    m = checagens.get("maquina")
    meta = m["meta"] if m else {}
    nome_pc = meta.get("nome", "PC Mateus")
    sistema_pc = meta.get("sistema", "Windows 11")
    disco_livre = meta.get("disco_livre_gb", 0)
    discos = meta.get("discos") or []
    if "cpu" in meta and "memoria" in meta and discos:
        # espaço que não quebra dentro de cada item: o cartão é estreito e a linha só deve quebrar nos " · "
        itens = [f"CPU {meta['cpu']}%", f"memória {meta['memoria']}%",
                 *(f"{d['nome']} {d['livre_gb']} GB" for d in discos)]
        frase_disco = " · ".join(i.replace(" ", " ") for i in itens) + " livres"
    elif "cpu" in meta and "memoria" in meta:
        frase_disco = f"CPU {meta['cpu']}% · memória {meta['memoria']}% · {disco_livre} GB livres"
    else:
        frase_disco = f"C: com {disco_livre} GB livres" if disco_livre else "Disco operando normalmente"
    boot_str = meta.get("ligada_desde", "")

    # Nó Mesa / Máquina
    mesa_node = {
        "id": "mesa",
        "tipo": "zona",
        "zona": "mesa",
        "rotulo": nome_pc,
        "sub": sistema_pc,
        "oque": "A máquina onde as rotinas do Automateum rodam.",
        "maquina": True,
        "estado": "bom" if (not m or m["estado"] == OK) else _MAPA_ESTADO.get(m["estado"], "atencao"),
        "frase": frase_disco,
        "linhas": [f"{d['nome']} {d['livre_gb']} GB livres de {d['total_gb']} GB ({d['usado_pct']}% usado)"
                   for d in discos] + ([f"ligada desde {boot_str}"] if boot_str else []),
        "esperando": [],
        "causa": None,
    }

    # Nó Internet / Saída
    internet_node = {
        "id": "internet",
        "tipo": "zona",
        "zona": "internet",
        "rotulo": "Internet",
        "sub": "serviços de fora",
        "oque": "Acesso e conectividade de rede do Automateum para APIs e serviços externos.",
        "estado": "bom",
        "frase": "rede e serviços conectados",
        "ms": 25,
        "linhas": [],
        "esperando": [],
        "causa": None,
    }

    nos = [mesa_node, internet_node]
    ligacoes = [
        {
            "id": "mesa~internet",
            "tipo": "ligacao",
            "de": "mesa",
            "para": "internet",
            "rotulo": "saída para a internet",
            "interna": False,
            "estado": "bom",
            "frase": "conectividade de rede ativa",
            "causa": None,
            "linhas": [],
            "esperando": [],
        }
    ]

    # Celulares que estão olhando o painel pela rede local: um cartão embaixo do da máquina, ligado a ela
    for c in celulares or []:
        segundos = max(0, int(time.time() - c["visto"]))
        ligado = segundos <= 180
        cid = f"cel-{c['id']}"
        nos.append({
            "id": cid, "tipo": "zona", "zona": "mesa", "maquina": True, "rotulo": c["nome"], "sub": c["detalhe"] or None,
            "oque": "Aparelho que está vendo este painel pela rede local (só leitura).",
            "estado": "bom" if ligado else "desligado",
            "frase": "conectado agora" if ligado else f"visto há {max(1, segundos // 60)} min",
            "linhas": [f"endereço {c['ip']}"], "esperando": [], "causa": None,
        })
        ligacoes.append({
            "id": f"mesa~{cid}", "tipo": "ligacao", "de": "mesa", "para": cid, "rotulo": "Wi-Fi", "interna": False,
            "estado": "bom" if ligado else "desligado", "frase": "vendo o painel pela rede local",
            "causa": None, "linhas": [], "esperando": [],
        })

    # Serviços (externo)
    for sid, s in SERVICOS.items():
        c = checagens.get(sid)
        motivo = s.configurado(config)
        if motivo:
            est = "desligado"
            frase = motivo
            ms = None
        elif not c:
            est = "duvida"
            frase = "aguardando checagem"
            ms = None
        else:
            est = _MAPA_ESTADO.get(c["estado"], "bom")
            frase = c["detalhe"]
            ms = c.get("ms")

        nos.append({
            "id": sid,
            "tipo": "externo",
            "zona": "internet",
            "rotulo": s.nome,
            "sub": None,
            "oque": s.descricao or f"Serviço {s.nome}",
            "estado": est,
            "frase": frase,
            "ms": ms,
            "linhas": [],
            "esperando": [],
            "causa": None,
            **({"motor": ia.situacao(config, estado)} if sid == "claude" else {}),
        })

    # Frentes (grupos)
    frentes_nomes = list(dict.fromkeys(r.frente for r in ROTINAS.values()))
    for ordem, f_nome in enumerate(frentes_nomes, 1):
        membros = [r for r in ROTINAS.values() if r.frente == f_nome]
        total = len(membros)
        fid = f"frente-{f_nome.lower().replace(' ', '-')}"

        nos.append({
            "id": fid,
            "tipo": "grupo",
            "zona": "mesa",
            "dominio": "trabalho",
            "ordem": ordem,
            "rotulo": f_nome,
            "resumo": f"{total} rotina(s) associada(s)",
            "oque": f"Frente de trabalho {f_nome} do Automateum.",
            "estado": "bom",
            "frase": f"{total} rotina(s) ativas",
            "linhas": [],
            "esperando": [],
            "causa": None,
        })

        # Rotinas dessa frente
        for r in membros:
            rid = r.id
            node_id = f"rot-{rid}"
            u = ultimas.get(rid)
            rodando = ag.rodando(rid)
            quando_str = quando_texto(ag.quando(r))
            proxima = ag.proxima(rid)

            if motivo_p := ag.motivo_parada(r):
                est_r = "desligado"
                frase_r = motivo_p
                passo = "desligada"
            elif rodando:
                est_r = "bom"
                frase_r = "rodando agora…"
                passo = "rodando"
            elif not u:
                est_r = "desligado" if quando_str == "desligada" else "duvida"
                frase_r = "ainda não rodou"
                passo = "nunca"
            else:
                est_r = _MAPA_ESTADO.get(u["status"], "bom")
                frase_r = u["resumo"]
                passo = "codigo"

            ultima_iso = (u["fim"] or u["inicio"]) if u else None
            extra = {}
            if rid == "preparar_prompts":
                # o cartão mostra quais projetos estão ativos; a gaveta traz as chaves de cada um
                extra["projetos"] = projetos.situacao(config, estado)
                if est_r != "desligado" and not rodando and (not u or u["status"] == "ok"):
                    frase_r = projetos.resumo(extra["projetos"])

            nos.append({
                "id": node_id,
                "tipo": "rotina",
                "pai": fid,
                "repete_min": 60,
                "caminho": f"\\Automateum\\{r.nome}",
                "rotulo": r.nome,
                "oque": r.descricao or r.nome,
                "estado": est_r,
                "frase": frase_r,
                "passo": passo,
                "ultima": ultima_iso,
                "proxima": proxima,
                "ligada": est_r != "desligado",
                "resultado": 0 if est_r == "bom" else 1,
                "rodando": rodando,
                "rodar_ok": True,
                "agenda": [[5, 5, 10080]],
                "linhas": [f"Horário: {quando_str}"],
                "esperando": [],
                "causa": None,
                "mede": list(r.usa),
                "zona": "mesa",
                **extra,
            })

            # Ligação da Frente com os Serviços que suas rotinas usam
            for s in r.usa:
                lid = f"{fid}~{s}"
                if not any(l["id"] == lid for l in ligacoes):
                    ligacoes.append({
                        "id": lid,
                        "tipo": "ligacao",
                        "de": fid,
                        "para": s,
                        "rotulo": f"usa {s}",
                        "interna": False,
                        "linhas": [],
                        "esperando": [],
                        "causa": None,
                        "estado": "bom",
                        "frase": f"rotinas de {f_nome} comunicam com {s}",
                    })

    # Um cartão por projeto, ligado à frente "Projetos"; a gaveta dele traz o botão, as issues e os prompts
    fid_proj = next((n["id"] for n in nos if n["tipo"] == "grupo" and n["rotulo"] == "Projetos"), None)
    for p in projetos.situacao(config, estado):
        pid_no = f"proj-{p['id']}"
        livres = [i for i in p["disponiveis"]]
        frase_p = ("desativado" if not p["ativo"] else
                   f"{len(p['prontos'])} prompt(s) pronto(s)" + (f" · {len(livres)} issue(s) esperando" if livres else ""))
        nos.append({
            "id": pid_no, "tipo": "externo", "zona": "internet", "rotulo": p["nome"], "sub": None,
            "oque": f"Projeto {p['nome']} ({p['github']}): issues abertas viram prompt pronto no Orca, nunca enviado.",
            "estado": "bom" if p["ativo"] else "desligado", "frase": frase_p, "ms": None,
            "linhas": [], "esperando": [], "causa": None, "projetos": [p],
        })
        if fid_proj:
            ligacoes.append({"id": f"{fid_proj}~{pid_no}", "tipo": "ligacao", "de": fid_proj, "para": pid_no,
                             "rotulo": "projeto", "interna": False, "linhas": [], "esperando": [], "causa": None,
                             "estado": "bom" if p["ativo"] else "desligado", "frase": f"issues de {p['github']}"})

    # Destino / Com você (Celular / Obsidian / Diário)
    nos.append({
        "id": "celular",
        "tipo": "zona",
        "zona": "celular",
        "rotulo": "Obsidian / Diário",
        "sub": "Notas & Resumos",
        "oque": "Destino final das rotinas do Automateum no cofre pessoal.",
        "estado": "bom",
        "frase": "notas e resumos integrados",
        "linhas": [],
        "esperando": [],
        "causa": None,
    })

    # Avisos do sistema
    esperando = []
    for idx, av in enumerate(avisos):
        esperando.append({
            "id": f"aviso-{idx}",
            "texto": f"{av.get('rotina', 'Aviso')}: {av.get('texto', '')}",
            "prazo": av.get("quando", ""),
            "de": "celular",
            "estado": "dele" if av.get("nivel") == ATENCAO else "ruim",
        })

    historico = {n["id"]: "bbbbbbbbbbbbbbbbbbbbbbbbbbbb" for n in nos}
    for l in ligacoes:
        historico[l["id"]] = "bbbbbbbbbbbbbbbbbbbbbbbbbbbb"

    agora_iso = agora()
    gerado_ms = int(time.time() * 1000)

    return {
        "versao": 2,
        "pagina_versao": 1792051782,
        "gerado": agora_iso,
        "gerado_ms": gerado_ms,
        "duracao_ms": 25,
        "boot": agora_iso,
        "agenda_base": agora_iso,
        "zonas": ["mesa", "internet", "celular"],
        "dominios": {"trabalho": "Trabalho", "pessoal": "Pessoal"},
        "nos": nos,
        "ligacoes": ligacoes,
        "contagem": {
            "bom": sum(1 for n in nos if n["estado"] == "bom"),
            "desligado": sum(1 for n in nos if n["estado"] == "desligado"),
            "construcao": 0,
            "total": len(nos),
        },
        "raizes": [],
        "esperando": esperando,
        "historico": historico,
        "fatia": 5973589,
        "fatia_s": 300,
        "erros_motor": [],
        "prova": None,
        "intervalo_s": 30,
    }
