"""Agenda e executa as rotinas, gravando cada execução e avisando o painel."""
from __future__ import annotations

import threading
import traceback
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from ..config import Config
from .estado import Estado
from .eventos import Barramento
from .registro import ATENCAO, FALHA, OK, ROTINAS, SERVICOS, Atencao, Resultado, Rotina, gatilho


class Contexto:
    """O que uma rotina recebe para trabalhar."""

    def __init__(self, config: Config, estado: Estado, rotina: Rotina, exec_id: int):
        self.config, self.estado, self.rotina, self.exec_id = config, estado, rotina, exec_id

    def log(self, mensagem: str) -> None:
        self.estado.log_execucao(self.exec_id, mensagem)

    def avisar(self, texto: str, nivel: str = ATENCAO) -> None:
        self.estado.avisar(self.rotina.id, texto, nivel)


class Agendador:
    def __init__(self, config: Config, estado: Estado, eventos: Barramento):
        self.config, self.estado, self.eventos = config, estado, eventos
        self._sched = BackgroundScheduler()
        self._travas = {id: threading.Lock() for id in ROTINAS}

    def quando(self, rotina: Rotina) -> str:
        return self.config.secao("horarios").get(rotina.id, rotina.quando)

    def motivo_parada(self, rotina: Rotina) -> str | None:
        """Por que a rotina não pode rodar agora; None quando pode."""
        for sid in rotina.usa:
            if motivo := SERVICOS[sid].configurado(self.config):
                return f"{SERVICOS[sid].nome}: {motivo}"
        return None

    def iniciar(self) -> None:
        self.estado.marcar_interrompidas()
        self.estado.limpar_antigos()
        for r in ROTINAS.values():
            if g := gatilho(self.quando(r)):
                self._sched.add_job(self.executar, g, args=[r.id], id=r.id, max_instances=1,
                                    coalesce=True, misfire_grace_time=600)
        self._sched.start()
        # Primeira leitura logo na subida, para o painel não abrir vazio.
        for id in ("saude", "tasks_obsidian"):
            if id in ROTINAS:
                self.rodar_agora(id, manual=False)

    def parar(self) -> None:
        self._sched.shutdown(wait=False)

    def proxima(self, rotina_id: str) -> str | None:
        job = self._sched.get_job(rotina_id)
        return job.next_run_time.isoformat(timespec="seconds") if job and job.next_run_time else None

    def rodando(self, rotina_id: str) -> bool:
        trava = self._travas.get(rotina_id)
        return trava.locked() if trava else False

    def rodar_agora(self, rotina_id: str, manual: bool = True) -> None:
        threading.Thread(target=self.executar, args=[rotina_id, manual], daemon=True,
                         name=f"rotina-{rotina_id}").start()

    def executar(self, rotina_id: str, manual: bool = False) -> None:
        rotina = ROTINAS[rotina_id]
        if self.motivo_parada(rotina):
            return
        trava = self._travas[rotina_id]
        if not trava.acquire(blocking=False):
            return  # já está rodando
        try:
            anterior = self.estado.ultimas_execucoes().get(rotina_id, {}).get("status")
            exec_id = self.estado.iniciar_execucao(rotina_id, manual)
            self.eventos.publicar("rotina", id=rotina_id, status="rodando")
            ctx = Contexto(self.config, self.estado, rotina, exec_id)
            try:
                saida = rotina.func(ctx)
                r = saida if isinstance(saida, Resultado) else Resultado(OK, str(saida or ""))
            except Atencao as e:
                r = Resultado(ATENCAO, str(e))
            except Exception as e:
                ctx.log(traceback.format_exc())
                # RuntimeError é o erro que os serviços levantam já com mensagem pronta para o painel.
                texto = str(e) if type(e) is RuntimeError else f"{type(e).__name__}: {e}"
                r = Resultado(FALHA, texto[:300])
            self.estado.finalizar_execucao(exec_id, r.estado, r.resumo)
            # Avisa só na virada para falha, não a cada repetição do mesmo erro.
            if r.estado == FALHA and anterior != FALHA:
                self.estado.avisar(rotina_id, f"{rotina.nome} falhou: {r.resumo}", FALHA)
            self.eventos.publicar("rotina", id=rotina_id, status=r.estado,
                                  quando=datetime.now().isoformat(timespec="seconds"))
        finally:
            trava.release()
