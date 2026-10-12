"""Barramento em memória: as rotinas publicam de qualquer thread e o painel recebe por SSE."""
from __future__ import annotations

import asyncio
import threading


class Barramento:
    def __init__(self) -> None:
        self._trava = threading.Lock()
        self._assinantes: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []

    def assinar(self) -> asyncio.Queue:
        fila: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._trava:
            self._assinantes.append((asyncio.get_running_loop(), fila))
        return fila

    def cancelar(self, fila: asyncio.Queue) -> None:
        with self._trava:
            self._assinantes = [(l, f) for l, f in self._assinantes if f is not fila]

    def publicar(self, tipo: str, **dados) -> None:
        evento = {"tipo": tipo, **dados}
        with self._trava:
            assinantes = list(self._assinantes)
        for loop, fila in assinantes:
            try:
                loop.call_soon_threadsafe(self._entregar, fila, evento)
            except RuntimeError:
                pass  # o loop do assinante já fechou

    @staticmethod
    def _entregar(fila: asyncio.Queue, evento: dict) -> None:
        if not fila.full():
            fila.put_nowait(evento)
