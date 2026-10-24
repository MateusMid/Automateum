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
CREATE TABLE IF NOT EXISTS tasks_vistas (ident TEXT PRIMARY KEY, desde TEXT NOT NULL);
-- até qual mensagem (inclusive) a conversa já foi vista; o que é mais novo volta a aparecer
CREATE TABLE IF NOT EXISTS conversas_vistas (fonte TEXT NOT NULL, origem TEXT NOT NULL, ate TEXT NOT NULL,
    PRIMARY KEY (fonte, origem));
CREATE TABLE IF NOT EXISTS medidas (
    quando TEXT PRIMARY KEY, cpu INTEGER, memoria INTEGER, disco_livre_gb INTEGER, discos TEXT
);
-- uma linha por tentativa de pergunta a uma IA; só os números, nunca o texto da pergunta ou da resposta
CREATE TABLE IF NOT EXISTS chamadas_ia (
    quando TEXT NOT NULL, rotina TEXT, motor TEXT NOT NULL, ms INTEGER, ok INTEGER, reserva INTEGER
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

    def rodadas_por_dia(self, rotina: str, dias: int = 14) -> list[dict]:
        """Quantas rodadas terminaram bem, com atenção e em falha em cada um dos últimos `dias` (hoje por último)."""
        hoje = datetime.now().date()
        lista = [{"dia": (hoje - timedelta(days=d)).isoformat(), "ok": 0, "atencao": 0, "falha": 0}
                 for d in range(dias - 1, -1, -1)]
        por_dia = {d["dia"]: d for d in lista}
        for l in self._linhas("SELECT substr(inicio, 1, 10) AS dia, status, COUNT(*) AS n FROM execucoes "
                              "WHERE rotina=? AND inicio >= ? GROUP BY dia, status", (rotina, lista[0]["dia"])):
            if l["dia"] in por_dia and l["status"] in ("ok", "atencao", "falha"):   # a que ainda roda não conta
                por_dia[l["dia"]][l["status"]] = l["n"]
        return lista

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
        self._exec("DELETE FROM chamadas_ia WHERE quando < ?", (corte,))
        # as medições da máquina são de 2 em 2 minutos: só os últimos dias interessam
        self._exec("DELETE FROM medidas WHERE quando < ?",
                   ((datetime.now() - timedelta(days=7)).isoformat(timespec="seconds"),))

    # --- uso da IA
    def registrar_chamada_ia(self, rotina: str, motor: str, ms: int, ok: bool, reserva: bool) -> None:
        self._exec("INSERT INTO chamadas_ia (quando, rotina, motor, ms, ok, reserva) VALUES (?,?,?,?,?,?)",
                   (agora(), rotina, motor, ms, int(ok), int(reserva)))

    def reserva_seguidas(self) -> int:
        """Quantas das últimas respostas seguidas vieram do motor de reserva."""
        n = 0
        for l in self._linhas("SELECT reserva FROM chamadas_ia WHERE ok=1 ORDER BY rowid DESC LIMIT 100"):
            if not l["reserva"]:
                break
            n += 1
        return n

    def uso_da_ia(self, dias: int = 14) -> dict:
        """Por dia (hoje por último): respostas do principal, da reserva e falhas; por motor: chamadas e tempo médio."""
        hoje = datetime.now().date()
        lista = [{"dia": (hoje - timedelta(days=d)).isoformat(), "principal": 0, "reserva": 0, "falhas": 0}
                 for d in range(dias - 1, -1, -1)]
        por_dia = {d["dia"]: d for d in lista}
        for l in self._linhas("SELECT substr(quando, 1, 10) AS dia, ok, reserva, COUNT(*) AS n FROM chamadas_ia "
                              "WHERE quando >= ? GROUP BY dia, ok, reserva", (lista[0]["dia"],)):
            if d := por_dia.get(l["dia"]):
                d["falhas" if not l["ok"] else "reserva" if l["reserva"] else "principal"] += l["n"]
        motores = {l["motor"]: {"respostas": l["respostas"] or 0, "falhas": l["falhas"] or 0,
                                "ms_medio": round(l["ms_medio"]) if l["ms_medio"] is not None else None}
                   for l in self._linhas("SELECT motor, SUM(ok) AS respostas, SUM(1 - ok) AS falhas, "
                                         "AVG(CASE WHEN ok=1 THEN ms END) AS ms_medio FROM chamadas_ia "
                                         "WHERE quando >= ? GROUP BY motor", (lista[0]["dia"],))}
        return {"dias": lista, "motores": motores, "reserva_seguidas": self.reserva_seguidas()}

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

    def item(self, fonte: str, chave: str) -> dict | None:
        linhas = self._linhas("SELECT * FROM itens WHERE fonte=? AND chave=?", (fonte, chave))
        return linhas[0] if linhas else None

    def ver_ate(self, fonte: str, origem: str, ate: str) -> None:
        """Marca a conversa como vista até `ate`. Nunca volta atrás: uma marca mais antiga não desfaz uma mais nova."""
        self._exec("INSERT INTO conversas_vistas (fonte, origem, ate) VALUES (?,?,?) ON CONFLICT(fonte, origem) "
                   "DO UPDATE SET ate = MAX(ate, excluded.ate)", (fonte, origem, ate))

    def itens_nao_vistos(self, fontes: list[str], coletado_apos: str = "", limite: int = 500) -> list[dict]:
        """Como `itens`, sem o que já foi marcado como visto na sua conversa (até a mensagem marcada, inclusive)."""
        vistas = {(f, o): a for f, o, a in self._exec("SELECT fonte, origem, ate FROM conversas_vistas").fetchall()}
        saida = []
        for i in self.itens(fontes, coletado_apos, limite=100_000):
            ate = vistas.get((i["fonte"], i["origem"]))
            if ate and (i["quando"] or "") <= ate:
                continue
            saida.append(i)
            if len(saida) == limite:
                break
        return saida

    def contar_itens(self, fonte: str) -> int:
        return self._exec("SELECT COUNT(*) FROM itens WHERE fonte=?", (fonte,)).fetchone()[0]

    def remover_origens(self, fonte: str, origens: list[str]) -> int:
        """Apaga os itens guardados dessas origens (conversas que saíram da lista permitida)."""
        if not origens:
            return 0
        marcas = ",".join("?" * len(origens))
        return self._exec(f"DELETE FROM itens WHERE fonte=? AND origem IN ({marcas})", (fonte, *origens)).rowcount

    def remover_sem_marca(self, fonte: str, origem: str, marcas: list[str]) -> int:
        """Apaga os itens dessa origem cujo texto não cita nenhuma das marcas (`@Nome`)."""
        sobra = [r for r in self._exec("SELECT chave, titulo FROM itens WHERE fonte=? AND origem=?", (fonte, origem)).fetchall()
                 if not any(f"@{m.lower()}" in (r[1] or "").lower() for m in marcas if m)]
        for chave, _ in sobra:
            self._exec("DELETE FROM itens WHERE fonte=? AND chave=?", (fonte, chave))
        return len(sobra)

    def origens(self, fonte: str) -> list[str]:
        return [r[0] for r in self._exec("SELECT DISTINCT origem FROM itens WHERE fonte=?", (fonte,)).fetchall() if r[0]]

    def podar_itens(self, fonte: str, dias: int) -> None:
        corte = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
        self._exec("DELETE FROM itens WHERE fonte=? AND coletado < ?", (fonte, corte))

    def datas_das_tasks(self, tasks: dict[str, str]) -> dict[str, str]:
        """Desde quando cada task está aberta. `tasks` leva cada task à data mais antiga em que se sabe que ela já
        existia; fica guardada a menor data já vista. As que sumiram (feitas ou apagadas) são esquecidas."""
        with self._transacao():
            self._db.executemany("INSERT INTO tasks_vistas VALUES (?,?) ON CONFLICT(ident) DO UPDATE SET "
                                 "desde = MIN(desde, excluded.desde)", list(tasks.items()))
            guardadas = dict(self._db.execute("SELECT ident, desde FROM tasks_vistas").fetchall())
            self._db.executemany("DELETE FROM tasks_vistas WHERE ident=?", [(k,) for k in guardadas if k not in tasks])
        return {k: guardadas[k] for k in tasks}

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
