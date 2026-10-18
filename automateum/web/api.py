"""API e painel. Escuta só em 127.0.0.1."""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import secrets
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import rotinas, servicos  # noqa: F401  (registram rotinas e serviços)
from ..config import Config
from ..nucleo import grafo, mapa_leo, projetos, saidas
from ..nucleo.agendador import Agendador
from ..nucleo.estado import Estado, agora
from ..nucleo.eventos import Barramento
from ..nucleo.registro import ATENCAO, FALHA, OK, ROTINAS, SERVICOS, quando_texto
from ..servicos import ia, maquina
from . import celular as acesso_celular

_ESTATICOS = Path(__file__).parent / "static"
_LOCAIS = {"127.0.0.1", "localhost"}
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class _Estaticos(StaticFiles):
    """Arquivos do painel que o navegador revalida a cada carga (ETag): sem isso ele guarda o JS antigo
    e uma atualização do painel só aparece depois de um recarregar forçado."""

    async def get_response(self, path, scope):
        resposta = await super().get_response(path, scope)
        resposta.headers["Cache-Control"] = "no-cache"
        return resposta


def _erro(status: int, mensagem: str) -> JSONResponse:
    # o mapa lê "erro" nas respostas de ação
    return JSONResponse({"erro": mensagem}, status_code=status)


# Código que o mapa espera para cada estado de execução: 0 ok, -1 aviso, 1 falha.
_CODIGO = {OK: 0, ATENCAO: -1, FALHA: 1}


def _abrir_no_sistema(uri: str) -> None:
    """Entrega o endereço ao programa registrado para ele (o Obsidian, para obsidian://)."""
    if sys.platform == "win32":
        os.startfile(uri)  # noqa: S606
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", uri])


