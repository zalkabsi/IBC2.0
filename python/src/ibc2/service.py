"""Installing ibc2 so it starts by itself: Task Scheduler (Windows), systemd (Linux), launchd (macOS)."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from . import paths

TASK_NAME = "ibc2"
LAUNCHD_LABEL = "io.github.zalkabsi.ibc2"


def _python() -> str:
    exe = Path(sys.executable)
    if os.name == "nt":
        pythonw = exe.with_name("pythonw.exe")  # no console window
        if pythonw.exists():
            return str(pythonw)
    return str(exe)


def windows_task_xml(python: str, home: Path, user: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>ibc2: keeps Interactive Brokers Gateway/TWS logged in</Description></RegistrationInfo>
  <Triggers>
    <LogonTrigger><Enabled>true</Enabled><UserId>{escape(user)}</UserId><Delay>PT30S</Delay></LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author"><UserId>{escape(user)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(python)}</Command>
      <Arguments>-m ibc2 run</Arguments>
      <WorkingDirectory>{escape(str(home))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def systemd_unit(python: str, home: Path) -> str:
    return f"""[Unit]
Description=ibc2: keeps Interactive Brokers Gateway/TWS logged in
After=network-online.target

[Service]
Type=simple
Environment=IBC2_HOME={home}
ExecStart={python} -m ibc2 run
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
"""


def launchd_plist(python: str, home: Path) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{LAUNCHD_LABEL}</string>
  <key>ProgramArguments</key><array><string>{escape(python)}</string><string>-m</string><string>ibc2</string><string>run</string></array>
  <key>EnvironmentVariables</key><dict><key>IBC2_HOME</key><string>{escape(str(home))}</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
"""


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603


def install() -> str:
    system = platform.system()
    python, home = _python(), paths.home()
    if system == "Windows":
        import getpass

        user = f"{os.environ.get('USERDOMAIN', '')}\\{getpass.getuser()}".lstrip("\\")
        xml_path = paths.runtime_dir() / "ibc2-task.xml"
        xml_path.write_text(windows_task_xml(python, home, user), encoding="utf-16")
        r = _run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"])
        xml_path.unlink(missing_ok=True)
        if r.returncode != 0:
            raise RuntimeError(f"schtasks failed: {(r.stderr or r.stdout).strip()}")
        return f"Installed the '{TASK_NAME}' scheduled task: ibc2 starts when you log in to Windows."
    if system == "Darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_text(launchd_plist(python, home), encoding="utf-8")
        _run(["launchctl", "unload", str(plist)])
        r = _run(["launchctl", "load", str(plist)])
        if r.returncode != 0:
            raise RuntimeError(f"launchctl failed: {(r.stderr or r.stdout).strip()}")
        return f"Installed launch agent {plist}"
    unit = Path.home() / ".config" / "systemd" / "user" / "ibc2.service"
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(systemd_unit(python, home), encoding="utf-8")
    for cmd in (["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", "ibc2.service"]):
        r = _run(cmd)
        if r.returncode != 0:
            raise RuntimeError(f"{' '.join(cmd)} failed: {(r.stderr or r.stdout).strip()}")
    return ("Installed and started the systemd user service 'ibc2'. To keep it running when you are logged "
            "out, run: loginctl enable-linger $USER. (Gateway needs a display; on a headless server use the "
            "Docker image instead.)")


def uninstall() -> str:
    system = platform.system()
    if system == "Windows":
        r = _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"])
        return "Removed the scheduled task." if r.returncode == 0 else "No scheduled task was installed."
    if system == "Darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
        _run(["launchctl", "unload", str(plist)])
        plist.unlink(missing_ok=True)
        return "Removed the launch agent."
    _run(["systemctl", "--user", "disable", "--now", "ibc2.service"])
    (Path.home() / ".config" / "systemd" / "user" / "ibc2.service").unlink(missing_ok=True)
    _run(["systemctl", "--user", "daemon-reload"])
    return "Removed the systemd user service."
