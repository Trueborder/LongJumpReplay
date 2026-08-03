from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


DEFAULT_HOTKEYS = {
    "freeze_toggle": "space",
    "return_live": "Home",
    "previous_frame": "Left",
    "next_frame": "Right",
    "previous_attempt": "Control-Prior",
    "next_attempt": "Control-Next",
    "previous_athlete": "Alt-Left",
    "next_athlete": "Alt-Right",
    "decision_not_decided": "n",
    "decision_valid": "v",
    "decision_foul": "f",
    "decision_review": "u",
    "mark_passed": "s",
    "add_marker": "m",
    "save_frame": "p",
    "export_attempt": "e",
    "clear_all_recordings": "Control-Delete",
    "toggle_attempts": "a",
    "toggle_competition_board": "b",
    "toggle_timeline": "t",
    "toggle_live_preview": "l",
    "toggle_fullscreen": "F11",
    "reset_view": "r",
    "toggle_guide": "g",
    "toggle_comparison": "c",
    "start_competition_wizard": "Control-n",
}


@dataclass(slots=True)
class GeneralConfig:
    language: str = "en"  # en | cs
    confirm_destructive_actions: bool = True
    show_tooltips: bool = True


@dataclass(slots=True)
class CameraConfig:
    source_type: str = "camera"  # camera | synthetic | file
    device_index: int = 0
    file_path: str = ""
    width: int = 1280
    height: int = 720
    fps: float = 120.0
    fourcc: str = "MJPG"
    backend: str = "DSHOW"  # DSHOW | MSMF | ANY
    buffer_size: int = 1
    loop_file: bool = True
    reconnect_seconds: float = 2.0


@dataclass(slots=True)
class BufferConfig:
    duration_seconds: float = 30.0
    jpeg_quality: int = 82
    encoder_queue_size: int = 128
    max_memory_mb: int = 4096
    store_every_nth_frame: int = 1


@dataclass(slots=True)
class AttemptsConfig:
    pre_seconds: float = 30.0
    post_seconds: float = 10.0
    retention_minutes: float = 10.0
    max_attempts: int = 24
    max_cache_gb: float = 4.0
    cache_directory: str = "cache"
    temp_codec: str = "mp4v"
    auto_select_new: bool = True


@dataclass(slots=True)
class CompetitionConfig:
    enabled: bool = True
    decision_controls_enabled: bool = True
    require_decision_before_continue: bool = False
    default_decision: str = "Not decided"
    auto_advance_on_attempt_complete: bool = True
    boys_enabled: bool = True
    girls_enabled: bool = True
    boys_competitors: int = 8
    girls_competitors: int = 8
    default_attempts_per_competitor: int = 3
    attempts_overrides: dict[str, int] = field(default_factory=dict)
    active_group: str = "Boys"
    current_competitor_by_group: dict[str, int] = field(default_factory=lambda: {"Boys": 1, "Girls": 1})
    auto_advance_after_decision: bool = False
    auto_save_evidence: bool = True
    auto_return_live: bool = False
    auto_return_delay_seconds: float = 1.5
    show_competitor_selector: bool = True
    show_competition_board: bool = True
    show_state_banner: bool = False
    next_athlete_overlay: bool = False

    # Final round. Qualification ranking is external to this camera tool, so
    # finalists are selected explicitly by the operator.
    final_round_enabled: bool = False
    finalists_count: int = 8
    final_attempts: int = 3
    final_order: str = "reverse"  # same | reverse | manual
    finalist_numbers_by_group: dict[str, list[int]] = field(default_factory=lambda: {"Boys": [], "Girls": []})
    final_round_started_by_group: dict[str, bool] = field(default_factory=lambda: {"Boys": False, "Girls": False})

    # Optional operator aids.
    enable_special_results: bool = False  # Passed / DNS / Withdrawn / Reattempt
    recovery_prompt_enabled: bool = False
    event_export_enabled: bool = False
    keyboard_competition_controls: bool = False
    operator_mode_enabled: bool = False
    camera_diagnostic_enabled: bool = False
    wizard_button_visible: bool = True
    clear_temp_on_new_competition: bool = False


