"""
Core memory store with SQLite backend, git-like versioning, compression, and search.
"""
import sqlite3
import json
import hashlib
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class MemoryStore:
    """Git-like versioned memory store backed by SQLite."""

    def __init__(self, db_path: str = "~/.agent-memory-forge/memory.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                content TEXT NOT NULL,
                compressed INTEGER DEFAULT 0,
                content_hash TEXT NOT NULL,
                tags TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                importance REAL DEFAULT 0.5,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                is_deleted INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS memory_versions (
                version_id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                version INTEGER NOT NULL,
                commit_message TEXT DEFAULT '',
                committed_at TEXT NOT NULL,
                FOREIGN KEY (memory_id) REFERENCES memories(id)
            );

            CREATE TABLE IF NOT EXISTS branches (
                branch_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                name TEXT NOT NULL,
                head_version_id TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(agent_id, name)
            );

            CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent_id);
            CREATE INDEX IF NOT EXISTS idx_memories_tags ON memories(tags);
            CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
            CREATE INDEX IF NOT EXISTS idx_versions_memory ON memory_versions(memory_id);
        """)
        self.conn.commit()

    def _generate_id(self, content: str) -> str:
        """Generate unique ID from content hash + timestamp."""
        ts = str(time.time_ns())
        return hashlib.sha256(f"{content}{ts}".encode()).hexdigest()[:16]

    def _hash(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    def _compress(self, content: str) -> bytes:
        return zlib.compress(content.encode(), level=6)

    def _decompress(self, data: bytes) -> str:
        return zlib.decompress(data).decode()

    def remember(
        self,
        agent_id: str,
        content: str,
        tags: Optional[list] = None,
        metadata: Optional[dict] = None,
        importance: float = 0.5,
        commit_message: str = "",
    ) -> str:
        """Store a new memory. Returns memory ID."""
        now = datetime.now(timezone.utc).isoformat()
        mem_id = self._generate_id(content)
        content_hash = self._hash(content)

        self.conn.execute(
            """INSERT INTO memories (id, agent_id, content, content_hash, tags, metadata, importance, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mem_id,
                agent_id,
                content,
                content_hash,
                json.dumps(tags or []),
                json.dumps(metadata or {}),
                importance,
                now,
                now,
            ),
        )

        # Create initial version
        version_id = self._generate_id(f"v1{mem_id}")
        self.conn.execute(
            """INSERT INTO memory_versions (version_id, memory_id, content, content_hash, version, commit_message, committed_at)
               VALUES (?, ?, ?, ?, 1, ?, ?)""",
            (version_id, mem_id, content, content_hash, commit_message or "Initial memory", now),
        )

        # Update or create main branch
        self._update_branch_head(agent_id, "main", version_id)

        self.conn.commit()
        return mem_id

    def recall(
        self,
        agent_id: str,
        query: Optional[str] = None,
        tags: Optional[list] = None,
        limit: int = 10,
        include_deleted: bool = False,
    ) -> list:
        """Recall memories by agent, optionally filtering by query/tags."""
        sql = "SELECT * FROM memories WHERE agent_id = ?"
        params: list = [agent_id]

        if not include_deleted:
            sql += " AND is_deleted = 0"

        if tags:
            for tag in tags:
                sql += " AND tags LIKE ?"
                params.append(f'%"{tag}"%')

        sql += " ORDER BY importance DESC, created_at DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(sql, params).fetchall()
        results = []
        for row in rows:
            mem = dict(row)
            mem["tags"] = json.loads(mem["tags"])
            mem["metadata"] = json.loads(mem["metadata"])

            # Simple text matching if query provided
            if query:
                query_lower = query.lower()
                content_lower = mem["content"].lower()
                tag_match = any(query_lower in t.lower() for t in mem["tags"])
                if query_lower not in content_lower and not tag_match:
                    continue

            results.append(mem)

        return results

    def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        tags: Optional[list] = None,
        metadata: Optional[dict] = None,
        importance: Optional[float] = None,
        commit_message: str = "",
    ) -> bool:
        """Update a memory, creating a new version."""
        row = self.conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if not row:
            return False

        row = dict(row)
        now = datetime.now(timezone.utc).isoformat()
        new_content = content if content is not None else row["content"]
        new_hash = self._hash(new_content)
        new_tags = json.dumps(tags if tags is not None else json.loads(row["tags"]))
        new_meta = json.dumps(metadata if metadata is not None else json.loads(row["metadata"]))
        new_importance = importance if importance is not None else row["importance"]
        new_version = row["version"] + 1

        # Update memory
        self.conn.execute(
            """UPDATE memories SET content=?, content_hash=?, tags=?, metadata=?,
               importance=?, updated_at=?, version=? WHERE id=?""",
            (new_content, new_hash, new_tags, new_meta, new_importance, now, new_version, memory_id),
        )

        # Create version entry
        version_id = self._generate_id(f"v{new_version}{memory_id}")
        self.conn.execute(
            """INSERT INTO memory_versions (version_id, memory_id, content, content_hash, version, commit_message, committed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (version_id, memory_id, new_content, new_hash, new_version, commit_message or f"Update v{new_version}", now),
        )

        self._update_branch_head(row["agent_id"], "main", version_id)
        self.conn.commit()
        return True

    def forget(self, memory_id: str, hard: bool = False) -> bool:
        """Soft-delete or hard-delete a memory."""
        row = self.conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if not row:
            return False

        if hard:
            self.conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            self.conn.execute("DELETE FROM memory_versions WHERE memory_id = ?", (memory_id,))
        else:
            self.conn.execute("UPDATE memories SET is_deleted=1, updated_at=? WHERE id = ?",
                            (datetime.now(timezone.utc).isoformat(), memory_id))
        self.conn.commit()
        return True

    def get_versions(self, memory_id: str) -> list:
        """Get version history for a memory."""
        rows = self.conn.execute(
            "SELECT * FROM memory_versions WHERE memory_id = ? ORDER BY version",
            (memory_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def rollback(self, memory_id: str, version: int) -> bool:
        """Rollback memory to a specific version."""
        row = self.conn.execute(
            "SELECT * FROM memory_versions WHERE memory_id = ? AND version = ?",
            (memory_id, version),
        ).fetchone()
        if not row:
            return False

        row = dict(row)
        now = datetime.now(timezone.utc).isoformat()
        mem = self.conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        mem = dict(mem)
        new_version = mem["version"] + 1

        self.conn.execute(
            """UPDATE memories SET content=?, content_hash=?, updated_at=?, version=? WHERE id=?""",
            (row["content"], row["content_hash"], now, new_version, memory_id),
        )

        version_id = self._generate_id(f"v{new_version}{memory_id}")
        self.conn.execute(
            """INSERT INTO memory_versions (version_id, memory_id, content, content_hash, version, commit_message, committed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (version_id, memory_id, row["content"], row["content_hash"], new_version,
             f"Rollback to v{version}", now),
        )

        self._update_branch_head(mem["agent_id"], "main", version_id)
        self.conn.commit()
        return True

    def _update_branch_head(self, agent_id: str, branch_name: str, version_id: str):
        """Update branch head pointer."""
        now = datetime.now(timezone.utc).isoformat()
        branch_id = f"{agent_id}/{branch_name}"
        existing = self.conn.execute(
            "SELECT branch_id FROM branches WHERE branch_id = ?", (branch_id,)
        ).fetchone()

        if existing:
            self.conn.execute(
                "UPDATE branches SET head_version_id = ? WHERE branch_id = ?",
                (version_id, branch_id),
            )
        else:
            self.conn.execute(
                "INSERT INTO branches (branch_id, agent_id, name, head_version_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (branch_id, agent_id, branch_name, version_id, now),
            )

    def share_memory(self, memory_id: str, target_agent_id: str, new_tags: Optional[list] = None) -> str:
        """Share a memory with another agent (cross-agent memory sharing)."""
        row = self.conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if not row:
            raise ValueError(f"Memory {memory_id} not found")

        row = dict(row)
        now = datetime.now(timezone.utc).isoformat()
        new_id = self._generate_id(f"shared{target_agent_id}{memory_id}")
        tags = new_tags if new_tags is not None else json.loads(row["tags"])
        tags.append(f"shared_from:{row['agent_id']}")

        self.conn.execute(
            """INSERT INTO memories (id, agent_id, content, content_hash, tags, metadata, importance, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (new_id, target_agent_id, row["content"], row["content_hash"],
             json.dumps(tags), row["metadata"], row["importance"], now, now),
        )

        version_id = self._generate_id(f"v1{new_id}")
        self.conn.execute(
            """INSERT INTO memory_versions (version_id, memory_id, content, content_hash, version, commit_message, committed_at)
               VALUES (?, ?, ?, ?, 1, ?, ?)""",
            (version_id, new_id, row["content"], row["content_hash"],
             f"Shared from agent '{row['agent_id']}'", now),
        )

        self._update_branch_head(target_agent_id, "main", version_id)
        self.conn.commit()
        return new_id

    def get_stats(self, agent_id: str) -> dict:
        """Get memory statistics for an agent."""
        total = self.conn.execute(
            "SELECT COUNT(*) FROM memories WHERE agent_id = ? AND is_deleted = 0", (agent_id,)
        ).fetchone()[0]

        deleted = self.conn.execute(
            "SELECT COUNT(*) FROM memories WHERE agent_id = ? AND is_deleted = 1", (agent_id,)
        ).fetchone()[0]

        avg_importance = self.conn.execute(
            "SELECT AVG(importance) FROM memories WHERE agent_id = ? AND is_deleted = 0", (agent_id,)
        ).fetchone()[0]

        all_tags_raw = self.conn.execute(
            "SELECT tags FROM memories WHERE agent_id = ? AND is_deleted = 0", (agent_id,)
        ).fetchall()

        tag_counts: dict = {}
        for (tags_str,) in all_tags_raw:
            for t in json.loads(tags_str):
                tag_counts[t] = tag_counts.get(t, 0) + 1

        versions_count = self.conn.execute(
            "SELECT COUNT(*) FROM memory_versions mv JOIN memories m ON mv.memory_id = m.id WHERE m.agent_id = ?",
            (agent_id,),
        ).fetchone()[0]

        return {
            "agent_id": agent_id,
            "total_memories": total,
            "deleted_memories": deleted,
            "total_versions": versions_count,
            "avg_importance": round(avg_importance or 0, 2),
            "top_tags": sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10],
        }

    def export_memories(self, agent_id: str, format: str = "json") -> str:
        """Export all memories for an agent."""
        memories = self.recall(agent_id, limit=10000, include_deleted=True)
        if format == "json":
            return json.dumps(memories, indent=2, default=str)
        elif format == "markdown":
            lines = [f"# Memory Export — Agent: {agent_id}\n"]
            for m in memories:
                status = "🗑️ " if m.get("is_deleted") else "🧠 "
                lines.append(f"## {status}{m['id']} (v{m['version']})")
                lines.append(f"- **Tags:** {', '.join(m['tags'])}")
                lines.append(f"- **Importance:** {m['importance']}")
                lines.append(f"- **Created:** {m['created_at']}")
                lines.append(f"\n{m['content']}\n")
                lines.append("---\n")
            return "\n".join(lines)
        else:
            raise ValueError(f"Unknown format: {format}")

    def import_memories(self, agent_id: str, data: str, format: str = "json") -> int:
        """Import memories from JSON."""
        if format != "json":
            raise ValueError(f"Unknown format: {format}")

        items = json.loads(data)
        count = 0
        for item in items:
            content = item.get("content", "")
            tags = item.get("tags", [])
            if isinstance(tags, str):
                tags = json.loads(tags)
            metadata = item.get("metadata", {})
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            importance = item.get("importance", 0.5)

            self.remember(agent_id, content, tags=tags, metadata=metadata,
                         importance=importance, commit_message="Imported")
            count += 1

        return count

    def close(self):
        self.conn.close()
