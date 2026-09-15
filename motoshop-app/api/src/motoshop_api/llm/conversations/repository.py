"""Repositorio tenant-aware para conversaciones y mensajes del agente.

La implementación productiva usa Supabase REST con la service key. La
validación de tenant y usuario se hace siempre en el servidor antes de cada
operación; el repositorio en memoria queda como fallback local y fixture de
tests cuando Supabase no está configurado.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Protocol
from uuid import UUID, uuid4

import httpx

from motoshop_api.config import settings

logger = logging.getLogger(__name__)


class ConversationRepository(Protocol):
    def list_conversations(
        self, tenant_id: str, user_id: str, limit: int = 30
    ) -> list[dict[str, Any]]: ...

    def create_conversation(
        self, tenant_id: str, user_id: str, title: str = "Nueva conversación"
    ) -> dict[str, Any]: ...

    def get_conversation(
        self, tenant_id: str, user_id: str, conversation_id: str
    ) -> dict[str, Any] | None: ...

    def list_messages(
        self, tenant_id: str, user_id: str, conversation_id: str, limit: int = 40
    ) -> list[dict[str, Any]]: ...

    def append_turn(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        *,
        request_id: str | None = None,
        tools_used: list[str] | None = None,
        sources: list[dict[str, Any]] | None = None,
        freshness: list[dict[str, Any]] | None = None,
        entity_refs: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        model: str | None = None,
        provider: str | None = None,
        tokens_input: int = 0,
        tokens_output: int = 0,
        latency_ms: int = 0,
        status: str = "success",
        error_code: str | None = None,
    ) -> None: ...

    def archive_conversation(self, tenant_id: str, user_id: str, conversation_id: str) -> bool: ...

    def rename_conversation(
        self, tenant_id: str, user_id: str, conversation_id: str, title: str
    ) -> bool: ...


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _after(timestamp: str) -> str:
    return (datetime.fromisoformat(timestamp) + timedelta(microseconds=1)).isoformat()


def _valid_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


class InMemoryConversationRepository:
    """Repositorio aislado por tenant y usuario para desarrollo/tests."""

    def __init__(self) -> None:
        self._conversations: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._messages: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    def list_conversations(
        self, tenant_id: str, user_id: str, limit: int = 30
    ) -> list[dict[str, Any]]:
        rows = [
            row
            for (tenant, user, _), row in self._conversations.items()
            if tenant == tenant_id and user == user_id and row["status"] == "active"
        ]
        rows.sort(key=lambda row: row["last_message_at"], reverse=True)
        return rows[:limit]

    def create_conversation(
        self, tenant_id: str, user_id: str, title: str = "Nueva conversación"
    ) -> dict[str, Any]:
        conversation_id = str(uuid4())
        now = _now()
        row = {
            "id": conversation_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "title": title[:120],
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "last_message_at": now,
            "message_count": 0,
        }
        self._conversations[(tenant_id, user_id, conversation_id)] = row
        self._messages[(tenant_id, user_id, conversation_id)] = []
        return row

    def get_conversation(
        self, tenant_id: str, user_id: str, conversation_id: str
    ) -> dict[str, Any] | None:
        return self._conversations.get((tenant_id, user_id, conversation_id))

    def list_messages(
        self, tenant_id: str, user_id: str, conversation_id: str, limit: int = 40
    ) -> list[dict[str, Any]]:
        rows = self._messages.get((tenant_id, user_id, conversation_id), [])
        return rows[-limit:]

    def append_turn(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        **metadata: Any,
    ) -> None:
        key = (tenant_id, user_id, conversation_id)
        conversation = self._conversations.get(key)
        if conversation is None:
            conversation = self.create_conversation(tenant_id, user_id)
            conversation_id = conversation["id"]
            key = (tenant_id, user_id, conversation_id)
        now = _now()
        request_id = metadata.get("request_id") or str(uuid4())
        messages = self._messages.setdefault(key, [])
        if any(row.get("request_id") == request_id for row in messages):
            return
        messages.extend(
            [
                {
                    "id": str(uuid4()),
                    "conversation_id": conversation_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "role": "user",
                    "content": user_message,
                    "request_id": request_id,
                    "created_at": now,
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": conversation_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "role": "assistant",
                    "content": assistant_message,
                    "request_id": request_id,
                    "tools_used": metadata.get("tools_used", []),
                    "sources": metadata.get("sources", []),
                    "freshness": metadata.get("freshness", []),
                    "entity_refs": metadata.get("entity_refs", []),
                    "attachments": metadata.get("attachments", []),
                    "model": metadata.get("model"),
                    "provider": metadata.get("provider"),
                    "tokens_input": metadata.get("tokens_input", 0),
                    "tokens_output": metadata.get("tokens_output", 0),
                    "latency_ms": metadata.get("latency_ms", 0),
                    "status": metadata.get("status", "success"),
                    "error_code": metadata.get("error_code"),
                    "created_at": now,
                },
            ]
        )
        conversation["message_count"] = len(messages)
        conversation["updated_at"] = now
        conversation["last_message_at"] = now
        if conversation.get("title") == "Nueva conversación":
            conversation["title"] = user_message[:80]

    def archive_conversation(self, tenant_id: str, user_id: str, conversation_id: str) -> bool:
        row = self._conversations.get((tenant_id, user_id, conversation_id))
        if row is None:
            return False
        row["status"] = "archived"
        row["updated_at"] = _now()
        return True

    def rename_conversation(
        self, tenant_id: str, user_id: str, conversation_id: str, title: str
    ) -> bool:
        row = self._conversations.get((tenant_id, user_id, conversation_id))
        if row is None:
            return False
        row["title"] = title[:120]
        row["updated_at"] = _now()
        return True


class SQLiteConversationRepository:
    """Persistencia local durable, adecuada para Raspberry y desarrollo offline."""

    def __init__(self, path: str) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        with self._connect() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS agent_conversations (
                    id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, user_id TEXT NOT NULL,
                    title TEXT NOT NULL, status TEXT NOT NULL, message_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    last_message_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS conversation_owner_idx
                    ON agent_conversations(tenant_id, user_id, last_message_at DESC);
                CREATE TABLE IF NOT EXISTS agent_messages (
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, tenant_id TEXT NOT NULL,
                    user_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
                    request_id TEXT, tools_used TEXT NOT NULL, sources TEXT NOT NULL,
                    model TEXT, provider TEXT, tokens_input INTEGER NOT NULL,
                    tokens_output INTEGER NOT NULL, latency_ms INTEGER NOT NULL,
                    status TEXT NOT NULL, error_code TEXT, created_at TEXT NOT NULL,
                    evidence TEXT NOT NULL DEFAULT '[]', freshness TEXT NOT NULL DEFAULT '[]',
                    entity_refs TEXT NOT NULL DEFAULT '[]', attachments TEXT NOT NULL DEFAULT '[]',
                    FOREIGN KEY(conversation_id) REFERENCES agent_conversations(id)
                        ON DELETE CASCADE,
                    UNIQUE(conversation_id, request_id, role)
                );
            """)
            for column in ("evidence", "freshness", "entity_refs", "attachments"):
                try:
                    con.execute(
                        f"ALTER TABLE agent_messages ADD COLUMN {column} TEXT NOT NULL DEFAULT '[]'"
                    )
                except sqlite3.OperationalError as exc:
                    if "duplicate column" not in str(exc).lower():
                        raise

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=5)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    @staticmethod
    def _conversation(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    @staticmethod
    def _message(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["tools_used"] = json.loads(result.get("tools_used") or "[]")
        result["sources"] = json.loads(result.get("sources") or "[]")
        result["freshness"] = json.loads(result.get("freshness") or "[]")
        result["entity_refs"] = json.loads(result.get("entity_refs") or "[]")
        result["attachments"] = json.loads(result.get("attachments") or "[]")
        return result

    def list_conversations(
        self, tenant_id: str, user_id: str, limit: int = 30
    ) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM agent_conversations "
                "WHERE tenant_id=? AND user_id=? AND status='active' "
                "ORDER BY last_message_at DESC LIMIT ?",
                (tenant_id, user_id, max(1, min(limit, 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_conversation(
        self, tenant_id: str, user_id: str, title: str = "Nueva conversación"
    ) -> dict[str, Any]:
        row = {
            "id": str(uuid4()),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "title": title[:120],
            "status": "active",
            "message_count": 0,
            "created_at": _now(),
            "updated_at": _now(),
            "last_message_at": _now(),
        }
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT INTO agent_conversations VALUES "
                "(:id,:tenant_id,:user_id,:title,:status,:message_count,"
                ":created_at,:updated_at,:last_message_at)",
                row,
            )
        return row

    def get_conversation(
        self, tenant_id: str, user_id: str, conversation_id: str
    ) -> dict[str, Any] | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM agent_conversations WHERE id=? AND tenant_id=? AND user_id=?",
                (conversation_id, tenant_id, user_id),
            ).fetchone()
        return self._conversation(row)

    def list_messages(
        self, tenant_id: str, user_id: str, conversation_id: str, limit: int = 40
    ) -> list[dict[str, Any]]:
        if not self.get_conversation(tenant_id, user_id, conversation_id):
            return []
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM agent_messages "
                "WHERE conversation_id=? AND tenant_id=? AND user_id=? "
                "ORDER BY created_at ASC LIMIT ?",
                (conversation_id, tenant_id, user_id, max(1, min(limit, 100))),
            ).fetchall()
        return [self._message(row) for row in rows]

    def append_turn(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        **metadata: Any,
    ) -> None:
        request_id = metadata.get("request_id") or str(uuid4())
        now = _now()
        assistant_at = _after(now)
        common = (conversation_id, tenant_id, user_id, request_id)
        with self._lock, self._connect() as con:
            owner = con.execute(
                "SELECT title, message_count FROM agent_conversations "
                "WHERE id=? AND tenant_id=? AND user_id=?",
                (conversation_id, tenant_id, user_id),
            ).fetchone()
            if owner is None:
                raise PermissionError("conversation_not_owned")
            con.execute(
                "INSERT OR IGNORE INTO agent_messages VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    *common[:3],
                    "user",
                    user_message,
                    request_id,
                    "[]",
                    "[]",
                    None,
                    None,
                    0,
                    0,
                    0,
                    "success",
                    None,
                    now,
                    "[]",
                    "[]",
                    "[]",
                    "[]",
                ),
            )
            con.execute(
                "INSERT OR IGNORE INTO agent_messages VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    *common[:3],
                    "assistant",
                    assistant_message,
                    request_id,
                    json.dumps(metadata.get("tools_used", [])),
                    json.dumps(metadata.get("sources", [])),
                    metadata.get("model"),
                    metadata.get("provider"),
                    metadata.get("tokens_input", 0),
                    metadata.get("tokens_output", 0),
                    metadata.get("latency_ms", 0),
                    metadata.get("status", "success"),
                    metadata.get("error_code"),
                    assistant_at,
                    json.dumps(metadata.get("sources", [])),
                    json.dumps(metadata.get("freshness", [])),
                    json.dumps(metadata.get("entity_refs", [])),
                    json.dumps(metadata.get("attachments", [])),
                ),
            )
            count = con.execute(
                "SELECT COUNT(*) FROM agent_messages WHERE conversation_id=?", (conversation_id,)
            ).fetchone()[0]
            title = user_message[:80] if owner["message_count"] == 0 else owner["title"]
            con.execute(
                "UPDATE agent_conversations SET title=?, message_count=?, "
                "updated_at=?, last_message_at=? WHERE id=?",
                (title, count, now, now, conversation_id),
            )

    def archive_conversation(self, tenant_id: str, user_id: str, conversation_id: str) -> bool:
        with self._lock, self._connect() as con:
            cursor = con.execute(
                "UPDATE agent_conversations SET status='archived', updated_at=? "
                "WHERE id=? AND tenant_id=? AND user_id=?",
                (_now(), conversation_id, tenant_id, user_id),
            )
        return cursor.rowcount > 0

    def rename_conversation(
        self, tenant_id: str, user_id: str, conversation_id: str, title: str
    ) -> bool:
        with self._lock, self._connect() as con:
            cursor = con.execute(
                "UPDATE agent_conversations SET title=?, updated_at=? "
                "WHERE id=? AND tenant_id=? AND user_id=?",
                (title[:120], _now(), conversation_id, tenant_id, user_id),
            )
        return cursor.rowcount > 0


