#!/usr/bin/env python3
"""
agent-memory-forge — Git-like versioning for AI agent memory
Unified memory system with compression and cross-agent sharing.
"""

import sqlite3
import json
import hashlib
import time
import zlib
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from difflib import unified_diff

# ── Configuration ──────────────────────────────────────────────────────────

DB_PATH = Path.home() / ".agent-memory-forge" / "memory.db"

# ── Database ──────────────────────────────────────────────────────────────

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    
    # Memory entries with versioning
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            importance REAL DEFAULT 0.5,
            agent TEXT DEFAULT 'shared',
            version INTEGER DEFAULT 1,
            timestamp TEXT NOT NULL,
            checksum TEXT NOT NULL,
            compressed INTEGER DEFAULT 0,
            is_current INTEGER DEFAULT 1,
            metadata TEXT DEFAULT '{}'
        )
    """)
    
    # Version history
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            change_type TEXT DEFAULT 'update',
            diff TEXT DEFAULT '',
            FOREIGN KEY (memory_id) REFERENCES memories(id)
        )
    """)
    
    # Cross-agent sharing registry
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shared_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id INTEGER NOT NULL,
            source_agent TEXT NOT NULL,
            target_agent TEXT NOT NULL,
            shared_at TEXT NOT NULL,
            FOREIGN KEY (memory_id) REFERENCES memories(id)
        )
    """)
    
    # Indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_agent ON memories(agent)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_current ON memories(is_current)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_history_memory ON memory_history(memory_id)")
    
    conn.commit()
    return conn

def get_conn():
    return sqlite3.connect(str(DB_PATH))

# ── Compression ───────────────────────────────────────────────────────────

def compress_content(content: str) -> bytes:
    """Compress content using zlib."""
    return zlib.compress(content.encode("utf-8"), level=6)

def decompress_content(data: bytes) -> str:
    """Decompress zlib-compressed content."""
    return zlib.decompress(data).decode("utf-8")

def should_compress(content: str, threshold: int = 500) -> bool:
    """Check if content should be compressed based on size."""
    return len(content) > threshold

# ── Checksum ──────────────────────────────────────────────────────────────

def compute_checksum(content: str) -> str:
    """Compute SHA-256 checksum of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

# ── Memory CRUD ───────────────────────────────────────────────────────────

def store_memory(key: str, content: str, category: str = "general",
                importance: float = 0.5, agent: str = "shared",
                metadata: dict = None) -> dict:
    """Store a memory entry with versioning."""
    conn = get_conn()
    now = datetime.now().isoformat()
    checksum = compute_checksum(content)
    
    # Check if key already exists
    existing = conn.execute(
        "SELECT id, version, content FROM memories WHERE key = ? AND is_current = 1",
        (key,)
    ).fetchone()
    
    if existing:
        mem_id, old_version, old_content = existing
        
        # Check if content actually changed
        if compute_checksum(old_content) == checksum:
            conn.close()
            return {"status": "unchanged", "key": key, "version": old_version}
        
        # Archive old version
        diff = "\n".join(unified_diff(
            old_content.splitlines(), content.splitlines(),
            lineterm="", fromfile=f"v{old_version}", tofile=f"v{old_version + 1}"
        ))
        
        conn.execute(
            "INSERT INTO memory_history (memory_id, version, content, timestamp, change_type, diff) VALUES (?, ?, ?, ?, ?, ?)",
            (mem_id, old_version, old_content, now, "update", diff)
        )
        
        # Update current
        use_compression = should_compress(content)
        stored_content = compress_content(content) if use_compression else content
        
        conn.execute("""
            UPDATE memories SET
                content = ?, version = ?, timestamp = ?, checksum = ?,
                compressed = ?, importance = ?, category = ?, metadata = ?
            WHERE id = ?
        """, (
            stored_content if not use_compression else content,
            old_version + 1, now, checksum,
            1 if use_compression else 0,
            importance, category, json.dumps(metadata or {}),
            mem_id
        ))
        
        conn.commit()
        conn.close()
        
        return {"status": "updated", "key": key, "version": old_version + 1}
    else:
        # New memory
        use_compression = should_compress(content)
        
        conn.execute("""
            INSERT INTO memories (key, content, category, importance, agent, version, timestamp, checksum, compressed, metadata)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
        """, (
            key, content, category, importance, agent,
            now, checksum, 1 if use_compression else 0,
            json.dumps(metadata or {})
        ))
        
        conn.commit()
        conn.close()
        
        return {"status": "created", "key": key, "version": 1}