@dataclass(slots=True)
class DisplayConfig:
    refresh_hz: int = 60  # retained for compatibility; performance.preview_refresh_hz is authoritative
    fullscreen: bool = False
    theme: str = "system"  # system | dark | light
    layout: str = "replay_pip"  # replay_pip | side_by_side | replay_only | live_only | comparison | board_detail
    show_attempts_panel: bool = True
    show_timeline: bool = True
    show_status_bar: bool = True
    show_live_preview: bool = True
    show_decision_controls: bool = True
    show_capture_warnings: bool = True
    show_takeoff_assist_badge: bool = True
    attempts_panel_width: int = 360
    timeline_height: int = 138
    guide_enabled: bool = True
    guide_x_ratio: float = 0.5
    guide_y_ratio: float = 0.5
    guide_angle_deg: float = 0.0
    guide_width_px: int = 2
    board_roi_enabled: bool = True
    board_roi_x: float = 0.35
    board_roi_y: float = 0.35
    board_roi_width: float = 0.30
    board_roi_height: float = 0.45
    board_roi_visible: bool = False
    comparison_enabled: bool = True
    comparison_offset_frames: int = 1
    remember_geometry: bool = True
    window_geometry: str = "1360x820"


@dataclass(slots=True)
class PerformanceConfig:
    preset: str = "balanced"  # quiet | balanced | high | evidence | custom
    preview_refresh_hz: int = 60
    timeline_refresh_hz: int = 30
    status_refresh_hz: int = 4
    attempts_refresh_hz: int = 3
    preview_scale: float = 1.0
    pause_hidden_panels: bool = True
    reduce_when_minimized: bool = True
    adaptive_enabled: bool = False
    menu_throttle_enabled: bool = True


PERFORMANCE_PRESETS: dict[str, dict[str, Any]] = {
    "quiet": {
        "preview_refresh_hz": 24,
        "timeline_refresh_hz": 15,
        "status_refresh_hz": 2,
        "attempts_refresh_hz": 2,
        "preview_scale": 0.75,
        "pause_hidden_panels": True,
        "reduce_when_minimized": True,
        "adaptive_enabled": True,
        "assist_width": 160,
    },
    "balanced": {
        "preview_refresh_hz": 60,
        "timeline_refresh_hz": 30,
        "status_refresh_hz": 4,
        "attempts_refresh_hz": 3,
        "preview_scale": 1.0,
        "pause_hidden_panels": True,
        "reduce_when_minimized": True,
        "adaptive_enabled": False,
        "assist_width": 240,
    },
    "high": {
        "preview_refresh_hz": 90,
        "timeline_refresh_hz": 45,
        "status_refresh_hz": 6,
        "attempts_refresh_hz": 4,
        "preview_scale": 1.0,
        "pause_hidden_panels": True,
        "reduce_when_minimized": True,
        "adaptive_enabled": False,
        "assist_width": 360,
    },
    "evidence": {
        "preview_refresh_hz": 60,
        "timeline_refresh_hz": 30,
        "status_refresh_hz": 4,
        "attempts_refresh_hz": 3,
        "preview_scale": 1.0,
        "pause_hidden_panels": True,
        "reduce_when_minimized": True,
        "adaptive_enabled": False,
        "assist_width": 480,
    },
}


@dataclass(slots=True)
class TimelineConfig:
    detail_window_seconds: float = 2.0
    min_detail_seconds: float = 0.1
    max_detail_seconds: float = 60.0
    show_frame_ticks: bool = True
    snap_to_frames: bool = True


@dataclass(slots=True)
class TakeoffAssistConfig:
    enabled: bool = False
    auto_seek_after_freeze: bool = True
    quick_review_enabled: bool = False
    quick_review_speed: float = 0.25
    analysis_seconds_before_freeze: float = 2.5
    analysis_seconds_after_freeze: float = 0.25
    seek_lead_frames: int = 0
    minimum_confidence: float = 0.18
    downscale_width: int = 240


@dataclass(slots=True)
class ExportConfig:
    directory: str = "exports"
    evidence_directory: str = "evidence"
    codec: str = "mp4v"
    target_fps: float = 0.0
    write_sidecar_json: bool = True
    evidence_include_overlay: bool = True
    evidence_save_raw: bool = True


@dataclass(slots=True)
class HotkeyConfig:
    enabled: bool = True
    bindings: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_HOTKEYS))


@dataclass(slots=True)
class ShuttleConfig:
    enabled: bool = True
    direct_hid: bool = True
    vendor_id: int = 0x0B33
    product_ids: list[int] = field(default_factory=lambda: [0x0020, 0x0010, 0x0030])
    poll_timeout_ms: int = 100
    jog_action: str = "step_frame"
    shuttle_action: str = "select_attempt"
    shuttle_debounce_ms: int = 250
    button_map: dict[str, int] = field(
        default_factory=lambda: {
            "freeze_toggle": 1,
            "return_live": 2,
            "decision_valid": 3,
            "decision_foul": 4,
            "decision_review": 5,
        }
    )
    keyboard_fallback: bool = True


