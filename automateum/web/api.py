"""API e painel. Escuta só em 127.0.0.1."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .. import rotinas, servicos  # noqa: F401  (registram rotinas e serviços)
from ..config import Config
from ..nucleo import grafo
from ..nucleo.agendador import Agendador
from ..nucleo.estado import Estado
from ..nucleo.eventos import Barramento
from ..nucleo.registro import ROTINAS, SERVICOS, quando_texto

_ESTATICOS = Path(__file__).parent / "static"
_LOCAIS = {"127.0.0.1", "localhost"}
# De qual fonte de itens cada rotina é dona, para mostrar a lista no painel lateral.
_ITENS = {"tasks_obsidian": "obsidian", "tasks_github": "github", "coletar_slack": "slack",
          "coletar_gmail": "gmail"}


def criar_app(config: Config) -> FastAPI:
    estado = Estado(config.banco)
    eventos = Barramento()
    agendador = Agendador(config, estado, eventos)

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
            fonte = _ITENS.get(nid)
            return {
                "tipo": tipo, "titulo": r.nome, "descricao": r.descricao,
                "campos": [["frente", r.frente], ["quando", quando_texto(agendador.quando(r))],
                           ["próxima", grafo._hora(agendador.proxima(nid)) or "—"],
                           ["usa", ", ".join(SERVICOS[s].nome for s in r.usa) or "só a máquina"]],
                "rodar": nid, "motivo": agendador.motivo_parada(r), "rodando": agendador.rodando(nid),
                "execucoes": estado.execucoes(nid),
                "itens": estado.itens([fonte], limite=200) if fonte else [],
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

    app.mount("/static", StaticFiles(directory=_ESTATICOS), name="static")
    return app
