#!/usr/bin/env python3
"""
mac_sweep — a beautiful CLI tool to find junk, cache, and cruft on macOS
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
#  Optional rich dependency (install if missing)
# ─────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.prompt import Confirm
    from rich import box
    from rich.text import Text
    from rich.columns import Columns
    from rich.align import Align
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

HOME = Path.home()
console = Console() if HAS_RICH else None

# ─────────────────────────────────────────────
#  Scan targets
# ─────────────────────────────────────────────

SCAN_TARGETS = [
    {
        "label": "User Cache",
        "path": HOME / "Library/Caches",
        "description": "App caches stored per-user",
        "safe": True,
        "category": "cache",
    },
    {
        "label": "System Cache",
        "path": Path("/Library/Caches"),
        "description": "System-wide app caches",
        "safe": True,
        "category": "cache",
    },
    {
        "label": "Browser Caches",
        "path": HOME / "Library/Caches/Google/Chrome",
        "description": "Chrome browser cache",
        "safe": True,
        "category": "browser",
    },
    {
        "label": "Safari Cache",
        "path": HOME / "Library/Caches/com.apple.Safari",
        "description": "Safari browser cache",
        "safe": True,
        "category": "browser",
    },
    {
        "label": "Homebrew Cache",
        "path": HOME / "Library/Caches/Homebrew",
        "description": "Downloaded Homebrew packages",
        "safe": True,
        "category": "package",
    },
    {
        "label": "pip Cache",
        "path": HOME / "Library/Caches/pip",
        "description": "Python pip package cache",
        "safe": True,
        "category": "package",
    },
    {
        "label": "npm Cache",
        "path": HOME / ".npm/_cacache",
        "description": "Node.js npm package cache",
        "safe": True,
        "category": "package",
    },
    {
        "label": "Yarn Cache",
        "path": HOME / "Library/Caches/Yarn",
        "description": "Yarn package manager cache",
        "safe": True,
        "category": "package",
    },
    {
        "label": "Gradle Cache",
        "path": HOME / ".gradle/caches",
        "description": "Java Gradle build cache",
        "safe": True,
        "category": "package",
    },
    {
        "label": "Maven Cache",
        "path": HOME / ".m2/repository",
        "description": "Java Maven local repository",
        "safe": True,
        "category": "package",
    },
    {
        "label": "Xcode DerivedData",
        "path": HOME / "Library/Developer/Xcode/DerivedData",
        "description": "Xcode build artefacts (can be very large)",
        "safe": True,
        "category": "dev",
    },
    {
        "label": "Xcode Archives",
        "path": HOME / "Library/Developer/Xcode/Archives",
        "description": "Old Xcode app archives",
        "safe": False,
        "category": "dev",
    },
    {
        "label": "iOS Device Support",
        "path": HOME / "Library/Developer/Xcode/iOS DeviceSupport",
        "description": "Device symbols for older iOS versions",
        "safe": True,
        "category": "dev",
    },
    {
        "label": "Simulator Runtimes",
        "path": HOME / "Library/Developer/CoreSimulator/Caches",
        "description": "iOS Simulator caches",
        "safe": True,
        "category": "dev",
    },
    {
        "label": "Trash",
        "path": HOME / ".Trash",
        "description": "Items in the Trash waiting to be emptied",
        "safe": True,
        "category": "system",
    },
    {
        "label": "Old Logs",
        "path": HOME / "Library/Logs",
        "description": "Application log files",
        "safe": True,
        "category": "logs",
    },
    {
        "label": "System Logs",
        "path": Path("/var/log"),
        "description": "macOS system logs",
        "safe": True,
        "category": "logs",
    },
    {
        "label": "Crash Reports",
        "path": HOME / "Library/Logs/DiagnosticReports",
        "description": "App crash diagnostic reports",
        "safe": True,
        "category": "logs",
    },
    {
        "label": "iOS Backups",
        "path": HOME / "Library/Application Support/MobileSync/Backup",
        "description": "Local iPhone/iPad backups",
        "safe": False,
        "category": "backup",
    },
    {
        "label": "Time Machine Snapshots",
        "path": Path("/.MobileBackups"),
        "description": "Local Time Machine snapshots",
        "safe": False,
        "category": "backup",
    },
    {
        "label": "Docker Data",
        # Docker Desktop stores its VM disk image here on modern macOS.
        # The old path (Library/Containers/com.docker.docker/Data) contains a sparse
        # virtual disk whose st_size vastly overstates real usage — we now use st_blocks.
        "path": HOME / "Library/Containers/com.docker.docker/Data/vms/0/data",
        "description": "Docker VM disk (actual allocated size)",
        "safe": False,
        "category": "dev",
    },
    {
        "label": "Docker Cache",
        "path": HOME / "Library/Containers/com.docker.docker/Data/cache",
        "description": "Docker layer & build cache",
        "safe": True,
        "category": "dev",
    },
    # NOTE: We intentionally do NOT scan all of ~/Library/Application Support —
    # it's too broad and includes active app data. The scan_app_leftovers() function
    # handles this more carefully via the 'leftovers' command.
    {
        "label": "Language Support Files",
        "path": Path("/System/Library/PrivateFrameworks"),
        "description": "Extra language packs (read-only on modern macOS)",
        "safe": False,
        "category": "system",
    },
    {
        "label": "Old Downloads",
        "path": HOME / "Downloads",
        "description": "Files in Downloads folder (review before deleting)",
        "safe": False,
        "category": "user",
    },
]

CATEGORY_COLORS = {
    "cache":   "cyan",
    "browser": "blue",
    "package": "green",
    "dev":     "yellow",
    "logs":    "magenta",
    "backup":  "red",
    "apps":    "orange3",
    "system":  "white",
    "user":    "bright_white",
}

CATEGORY_ICONS = {
    "cache":   "🗂 ",
    "browser": "🌐",
    "package": "📦",
    "dev":     "🔨",
    "logs":    "📋",
    "backup":  "💾",
    "apps":    "📱",
    "system":  "⚙️ ",
    "user":    "👤",
}

# ─────────────────────────────────────────────
#  Utility helpers
# ─────────────────────────────────────────────

def get_dir_size(path: Path) -> int:
    """Return actual on-disk size in bytes (uses st_blocks to handle sparse files correctly).
    
    st_size is the logical/apparent size — for sparse virtual disk images (Docker .raw,
    .qcow2, VM disks) it reports the full virtual size which can be hundreds of GBs even
    when the actual data is much smaller. st_blocks * 512 gives the real allocated blocks.
    """
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                st = entry.stat(follow_symlinks=False)
                if entry.is_file(follow_symlinks=False):
                    # Use actual allocated blocks. st_blocks is in 512-byte units.
                    # Fall back to st_size if st_blocks is unavailable (shouldn't happen on macOS).
                    blocks = getattr(st, 'st_blocks', None)
                    if blocks is not None:
                        total += blocks * 512
                    else:
                        total += st.st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += get_dir_size(Path(entry.path))
            except (PermissionError, OSError):
                pass
    except (PermissionError, OSError):
        pass
    return total


def human_size(n: int) -> str:
    """Convert bytes to a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def safe_delete(path: Path, dry_run: bool = True) -> tuple[bool, str]:
    """Delete a path. Returns (success, message)."""
    if dry_run:
        return True, "dry-run"
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return True, "deleted"
    except PermissionError:
        return False, "permission denied"
    except Exception as e:
        return False, str(e)

