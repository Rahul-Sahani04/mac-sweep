import argparse

from .config import CATEGORY_COLORS, RISK_RANK
from .commands.scan import cmd_scan
from .commands.clean import cmd_clean
from .commands.large import cmd_large
from .commands.doctor import cmd_doctor
from .commands.leftovers import cmd_leftovers
from .commands.restore import cmd_restore


def normalize_argv(raw_argv: list[str]) -> list[str]:
    commands = {"scan", "clean", "large", "doctor", "leftovers", "restore"}
    if raw_argv and raw_argv[0] not in commands:
        discovered = next((c for c in commands if c in raw_argv), None)
        if discovered:
            return [discovered] + [a for a in raw_argv if a != discovered]
        if "--path" in raw_argv:
            return ["scan"] + raw_argv
    return raw_argv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mac-sweep",
        description="🧹  mac-sweep — find and remove junk on macOS",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Scan for junk and show a report")
    p_scan.add_argument("--category", "-c", nargs="+", choices=list(CATEGORY_COLORS.keys()), help="Filter to specific categories")
    p_scan.add_argument("--top", type=int, default=None, help="Show only the top N largest locations")
    p_scan.add_argument("--age-days", type=int, default=None, help="Only count files older than this many days")
    p_scan.add_argument("--exclude", nargs="+", default=None, help="Glob patterns to exclude (name, relative, or full path)")
    p_scan.add_argument("--path", "-p", default=None, help="Custom directory to scan as a single target")
    p_scan.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_scan.set_defaults(func=cmd_scan)

    p_clean = sub.add_parser("clean", help="Interactively delete junk")
    p_clean.add_argument("--category", "-c", nargs="+", choices=list(CATEGORY_COLORS.keys()))
    p_clean.add_argument("--safe-only", "-s", action="store_true", help="Only prompt for safe-to-delete locations")
    p_clean.add_argument("--yes", "-y", action="store_true", help="Auto-confirm all deletions")
    p_clean.add_argument("--dry-run", "-n", action="store_true", help="Show what would be deleted without deleting")
    p_clean.add_argument("--risk-level", choices=list(RISK_RANK.keys()), default="review", help="Max risk level to include (default: review)")
    p_clean.add_argument("--delete-mode", choices=["permanent", "trash"], default="permanent", help="Delete permanently or move to trash (default: permanent)")
    p_clean.add_argument("--age-days", type=int, default=None, help="Only consider files older than this many days")
    p_clean.add_argument("--exclude", nargs="+", default=None, help="Glob patterns to exclude (name, relative, or full path)")
    p_clean.add_argument("--preview-suspicious", dest="preview_suspicious", action="store_true", help="Preview largest items for review/danger targets (default: enabled)")
    p_clean.add_argument("--no-preview-suspicious", dest="preview_suspicious", action="store_false", help="Disable preview prompts for review/danger targets")
    p_clean.set_defaults(preview_suspicious=True)
    p_clean.add_argument("--preview-limit", type=int, default=5, help="Max rows to show in suspicious preview (default: 5)")
    p_clean.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_clean.set_defaults(func=cmd_clean)

    p_large = sub.add_parser("large", help="Find large files")
    p_large.add_argument("--path", "-p", default=None, help="Directory to search (default: ~)")
    p_large.add_argument("--min-mb", "-m", type=int, default=100, help="Minimum file size in MB (default: 100)")
    p_large.add_argument("--limit", "-l", type=int, default=30, help="Max results to show (default: 30)")
    p_large.add_argument("--hidden", action="store_true", help="Include hidden directories")
    p_large.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_large.set_defaults(func=cmd_large)

    p_doc = sub.add_parser("doctor", help="Quick system health summary")
    p_doc.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_doc.set_defaults(func=cmd_doctor)

    p_left = sub.add_parser("leftovers", help="Find orphaned app support folders")
    p_left.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_left.set_defaults(func=cmd_leftovers)

    p_restore = sub.add_parser("restore", help="Restore cleanup items from trash-mode manifest")
    p_restore.add_argument("--manifest", default=None, help="Path to a cleanup manifest JSON file")
    p_restore.add_argument("--list", action="store_true", help="List available cleanup manifests")
    p_restore.add_argument("--dry-run", action="store_true", help="Preview what would be restored")
    p_restore.add_argument("--overwrite", action="store_true", help="Overwrite destination if it already exists")
    p_restore.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_restore.set_defaults(func=cmd_restore)

    return parser