def criar_app(config: Config) -> FastAPI:
    estado = Estado(config.banco)
    eventos = Barramento()
    agendador = Agendador(config, estado, eventos)
    # Token da sessão: vai só para a página local (acoes.js). Ações exigem também a origem local.
    token = secrets.token_urlsafe(24)
    porta = int(config.secao("painel").get("porta", 8765))
    # leitura pelo celular na rede local: desligada, a não ser que o config.local.toml peça
    celular = acesso_celular.Celular(config.pasta_dados) if config.secao("painel").get("celular") else None

    def _token_ok(request: Request) -> bool:
        return hmac.compare_digest(request.headers.get("x-mapa-token", ""), token)

    def _origem_local(request: Request) -> bool:
        origem = request.headers.get("origin")
        return origem is not None and urlsplit(origem).hostname in _LOCAIS

    @asynccontextmanager
    async def vida(app: FastAPI):
        agendador.iniciar()
        yield
        agendador.parar()

    app = FastAPI(title="Automateum", lifespan=vida, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.agendador, app.state.estado = agendador, estado
    app.state.celular = celular

    def _recusa(status: int, texto: str) -> Response:
        return HTMLResponse("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                            f"<body style='font:16px system-ui;padding:24px;background:#0c0c0b;color:#ecebe6'>{texto}", status_code=status)

    async def _de_fora(request: Request, host: str, origem: str | None, seguir):
        """Pedido que não veio do próprio computador: só leitura, da rede privada, com a chave do celular."""
        ip = request.client.host if request.client else ""
        if not (acesso_celular.privado(ip) and acesso_celular.privado(host)):
            return JSONResponse({"detail": "origem não permitida"}, status_code=403)
        if origem and urlsplit(origem).hostname != host:
            return JSONResponse({"detail": "origem não permitida"}, status_code=403)
        if request.method not in ("GET", "HEAD") or not acesso_celular.caminho_de_leitura(request.url.path):
            return JSONResponse({"detail": "o celular só lê o painel"}, status_code=403)
        if celular.bloqueado(ip):
            return _recusa(429, "Muitas tentativas. Aguarde alguns minutos.")
        if celular.cookie_ok(request.cookies.get(acesso_celular.COOKIE, "")):
            celular.visto(ip, request.headers.get("user-agent", ""), request.headers.get("sec-ch-ua-model", ""))
            return await seguir(request)
        tentativa = request.query_params.get("chave")
        if tentativa is not None:
            if not celular.chave_ok(tentativa):
                celular.falhou(ip)
                return _recusa(401, "Chave errada. Abra a página <b>/celular</b> no computador e use o QR code de lá.")
            resposta = RedirectResponse(request.url.path or "/", status_code=303)
            resposta.set_cookie(acesso_celular.COOKIE, celular.selo(), max_age=60 * 60 * 24 * 90, httponly=True, samesite="strict")
            return resposta
        return _recusa(401, "Acesso do celular: abra no computador a página <b>/celular</b> e leia o QR code de lá.")

    @app.middleware("http")
    async def so_local(request: Request, seguir):
        # Barra páginas de outros sites (CSRF) e DNS rebinding: só o próprio painel fala com a API.
        host = (request.headers.get("host") or "").rsplit(":", 1)[0]
        origem = request.headers.get("origin")
        if host in _LOCAIS:
            # com a rede aberta, "Host: 127.0.0.1" vindo de outro aparelho não pode valer como local
            if celular and (request.client.host if request.client else "") not in _LOOPBACK | {"testclient"}:
                return JSONResponse({"detail": "origem não permitida"}, status_code=403)
            if origem and urlsplit(origem).hostname not in _LOCAIS:
                return JSONResponse({"detail": "origem não permitida"}, status_code=403)
            return await seguir(request)
        if celular is None:
            return JSONResponse({"detail": "origem não permitida"}, status_code=403)
        return await _de_fora(request, host, origem, seguir)

    @app.get("/celular")
    def pagina_celular():
        """Só no computador: o endereço (com a chave) e o QR code para abrir o painel no celular."""
        if celular is None:
            return _recusa(200, "O acesso pelo celular está desligado. No <code>config.local.toml</code> ponha "
                                "<code>celular = true</code> em <code>[painel]</code> e reinicie o Automateum.")
        chave = celular.chave()
        links = [f"http://{ip}:{porta}/?chave={chave}" for ip in acesso_celular.ips_da_maquina()]
        try:
            import segno
            qrs = [segno.make(l, error="m").svg_inline(scale=6, dark="#000", light="#fff", border=2) for l in links]
        except ImportError:
            qrs = ["" for _ in links]
        corpo = "<h2>Painel no celular</h2><p>O celular precisa estar no mesmo Wi-Fi que este computador. Só leitura.</p>"
        for l, q in zip(links, qrs):
            corpo += f"<div style='margin:16px 0'>{q}</div><p><code style='word-break:break-all'>{l}</code></p>"
        if not links:
            corpo += "<p>Não achei o endereço de rede deste computador. Conecte-se a uma rede e recarregue.</p>"
        corpo += ("<p style='color:#8d8b84'>A chave fica só neste computador (dados/celular.chave). Quem tiver o endereço acima "
                  "lê o painel enquanto estiver na sua rede. Para invalidar, apague esse arquivo e reinicie.</p>")
        return _recusa(200, corpo)

    @app.get("/")
    def painel():
        return FileResponse(_ESTATICOS / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/dados/estado.js")
    def estado_js():
        dados = mapa_leo.montar_mapa_leo(config, estado, agendador, celular.conectados() if celular else [])
        js = f"window.MAPA = {json.dumps(dados, ensure_ascii=False)};"
        from fastapi.responses import Response
        return Response(content=js, media_type="application/javascript", headers={"Cache-Control": "no-store"})

    @app.get("/dados/acoes.js")
    def acoes_js():
        js = f"window.MAPA_ACOES = {json.dumps({'porta': porta, 'token': token})};"
        return Response(content=js, media_type="application/javascript", headers={"Cache-Control": "no-store"})

    @app.get("/vivo")
    def vivo():
        return {"ok": True}

    @app.post("/acao")
    async def acao(request: Request):
        # POST de outra origem sempre traz Origin; exigir a origem local fecha o CSRF mesmo com o token.
        if not (_origem_local(request) and _token_ok(request)):
            return _erro(403, "sem permissão")
        try:
            nome = str((await request.json()).get("acao", ""))
        except (ValueError, AttributeError):
            return _erro(400, "pedido inválido")
        tipo, _, alvo = nome.partition(":")
        alvo = alvo.removeprefix("rot-")  # o mapa manda o id do nó ("rot-<rotina>"), não o da rotina
        if nome == "medir-agora":
            tipo, alvo = "rodar", "saude"
        if tipo in ("ligar", "desligar") and alvo in ROTINAS:
            agendador.ligar(alvo, ligada=tipo == "ligar")
            return {"id": 0}  # sem rodada para acompanhar: /estado/0 responde como concluído
        if tipo == "motor" and alvo in ia.MOTORES:
            ia.definir(estado, alvo)
            return {"id": 0}
        if tipo in ("projeto-ligar", "projeto-desligar") and alvo in projetos.lista(config):
            projetos.definir(config, estado, alvo, tipo == "projeto-ligar")
            return {"id": 0}
        if tipo == "abrir-nota" and alvo in ROTINAS:
            # o navegador embutido do Orca bloqueia links obsidian://; o servidor abre a nota neste computador
            achada = saidas.nota(config, alvo)
            if not achada or not achada["obsidian"].startswith("obsidian://open?"):
                return _erro(404, "essa rotina ainda não tem nota no cofre")
            try:
                _abrir_no_sistema(achada["obsidian"])
            except OSError as e:
                return _erro(500, f"não consegui abrir o Obsidian: {e}")
            return {"id": 0}
        if tipo in ("revisao-todos-ligar", "revisao-todos-desligar") and alvo in projetos.lista(config):
            projetos.definir_revisar_todos(config, estado, alvo, tipo == "revisao-todos-ligar")
            if tipo == "revisao-todos-ligar":   # procura já, sem esperar os 15 minutos
                exec_id = agendador.disparar("preparar_revisoes")
                return {"id": exec_id if exec_id is not None else 0}
            return {"id": 0}
        if tipo == "projeto-comecar":
            pid, _, numero = alvo.partition(":")
            if pid not in projetos.lista(config) or not numero.isdigit():
                return _erro(400, f"ação desconhecida: {nome}")
            projetos.aceitar(config, estado, pid, int(numero))
            exec_id = agendador.disparar("preparar_prompts")   # prepara já, sem esperar os 15 minutos
            return {"id": exec_id if exec_id is not None else 0}
        if tipo in ("projeto-refazer", "revisao-refazer"):
            pid, _, numero = alvo.partition(":")
            revisao = tipo == "revisao-refazer"
            try:
                projetos.pedir_de_novo(config, estado, pid, int(numero), "pr" if revisao else "issue")
            except ValueError:
                return _erro(400, f"ação desconhecida: {nome}")
            exec_id = agendador.disparar("preparar_revisoes" if revisao else "preparar_prompts")
            return {"id": exec_id if exec_id is not None else 0}
        if tipo == "rodar" and alvo in ROTINAS:
            exec_id = agendador.disparar(alvo)
            if exec_id is None:
                motivo = agendador.motivo_parada(ROTINAS[alvo]) or "já está rodando"
                return _erro(409, motivo)
            return {"id": exec_id}
        return _erro(400, f"ação desconhecida: {nome}")

    @app.get("/estado/{eid}")
    def estado_acao(eid: int, request: Request):
        if not _token_ok(request):
            return _erro(403, "sem permissão")
        if eid == 0:
            return {"fim": agora(), "codigo": 0, "texto": ""}
        execucao = estado.execucao(eid)
        if execucao is None:
            return _erro(404, "execução desconhecida")
        if execucao["fim"] is None:
            return {"fim": None, "codigo": None, "texto": ""}
        return {"fim": execucao["fim"], "codigo": _CODIGO.get(execucao["status"], 1),
                "texto": execucao["resumo"]}

    @app.get("/api/grafo")
    def ver_grafo():
        return grafo.montar(config, estado, agendador)

    @app.get("/api/projeto/{pid}/prompt/{numero}")
    def ver_prompt(pid: str, numero: int, tipo: str = "issue"):
        """O texto do prompt deixado no Orca, para ler na gaveta (fora da lista do celular: só no computador)."""
        texto = projetos.ler_texto(config, pid, numero, "pr" if tipo == "pr" else "issue")
        if texto is None:
            return _erro(404, "prompt desconhecido")
        return {"texto": texto}

    @app.get("/api/hoje")
    def ver_hoje():
        """Os últimos textos gerados (briefing, resumo de mensagens, fechamento) para a faixa "Hoje" do mapa."""
        textos = []
        for rid, titulo in (("meu_dia", "Briefing do dia"), ("resumo_mensagens", "Resumo das mensagens"),
                            ("dia_fechado", "Fechamento do dia")):
            if ultimo := saidas.ultimo_texto(estado, rid):
                textos.append({"id": rid, "titulo": titulo, "quando": ultimo["quando"],
                               "conteudo": ultimo["conteudo"], "nota": saidas.nota(config, rid)})
        return {"gerado": agora(), "textos": textos}

    @app.get("/api/maquina/historico")
    def historico_da_maquina(horas: int = 24):
        """CPU, memória e disco das últimas horas, reduzidos a poucos pontos, para o gráfico da máquina."""
        horas = max(1, min(horas, 168))
        desde = (datetime.now() - timedelta(hours=horas)).isoformat(timespec="seconds")
        return {"desde": desde, "medidas": maquina.reduzir_medidas(estado.medidas(desde))}

    @app.get("/api/eventos")
    async def ver_eventos(request: Request):
        async def fluxo():
            fila = eventos.assinar()
            try:
                yield "retry: 2000\n\n"
                while not await request.is_disconnected():
                    try:
                        evento = await asyncio.wait_for(fila.get(), timeout=15)
                        yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": vivo\n\n"
            finally:
                eventos.cancelar(fila)
        return StreamingResponse(fluxo(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.post("/api/rotinas/{rid}/rodar")
    def rodar(rid: str):
        if rid not in ROTINAS:
            raise HTTPException(404, "rotina desconhecida")
        if motivo := agendador.motivo_parada(ROTINAS[rid]):
            raise HTTPException(409, motivo)
        if agendador.rodando(rid):
            raise HTTPException(409, "já está rodando")
        agendador.rodar_agora(rid)
        return {"ok": True}

    @app.get("/api/no/{tipo}/{nid}")
    def detalhe(tipo: str, nid: str):
        if tipo == "rotina" and nid in ROTINAS:
            r = ROTINAS[nid]
            fonte = saidas.FONTES.get(nid)
            return {
                "tipo": tipo, "titulo": r.nome, "descricao": r.descricao,
                "campos": [["frente", r.frente], ["quando", quando_texto(agendador.quando(r))],
                           ["próxima", grafo._hora(agendador.proxima(nid)) or "—"],
                           ["usa", ", ".join(SERVICOS[s].nome for s in r.usa) or "só a máquina"]],
                "rodar": nid, "motivo": agendador.motivo_parada(r), "rodando": agendador.rodando(nid),
                "execucoes": estado.execucoes(nid),
                "itens": estado.itens([fonte], limite=200) if fonte else [],
                "nota": saidas.nota(config, nid),
                "texto": saidas.ultimo_texto(estado, nid),
            }
        if tipo == "servico" and nid in SERVICOS:
            s = SERVICOS[nid]
            c = estado.checagens().get(nid)
            usam = [r for r in ROTINAS.values() if nid in r.usa]
            campos = [["rotinas", ", ".join(r.nome for r in usam) or "nenhuma"]]
            if motivo := s.configurado(config):
                campos.insert(0, ["falta", motivo])
            elif c:
                campos[:0] = [["estado", c["detalhe"]], ["latência", f"{c['ms']} ms"],
                              ["checado", grafo._hora(c["quando"])]]
            return {"tipo": tipo, "titulo": s.nome, "descricao": s.descricao, "campos": campos}
        if tipo == "frente" and nid in grafo.frentes():
            membros = [r for r in ROTINAS.values() if r.frente == nid]
            return {"tipo": tipo, "titulo": nid, "descricao": "",
                    "campos": [[r.nome, quando_texto(agendador.quando(r))] for r in membros]}
        if tipo == "maquina":
            c = estado.checagens().get("maquina") or {"meta": {}, "detalhe": "", "quando": ""}
            m = c["meta"]
            # um campo por disco; leituras antigas, de um disco só, ainda têm `disco_livre_gb`
            discos = [[f"disco {d['nome']}", f"{d['livre_gb']} GB livres de {d['total_gb']} GB"]
                      for d in m.get("discos", [])] or [["disco livre", f"{m.get('disco_livre_gb', '—')} GB"]]
            return {"tipo": tipo, "titulo": m.get("nome", "esta máquina"), "descricao": c["detalhe"],
                    "campos": [["sistema", m.get("sistema", "—")], ["ip", m.get("ip", "—")],
                               ["ligada desde", m.get("ligada_desde", "—")], ["cpu", f"{m.get('cpu', '—')}%"],
                               ["memória", f"{m.get('memoria', '—')}%"], *discos,
                               ["checado", grafo._hora(c["quando"]) or "—"]]}
        if tipo == "destino":
            if nid == "avisos":
                return {"tipo": tipo, "titulo": "Avisos", "descricao": "Falhas e alertas das rotinas.",
                        "campos": [], "avisos": estado.avisos(limite=40)}
            fontes = [r for r in ROTINAS.values() if nid in r.entrega]
            pasta = config.secao("obsidian").get(
                "pasta_diario" if nid == "diario" else "pasta_automateum", "")
            return {"tipo": tipo, "titulo": grafo._DESTINOS.get(nid, nid),
                    "descricao": f"Escrito no cofre, em {pasta}/.",
                    "campos": [[r.nome, quando_texto(agendador.quando(r))] for r in fontes]}
        raise HTTPException(404, "nó desconhecido")

    app.mount("/static", _Estaticos(directory=_ESTATICOS), name="static")
    return app
