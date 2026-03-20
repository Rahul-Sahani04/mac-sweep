from pathlib import Path

from ..config import HOME
from ..utils import HAS_RICH, console, Table, Panel, box, emit_json, get_dir_size, human_size, print_banner


def get_installed_app_names() -> set:
    names = set()
    for folder in [Path("/Applications"), HOME / "Applications"]:
        if folder.exists():
            for item in folder.iterdir():
                if item.suffix == ".app":
                    stem = item.stem.lower()
                    names.add(stem)
                    names.add(stem.replace(" ", ""))
                    names.add(stem.replace(" ", "-"))
    return names


def cmd_leftovers(args):
    if not args.json:
        print_banner()

    app_support = HOME / "Library/Application Support"
    if not app_support.exists():
        if HAS_RICH:
            console.print("[green]Application Support folder not found.[/green]")
        return

    installed = get_installed_app_names()

    skip_fragments = {
        "apple",
        "mobilesync",
        "syncservices",
        "addressbook",
        "callhistory",
        "coresimulator",
        "crashreporter",
        "dock",
        "spotlight",
        "swiftpm",
        "webkit",
        "siri",
        "helpviewer",
        "instruments",
        "dtrace",
        "mdworker",
    }

    if HAS_RICH:
        console.print("[bold cyan]Scanning Application Support for orphaned app data...[/bold cyan]\n")

    orphans = []
    for item in sorted(app_support.iterdir()):
        name_lower = item.name.lower()
        if name_lower.startswith("."):
            continue
        if any(s in name_lower for s in skip_fragments):
            continue
        matched = any(app in name_lower or name_lower in app for app in installed)
        if not matched:
            sz = get_dir_size(item)
            if sz > 1024 * 1024:
                orphans.append((item, sz))

    orphans.sort(key=lambda x: x[1], reverse=True)

    if args.json:
        total = sum(sz for _, sz in orphans)
        emit_json(
            {
                "command": "leftovers",
                "count": len(orphans),
                "total_bytes": total,
                "total_human": human_size(total),
                "results": [
                    {
                        "folder": item.name,
                        "path": str(item),
                        "size_bytes": sz,
                        "size_human": human_size(sz),
                    }
                    for item, sz in orphans
                ],
            }
        )
        return

    if not orphans:
        if HAS_RICH:
            console.print("[green]✓ No obvious app leftovers found.[/green]")
        return

    if HAS_RICH:
        table = Table(box=box.SIMPLE_HEAD, header_style="bold bright_white", border_style="dim", min_width=70)
        table.add_column("Folder", style="bold white", width=36)
        table.add_column("Size", justify="right", width=12)
        table.add_column("Path", style="dim")

        for item, sz in orphans:
            size_str = human_size(sz)
            if sz > 500_000_000:
                size_str = f"[bold red]{size_str}[/bold red]"
            elif sz > 100_000_000:
                size_str = f"[bold yellow]{size_str}[/bold yellow]"
            else:
                size_str = f"[green]{size_str}[/green]"
            table.add_row(item.name, size_str, str(item))

        console.print(table)
        total = sum(sz for _, sz in orphans)
        console.print()
        console.print(
            Panel(
                f"[dim]Found [bold white]{len(orphans)}[/bold white] possible leftovers · "
                f"[bold white]{human_size(total)}[/bold white] total\n"
                f"Review carefully before deleting - some may be from active apps.[/dim]",
                border_style="yellow",
                expand=False,
            )
        )
    else:
        for item, sz in orphans:
            print(f"  {human_size(sz):>10}  {item}")
