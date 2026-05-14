"""
CLI interface for Agent Memory Forge.
"""
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich import print as rprint

from agent_memory_forge.store import MemoryStore
from agent_memory_forge import __version__

console = Console()


def get_store(ctx) -> MemoryStore:
    db_path = ctx.obj.get("db_path", "~/.agent-memory-forge/memory.db")
    return MemoryStore(db_path)


@click.group()
@click.version_option(version=__version__, prog_name="agent-memory-forge")
@click.option("--db", "db_path", default="~/.agent-memory-forge/memory.db",
              help="Path to SQLite database", show_default=True)
@click.option("--agent", "agent_id", default="default",
              help="Agent ID to operate on", show_default=True)
@click.option("--json-output", "json_output", is_flag=True, default=False,
              help="Output as JSON (for scripting)")
@click.pass_context
def cli(ctx, db_path, agent_id, json_output):
    """🧠 Agent Memory Forge — Unified agent memory with git-like versioning.

    Store, recall, version, and share memories across AI agents.
    Think Git + SQLite + semantic search for agent memory.
    """
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = db_path
    ctx.obj["agent_id"] = agent_id
    ctx.obj["json_output"] = json_output


@cli.command()
@click.argument("content")
@click.option("--tag", "-t", multiple=True, help="Tags for this memory")
@click.option("--importance", "-i", default=0.5, type=float,
              help="Importance score 0.0-1.0", show_default=True)
@click.option("--metadata", "-m", default="{}",
              help="JSON metadata string")
@click.option("--message", "commit_message", default="",
              help="Commit message (like git commit -m)")
@click.pass_context
def remember(ctx, content, tag, importance, metadata, commit_message):
    """Store a new memory.

    \b
    Examples:
        amf remember "User prefers dark mode" -t preference -t ui -i 0.8
        amf remember "API key: sk-xxx" -t secrets --importance 1.0
        amf remember "Meeting notes from standup" -t work -m '{"project": "alpha"}'
    """
    store = get_store(ctx)
    agent_id = ctx.obj["agent_id"]

    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError:
        console.print("[red]Error: --metadata must be valid JSON[/red]")
        sys.exit(1)

    mem_id = store.remember(
        agent_id=agent_id,
        content=content,
        tags=list(tag),
        metadata=meta,
        importance=importance,
        commit_message=commit_message,
    )
    store.close()

    if ctx.obj["json_output"]:
        click.echo(json.dumps({"id": mem_id, "status": "stored"}))
    else:
        console.print(f"[green]✓[/green] Memory stored: [bold]{mem_id}[/bold]")
        if tag:
            console.print(f"  Tags: {', '.join(tag)}")
        console.print(f"  Importance: {importance}")


@cli.command()
@click.argument("query", required=False)
@click.option("--tag", "-t", "tags", multiple=True, help="Filter by tags")
@click.option("--limit", "-n", default=10, type=int, help="Max results", show_default=True)
@click.option("--all", "include_deleted", is_flag=True, help="Include deleted memories")
@click.pass_context
def recall(ctx, query, tags, limit, include_deleted):
    """Search and recall memories.

    \b
    Examples:
        amf recall "dark mode"
        amf recall --tag preference --tag ui
        amf recall --limit 50
    """
    store = get_store(ctx)
    agent_id = ctx.obj["agent_id"]

    results = store.recall(
        agent_id=agent_id,
        query=query,
        tags=list(tags) if tags else None,
        limit=limit,
        include_deleted=include_deleted,
    )
    store.close()

    if ctx.obj["json_output"]:
        click.echo(json.dumps(results, indent=2, default=str))
    else:
        if not results:
            console.print("[yellow]No memories found.[/yellow]")
            return

        table = Table(title=f"🧠 Memories for agent: {agent_id}", show_lines=True)
        table.add_column("ID", style="cyan", width=18)
        table.add_column("Content", style="white", max_width=60)
        table.add_column("Tags", style="green", max_width=30)
        table.add_column("Imp.", style="yellow", width=6)
        table.add_column("Ver.", style="dim", width=4)
        table.add_column("Created", style="dim", width=20)

        for mem in results:
            status = "🗑️" if mem.get("is_deleted") else ""
            table.add_row(
                f"{status}{mem['id']}",
                mem["content"][:100] + ("..." if len(mem["content"]) > 100 else ""),
                ", ".join(mem["tags"][:5]),
                f"{mem['importance']:.1f}",
                str(mem["version"]),
                mem["created_at"][:19],
            )

        console.print(table)
        console.print(f"\n[dim]Found {len(results)} memories[/dim]")


