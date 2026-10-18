"""Estado persistente em SQLite: execuções, checagens, itens coletados, cursores e avisos."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from .registro import Checagem

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS execucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rotina TEXT NOT NULL, inicio TEXT NOT NULL, fim TEXT,
    status TEXT NOT NULL, resumo TEXT DEFAULT '', log TEXT DEFAULT '', manual INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS execucoes_rotina ON execucoes (rotina, id);
CREATE TABLE IF NOT EXISTS checagens (
    servico TEXT PRIMARY KEY, estado TEXT, detalhe TEXT, ms INTEGER, meta TEXT, quando TEXT
);
CREATE TABLE IF NOT EXISTS itens (
    fonte TEXT NOT NULL, chave TEXT NOT NULL, titulo TEXT, corpo TEXT, origem TEXT, url TEXT,
    quando TEXT, coletado TEXT NOT NULL, PRIMARY KEY (fonte, chave)
);
CREATE TABLE IF NOT EXISTS cursores (chave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS medidas (
    quando TEXT PRIMARY KEY, cpu INTEGER, memoria INTEGER, disco_livre_gb INTEGER, discos TEXT
);
CREATE TABLE IF NOT EXISTS avisos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, quando TEXT, rotina TEXT, nivel TEXT, texto TEXT
);
"""

_CAMPOS_ITEM = ("chave", "titulo", "corpo", "origem", "url", "quando")


def agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Estado:
    def __init__(self, caminho: Path | str):
        self._trava = threading.RLock()
        self._db = sqlite3.connect(str(caminho), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_ESQUEMA)
        # bancos criados antes de a máquina ter mais de um disco não têm a coluna `discos`
        if "discos" not in {c["name"] for c in self._db.execute("PRAGMA table_info(medidas)")}:
            self._db.execute("ALTER TABLE medidas ADD COLUMN discos TEXT")

    def _exec(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._trava:
            return self._db.execute(sql, args)

    def _linhas(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._trava:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    @contextmanager
    def _transacao(self):
        with self._trava:
            self._db.execute("BEGIN")
            try:
                yield
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")

    # --- execuções
    def marcar_interrompidas(self) -> None:
        """Execuções que ficaram como 'rodando' pertencem a um processo que morreu."""
        self._exec("UPDATE execucoes SET status='falha', fim=?, resumo='interrompida: o Automateum foi "
                   "fechado no meio da execução' WHERE status='rodando'", (agora(),))

    def iniciar_execucao(self, rotina: str, manual: bool = False) -> int:
        return self._exec("INSERT INTO execucoes (rotina, inicio, status, manual) VALUES (?,?,?,?)",
                          (rotina, agora(), "rodando", int(manual))).lastrowid

    def log_execucao(self, exec_id: int, linha: str) -> None:
        self._exec("UPDATE execucoes SET log = log || ? WHERE id=?",
                   (f"{datetime.now():%H:%M:%S} {linha}\n", exec_id))

    def finalizar_execucao(self, exec_id: int, status: str, resumo: str) -> None:
        self._exec("UPDATE execucoes SET status=?, resumo=?, fim=? WHERE id=?",
                   (status, resumo, agora(), exec_id))

    def execucoes(self, rotina: str, limite: int = 15) -> list[dict]:
        return self._linhas("SELECT * FROM execucoes WHERE rotina=? ORDER BY id DESC LIMIT ?", (rotina, limite))

    def execucao(self, exec_id: int) -> dict | None:
        linhas = self._linhas("SELECT * FROM execucoes WHERE id=?", (exec_id,))
        return linhas[0] if linhas else None

    def ultimas_execucoes(self) -> dict[str, dict]:
        linhas = self._linhas("SELECT id, rotina, inicio, fim, status, resumo FROM execucoes WHERE id IN "
                              "(SELECT MAX(id) FROM execucoes GROUP BY rotina)")
        return {l["rotina"]: l for l in linhas}

    def limpar_antigos(self, dias: int = 30) -> None:
        corte = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
        self._exec("DELETE FROM execucoes WHERE inicio < ?", (corte,))
        self._exec("DELETE FROM avisos WHERE quando < ?", (corte,))
        # as medições da máquina são de 2 em 2 minutos: só os últimos dias interessam
        self._exec("DELETE FROM medidas WHERE quando < ?",
                   ((datetime.now() - timedelta(days=7)).isoformat(timespec="seconds"),))

    # --- medições da máquina
    def salvar_medida(self, cpu: int, memoria: int, disco_livre_gb: int, discos: dict[str, int] | None = None) -> None:
        """`discos`: GB livres por disco ({'C:': 85, 'D:': 94}); `disco_livre_gb` é o primeiro, para quem só conhece um."""
        self._exec("INSERT OR REPLACE INTO medidas (quando, cpu, memoria, disco_livre_gb, discos) VALUES (?,?,?,?,?)",
                   (agora(), cpu, memoria, disco_livre_gb, json.dumps(discos or {})))

    def medidas(self, desde: str) -> list[dict]:
        linhas = self._linhas("SELECT * FROM medidas WHERE quando >= ? ORDER BY quando", (desde,))
        for m in linhas:
            try:
                m["discos"] = json.loads(m["discos"]) if m.get("discos") else {}
            except ValueError:
                m["discos"] = {}
        return linhas

    # --- checagens de serviço
    def salvar_checagem(self, servico: str, c: Checagem) -> None:
        self._exec("INSERT OR REPLACE INTO checagens VALUES (?,?,?,?,?,?)",
                   (servico, c.estado, c.detalhe, c.ms, json.dumps(c.meta, ensure_ascii=False), agora()))

    def checagens(self) -> dict[str, dict]:
        saida = {}
        for l in self._linhas("SELECT * FROM checagens"):
            l["meta"] = json.loads(l["meta"] or "{}")
            saida[l["servico"]] = l
        return saida

    # --- itens coletados (tasks, mensagens)
    def substituir_itens(self, fonte: str, itens: list[dict]) -> None:
        """Para fontes que são uma fotografia do estado atual (ex.: tasks abertas)."""
        with self._transacao():
            self._db.execute("DELETE FROM itens WHERE fonte=?", (fonte,))
            self._inserir(fonte, itens)

    def juntar_itens(self, fonte: str, itens: list[dict]) -> int:
        """Para fontes que acumulam (ex.: mensagens). Devolve quantos eram novos."""
        with self._trava:
            antes = self._db.execute("SELECT COUNT(*) FROM itens WHERE fonte=?", (fonte,)).fetchone()[0]
            with self._transacao():
                self._inserir(fonte, itens, "OR IGNORE")
            depois = self._db.execute("SELECT COUNT(*) FROM itens WHERE fonte=?", (fonte,)).fetchone()[0]
            return depois - antes

    def _inserir(self, fonte: str, itens: list[dict], conflito: str = "OR REPLACE") -> None:
        momento = agora()
        self._db.executemany(
            f"INSERT {conflito} INTO itens (fonte, chave, titulo, corpo, origem, url, quando, coletado) "
            "VALUES (?,?,?,?,?,?,?,?)",
            [(fonte, *(str(i.get(c) or "") for c in _CAMPOS_ITEM), momento) for i in itens])

    def itens(self, fontes: list[str], coletado_apos: str = "", limite: int = 500) -> list[dict]:
        marcas = ",".join("?" * len(fontes))
        return self._linhas(f"SELECT * FROM itens WHERE fonte IN ({marcas}) AND coletado > ? "
                            "ORDER BY quando DESC, chave LIMIT ?", (*fontes, coletado_apos, limite))

    def contar_itens(self, fonte: str) -> int:
        return self._exec("SELECT COUNT(*) FROM itens WHERE fonte=?", (fonte,)).fetchone()[0]

    def remover_origens(self, fonte: str, origens: list[str]) -> int:
        """Apaga os itens guardados dessas origens (conversas que saíram da lista permitida)."""
        if not origens:
            return 0
        marcas = ",".join("?" * len(origens))
        return self._exec(f"DELETE FROM itens WHERE fonte=? AND origem IN ({marcas})", (fonte, *origens)).rowcount

    def origens(self, fonte: str) -> list[str]:
        return [r[0] for r in self._exec("SELECT DISTINCT origem FROM itens WHERE fonte=?", (fonte,)).fetchall() if r[0]]

    def podar_itens(self, fonte: str, dias: int) -> None:
        corte = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
        self._exec("DELETE FROM itens WHERE fonte=? AND coletado < ?", (fonte, corte))

    # --- cursores
    def cursor(self, chave: str, padrao: str = "") -> str:
        linha = self._exec("SELECT valor FROM cursores WHERE chave=?", (chave,)).fetchone()
        return linha[0] if linha else padrao

    def definir_cursor(self, chave: str, valor: str) -> None:
        self._exec("INSERT OR REPLACE INTO cursores VALUES (?,?)", (chave, valor))

    # --- avisos
    def avisar(self, rotina: str, texto: str, nivel: str = "atencao") -> None:
        self._exec("INSERT INTO avisos (quando, rotina, nivel, texto) VALUES (?,?,?,?)",
                   (agora(), rotina, nivel, texto))

    def avisos(self, limite: int = 20, horas: int | None = None, pendentes: bool = False) -> list[dict]:
        """Avisos mais recentes primeiro. `resolvido` marca os que uma rodada ok posterior da mesma
        rotina encerrou; `pendentes=True` esconde esses (o histórico em si nunca é apagado)."""
        corte = ""
        if horas is not None:
            corte = (datetime.now() - timedelta(hours=horas)).isoformat(timespec="seconds")
        # Conta a rodada que começou depois do aviso: a que o gerou não o resolve.
        resolvido = ("EXISTS (SELECT 1 FROM execucoes e WHERE e.rotina = a.rotina AND e.status = 'ok' "
                     "AND e.inicio > a.quando)")
        filtro = f" AND NOT {resolvido}" if pendentes else ""
        return self._linhas(f"SELECT a.*, {resolvido} AS resolvido FROM avisos a WHERE a.quando > ?{filtro} "
                            "ORDER BY a.id DESC LIMIT ?", (corte, limite))
