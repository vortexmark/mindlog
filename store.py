"""Storage and privacy layer: AES-256-GCM over SQLite (local) or PostgreSQL / Neon (hosted).

Backend is chosen at startup:
  * if DATABASE_URL is set to a postgres:// or postgresql:// URL  -> PostgreSQL (e.g. Neon)
  * otherwise                                                     -> a local SQLite file (mindlog.db)
The same functions are used either way, so the rest of the app does not change.

Privacy is identical on both backends, because the encryption happens here in Python:
  * The passphrase is never stored. scrypt turns it into 64 bytes: the first 32 are a login verifier
    (stored), the last 32 are the AES-256 key (kept only in memory while the user is logged in).
  * Every journal entry (text, mood, sleep, tags, labels, scores) is one encrypted blob. The database
    - SQLite file or Neon - holds only ciphertext and a timestamp.
  * Deleting the account deletes every row that belongs to the user.
"""
import contextlib, hashlib, hmac, json, os, secrets, threading, time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_PG = DATABASE_URL.startswith(("postgres://", "postgresql://"))

if USE_PG:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg import errors as pg_errors
    _DUPLICATE = (pg_errors.UniqueViolation,)
    P, BYTEA, PK, INT = "%s", "BYTEA", "BIGSERIAL PRIMARY KEY", "BIGINT"
else:
    import sqlite3
    DB_PATH = os.environ.get("MINDLOG_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "mindlog.db"))
    _DUPLICATE = (sqlite3.IntegrityError,)
    P, BYTEA, PK, INT = "?", "BLOB", "INTEGER PRIMARY KEY", "INTEGER"

SESSION_MINUTES = 60
_lock = threading.Lock()         # serialises writes
_schema_lock = threading.Lock()  # separate, so creating the schema inside db() can never
                                 # deadlock a caller that already holds _lock (register, add_entry)
_sessions = {}  # token -> {"user_id", "key", "expires"}  (never persisted; lost on restart, by design)

SCHEMA = [
    f"""CREATE TABLE IF NOT EXISTS users (id {PK}, username TEXT UNIQUE NOT NULL, salt {BYTEA} NOT NULL,
        verifier {BYTEA} NOT NULL, consent_at TEXT NOT NULL, research_consent INTEGER NOT NULL DEFAULT 0,
        weekly_goal INTEGER NOT NULL DEFAULT 4, profile {BYTEA}, created_at TEXT NOT NULL)""",
    f"""CREATE TABLE IF NOT EXISTS entries (id {PK}, user_id {INT} NOT NULL, created_at TEXT NOT NULL,
        nonce {BYTEA} NOT NULL, blob {BYTEA} NOT NULL)""",
    f"""CREATE TABLE IF NOT EXISTS corrections (id {PK}, user_id {INT} NOT NULL, entry_id {INT}, created_at TEXT NOT NULL,
        text TEXT NOT NULL, language TEXT, predicted TEXT NOT NULL, corrected TEXT NOT NULL)""",
]

_schema_ready = False


def _connect():
    if USE_PG:
        # Force UTF-8 so TEXT columns always come back as str (Neon is UTF-8; this also
        # protects against a SQL_ASCII database, where text would otherwise return as bytes).
        return psycopg.connect(DATABASE_URL, row_factory=dict_row, client_encoding="UTF8")
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


@contextlib.contextmanager
def db():
    """One short-lived connection per operation: commits on success, always closes.
    On the first use in a process it creates the tables if they do not exist."""
    global _schema_ready
    con = _connect()
    try:
        if not _schema_ready:
            with _schema_lock:
                if not _schema_ready:
                    cur = con.cursor()
                    for stmt in SCHEMA:
                        cur.execute(stmt)
                    con.commit()
                    _schema_ready = True
        yield con
        con.commit()
    finally:
        con.close()


def init():
    with db():
        pass


def _b(x):
    """Coerce a stored binary column (sqlite bytes, or psycopg memoryview) to plain bytes."""
    return bytes(x) if x is not None else None


def _insert_id(con, sql, params):
    """INSERT ... and return the new row's id on either backend."""
    if USE_PG:
        return con.execute(sql + " RETURNING id", params).fetchone()["id"]
    return con.execute(sql, params).lastrowid


def _derive(passphrase: str, salt: bytes):
    raw = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=64, maxmem=64 * 1024 * 1024)
    return raw[:32], raw[32:]


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _norm_user(username: str) -> str:
    """Usernames are matched case-insensitively and without surrounding spaces, so 'Amina' and ' amina '
    are the same account. This removes the commonest reason a correct passphrase was rejected."""
    return username.strip().lower()


def encrypt(key: bytes, obj, aad: str):
    nonce = secrets.token_bytes(12)
    return nonce, AESGCM(key).encrypt(nonce, json.dumps(obj, ensure_ascii=False).encode("utf-8"), aad.encode())


def decrypt(key: bytes, nonce: bytes, blob: bytes, aad: str):
    return json.loads(AESGCM(key).decrypt(_b(nonce), _b(blob), aad.encode()).decode("utf-8"))


# ------------------------------------------------------------------ accounts and sessions
def register(username: str, passphrase: str, research_consent: bool):
    username = _norm_user(username)
    salt = secrets.token_bytes(16)
    verifier, _ = _derive(passphrase, salt)
    try:
        with _lock, db() as con:
            _insert_id(con, f"INSERT INTO users (username, salt, verifier, consent_at, research_consent, created_at) "
                            f"VALUES ({P},{P},{P},{P},{P},{P})",
                       (username, salt, verifier, _now(), int(research_consent), _now()))
    except _DUPLICATE:
        return None
    return login(username, passphrase)


