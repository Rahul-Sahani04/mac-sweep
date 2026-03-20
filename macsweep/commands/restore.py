import json
import shutil
from pathlib import Path

from ..config import HOME
from ..utils import HAS_RICH, console, Table, Panel, box, emit_json, human_size


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
        console.print(
            Panel(
                f"[bold white]Restored: [green]{restored}[/green]  ·  "
                f"Skipped: [yellow]{skipped}[/yellow]  ·  "
                f"Failed: [red]{failed}[/red]\n"
                f"Recovered size: [bold cyan]{human_size(restored_bytes)}[/bold cyan][/bold white]",
                border_style="cyan",
                expand=False,
            )
        )
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
