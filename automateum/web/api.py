"""API e painel. Escuta só em 127.0.0.1."""
from __future__ import annotations

import asyncio
import hmac
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import rotinas, servicos  # noqa: F401  (registram rotinas e serviços)
from ..config import Config
from ..nucleo import grafo, mapa_leo, saidas
from ..nucleo.agendador import Agendador
from ..nucleo.estado import Estado, agora
from ..nucleo.eventos import Barramento
from ..nucleo.registro import ATENCAO, FALHA, OK, ROTINAS, SERVICOS, quando_texto

_ESTATICOS = Path(__file__).parent / "static"
_LOCAIS = {"127.0.0.1", "localhost"}


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


def criar_app(config: Config) -> FastAPI:
    estado = Estado(config.banco)
    eventos = Barramento()
    agendador = Agendador(config, estado, eventos)
    # Token da sessão: vai só para a página local (acoes.js). Ações exigem também a origem local.
    token = secrets.token_urlsafe(24)
    porta = int(config.secao("painel").get("porta", 8765))

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

    @app.middleware("http")
    async def so_local(request: Request, seguir):
        # Barra páginas de outros sites (CSRF) e DNS rebinding: só o próprio painel fala com a API.
        host = (request.headers.get("host") or "").rsplit(":", 1)[0]
        origem = request.headers.get("origin")
        if host not in _LOCAIS or (origem and urlsplit(origem).hostname not in _LOCAIS):
            return JSONResponse({"detail": "origem não permitida"}, status_code=403)
        return await seguir(request)

    @app.get("/")
    def painel():
        return FileResponse(_ESTATICOS / "index.html", headers={"Cache-Control": "no-store"})

    @app.get("/dados/estado.js")
    def estado_js():
        dados = mapa_leo.montar_mapa_leo(config, estado, agendador)
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
            return {"tipo": tipo, "titulo": m.get("nome", "esta máquina"), "descricao": c["detalhe"],
                    "campos": [["sistema", m.get("sistema", "—")], ["ip", m.get("ip", "—")],
                               ["ligada desde", m.get("ligada_desde", "—")], ["cpu", f"{m.get('cpu', '—')}%"],
                               ["memória", f"{m.get('memoria', '—')}%"],
                               ["disco livre", f"{m.get('disco_livre_gb', '—')} GB"],
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
