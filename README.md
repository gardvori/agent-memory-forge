# 🧠 agent-memory-forge

Git-like versioning for AI agent memory. Unified memory system with compression and cross-agent sharing.

## Features

- **Version Control** — Every memory change is tracked with diffs, like git
- **Compression** — Large memories auto-compressed with zlib
- **Cross-Agent Sharing** — Share memories between agents (Meridian ↔ Hermes ↔ Armodeus)
- **Rollback** — Revert any memory to a previous version
- **Search** — Full-text search with filters (category, agent, importance)
- **Export/Import** — JSON or Markdown export for backup
- **Pruning** — Auto-clean old/low-importance memories
- **Zero Dependencies** — Pure Python stdlib + SQLite

## Installation

```bash
git clone https://github.com/gardvori/agent-memory-forge.git
cd agent-memory-forge
python3 agent_memory_forge.py init
```

## Usage

```bash
# Initialize
python3 agent_memory_forge.py init

# Store a memory
python3 agent_memory_forge.py store "user_preference" "User prefers concise responses" --category preference --importance 0.9

# Get a memory
python3 agent_memory_forge.py get "user_preference"

# Search memories
python3 agent_memory_forge.py search --query "trading" --category strategy

# Version history
python3 agent_memory_forge.py history "user_preference"

# Rollback
python3 agent_memory_forge.py rollback "user_preference" 2

# Share between agents
python3 agent_memory_forge.py share "trading_lesson" --from meridian --to hermes

# Statistics
python3 agent_memory_forge.py stats

# Export
python3 agent_memory_forge.py export --format markdown --output memories.md

# Import
python3 agent_memory_forge.py import memories.json

# Prune old memories
python3 agent_memory_forge.py prune --days 30 --min-importance 0.3
```

## License

MIT
