#!/usr/bin/env python3
"""
mac_sweep — a beautiful CLI tool to find junk, cache, and cruft on macOS
"""

import os
import sys
import shutil
import subprocess
import argparse
import json
from pathlib import Path
from datetime import datetime

from mac_sweep_config import (
    HOME,
    SCAN_TARGETS,
    CATEGORY_COLORS,
    CATEGORY_ICONS,
    RISK_RANK,
    RISK_COLORS,
)
from mac_sweep_utils import (
    HAS_RICH,
    console,
    Table,
    Panel,
    Progress,
    SpinnerColumn,
    BarColumn,
    TextColumn,
    TimeElapsedColumn,
    Confirm,
    box,
    emit_json,
    risk_for_target,
    get_dir_size,
    human_size,
    safe_delete,
    build_scan_results,
    preview_items,
    print_banner,
)

# ─────────────────────────────────────────────
#  Scan command
# ─────────────────────────────────────────────

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
        progress_label="Scanning…",
    )

    # Filter to existing paths only for display
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
        print(f"Run: mac-sweep clean")


# ─────────────────────────────────────────────
#  Clean command
# ─────────────────────────────────────────────

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
        console.print("[bold cyan]Scanning for junk…[/bold cyan]\n")

    exclude_patterns = args.exclude or []
    raw_results = build_scan_results(
        selected,
        exclude_patterns=exclude_patterns,
        min_age_days=args.age_days,
        progress_label="Preparing clean plan…",
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
            console.print("[green]✓ Nothing to clean — your Mac is already tidy![/green]")
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
            console.print(f"  Size: [bold yellow]{size_str}[/bold yellow]  "
                          f"Safe: {'[green]Yes[/green]' if r['safe'] else '[red]Caution[/red]'}  "
                          f"Risk: [{risk_color}]{r['risk']}[/{risk_color}]")
            console.print(f"  [dim]Why: {r['safe_reason']}[/dim]")

        if args.preview_suspicious and not args.yes and r["risk"] in {"review", "danger"} and HAS_RICH and not args.json:
            if Confirm.ask("  Preview largest items before deciding?", default=True):
                preview = preview_items(r["path"], limit=args.preview_limit, exclude_patterns=exclude_patterns, min_age_days=args.age_days)
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
        progress_label="Measuring post-clean snapshot…",
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


# ─────────────────────────────────────────────
#  Large files command
# ─────────────────────────────────────────────

def cmd_large(args):
    if not args.json:
        print_banner()
    search_path = Path(args.path).expanduser() if args.path else HOME
    min_size = args.min_mb * 1024 * 1024
    limit = args.limit

    if HAS_RICH and not args.json:
        console.print(f"[bold cyan]Searching for files > {args.min_mb} MB in[/bold cyan] [dim]{search_path}[/dim]\n")

    large_files = []

    with (Progress(
        SpinnerColumn(spinner_name="dots2", style="cyan"),
        TextColumn("[bold cyan]{task.description}"),
        console=console,
        transient=True,
    ) if HAS_RICH else open(os.devnull)) as progress:
        if HAS_RICH:
            task = progress.add_task("Scanning…", total=None)

        try:
            for root, dirs, files in os.walk(search_path, followlinks=False):
                dirs[:] = [d for d in dirs if not d.startswith('.') or args.hidden]
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
        emit_json({
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
        })
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


# ─────────────────────────────────────────────
#  Doctor command — quick system summary
# ─────────────────────────────────────────────

def cmd_doctor(args):
    if not args.json:
        print_banner()

    checks = []

    # Disk usage
    total, used, free = shutil.disk_usage("/")
    pct = used / total * 100
    checks.append(("Disk Usage", f"{human_size(used)} / {human_size(total)} ({pct:.0f}%)",
                   "red" if pct > 90 else "yellow" if pct > 75 else "green"))

    # macOS version
    try:
        ver = subprocess.check_output(["sw_vers", "-productVersion"], text=True).strip()
        checks.append(("macOS Version", ver, "white"))
    except Exception:
        pass

    # Homebrew outdated
    try:
        out = subprocess.check_output(["brew", "outdated"], text=True, stderr=subprocess.DEVNULL).strip()
        count = len(out.splitlines()) if out else 0
        checks.append(("Homebrew Outdated", f"{count} package(s)", "yellow" if count > 5 else "green"))
    except Exception:
        checks.append(("Homebrew", "not installed", "dim"))

    # Trash size
    trash = HOME / ".Trash"
    if trash.exists():
        sz = get_dir_size(trash)
        checks.append(("Trash", human_size(sz), "yellow" if sz > 1e8 else "green"))

    # Cache estimate
    cache = HOME / "Library/Caches"
    if cache.exists():
        sz = get_dir_size(cache)
        checks.append(("User Caches", human_size(sz), "red" if sz > 2e9 else "yellow" if sz > 500e6 else "green"))

    recommendation_targets = [
        t for t in SCAN_TARGETS
        if t["safe"] or t["category"] in {"logs", "user", "backup", "dev"}
    ]
    recommendation_results = [r for r in build_scan_results(recommendation_targets) if r["exists"] and r["size"] > 0]
    recommendation_results.sort(key=lambda r: r["size"], reverse=True)
    top_recommendations = recommendation_results[:5]

    recommendations = []
    for r in top_recommendations:
        if r["risk"] == "safe":
            action = "Safe cleanup candidate"
        elif r["risk"] == "review":
            action = "Review before cleanup"
        else:
            action = "High caution; inspect manually"
        recommendations.append({
            "label": r["label"],
            "category": r["category"],
            "path": str(r["path"]),
            "risk": r["risk"],
            "estimated_reclaim_bytes": r["size"],
            "estimated_reclaim_human": human_size(r["size"]),
            "action": action,
        })

    if args.json:
        emit_json({
            "command": "doctor",
            "checks": [
                {"label": label, "value": value, "severity": color}
                for label, value, color in checks
            ],
            "recommended_actions": recommendations,
        })
        return

    if HAS_RICH:
        table = Table(box=box.SIMPLE_HEAD, header_style="bold bright_white", border_style="dim", min_width=60)
        table.add_column("Check", style="bold white", width=22)
        table.add_column("Result", width=40)

        for label, value, color in checks:
            table.add_row(label, f"[{color}]{value}[/{color}]")

        console.print(table)
        console.print()
        if recommendations:
            rec_table = Table(box=box.SIMPLE_HEAD, header_style="bold white", border_style="dim")
            rec_table.add_column("Priority", style="dim", width=8)
            rec_table.add_column("Action", style="bold white", width=26)
            rec_table.add_column("Est. Reclaim", justify="right", width=12)
            rec_table.add_column("Risk", width=8)
            for i, rec in enumerate(recommendations, 1):
                risk_color = RISK_COLORS.get(rec["risk"], "white")
                rec_table.add_row(
                    f"#{i}",
                    f"{rec['label']} ({rec['action']})",
                    f"[green]{rec['estimated_reclaim_human']}[/green]",
                    f"[{risk_color}]{rec['risk']}[/{risk_color}]",
                )
            console.print("[bold cyan]Recommended Actions (Ranked)[/bold cyan]")
            console.print(rec_table)
            console.print()
        console.print("[dim]Run [bold]mac-sweep scan[/bold] for a full junk analysis.[/dim]")
    else:
        for label, value, _ in checks:
            print(f"  {label:25s}  {value}")
        if recommendations:
            print("\nRecommended actions:")
            for i, rec in enumerate(recommendations, 1):
                print(f"  {i}. {rec['label']} ({rec['estimated_reclaim_human']}, risk: {rec['risk']})")



# ─────────────────────────────────────────────
#  App leftovers command
# ─────────────────────────────────────────────

def get_installed_app_names() -> set:
    """Return a set of app name fragments from /Applications."""
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
    """Find ~/Library/Application Support folders with no matching installed app."""
    if not args.json:
        print_banner()

    app_support = HOME / "Library/Application Support"
    if not app_support.exists():
        if HAS_RICH:
            console.print("[green]Application Support folder not found.[/green]")
        return

    installed = get_installed_app_names()

    SKIP_FRAGMENTS = {
        "apple", "mobilesync", "syncservices", "addressbook", "callhistory",
        "coresimulator", "crashreporter", "dock", "spotlight", "swiftpm",
        "webkit", "siri", "helpviewer", "instruments", "dtrace", "mdworker",
    }

    if HAS_RICH:
        console.print("[bold cyan]Scanning Application Support for orphaned app data…[/bold cyan]\n")

    orphans = []
    for item in sorted(app_support.iterdir()):
        name_lower = item.name.lower()
        if name_lower.startswith('.'):
            continue
        if any(s in name_lower for s in SKIP_FRAGMENTS):
            continue
        matched = any(app in name_lower or name_lower in app for app in installed)
        if not matched:
            sz = get_dir_size(item)
            if sz > 1024 * 1024:
                orphans.append((item, sz))

    orphans.sort(key=lambda x: x[1], reverse=True)

    if args.json:
        total = sum(sz for _, sz in orphans)
        emit_json({
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
        })
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
        console.print(Panel(
            f"[dim]Found [bold white]{len(orphans)}[/bold white] possible leftovers · "
            f"[bold white]{human_size(total)}[/bold white] total\n"
            f"Review carefully before deleting — some may be from active apps.[/dim]",
            border_style="yellow",
            expand=False,
        ))
    else:
        for item, sz in orphans:
            print(f"  {human_size(sz):>10}  {item}")


def cmd_restore(args):
    manifests_dir = HOME / ".mac_sweep" / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)

    manifest_files = sorted(manifests_dir.glob("cleanup-*.json"), reverse=True)
    if args.list:
        if args.json:
            emit_json({
                "command": "restore",
                "mode": "list",
                "manifests": [str(m) for m in manifest_files],
            })
            return
        if HAS_RICH:
            table = Table(box=box.SIMPLE_HEAD, header_style="bold white", border_style="dim")
            table.add_column("Manifest", style="white")
            for m in manifest_files:
                table.add_row(str(m))
            console.print(table)
        else:
            for m in manifest_files:
                print(m)
        return

    if args.manifest:
        manifest_path = Path(args.manifest).expanduser()
    else:
        if not manifest_files:
            if args.json:
                emit_json({"command": "restore", "status": "no-manifest-found"})
            else:
                print("No cleanup manifest found.")
            return
        manifest_path = manifest_files[0]

    if not manifest_path.exists():
        if args.json:
            emit_json({"command": "restore", "status": "manifest-not-found", "manifest": str(manifest_path)})
        else:
            print(f"Manifest not found: {manifest_path}")
        return

    data = json.loads(manifest_path.read_text())
    items = data.get("items", [])

    restored = 0
    skipped = 0
    failed = 0
    restored_bytes = 0
    results = []

    for item in items:
        src = item.get("source_path")
        trash_path = item.get("trash_path")
        size = int(item.get("size_bytes", 0))
        status = item.get("status")
        if status != "success" or not trash_path:
            continue

        src_path = Path(src)
        from_path = Path(trash_path)
        if not from_path.exists():
            skipped += 1
            results.append({"source_path": src, "status": "skipped", "message": "trash item missing"})
            continue

        if src_path.exists() and not args.overwrite:
            skipped += 1
            results.append({"source_path": src, "status": "skipped", "message": "destination exists"})
            continue

        if args.dry_run:
            restored += 1
            restored_bytes += size
            results.append({"source_path": src, "status": "dry-run", "message": f"would restore from {from_path}"})
            continue

        try:
            src_path.parent.mkdir(parents=True, exist_ok=True)
            if src_path.exists() and args.overwrite:
                if src_path.is_dir():
                    shutil.rmtree(src_path)
                else:
                    src_path.unlink()
            shutil.move(str(from_path), str(src_path))
            restored += 1
            restored_bytes += size
            results.append({"source_path": src, "status": "restored", "message": "ok"})
        except Exception as e:
            failed += 1
            results.append({"source_path": src, "status": "failed", "message": str(e)})

    if args.json:
        emit_json({
            "command": "restore",
            "manifest": str(manifest_path),
            "summary": {
                "restored": restored,
                "skipped": skipped,
                "failed": failed,
                "restored_bytes": restored_bytes,
                "restored_human": human_size(restored_bytes),
            },
            "results": results,
        })
        return

    if HAS_RICH:
        console.print(Panel(
            f"[bold white]Restored: [green]{restored}[/green]  ·  "
            f"Skipped: [yellow]{skipped}[/yellow]  ·  "
            f"Failed: [red]{failed}[/red]\n"
            f"Recovered size: [bold cyan]{human_size(restored_bytes)}[/bold cyan][/bold white]",
            border_style="cyan",
            expand=False,
        ))
        if results:
            t = Table(box=box.SIMPLE_HEAD, header_style="bold white", border_style="dim")
            t.add_column("Source", style="dim")
            t.add_column("Status")
            t.add_column("Message", style="dim")
            for row in results:
                t.add_row(row["source_path"], row["status"], row["message"])
            console.print(t)
    else:
        print(f"Restored {restored} item(s), skipped {skipped}, failed {failed}, recovered {human_size(restored_bytes)}")


