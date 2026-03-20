"""
mac-sweep AI report command
───────────────────────────
Runs a scan (or reuses piped JSON) and sends the results to a local LLM
(Ollama or LM Studio) for a plain-English analysis.

Supports:
  • Ollama   — http://localhost:11434  (default)
  • LM Studio — http://localhost:1234  (--backend lmstudio)

Usage:
  mac-sweep report                          # scan + AI analysis, print inline
  mac-sweep report --save                   # also write ~/mac-sweep-report.md
  mac-sweep report --backend lmstudio       # use LM Studio instead
  mac-sweep report --model llama3.2         # pick a specific model
  mac-sweep report --mode large             # analyse large-files instead of scan
  mac-sweep report --mode doctor            # analyse system health
  mac-sweep scan --json | mac-sweep report --stdin   # pipe scan JSON in
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from ..config import SCAN_TARGETS, CATEGORY_COLORS
from ..utils import (
    HAS_RICH,
    console,
    Panel,
    Text,
    Align,
    human_size,
    build_scan_results,
    get_dir_size,
    print_banner,
)

HOME = Path.home()

# ── Backend definitions ────────────────────────────────────────────────────────

BACKENDS = {
    "ollama": {
        "name": "Ollama",
        "base_url": "http://localhost:11434",
        "chat_path": "/api/chat",
        "models_path": "/api/tags",
        "default_model": "llama3.2",
        "stream_key": "message",          # nested: response.message.content
        "style": "ollama",
    },
    "lmstudio": {
        "name": "LM Studio",
        "base_url": "http://localhost:1234",
        "chat_path": "/v1/chat/completions",
        "models_path": "/v1/models",
        "default_model": None,            # auto-detect from running model
        "stream_key": "delta",            # nested: choices[0].delta.content
        "style": "openai",
    },
}

# ── Prompt templates ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a macOS disk-cleanup advisor embedded in a CLI tool called mac-sweep.
Your job is to read scan/health data and produce a clear, friendly, actionable report.

Rules:
- Be concise. Use markdown headers and bullet points.
- Give a short 2-sentence executive summary first.
- Then list items to clean in priority order (biggest wins first).
- For each item explain: what it is, why it's safe (or not) to delete, and the command to use.
- Flag anything that needs caution with ⚠️.
- End with an estimated total reclaim and one-liner next step.
- Do NOT repeat raw numbers the user can already see; add context instead.
- Keep the full report under 600 words.
"""

def build_scan_prompt(scan_data: dict) -> str:
    results = scan_data.get("results", [])
    total = scan_data.get("summary", {}).get("total_human", "unknown")
    lines = [f"Mac disk scan results — potential savings: {total}\n"]
    for r in results:
        flag = "SAFE" if r.get("safe") else f"RISK:{r.get('risk','?').upper()}"
        lines.append(f"- [{flag}] {r['label']} ({r['category']}): {r['size_human']} — {r['description']}")
    return "\n".join(lines)


def build_doctor_prompt(doctor_data: dict) -> str:
    lines = ["Mac system health snapshot:\n"]
    for check in doctor_data.get("checks", []):
        lines.append(f"- {check['label']}: {check['value']}")
    return "\n".join(lines)


def build_large_prompt(large_data: dict) -> str:
    files = large_data.get("files", [])
    lines = [f"Largest files on this Mac ({len(files)} shown):\n"]
    for f in files[:20]:
        lines.append(f"- {f['size_human']:>10}  {f['path']}")
    return "\n".join(lines)


def build_leftovers_prompt(data: dict) -> str:
    items = data.get("orphans", [])
    total = human_size(sum(i.get("size_bytes", 0) for i in items))
    lines = [f"Orphaned app-support folders ({len(items)} found, {total} total):\n"]
    for i in items[:25]:
        lines.append(f"- {i.get('size_human','?'):>10}  {i['name']}")
    return "\n".join(lines)


# ── Backend helpers ───────────────────────────────────────────────────────────

def _http_json(url: str, payload: dict | None = None, timeout: int = 10) -> dict:
    """GET (payload=None) or POST JSON and return parsed response."""
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def detect_backend() -> str | None:
    """Return 'ollama', 'lmstudio', or None if neither is reachable."""
    for name, cfg in BACKENDS.items():
        try:
            urllib.request.urlopen(cfg["base_url"], timeout=2)
            return name
        except Exception:
            pass
    return None


def list_models(backend: str) -> list[str]:
    cfg = BACKENDS[backend]
    try:
        resp = _http_json(cfg["base_url"] + cfg["models_path"], timeout=5)
        if backend == "ollama":
            return [m["name"] for m in resp.get("models", [])]
        else:
            return [m["id"] for m in resp.get("data", [])]
    except Exception:
        return []


def resolve_model(backend: str, requested: str | None) -> str | None:
    cfg = BACKENDS[backend]
    if requested:
        return requested
    if cfg["default_model"]:
        return cfg["default_model"]
    models = list_models(backend)
    return models[0] if models else None


