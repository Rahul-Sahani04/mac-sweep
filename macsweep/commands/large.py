import os
from pathlib import Path

from ..config import HOME
from ..utils import (
    HAS_RICH,
    console,
    Table,
    Progress,
    SpinnerColumn,
    TextColumn,
    box,
    emit_json,
    human_size,
    print_banner,
)


def cmd_large(args):
    if not args.json:
        print_banner()
    search_path = Path(args.path).expanduser() if args.path else HOME
    min_size = args.min_mb * 1024 * 1024
    limit = args.limit

    if HAS_RICH and not args.json:
        console.print(f"[bold cyan]Searching for files > {args.min_mb} MB in[/bold cyan] [dim]{search_path}[/dim]\n")

    large_files = []

    with (
        Progress(
            SpinnerColumn(spinner_name="dots2", style="cyan"),
            TextColumn("[bold cyan]{task.description}"),
            console=console,
            transient=True,
        )
        if HAS_RICH
        else open(os.devnull)
    ) as progress:
        if HAS_RICH:
            progress.add_task("Scanning...", total=None)

        try:
            for root, dirs, files in os.walk(search_path, followlinks=False):
                dirs[:] = [d for d in dirs if not d.startswith(".") or args.hidden]
                for fname in files:
                    fpath = Path(root) / fname
                    try:
                        size = fpath.stat().st_size
                        if size >= min_size:
                            large_files.append((fpath, size))
                    except (PermissionError, OSError):
                        pass
        except (PermissionError, OSError):
            pass

    large_files.sort(key=lambda x: x[1], reverse=True)
    large_files = large_files[:limit]

    if args.json:
        emit_json(
            {
                "command": "large",
                "path": str(search_path),
                "min_mb": args.min_mb,
                "limit": limit,
                "count": len(large_files),
                "results": [
                    {
                        "path": str(fpath),
                        "size_bytes": size,
                        "size_human": human_size(size),
                    }
                    for fpath, size in large_files
                ],
            }
        )
        return

    if HAS_RICH:
        table = Table(box=box.SIMPLE_HEAD, header_style="bold bright_white", border_style="dim", min_width=80)
        table.add_column("#", style="dim", width=4)
        table.add_column("Size", justify="right", width=10)
        table.add_column("File", style="white")

        for i, (fpath, size) in enumerate(large_files, 1):
            sz = human_size(size)
            if size > 1_000_000_000:
                sz_str = f"[bold red]{sz}[/bold red]"
            elif size > 500_000_000:
                sz_str = f"[bold yellow]{sz}[/bold yellow]"
            else:
                sz_str = f"[green]{sz}[/green]"
            table.add_row(str(i), sz_str, str(fpath))

        console.print(table)
        if not large_files:
            console.print(f"[green]No files larger than {args.min_mb} MB found.[/green]")
    else:
        for i, (fpath, size) in enumerate(large_files, 1):
            print(f"  {i:3}.  {human_size(size):>10}  {fpath}")
