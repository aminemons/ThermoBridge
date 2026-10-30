"""Small provenance helpers shared by reproducible ThermoBridge runs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_hash() -> str:
    paths = sorted(p for name in ("src", "scripts", "configs", "rtl", "tb", "tests", "flow")
                   for base in [ROOT / name] if base.exists() for p in base.rglob("*")
                   if p.is_file() and not any(x in {"__pycache__", ".pytest_cache", "build"} for x in p.parts))
    h = hashlib.sha256()
    for p in paths:
        h.update(p.relative_to(ROOT).as_posix().encode())
        h.update(bytes.fromhex(sha256_file(p)))
    return h.hexdigest()


def git_state() -> dict:
    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    commit=git("rev-parse", "HEAD") or os.environ.get('THERMOBRIDGE_SOURCE_COMMIT')
    dirty=git("status", "--porcelain")
    return {"commit":commit,"dirty":bool(dirty) if dirty is not None else os.environ.get('THERMOBRIDGE_SOURCE_DIRTY','true')=='true'}


def write_manifest(path: Path, *, run_id: str, command: list[str], input_paths: list[Path], seed, started: datetime,
                   status: str, output_paths: list[Path], extra: dict | None = None) -> dict:
    if status=='complete':
        missing=[str(p) for p in output_paths if not p.is_file()]
        if missing:raise FileNotFoundError('Successful run is missing outputs: '+', '.join(missing))
    state = git_state()
    env_path = ROOT / "reports/environment.json"
    try:
        environment = json.loads(env_path.read_text(encoding="utf-8"))
        tool_versions = {name: (value.get("version") if isinstance(value, dict) else value)
                         for name, value in environment.get("tools", {}).items()}
        tool_versions.update(environment.get("python_packages", {}))
        environment_hash = sha256_file(env_path)
    except (OSError, json.JSONDecodeError):
        tool_versions, environment_hash = {"python": sys.version.split()[0]}, None
    manifest = {
        "schema": "thermobridge.run.v1", "run_id": run_id,
        "timestamp_utc": started.astimezone(timezone.utc).isoformat(),
        "source_commit": state["commit"], "git_dirty": state["dirty"], "source_sha256": source_hash(),
        "input_sha256": {p.resolve().relative_to(ROOT).as_posix(): sha256_file(p) for p in input_paths},
        "seed": seed, "tool_versions": tool_versions,
        "environment_manifest_sha256": environment_hash,
        "command": command, "duration_s": (datetime.now(timezone.utc) - started).total_seconds(),
        "status": status,
        "outputs": {p.resolve().relative_to(ROOT).as_posix(): sha256_file(p) for p in output_paths if p.exists()},
    }
    if extra:
        manifest.update(extra)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