@dataclass(slots=True)
class AppConfig:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    buffer: BufferConfig = field(default_factory=BufferConfig)
    attempts: AttemptsConfig = field(default_factory=AttemptsConfig)
    competition: CompetitionConfig = field(default_factory=CompetitionConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    timeline: TimelineConfig = field(default_factory=TimelineConfig)
    takeoff_assist: TakeoffAssistConfig = field(default_factory=TakeoffAssistConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    hotkeys: HotkeyConfig = field(default_factory=HotkeyConfig)
    shuttle: ShuttleConfig = field(default_factory=ShuttleConfig)

    def validate(self) -> None:
        if self.general.language not in {"en", "cs"}:
            raise ValueError("general.language must be en or cs")
        if self.camera.source_type not in {"camera", "synthetic", "file"}:
            raise ValueError("camera.source_type must be camera, synthetic, or file")
        if self.camera.width <= 0 or self.camera.height <= 0:
            raise ValueError("Camera dimensions must be positive")
        if not 1 <= self.camera.fps <= 1000:
            raise ValueError("camera.fps must be between 1 and 1000")
        if len(self.camera.fourcc) != 4:
            raise ValueError("camera.fourcc must contain exactly four characters")
        if not 1 <= self.buffer.duration_seconds <= 600:
            raise ValueError("buffer.duration_seconds must be between 1 and 600")
        if not 1 <= self.buffer.jpeg_quality <= 100:
            raise ValueError("buffer.jpeg_quality must be between 1 and 100")
        if self.buffer.encoder_queue_size < 2:
            raise ValueError("buffer.encoder_queue_size must be at least 2")
        if self.buffer.max_memory_mb < 128:
            raise ValueError("buffer.max_memory_mb must be at least 128")
        if self.attempts.pre_seconds < 0 or self.attempts.post_seconds < 0:
            raise ValueError("Attempt pre/post roll cannot be negative")
        if self.attempts.retention_minutes < 0.5:
            raise ValueError("Attempt retention must be at least 0.5 minutes")
        if not 1 <= self.attempts.max_attempts <= 500:
            raise ValueError("attempts.max_attempts must be between 1 and 500")
        if self.attempts.max_cache_gb < 0.1:
            raise ValueError("attempts.max_cache_gb must be at least 0.1")
        if len(self.attempts.temp_codec) != 4 or len(self.export.codec) != 4:
            raise ValueError("Video codecs must contain exactly four characters")
        c = self.competition
        if not 0 <= c.boys_competitors <= 200 or not 0 <= c.girls_competitors <= 200:
            raise ValueError("Competitor counts must be between 0 and 200")
        if not 1 <= c.default_attempts_per_competitor <= 20:
            raise ValueError("Attempts per competitor must be between 1 and 20")
        if not 1 <= c.final_attempts <= 20:
            raise ValueError("Final attempts must be between 1 and 20")
        if not 1 <= c.finalists_count <= 200:
            raise ValueError("Finalists count must be between 1 and 200")
        if c.final_order not in {"same", "reverse", "manual"}:
            raise ValueError("Unsupported final order")
        if c.active_group not in {"Boys", "Girls"}:
            raise ValueError("competition.active_group must be Boys or Girls")
        if not 0 <= c.auto_return_delay_seconds <= 30:
            raise ValueError("Auto-return delay must be between 0 and 30 seconds")
        for key, value in c.attempts_overrides.items():
            if ":" not in str(key) or not 1 <= int(value) <= 20:
                raise ValueError("Invalid per-athlete attempts override")
        for group, values in c.finalist_numbers_by_group.items():
            if group not in {"Boys", "Girls"} or any(int(v) < 1 for v in values):
                raise ValueError("Invalid finalist list")
        if self.display.theme not in {"system", "dark", "light"}:
            raise ValueError("display.theme must be system, dark, or light")
        if self.display.layout not in {"replay_pip", "side_by_side", "replay_only", "live_only", "comparison", "board_detail"}:
            raise ValueError("Unsupported display.layout")
        if not 5 <= self.display.refresh_hz <= 240:
            raise ValueError("display.refresh_hz must be between 5 and 240")
        p = self.performance
        if p.preset not in {"quiet", "balanced", "high", "evidence", "custom"}:
            raise ValueError("Unsupported performance preset")
        if not 5 <= p.preview_refresh_hz <= 240 or not 5 <= p.timeline_refresh_hz <= 120:
            raise ValueError("Performance refresh rates are outside supported limits")
        if not 1 <= p.status_refresh_hz <= 30 or not 1 <= p.attempts_refresh_hz <= 30:
            raise ValueError("Status refresh rates are outside supported limits")
        if not 0.25 <= p.preview_scale <= 1.0:
            raise ValueError("Preview scale must be between 0.25 and 1.0")
        if not 0 <= self.display.guide_x_ratio <= 1 or not 0 <= self.display.guide_y_ratio <= 1:
            raise ValueError("Guide position must be within the image")
        if not -89.9 <= self.display.guide_angle_deg <= 89.9:
            raise ValueError("Guide angle must be between -89.9 and 89.9 degrees")
        for value in (self.display.board_roi_x, self.display.board_roi_y, self.display.board_roi_width, self.display.board_roi_height):
            if not 0 <= value <= 1:
                raise ValueError("Board ROI values must be between 0 and 1")
        if self.display.board_roi_width <= 0 or self.display.board_roi_height <= 0:
            raise ValueError("Board ROI must have a positive size")
        if self.display.board_roi_x + self.display.board_roi_width > 1.0001 or self.display.board_roi_y + self.display.board_roi_height > 1.0001:
            raise ValueError("Board ROI must fit inside the image")
        if self.timeline.min_detail_seconds <= 0:
            raise ValueError("timeline.min_detail_seconds must be positive")
        if self.timeline.max_detail_seconds < self.timeline.min_detail_seconds:
            raise ValueError("timeline.max_detail_seconds must be >= minimum")
        if self.timeline.detail_window_seconds <= 0:
            raise ValueError("timeline.detail_window_seconds must be positive")
        a = self.takeoff_assist
        if a.analysis_seconds_before_freeze <= 0 or a.analysis_seconds_after_freeze < 0:
            raise ValueError("Take-off analysis window is invalid")
        if not 0 <= a.minimum_confidence <= 1:
            raise ValueError("Take-off confidence must be between 0 and 1")
        if not 80 <= a.downscale_width <= 1280:
            raise ValueError("Take-off analysis width must be between 80 and 1280")
        if not isinstance(self.hotkeys.bindings, dict):
            raise ValueError("hotkeys.bindings must be an object")


def apply_performance_preset(config: AppConfig, preset: str) -> None:
    if preset not in PERFORMANCE_PRESETS:
        if preset != "custom":
            raise ValueError(f"Unknown performance preset: {preset}")
        config.performance.preset = "custom"
        return
    values = PERFORMANCE_PRESETS[preset]
    p = config.performance
    p.preset = preset
    for key in ("preview_refresh_hz", "timeline_refresh_hz", "status_refresh_hz", "attempts_refresh_hz", "preview_scale", "pause_hidden_panels", "reduce_when_minimized", "adaptive_enabled"):
        setattr(p, key, values[key])
    config.display.refresh_hz = p.preview_refresh_hz
    # Performance presets reduce presentation/analysis workload. They do not
    # silently change the quality of frames retained as evidence. Buffer JPEG
    # quality remains an explicit Advanced/Performance choice.
    config.takeoff_assist.downscale_width = int(values["assist_width"])


def _deep_update(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def config_from_dict(data: dict[str, Any]) -> AppConfig:
    merged = _deep_update(asdict(AppConfig()), data)
    config = AppConfig(
        general=GeneralConfig(**merged["general"]),
        camera=CameraConfig(**merged["camera"]),
        buffer=BufferConfig(**merged["buffer"]),
        attempts=AttemptsConfig(**merged["attempts"]),
        competition=CompetitionConfig(**merged["competition"]),
        display=DisplayConfig(**merged["display"]),
        performance=PerformanceConfig(**merged["performance"]),
        timeline=TimelineConfig(**merged["timeline"]),
        takeoff_assist=TakeoffAssistConfig(**merged["takeoff_assist"]),
        export=ExportConfig(**merged["export"]),
        hotkeys=HotkeyConfig(**merged["hotkeys"]),
        shuttle=ShuttleConfig(**merged["shuttle"]),
    )
    # Migrate pre-2.3 configs which only had display.refresh_hz.
    if "performance" not in data:
        config.performance.preview_refresh_hz = config.display.refresh_hz
    config.hotkeys.bindings = {**DEFAULT_HOTKEYS, **config.hotkeys.bindings}
    config.validate()
    return config


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    if not path.exists():
        config = AppConfig()
        save_config(config, path)
        return config
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("The root of config.json must be a JSON object")
    return config_from_dict(data)


def save_config(config: AppConfig, path: str | Path) -> None:
    config.validate()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as file:
        json.dump(asdict(config), file, ensure_ascii=False, indent=2)
        file.write("\n")
    temp.replace(path)
