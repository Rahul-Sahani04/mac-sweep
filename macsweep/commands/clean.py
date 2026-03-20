import sys
import json
from datetime import datetime

from ..config import (
    HOME,
    SCAN_TARGETS,
    CATEGORY_COLORS,
    CATEGORY_ICONS,
    RISK_RANK,
    RISK_COLORS,
)
from ..utils import (
    HAS_RICH,
    console,
    Table,
    Panel,
    Confirm,
    box,
    emit_json,
    risk_for_target,
    human_size,
    safe_delete,
    build_scan_results,
    preview_items,
    print_banner,
)


def cmd_clean(args):
    if not args.json:
        print_banner()

    selected = [t for t in SCAN_TARGETS if not args.category or t["category"] in args.category]
    if args.safe_only:
        selected = [t for t in selected if t["safe"]]
    else:
        selected = [
            t for t in selected
            if RISK_RANK[risk_for_target(t)] <= RISK_RANK[args.risk_level]
        ]

    if HAS_RICH and not args.json:
        console.print("[bold cyan]Scanning for junk...[/bold cyan]\n")

    exclude_patterns = args.exclude or []
    raw_results = build_scan_results(
        selected,
        exclude_patterns=exclude_patterns,
        min_age_days=args.age_days,
        progress_label="Preparing clean plan...",
    )
    results = [r for r in raw_results if r["exists"] and r["size"] > 0]
    results.sort(key=lambda r: r["size"], reverse=True)

    if not results:
        if args.json:
            emit_json({
                "command": "clean",
                "summary": {
                    "deleted_locations": 0,
                    "deleted_bytes": 0,
                    "deleted_human": human_size(0),
                },
                "message": "Nothing to clean",
            })
            return
        if HAS_RICH:
            console.print("[green]✓ Nothing to clean - your Mac is already tidy![/green]")
        else:
            print("Nothing to clean!")
        return

    cleanup_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    manifests_dir = HOME / ".mac_sweep" / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifests_dir / f"cleanup-{cleanup_id}.json"
    trash_dir = HOME / ".Trash" / "mac-sweep" / cleanup_id

    before_by_category = {}
    by_risk = {"safe": 0, "review": 0, "danger": 0}
    for r in results:
        before_by_category.setdefault(r["category"], 0)
        before_by_category[r["category"]] += r["size"]
        by_risk[r["risk"]] += r["size"]

    estimated_total = sum(r["size"] for r in results)
    if HAS_RICH and not args.json:
        console.print(Panel(
            f"[bold white]Estimated reclaim potential: [bold cyan]{human_size(estimated_total)}[/bold cyan]\n"
            f"[green]safe: {human_size(by_risk['safe'])}[/green]  ·  "
            f"[yellow]review: {human_size(by_risk['review'])}[/yellow]  ·  "
            f"[red]danger: {human_size(by_risk['danger'])}[/red][/bold white]",
            border_style="cyan",
            expand=False,
        ))

    deleted_size = 0
    deleted_count = 0
    skipped_count = 0
    failed_count = 0
    manifest_items = []

    for r in results:
        size_str = human_size(r["size"])
        cat_color = CATEGORY_COLORS.get(r["category"], "white")
        icon = CATEGORY_ICONS.get(r["category"], "  ")
        risk_color = RISK_COLORS.get(r["risk"], "white")

        if HAS_RICH and not args.json:
            console.print(
                f"\n[bold white]{r['label']}[/bold white]  "
                f"[{cat_color}]{icon} {r['category']}[/{cat_color}]  "
                f"[dim]{r['path']}[/dim]"
            )
            console.print(f"  [dim]{r['description']}[/dim]")
            console.print(
                f"  Size: [bold yellow]{size_str}[/bold yellow]  "
                f"Safe: {'[green]Yes[/green]' if r['safe'] else '[red]Caution[/red]'}  "
                f"Risk: [{risk_color}]{r['risk']}[/{risk_color}]"
            )
            console.print(f"  [dim]Why: {r['safe_reason']}[/dim]")

        if args.preview_suspicious and not args.yes and r["risk"] in {"review", "danger"} and HAS_RICH and not args.json:
            if Confirm.ask("  Preview largest items before deciding?", default=True):
                preview = preview_items(
                    r["path"],
                    limit=args.preview_limit,
                    exclude_patterns=exclude_patterns,
                    min_age_days=args.age_days,
                )
                if preview:
                    p_table = Table(box=box.SIMPLE, header_style="bold white", border_style="dim")
                    p_table.add_column("Size", justify="right", width=10)
                    p_table.add_column("Item", style="dim")
                    for item, sz in preview:
                        p_table.add_row(human_size(sz), str(item))
                    console.print(p_table)
                else:
                    console.print("  [dim]No previewable items found.[/dim]")

        interactive_mode = (not args.json) and sys.stdin.isatty()
        should_delete = args.yes or (interactive_mode and HAS_RICH and Confirm.ask(f"  Delete [bold]{r['label']}[/bold]?"))
        if should_delete:
            ok, msg, destination = safe_delete(
                r["path"],
                dry_run=args.dry_run,
                delete_mode=args.delete_mode,
                trash_dir=trash_dir,
            )
            if ok:
                deleted_size += r["size"]
                deleted_count += 1
                label = "[dim](dry run)[/dim]" if args.dry_run else "[green]✓ Deleted[/green]"
                if HAS_RICH and not args.json:
                    console.print(f"  {label}")
                else:
                    print(f"  {'(dry run)' if args.dry_run else 'Deleted'}: {r['label']}")
            else:
                failed_count += 1
                if HAS_RICH and not args.json:
                    console.print(f"  [red]✗ Failed: {msg}[/red]")
                else:
                    print(f"  Failed: {msg}")
            manifest_items.append({
                "label": r["label"],
                "source_path": str(r["path"]),
                "trash_path": destination,
                "size_bytes": r["size"],
                "risk": r["risk"],
                "status": "success" if ok else "failed",
                "message": msg,
            })
        else:
            skipped_count += 1
            manifest_items.append({
                "label": r["label"],
                "source_path": str(r["path"]),
                "trash_path": None,
                "size_bytes": r["size"],
                "risk": r["risk"],
                "status": "skipped",
                "message": "user skipped",
            })

    category_targets = [t for t in SCAN_TARGETS if t["category"] in before_by_category]
    after_results = build_scan_results(
        category_targets,
        exclude_patterns=exclude_patterns,
        min_age_days=args.age_days,
        progress_label="Measuring post-clean snapshot...",
    )
    after_by_category = {}
    for r in after_results:
        if r["exists"]:
            after_by_category.setdefault(r["category"], 0)
            after_by_category[r["category"]] += r["size"]

    snapshot = []
    for category, before_bytes in sorted(before_by_category.items()):
        after_bytes = after_by_category.get(category, 0)
        snapshot.append({
            "category": category,
            "before_bytes": before_bytes,
            "after_bytes": after_bytes,
            "reclaimed_bytes": max(before_bytes - after_bytes, 0),
        })

    manifest_payload = {
        "cleanup_id": cleanup_id,
        "created_at": datetime.now().isoformat(),
        "delete_mode": args.delete_mode,
        "dry_run": args.dry_run,
        "filters": {
            "category": args.category,
            "safe_only": args.safe_only,
            "risk_level": args.risk_level,
            "age_days": args.age_days,
            "exclude": exclude_patterns,
        },
        "summary": {
            "deleted_locations": deleted_count,
            "skipped_locations": skipped_count,
            "failed_locations": failed_count,
            "deleted_bytes": deleted_size,
        },
        "items": manifest_items,
        "snapshot": snapshot,
    }
    manifest_path.write_text(json.dumps(manifest_payload, indent=2))

    if args.json:
        emit_json({
            "command": "clean",
            "manifest": str(manifest_path),
            "summary": {
                "deleted_locations": deleted_count,
                "skipped_locations": skipped_count,
                "failed_locations": failed_count,
                "deleted_bytes": deleted_size,
                "deleted_human": human_size(deleted_size),
            },
            "snapshot": [
                {
                    **row,
                    "before_human": human_size(row["before_bytes"]),
                    "after_human": human_size(row["after_bytes"]),
                    "reclaimed_human": human_size(row["reclaimed_bytes"]),
                }
                for row in snapshot
            ],
        })
        return

    if HAS_RICH:
        action = "Would free" if args.dry_run else "Freed"
        console.print()
        console.print(Panel(
            f"[bold white]{action} [bold cyan]{human_size(deleted_size)}[/bold cyan] "
            f"across [bold cyan]{deleted_count}[/bold cyan] location(s)  ·  "
            f"skipped [bold]{skipped_count}[/bold]  ·  failed [bold]{failed_count}[/bold][/bold white]",
            border_style="green" if deleted_count else "dim",
            expand=False,
        ))

        snap_table = Table(box=box.SIMPLE_HEAD, header_style="bold white", border_style="dim")
        snap_table.add_column("Category", style="bold")
        snap_table.add_column("Before", justify="right")
        snap_table.add_column("After", justify="right")
        snap_table.add_column("Reclaimed", justify="right")
        for row in snapshot:
            snap_table.add_row(
                row["category"],
                human_size(row["before_bytes"]),
                human_size(row["after_bytes"]),
                f"[green]{human_size(row['reclaimed_bytes'])}[/green]",
            )
        console.print()
        console.print("[bold cyan]Category Snapshot (Before vs After)[/bold cyan]")
        console.print(snap_table)
        console.print(f"\n[dim]Rollback manifest: {manifest_path}[/dim]")
    else:
        print(f"\nCleaned {deleted_count} locations, freed {human_size(deleted_size)}")