# ─────────────────────────────────────────────
#  Banner
# ─────────────────────────────────────────────

BANNER = r"""
  ███╗   ███╗ █████╗  ██████╗    ███████╗██╗    ██╗███████╗███████╗██████╗
  ████╗ ████║██╔══██╗██╔════╝    ██╔════╝██║    ██║██╔════╝██╔════╝██╔══██╗
  ██╔████╔██║███████║██║         ███████╗██║ █╗ ██║█████╗  █████╗  ██████╔╝
  ██║╚██╔╝██║██╔══██║██║         ╚════██║██║███╗██║██╔══╝  ██╔══╝  ██╔═══╝
  ██║ ╚═╝ ██║██║  ██║╚██████╗    ███████║╚███╔███╔╝███████╗███████╗██║
  ╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝    ╚══════╝ ╚══╝╚══╝ ╚══════╝╚══════╝╚═╝
"""

def print_banner():
    if HAS_RICH:
        console.print(BANNER, style="bold cyan", highlight=False)
        console.print(
            Align.center(
                Text("macOS disk junk finder & cleaner  ·  github.com/rahul-sahani04/mac-sweep", style="dim italic")
            )
        )
        console.print()
    else:
        print(BANNER)
        print("  macOS disk junk finder & cleaner")
        print()

