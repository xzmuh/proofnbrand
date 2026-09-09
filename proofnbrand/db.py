"""Camada de banco. SQLite por padrao; Postgres/Neon se PNB_DB_URL estiver setada.

O SQL e escrito uma vez com placeholder '?' e traduzido para '%s' no Postgres.
Os UPSERTs usam 'ON CONFLICT ... DO UPDATE', suportado pelos dois.
"""
import json
import os
import re
import sqlite3
from contextlib import contextmanager

DEFAULT_SQLITE = os.path.join(os.getcwd(), "leads.db")

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS leads (
        id           TEXT PRIMARY KEY,
        source       TEXT,
        name         TEXT,
        category     TEXT,
        city         TEXT,
        country      TEXT,
        currency     TEXT,
        lat          REAL,
        lon          REAL,
        phone        TEXT,
        email        TEXT,
        website      TEXT,
        address      TEXT,
        tags         TEXT,
        first_seen   TEXT,
        last_seen    TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS probes (
        lead_id      TEXT PRIMARY KEY,
        checked_at   TEXT,
        final_url    TEXT,
        status_code  INTEGER,
        reachable    INTEGER,
        error        TEXT,
        ttfb_ms      INTEGER,
        html_bytes   INTEGER,
        https        INTEGER,
        responsive   INTEGER,
        platform     TEXT,
        copyright_year INTEGER,
        has_title    INTEGER,
        has_meta_desc INTEGER,
        has_og       INTEGER,
        has_schema   INTEGER,
        has_favicon  INTEGER,
        legacy_html  INTEGER,
        signals      TEXT,
        found_email  TEXT,
        found_phone  TEXT,
        found_whats  TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS psi (
        lead_id      TEXT PRIMARY KEY,
        checked_at   TEXT,
        perf         REAL,
        seo          REAL,
        a11y         REAL,
        best         REAL,
        lcp_ms       REAL,
        cls          REAL,
        tbt_ms       REAL,
        error        TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS scores (
        lead_id      TEXT PRIMARY KEY,
        score        REAL,
        tier         TEXT,
        lead_type    TEXT,
        reasons      TEXT,
        pitch        TEXT,
        computed_at  TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS lead_status (
        lead_id      TEXT PRIMARY KEY,
        status       TEXT,
        notes        TEXT,
        updated_at   TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS geocache (
        key          TEXT PRIMARY KEY,
        payload      TEXT,
        cached_at    TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_leads_city ON leads(city)",
    "CREATE INDEX IF NOT EXISTS idx_scores_score ON scores(score)",
    "CREATE INDEX IF NOT EXISTS idx_leads_category ON leads(category)",
]


class Database:
    def __init__(self, url=None):
        self.url = url or os.environ.get("PNB_DB_URL") or ""
        self.is_pg = self.url.startswith("postgres")
        if self.is_pg:
            try:
                import psycopg  # noqa: F401
            except ImportError:
                raise SystemExit(
                    "PNB_DB_URL aponta para Postgres mas psycopg nao esta instalado.\n"
                    "Rode: pip install 'psycopg[binary]'"
                )
            import psycopg

            self.conn = psycopg.connect(self.url)
        else:
            path = self.url or DEFAULT_SQLITE
            self.conn = sqlite3.connect(path)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
            # A colheita e a descoberta podem escrever ao mesmo tempo que o
            # painel le; espera a trava em vez de estourar "database is locked".
            self.conn.execute("PRAGMA busy_timeout=15000")
        self.migrate()

    def _sql(self, sql):
        return re.sub(r"\?", "%s", sql) if self.is_pg else sql

    # Colunas acrescentadas depois da v1: bancos antigos ganham elas aqui.
    ADDED_COLUMNS = (
        ("probes", "found_email", "TEXT"),
        ("probes", "found_phone", "TEXT"),
        ("probes", "found_whats", "TEXT"),
        ("leads", "discovered_at", "TEXT"),
        ("leads", "website_source", "TEXT"),
    )

    def migrate(self):
        cur = self.conn.cursor()
        for stmt in SCHEMA:
            cur.execute(stmt)
        for table, column, coltype in self.ADDED_COLUMNS:
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            except Exception:
                pass  # ja existe
        self.conn.commit()

    def execute(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), params)
        return cur

    def executemany(self, sql, seq):
        cur = self.conn.cursor()
        cur.executemany(self._sql(sql), seq)
        return cur

    def query(self, sql, params=()):
        """Sempre devolve lista de dicts, independente do driver."""
        cur = self.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ---------- helpers de dominio ----------

    def upsert_lead(self, lead):
        self.execute(
            """INSERT INTO leads (id, source, name, category, city, country, currency,
                                  lat, lon, phone, email, website, address, tags,
                                  first_seen, last_seen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT (id) DO UPDATE SET
                   name=EXCLUDED.name, phone=EXCLUDED.phone, email=EXCLUDED.email,
                   website=EXCLUDED.website, address=EXCLUDED.address,
                   tags=EXCLUDED.tags, last_seen=EXCLUDED.last_seen""",
            (
                lead["id"], lead["source"], lead["name"], lead["category"],
                lead["city"], lead["country"], lead["currency"],
                lead["lat"], lead["lon"], lead["phone"], lead["email"],
                lead["website"], lead["address"], json.dumps(lead["tags"], ensure_ascii=False),
                lead["first_seen"], lead["last_seen"],
            ),
        )

    def cache_get(self, key):
        rows = self.query("SELECT payload FROM geocache WHERE key = ?", (key,))
        return json.loads(rows[0]["payload"]) if rows else None

    def cache_set(self, key, payload, when):
        self.execute(
            """INSERT INTO geocache (key, payload, cached_at) VALUES (?,?,?)
               ON CONFLICT (key) DO UPDATE SET payload=EXCLUDED.payload,
                                               cached_at=EXCLUDED.cached_at""",
            (key, json.dumps(payload, ensure_ascii=False), when),
        )
        self.commit()


@contextmanager
def open_db(url=None):
    db = Database(url)
    try:
        yield db
    finally:
        db.close()
