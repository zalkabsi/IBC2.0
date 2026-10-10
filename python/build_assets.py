"""Assemble src/ibc2/_ibc (IBC.jar + launch scripts + config template) before building the wheel.

Usage:  python build_assets.py [--jar path/to/IBC.jar]

By default the jar is taken from ../resources/IBC.jar; CI builds a fresh one with
'ant jar' first. The _ibc directory is git-ignored: it is a build product.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESOURCES = HERE.parent / "resources"
TARGET = HERE / "src" / "ibc2" / "_ibc"

# launch scripts for every OS live side by side; the wheel is platform independent
SCRIPTS = ["StartIBC.bat", "DisplayBannerAndLaunch.bat", "getExtraJavaOptions.ps1", "ibcstart.sh",
           "displaybannerandlaunch.sh", "SendIBCCommand.vbs"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", type=Path, default=RESOURCES / "IBC.jar")
    args = ap.parse_args()
    if not args.jar.exists():
        raise SystemExit(f"{args.jar} not found - run 'ant jar' first")

    if TARGET.exists():
        shutil.rmtree(TARGET)
    (TARGET / "scripts").mkdir(parents=True)
    shutil.copy2(args.jar, TARGET / "IBC.jar")
    for name in SCRIPTS:
        src = RESOURCES / "scripts" / name
        if not src.exists():
            continue
        if name.endswith(".sh"):
            # shell scripts must have LF endings or they fail on Linux/macOS, even when this
            # wheel is built from a Windows checkout that converted them to CRLF
            data = src.read_bytes().replace(b"\r\n", b"\n")
            (TARGET / "scripts" / name).write_bytes(data)
        else:
            shutil.copy2(src, TARGET / "scripts" / name)
    for name in ("config.ini", "dialogrules.txt", "version"):
        shutil.copy2(RESOURCES / name, TARGET / name)
    shutil.copy2(RESOURCES.parent / "LICENSE.txt", TARGET / "LICENSE.txt")
    print(f"assembled {TARGET}")


if __name__ == "__main__":
    main()