@cli.command()
@click.argument("memory_id")
@click.option("--content", "-c", default=None, help="New content")
@click.option("--tag", "-t", multiple=True, help="Replace tags")
@click.option("--importance", "-i", default=None, type=float, help="New importance")
@click.option("--message", "commit_message", default="", help="Commit message")
@click.pass_context
def update(ctx, memory_id, content, tag, importance, commit_message):
    """Update an existing memory (creates new version).

    \b
    Examples:
        amf update <id> -c "Updated content" -m "Fixed typo"
        amf update <id> -t new-tag -i 0.9
    """
    store = get_store(ctx)

    success = store.update_memory(
        memory_id=memory_id,
        content=content,
        tags=list(tag) if tag else None,
        importance=importance,
        commit_message=commit_message,
    )
    store.close()

    if success:
        console.print(f"[green]✓[/green] Memory [bold]{memory_id}[/bold] updated")
    else:
        console.print(f"[red]✗[/red] Memory [bold]{memory_id}[/bold] not found")
        sys.exit(1)


@cli.command()
@click.argument("memory_id")
@click.option("--hard", is_flag=True, help="Permanently delete (no undo)")
@click.pass_context
def forget(ctx, memory_id, hard):
    """Delete a memory (soft delete by default).

    \b
    Examples:
        amf forget <id>           # Soft delete (can be recovered)
        amf forget <id> --hard    # Permanent deletion
    """
    store = get_store(ctx)
    success = store.forget(memory_id, hard=hard)
    store.close()

    if success:
        mode = "permanently deleted" if hard else "soft-deleted"
        console.print(f"[yellow]⚠[/yellow] Memory [bold]{memory_id}[/bold] {mode}")
    else:
        console.print(f"[red]✗[/red] Memory [bold]{memory_id}[/bold] not found")
        sys.exit(1)


@cli.command("versions")
@click.argument("memory_id")
@click.pass_context
def list_versions(ctx, memory_id):
    """Show version history for a memory.

    \b
    Examples:
        amf versions <id>
    """
    store = get_store(ctx)
    versions = store.get_versions(memory_id)
    store.close()

    if not versions:
        console.print(f"[yellow]No versions found for {memory_id}[/yellow]")
        return

    table = Table(title=f"📜 Version History: {memory_id}")
    table.add_column("Version", style="cyan", width=8)
    table.add_column("Message", style="white", max_width=50)
    table.add_column("Hash", style="dim", width=12)
    table.add_column("Date", style="dim", width=20)

    for v in versions:
        table.add_row(
            f"v{v['version']}",
            v["commit_message"],
            v["content_hash"][:10],
            v["committed_at"][:19],
        )

    console.print(table)


@cli.command()
@click.argument("memory_id")
@click.argument("version", type=int)
@click.pass_context
def rollback(ctx, memory_id, version):
    """Rollback memory to a specific version.

    \b
    Examples:
        amf rollback <id> 3    # Rollback to version 3
    """
    store = get_store(ctx)
    success = store.rollback(memory_id, version)
    store.close()

    if success:
        console.print(f"[green]✓[/green] Rolled back [bold]{memory_id}[/bold] to v{version}")
    else:
        console.print(f"[red]✗[/red] Could not rollback (memory or version not found)")
        sys.exit(1)


