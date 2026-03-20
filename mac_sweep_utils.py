import os
import fnmatch
import json
from pathlib import Path
from datetime import datetime

from mac_sweep_config import CATEGORY_SAFE_EXPLANATIONS

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.prompt import Confirm
    from rich import box
    from rich.text import Text
    from rich.align import Align
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

console = Console() if HAS_RICH else None


def emit_json(payload: dict):
    print(json.dumps(payload, indent=2))


def risk_for_target(target: dict) -> str:
    if target.get("safe"):
        return "safe"
    if target.get("category") in {"backup", "system", "user", "apps"}:
        return "danger"
    return "review"


def should_exclude(path: Path, root: Path, exclude_patterns: list[str]) -> bool:
    if not exclude_patterns:
        return False
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)
    full = str(path)
    name = path.name
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(full, pattern):
            return True
    return False


def is_older_than(st, min_age_days: int | None) -> bool:
    if min_age_days is None:
        return True
    cutoff = datetime.now().timestamp() - (min_age_days * 86400)
    return st.st_mtime <= cutoff


def get_dir_size(path: Path, exclude_patterns: list[str] | None = None, min_age_days: int | None = None, root: Path | None = None) -> int:
    total = 0
    exclude_patterns = exclude_patterns or []
    root = root or path
    try:
        for entry in os.scandir(path):
            try:
                st = entry.stat(follow_symlinks=False)
                entry_path = Path(entry.path)
                if should_exclude(entry_path, root, exclude_patterns):
                    continue
                if entry.is_file(follow_symlinks=False):
                    if not is_older_than(st, min_age_days):
                        continue
                    blocks = getattr(st, "st_blocks", None)
                    if blocks is not None:
                        total += blocks * 512
                    else:
                        total += st.st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += get_dir_size(entry_path, exclude_patterns=exclude_patterns, min_age_days=min_age_days, root=root)
            except (PermissionError, OSError):
                pass
    except (PermissionError, OSError):
        pass
    return total


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def safe_delete(path: Path, dry_run: bool = True, delete_mode: str = "permanent", trash_dir: Path | None = None) -> tuple[bool, str, str | None]:
    if dry_run:
        return True, "dry-run", None
    try:
        if delete_mode == "trash":
            if trash_dir is None:
                raise ValueError("trash_dir is required when delete_mode='trash'")
            trash_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            candidate = trash_dir / f"{path.name}-{stamp}"
            n = 1
            while candidate.exists():
                candidate = trash_dir / f"{path.name}-{stamp}-{n}"
                n += 1
            import shutil
            shutil.move(str(path), str(candidate))
            return True, "moved-to-trash", str(candidate)
        if path.is_dir():
            import shutil
            shutil.rmtree(path)
        else:
            path.unlink()
        return True, "deleted", None
    except PermissionError:
        return False, "permission denied", None
    except Exception as e:
        return False, str(e), None


def build_scan_results(selected: list[dict], exclude_patterns: list[str] | None = None, min_age_days: int | None = None, progress_label: str = "Scanning…") -> list[dict]:
    exclude_patterns = exclude_patterns or []
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
            task = progress.add_task(progress_label, total=len(selected), size="")
            for target in selected:
                progress.update(task, description=f"[bold cyan]Scanning  [white]{target['label']}")
                p = target["path"]
                if p.exists():
                    size = get_dir_size(p, exclude_patterns=exclude_patterns, min_age_days=min_age_days, root=p)
                    results.append({
                        **target,
                        "exists": True,
                        "size": size,
                        "path": p,
                        "risk": risk_for_target(target),
                        "safe_reason": CATEGORY_SAFE_EXPLANATIONS.get(target["category"], "Review before deleting."),
                    })
                    progress.update(task, size=human_size(size))
                else:
                    results.append({
                        **target,
                        "exists": False,
                        "size": 0,
                        "path": p,
                        "risk": risk_for_target(target),
                        "safe_reason": CATEGORY_SAFE_EXPLANATIONS.get(target["category"], "Review before deleting."),
                    })
                progress.advance(task)
    else:
        for target in selected:
            p = target["path"]
            if p.exists():
                size = get_dir_size(p, exclude_patterns=exclude_patterns, min_age_days=min_age_days, root=p)
                results.append({
                    **target,
                    "exists": True,
                    "size": size,
                    "path": p,
                    "risk": risk_for_target(target),
                    "safe_reason": CATEGORY_SAFE_EXPLANATIONS.get(target["category"], "Review before deleting."),
                })
            else:
                results.append({
                    **target,
                    "exists": False,
                    "size": 0,
                    "path": p,
                    "risk": risk_for_target(target),
                    "safe_reason": CATEGORY_SAFE_EXPLANATIONS.get(target["category"], "Review before deleting."),
                })
    return results


def preview_items(path: Path, limit: int, exclude_patterns: list[str] | None = None, min_age_days: int | None = None) -> list[tuple[Path, int]]:
    exclude_patterns = exclude_patterns or []
    rows = []
    if not path.exists() or not path.is_dir():
        return rows
    try:
        for child in path.iterdir():
            if should_exclude(child, path, exclude_patterns):
                continue
            try:
                st = child.stat()
                if child.is_file():
                    if not is_older_than(st, min_age_days):
                        continue
                    rows.append((child, st.st_size))
                elif child.is_dir():
                    rows.append((child, get_dir_size(child, exclude_patterns=exclude_patterns, min_age_days=min_age_days, root=child)))
            except (PermissionError, OSError):
                pass
    except (PermissionError, OSError):
        return rows
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows[:limit]


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
