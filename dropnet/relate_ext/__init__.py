"""Package and install Dropnet as a Relate command extension (`relate run dropnet-ftc`).

Relate installs one executable per extension, so the package is a single file: the Python child on
macOS/Linux, and on Windows the same code behind a one-line batch header (`python -x` skips it).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHILD = Path(__file__).with_name("dropnet_ftc.py")
NAME = "dropnet-ftc"


def manifest(executable: str) -> dict:
    return {"kind": "command", "name": NAME, "version": "0.1.0", "protocol": "2025-06-18",
            "flags": [{"kind": "string", "name": "path", "default": ""},
                      {"kind": "integer", "name": "min_numbers", "default": 5}],
            "commit": "per-batch", "executable": executable}


def package(out: Path, windows: bool | None = None) -> Path:
    windows = os.name == "nt" if windows is None else windows
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    code = CHILD.read_text(encoding="utf-8")
    if windows:
        exe = "dropnet-ftc.cmd"
        header = f'@"{sys.executable}" -x "%~f0" %* & exit /b %errorlevel%\r\n'
        (out / exe).write_text(header + code, encoding="utf-8", newline="")
    else:
        exe = "dropnet_ftc.py"
        (out / exe).write_text(f"#!{sys.executable}\n" + code, encoding="utf-8")
        (out / exe).chmod(0o755)
    (out / "extension.json").write_text(json.dumps(manifest(exe), indent=2), encoding="utf-8")
    return out


def install(cli: str, env: dict | None = None) -> str:
    tmp = Path(tempfile.mkdtemp(prefix="dropnet-ext-"))
    try:
        pkg = package(tmp / NAME)
        r = subprocess.run([cli, "extension", "install", NAME, "--from", str(pkg), "--force"],
                           capture_output=True, text=True, env=env)
        if r.returncode:
            raise RuntimeError(r.stderr.strip() or r.stdout.strip())
        return r.stdout.strip()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
