"""Finding TWS / IB Gateway installations and a Java runtime."""

from __future__ import annotations

import os
import platform
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Install:
    app: str  # "gateway" or "tws"
    version: str  # major version, e.g. "1043"
    root: Path  # the folder that contains the version folder (what IBC calls TwsPath)
    program_dir: Path


def default_roots() -> list[Path]:
    override = os.environ.get("IBC2_TWS_PATH")
    system = platform.system()
    roots: list[Path] = []
    if override:
        roots.append(Path(override))
    if system == "Windows":
        drive = os.environ.get("SYSTEMDRIVE", "C:")
        roots += [Path(drive + "\\Jts"), Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Jts"]
    elif system == "Darwin":
        roots += [Path.home() / "Applications", Path("/Applications")]
    else:
        roots += [Path.home() / "Jts", Path("/opt/ibgateway"), Path("/opt/Jts")]
    unique: list[Path] = []
    for r in roots:
        if r.exists() and r not in unique:
            unique.append(r)
    return unique


_VERSION = re.compile(r"^\d{3,5}$")


def find_installs(roots: list[Path] | None = None) -> list[Install]:
    """Offline (not self-updating) installs, newest first. A ``jars`` folder must exist: IBC needs it."""
    found: list[Install] = []
    for root in roots if roots is not None else default_roots():
        if not root.exists():
            continue
        if platform.system() == "Darwin":
            for p in root.glob("Trader Workstation *"):
                v = p.name.rsplit(" ", 1)[-1]
                if _VERSION.match(v):
                    found.append(Install("tws", v, root, p))
            for p in root.glob("IB Gateway *"):
                v = p.name.rsplit(" ", 1)[-1]
                if _VERSION.match(v):
                    found.append(Install("gateway", v, root, p))
            continue
        for p in root.iterdir():
            if p.is_dir() and _VERSION.match(p.name) and (p / "jars").is_dir():
                found.append(Install("tws", p.name, root, p))
        gw = root / "ibgateway"
        if gw.is_dir():
            for p in gw.iterdir():
                if p.is_dir() and _VERSION.match(p.name) and (p / "jars").is_dir():
                    found.append(Install("gateway", p.name, root, p))
    return sorted(found, key=lambda i: int(i.version), reverse=True)


def pick_install(installs: list[Install], app: str = "", version: str = "") -> Install | None:
    for i in installs:
        if (not app or i.app == app) and (not version or i.version == version):
            return i
    return None


def find_java(install: Install | None = None) -> Path | None:
    """Path of a ``java`` executable: the one bundled with TWS/Gateway first, else the system one."""
    exe = "java.exe" if os.name == "nt" else "java"
    if install is not None:
        for sub in ("jre/bin", "jre64/bin", "../jre/bin"):
            cand = (install.program_dir / sub / exe).resolve()
            if cand.exists():
                return cand
        # install4j records the JRE it uses
        cfg_dir = install.program_dir / ".install4j"
        for cfg in cfg_dir.glob("*jre.cfg") if cfg_dir.is_dir() else []:
            try:
                line = cfg.read_text(encoding="utf-8").splitlines()[0].strip()
            except (OSError, IndexError):
                continue
            cand = Path(line) / "bin" / exe
            if cand.exists():
                return cand
    found = shutil.which("java")
    return Path(found) if found else None
