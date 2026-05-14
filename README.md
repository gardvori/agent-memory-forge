# 🧠 Agent Memory Forge

> **Unified agent memory system with git-like versioning, compression, and cross-agent sharing.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

**Think Git + SQLite + semantic search for AI agent memory.**

Every AI agent framework has its own memory format — MemGPT, Mem0, agentmemory, memoir — and none of them talk to each other. Agent Memory Forge is the **universal memory layer** that gives your agents persistent, versioned, searchable memory with a simple CLI.

## Why Agent Memory Forge?

| Problem | Solution |
|---------|----------|
| Agent memory is fragmented across frameworks | Unified SQLite-backed store with import/export |
| No version history for agent memories | Git-like versioning with rollback |
| Memory bloat from redundant data | Built-in zlib compression |
| Can't share memories between agents | Cross-agent memory sharing with provenance tags |
| No visibility into what agents remember | Rich CLI with stats, search, and export |

## Quick Start

```bash
pip install agent-memory-forge

# Store a memory
amf remember "User prefers dark mode" -t preference -t ui -i 0.8

# Search memories
amf recall "dark mode"

# Check stats
amf stats

# View version history
amf versions <memory-id>

# Share with another agent
amf share <memory-id> other-agent
```

## Installation

```bash
pip install agent-memory-forge
```

Or install from source:

```bash
git clone https://github.com/gardvori/agent-memory-forge.git
cd agent-memory-forge
pip install -e .
```

## CLI Reference

### `amf remember` — Store a memory

```bash
amf remember "content" [options]

Options:
  -t, --tag TEXT          Tags (repeatable)
  -i, --importance FLOAT  Importance 0.0-1.0 (default: 0.5)
  -m, --metadata TEXT     JSON metadata
  --message TEXT          Commit message
```

```bash
amf remember "API rate limit: 1000 req/min" -t api -t limits -i 0.9 \
  --message "Added rate limit info"
```

### `amf recall` — Search memories

```bash
amf recall [query] [options]

Options:
  -t, --tag TEXT     Filter by tags (repeatable)
  -n, --limit INT    Max results (default: 10)
  --all              Include deleted memories
```

```bash
amf recall "rate limit" -t api -n 5
amf recall --tag preference --tag ui
```

### `amf update` — Update a memory (creates new version)

```bash
amf update <memory-id> [options]

Options:
  -c, --content TEXT      New content
  -t, --tag TEXT          Replace tags
  -i, --importance FLOAT  New importance
  --message TEXT          Commit message
```

### `amf versions` — View version history

```bash
amf versions <memory-id>
```

### `amf rollback` — Rollback to a version

```bash
amf rollback <memory-id> <version>
```

### `amf forget` — Delete a memory

```bash
amf forget <memory-id>        # Soft delete
amf forget <memory-id> --hard # Permanent
```

### `amf share` — Share with another agent

```bash
amf share <memory-id> <target-agent> [-t tag]
```

### `amf stats` — Agent statistics

```bash
amf stats
amf --agent mybot stats
```

### `amf export` / `amf import` — Backup and restore

```bash
amf export -f json -o backup.json
amf export -f markdown -o memories.md
amf import backup.json
```

### `amf status` — Quick overview

```bash
amf status
```

## Global Options

| Option | Description |
|--------|-------------|
| `--agent AGENT_ID` | Agent ID (default: "default") |
| `--db PATH` | Database path (default: ~/.agent-memory-forge/memory.db) |
| `--json-output` | Machine-readable JSON output |

## Python API

```python
from agent_memory_forge.store import MemoryStore

store = MemoryStore("~/.agent-memory-forge/memory.db")

# Remember
mem_id = store.remember(
    agent_id="my-agent",
    content="User prefers Python over JavaScript",
    tags=["preference", "language"],
    importance=0.8,
)

# Recall
memories = store.recall(agent_id="my-agent", query="python")

# Update (creates new version)
store.update_memory(mem_id, content="User prefers Python 3.12", commit_message="Updated version")

# Version history
versions = store.get_versions(mem_id)

# Rollback
store.rollback(mem_id, version=1)

# Share across agents
new_id = store.share_memory(mem_id, target_agent_id="other-agent")

# Stats
stats = store.get_stats("my-agent")

# Export
json_data = store.export_memories("my-agent", format="json")

store.close()
```

## Architecture

```
┌─────────────────────────────────────────┐
│           CLI (Click + Rich)            │
├─────────────────────────────────────────┤
│           MemoryStore (Python)          │
│  ┌──────────┬──────────┬─────────────┐  │
│  │ Remember │  Recall  │   Version   │  │
│  │  Update  │  Search  │  Rollback   │  │
│  │  Forget  │  Stats   │   Share     │  │
│  └──────────┴──────────┴─────────────┘  │
├─────────────────────────────────────────┤
│         SQLite + zlib compression       │
│  ┌─────────────┬──────────────────────┐ │
│  │  memories    │  memory_versions     │ │
│  │  branches    │  (git-like history)  │ │
│  └─────────────┴──────────────────────┘ │
└─────────────────────────────────────────┘
```

## Comparison with Existing Solutions

| Feature | Agent Memory Forge | agentmemory | memoir | MemGPT | Mem0 |
|---------|-------------------|-------------|--------|--------|------|
| Git-like versioning | ✅ | ❌ | ✅ | ❌ | ❌ |
| Cross-agent sharing | ✅ | ❌ | ❌ | ❌ | ❌ |
| Compression | ✅ | ❌ | ❌ | ❌ | ❌ |
| CLI tool | ✅ | ❌ | ❌ | ❌ | ✅ |
| SQLite backend | ✅ | ✅ | ❌ | ✅ | ❌ |
| Import/Export | ✅ | ❌ | ❌ | ❌ | ❌ |
| Rollback | ✅ | ❌ | ✅ | ❌ | ❌ |
| Self-hosted | ✅ | ✅ | ✅ | ✅ | ❌ |

## Roadmap

- [ ] Semantic search with vector embeddings (sentence-transformers)
- [ ] Memory auto-compression for old/low-importance entries
- [ ] Web dashboard for visual memory exploration
- [ ] REST API server mode
- [ ] Memory graph visualization
- [ ] Integration with LangChain / LlamaIndex
- [ ] Multi-agent memory conflict resolution

## Contributing

Contributions welcome! See [issues](https://github.com/gardvori/agent-memory-forge/issues) for open tasks.

```bash
git clone https://github.com/gardvori/agent-memory-forge.git
cd agent-memory-forge
pip install -e ".[dev]"
pytest
```

## License

[MIT](LICENSE) — use it freely, build amazing agents.