def get_memory(key: str, version: int = None) -> dict:
    """Retrieve a memory by key, optionally at a specific version."""
    conn = get_conn()
    
    if version:
        # Get from history
        row = conn.execute("""
            SELECT h.content, h.version, h.timestamp, h.change_type
            FROM memory_history h
            JOIN memories m ON m.id = h.memory_id
            WHERE m.key = ? AND h.version = ?
        """, (key, version)).fetchone()
        
        if row:
            conn.close()
            return {"key": key, "content": row[0], "version": row[1], "timestamp": row[2], "source": "history"}
    else:
        # Get current
        row = conn.execute(
            "SELECT content, compressed, version, timestamp, category, importance, agent FROM memories WHERE key = ? AND is_current = 1",
            (key,)
        ).fetchone()
        
        if row:
            content = row[0]
            if row[1]:  # compressed
                content = decompress_content(content.encode())
            
            conn.close()
            return {
                "key": key, "content": content, "version": row[2],
                "timestamp": row[3], "category": row[4],
                "importance": row[5], "agent": row[6]
            }
    
    conn.close()
    return None

def search_memories(query: str = None, category: str = None, agent: str = None,
                   min_importance: float = 0.0, limit: int = 20) -> list:
    """Search memories with filters."""
    conn = get_conn()
    
    sql = "SELECT key, content, compressed, version, timestamp, category, importance, agent FROM memories WHERE is_current = 1"
    params = []
    
    if query:
        sql += " AND (key LIKE ? OR content LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%"])
    if category:
        sql += " AND category = ?"
        params.append(category)
    if agent:
        sql += " AND (agent = ? OR agent = 'shared')"
        params.append(agent)
    if min_importance > 0:
        sql += " AND importance >= ?"
        params.append(min_importance)
    
    sql += " ORDER BY importance DESC, timestamp DESC LIMIT ?"
    params.append(limit)
    
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    
    results = []
    for row in rows:
        content = row[1]
        if row[2]:  # compressed
            content = decompress_content(content.encode())
        results.append({
            "key": row[0], "content": content[:200] + "..." if len(content) > 200 else content,
            "version": row[3], "timestamp": row[4],
            "category": row[5], "importance": row[6], "agent": row[7]
        })
    
    return results

def get_history(key: str) -> list:
    """Get version history for a memory."""
    conn = get_conn()
    
    rows = conn.execute("""
        SELECT h.version, h.timestamp, h.change_type, h.diff
        FROM memory_history h
        JOIN memories m ON m.id = h.memory_id
        WHERE m.key = ?
        ORDER BY h.version DESC
    """, (key,)).fetchall()
    
    conn.close()
    
    return [{"version": r[0], "timestamp": r[1], "change_type": r[2], "diff": r[3][:500] if r[3] else ""} for r in rows]

def rollback(key: str, version: int) -> dict:
    """Rollback a memory to a previous version."""
    conn = get_conn()
    
    # Get the historical version
    row = conn.execute("""
        SELECT h.content, h.memory_id
        FROM memory_history h
        JOIN memories m ON m.id = h.memory_id
        WHERE m.key = ? AND h.version = ?
    """, (key, version)).fetchone()
    
    if not row:
        conn.close()
        return {"status": "error", "message": f"Version {version} not found for {key}"}
    
    content, mem_id = row
    now = datetime.now().isoformat()
    checksum = compute_checksum(content)
    
    # Get current for diff
    current = conn.execute("SELECT version, content FROM memories WHERE id = ?", (mem_id,)).fetchone()
    
    if current:
        old_version, old_content = current
        diff = "\n".join(unified_diff(
            old_content.splitlines(), content.splitlines(),
            lineterm="", fromfile=f"v{old_version}", tofile=f"v{version} (rollback)"
        ))
        
        conn.execute(
            "INSERT INTO memory_history (memory_id, version, content, timestamp, change_type, diff) VALUES (?, ?, ?, ?, ?, ?)",
            (mem_id, old_version, old_content, now, "rollback", diff)
        )
    
    # Restore
    conn.execute("""
        UPDATE memories SET content = ?, version = ?, timestamp = ?, checksum = ?, is_current = 1
        WHERE id = ?
    """, (content, version, now, checksum, mem_id))
    
    conn.commit()
    conn.close()
    
    return {"status": "rolled_back", "key": key, "to_version": version}

