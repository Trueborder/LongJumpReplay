from __future__ import annotations

from collections.abc import Callable
import sys
import tkinter as tk


Action = Callable[[], None]
KeyOverride = Callable[[tk.Event], bool]


ONE_SHOT_ACTIONS = {
    "freeze_toggle", "return_live", "previous_attempt", "next_attempt",
    "add_marker", "save_frame", "export_attempt", "toggle_attempts",
    "toggle_timeline", "toggle_live_preview", "toggle_fullscreen",
    "reset_view", "toggle_guide", "decision_valid", "decision_foul",
    "decision_review", "clear_all_recordings", "toggle_comparison",
    "timer_toggle",
}


def hotkey_to_sequence(value: str, release: bool = False) -> str:
    parts = [p for p in value.replace("+", "-").split("-") if p]
    if not parts:
        raise ValueError("Hotkey cannot be empty")
    key = parts[-1]
    modifiers = parts[:-1]
    event = "KeyRelease" if release else "KeyPress"
    prefix = "-".join(modifiers)
    return f"<{prefix + '-' if prefix else ''}{event}-{key}>"


def event_to_hotkey(event: tk.Event) -> str:
    modifiers: list[str] = []
    state = int(event.state)
    if state & 0x0004: modifiers.append("Control")
    if state & 0x0001: modifiers.append("Shift")
    # Tk uses Mod1 (0x0008) for Alt on X11, but that bit represents
    # Num Lock on Windows. Windows reports Alt with its extended 0x20000 bit.
    alt_mask = 0x00020000 if sys.platform == "win32" else 0x0008
    if state & alt_mask: modifiers.append("Alt")
    key = str(event.keysym)
    if key in {"Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R"}:
        return ""
    return "-".join([*modifiers, key])


class HotkeyRouter:
    """Application-wide hotkeys that take priority over focused buttons."""

    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self.bindtag = f"LongJumpReplayHotkeys{root.winfo_id()}"
        self._held: set[str] = set()
        self._sequences: list[str] = []
        self._key_override: KeyOverride | None = None

    def attach_tree(self, widget: tk.Misc | None = None) -> None:
        current = widget or self.root
        tags = current.bindtags()
        if self.bindtag not in tags:
            current.bindtags((self.bindtag, *tags))
        for child in current.winfo_children():
            self.attach_tree(child)

    def install(
        self,
        bindings: dict[str, str],
        actions: dict[str, Action],
        key_override: KeyOverride | None = None,
    ) -> None:
        self.clear()
        self._key_override = key_override
        for action_name, hotkey in bindings.items():
            action = actions.get(action_name)
            if not hotkey or action is None:
                continue
            press = hotkey_to_sequence(hotkey)
            if action_name in ONE_SHOT_ACTIONS:
                release = hotkey_to_sequence(hotkey, release=True)
                token = f"{action_name}:{hotkey}"
                def on_press(_event, token=token, action=action):
                    if self._handle_override(_event):
                        return "break"
                    if token not in self._held:
                        self._held.add(token); action()
                    return "break"
                def on_release(_event, token=token):
                    self._held.discard(token)
                    return "break"
                self.root.bind_class(self.bindtag, press, on_press)
                self.root.bind_class(self.bindtag, release, on_release)
                self._sequences.extend([press, release])
            else:
                def handler(_event, action=action):
                    if self._handle_override(_event):
                        return "break"
                    action(); return "break"
                self.root.bind_class(self.bindtag, press, handler)
                self._sequences.append(press)
        if key_override is not None:
            self.root.bind_class(self.bindtag, "<KeyPress>", self._generic_keypress)
            self._sequences.append("<KeyPress>")

    def _handle_override(self, event: tk.Event) -> bool:
        return bool(self._key_override and self._key_override(event))

    def _generic_keypress(self, event: tk.Event) -> str | None:
        return "break" if self._handle_override(event) else None

    def clear(self) -> None:
        for sequence in self._sequences:
            try:
                self.root.unbind_class(self.bindtag, sequence)
            except tk.TclError:
                pass
        self._held.clear()
        self._sequences.clear()
        self._key_override = None

    def close(self) -> None:
        self.clear()