# ─────────────────────────────────────────────
#  Scan command
# ─────────────────────────────────────────────

def cmd_scan(args):
    print_banner()

    selected = [t for t in SCAN_TARGETS if not args.category or t["category"] in args.category]
    results = []

    if HAS_RICH:
        with Progress(
            SpinnerColumn(spinner_name="dots2", style="cyan"),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=30, style="cyan", complete_style="bright_cyan"),
            TextColumn("[dim]{task.fields[size]}"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Scanning…", total=len(selected), size="")
            for target in selected:
                progress.update(task, description=f"[bold cyan]Scanning  [white]{target['label']}")
                p = target["path"]
                if p.exists():
                    size = get_dir_size(p)
                    results.append({**target, "exists": True, "size": size, "path": p})
                    progress.update(task, size=human_size(size))
                else:
                    results.append({**target, "exists": False, "size": 0, "path": p})
                progress.advance(task)
    else:
        for target in selected:
            p = target["path"]
            if p.exists():
                size = get_dir_size(p)
                results.append({**target, "exists": True, "size": size})
                print(f"  {target['label']:30s}  {human_size(size)}")
            else:
                results.append({**target, "exists": False, "size": 0})

    # Filter to existing paths only for display
    found = [r for r in results if r["exists"]]
    found.sort(key=lambda r: r["size"], reverse=True)

    total = sum(r["size"] for r in found)

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
        table.add_column("Safe?", justify="center", width=6)

        for r in found:
            cat = r["category"]
            color = CATEGORY_COLORS.get(cat, "white")
            icon = CATEGORY_ICONS.get(cat, "  ")
            safe_badge = "[green]✓[/green]" if r["safe"] else "[red]![/red]"
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
                safe_badge,
            )

        console.print(table)
        console.print()
        console.print(Panel(
            f"[bold white]Found [bold cyan]{len(found)}[/bold cyan] locations  ·  "
            f"Potential savings: [bold {'red' if total > 1e9 else 'yellow'}]{human_size(total)}[/bold {'red' if total > 1e9 else 'yellow'}]\n"
            f"[dim]Run [bold]mac-sweep clean[/bold] to interactively delete, or [bold]mac-sweep clean --safe-only[/bold] for auto-clean[/dim]",
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
    print_banner()

    selected = [t for t in SCAN_TARGETS if not args.category or t["category"] in args.category]
    if args.safe_only:
        selected = [t for t in selected if t["safe"]]

    if HAS_RICH:
        console.print("[bold cyan]Scanning for junk…[/bold cyan]\n")

    results = []
    for target in selected:
        p = target["path"]
        if p.exists():
            size = get_dir_size(p)
            if size > 0:
                results.append({**target, "path": p, "size": size})

    results.sort(key=lambda r: r["size"], reverse=True)

    if not results:
        if HAS_RICH:
            console.print("[green]✓ Nothing to clean — your Mac is already tidy![/green]")
        else:
            print("Nothing to clean!")
        return

    deleted_size = 0
    deleted_count = 0

    for r in results:
        size_str = human_size(r["size"])
        cat_color = CATEGORY_COLORS.get(r["category"], "white")
        icon = CATEGORY_ICONS.get(r["category"], "  ")

        if HAS_RICH:
            console.print(
                f"\n[bold white]{r['label']}[/bold white]  "
                f"[{cat_color}]{icon} {r['category']}[/{cat_color}]  "
                f"[dim]{r['path']}[/dim]"
            )
            console.print(f"  [dim]{r['description']}[/dim]")
            console.print(f"  Size: [bold yellow]{size_str}[/bold yellow]  "
                          f"Safe: {'[green]Yes[/green]' if r['safe'] else '[red]Caution[/red]'}")

        if args.yes or (HAS_RICH and Confirm.ask(f"  Delete [bold]{r['label']}[/bold]?")):
            ok, msg = safe_delete(r["path"], dry_run=args.dry_run)
            if ok:
                deleted_size += r["size"]
                deleted_count += 1
                label = "[dim](dry run)[/dim]" if args.dry_run else "[green]✓ Deleted[/green]"
                if HAS_RICH:
                    console.print(f"  {label}")
                else:
                    print(f"  {'(dry run)' if args.dry_run else 'Deleted'}: {r['label']}")
            else:
                if HAS_RICH:
                    console.print(f"  [red]✗ Failed: {msg}[/red]")
                else:
                    print(f"  Failed: {msg}")

    if HAS_RICH:
        action = "Would free" if args.dry_run else "Freed"
        console.print()
        console.print(Panel(
            f"[bold white]{action} [bold cyan]{human_size(deleted_size)}[/bold cyan] "
            f"across [bold cyan]{deleted_count}[/bold cyan] location(s)[/bold white]",
            border_style="green" if deleted_count else "dim",
            expand=False,
        ))
    else:
        print(f"\nCleaned {deleted_count} locations, freed {human_size(deleted_size)}")


# ─────────────────────────────────────────────
#  Large files command
# ─────────────────────────────────────────────

def cmd_large(args):
    print_banner()
    search_path = Path(args.path).expanduser() if args.path else HOME
    min_size = args.min_mb * 1024 * 1024
    limit = args.limit

    if HAS_RICH:
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

    if HAS_RICH:
        table = Table(box=box.SIMPLE_HEAD, header_style="bold bright_white", border_style="dim", min_width=60)
        table.add_column("Check", style="bold white", width=22)
        table.add_column("Result", width=40)

        for label, value, color in checks:
            table.add_row(label, f"[{color}]{value}[/{color}]")

        console.print(table)
        console.print()
        console.print("[dim]Run [bold]mac-sweep scan[/bold] for a full junk analysis.[/dim]")
    else:
        for label, value, _ in checks:
            print(f"  {label:25s}  {value}")



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


# ─────────────────────────────────────────────
#  CLI entrypoint
# ─────────────────────────────────────────────

def main():
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
    p_clean.set_defaults(func=cmd_clean)

    # ── large ──
    p_large = sub.add_parser("large", help="Find large files")
    p_large.add_argument("--path", "-p", default=None, help="Directory to search (default: ~)")
    p_large.add_argument("--min-mb", "-m", type=int, default=100, help="Minimum file size in MB (default: 100)")
    p_large.add_argument("--limit", "-l", type=int, default=30, help="Max results to show (default: 30)")
    p_large.add_argument("--hidden", action="store_true", help="Include hidden directories")
    p_large.set_defaults(func=cmd_large)

    # ── doctor ──
    p_doc = sub.add_parser("doctor", help="Quick system health summary")
    p_doc.set_defaults(func=cmd_doctor)

    # ── leftovers ──
    p_left = sub.add_parser("leftovers", help="Find orphaned app support folders")
    p_left.set_defaults(func=cmd_leftovers)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()