@cli.command()
@click.argument("memory_id")
@click.argument("target_agent")
@click.option("--tag", "-t", multiple=True, help="Additional tags for shared copy")
@click.pass_context
def share(ctx, memory_id, target_agent, tag):
    """Share a memory with another agent.

    \b
    Examples:
        amf share <id> other-agent
        amf share <id> other-agent -t shared -t important
    """
    store = get_store(ctx)
    try:
        new_id = store.share_memory(memory_id, target_agent, list(tag) if tag else None)
        console.print(f"[green]✓[/green] Memory shared with agent [bold]{target_agent}[/bold]")
        console.print(f"  New memory ID: {new_id}")
    except ValueError as e:
        console.print(f"[red]✗[/red] {e}")
        sys.exit(1)
    finally:
        store.close()


@cli.command()
@click.pass_context
def stats(ctx):
    """Show memory statistics for current agent.

    \b
    Examples:
        amf stats
        amf --agent mybot stats
    """
    store = get_store(ctx)
    agent_id = ctx.obj["agent_id"]
    s = store.get_stats(agent_id)
    store.close()

    if ctx.obj["json_output"]:
        click.echo(json.dumps(s, indent=2))
    else:
        console.print(Panel(
            f"[bold]Agent:[/bold] {s['agent_id']}\n"
            f"[bold]Active Memories:[/bold] {s['total_memories']}\n"
            f"[bold]Deleted Memories:[/bold] {s['deleted_memories']}\n"
            f"[bold]Total Versions:[/bold] {s['total_versions']}\n"
            f"[bold]Avg Importance:[/bold] {s['avg_importance']}",
            title="📊 Memory Stats",
            border_style="blue",
        ))

        if s["top_tags"]:
            tag_table = Table(title="Top Tags", show_header=False, box=None)
            tag_table.add_column("Tag", style="green")
            tag_table.add_column("Count", style="yellow")
            for tag, count in s["top_tags"]:
                tag_table.add_row(tag, str(count))
            console.print(tag_table)


@cli.command()
@click.option("--format", "-f", "fmt", default="json",
              type=click.Choice(["json", "markdown"]), help="Export format")
@click.option("--output", "-o", default=None, help="Output file (default: stdout)")
@click.pass_context
def export(ctx, fmt, output):
    """Export all memories for current agent.

    \b
    Examples:
        amf export -f json -o memories.json
        amf export -f markdown -o memories.md
    """
    store = get_store(ctx)
    agent_id = ctx.obj["agent_id"]
    data = store.export_memories(agent_id, format=fmt)
    store.close()

    if output:
        Path(output).write_text(data)
        console.print(f"[green]✓[/green] Exported to {output}")
    else:
        click.echo(data)


@cli.command()
@click.argument("file_path")
@click.option("--format", "-f", "fmt", default="json",
              type=click.Choice(["json"]), help="Import format")
@click.pass_context
def import_(ctx, file_path, fmt):
    """Import memories from a JSON file.

    \b
    Examples:
        amf import memories.json
    """
    store = get_store(ctx)
    agent_id = ctx.obj["agent_id"]
    data = Path(file_path).read_text()
    count = store.import_memories(agent_id, data, format=fmt)
    store.close()

    console.print(f"[green]✓[/green] Imported {count} memories")


@cli.command()
@click.pass_context
def status(ctx):
    """Quick status overview."""
    store = get_store(ctx)
    agent_id = ctx.obj["agent_id"]
    s = store.get_stats(agent_id)

    # Get recent memories
    recent = store.recall(agent_id, limit=5)
    store.close()

    console.print(Panel(
        f"[bold cyan]Agent Memory Forge v{__version__}[/bold cyan]\n"
        f"Agent: [bold]{agent_id}[/bold]  |  "
        f"DB: {ctx.obj['db_path']}\n"
        f"Memories: [bold]{s['total_memories']}[/bold]  |  "
        f"Versions: [bold]{s['total_versions']}[/bold]",
        title="🧠 Status",
        border_style="green",
    ))

    if recent:
        console.print("\n[bold]Recent memories:[/bold]")
        for mem in recent:
            console.print(f"  • [{mem['id'][:8]}] {mem['content'][:60]}...")


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