def stream_ollama(base_url: str, model: str, messages: list[dict]):
    """Stream from Ollama /api/chat, yielding text chunks."""
    payload = {"model": model, "messages": messages, "stream": True}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        base_url + "/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw_line in resp:
            line = raw_line.decode().strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
                text = chunk.get("message", {}).get("content", "")
                if text:
                    yield text
                if chunk.get("done"):
                    break
            except json.JSONDecodeError:
                pass


def stream_openai(base_url: str, model: str, messages: list[dict]):
    """Stream from OpenAI-compatible /v1/chat/completions, yielding text chunks."""
    payload = {"model": model, "messages": messages, "stream": True}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        base_url + "/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw_line in resp:
            line = raw_line.decode().strip()
            if not line or line == "data: [DONE]":
                continue
            if line.startswith("data: "):
                line = line[6:]
            try:
                chunk = json.loads(line)
                text = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if text:
                    yield text
            except json.JSONDecodeError:
                pass


def stream_response(backend: str, model: str, messages: list[dict]):
    cfg = BACKENDS[backend]
    if cfg["style"] == "ollama":
        yield from stream_ollama(cfg["base_url"], model, messages)
    else:
        yield from stream_openai(cfg["base_url"], model, messages)


# ── Gather data helpers ───────────────────────────────────────────────────────

def gather_scan_data(args) -> dict:
    """Run a scan and return JSON-serialisable dict."""
    selected = [t for t in SCAN_TARGETS if not getattr(args, "category", None) or t["category"] in args.category]
    # Temporarily mock args fields needed by build_scan_results
    class _FakeArgs:
        exclude = None
        age_days = None
    results_raw = build_scan_results(selected, progress_label="Scanning for AI report…")
    found = [r for r in results_raw if r["exists"]]
    found.sort(key=lambda r: r["size"], reverse=True)
    total = sum(r["size"] for r in found)
    return {
        "command": "scan",
        "summary": {"locations": len(found), "total_bytes": total, "total_human": human_size(total)},
        "results": [
            {
                "label": r["label"],
                "category": r["category"],
                "path": str(r["path"]),
                "size_bytes": r["size"],
                "size_human": human_size(r["size"]),
                "safe": r["safe"],
                "risk": r["risk"],
                "description": r["description"],
                "safe_reason": r["safe_reason"],
            }
            for r in found
        ],
    }


def gather_doctor_data() -> dict:
    """Collect doctor checks and return dict."""
    checks = []
    total, used, free = shutil.disk_usage("/")
    pct = used / total * 100
    checks.append({"label": "Disk Usage", "value": f"{human_size(used)} / {human_size(total)} ({pct:.0f}%)"})
    try:
        ver = subprocess.check_output(["sw_vers", "-productVersion"], text=True).strip()
        checks.append({"label": "macOS Version", "value": ver})
    except Exception:
        pass
    try:
        out = subprocess.check_output(["brew", "outdated"], text=True, stderr=subprocess.DEVNULL).strip()
        count = len(out.splitlines()) if out else 0
        checks.append({"label": "Homebrew Outdated", "value": f"{count} package(s)"})
    except Exception:
        checks.append({"label": "Homebrew", "value": "not installed"})
    trash = HOME / ".Trash"
    if trash.exists():
        checks.append({"label": "Trash", "value": human_size(get_dir_size(trash))})
    cache = HOME / "Library/Caches"
    if cache.exists():
        checks.append({"label": "User Caches", "value": human_size(get_dir_size(cache))})
    return {"command": "doctor", "checks": checks}


