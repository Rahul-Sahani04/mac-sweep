# 🧹 mac-sweep

> A beautiful, fast CLI tool to find and remove junk, caches, and cruft from macOS.

```
  ███╗   ███╗ █████╗  ██████╗    ███████╗██╗    ██╗███████╗███████╗██████╗
  ████╗ ████║██╔══██╗██╔════╝    ██╔════╝██║    ██║██╔════╝██╔════╝██╔══██╗
  ██╔████╔██║███████║██║         ███████╗██║ █╗ ██║█████╗  █████╗  ██████╔╝
  ██║╚██╔╝██║██╔══██║██║         ╚════██║██║███╗██║██╔══╝  ██╔══╝  ██╔═══╝
  ██║ ╚═╝ ██║██║  ██║╚██████╗    ███████║╚███╔███╔╝███████╗███████╗██║
  ╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝    ╚══════╝ ╚══╝╚══╝ ╚══════╝╚══════╝╚═╝
```

---

## Features

- 🔍 **Scan** — Survey 20+ known junk locations with sizes and safety ratings
- 🗑️ **Clean** — Interactive or auto mode with risk levels and suspicious previews
- 📁 **Large files** — Hunt down space hogs anywhere on disk
- 🩺 **Doctor** — Instant system health snapshot
- 🧯 **Trash mode + restore** — Move cleaned items to trash with rollback manifests
- 🧩 **Automation-friendly JSON** — `--json` output for scripting and cron jobs
- 🎨 **Beautiful output** — Powered by [Rich](https://github.com/Textualize/rich), degrades gracefully without it
- ✅ **Dry-run mode** — Preview what would be deleted before committing

---

## Install

```bash
# Clone and install
git clone https://github.com/rahul-sahani04/mac-sweep
cd mac-sweep
bash install.sh

# Run from repo using local virtualenv
./run.sh scan

# Or use global command installed by install.sh
mac-sweep scan
```

The installer creates a local virtual environment at `.venv/`, installs dependencies from `requirements.txt`, and installs `mac-sweep` to `/usr/local/bin`.

If `/usr/local/bin` needs elevated permissions on your machine:

```bash
sudo bash install.sh
```

---

## Commands

### `scan` — find junk, show a report

```bash
mac-sweep scan
mac-sweep scan --category cache package dev
mac-sweep scan --path ~/Movies
mac-sweep --path ~/Movies           # convenience shortcut (defaults to scan)
mac-sweep scan --top 10 --age-days 30 --exclude "*.tmp" "*.log"
mac-sweep scan --json
```

Output: a sorted table of every junk location found, with sizes and safety ratings.

### `clean` — interactive deletion

```bash
mac-sweep clean                # prompts for each location
mac-sweep clean --safe-only    # only safe-to-delete targets
mac-sweep clean --safe-only --yes   # fully automatic safe clean
mac-sweep clean --dry-run      # preview without deleting
mac-sweep clean --risk-level safe --delete-mode trash
mac-sweep clean --preview-suspicious --preview-limit 5
mac-sweep clean --json
```

`clean` writes a rollback manifest to `~/.mac_sweep/manifests/`.

### `large` — find large files

```bash
mac-sweep large                    # files > 100 MB in ~
mac-sweep large --min-mb 500       # raise threshold to 500 MB
mac-sweep large --path ~/Movies    # search a specific folder
mac-sweep large --limit 50         # show more results
```

### `doctor` — quick health check

```bash
mac-sweep doctor
mac-sweep doctor --json
```

Shows: disk usage %, macOS version, Homebrew outdated count, Trash & cache sizes.

### `restore` — restore from trash-mode cleanup

```bash
mac-sweep restore --list
mac-sweep restore --dry-run
mac-sweep restore --manifest ~/.mac_sweep/manifests/cleanup-YYYYMMDD-HHMMSS.json
```

---

## Categories

| Category | What it covers |
|----------|---------------|
| `cache`  | User & system caches |
| `browser`| Chrome, Safari browser caches |
| `package`| npm, pip, Homebrew, Yarn, Gradle, Maven |
| `dev`    | Xcode DerivedData, simulators, Docker |
| `logs`   | App logs, crash reports, system logs |
| `backup` | iOS backups, Time Machine local snapshots |
| `apps`   | Leftover app support files |
| `system` | Trash, language packs |
| `user`   | Downloads and other user directories |

---

## Safety

Locations marked **Safe: ✓** are regenerated automatically by the OS or apps.
Locations marked **Safe: !** may contain data you want to keep — always review before deleting.

Use `--dry-run` to preview any operation safely.

---

## Requirements

- macOS 12+
- Python 3.8+
- Internet access during first install to fetch Python dependencies

Project files added for reproducible setup:

- `.gitignore` — ignores `.venv`, Python caches, and local artifacts
- `requirements.txt` — dependency list installed by `install.sh`
- `run.sh` — runs the app using the project virtualenv

Code layout (modularized):

- `mac_sweep.py` — compatibility entrypoint
- `macsweep/` — Python package root
- `macsweep/__main__.py` — package entrypoint (`python -m macsweep`)
- `macsweep/cli.py` — argument parsing and command routing
- `macsweep/config.py` — scan targets, category config, risk config
- `macsweep/utils.py` — shared helpers (size, filtering, deletion, JSON, rich rendering)
- `macsweep/commands/scan.py` — scan command
- `macsweep/commands/clean.py` — clean command
- `macsweep/commands/large.py` — large-files command
- `macsweep/commands/doctor.py` — doctor command
- `macsweep/commands/leftovers.py` — leftovers command
- `macsweep/commands/restore.py` — restore command

---

## License

MIT
