from __future__ import annotations

import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk
import winreg


APP_NAME = "Long Jump Replay"
APP_VERSION = "2.3"
INSTALL_DIR = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "LongJumpReplay"
START_MENU_DIR = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\LongJumpReplay"


def payload_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / "payload" / name


def installer_path() -> Path:
    return Path(sys.executable).resolve()


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def relaunch_as_admin() -> bool:
    arguments = subprocess.list2cmdline(sys.argv[1:])
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(installer_path()), arguments, None, 1)
    return result > 32


def create_shortcut(path: Path, target: Path, arguments: str = "", description: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$shortcut = $shell.CreateShortcut('{path}'); "
        f"$shortcut.TargetPath = '{target}'; "
        f"$shortcut.Arguments = '{arguments}'; "
        f"$shortcut.WorkingDirectory = '{target.parent}'; "
        f"$shortcut.Description = '{description}'; "
        "$shortcut.Save()"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], check=True, creationflags=subprocess.CREATE_NO_WINDOW)


def register_uninstaller(uninstaller: Path) -> None:
    with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY) as key:
        values = {
            "DisplayName": APP_NAME,
            "DisplayVersion": APP_VERSION,
            "Publisher": "LongJumpReplay",
            "InstallLocation": str(INSTALL_DIR),
            "UninstallString": f'"{uninstaller}" --uninstall',
            "NoModify": 1,
            "NoRepair": 1,
        }
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ, value)


def install() -> None:
    executable = payload_path("LongJumpReplay.exe")
    if not executable.exists():
        raise FileNotFoundError("The application payload is missing from this installer.")
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(executable, INSTALL_DIR / "LongJumpReplay.exe")
    for name in ("README_SHARE.txt", "THIRD_PARTY_NOTICES.txt"):
        source = payload_path(name)
        if source.exists():
            shutil.copy2(source, INSTALL_DIR / name)
    uninstaller = INSTALL_DIR / "Uninstall Long Jump Replay.exe"
    shutil.copy2(installer_path(), uninstaller)
    start_menu_shortcut = START_MENU_DIR / "Long Jump Replay.lnk"
    create_shortcut(start_menu_shortcut, INSTALL_DIR / "LongJumpReplay.exe", description="Open the Long Jump Replay judge station")
    desktop_shortcut = Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop" / "Long Jump Replay.lnk"
    create_shortcut(desktop_shortcut, INSTALL_DIR / "LongJumpReplay.exe", description="Open the Long Jump Replay judge station")
    register_uninstaller(uninstaller)


def uninstall() -> None:
    for shortcut in (START_MENU_DIR / "Long Jump Replay.lnk", Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop" / "Long Jump Replay.lnk"):
        try:
            shortcut.unlink()
        except FileNotFoundError:
            pass
    try:
        START_MENU_DIR.rmdir()
    except OSError:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, UNINSTALL_KEY)
    except FileNotFoundError:
        pass
    command = f"Start-Sleep -Milliseconds 700; Remove-Item -LiteralPath '{INSTALL_DIR}' -Recurse -Force -ErrorAction SilentlyContinue"
    subprocess.Popen(["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-Command", command], creationflags=subprocess.CREATE_NO_WINDOW)


def show_window() -> None:
    root = tk.Tk()
    root.title(f"{APP_NAME} {APP_VERSION} Setup")
    root.resizable(False, False)
    root.geometry("540x340")
    frame = ttk.Frame(root, padding=28)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="LONG JUMP REPLAY", font=("Segoe UI", 18, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Windows installer", foreground="#4f8cff").pack(anchor="w", pady=(2, 18))
    ttk.Label(frame, text="Install the judge station for all users on this computer.\nThe application will be placed in Program Files.", wraplength=470, justify="left").pack(anchor="w")
    ttk.Label(frame, text=str(INSTALL_DIR), font=("Consolas", 9)).pack(anchor="w", pady=(16, 18))
    status = tk.StringVar(value="Ready to install")
    ttk.Label(frame, textvariable=status).pack(anchor="w")
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", side="bottom", pady=(20, 0))

    def run_install() -> None:
        try:
            install()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Installation failed:\n\n{exc}", parent=root)
            return
        status.set("Installation complete")
        messagebox.showinfo(APP_NAME, "Long Jump Replay was installed. You can start it from the Windows Start Menu.", parent=root)
        root.destroy()

    ttk.Button(buttons, text="Cancel", command=root.destroy).pack(side="right")
    ttk.Button(buttons, text="Install", command=run_install).pack(side="right", padx=(0, 8))
    root.mainloop()


def main() -> int:
    if "--self-test" in sys.argv:
        return 0 if payload_path("LongJumpReplay.exe").exists() else 10
    if not is_admin():
        if relaunch_as_admin():
            return 0
        return 1
    if "--uninstall" in sys.argv:
        uninstall()
        return 0
    show_window()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
