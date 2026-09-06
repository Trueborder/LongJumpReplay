from __future__ import annotations

from dataclasses import dataclass
from queue import Queue
from threading import Event, Thread
import time

from .config import ShuttleConfig

try:
    import hid  # type: ignore
except Exception:  # pragma: no cover - optional on non-Windows test systems
    hid = None


@dataclass(frozen=True, slots=True)
class ShuttleDevice:
    vendor_id: int
    product_id: int
    path: bytes | str
    product: str


BUTTON_MASKS = {
    0x0020: [0x0010, 0x0020, 0x0040, 0x0080, 0x0100],  # ShuttleXpress
    0x0010: [0x0001, 0x0002, 0x0004, 0x0008, 0x0010, 0x0020, 0x0040, 0x0080, 0x0100, 0x0200, 0x0400, 0x0800, 0x1000],
    0x0030: [0x0001, 0x0002, 0x0004, 0x0008, 0x0010, 0x0020, 0x0040, 0x0080, 0x0100, 0x0200, 0x0400, 0x0800, 0x1000, 0x2000, 0x4000],
}


def parse_shuttle_packet(data: bytes | list[int], product_id: int, previous_jog: int = 0) -> tuple[int, int, list[int]]:
    raw = bytes(data)
    if len(raw) == 6 and raw[0] == 0:
        raw = raw[1:]
    if len(raw) != 5:
        raise ValueError(f"Unexpected Shuttle packet length: {len(raw)}")
    shuttle = int.from_bytes(raw[0:1], "little", signed=True)
    jog = raw[1]
    buttons_raw = int.from_bytes(raw[3:5], "little", signed=False)
    masks = BUTTON_MASKS.get(product_id, BUTTON_MASKS[0x0020])
    pressed = [index + 1 for index, mask in enumerate(masks) if buttons_raw & mask]
    return shuttle, jog, pressed


def jog_direction(previous: int, current: int) -> int:
    if previous == current:
        return 0
    if (previous == 0xFF and current == 0) or (not (previous == 0 and current == 0xFF) and previous < current):
        return 1
    return -1


def list_shuttle_devices(config: ShuttleConfig) -> list[ShuttleDevice]:
    if hid is None:
        return []
    devices = []
    for info in hid.enumerate(config.vendor_id, 0):
        pid = int(info.get("product_id", 0))
        if pid not in config.product_ids:
            continue
        devices.append(ShuttleDevice(config.vendor_id, pid, info["path"], str(info.get("product_string") or "Contour Shuttle")))
    return devices


class ShuttleHIDPoller:
    """Direct ShuttleXpress/Pro input with no Contour profile required."""

    def __init__(self, config: ShuttleConfig, action_queue: Queue[tuple[str, int]]) -> None:
        self.config = config
        self.action_queue = action_queue
        self._stop = Event()
        self._thread: Thread | None = None
        self.status = "Disabled"
        self.last_shuttle = 0
        self.last_jog = 0
        self.last_buttons: set[int] = set()
        self.device_name = ""

    def start(self) -> None:
        if not self.config.enabled:
            self.status = "Disabled in settings"
            return
        if not self.config.direct_hid:
            self.status = "Keyboard-driver mode"
            return
        if hid is None:
            self.status = "Direct HID unavailable; keyboard fallback active"
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._loop, name="shuttle-hid", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 1.0) -> list[str]:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout)
        return [self._thread.name] if self._thread and self._thread.is_alive() else []

    def _loop(self) -> None:
        while not self._stop.is_set():
            devices = list_shuttle_devices(self.config)
            if not devices:
                self.status = "Shuttle not connected · keyboard fallback ready"
                self._stop.wait(1.0)
                continue
            device_info = devices[0]
            device = None
            try:
                device = hid.device()
                device.open_path(device_info.path)
                device.set_nonblocking(False)
                self.device_name = device_info.product
                self.status = f"Connected: {self.device_name}"
                self._read_loop(device, device_info.product_id)
            except Exception as exc:
                self.status = f"Direct HID unavailable ({exc}) · keyboard fallback ready"
                self._stop.wait(1.0)
            finally:
                if device is not None:
                    try: device.close()
                    except Exception: pass

    def _read_loop(self, device, product_id: int) -> None:
        previous_jog = 0
        previous_buttons: set[int] = set()
        shuttle_armed = True
        last_attempt_switch = 0.0
        button_actions = {button: action for action, button in self.config.button_map.items()}
        while not self._stop.is_set():
            data = device.read(6, self.config.poll_timeout_ms)
            if not data:
                continue
            shuttle, jog, buttons = parse_shuttle_packet(data, product_id, previous_jog)
            self.last_shuttle, self.last_jog, self.last_buttons = shuttle, jog, set(buttons)

            direction = jog_direction(previous_jog, jog)
            if direction and self.config.jog_action == "step_frame":
                self.action_queue.put(("step_frame", direction))
            previous_jog = jog

            now = time.perf_counter()
            if shuttle == 0:
                shuttle_armed = True
            elif shuttle_armed and self.config.shuttle_action == "select_attempt":
                if (now - last_attempt_switch) * 1000 >= self.config.shuttle_debounce_ms:
                    self.action_queue.put(("select_attempt", 1 if shuttle > 0 else -1))
                    last_attempt_switch = now
                    shuttle_armed = False

            current_buttons = set(buttons)
            for pressed in current_buttons - previous_buttons:
                action = button_actions.get(pressed)
                if action:
                    self.action_queue.put((action, 1))
            for released in previous_buttons - current_buttons:
                action = button_actions.get(released)
                if action == "hold_playback":
                    self.action_queue.put((action, 0))
            previous_buttons = current_buttons
