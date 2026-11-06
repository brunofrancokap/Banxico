"""Persistência: registro de documentos em SQLite + arquivos brutos imutáveis em disco.

Layout dos arquivos:
    data/raw/<source>/<YYYY>/<YYYY-MM-DD>_<remote_id>.<ext>   (imutável, fonte da verdade)
    data/text/<source>/<YYYY>/<YYYY-MM-DD>_<remote_id>.md     (derivado, regenerável)
O banco é o índice central; cada etapa derivada é uma tabela ligada a documents.id.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import DB_PATH, RAW_DIR
from .models import DocumentRef

SCHEMA_VERSION = 3

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS documents (
    id             TEXT PRIMARY KEY,          -- "<source>:<remote_id>"
    source         TEXT NOT NULL,
    doc_type       TEXT NOT NULL,
    language       TEXT NOT NULL,
    doc_date       TEXT NOT NULL,             -- ISO yyyy-mm-dd
    title          TEXT,
    url            TEXT NOT NULL,
    remote_id      TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'discovered',  -- discovered | downloaded | error
    local_path     TEXT,                      -- relativo a data/
    sha256         TEXT,
    size_bytes     INTEGER,
    content_type   TEXT,
    error          TEXT,
    discovered_at  TEXT NOT NULL,
    downloaded_at  TEXT
);
CREATE INDEX IF NOT EXISTS ix_documents_source_date ON documents(source, doc_date);
"""

SCHEMA_V2 = """
-- Uma linha por documento extraído (última extração).
CREATE TABLE IF NOT EXISTS extractions (
    document_id        TEXT PRIMARY KEY REFERENCES documents(id),
    extractor_version  TEXT NOT NULL,
    n_pages            INTEGER,
    n_segments         INTEGER,
    n_paragraphs       INTEGER,
    text_path          TEXT,                  -- relativo a data/
    error              TEXT,
    extracted_at       TEXT NOT NULL
);
-- Segmentos em ordem de leitura. kind: paragraph|heading|table|footnote|figure
CREATE TABLE IF NOT EXISTS segments (
    document_id  TEXT NOT NULL REFERENCES documents(id),
    seq          INTEGER NOT NULL,
    kind         TEXT NOT NULL,
    section      TEXT,                        -- rótulo heurístico (ver text/sections.py)
    page         INTEGER,
    bold         INTEGER,
    text         TEXT NOT NULL,
    PRIMARY KEY (document_id, seq)
);
CREATE INDEX IF NOT EXISTS ix_segments_section ON segments(section);
CREATE VIEW IF NOT EXISTS v_paragraphs AS
    SELECT d.source, d.doc_type, d.doc_date, s.document_id, s.seq, s.section, s.text
    FROM segments s JOIN documents d ON d.id = s.document_id
    WHERE s.kind = 'paragraph';
"""