# ─────────────────────────────────────────────
#  CLI entrypoint
# ─────────────────────────────────────────────

def main():
    raw_argv = sys.argv[1:]
    commands = {"scan", "clean", "large", "doctor", "leftovers", "restore"}
    if raw_argv and raw_argv[0] not in commands:
        discovered = next((c for c in commands if c in raw_argv), None)
        if discovered:
            raw_argv = [discovered] + [a for a in raw_argv if a != discovered]
        elif "--path" in raw_argv:
            # Convenience: allow `mac-sweep --path ~/Movies` and default to scan.
            raw_argv = ["scan"] + raw_argv

    parser = argparse.ArgumentParser(
        prog="mac-sweep",
        description="🧹  mac-sweep — find and remove junk on macOS",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── scan ──
    p_scan = sub.add_parser("scan", help="Scan for junk and show a report")
    p_scan.add_argument("--category", "-c", nargs="+",
                        choices=list(CATEGORY_COLORS.keys()),
                        help="Filter to specific categories")
    p_scan.add_argument("--top", type=int, default=None,
                        help="Show only the top N largest locations")
    p_scan.add_argument("--age-days", type=int, default=None,
                        help="Only count files older than this many days")
    p_scan.add_argument("--exclude", nargs="+", default=None,
                        help="Glob patterns to exclude (name, relative, or full path)")
    p_scan.add_argument("--path", "-p", default=None,
                        help="Custom directory to scan as a single target")
    p_scan.add_argument("--json", action="store_true",
                        help="Output machine-readable JSON")
    p_scan.set_defaults(func=cmd_scan)

    # ── clean ──
    p_clean = sub.add_parser("clean", help="Interactively delete junk")
    p_clean.add_argument("--category", "-c", nargs="+",
                         choices=list(CATEGORY_COLORS.keys()))
    p_clean.add_argument("--safe-only", "-s", action="store_true",
                         help="Only prompt for safe-to-delete locations")
    p_clean.add_argument("--yes", "-y", action="store_true",
                         help="Auto-confirm all deletions")
    p_clean.add_argument("--dry-run", "-n", action="store_true",
                         help="Show what would be deleted without deleting")
    p_clean.add_argument("--risk-level", choices=list(RISK_RANK.keys()), default="review",
                         help="Max risk level to include (default: review)")
    p_clean.add_argument("--delete-mode", choices=["permanent", "trash"], default="permanent",
                         help="Delete permanently or move to trash (default: permanent)")
    p_clean.add_argument("--age-days", type=int, default=None,
                         help="Only consider files older than this many days")
    p_clean.add_argument("--exclude", nargs="+", default=None,
                         help="Glob patterns to exclude (name, relative, or full path)")
    p_clean.add_argument("--preview-suspicious", dest="preview_suspicious", action="store_true",
                         help="Preview largest items for review/danger targets (default: enabled)")
    p_clean.add_argument("--no-preview-suspicious", dest="preview_suspicious", action="store_false",
                         help="Disable preview prompts for review/danger targets")
    p_clean.set_defaults(preview_suspicious=True)
    p_clean.add_argument("--preview-limit", type=int, default=5,
                         help="Max rows to show in suspicious preview (default: 5)")
    p_clean.add_argument("--json", action="store_true",
                         help="Output machine-readable JSON")
    p_clean.set_defaults(func=cmd_clean)

    # ── large ──
    p_large = sub.add_parser("large", help="Find large files")
    p_large.add_argument("--path", "-p", default=None, help="Directory to search (default: ~)")
    p_large.add_argument("--min-mb", "-m", type=int, default=100, help="Minimum file size in MB (default: 100)")
    p_large.add_argument("--limit", "-l", type=int, default=30, help="Max results to show (default: 30)")
    p_large.add_argument("--hidden", action="store_true", help="Include hidden directories")
    p_large.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_large.set_defaults(func=cmd_large)

    # ── doctor ──
    p_doc = sub.add_parser("doctor", help="Quick system health summary")
    p_doc.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_doc.set_defaults(func=cmd_doctor)

    # ── leftovers ──
    p_left = sub.add_parser("leftovers", help="Find orphaned app support folders")
    p_left.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_left.set_defaults(func=cmd_leftovers)

    # ── restore ──
    p_restore = sub.add_parser("restore", help="Restore cleanup items from trash-mode manifest")
    p_restore.add_argument("--manifest", default=None, help="Path to a cleanup manifest JSON file")
    p_restore.add_argument("--list", action="store_true", help="List available cleanup manifests")
    p_restore.add_argument("--dry-run", action="store_true", help="Preview what would be restored")
    p_restore.add_argument("--overwrite", action="store_true", help="Overwrite destination if it already exists")
    p_restore.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_restore.set_defaults(func=cmd_restore)

    args = parser.parse_args(raw_argv)
    args.func(args)


if __name__ == "__main__":
    main()