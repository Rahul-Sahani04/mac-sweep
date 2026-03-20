from pathlib import Path
from datetime import datetime

from ..config import SCAN_TARGETS, CATEGORY_COLORS, CATEGORY_ICONS, RISK_COLORS
from ..utils import (
    HAS_RICH,
    console,
    Table,
    Panel,
    box,
    emit_json,
    human_size,
    build_scan_results,
    print_banner,
)


def cmd_scan(args):
    if not args.json:
        print_banner()

    if args.path:
        custom_path = Path(args.path).expanduser()
        selected = [{
            "label": "Custom Path",
            "path": custom_path,
            "description": f"Custom scan target: {custom_path}",
            "safe": False,
            "category": "user",
        }]
    else:
        selected = [t for t in SCAN_TARGETS if not args.category or t["category"] in args.category]

    exclude_patterns = args.exclude or []
    results = build_scan_results(
        selected,
        exclude_patterns=exclude_patterns,
        min_age_days=args.age_days,
        progress_label="Scanning...",
    )

    found = [r for r in results if r["exists"]]
    found.sort(key=lambda r: r["size"], reverse=True)

    if args.top:
        found = found[: args.top]

    total = sum(r["size"] for r in found)

    if args.json:
        emit_json({
            "command": "scan",
            "generated_at": datetime.now().isoformat(),
            "filters": {
                "category": args.category,
                "top": args.top,
                "age_days": args.age_days,
                "exclude": exclude_patterns,
            },
            "summary": {
                "locations": len(found),
                "total_bytes": total,
                "total_human": human_size(total),
            },
            "results": [
                {
                    "label": r["label"],
                    "category": r["category"],
                    "path": str(r["path"]),
                    "size_bytes": r["size"],
                    "size_human": human_size(r["size"]),
                    "safe": r["safe"],
                    "risk": r["risk"],
                    "safe_reason": r["safe_reason"],
                }
                for r in found
            ],
        })
        return

    if HAS_RICH:
        table = Table(
            box=box.SIMPLE_HEAD,
            show_header=True,
            header_style="bold bright_white",
            border_style="dim",
            pad_edge=False,
            min_width=80,
        )
        table.add_column("Category", style="dim", width=10)
        table.add_column("Name", style="bold white", width=24)
        table.add_column("Description", style="dim", width=36)
        table.add_column("Size", justify="right", width=10)
        table.add_column("Risk", justify="center", width=8)
        table.add_column("Safe?", justify="center", width=6)
        table.add_column("Why", style="dim", width=32)

        for r in found:
            cat = r["category"]
            color = CATEGORY_COLORS.get(cat, "white")
            icon = CATEGORY_ICONS.get(cat, "  ")
            safe_badge = "[green]✓[/green]" if r["safe"] else "[red]![/red]"
            risk_color = RISK_COLORS.get(r["risk"], "white")
            size_str = human_size(r["size"])
            if r["size"] > 500_000_000:
                size_str = f"[bold red]{size_str}[/bold red]"
            elif r["size"] > 100_000_000:
                size_str = f"[bold yellow]{size_str}[/bold yellow]"
            else:
                size_str = f"[green]{size_str}[/green]"

            table.add_row(
                f"[{color}]{icon} {cat}[/{color}]",
                r["label"],
                r["description"],
                size_str,
                f"[{risk_color}]{r['risk']}[/{risk_color}]",
                safe_badge,
                r["safe_reason"],
            )

        console.print(table)
        console.print()
        filter_note = []
        if args.age_days is not None:
            filter_note.append(f"only files older than {args.age_days} day(s)")
        if exclude_patterns:
            filter_note.append(f"excluding {len(exclude_patterns)} pattern(s)")
        if args.top:
            filter_note.append(f"showing top {args.top}")

        console.print(Panel(
            f"[bold white]Found [bold cyan]{len(found)}[/bold cyan] locations  ·  "
            f"Potential savings: [bold {'red' if total > 1e9 else 'yellow'}]{human_size(total)}[/bold {'red' if total > 1e9 else 'yellow'}]\n"
            f"[dim]{' · '.join(filter_note) if filter_note else 'No extra filters applied.'}\n"
            f"Run [bold]mac-sweep clean[/bold] to interactively delete, or [bold]mac-sweep clean --safe-only[/bold] for auto-clean[/dim]",
            border_style="cyan",
            expand=False,
        ))
    else:
        print(f"\nTotal potential savings: {human_size(total)}")
        print("Run: mac-sweep clean")