def gather_large_data(min_mb: int = 200, limit: int = 20) -> dict:
    """Find large files and return dict."""
    min_size = min_mb * 1024 * 1024
    large_files = []
    try:
        for root, dirs, files in __import__("os").walk(HOME, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in files:
                fpath = Path(root) / fname
                try:
                    size = fpath.stat().st_size
                    if size >= min_size:
                        large_files.append({"path": str(fpath), "size_bytes": size, "size_human": human_size(size)})
                except (PermissionError, OSError):
                    pass
    except (PermissionError, OSError):
        pass
    large_files.sort(key=lambda f: f["size_bytes"], reverse=True)
    return {"command": "large", "min_mb": min_mb, "files": large_files[:limit]}


# ── Rendering helpers ─────────────────────────────────────────────────────────

def _print_streaming(backend_name: str, model: str, chunks):
    """Stream AI output to terminal with rich formatting."""
    full_text = []

    if HAS_RICH:
        console.print()
        console.print(Panel(
            f"[dim]🤖  {backend_name}  ·  model: [bold white]{model}[/bold white]  ·  streaming…[/dim]",
            border_style="cyan",
            expand=False,
        ))
        console.print()

        # Stream raw — rich Markdown rendering happens after
        from rich.live import Live
        from rich.markdown import Markdown

        buffer = ""
        with Live(Markdown(buffer), console=console, refresh_per_second=8) as live:
            for chunk in chunks:
                buffer += chunk
                full_text.append(chunk)
                live.update(Markdown(buffer))

        console.print()
    else:
        print(f"\n[{backend_name} · {model}]\n")
        for chunk in chunks:
            print(chunk, end="", flush=True)
            full_text.append(chunk)
        print("\n")

    return "".join(full_text)


def _save_report(content: str, mode: str) -> Path:
    """Write the report to ~/mac-sweep-report.md"""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = HOME / f"mac-sweep-report-{mode}-{ts}.md"
    header = f"# mac-sweep AI Report\n\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n\n---\n\n"
    out_path.write_text(header + content)
    return out_path


# ── Main command ──────────────────────────────────────────────────────────────

def cmd_report(args):
    if not getattr(args, "stdin", False):
        print_banner()

    # ── 1. Detect / validate backend ──────────────────────────────────────────
    requested_backend = getattr(args, "backend", None) or "auto"

    if requested_backend == "auto":
        backend = detect_backend()
        if not backend:
            _no_backend_error()
            return
    else:
        backend = requested_backend
        cfg = BACKENDS.get(backend)
        if not cfg:
            _err(f"Unknown backend '{backend}'. Choose: {', '.join(BACKENDS)}")
            return
        try:
            urllib.request.urlopen(cfg["base_url"], timeout=3)
        except Exception:
            _no_backend_error(backend)
            return

    cfg = BACKENDS[backend]

    # ── 2. Resolve model ──────────────────────────────────────────────────────
    model = resolve_model(backend, getattr(args, "model", None))
    if not model:
        _err(f"No model found on {cfg['name']}. Pull one first, e.g.:\n  ollama pull llama3.2")
        return

    # ── 3. Gather data ────────────────────────────────────────────────────────
    mode = getattr(args, "mode", "scan")

    if getattr(args, "stdin", False):
        raw = sys.stdin.read().strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            _err("Could not parse JSON from stdin.")
            return
        # infer mode from JSON
        mode = data.get("command", "scan")
    else:
        if HAS_RICH:
            console.print(f"[bold cyan]Gathering data ({mode})…[/bold cyan]")

        if mode == "scan":
            data = gather_scan_data(args)
        elif mode == "doctor":
            data = gather_doctor_data()
        elif mode == "large":
            min_mb = getattr(args, "min_mb", 200)
            data = gather_large_data(min_mb=min_mb)
        elif mode == "leftovers":
            # reuse leftovers command data via its JSON output
            data = {"command": "leftovers", "orphans": [], "note": "Run mac-sweep leftovers --json for details."}
        else:
            data = gather_scan_data(args)

    # ── 4. Build prompt ───────────────────────────────────────────────────────
    if mode == "doctor":
        user_content = build_doctor_prompt(data)
    elif mode == "large":
        user_content = build_large_prompt(data)
    elif mode == "leftovers":
        user_content = build_leftovers_prompt(data)
    else:
        user_content = build_scan_prompt(data)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]

    # ── 5. Stream response ────────────────────────────────────────────────────
    if HAS_RICH:
        console.print(f"\n[dim]Connected to [bold white]{cfg['name']}[/bold white] · model [bold white]{model}[/bold white][/dim]")

    try:
        chunks = stream_response(backend, model, messages)
        full_text = _print_streaming(cfg["name"], model, chunks)
    except urllib.error.URLError as e:
        _err(f"Connection to {cfg['name']} failed: {e.reason}")
        return
    except Exception as e:
        _err(f"Streaming error: {e}")
        return

    # ── 6. Optionally save ────────────────────────────────────────────────────
    if getattr(args, "save", False) and full_text:
        path = _save_report(full_text, mode)
        if HAS_RICH:
            console.print(Panel(
                f"[green]✓ Report saved to[/green] [bold white]{path}[/bold white]",
                border_style="green",
                expand=False,
            ))
        else:
            print(f"\nReport saved to: {path}")


# ── Error helpers ─────────────────────────────────────────────────────────────

def _err(msg: str):
    if HAS_RICH:
        console.print(f"[bold red]✗[/bold red] {msg}")
    else:
        print(f"Error: {msg}", file=sys.stderr)


def _no_backend_error(requested: str | None = None):
    name = BACKENDS[requested]["name"] if requested and requested in BACKENDS else "Ollama or LM Studio"
    if HAS_RICH:
        console.print(Panel(
            f"[bold red]✗ Could not reach {name}[/bold red]\n\n"
            "[white]To use AI reports you need a local LLM running:[/white]\n\n"
            "[bold cyan]  Ollama (recommended)[/bold cyan]\n"
            "    brew install ollama\n"
            "    ollama serve\n"
            "    ollama pull llama3.2\n\n"
            "[bold cyan]  LM Studio[/bold cyan]\n"
            "    Download from lmstudio.ai, load a model, start the local server\n\n"
            "[dim]Then run:  mac-sweep report[/dim]",
            border_style="red",
            title="Local AI not found",
            expand=False,
        ))
    else:
        print(f"\nError: {name} is not running.\n"
              "Install Ollama: brew install ollama && ollama serve && ollama pull llama3.2\n"
              "Or use LM Studio: lmstudio.ai\n")
