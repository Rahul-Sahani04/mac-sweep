import shutil
import subprocess

from ..config import HOME, SCAN_TARGETS, RISK_COLORS
from ..utils import (
    HAS_RICH,
    console,
    Table,
    box,
    emit_json,
    human_size,
    build_scan_results,
    get_dir_size,
    print_banner,
)


def cmd_doctor(args):
    if not args.json:
        print_banner()

    checks = []

    total, used, _ = shutil.disk_usage("/")
    pct = used / total * 100
    checks.append(
        (
            "Disk Usage",
            f"{human_size(used)} / {human_size(total)} ({pct:.0f}%)",
            "red" if pct > 90 else "yellow" if pct > 75 else "green",
        )
    )

    try:
        ver = subprocess.check_output(["sw_vers", "-productVersion"], text=True).strip()
        checks.append(("macOS Version", ver, "white"))
    except Exception:
        pass

    try:
        out = subprocess.check_output(["brew", "outdated"], text=True, stderr=subprocess.DEVNULL).strip()
        count = len(out.splitlines()) if out else 0
        checks.append(("Homebrew Outdated", f"{count} package(s)", "yellow" if count > 5 else "green"))
    except Exception:
        checks.append(("Homebrew", "not installed", "dim"))

    trash = HOME / ".Trash"
    if trash.exists():
        sz = get_dir_size(trash)
        checks.append(("Trash", human_size(sz), "yellow" if sz > 1e8 else "green"))

    cache = HOME / "Library/Caches"
    if cache.exists():
        sz = get_dir_size(cache)
        checks.append(("User Caches", human_size(sz), "red" if sz > 2e9 else "yellow" if sz > 500e6 else "green"))

    recommendation_targets = [
        t for t in SCAN_TARGETS if t["safe"] or t["category"] in {"logs", "user", "backup", "dev"}
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
        recommendations.append(
            {
                "label": r["label"],
                "category": r["category"],
                "path": str(r["path"]),
                "risk": r["risk"],
                "estimated_reclaim_bytes": r["size"],
                "estimated_reclaim_human": human_size(r["size"]),
                "action": action,
            }
        )

    if args.json:
        emit_json(
            {
                "command": "doctor",
                "checks": [{"label": label, "value": value, "severity": color} for label, value, color in checks],
                "recommended_actions": recommendations,
            }
        )
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