SCHEMA_V3 = """
-- Uma linha por reunião (comunicado de PM). Recalculada inteira a cada `banxico structure`.
CREATE TABLE IF NOT EXISTS decisions (
    document_id      TEXT PRIMARY KEY REFERENCES documents(id),
    doc_date         TEXT NOT NULL,
    struct_version   TEXT NOT NULL,
    instrument       TEXT,          -- tasa | corto
    action           TEXT,          -- hike | cut | hold
    change_bp        INTEGER,       -- tasa: Δ taxa; corto: Δ condições monetárias (se informado)
    rate             REAL,          -- tasa objetivo após a decisão (%)
    corto_mn         INTEGER,       -- nível do corto (milhões de pesos)
    effective_date   TEXT,
    extraordinary    INTEGER,
    vote_type        TEXT,          -- unanimous | majority | NULL (não informado)
    vote_source      TEXT,          -- named | text
    n_for            INTEGER,
    n_against        INTEGER,
    votes_for        TEXT,          -- JSON [nome]
    dissents         TEXT,          -- JSON [{name, action, change_bp, rate}]
    dissent_summary  TEXT,          -- "Jonathan Heath: hold" (legível)
    infl_bias        TEXT,          -- up | down | balanced | uncertain
    infl_change      TEXT,          -- improved | deteriorated | unchanged
    infl_evidence    TEXT,
    growth_bias      TEXT,
    growth_change    TEXT,
    growth_evidence  TEXT,
    guidance         TEXT,
    title_action     TEXT,          -- do título da listagem (validação cruzada)
    title_change_bp  INTEGER,
    title_rate       REAL,
    checks           TEXT,          -- JSON [aviso]
    n_warnings       INTEGER,       -- avisos que não são "info"
    parsed_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_decisions_date ON decisions(doc_date);
-- Quadro de pronósticos em formato longo.
CREATE TABLE IF NOT EXISTS forecasts (
    document_id   TEXT NOT NULL REFERENCES documents(id),
    vintage       TEXT NOT NULL,    -- actual | anterior
    vintage_date  TEXT,
    series        TEXT NOT NULL,    -- headline_yoy | core_yoy | headline_qoq_saar | core_qoq_saar
    period        TEXT NOT NULL,    -- 2026Q4
    value         REAL NOT NULL,
    PRIMARY KEY (document_id, vintage, series, period)
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, db_path: Path = DB_PATH, raw_dir: Path = RAW_DIR):
        self.db_path = db_path
        self.raw_dir = raw_dir
        self.data_dir = raw_dir.parent
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        current = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if current < 1:
            self.conn.executescript(SCHEMA_V1)
        if current < 2:
            self.conn.executescript(SCHEMA_V2)
        if current < 3:
            self.conn.executescript(SCHEMA_V3)
        # Próximas migrações: `if current < 4: ...` (e incrementar SCHEMA_VERSION)
        self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- registro -----------------------------------------------------------
    def upsert_refs(self, refs: list[DocumentRef]) -> int:
        """Insere documentos novos; atualiza metadados de listagem dos existentes. Retorna nº de novos."""
        before = self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        now = utcnow()
        self.conn.executemany(
            """
            INSERT INTO documents (id, source, doc_type, language, doc_date, title, url, remote_id, discovered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                doc_date = excluded.doc_date, title = excluded.title, url = excluded.url
            """,
            [
                (r.doc_id, r.source, r.doc_type, r.language, r.date.isoformat(), r.title, r.url, r.remote_id, now)
                for r in refs
            ],
        )
        self.conn.commit()
        after = self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        return after - before

    def pending(self, source: str, since: str | None = None, force: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM documents WHERE source = ?"
        params: list = [source]
        if not force:
            sql += " AND status != 'downloaded'"
        if since:
            sql += " AND doc_date >= ?"
            params.append(since)
        sql += " ORDER BY doc_date"
        return self.conn.execute(sql, params).fetchall()

    def mark_downloaded(self, doc_id: str, local_path: Path, sha256: str, size: int, content_type: str) -> None:
        self.conn.execute(
            """UPDATE documents SET status='downloaded', local_path=?, sha256=?, size_bytes=?,
                   content_type=?, error=NULL, downloaded_at=? WHERE id=?""",
            (local_path.relative_to(self.data_dir).as_posix(), sha256, size, content_type, utcnow(), doc_id),
        )
        self.conn.commit()

    def mark_error(self, doc_id: str, error: str) -> None:
        self.conn.execute("UPDATE documents SET status='error', error=? WHERE id=?", (error[:500], doc_id))
        self.conn.commit()

    def summary(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT source, status, COUNT(*) AS n, MIN(doc_date) AS first, MAX(doc_date) AS last
               FROM documents GROUP BY source, status ORDER BY source, status"""
        ).fetchall()

    def get(self, doc_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()

    def find(self, source: str, date_prefix: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM documents WHERE source = ? AND doc_date LIKE ? ORDER BY doc_date",
            (source, date_prefix + "%"),
        ).fetchall()

    # --- extração de texto ----------------------------------------------------
    def pending_extraction(self, source: str, version: str, since: str | None = None,
                           force: bool = False) -> list[sqlite3.Row]:
        sql = """SELECT d.* FROM documents d LEFT JOIN extractions e ON e.document_id = d.id
                 WHERE d.source = ? AND d.status = 'downloaded'"""
        params: list = [source]
        if not force:
            sql += " AND (e.document_id IS NULL OR e.extractor_version != ? OR e.error IS NOT NULL)"
            params.append(version)
        if since:
            sql += " AND d.doc_date >= ?"
            params.append(since)
        return self.conn.execute(sql + " ORDER BY d.doc_date", params).fetchall()

    def save_extraction(self, doc_id: str, version: str, n_pages: int, segments: list,
                        text_path: Path | None) -> None:
        with self.conn:  # transação: substitui segmentos de forma atômica
            self.conn.execute("DELETE FROM segments WHERE document_id = ?", (doc_id,))
            self.conn.executemany(
                "INSERT INTO segments (document_id, seq, kind, section, page, bold, text) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(doc_id, s.seq, s.kind, s.section, s.page, int(s.bold), s.text) for s in segments],
            )
            self.conn.execute(
                """INSERT OR REPLACE INTO extractions
                   (document_id, extractor_version, n_pages, n_segments, n_paragraphs, text_path, error, extracted_at)
                   VALUES (?, ?, ?, ?, ?, ?, NULL, ?)""",
                (doc_id, version, n_pages, len(segments), sum(s.kind == "paragraph" for s in segments),
                 text_path.relative_to(self.data_dir).as_posix() if text_path else None, utcnow()),
            )

    def save_extraction_error(self, doc_id: str, version: str, error: str) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO extractions (document_id, extractor_version, error, extracted_at)
               VALUES (?, ?, ?, ?)""",
            (doc_id, version, error[:500], utcnow()),
        )
        self.conn.commit()

    def segments(self, doc_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM segments WHERE document_id = ? ORDER BY seq", (doc_id,)
        ).fetchall()

    def extraction_summary(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT d.source, e.extractor_version, COUNT(*) AS n,
                      SUM(e.error IS NOT NULL) AS errors, SUM(e.n_paragraphs) AS paragraphs
               FROM extractions e JOIN documents d ON d.id = e.document_id
               GROUP BY d.source, e.extractor_version"""
        ).fetchall()

    # --- dados estruturados ----------------------------------------------------
    def extracted_documents(self, source: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT d.* FROM documents d JOIN extractions e ON e.document_id = d.id
               WHERE d.source = ? AND e.error IS NULL ORDER BY d.doc_date""",
            (source,),
        ).fetchall()

    def replace_structured(self, source: str, decision_rows: list[dict], forecast_rows: list[tuple]) -> None:
        """Substitui atomicamente decisions/forecasts da fonte (recalculados juntos por causa
        das validações de série)."""
        with self.conn:
            ids = [r["id"] for r in self.conn.execute("SELECT id FROM documents WHERE source = ?", (source,))]
            self.conn.executemany("DELETE FROM decisions WHERE document_id = ?", [(i,) for i in ids])
            self.conn.executemany("DELETE FROM forecasts WHERE document_id = ?", [(i,) for i in ids])
            if decision_rows:
                cols = list(decision_rows[0])
                self.conn.executemany(
                    f"INSERT INTO decisions ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    [tuple(r[c] for c in cols) for r in decision_rows],
                )
            self.conn.executemany(
                "INSERT OR REPLACE INTO forecasts (document_id, vintage, vintage_date, series, period, value) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                forecast_rows,
            )

    def decisions(self, since: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM decisions"
        params: list = []
        if since:
            sql += " WHERE doc_date >= ?"
            params.append(since)
        return self.conn.execute(sql + " ORDER BY doc_date", params).fetchall()

    def decision(self, doc_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM decisions WHERE document_id = ?", (doc_id,)).fetchone()

    def forecasts(self, doc_id: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM forecasts WHERE document_id = ? ORDER BY series, vintage, period", (doc_id,)
        ).fetchall()

    def paragraphs(self, doc_id: str) -> list[tuple[str | None, str]]:
        return [(r["section"], r["text"]) for r in self.conn.execute(
            "SELECT section, text FROM segments WHERE document_id = ? AND kind = 'paragraph' ORDER BY seq",
            (doc_id,))]

    # --- arquivos -----------------------------------------------------------
    def raw_path_for(self, row: sqlite3.Row, ext: str) -> Path:
        year = row["doc_date"][:4]
        return self.raw_dir / row["source"] / year / f"{row['doc_date']}_{row['remote_id']}.{ext}"

    def text_path_for(self, row: sqlite3.Row) -> Path:
        year = row["doc_date"][:4]
        return self.data_dir / "text" / row["source"] / year / f"{row['doc_date']}_{row['remote_id']}.md"

    def abs_path(self, relative: str) -> Path:
        return self.data_dir / relative