class SupabaseConversationRepository:
    """Persistencia REST contra tablas tenant-scoped de Supabase."""

    def __init__(self) -> None:
        if not settings.supabase_url or not settings.supabase_service_key:
            raise RuntimeError("Supabase no está configurado")
        self._base = f"{settings.supabase_url.rstrip('/')}/rest/v1"
        self._headers = {
            "apikey": settings.supabase_service_key,
            "Authorization": f"Bearer {settings.supabase_service_key}",
            "Content-Type": "application/json",
        }
        self._http = httpx.Client(timeout=httpx.Timeout(8.0))

    def healthcheck(self) -> None:
        self._request("GET", "agent_conversations", params={"select": "id", "limit": "1"})

    def _request(
        self, method: str, table: str, *, headers: dict[str, str] | None = None, **kwargs: Any
    ) -> list[dict[str, Any]]:
        request_headers = {**self._headers, **(headers or {})}
        response = self._http.request(
            method, f"{self._base}/{table}", headers=request_headers, **kwargs
        )
        response.raise_for_status()
        if not response.content:
            return []
        payload = response.json()
        return payload if isinstance(payload, list) else [payload]

    def list_conversations(
        self, tenant_id: str, user_id: str, limit: int = 30
    ) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            "agent_conversations",
            params={
                "tenant_id": f"eq.{tenant_id}",
                "user_id": f"eq.{user_id}",
                "status": "eq.active",
                "select": "*",
                "order": "last_message_at.desc",
                "limit": str(limit),
            },
        )

    def create_conversation(
        self, tenant_id: str, user_id: str, title: str = "Nueva conversación"
    ) -> dict[str, Any]:
        rows = self._request(
            "POST",
            "agent_conversations",
            json={
                "tenant_id": tenant_id,
                "user_id": user_id,
                "title": title[:120],
                "status": "active",
            },
            headers={**self._headers, "Prefer": "return=representation"},
        )
        return rows[0]

    def get_conversation(
        self, tenant_id: str, user_id: str, conversation_id: str
    ) -> dict[str, Any] | None:
        if not _valid_uuid(conversation_id):
            return None
        rows = self._request(
            "GET",
            "agent_conversations",
            params={
                "id": f"eq.{conversation_id}",
                "tenant_id": f"eq.{tenant_id}",
                "user_id": f"eq.{user_id}",
                "select": "*",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def list_messages(
        self, tenant_id: str, user_id: str, conversation_id: str, limit: int = 40
    ) -> list[dict[str, Any]]:
        if not self.get_conversation(tenant_id, user_id, conversation_id):
            return []
        return self._request(
            "GET",
            "agent_messages",
            params={
                "conversation_id": f"eq.{conversation_id}",
                "tenant_id": f"eq.{tenant_id}",
                "user_id": f"eq.{user_id}",
                "select": "*",
                "order": "created_at.asc",
                "limit": str(limit),
            },
        )

    def append_turn(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        **metadata: Any,
    ) -> None:
        conversation = self.get_conversation(tenant_id, user_id, conversation_id)
        if not conversation:
            raise PermissionError("conversation_not_owned")
        request_id = metadata.get("request_id") or str(uuid4())
        now = _now()
        assistant_at = _after(now)
        rows = [
            {
                "conversation_id": conversation_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "role": "user",
                "content": user_message,
                "request_id": request_id,
                "created_at": now,
            },
            {
                "conversation_id": conversation_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "role": "assistant",
                "content": assistant_message,
                "request_id": request_id,
                "tools_used": metadata.get("tools_used", []),
                "sources": metadata.get("sources", []),
                "evidence": metadata.get("sources", []),
                "freshness": metadata.get("freshness", []),
                "entity_refs": metadata.get("entity_refs", []),
                "attachments": metadata.get("attachments", []),
                "model": metadata.get("model"),
                "provider": metadata.get("provider"),
                "tokens_input": metadata.get("tokens_input", 0),
                "tokens_output": metadata.get("tokens_output", 0),
                "latency_ms": metadata.get("latency_ms", 0),
                "status": metadata.get("status", "success"),
                "error_code": metadata.get("error_code"),
                "created_at": assistant_at,
            },
        ]
        try:
            self._request(
                "POST",
                "agent_messages",
                params={"on_conflict": "conversation_id,request_id,role"},
                json=rows,
                headers={"Prefer": "return=minimal,resolution=ignore-duplicates"},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (409,):
                raise
        update = {
            "updated_at": now,
            "last_message_at": now,
            "message_count": int(conversation.get("message_count", 0)) + 2,
        }
        if int(conversation.get("message_count", 0)) == 0:
            update["title"] = user_message[:80]
        self._request(
            "PATCH",
            "agent_conversations",
            params={
                "id": f"eq.{conversation_id}",
                "tenant_id": f"eq.{tenant_id}",
                "user_id": f"eq.{user_id}",
            },
            json=update,
        )

    def archive_conversation(self, tenant_id: str, user_id: str, conversation_id: str) -> bool:
        rows = self._request(
            "PATCH",
            "agent_conversations",
            params={
                "id": f"eq.{conversation_id}",
                "tenant_id": f"eq.{tenant_id}",
                "user_id": f"eq.{user_id}",
            },
            json={"status": "archived", "updated_at": _now()},
            headers={**self._headers, "Prefer": "return=representation"},
        )
        return bool(rows)

    def rename_conversation(
        self, tenant_id: str, user_id: str, conversation_id: str, title: str
    ) -> bool:
        rows = self._request(
            "PATCH",
            "agent_conversations",
            params={
                "id": f"eq.{conversation_id}",
                "tenant_id": f"eq.{tenant_id}",
                "user_id": f"eq.{user_id}",
            },
            json={"title": title[:120], "updated_at": _now()},
            headers={**self._headers, "Prefer": "return=representation"},
        )
        return bool(rows)


_repo: ConversationRepository | None = None


def get_conversation_repository() -> ConversationRepository:
    global _repo
    if _repo is not None:
        return _repo
    backend = settings.agent_conversation_backend.strip().lower()
    if backend not in {"auto", "supabase", "sqlite", "memory"}:
        raise RuntimeError("AGENT_CONVERSATION_BACKEND debe ser auto, supabase, sqlite o memory")
    if backend == "memory":
        _repo = InMemoryConversationRepository()
        return _repo
    if backend in {"auto", "supabase"} and settings.supabase_url and settings.supabase_service_key:
        try:
            supabase = SupabaseConversationRepository()
            supabase.healthcheck()
            _repo = supabase
            return _repo
        except Exception as exc:
            if backend == "supabase":
                raise RuntimeError("Supabase conversation store no disponible") from exc
            logger.warning(
                "agent_conversation_supabase_unavailable fallback=sqlite error=%s",
                type(exc).__name__,
            )
    elif backend == "supabase":
        raise RuntimeError("Supabase conversation store no configurado")
    _repo = SQLiteConversationRepository(settings.agent_conversation_db_path)
    return _repo


def reset_conversation_repository() -> None:
    """Hook de tests para evitar estado compartido entre casos."""
    global _repo
    _repo = None
