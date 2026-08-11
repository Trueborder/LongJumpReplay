"""Operator GUI for creating offline LongJumpReplay license keys.

This tool is for the product owner or support team only. Never distribute it
with the customer application: it needs the private signing-key sidecar.
"""

from __future__ import annotations

from datetime import datetime
import re
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Make direct execution (`python tools\license_generator.py`) resolve the
# project package in the same way as the existing command-line admin tool.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.license_admin import create_license, private_key_path


MACHINE_CODE_PATTERN = re.compile(r"^[0-9A-F]{4}(?:-[0-9A-F]{4}){3}$")


def normalize_machine_code(value: str) -> str:
    """Normalize pasted machine-code text to the format used by the app."""
    compact = re.sub(r"[\s-]", "", value.strip()).upper()
    if len(compact) == 16 and re.fullmatch(r"[0-9A-F]+", compact):
        return "-".join(compact[index : index + 4] for index in range(0, 16, 4))
    return value.strip().upper()


def default_license_id() -> str:
    return datetime.now().strftime("LJR-%Y%m%d-%H%M%S")


class LicenseGenerator:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("LongJumpReplay License Generator")
        self.root.minsize(720, 520)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.machine_var = tk.StringVar()
        self.customer_var = tk.StringVar()
        self.license_id_var = tk.StringVar(value=default_license_id())
        self.key_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")

        body = ttk.Frame(root, padding=24)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.rowconfigure(7, weight=1)

        ttk.Label(body, text="LongJumpReplay license generator", style="Title.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(
            body,
            text=(
                "Create a machine-bound offline license. Ask the customer to copy the "
                "machine code shown by their first launch."
            ),
            wraplength=650,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 22))

        self._field(body, 2, "Customer / organization", self.customer_var)
        self._field(body, 3, "Machine code", self.machine_var)
        self._field(body, 4, "License ID", self.license_id_var)

        ttk.Label(body, text="Generated license key").grid(row=5, column=0, columnspan=3, sticky="w", pady=(22, 4))
        ttk.Entry(body, textvariable=self.key_var).grid(row=6, column=0, columnspan=3, sticky="ew")

        buttons = ttk.Frame(body)
        buttons.grid(row=8, column=0, columnspan=3, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Save key…", command=self.save_key).pack(side="right")
        ttk.Button(buttons, text="Copy key", command=self.copy_key).pack(side="right", padx=(0, 8))
        ttk.Button(buttons, text="Generate key", command=self.generate, style="Accent.TButton").pack(
            side="right", padx=(0, 8)
        )
        ttk.Label(body, textvariable=self.status_var, wraplength=650).grid(
            row=9, column=0, columnspan=3, sticky="w", pady=(14, 0)
        )
        ttk.Label(
            body,
            text=(
                "Security: keep this program and .license_private_key.json on your admin PC. "
                "Do not send either file to customers."
            ),
            wraplength=650,
            justify="left",
        ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(26, 0))

        if not private_key_path().exists():
            self.status_var.set(f"Private key not found: {private_key_path()}")

    @staticmethod
    def _field(body: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(body, textvariable=variable).grid(row=row, column=1, columnspan=2, sticky="ew", pady=5)

    def generate(self) -> None:
        machine = normalize_machine_code(self.machine_var.get())
        customer = self.customer_var.get().strip()
        license_id = self.license_id_var.get().strip()
        if not MACHINE_CODE_PATTERN.fullmatch(machine):
            self.status_var.set("Enter a machine code such as D498-C0D1-7C76-26CB.")
            return
        if not customer:
            self.status_var.set("Enter the customer or organization name.")
            return
        if not license_id:
            self.status_var.set("Enter an internal license ID.")
            return
        try:
            self.key_var.set(create_license(machine, customer, license_id))
        except OSError as exc:
            self.status_var.set(f"Could not read the private key: {exc}")
            return
        except (KeyError, TypeError, ValueError) as exc:
            self.status_var.set(f"Could not generate the license: {exc}")
            return
        self.machine_var.set(machine)
        self.status_var.set("License created. Copy the key and send only the key to the customer.")

    def copy_key(self) -> None:
        key = self.key_var.get().strip()
        if not key:
            self.status_var.set("Generate a key first.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(key)
        self.root.update()
        self.status_var.set("License key copied to the clipboard.")

    def save_key(self) -> None:
        key = self.key_var.get().strip()
        if not key:
            self.status_var.set("Generate a key first.")
            return
        target = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save license key",
            defaultextension=".txt",
            filetypes=[("License text", "*.txt"), ("All files", "*.*")],
        )
        if not target:
            return
        try:
            with open(target, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(key + "\n")
        except OSError as exc:
            messagebox.showerror("Save failed", str(exc), parent=self.root)
            return
        self.status_var.set(f"License saved to {target}")


def main() -> int:
    root = tk.Tk()
    try:
        ttk.Style(root).configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        LicenseGenerator(root)
        root.mainloop()
    finally:
        root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