def share_memory(key: str, source_agent: str, target_agent: str) -> dict:
    """Share a memory from one agent to another."""
    conn = get_conn()
    
    mem = conn.execute(
        "SELECT id FROM memories WHERE key = ? AND is_current = 1", (key,)
    ).fetchone()
    
    if not mem:
        conn.close()
        return {"status": "error", "message": f"Memory {key} not found"}
    
    conn.execute("""
        INSERT INTO shared_memories (memory_id, source_agent, target_agent, shared_at)
        VALUES (?, ?, ?, ?)
    """, (mem[0], source_agent, target_agent, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    return {"status": "shared", "key": key, "from": source_agent, "to": target_agent}

def get_stats() -> dict:
    """Get memory database statistics."""
    conn = get_conn()
    
    total = conn.execute("SELECT COUNT(*) FROM memories WHERE is_current = 1").fetchone()[0]
    total_history = conn.execute("SELECT COUNT(*) FROM memory_history").fetchone()[0]
    total_shared = conn.execute("SELECT COUNT(*) FROM shared_memories").fetchone()[0]
    
    categories = conn.execute("""
        SELECT category, COUNT(*) FROM memories WHERE is_current = 1 GROUP BY category
    """).fetchall()
    
    agents = conn.execute("""
        SELECT agent, COUNT(*) FROM memories WHERE is_current = 1 GROUP BY agent
    """).fetchall()
    
    # Size estimate
    size_bytes = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    
    conn.close()
    
    return {
        "total_memories": total,
        "total_history_entries": total_history,
        "total_shared": total_shared,
        "categories": {c[0]: c[1] for c in categories},
        "agents": {a[0]: a[1] for a in agents},
        "db_size_bytes": size_bytes,
        "db_size_mb": round(size_bytes / 1024 / 1024, 2)
    }

def export_memories(agent: str = None, format: str = "json") -> str:
    """Export memories for backup or sharing."""
    conn = get_conn()
    
    if agent:
        rows = conn.execute(
            "SELECT key, content, compressed, category, importance, agent, version, timestamp FROM memories WHERE is_current = 1 AND (agent = ? OR agent = 'shared')",
            (agent,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT key, content, compressed, category, importance, agent, version, timestamp FROM memories WHERE is_current = 1"
        ).fetchall()
    
    conn.close()
    
    memories = []
    for row in rows:
        content = row[1]
        if row[2]:
            content = decompress_content(content.encode())
        memories.append({
            "key": row[0], "content": content, "category": row[3],
            "importance": row[4], "agent": row[5], "version": row[6],
            "timestamp": row[7]
        })
    
    if format == "json":
        return json.dumps(memories, indent=2)
    elif format == "markdown":
        lines = ["# Agent Memory Export\n"]
        for m in memories:
            lines.append(f"## {m['key']} (v{m['version']})")
            lines.append(f"**Category:** {m['category']} | **Importance:** {m['importance']} | **Agent:** {m['agent']}")
            lines.append(f"**Updated:** {m['timestamp']}\n")
            lines.append(m['content'])
            lines.append("\n---\n")
        return "\n".join(lines)
    
    return json.dumps(memories)

# ── CLI Interface ──────────────────────────────────────────────────────────

def cmd_init(args):
    """Initialize database."""
    init_db()
    print(f"✅ Memory forge initialized at {DB_PATH}")

def cmd_store(args):
    """Store a memory."""
    content = args.content
    if args.file:
        content = Path(args.file).read_text()
    
    result = store_memory(
        args.key, content,
        category=args.category or "general",
        importance=args.importance or 0.5,
        agent=args.agent or "shared"
    )
    print(f"✅ {result['status']}: {result['key']} (v{result['version']})")

def cmd_get(args):
    """Get a memory."""
    result = get_memory(args.key, args.version)
    if result:
        print(f"\n📝 {result['key']} (v{result.get('version', '?')})")
        print(f"   Category: {result.get('category', '?')} | Importance: {result.get('importance', '?')} | Agent: {result.get('agent', '?')}")
        print(f"   Updated: {result.get('timestamp', '?')}\n")
        print(result['content'])
    else:
        print(f"❌ Memory not found: {args.key}")

def cmd_search(args):
    """Search memories."""
    results = search_memories(
        query=args.query, category=args.category,
        agent=args.agent, min_importance=args.min_importance or 0,
        limit=args.limit or 20
    )
    
    if not results:
        print("No memories found.")
        return
    
    print(f"\n🔍 Found {len(results)} memories:\n")
    for r in results:
        print(f"  📝 {r['key']} (v{r['version']}) [{r['category']}] importance={r['importance']}")
        print(f"     {r['content'][:100]}...")
        print()

def cmd_history(args):
    """Show version history."""
    history = get_history(args.key)
    if not history:
        print(f"No history found for {args.key}")
        return
    
    print(f"\n📜 History for {args.key}:\n")
    for h in history:
        print(f"  v{h['version']} — {h['timestamp'][:16]} ({h['change_type']})")
        if h['diff']:
            for line in h['diff'].split('\n')[:5]:
                print(f"    {line}")
            print()

def cmd_rollback(args):
    """Rollback to a previous version."""
    result = rollback(args.key, args.version)
    if result['status'] == 'rolled_back':
        print(f"✅ Rolled back {result['key']} to v{result['to_version']}")
    else:
        print(f"❌ {result['message']}")

def cmd_share(args):
    """Share memory between agents."""
    result = share_memory(args.key, args.from_agent, args.to_agent)
    print(f"✅ {result['status']}: {result['key']} from {result.get('from', '?')} to {result.get('to', '?')}")

def cmd_stats(args):
    """Show statistics."""
    stats = get_stats()
    print(f"\n📊 Memory Forge Statistics\n")
    print(f"Total Memories:     {stats['total_memories']}")
    print(f"History Entries:    {stats['total_history_entries']}")
    print(f"Shared Memories:    {stats['total_shared']}")
    print(f"Database Size:      {stats['db_size_mb']} MB")
    print(f"\nCategories:")
    for cat, count in stats['categories'].items():
        print(f"  {cat}: {count}")
    print(f"\nAgents:")
    for agent, count in stats['agents'].items():
        print(f"  {agent}: {count}")
    print()

def cmd_export(args):
    """Export memories."""
    output = export_memories(agent=args.agent, format=args.format or "json")
    if args.output:
        Path(args.output).write_text(output)
        print(f"✅ Exported to {args.output}")
    else:
        print(output)

def cmd_import(args):
    """Import memories from JSON file."""
    data = json.loads(Path(args.file).read_text())
    conn = get_conn()
    count = 0
    for item in data:
        result = store_memory(
            item["key"], item["content"],
            category=item.get("category", "general"),
            importance=item.get("importance", 0.5),
            agent=item.get("agent", "shared")
        )
        count += 1
    conn.close()
    print(f"✅ Imported {count} memories")

def cmd_prune(args):
    """Prune old/unimportant memories."""
    conn = get_conn()
    cutoff = (datetime.now() - timedelta(days=args.days or 30)).strftime("%Y-%m-%d")
    
    # Mark low-importance old memories as not current
    rows = conn.execute("""
        UPDATE memories SET is_current = 0
        WHERE is_current = 1 AND importance < ? AND timestamp < ?
    """, (args.min_importance or 0.3, cutoff))
    
    pruned = rows.rowcount
    conn.commit()
    conn.close()
    
    print(f"✅ Pruned {pruned} old/low-importance memories")

# ── Entry Point ────────────────────────────────────────────────────────────

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="agent-memory-forge — Git-like versioning for AI agent memory",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command")
    
    subparsers.add_parser("init", help="Initialize database")
    
    store_parser = subparsers.add_parser("store", help="Store a memory")
    store_parser.add_argument("key", help="Memory key")
    store_parser.add_argument("content", nargs="?", help="Content (or use --file)")
    store_parser.add_argument("--file", help="Read content from file")
    store_parser.add_argument("--category", default="general")
    store_parser.add_argument("--importance", type=float, default=0.5)
    store_parser.add_argument("--agent", default="shared")
    
    get_parser = subparsers.add_parser("get", help="Get a memory")
    get_parser.add_argument("key", help="Memory key")
    get_parser.add_argument("--version", type=int, help="Specific version")
    
    search_parser = subparsers.add_parser("search", help="Search memories")
    search_parser.add_argument("--query", help="Search query")
    search_parser.add_argument("--category", help="Filter by category")
    search_parser.add_argument("--agent", help="Filter by agent")
    search_parser.add_argument("--min-importance", type=float, default=0)
    search_parser.add_argument("--limit", type=int, default=20)
    
    history_parser = subparsers.add_parser("history", help="Show version history")
    history_parser.add_argument("key", help="Memory key")
    
    rollback_parser = subparsers.add_parser("rollback", help="Rollback to version")
    rollback_parser.add_argument("key", help="Memory key")
    rollback_parser.add_argument("version", type=int, help="Target version")
    
    share_parser = subparsers.add_parser("share", help="Share memory between agents")
    share_parser.add_argument("key", help="Memory key")
    share_parser.add_argument("--from", dest="from_agent", help="Source agent")
    share_parser.add_argument("--to", dest="to_agent", help="Target agent")
    
    subparsers.add_parser("stats", help="Show statistics")
    
    export_parser = subparsers.add_parser("export", help="Export memories")
    export_parser.add_argument("--agent", help="Filter by agent")
    export_parser.add_argument("--format", choices=["json", "markdown"], default="json")
    export_parser.add_argument("--output", help="Output file")
    
    import_parser = subparsers.add_parser("import", help="Import memories")
    import_parser.add_argument("file", help="JSON file to import")
    
    prune_parser = subparsers.add_parser("prune", help="Prune old memories")
    prune_parser.add_argument("--days", type=int, default=30)
    prune_parser.add_argument("--min-importance", type=float, default=0.3)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    commands = {
        "init": cmd_init, "store": cmd_store, "get": cmd_get,
        "search": cmd_search, "history": cmd_history, "rollback": cmd_rollback,
        "share": cmd_share, "stats": cmd_stats, "export": cmd_export,
        "import": cmd_import, "prune": cmd_prune,
    }
    
    commands[args.command](args)

if __name__ == "__main__":
    main()