def login(username: str, passphrase: str):
    username = _norm_user(username)
    with db() as con:
        u = con.execute(f"SELECT * FROM users WHERE username={P}", (username,)).fetchone()
    if not u:
        _derive(passphrase, b"0" * 16)  # same work for unknown users (timing)
        return None
    verifier, key = _derive(passphrase, _b(u["salt"]))
    if not hmac.compare_digest(verifier, _b(u["verifier"])):
        return None
    token = secrets.token_urlsafe(32)
    _sessions[token] = {"user_id": u["id"], "key": key, "expires": time.time() + SESSION_MINUTES * 60}
    return token


def session(token: str):
    s = _sessions.get(token or "")
    if not s or s["expires"] < time.time():
        _sessions.pop(token, None)
        return None
    s["expires"] = time.time() + SESSION_MINUTES * 60
    return s


def logout(token: str):
    _sessions.pop(token, None)


def check_passphrase(user_id: int, passphrase: str) -> bool:
    with db() as con:
        u = con.execute(f"SELECT salt, verifier FROM users WHERE id={P}", (user_id,)).fetchone()
    return bool(u) and hmac.compare_digest(_derive(passphrase, _b(u["salt"]))[0], _b(u["verifier"]))


def get_user(s):
    with db() as con:
        u = con.execute(f"SELECT * FROM users WHERE id={P}", (s["user_id"],)).fetchone()
    prof = _b(u["profile"])
    profile = decrypt(s["key"], prof[:12], prof[12:], f"profile:{u['id']}") if prof else {}
    return {"username": u["username"], "consent_at": u["consent_at"], "research_consent": bool(u["research_consent"]),
            "weekly_goal": u["weekly_goal"], "habit": profile.get("habit", "")}


def update_settings(s, weekly_goal=None, habit=None, research_consent=None):
    with _lock, db() as con:
        if weekly_goal is not None:
            con.execute(f"UPDATE users SET weekly_goal={P} WHERE id={P}", (int(weekly_goal), s["user_id"]))
        if research_consent is not None:
            con.execute(f"UPDATE users SET research_consent={P} WHERE id={P}", (int(research_consent), s["user_id"]))
            if not research_consent:   # withdrawing consent removes what was shared
                con.execute(f"DELETE FROM corrections WHERE user_id={P}", (s["user_id"],))
        if habit is not None:
            nonce, blob = encrypt(s["key"], {"habit": habit}, f"profile:{s['user_id']}")
            con.execute(f"UPDATE users SET profile={P} WHERE id={P}", (nonce + blob, s["user_id"]))


def delete_account(s):
    with _lock, db() as con:
        for table in ("entries", "corrections"):
            con.execute(f"DELETE FROM {table} WHERE user_id={P}", (s["user_id"],))
        con.execute(f"DELETE FROM users WHERE id={P}", (s["user_id"],))
    for t in [t for t, v in _sessions.items() if v["user_id"] == s["user_id"]]:
        _sessions.pop(t, None)


# ------------------------------------------------------------------ entries
def add_entry(s, record: dict, created_at: str = None) -> int:
    created_at = created_at or _now()
    nonce, blob = encrypt(s["key"], record, f"{s['user_id']}:{created_at}")
    with _lock, db() as con:
        return _insert_id(con, f"INSERT INTO entries (user_id, created_at, nonce, blob) VALUES ({P},{P},{P},{P})",
                          (s["user_id"], created_at, nonce, blob))


def list_entries(s):
    with db() as con:
        rows = con.execute(f"SELECT * FROM entries WHERE user_id={P} ORDER BY created_at", (s["user_id"],)).fetchall()
    return [{"id": r["id"], "created_at": r["created_at"], **decrypt(s["key"], r["nonce"], r["blob"], f"{s['user_id']}:{r['created_at']}")} for r in rows]


def get_entry(s, entry_id: int):
    with db() as con:
        r = con.execute(f"SELECT * FROM entries WHERE id={P} AND user_id={P}", (entry_id, s["user_id"])).fetchone()
    if not r:
        return None
    return {"id": r["id"], "created_at": r["created_at"], **decrypt(s["key"], r["nonce"], r["blob"], f"{s['user_id']}:{r['created_at']}")}


def replace_entry(s, entry_id: int, created_at: str, record: dict):
    nonce, blob = encrypt(s["key"], record, f"{s['user_id']}:{created_at}")
    with _lock, db() as con:
        con.execute(f"UPDATE entries SET nonce={P}, blob={P} WHERE id={P} AND user_id={P}", (nonce, blob, entry_id, s["user_id"]))


def delete_entry(s, entry_id: int):
    with _lock, db() as con:
        con.execute(f"DELETE FROM entries WHERE id={P} AND user_id={P}", (entry_id, s["user_id"]))
        con.execute(f"DELETE FROM corrections WHERE entry_id={P} AND user_id={P}", (entry_id, s["user_id"]))


def add_correction(s, entry_id, text, language, predicted, corrected):
    """Only called when the user has opted in to sharing corrections. Stored readable so the team can retrain."""
    with _lock, db() as con:
        con.execute(f"DELETE FROM corrections WHERE entry_id={P} AND user_id={P}", (entry_id, s["user_id"]))
        _insert_id(con, f"INSERT INTO corrections (user_id, entry_id, created_at, text, language, predicted, corrected) "
                        f"VALUES ({P},{P},{P},{P},{P},{P},{P})",
                   (s["user_id"], entry_id, _now(), text, language, predicted, corrected))
