from __future__ import annotations

import csv
from copy import deepcopy
import json
import logging
import math
import os
import shutil
import subprocess
import sys
import zipfile
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread
import time
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageTk

from .adjudication import (
    AdjudicationSessionStore,
    BoardReferenceState,
    DurabilityError,
    parse_distance_centimetres,
    parse_wind_metres_per_second,
)
from . import VERSION_SHORT, __version__
from .activation import authorization_permits, current_authorization
from .attempts import AttemptManager
from .board_calibration_wizard import BoardCalibrationWizard
from .athlete_timer import AthleteTimerController, AthleteTimerState, format_countdown, format_countdown_tenths
from .capture import CaptureEngine, OpenCVCameraSource
from .camera_devices import enumerate_camera_devices
from .competition import CompetitionSession, RosterAssignment
from .competition_board import CompetitionBoard
from .competition_setup import RecordingDisposition, WizardReadiness, merge_competition_setup
from .competition_wizard import CompetitionWizard
from .competition_io import CsvExportAdapter, JsonExportAdapter, adapter_for_path
from .config import (
    MAX_TIMELINE_HEIGHT,
    MIN_TIMELINE_HEIGHT,
    AppConfig,
    CompetitionConfig,
    clamp_display_panel_sizes,
    save_config,
)
from .i18n import Translator
from .exporter import save_bgr_png
from .hotkeys import HotkeyRouter
from .models import AttemptDecision, AttemptSession, AttemptState, TimelineModel
from .playback import PlaybackController, PlaybackMode
from .progress import ProgressState, StartupProgressEvent
from .portable_paths import app_data_paths, writable_data_directory
from .recording_thumbnails import RecordingThumbnailWorker
from .ring_buffer import TimeRingBuffer
from .runtime_diagnostics import RuntimeTelemetry, log_event
from .settings_dialog import SettingsDialog
from .shuttle_hid import ShuttleHIDPoller, list_shuttle_devices
from .takeoff_assist import detect_takeoff_candidate
from .top_view_projection import (
    ProjectionCalibration,
    ProjectionCandidate,
    ProjectionProgressDialog,
    TopViewProjectionWindow,
    board_search_roi,
    calibration_matches,
    consecutive_candidate_indices,
    filter_projection_candidates,
    rank_decoded_projection_frames,
)
from .theme import ThemeManager, ask_themed_yes_no, configure_popup, show_themed_info
from .timeline import ProfessionalTimeline, format_wall_time_ns
from .trial import capabilities_for, record_successful_export, trial_exports_remaining, trial_is_active, trial_status
from .video_canvas import VideoCanvas
from .update_ui import UpdateCheckDialog, UpdateDialog
from .updater import (
    UpdateCheckResult,
    UpdateCheckTask,
    UpdateError,
    schedule_installer_after_exit,
    start_update_check,
)


def camera_waiting_messages(
    translator: Translator,
    source_type: str,
    device_index: int,
    selected_camera: bool,
) -> tuple[str, str]:
    """Return the camera wait text for initial or selected-device startup."""
    if source_type == "file":
        return translator("camera.file_loading"), translator("camera.file_loading_detail")
    if selected_camera and source_type == "camera":
        return (
            translator("camera.input_waiting_selected", index=device_index),
            translator("camera.input_checking_selected", index=device_index),
        )
    return translator("camera.input_waiting"), translator("camera.input_checking")


def first_available_camera(
    probe_results: dict[int, bool | None],
    candidates: tuple[int, ...] = (0, 1),
) -> int | None:
    """Return the first camera confirmed by the startup probe."""
    return next((index for index in candidates if probe_results.get(index) is True), None)


class MainWindow:
    # The canvas requests 154 px.  The compact default adds only its wrapper
    # padding, while the sash still permits a taller or shorter operator view.
    TIMELINE_USABLE_HEIGHT = 164
    VIDEO_USABLE_HEIGHT = 260

    def __init__(
        self,
        root: tk.Tk,
        config: AppConfig,
        config_path: Path,
        persistent_camera_source_type: str | None = None,
        startup_camera_index: int | None = None,
        startup_update_task: UpdateCheckTask | None = None,
        startup_progress: Callable[[StartupProgressEvent], None] | None = None,
    ) -> None:
        def report(operation: str, completed: int, total: int, detail: str = "", *, phase: str = "interface", state: ProgressState = ProgressState.DETERMINATE) -> None:
            if startup_progress:
                startup_progress(StartupProgressEvent(phase, operation, completed, total, .4 if phase == "interface" else .1, detail, state))

        report("Preparing application state…", 0, 8)
        self.root = root
        self.config = config
        initial_trial = capabilities_for()
        paid_authorized = current_authorization()[0]
        self._takeoff_assist_entitled = authorization_permits("takeoff_assist")
        self._evaluation_mode = initial_trial.active and not paid_authorized
        self._trial_expired = False
        self._trial_expiry_job: str | None = None
        self._trial_expiry_dialog_open = False
        self._trial_competition_before_lock = deepcopy(config.competition)
        self._trial_show_decisions_before_lock = config.display.show_decision_controls
        if self._evaluation_mode:
            # The evaluation demonstrates capture, freeze, replay and up to
            # three standalone exports. It must never become a competition tool.
            self.config.competition.enabled = False
            self.config.competition.show_competition_board = False
            self.config.competition.decision_controls_enabled = False
            self.config.competition.event_export_enabled = False
            self.config.competition.auto_save_evidence = False
            self.config.display.show_decision_controls = False
        self._restore_startup_view()
        report("Preparing application state…", 1, 8, "Workspace preferences restored")
        self.config_path = config_path
        self.data_paths = app_data_paths(
            config_path,
            cache_directory=config.attempts.cache_directory,
            recordings_directory=config.attempts.recordings_directory,
            export_directory=config.export.directory,
            evidence_directory=config.export.evidence_directory,
        )
        self._persistent_camera_source_type = persistent_camera_source_type
        self._selected_camera_startup_feedback = startup_camera_index is not None
        self.translator = Translator(config.general.language)
        self.root.title(self.translator("app.title"))
        self.root.minsize(1100, 700)
        if config.display.window_geometry:
            try: self.root.geometry(config.display.window_geometry)
            except tk.TclError: pass

        self.action_queue: Queue[tuple[str, int]] = Queue()
        self.event_queue: Queue[tuple[str, object]] = Queue()
        self.buffer = TimeRingBuffer(config.buffer.duration_seconds, config.buffer.max_memory_mb)
        self.capture = CaptureEngine(
            config.camera,
            config.buffer,
            self.buffer,
            buffer_enabled=config.capture.mode == "buffer",
        )
        self.attempts = AttemptManager(
            self.buffer,
            config.attempts,
            config.export,
            self.data_paths.cache,
            self.event_queue,
            persistent_directory=self.data_paths.recordings,
        )
        self.thumbnail_worker = RecordingThumbnailWorker(self.data_paths.thumbnails, self.event_queue)
        self.capture.set_packet_listener(self.attempts.append_recording_packet)
        self.adjudication = AdjudicationSessionStore(self.data_paths.adjudication, writable_data_directory() / "adjudication-recovery")
        self.playback = PlaybackController(self.buffer, self.attempts)
        self.athlete_timer = AthleteTimerController(config.athlete_timer.duration_seconds)
        # A new judging session always starts at the first athlete's first
        # attempt.  The persisted selection remains available for explicit
        # navigation, but must not silently carry into a fresh startup.
        enabled_groups = [group for group, enabled in (("Boys", config.competition.boys_enabled), ("Girls", config.competition.girls_enabled)) if enabled]
        config.competition.active_group = enabled_groups[0] if enabled_groups else "Boys"
        config.competition.current_competitor_by_group["Boys"] = 1
        config.competition.current_competitor_by_group["Girls"] = 1
        self.competition = CompetitionSession(config.competition)
        self.shuttle = ShuttleHIDPoller(config.shuttle, self.action_queue)
        report("Creating replay components…", 2, 8, "Replay, capture and evidence components created")

        self.theme = ThemeManager(root)
        self.palette = self.theme.apply(config.display.theme)
        report("Applying interface theme…", 3, 8, "Interface theme applied")
        self._closing = False
        self._shutdown_started = 0.0
        self._tick_job: str | None = None
        self._quick_review_job: str | None = None
        self._auto_live_job: str | None = None
        self._last_live_index = -1
        self._last_replay_key: object = None
        self._last_stats_update = 0.0
        self._last_timeline_update = 0.0
        self._last_attempts_refresh = 0.0
        self._last_error = ""
        self._displayed_bgr: np.ndarray | None = None
        self._displayed_timestamp_ns = 0
        self._message_until = 0.0
        self._attempts_pane_added = False
        self._timeline_pane_added = False
        self._window_interacting = False
        self._window_interaction_job: str | None = None
        self._last_root_geometry = ""
        self._calibration_mode = False
        self._board_calibration_wizard: BoardCalibrationWizard | None = None
        self._startup_calibration_opened = False
        self._warning_active = False
        self._assist_warning_attempt_id: int | None = None
        self._top_view_window: TopViewProjectionWindow | None = None
        self._top_view_loading_dialog: ProjectionProgressDialog | None = None
        self._top_view_loading_cancel: Event | None = None
        self._takeoff_projection_indices: dict[int, tuple[int, ...]] = {}
        self._takeoff_projection_lock = Lock()
        self._last_video_update = 0.0
        self._menu_active_until = 0.0
        # Operator/setup mode is a development-only compatibility flag and is
        # never enabled by the customer application.
        self._operator_mode = False
        self._recovery_checked = False
        self._last_board_signature: object = None
        self._board_next_assignment: RosterAssignment | None = None
        self._last_timer_render_signature: object = None
        self._system_paused = False
        self._system_pause_transition = False
        self._camera_starting = False
        self._camera_start_started_at = 0.0
        self._camera_start_deadline = 0.0
        self._camera_input_timed_out = False
        self._camera_retrying = False
        self._camera_retry_stop_complete = False
        self._camera_probe_generation = 0
        self._camera_probe_stop = Event()
        self._camera_probe_lock = Lock()
        self._camera_probe_results: dict[int, bool | None] = {}
        self._camera_help_dialog: tk.Toplevel | None = None
        self._busy_depth = 0
        self._busy_message = ""
        self._busy_show_job: str | None = None
        # Export/Delete follow the last explicit capture selection, not merely
        # whichever attempt the replay controller still has open.
        self._selected_action_attempt_id: int | None = None
        self._durability_blocked_attempt_id: int | None = None
        self._measurement_record_id: str | None = None
        self._measurement_continue_attempt_id: int | None = None
        self._measurement_popup: tk.Toplevel | None = None
        self._measurement_popup_save_button: ttk.Button | None = None
        self._attempt_editor: tk.Toplevel | None = None
        self._recording_auto_stop_job: str | None = None
        self._hold_playback = False
        self._hold_playback_job: str | None = None
        self._telemetry = RuntimeTelemetry()
        self._logger = logging.getLogger("long_jump_replay")
        self._startup_update_task = startup_update_task
        self._manual_update_task: UpdateCheckTask | None = None
        self._manual_update_parent: tk.Misc | None = None
        self._update_check_dialog: UpdateCheckDialog | None = None
        self._update_dialog: UpdateDialog | None = None

        self._build_variables()
        self._build_menu()
        report("Building operator interface…", 4, 8, "Menus and interface state created")
        self._build_layout()
        report("Building operator interface…", 5, 8, "Judge workspace constructed")
        self.hotkeys = HotkeyRouter(root)
        self._install_hotkeys()
        self._apply_layout()
        self._apply_visibility()
        report("Connecting operator controls…", 7, 8, "Keyboard and workspace controls connected")
        self._refresh_competitor_selector()
        if config.display.fullscreen:
            self.root.attributes("-fullscreen", True)
        else:
            self.root.after_idle(self._apply_initial_window_state)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        report("Finishing interface construction…", 8, 8, "Main interface constructed")

        report("Starting background services…", 0, 4, phase="services")
        self.attempts.start()
        self.thumbnail_worker.start()
        report("Starting background services…", 1, 4, "Attempt worker started", phase="services")
        self._reconcile_adjudication_records()
        self.root.after(150, self._check_recovered_session)
        self._start_camera_with_feedback(self._t("status.starting"))
        report("Starting background services…", 2, 4, "Camera worker started", phase="services")
        self.shuttle.start()
        report("Starting background services…", 3, 4, "Input services started", phase="services")
        self._schedule_tick()
        if self._evaluation_mode:
            self._schedule_trial_expiry_check()
        if not self.config.general.onboarding_completed:
            self.root.after(350, self.show_onboarding)
        if not self.config.general.recording_mode_prompted:
            # Let startup actions, camera readiness, and the onboarding card
            # settle before presenting this non-blocking mode choice.
            self.root.after(5000, self._prompt_recording_mode)
        if self._startup_update_task is not None:
            self.root.after(700, lambda: self._poll_update_task(self._startup_update_task, manual=False))
        report("Judge station ready", 4, 4, "Required workers are running", phase="services")

    # ------------------------------------------------------------------ UI
    def _restore_startup_view(self) -> None:
        """Start every session with the complete judging workspace visible."""
        display = self.config.display
        display.show_attempts_panel = True
        display.show_timeline = True
        display.show_status_bar = True
        display.show_live_preview = True
        clamp_display_panel_sizes(display)
        if display.timeline_height in {200, 208, 220}:
            display.timeline_height = self.TIMELINE_USABLE_HEIGHT
        self.config.competition.show_competition_board = not getattr(self, "_evaluation_mode", False)

    def _build_variables(self) -> None:
        d = self.config.display
        self.var_show_attempts = tk.BooleanVar(value=d.show_attempts_panel)
        self.var_show_timeline = tk.BooleanVar(value=d.show_timeline)
        self.var_show_status = tk.BooleanVar(value=d.show_status_bar)
        self.var_show_live = tk.BooleanVar(value=d.show_live_preview)
        self.var_show_board = tk.BooleanVar(value=self.config.competition.show_competition_board)
        self.var_show_board_outline = tk.BooleanVar(value=d.board_roi_visible)
        self.var_show_foul_area = tk.BooleanVar(value=d.guide_enabled)
        self.var_layout = tk.StringVar(value=d.layout)
        self.var_theme = tk.StringVar(value=d.theme)
        self.camera_selector_var = tk.IntVar(value=self.config.camera.device_index)
        self.camera_var = tk.StringVar(value="Starting camera…")
        self.clock_var = tk.StringVar(value="")
        self.timer_prefix_var = tk.StringVar(value=self._t("timer.ready"))
        self.timer_value_var = tk.StringVar(value=format_countdown(self.config.athlete_timer.duration_seconds))
        self.mode_var = tk.StringVar(value=self._t("mode.live"))
        self.status_var = tk.StringVar(value="Initialising…")
        self.message_var = tk.StringVar(value="")
        self.warning_var = tk.StringVar(value="")
        self.recording_var = tk.StringVar(value="")
        self.assist_warning_var = tk.StringVar(value="")
        self.camera_warning_var = tk.StringVar(value="")
        self.attempt_summary_var = tk.StringVar(value=self._t("attempts.none"))
        self.competition_banner_var = tk.StringVar(value="")
        self.group_var = tk.StringVar(value=self.config.competition.active_group)
        self.competitor_var = tk.StringVar(value=str(self.config.competition.current_competitor_by_group.get(self.config.competition.active_group, 1)))
        self.current_try_var = tk.StringVar(value="Try 1")
        self.board_target_var = tk.StringVar(value="")
        self.measurement_distance_var = tk.StringVar(value="")
        self.measurement_wind_var = tk.StringVar(value="")
        self.measurement_error_var = tk.StringVar(value="")

    def _t(self, key: str, **kwargs) -> str:
        return self.translator(key, **kwargs)

    def _group_display(self, group: str) -> str:
        return self._t("competition.boys") if group == "Boys" else self._t("competition.girls")

    def _group_internal(self, display: str) -> str:
        return "Boys" if display in {"Boys", "Chlapci", self._t("competition.boys")} else "Girls"

    def _resize_board_navigation(self, _event: tk.Event | None = None) -> None:
        """Wrap board instructions to the available width after every resize."""
        try:
            width = max(160, self.board_navigation.winfo_width() - 20)
            if int(self.board_keyboard_hint.cget("wraplength") or 0) != width:
                self.board_keyboard_hint.configure(wraplength=width)
        except tk.TclError:
            return

    @staticmethod
    def _geometry_nearly_fills_screen(geometry: str, screen_width: int, screen_height: int) -> bool:
        try:
            size = geometry.split("+", 1)[0]
            width_text, height_text = size.split("x", 1)
            width, height = int(width_text), int(height_text)
        except (TypeError, ValueError):
            return False
        return width >= screen_width * .90 and height >= screen_height * .85

    def _apply_initial_window_state(self) -> None:
        try:
            should_maximize = self.config.display.window_maximized or self._geometry_nearly_fills_screen(
                self.config.display.window_geometry,
                self.root.winfo_screenwidth(),
                self.root.winfo_screenheight(),
            )
            if should_maximize:
                self.root.state("zoomed")
        except tk.TclError:
            pass

    def _begin_menu_interaction(self) -> None:
        if not self.config.performance.menu_throttle_enabled:
            return
        self._menu_active_until = time.perf_counter() + 1.0

    def _build_menu(self) -> None:
        # A lightweight in-window menu replaces the native root menubar. The
        # popup menus are created once and never rebuilt by the video loop.
        self.file_menu = tk.Menu(self.root, tearoff=False, postcommand=self._begin_menu_interaction)
        restricted_state = "disabled" if self._evaluation_mode and not capabilities_for().permits("competition_setup") else "normal"
        self.file_menu.add_command(label=self._t("menu.wizard") + "\tCtrl+N", command=self.start_competition_wizard, state=restricted_state)
        self.file_menu.add_command(label=self._t("menu.import_roster"), command=self.import_roster, state=restricted_state)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self._t("menu.export") + "\tE", command=self.export_current_attempt)
        self.file_menu.add_command(label=self._t("menu.save_frame") + "\tP", command=self.save_current_frame)
        self.file_menu.add_command(label=self._t("menu.export_evidence"), command=self.export_adjudication_package, state=restricted_state)
        if self.config.competition.event_export_enabled:
            self.file_menu.add_command(label=self._t("menu.export_event"), command=self.export_competition_package, state=restricted_state)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self._t("menu.clear") + "\tCtrl+Delete", command=self.clear_all_recordings)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self._t("menu.exports"), command=self.open_exports_folder)
        self.file_menu.add_command(label="Open recordings folder", command=self.open_recordings_folder)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self._t("menu.settings"), command=self.open_settings)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self._t("menu.exit"), command=self.close)
        self.camera_menu = tk.Menu(self.root, tearoff=False, postcommand=self._populate_camera_menu)
        self.view_menu = tk.Menu(self.root, tearoff=False, postcommand=self._begin_menu_interaction)
        self.layout_menu = tk.Menu(self.view_menu, tearoff=False, postcommand=self._begin_menu_interaction)
        layouts = [
            ("replay_pip", "layout.replay_pip"), ("side_by_side", "layout.side_by_side"),
            ("board_detail", "layout.board_detail"), ("comparison", "layout.comparison"),
            ("replay_only", "layout.replay_only"), ("live_only", "layout.live_only"),
        ]
        for value, key in layouts:
            self.layout_menu.add_radiobutton(label=self._t(key), variable=self.var_layout, value=value, command=self._menu_layout_changed)
        self.view_menu.add_cascade(label=self._t("menu.layout"), menu=self.layout_menu)
        self.view_menu.add_checkbutton(label=self._t("menu.attempts") + "\tA", variable=self.var_show_attempts, command=self.toggle_attempts_panel)
        self.var_show_board = getattr(self, "var_show_board", tk.BooleanVar(value=self.config.competition.show_competition_board))
        self.view_menu.add_checkbutton(label=self._t("menu.board") + "\tB", variable=self.var_show_board, command=self.toggle_competition_board, state=restricted_state)
        self.view_menu.add_checkbutton(label=self._t("menu.timeline") + "\tT", variable=self.var_show_timeline, command=self.toggle_timeline)
        self.view_menu.add_checkbutton(label=self._t("menu.live") + "\tL", variable=self.var_show_live, command=self.toggle_live_preview)
        self.view_menu.add_checkbutton(label=self._t("menu.status"), variable=self.var_show_status, command=self.toggle_status_bar)
        self.view_menu.add_separator()
        self.theme_menu = tk.Menu(self.view_menu, tearoff=False, postcommand=self._begin_menu_interaction)
        for value, key in [("system", "theme.system"), ("dark", "theme.dark"), ("light", "theme.light")]:
            self.theme_menu.add_radiobutton(label=self._t(key), variable=self.var_theme, value=value, command=self._menu_theme_changed)
        self.view_menu.add_cascade(label=self._t("menu.theme"), menu=self.theme_menu)
        self.view_menu.add_separator()
        self.view_menu.add_command(label=self._t("menu.calibration"), command=self.open_board_calibration)
        self.view_menu.add_checkbutton(label=self._t("menu.show_board_outline"), variable=self.var_show_board_outline, command=self.toggle_board_overlay)
        self.view_menu.add_checkbutton(label=self._t("menu.show_foul_area") + "\tG", variable=self.var_show_foul_area, command=self.toggle_foul_overlay)
        self.view_menu.add_command(label=self._t("menu.comparison") + "\tC", command=self.toggle_comparison)
        self.view_menu.add_command(label=self._t("menu.fullscreen") + "\tF11", command=self.toggle_fullscreen)
        self.view_menu.add_command(label=self._t("menu.reset") + "\tR", command=self.reset_video_views)
        self.help_menu = tk.Menu(self.root, tearoff=False, postcommand=self._begin_menu_interaction)
        self.help_menu.add_command(label=self._t("menu.controls"), command=self.show_controls)
        self.help_menu.add_separator()
        self.help_menu.add_command(label=self._t("menu.check_updates"), command=self.check_for_updates)
        self.help_menu.add_separator()
        self.help_menu.add_command(label=self._t("menu.about"), command=lambda: show_themed_info(self.root, self._t("menu.about"), f"Long Jump Replay {__version__}\nLive video review for long-jump take-off decisions."))
        self._style_all_menus()

    def check_for_updates(self, parent: tk.Misc | None = None) -> None:
        if self._manual_update_task is not None and not self._manual_update_task.done:
            if self._update_check_dialog is not None:
                try:
                    self._update_check_dialog.window.lift()
                except tk.TclError:
                    pass
            return
        self._manual_update_parent = parent or self.root
        self._update_check_dialog = UpdateCheckDialog(self._manual_update_parent, self.config.general.language)
        self._manual_update_task = start_update_check(respect_skip=False)
        self.root.after(80, lambda: self._poll_update_task(self._manual_update_task, manual=True))

    def _poll_update_task(self, task: UpdateCheckTask | None, *, manual: bool) -> None:
        if task is None or self._closing:
            return
        result = task.result()
        if result is None:
            self.root.after(120, lambda: self._poll_update_task(task, manual=manual))
            return
        if manual and task is self._manual_update_task:
            self._manual_update_task = None
            if self._update_check_dialog is not None:
                self._update_check_dialog.close()
                self._update_check_dialog = None
        self._handle_update_result(result, manual=manual)

    def _handle_update_result(self, result: UpdateCheckResult, *, manual: bool) -> None:
        parent = self.root
        if manual and self._manual_update_parent is not None:
            try:
                if self._manual_update_parent.winfo_exists():
                    parent = self._manual_update_parent
            except tk.TclError:
                pass
            self._manual_update_parent = None
        if result.status == "available" and result.release:
            if self._update_dialog is not None and self._update_dialog.window.winfo_exists():
                self._update_dialog.window.lift()
                return
            self._update_dialog = UpdateDialog(
                parent,
                result.release,
                self.config.general.language,
                self._install_downloaded_update,
            )
            return
        if not manual:
            if result.status == "error":
                self._logger.info("update_check_failed error=%s", result.message)
            return
        if result.status == "current":
            show_themed_info(
                parent,
                self._t("update.title"),
                self._t("update.current", version=VERSION_SHORT),
            )
        elif result.status == "error":
            show_themed_info(parent, self._t("update.title"), result.message)

    def _install_downloaded_update(self, installer: Path) -> None:
        self._show_message(self._t("update.launching"), 8)
        result_queue: Queue[UpdateError | None] = Queue(maxsize=1)

        def launch() -> None:
            try:
                schedule_installer_after_exit(installer)
            except UpdateError as error:
                result_queue.put(error)
            else:
                result_queue.put(None)

        def poll() -> None:
            if self._closing:
                return
            try:
                error = result_queue.get_nowait()
            except Empty:
                self.root.after(80, poll)
                return
            if error is not None:
                if self._update_dialog is not None and self._update_dialog.window.winfo_exists():
                    self._update_dialog.show_install_launch_error(str(error))
                show_themed_info(self.root, self._t("update.title"), str(error))
                return
            self._show_message(self._t("update.closing"), 8)
            self.close()

        Thread(target=launch, name="update-installer-launch", daemon=True).start()
        self.root.after(80, poll)

    def _style_all_menus(self) -> None:
        for name in ("file_menu", "camera_menu", "view_menu", "layout_menu", "theme_menu", "help_menu", "special_result_menu"):
            menu = getattr(self, name, None)
            if isinstance(menu, tk.Menu):
                self.theme.style_menu(menu)

    def _attach_header_menus(self, header: ttk.Frame) -> None:
        self.header_menu_frame = ttk.Frame(header, style="Panel.TFrame")
        self.header_menu_frame.pack(side="left", padx=(22, 0))
        self.file_menu_button = ttk.Menubutton(self.header_menu_frame, text=self._t("menu.file"), menu=self.file_menu, style="Header.TMenubutton")
        self.view_menu_button = ttk.Menubutton(self.header_menu_frame, text=self._t("menu.view"), menu=self.view_menu, style="Header.TMenubutton")
        self.help_menu_button = ttk.Menubutton(self.header_menu_frame, text=self._t("menu.help"), menu=self.help_menu, style="Header.TMenubutton")
        self.camera_menu_button = ttk.Menubutton(self.header_menu_frame, text=self._t("menu.camera"), menu=self.camera_menu, style="Header.TMenubutton")
        for index, button in enumerate((self.file_menu_button, self.view_menu_button, self.help_menu_button, self.camera_menu_button)):
            button.pack(side="left", padx=1)
            if index == 3:
                button.pack_configure(padx=(10, 1))
            button.bind("<ButtonPress-1>", lambda _e: self._begin_menu_interaction(), add="+")

    def _populate_camera_menu(self) -> None:
        """Refresh the compact camera selector immediately before it opens."""
        self.camera_menu.delete(0, "end")
        current = self.config.camera.device_index
        devices = enumerate_camera_devices(current)
        self.camera_selector_var.set(current)
        for device in devices:
            self.camera_menu.add_radiobutton(
                label=device.label,
                variable=self.camera_selector_var,
                value=device.index,
                command=lambda index=device.index: self.select_camera_device(index),
            )
        self.camera_menu.add_separator()
        self.camera_menu.add_command(label=self._t("menu.settings"), command=self.open_settings)

    def select_camera_device(self, index: int) -> None:
        """Select a detected camera through the normal restart-safe settings path."""
        index = int(index)
        if self.config.camera.source_type == "camera" and index == self.config.camera.device_index:
            self._show_message(self._t("camera.already_selected"), 3)
            return
        new_config = deepcopy(self.config)
        new_config.camera.source_type = "camera"
        new_config.camera.device_index = index
        self.apply_settings(new_config)

    def _build_layout(self) -> None:
        self.outer = ttk.Frame(self.root, style="App.TFrame", padding=(12, 10, 12, 10))
        self.outer.pack(fill="both", expand=True)

        header = ttk.Frame(self.outer, style="JudgeHeader.TFrame", padding=(14, 9))
        header.pack(fill="x", pady=(0, 8))
        header_brand = ttk.Frame(header, style="Panel.TFrame")
        header_brand.pack(side="left")
        self.header_title = ttk.Label(header_brand, text=self._t("app.header"), style="Brand.TLabel")
        self.header_title.pack(anchor="w")
        self._attach_header_menus(header)
        ttk.Label(header, textvariable=self.camera_var, style="Muted.TLabel").pack(side="left", padx=(18, 0), pady=(3, 0))
        self.timer_frame = tk.Frame(header, borderwidth=0, highlightthickness=1, cursor="hand2")
        self.timer_frame.pack(side="right", padx=(12, 0), pady=(1, 0))
        self.timer_prefix_label = tk.Label(self.timer_frame, textvariable=self.timer_prefix_var, borderwidth=0, cursor="hand2", font=("Segoe UI Semibold", 10))
        self.timer_prefix_label.pack(side="left", padx=(6, 5), pady=3)
        self.timer_value_label = tk.Label(self.timer_frame, textvariable=self.timer_value_var, borderwidth=0, cursor="hand2", font=("Consolas", 12, "bold"))
        self.timer_value_label.pack(side="left", padx=(0, 6), pady=3)
        for widget in (self.timer_frame, self.timer_prefix_label, self.timer_value_label):
            widget.bind("<Button-1>", self._on_timer_click)
        self.system_pause_button = ttk.Button(header, text=self._t("button.pause_system"), width=14, style="SystemPause.TButton", command=self.toggle_system_pause)
        self.system_pause_button.pack(side="right", padx=(12, 0), pady=(1, 0))
        self.mode_badge = tk.Label(header, textvariable=self.mode_var, width=14, anchor="center", padx=10, pady=4, borderwidth=0, font=("Segoe UI Semibold", 9))
        self.mode_badge.pack(side="right", padx=(10, 0))
        ttk.Label(header, textvariable=self.clock_var, style="Muted.TLabel").pack(side="right", pady=(3, 0))
        self._update_athlete_timer_display()

        self.warning_banner = tk.Label(self.outer, textvariable=self.warning_var, anchor="w", padx=10, pady=5, font=("Segoe UI Semibold", 9))
        if self._evaluation_mode:
            self.evaluation_banner = tk.Label(
                self.outer,
                text="Evaluation only — competition features disabled" if self.config.general.language != "cs" else "Pouze zkušební režim — soutěžní funkce jsou vypnuté",
                anchor="center", padx=10, pady=6, font=("Segoe UI Semibold", 9),
                bg="#5b4300", fg="#fff1b8",
            )
            self.evaluation_banner.pack(fill="x", pady=(0, 8))
        self.competition_banner = tk.Label(self.outer, textvariable=self.competition_banner_var, anchor="center", padx=10, pady=5, font=("Segoe UI Semibold", 9))

        self.wizard_button = ttk.Button(self.outer, text=self._t("button.wizard"), style="Accent.TButton", command=self.start_competition_wizard)
        self.wizard_button.pack(anchor="w", pady=(0, 6))
        if self._evaluation_mode:
            self.wizard_button.configure(state="disabled")

        self.content_pane = ttk.Panedwindow(self.outer, orient="horizontal")
        self.content_pane.pack(fill="both", expand=True)
        self.workspace = ttk.Frame(self.content_pane, style="App.TFrame")
        self.attempts_panel = self._build_attempts_panel(self.content_pane)
        self.content_pane.add(self.workspace, weight=5)
        self.workspace.rowconfigure(0, weight=1)
        self.workspace.columnconfigure(0, weight=1)

        self.media_pane = ttk.Panedwindow(self.workspace, orient="vertical")
        self.media_pane.grid(row=0, column=0, sticky="nsew")
        self.video_host = ttk.Frame(self.media_pane, style="Panel.TFrame", height=520)
        kwargs = self._video_calibration_kwargs()
        self.replay_canvas = VideoCanvas(self.video_host, self.palette, guide_changed=self._guide_changed, calibration_changed=self._calibration_changed, language=self.config.general.language, **kwargs)
        self.live_canvas = VideoCanvas(self.video_host, self.palette, compact=True, language=self.config.general.language, **kwargs)
        self.board_canvas = VideoCanvas(self.video_host, self.palette, compact=True, guide_enabled=False, board_roi_enabled=False, board_roi_visible=False, language=self.config.general.language)
        self.comparison_prev_canvas = VideoCanvas(self.video_host, self.palette, compact=True, guide_enabled=False, board_roi_enabled=False, board_roi_visible=False, language=self.config.general.language)
        self.comparison_next_canvas = VideoCanvas(self.video_host, self.palette, compact=True, guide_enabled=False, board_roi_enabled=False, board_roi_visible=False, language=self.config.general.language)

        self.timeline_wrap = ttk.Frame(self.workspace, style="Panel.TFrame", padding=(5, 4), height=max(MIN_TIMELINE_HEIGHT, self.config.display.timeline_height))
        self.timeline_wrap.rowconfigure(0, weight=1)
        self.timeline_wrap.columnconfigure(0, weight=1)
        self.timeline = ProfessionalTimeline(
            self.timeline_wrap, self.palette, self.seek_timeline,
            detail_window_seconds=self.config.timeline.detail_window_seconds,
            min_detail_seconds=self.config.timeline.min_detail_seconds,
            max_detail_seconds=self.config.timeline.max_detail_seconds,
            on_zoom_commit=self._commit_timeline_zoom,
            language=self.config.general.language,
        )
        self.timeline.grid(row=0, column=0, sticky="nsew")
        self.timeline_hint_label = ttk.Label(
            self.timeline_wrap, text="", style="TimelineHint.TLabel",
            anchor="center", justify="center",
        )
        # Keep the compatibility attribute for integrations, but remove the
        # obsolete keyboard/zoom instruction strip from the operator surface.
        self.timeline_hint_label.grid_remove()
        self.media_pane.add(self.video_host, weight=5)
        self.media_pane.add(self.timeline_wrap, weight=1)
        self._timeline_pane_added = True
        self.root.after_idle(self._set_timeline_sash)
        self.root.after(180, self._set_timeline_sash)

        self.controls = ttk.Frame(self.workspace, style="ControlDock.TFrame", padding=(7, 5))
        self.controls.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.freeze_button = ttk.Button(self.controls, text=self._t("button.freeze"), width=14, style="PrimaryJudge.TButton", command=self.toggle_freeze)
        self.freeze_button.pack(side="left")
        # Freeze and Live are one primary toggle. Keep the old attribute as an
        # alias for integrations, but do not create a second visible button.
        self.live_button = self.freeze_button
        self.freeze_button.pack(side="left", padx=(0, 12))
        self.recording_status_label = ttk.Label(self.controls, textvariable=self.recording_var, style="Warning.TLabel")
        self.recording_status_label.pack(side="left", padx=(0, 12))
        self.assist_warning_label = ttk.Label(self.controls, textvariable=self.assist_warning_var, style="Warning.TLabel")
        # Keep the failure notice out of the way until a frozen attempt needs it.
        self.assist_warning_label.pack_forget()
        self.frame_group = ttk.Frame(self.controls, style="ControlDock.TFrame")
        self.frame_group_label = ttk.Label(self.frame_group, text=self._t("controls.frame_review"), style="ContextTitle.TLabel")
        self.frame_group_label.pack(anchor="w")
        frame_buttons = ttk.Frame(self.frame_group, style="ControlDock.TFrame")
        frame_buttons.pack(anchor="w", pady=(2, 0))
        self.prev_frame_button = ttk.Button(frame_buttons, text=self._t("button.previous_frame"), width=12, style="Control.TButton", command=lambda: self.step_frame(-1))
        self.prev_frame_button.pack(side="left", padx=(0, 2))
        self.next_frame_button = ttk.Button(frame_buttons, text=self._t("button.next_frame"), width=12, style="Control.TButton", command=lambda: self.step_frame(1))
        self.next_frame_button.pack(side="left", padx=2)
        self.top_view_button = ttk.Button(frame_buttons, text=self._t("button.top_view"), width=16, style="Control.TButton", command=self.open_top_view_projection)
        self.top_view_button.pack(side="left", padx=(7, 0))
        self.frame_group.pack(side="left", padx=(0, 12))

        self.decision_frame = ttk.Frame(self.controls, style="ControlDock.TFrame")
        self.decision_group_label = ttk.Label(self.decision_frame, text=self._t("controls.judging"), style="ContextTitle.TLabel")
        self.decision_group_label.pack(anchor="w")
        decision_buttons = ttk.Frame(self.decision_frame, style="ControlDock.TFrame")
        decision_buttons.pack(anchor="w", pady=(2, 0))
        self.not_decided_button = ttk.Button(decision_buttons, text=self._t("button.not_decided"), width=12, style="JudgePending.TButton", command=lambda: self.mark_decision(AttemptDecision.NOT_DECIDED))
        self.not_decided_button.pack(side="left", padx=(0, 2))
        self.valid_button = ttk.Button(decision_buttons, text=self._t("button.valid"), width=12, style="JudgeValid.TButton", command=lambda: self.mark_decision(AttemptDecision.VALID))
        self.valid_button.pack(side="left", padx=2)
        self.foul_button = ttk.Button(decision_buttons, text=self._t("button.foul"), width=12, style="JudgeFoul.TButton", command=lambda: self.mark_decision(AttemptDecision.FOUL))
        self.foul_button.pack(side="left", padx=2)
        self.review_button = ttk.Button(decision_buttons, text=self._t("button.review"), width=12, style="JudgeReview.TButton", command=lambda: self.mark_decision(AttemptDecision.REVIEW))
        self.review_button.pack(side="left", padx=2)
        self.decision_frame.pack(side="left")

        self.measurement_frame = ttk.Frame(self.workspace, style="Toolbar.TFrame", padding=(7, 5))
        self.measurement_title_label = ttk.Label(self.measurement_frame, text=self._t("measurement.title"), style="ContextTitle.TLabel")
        self.measurement_title_label.pack(side="left", padx=(0, 12))
        self.measurement_distance_label = ttk.Label(self.measurement_frame, text=self._t("measurement.distance"), style="Muted.TLabel")
        self.measurement_distance_label.pack(side="left")
        self.measurement_distance_entry = ttk.Entry(self.measurement_frame, textvariable=self.measurement_distance_var, width=8)
        self.measurement_distance_entry.pack(side="left", padx=(5, 12))
        self.measurement_wind_label = ttk.Label(self.measurement_frame, text=self._t("measurement.wind"), style="Muted.TLabel")
        self.measurement_wind_entry = ttk.Entry(self.measurement_frame, textvariable=self.measurement_wind_var, width=7)
        self.measurement_save_button = ttk.Button(self.measurement_frame, text=self._t("measurement.save"), style="Accent.TButton", command=self._save_measurement)
        self.measurement_save_button.pack(side="right")
        self.measurement_skip_button = ttk.Button(self.measurement_frame, text=self._t("measurement.skip"), command=self._skip_measurement)
        self.measurement_skip_button.pack(side="right", padx=(0, 7))
        self.measurement_error_label = ttk.Label(self.measurement_frame, textvariable=self.measurement_error_var, style="Warning.TLabel")
        self.measurement_error_label.pack(side="right", padx=(0, 10))
        self.measurement_frame.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        self.measurement_frame.grid_remove()

        self.center_overlay = tk.Label(self.video_host, text="", justify="center", padx=18, pady=10, font=("Segoe UI Semibold", 14), borderwidth=0)
        self.camera_waiting_frame = ttk.Frame(self.video_host, style="Toolbar.TFrame", padding=(18, 14))
        self.camera_waiting_title = ttk.Label(self.camera_waiting_frame, text=self._t("camera.input_waiting"), style="ContextTitle.TLabel")
        self.camera_waiting_title.pack(anchor="center")
        self.camera_waiting_detail = ttk.Label(self.camera_waiting_frame, text=self._t("camera.input_checking"), style="Muted.TLabel")
        self.camera_waiting_detail.pack(anchor="center", pady=(4, 9))
        self.camera_waiting_progress = ttk.Progressbar(self.camera_waiting_frame, mode="indeterminate", length=300)
        self.camera_waiting_progress.pack(fill="x")
        self.camera_action_frame = ttk.Frame(self.video_host, style="Toolbar.TFrame", padding=(8, 6))
        self.camera_try_again_button = ttk.Button(self.camera_action_frame, text=self._t("camera.try_again"), style="Accent.TButton", command=self._try_camera_again)
        self.camera_try_again_button.pack(side="left")
        self.camera_help_button = ttk.Button(self.camera_action_frame, text=self._t("camera.help_button"), style="Control.TButton", command=self.show_camera_help)
        self.camera_help_button.pack(side="left", padx=(8, 0))
        self.camera_waiting_frame.place_forget()
        self.camera_action_frame.place_forget()

        self.status_bar = ttk.Frame(self.workspace, style="Toolbar.TFrame", padding=(10, 5))
        self.status_bar.grid(row=3, column=0, sticky="ew", pady=(5, 0))
        self.status_bar.columnconfigure(0, weight=1)
        ttk.Label(self.status_bar, textvariable=self.status_var, style="Status.TLabel", anchor="w").grid(row=0, column=0, sticky="ew")
        self.camera_warning_label = ttk.Label(
            self.status_bar, textvariable=self.camera_warning_var,
            style="StatusWarning.TLabel", anchor="e",
        )
        self.camera_warning_label.grid(row=0, column=1, sticky="e", padx=(10, 0))
        self.status_progress = ttk.Progressbar(self.status_bar, mode="indeterminate", length=110)
        self.status_progress.grid(row=0, column=2, sticky="e", padx=(12, 0))
        self.status_progress.grid_remove()
        ttk.Label(self.status_bar, textvariable=self.message_var, style="Status.TLabel", anchor="e").grid(row=0, column=3, sticky="e", padx=(12, 0))

    def _video_calibration_kwargs(self) -> dict:
        d = self.config.display
        return dict(
            guide_enabled=d.guide_enabled,
            guide_x_ratio=d.guide_x_ratio,
            guide_y_ratio=d.guide_y_ratio,
            guide_angle_deg=d.guide_angle_deg,
            guide_width_px=d.guide_width_px,
            board_roi=(d.board_roi_x, d.board_roi_y, d.board_roi_width, d.board_roi_height),
            board_roi_enabled=d.board_roi_enabled,
            board_roi_visible=d.board_roi_visible,
            projection_board=tuple(tuple(point) for point in self.config.top_view_projection.board_corners),
            projection_foul_area=tuple(tuple(point) for point in self.config.top_view_projection.foul_area),
        )

    def _build_attempts_panel(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Panel.TFrame", padding=(7, 7))
        top = ttk.Frame(frame, style="Panel.TFrame")
        top.pack(fill="x", pady=(0, 6))
        self.attempts_title_label = ttk.Label(top, text=self._t("attempts.title"), style="PanelTitle.TLabel")
        self.attempts_title_label.pack(side="left")
        ttk.Label(top, textvariable=self.attempt_summary_var, style="Muted.TLabel").pack(side="right")

        self.side_notebook = ttk.Notebook(frame)
        self.side_notebook.pack(fill="both", expand=True)
        self.recordings_tab = ttk.Frame(self.side_notebook, style="Panel.TFrame", padding=(2, 4))
        self.board_tab = ttk.Frame(self.side_notebook, style="Panel.TFrame", padding=(2, 4))
        self.side_notebook.add(self.recordings_tab, text=self._t("captures.title").title())
        self.side_notebook.add(self.board_tab, text=self._t("board.title").title())

        self._thumbnail_images: dict[int, ImageTk.PhotoImage] = {}
        self._thumbnail_fallback = ImageTk.PhotoImage(Image.new("RGB", (72, 44), self.palette["surface2"]))
        tree_style = ttk.Style(self.root)
        tree_style.configure("Recording.Treeview", rowheight=58, font=("Segoe UI", 10))
        tree_style.configure("Recording.Treeview.Heading", font=("Segoe UI Semibold", 9))
        tree = ttk.Treeview(self.recordings_tab, columns=("recording", "group", "athlete", "try", "result", "distance", "wind", "time", "duration", "media", "keep"), show="tree headings", selectmode="browse", style="Recording.Treeview")
        tree.heading("#0", text="")
        tree.column("#0", width=78, minwidth=78, stretch=False, anchor="center")
        specs = [
            ("recording", self._t("table.recording"), 72),
            ("group", self._t("table.group"), 54), ("athlete", "#", 30), ("try", self._t("table.attempt"), 50),
            ("result", self._t("table.result"), 82), ("time", self._t("table.time"), 58), ("duration", self._t("table.duration"), 64), ("media", self._t("table.media"), 65), ("keep", self._t("table.keep"), 54),
            ("distance", self._t("table.distance"), 62), ("wind", self._t("table.wind"), 52),
        ]
        for key, label, width in specs:
            tree.heading(key, text=label); tree.column(key, width=width, anchor="center", stretch=key in {"result", "media"})
        tree.pack(fill="both", expand=True)
        tree.bind("<<TreeviewSelect>>", self._attempt_tree_selected)
        tree.bind("<Double-1>", self._open_attempt_editor_from_tree)
        tree.bind("<Button-3>", self._show_attempt_context_menu)
        tree.bind("<Shift-F10>", self._show_attempt_keyboard_context_menu)
        self.attempt_tree = tree
        self.attempt_context_menu = tk.Menu(self.root, tearoff=False)
        self.attempt_context_menu.add_command(label=self._t("attempts.open"), command=self._open_attempt_from_recordings)
        self.attempt_context_menu.add_command(label=self._t("attempts.edit"), command=self._edit_attempt_from_recordings)
        self.attempt_context_menu.add_command(label=self._t("attempts.export"), command=self._export_attempt_from_recordings)
        self.attempt_context_menu.add_separator()
        self._recording_verdict_indices: list[int] = []
        for decision in (
            AttemptDecision.NOT_DECIDED, AttemptDecision.VALID, AttemptDecision.FOUL,
            AttemptDecision.REVIEW, AttemptDecision.PASSED, AttemptDecision.MISSING,
            AttemptDecision.WITHDRAWN,
        ):
            self.attempt_context_menu.add_command(
                label=self._decision_display(decision),
                command=lambda value=decision: self._mark_attempt_from_recordings(value),
            )
            self._recording_verdict_indices.append(int(self.attempt_context_menu.index("end")))
        self.attempt_context_menu.add_separator()
        self.attempt_context_menu.add_command(label=self._t("attempts.measurement"), command=self._edit_measurement_from_recordings)
        self._recording_measurement_menu_index = int(self.attempt_context_menu.index("end"))
        self.attempt_context_menu.add_separator()
        self.attempt_context_menu.add_command(label=self._t("attempts.delete"), command=self._delete_attempt_from_recordings)
        self._recording_delete_menu_index = int(self.attempt_context_menu.index("end"))
        self.theme.style_menu(self.attempt_context_menu)

        self.board_navigation = ttk.Frame(self.board_tab, style="Toolbar.TFrame", padding=(10, 7))
        self.board_navigation.pack(fill="x", pady=(0, 5))
        self.board_navigation.columnconfigure(0, weight=1)
        self.board_target_title_label = ttk.Label(self.board_navigation, text=self._t("board.next_target"), style="ContextTitle.TLabel")
        self.board_target_title_label.grid(row=0, column=0, sticky="w")
        self.board_target_label = ttk.Label(self.board_navigation, textvariable=self.board_target_var, style="ContextValue.TLabel")
        self.board_target_label.grid(row=1, column=0, sticky="w")
        self.special_result_button = ttk.Menubutton(self.board_navigation, text=self._t("button.more"))
        self.special_result_menu = tk.Menu(self.special_result_button, tearoff=False)
        self.special_result_menu.add_command(label=self._t("status.passed"), command=lambda: self.mark_special_result(AttemptDecision.PASSED))
        self.special_result_menu.add_command(label=self._t("status.missing"), command=lambda: self.mark_special_result(AttemptDecision.MISSING))
        self.special_result_menu.add_command(label=self._t("status.withdrawn"), command=lambda: self.mark_special_result(AttemptDecision.WITHDRAWN))
        self.special_result_menu.add_separator(); self.special_result_menu.add_command(label=self._t("status.reattempt"), command=self.grant_reattempt)
        self.special_result_button.configure(menu=self.special_result_menu); self.theme.style_menu(self.special_result_menu)
        self.special_result_button.grid(row=0, column=1, rowspan=2, sticky="ne", padx=(10, 0))
        self.board_keyboard_hint = ttk.Label(
            self.board_navigation,
            text=self._t("board.keyboard_hint"),
            style="ContextTitle.TLabel",
            justify="left",
            anchor="w",
            wraplength=640,
        )
        self.board_keyboard_hint.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        self.board_navigation.bind("<Configure>", self._resize_board_navigation, add="+")

        self.competition_board = CompetitionBoard(
            self.board_tab, self.palette, self._open_attempt_from_board, self._select_cell_from_board,
            self._mark_attempt_from_board, self._mark_empty_cell_from_board, self._delete_attempt_from_board,
            self._edit_measurement_from_board, self._show_attempt_editor,
        )
        self.theme.style_menu(self.competition_board.context_menu)
        self.competition_board.pack(fill="both", expand=True)

        footer = ttk.Frame(frame, style="Panel.TFrame")
        footer.pack(fill="x", pady=(6, 0))
        row = ttk.Frame(footer, style="Panel.TFrame"); row.pack(fill="x")
        for column in range(4):
            row.columnconfigure(column, weight=1, uniform="attempt-actions")
        self.open_attempt_button = ttk.Button(row, text=self._t("attempts.open"), command=self._open_attempt_from_recordings, style="MutedAction.TButton")
        self.open_attempt_button.grid(row=0, column=0, sticky="ew")
        self.export_button = ttk.Button(row, text=self._t("attempts.export"), command=self.export_current_attempt, style="MutedAction.TButton")
        self.export_button.grid(row=0, column=1, sticky="ew", padx=5)
        self.delete_button = ttk.Button(row, text=self._t("attempts.delete"), command=self.delete_current_attempt, style="MutedAction.TButton")
        self.delete_button.grid(row=0, column=2, sticky="ew")
        self.clear_button = ttk.Button(row, text=self._t("attempts.clear"), command=self.clear_all_recordings, style="MutedAction.TButton")
        self.clear_button.grid(row=0, column=3, sticky="ew", padx=(5, 0))
        for button in (self.open_attempt_button, self.export_button, self.delete_button, self.clear_button):
            button.state(["disabled"])
        return frame

    # ------------------------------------------------------------ hotkeys/tick
    def _install_hotkeys(self) -> None:
        actions = {
            "freeze_toggle": self.toggle_freeze,
            "return_live": self.return_live,
            "previous_frame": lambda: self.step_frame(-1),
            "next_frame": lambda: self.step_frame(1),
            "previous_attempt": lambda: self.select_relative_attempt(-1),
            "next_attempt": lambda: self.select_relative_attempt(1),
            "previous_athlete": lambda: self._select_competitor_delta(-1),
            "next_athlete": lambda: self._select_competitor_delta(1),
            "decision_not_decided": lambda: self.mark_decision(AttemptDecision.NOT_DECIDED),
            "decision_valid": lambda: self.mark_decision(AttemptDecision.VALID),
            "decision_foul": lambda: self.mark_decision(AttemptDecision.FOUL),
            "decision_review": lambda: self.mark_decision(AttemptDecision.REVIEW),
            "mark_passed": lambda: self.mark_special_result(AttemptDecision.PASSED),
            "add_marker": self.add_marker,
            "save_frame": self.save_current_frame,
            "export_attempt": self.export_current_attempt,
            "clear_all_recordings": self.clear_all_recordings,
            "toggle_attempts": self._hotkey_toggle_attempts,
            "toggle_competition_board": self._hotkey_toggle_board,
            "toggle_timeline": self._hotkey_toggle_timeline,
            "toggle_live_preview": self._hotkey_toggle_live,
            "toggle_fullscreen": self.toggle_fullscreen,
            "reset_view": self.reset_video_views,
            "toggle_guide": self.toggle_guide,
            "toggle_comparison": self.toggle_comparison,
            "start_competition_wizard": self.start_competition_wizard,
            "timer_toggle": self.toggle_athlete_timer,
            "open_top_view": self.open_top_view_projection,
        }
        if not (self.config.competition.enabled and self.config.competition.keyboard_competition_controls):
            for name in ("previous_athlete", "next_athlete", "mark_passed"):
                actions.pop(name, None)
        self.hotkeys.attach_tree()
        bindings = self.config.hotkeys.bindings if self.config.hotkeys.enabled else {}
        self.hotkeys.install(bindings, actions, key_override=self._handle_context_key)

    def _competition_board_keyboard_active(self) -> bool:
        if not (self.config.competition.enabled and self._attempts_pane_added):
            return False
        try:
            return self.side_notebook.select() == str(self.board_tab) and self.side_notebook.tab(self.board_tab, "state") != "hidden"
        except tk.TclError:
            return False

    def _handle_context_key(self, event: tk.Event) -> bool:
        if self._measurement_record_id:
            key = str(event.keysym)
            if key == "space":
                self._skip_measurement()
                return True
            if key in {"Return", "KP_Enter"}:
                self._save_measurement()
                return True
        if not self._competition_board_keyboard_active() or int(event.state) & 0x000D:
            return False
        # Horizontal arrows are reserved for replay frame stepping.  Only
        # vertical arrows navigate board rows; this keeps Left/Right
        # consistent whether focus is on the board or another panel.
        directions = {"Up": (0, -1), "Down": (0, 1)}
        direction = directions.get(str(event.keysym))
        if direction is not None:
            self.competition_board.move_focus(*direction)
            return True
        if str(event.keysym) in {"Return", "KP_Enter"}:
            self.competition_board.activate_focused()
            return True
        return False

    def _effective_preview_hz(self) -> int:
        p = self.config.performance
        if self._window_interacting:
            return 12
        if time.perf_counter() < self._menu_active_until:
            return 15
        try:
            if p.reduce_when_minimized and self.root.state() == "iconic":
                return 4
        except tk.TclError:
            pass
        hz = p.preview_refresh_hz
        if p.adaptive_enabled:
            stats = self.capture.stats()
            if stats.queue_depth > max(8, self.config.buffer.encoder_queue_size // 2) or stats.queue_drops:
                hz = min(hz, 12)
        return max(4, int(hz))

    def _schedule_tick(self) -> None:
        if self._closing: return
        hz = self._effective_preview_hz()
        if self._timeline_pane_added and not self._window_interacting:
            hz = max(hz, int(self.config.performance.timeline_refresh_hz))
        interval = max(4, round(1000 / hz))
        self._tick_job = self.root.after(interval, self._tick)

    def _schedule_trial_expiry_check(self) -> None:
        if self._closing or not self._evaluation_mode:
            return
        self._trial_expiry_job = self.root.after(1000, self._check_trial_expiry)

    def _check_trial_expiry(self) -> None:
        self._trial_expiry_job = None
        if self._closing or not self._evaluation_mode:
            return
        status = trial_status()
        if not status.active and not self._trial_expired:
            self._trial_expired = True
            self._lock_trial_configuration()
            if hasattr(self, "evaluation_banner"):
                self.evaluation_banner.configure(
                    text="Evaluation expired — activate LongJumpReplay to continue"
                    if self.config.general.language != "cs"
                    else "Zkušební režim vypršel — pro pokračování aktivujte LongJumpReplay"
                )
            self._build_menu()
            self.file_menu_button.configure(menu=self.file_menu)
            self.camera_menu_button.configure(menu=self.camera_menu)
            self.view_menu_button.configure(menu=self.view_menu)
            self._update_judging_controls()
            self.root.after_idle(self._show_trial_expiry_dialog)
        self._schedule_trial_expiry_check()

    def _lock_trial_configuration(self) -> None:
        self.config.competition.enabled = False
        self.config.competition.show_competition_board = False
        self.config.competition.decision_controls_enabled = False
        self.config.competition.event_export_enabled = False
        self.config.competition.auto_save_evidence = False
        self.config.display.show_decision_controls = False
        if hasattr(self, "var_show_board"):
            self.var_show_board.set(False)
        self._apply_visibility()
        if hasattr(self, "freeze_button"):
            self._set_system_paused_ui()

    def _show_trial_expiry_dialog(self) -> None:
        if self._closing or self._trial_expiry_dialog_open:
            return
        self._trial_expiry_dialog_open = True
        try:
            from .licensing import ensure_license_or_trial
            accepted = ensure_license_or_trial(self.root, self.config.general.language)
        finally:
            self._trial_expiry_dialog_open = False
        if accepted:
            self._evaluation_mode = False
            self._trial_expired = False
            self.config.competition = deepcopy(self._trial_competition_before_lock)
            self.config.display.show_decision_controls = self._trial_show_decisions_before_lock
            self.competition.update_config(self.config.competition)
            self.var_show_board.set(self.config.competition.show_competition_board)
            if hasattr(self, "evaluation_banner"):
                self.evaluation_banner.destroy()
            self._build_menu()
            self.file_menu_button.configure(menu=self.file_menu)
            self.camera_menu_button.configure(menu=self.camera_menu)
            self.view_menu_button.configure(menu=self.view_menu)
            self._apply_visibility()
            self.wizard_button.configure(state="normal")
            self._set_system_paused_ui()
            self._update_judging_controls()
        elif not self._closing:
            self._show_message("The evaluation is locked. Activate a paid licence or exit LongJumpReplay.", 12)

    def _preview_frame(self, frame: np.ndarray) -> np.ndarray:
        scale = float(self.config.performance.preview_scale)
        if scale >= .995:
            return frame
        h, w = frame.shape[:2]
        return cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)

    def _tick(self) -> None:
        if self._closing: return
        tick_started = time.perf_counter()
        self._process_action_queue(); self._process_event_queue()
        self._update_athlete_timer_display()
        now = time.perf_counter()
        suspended = self._window_interacting or now < self._menu_active_until
        try:
            minimized = self.config.performance.reduce_when_minimized and self.root.state() == "iconic"
        except tk.TclError:
            minimized = False
        live_frame, live_ts, live_index = self.capture.latest.get()
        if not suspended and not minimized and live_frame is not None and live_index != self._last_live_index:
            self._last_live_index = live_index
            preview = self._preview_frame(live_frame)
            show_live = self.live_canvas.winfo_manager() or not self.config.performance.pause_hidden_panels
            if show_live:
                self.live_canvas.set_frame(preview)
            if self.playback.mode is PlaybackMode.LIVE:
                self.replay_canvas.set_frame(preview)
                self._displayed_bgr = live_frame
                self._displayed_timestamp_ns = live_ts
                self._last_replay_key = ("live", live_index)
                self._update_auxiliary_views()

        if self._camera_starting and not self._camera_retrying:
            if live_frame is not None:
                self._finish_camera_start_feedback()
                if not self._startup_calibration_opened:
                    self._startup_calibration_opened = True
                    calibration_frame = live_frame.copy()
                    self.root.after_idle(lambda: self.open_board_calibration(startup=True, frame_bgr=calibration_frame))
                if self._system_pause_transition and not self._system_paused:
                    self._system_pause_transition = False
                    self._set_system_paused_ui()
                    self._show_message(self._t("system.resumed"), 5)
            elif now >= self._camera_start_deadline:
                self._finish_camera_start_feedback(timed_out=True)
                if self._system_pause_transition and not self._system_paused:
                    self._system_pause_transition = False
                    self._set_system_paused_ui()

        if self._camera_retrying and self._camera_retry_stop_complete:
            self._camera_retry_stop_complete = False
            self._camera_start_started_at = now
            self._camera_start_deadline = now + 10.0
            self.capture.start()
            self._start_camera_probe()
            self._camera_retrying = False

        if not suspended and not minimized and self.playback.mode is not PlaybackMode.LIVE:
            key = self._playback_key()
            if key != self._last_replay_key:
                media = self.playback.displayed_frame()
                if media.frame_bgr is not None:
                    self.replay_canvas.set_frame(self._preview_frame(media.frame_bgr))
                    self._displayed_bgr = media.frame_bgr
                    self._displayed_timestamp_ns = media.timestamp_ns
                    self._update_auxiliary_views()
                self._last_replay_key = key

        if not suspended and not minimized:
            self._update_video_labels()
            if (not self.config.performance.pause_hidden_panels or self._timeline_pane_added) and now - self._last_timeline_update >= 1 / max(1, self.config.performance.timeline_refresh_hz):
                self._last_timeline_update = now; self._update_timeline()
            if now - self._last_stats_update >= 1 / max(1, self.config.performance.status_refresh_hz):
                self._last_stats_update = now; self._update_status()
            if now - self._last_attempts_refresh >= 1 / max(1, self.config.performance.attempts_refresh_hz):
                self._last_attempts_refresh = now; self._refresh_attempts(); self._refresh_current_try()
        self._telemetry.record_ui_tick(time.perf_counter() - tick_started)
        self._schedule_tick()

    def _update_auxiliary_views(self) -> None:
        layout = self.config.display.layout
        if layout == "comparison" and self.playback.mode is not PlaybackMode.ATTEMPT:
            self.comparison_prev_canvas.set_frame(None); self.comparison_next_canvas.set_frame(None)
            self.comparison_prev_canvas.set_status("PREVIOUS FRAME", self.palette["muted"]); self.comparison_next_canvas.set_status("NEXT FRAME", self.palette["muted"])
        if layout == "board_detail" and self._displayed_bgr is not None:
            crop = self._crop_board_roi(self._displayed_bgr)
            self.board_canvas.set_frame(crop)
            self.board_canvas.set_status(self._t("overlay.board_detail"), self.palette["warning"])
        elif layout == "comparison" and self.playback.mode is PlaybackMode.ATTEMPT and self.playback.attempt_id is not None:
            offset = max(1, self.config.display.comparison_offset_frames)
            count = self.attempts.frame_count(self.playback.attempt_id)
            prev = self.attempts.get_frame(self.playback.attempt_id, max(0, self.playback.attempt_frame_index - offset))
            nxt = self.attempts.get_frame(self.playback.attempt_id, min(max(0, count - 1), self.playback.attempt_frame_index + offset))
            self.comparison_prev_canvas.set_frame(prev.frame_bgr)
            self.comparison_next_canvas.set_frame(nxt.frame_bgr)
            self.comparison_prev_canvas.set_status(f"−{offset} FRAME", self.palette["muted"])
            self.comparison_next_canvas.set_status(f"+{offset} FRAME", self.palette["muted"])

    def _crop_board_roi(self, frame: np.ndarray) -> np.ndarray:
        d = self.config.display
        h, w = frame.shape[:2]
        x0 = max(0, min(w - 1, int(d.board_roi_x * w))); y0 = max(0, min(h - 1, int(d.board_roi_y * h)))
        x1 = max(x0 + 1, min(w, int((d.board_roi_x + d.board_roi_width) * w)))
        y1 = max(y0 + 1, min(h, int((d.board_roi_y + d.board_roi_height) * h)))
        return frame[y0:y1, x0:x1].copy()

    # ---------------------------------------------------------- window motion
    def _on_root_configure(self, event) -> None:
        if self._closing or event.widget is not self.root: return
        try: geometry = self.root.geometry()
        except tk.TclError: return
        if geometry == self._last_root_geometry: return
        self._last_root_geometry = geometry
        self._begin_window_interaction()
        if self._window_interaction_job is not None:
            try: self.root.after_cancel(self._window_interaction_job)
            except tk.TclError: pass
        try: self._window_interaction_job = self.root.after(140, self._end_window_interaction)
        except tk.TclError: self._window_interaction_job = None

    def _all_video_canvases(self) -> tuple[VideoCanvas, ...]:
        return (self.replay_canvas, self.live_canvas, self.board_canvas, self.comparison_prev_canvas, self.comparison_next_canvas)

    def _begin_window_interaction(self) -> None:
        if self._window_interacting: return
        self._window_interacting = True
        for canvas in self._all_video_canvases(): canvas.set_render_suspended(True)
        self.timeline.set_render_suspended(True)

    def _end_window_interaction(self) -> None:
        self._window_interaction_job = None
        if self._closing: return
        self._window_interacting = False
        for canvas in self._all_video_canvases(): canvas.set_render_suspended(False)
        self.timeline.set_render_suspended(False)
        self._last_timeline_update = self._last_stats_update = self._last_attempts_refresh = 0.0
        self._update_video_labels(); self._update_timeline(); self._update_status()

    # -------------------------------------------------------------- rendering
    def _playback_key(self):
        if self.playback.mode is PlaybackMode.ATTEMPT:
            attempt = self.attempts.get_attempt(self.playback.attempt_id or -1)
            return ("attempt", self.playback.attempt_id, self.playback.attempt_frame_index, attempt.state if attempt else None, attempt.frame_count if attempt else 0)
        return ("buffer", self.playback.live_seq)

    def _update_video_labels(self) -> None:
        self._update_judging_controls()
        p = self.palette; stats = self.capture.stats()
        if self.config.capture.mode == "capture":
            self.freeze_button.configure(text="Stop recording" if self.attempts.is_recording else "Record")
            if self.attempts.is_recording:
                self.recording_var.set(f"● RECORDING {self.attempts.recording_elapsed_seconds():05.1f}s")
            elif self.recording_var.get().startswith("●"):
                self.recording_var.set("")
        else:
            self.freeze_button.configure(text=self._t("button.live") if self.playback.mode is not PlaybackMode.LIVE else self._t("button.freeze"))
        if self._system_paused:
            self.camera_waiting_frame.place_forget(); self.camera_action_frame.place_forget()
            self.mode_var.set(self._t("mode.paused")); self.mode_badge.configure(bg=p["muted"], fg="#ffffff")
            self.live_canvas.set_status(self._t("mode.paused"), p["muted"])
            self.replay_canvas.set_status(self._t("mode.paused"), p["muted"], self._t("system.paused_status"))
            return
        self._maybe_select_available_camera()
        no_video = (
            self.playback.mode is PlaybackMode.LIVE
            and self._displayed_bgr is None
            and not self._camera_starting
            and (self._camera_input_timed_out or bool(stats.last_error) or stats.captured_frames == 0)
        )
        self._update_camera_input_overlay(no_video)
        self.live_canvas.set_status(f"● LIVE · {stats.capture_fps:5.1f} fps", p["live"])
        if self.playback.mode is PlaybackMode.LIVE:
            self.mode_var.set(self._t("mode.live")); self.mode_badge.configure(bg=p["live"], fg="#ffffff")
            self.freeze_button.configure(text=self._t("button.freeze"))
            self.replay_canvas.set_status(f"● {self._t("overlay.live_review")}", p["live"], self._t("overlay.zoom_help"))
        elif self.playback.mode is PlaybackMode.LIVE_BUFFER:
            packet, newest = self.buffer.get(self.playback.live_seq), self.buffer.newest()
            offset = ((packet.timestamp_ns - newest.timestamp_ns) / 1e9) if packet and newest else 0
            self.mode_var.set(self._t("overlay.buffer_review")); self.mode_badge.configure(bg=p["warning"], fg="#111111")
            self.freeze_button.configure(text=self._t("button.live"))
            self.replay_canvas.set_status(f"{self._t("overlay.buffer")} · {offset:+.3f} s", p["warning"], self._t("overlay.frame_help"))
        else:
            attempt = self.attempts.get_attempt(self.playback.attempt_id or -1)
            label = f"{self._t("overlay.attempt")} #{attempt.attempt_id:02d}" if attempt else self._t("overlay.attempt")
            self.mode_var.set(label); self.mode_badge.configure(bg=p["warning"], fg="#111111")
            self.freeze_button.configure(text=self._t("button.live"))
            if attempt:
                rel = (self._displayed_timestamp_ns - attempt.freeze_timestamp_ns) / 1e9
                assist = f" · {self._t("overlay.assist")} {attempt.takeoff_confidence:.0%}" if attempt.takeoff_candidate_index is not None and self.config.display.show_takeoff_assist_badge else ""
                wall_ns = attempt.media_start_wall_time_ns + max(0, self._displayed_timestamp_ns - attempt.start_timestamp_ns) if attempt.media_start_wall_time_ns else 0
                wall = format_wall_time_ns(wall_ns) if wall_ns else f"+{rel:.3f}s"
                secondary = f"{self._attempt_roster_display(attempt)} · {wall} · {self._t("overlay.frame")} {self.playback.attempt_frame_index + 1}/{max(1, attempt.frame_count)} · {self._decision_display(attempt.decision)}{assist}"
                color = self._decision_color(attempt.decision)
                self.replay_canvas.set_status(label, color, secondary)

    def _update_status(self) -> None:
        if self._system_paused:
            self.camera_var.set(self._t("mode.paused")); self.clock_var.set(time.strftime("%H:%M:%S"))
            self.status_var.set(self._t("system.paused_status"))
            self.camera_warning_var.set("")
            return
        capture, buffer = self.capture.stats(), self.buffer.stats()
        cache_gb = self.attempts.cache_size_bytes() / 1024 ** 3
        self.camera_var.set(capture.source_description); self.clock_var.set(time.strftime("%H:%M:%S"))
        if self.config.capture.mode == "capture":
            capture_text = f"CAP {capture.capture_fps:5.1f} fps  ·  CAPTURE MODE"
        else:
            capture_text = f"CAP {capture.capture_fps:5.1f} fps  ·  BUFFER {capture.encode_fps:5.1f} fps / {buffer.duration_seconds:4.1f} s"
        self.status_var.set(
            f"{capture_text}  ·  RAM {buffer.memory_bytes / 1024 ** 2:,.0f} MB  ·  drops {capture.queue_drops}  ·  cache {cache_gb:.2f} GB"
        )
        warning = self._capture_quality_warning(capture)
        if self.config.display.show_capture_warnings and warning:
            self.camera_warning_var.set(self._compact_capture_warning(capture))
        else:
            self.camera_warning_var.set("")
        if not self._busy_depth and time.perf_counter() >= self._message_until: self.message_var.set(self.shuttle.status)
        if capture.last_error and capture.last_error != self._last_error:
            self._last_error = capture.last_error; self._show_message(f"Camera: {capture.last_error}", 8)

    def _begin_busy(self, message: str, *, mode: str = "indeterminate", delay_ms: int = 0) -> None:
        """Show non-blocking activity feedback in the status bar."""
        self._busy_depth += 1
        self._busy_message = message
        self.message_var.set(message)
        if not hasattr(self, "status_progress"):
            return
        self.status_progress.stop()
        self.status_progress.configure(mode=mode, value=0)
        def show() -> None:
            self._busy_show_job = None
            if not self._busy_depth:
                return
            self.status_progress.grid()
            if str(self.status_progress.cget("mode")) == "indeterminate":
                self.status_progress.start(12)
        if delay_ms:
            self._busy_show_job = self.root.after(delay_ms, show)
        else:
            show()

    def _update_camera_input_overlay(self, no_video: bool) -> None:
        waiting = self._camera_starting and self._displayed_bgr is None
        timed_out = no_video and (self._camera_input_timed_out or not self._camera_starting)
        if waiting:
            self.camera_waiting_progress.start(12)
            self.camera_waiting_frame.place(relx=.5, rely=.55, anchor="center")
            self.camera_waiting_frame.lift()
            self.camera_action_frame.place_forget()
            return
        self.camera_waiting_progress.stop()
        self.camera_waiting_frame.place_forget()
        if timed_out:
            self.camera_action_frame.place(relx=.5, rely=.61, anchor="center")
            self.camera_action_frame.lift()
        else:
            self.camera_action_frame.place_forget()

    def _set_camera_waiting_feedback(self) -> None:
        title, detail = camera_waiting_messages(
            self.translator,
            self.config.camera.source_type,
            self.config.camera.device_index,
            self._selected_camera_startup_feedback,
        )
        self.camera_waiting_title.configure(text=title)
        self.camera_waiting_detail.configure(text=detail)

    def _start_camera_probe(self) -> None:
        self._camera_probe_stop.set()
        probe_stop = Event()
        self._camera_probe_stop = probe_stop
        self._camera_probe_generation += 1
        generation = self._camera_probe_generation
        if self.config.camera.source_type != "camera":
            with self._camera_probe_lock:
                self._camera_probe_results = {}
            return
        base_config = replace(self.config.camera)
        with self._camera_probe_lock:
            self._camera_probe_results = {0: None, 1: None}

        def probe() -> None:
            for index in (0, 1):
                if probe_stop.is_set() or generation != self._camera_probe_generation:
                    return
                available = False
                source = OpenCVCameraSource(replace(base_config, device_index=index))
                try:
                    source.open()
                    available, frame = source.read()
                    available = bool(available and frame is not None)
                except Exception:
                    available = False
                finally:
                    source.close()
                if probe_stop.is_set() or generation != self._camera_probe_generation:
                    return
                with self._camera_probe_lock:
                    self._camera_probe_results[index] = available

        Thread(target=probe, name="camera-input-probe", daemon=True).start()

    def _maybe_select_available_camera(self) -> None:
        """Use the first working camera found during the initial all-sources check."""
        if (
            self._selected_camera_startup_feedback
            or self._camera_retrying
            or not self._camera_starting
            or self.config.camera.source_type != "camera"
        ):
            return
        live_frame, _, _ = self.capture.latest.get()
        if live_frame is not None:
            return
        with self._camera_probe_lock:
            probe_results = dict(self._camera_probe_results)
        selected_index = first_available_camera(probe_results)
        if selected_index is None or selected_index == self.config.camera.device_index:
            return

        self.config.camera.device_index = selected_index
        self.capture.camera_config.device_index = selected_index
        self._selected_camera_startup_feedback = True
        self._set_camera_waiting_feedback()
        self._save_config_safely()
        log_event(self._logger, "camera_auto_selected", device_index=selected_index)
        self._try_camera_again()

    def _try_camera_again(self) -> None:
        if self._camera_retrying or self._closing:
            return
        self._camera_retrying = True
        self._camera_retry_stop_complete = False
        self._camera_starting = True
        self._camera_start_started_at = 0.0
        self._camera_start_deadline = 0.0
        self._camera_input_timed_out = False
        self.capture.latest.clear()
        self._displayed_bgr = None
        self._displayed_timestamp_ns = 0
        self._last_live_index = -1

        def stop_capture() -> None:
            try:
                self.capture.stop(timeout=2.5)
            finally:
                self._camera_retry_stop_complete = True

        Thread(target=stop_capture, name="camera-retry", daemon=True).start()

    def _start_camera_with_feedback(self, message: str) -> None:
        """Start capture while keeping a visible, bounded activity indicator."""
        self._set_camera_waiting_feedback()
        self._camera_starting = True
        self._camera_start_started_at = time.perf_counter()
        self._camera_start_deadline = self._camera_start_started_at + 10.0
        self._camera_input_timed_out = False
        self.capture.start()
        self._start_camera_probe()

    def _finish_camera_start_feedback(self, timed_out: bool = False) -> None:
        if not self._camera_starting:
            return
        self._camera_starting = False
        self._camera_start_deadline = 0.0
        self._camera_input_timed_out = timed_out

    def _end_busy(self) -> None:
        self._busy_depth = max(0, self._busy_depth - 1)
        if self._busy_depth:
            return
        self._busy_message = ""
        if self._busy_show_job is not None:
            try: self.root.after_cancel(self._busy_show_job)
            except tk.TclError: pass
            self._busy_show_job = None
        if hasattr(self, "status_progress"):
            self.status_progress.stop()
            self.status_progress.grid_remove()

    def _update_athlete_timer_display(self) -> None:
        snapshot = self.athlete_timer.snapshot()
        p = self.palette
        background = p["surface2"]
        prefix = ""
        prefix_visible = False
        prefix_color = p["muted"]
        if snapshot.state is AthleteTimerState.READY:
            prefix = self._t("timer.ready")
            prefix_visible = True
            prefix_color = p["accent"] if int(time.monotonic() / 0.5) % 2 == 0 else background
            value_color = p["accent"]
        elif snapshot.state is AthleteTimerState.STOPPED:
            prefix = self._t("timer.stopped")
            prefix_visible = True
            value_color = p["accent"]
        elif snapshot.state is AthleteTimerState.EXPIRED:
            value_color = p["danger"]
        elif snapshot.remaining_seconds <= 10:
            value_color = p["warning"]
        else:
            value_color = p["accent"]
        signature = (snapshot.state, snapshot.remaining_seconds, snapshot.remaining_tenths, prefix, prefix_visible, prefix_color, value_color, background, p["border"])
        if signature == self._last_timer_render_signature:
            return
        self._last_timer_render_signature = signature
        self.timer_frame.configure(highlightbackground=p["border"], highlightcolor=p["accent"])
        self.timer_frame.configure(bg=background)
        self.timer_prefix_label.configure(bg=background)
        self.timer_value_label.configure(bg=background)
        # Precision is most useful while the clock is running. Keep the
        # stable READY/STOPPED/EXPIRED states compact for existing operator
        # layouts and accessibility snapshots.
        value = format_countdown_tenths(snapshot.remaining_tenths) if snapshot.state is AthleteTimerState.RUNNING else format_countdown(snapshot.remaining_seconds)
        self.timer_value_var.set(value)
        if prefix_visible:
            self.timer_prefix_var.set(prefix)
            if not self.timer_prefix_label.winfo_manager():
                self.timer_prefix_label.pack(side="left", before=self.timer_value_label, padx=(6, 5), pady=3)
            self.timer_prefix_label.configure(fg=prefix_color)
        else:
            if self.timer_prefix_label.winfo_manager():
                self.timer_prefix_label.pack_forget()
        self.timer_value_label.configure(fg=value_color)

    def toggle_athlete_timer(self) -> None:
        if self._system_paused:
            self._show_message(self._t("system.paused_message"), 5)
            return
        if self.athlete_timer.snapshot().state is AthleteTimerState.RUNNING:
            self.athlete_timer.stop()
        elif self.playback.mode is not PlaybackMode.LIVE:
            self._show_message(self._t("timer.live_only"), 5)
            return
        else:
            self.athlete_timer.start()
        self._update_athlete_timer_display()

    def _on_timer_click(self, _event: tk.Event | None = None) -> None:
        self.toggle_athlete_timer()

    def _set_system_paused_ui(self) -> None:
        paused_or_stopping = self._system_paused or self._system_pause_transition
        self.system_pause_button.configure(
            text=self._t("button.resume_system") if self._system_paused and not self._system_pause_transition else self._t("button.pause_system"),
            style="SystemResume.TButton" if self._system_paused and not self._system_pause_transition else "SystemPause.TButton",
        )
        self.system_pause_button.state(["disabled"] if self._system_pause_transition else ["!disabled"])
        state = ["disabled"] if paused_or_stopping or self._trial_expired else ["!disabled"]
        for button in (self.freeze_button,):
            button.state(state)
        self._update_judging_controls()
        self._update_video_labels()
        self._update_status()

    def _update_judging_controls(self) -> None:
        """Enable frame review and verdict controls only for a frozen attempt."""
        enabled = (
            not self._system_paused
            and not self._system_pause_transition
            and self.playback.mode is PlaybackMode.ATTEMPT
            and self.playback.attempt_id is not None
        )
        state = ["!disabled"] if enabled else ["disabled"]
        for button in (self.prev_frame_button, self.next_frame_button):
            button.state(state)
        self.top_view_button.state(state)
        for button in (self.not_decided_button, self.valid_button, self.foul_button, self.review_button):
            button.state(state)

        # Recordings actions follow the explicit selection in either the
        # Recordings list or the Competition Board. Export and Delete are
        # intentionally quiet until that target is a real attempt; Clear
        # becomes a red action only when temporary attempts exist.
        selected_attempt = (
            self._selected_action_attempt_id is not None
            and self.attempts.get_attempt(self._selected_action_attempt_id) is not None
        )
        trial_policy = capabilities_for() if self._evaluation_mode else None
        export_allowed = (
            (not self._evaluation_mode and not trial_is_active())
            or bool(trial_policy and trial_policy.permits("video_export") and trial_policy.exports_remaining > 0)
        )
        self.open_attempt_button.state(["!disabled"] if selected_attempt else ["disabled"])
        self.export_button.state(["!disabled"] if selected_attempt and export_allowed else ["disabled"])
        self.delete_button.state(["!disabled"] if selected_attempt else ["disabled"])
        self.open_attempt_button.configure(style="Control.TButton" if selected_attempt else "MutedAction.TButton")
        self.export_button.configure(style="Control.TButton" if selected_attempt and export_allowed else "MutedAction.TButton")
        self.delete_button.configure(style="Control.TButton" if selected_attempt else "MutedAction.TButton")
        has_temporary_recordings = any(not attempt.persistent for attempt in self.attempts.attempts())
        self.clear_button.state(["!disabled"] if has_temporary_recordings else ["disabled"])
        clear_style = "Danger.TButton" if has_temporary_recordings else "MutedAction.TButton"
        if self.clear_button.cget("style") != clear_style:
            self.clear_button.configure(style=clear_style)

    def toggle_system_pause(self) -> None:
        if self._system_pause_transition:
            return
        if self._system_paused:
            self._system_paused = False
            self._system_pause_transition = True
            self._last_live_index = -1
            self._last_replay_key = None
            self._start_camera_with_feedback(self._t("status.resuming"))
            self._set_system_paused_ui()
            log_event(self._logger, "system_resumed")
            return

        self._cancel_scheduled_review()
        self._system_paused = True
        self._system_pause_transition = True
        self.playback.go_live()
        self.athlete_timer.reset(); self._update_athlete_timer_display()
        self._begin_busy(self._t("status.pausing"), delay_ms=350)
        self._show_message(self._t("system.pausing"), 5)
        self._set_system_paused_ui()
        log_event(self._logger, "system_pause_requested")

        def stop_capture() -> None:
            alive = self.capture.stop(timeout=2.5)
            self.event_queue.put(("system_pause_complete", alive))

        Thread(target=stop_capture, name="camera-pause", daemon=True).start()

    def _capture_quality_warning(self, stats=None) -> str:
        stats = stats or self.capture.stats()
        issues = []
        target = max(1.0, self.config.camera.fps)
        if stats.captured_frames > 20 and stats.capture_fps > 0 and stats.capture_fps < target * .85:
            issues.append(f"capture {stats.capture_fps:.1f} fps, requested {target:.0f}")
        if stats.queue_drops: issues.append(f"{stats.queue_drops} dropped frame(s)")
        if stats.last_error: issues.append(stats.last_error)
        return " · ".join(issues)

    def _compact_capture_warning(self, stats=None) -> str:
        """Return a short warning suitable for the single-line status row."""
        stats = stats or self.capture.stats()
        target = max(1.0, self.config.camera.fps)
        issues = []
        if stats.captured_frames > 20 and stats.capture_fps > 0 and stats.capture_fps < target * .85:
            issues.append(f"LOW FPS {stats.capture_fps:.0f}/{target:.0f}")
        if stats.queue_drops:
            issues.append(f"DROPS {stats.queue_drops}")
        if stats.last_error:
            issues.append("CAMERA ERROR")
        return "! " + " | ".join(issues) if issues else ""

    def _update_timeline(self) -> None:
        oldest, newest = self.buffer.oldest(), self.buffer.newest()
        if self.playback.mode is PlaybackMode.ATTEMPT and self.playback.attempt_id is not None:
            attempt = self.attempts.get_attempt(self.playback.attempt_id)
            if not attempt or attempt.frame_count <= 0: return
            playhead = self._displayed_timestamp_ns or (attempt.start_timestamp_ns + int(self.playback.attempt_frame_index / max(1.0, attempt.fps) * 1e9))
            markers = [m.timestamp_ns for m in attempt.markers]
            predicted_frame_ns = None
            if attempt.takeoff_candidate_index is not None:
                predicted_frame_ns = attempt.start_timestamp_ns + int(attempt.takeoff_candidate_index / max(1.0, attempt.fps) * 1e9)
            model = TimelineModel(
                start_ns=attempt.start_timestamp_ns,
                end_ns=max(attempt.start_timestamp_ns + 1, attempt.end_timestamp_ns),
                playhead_ns=playhead,
                reference_ns=attempt.freeze_timestamp_ns,
                freeze_ns=attempt.freeze_timestamp_ns,
                markers_ns=tuple(markers),
                available_start_ns=attempt.start_timestamp_ns,
                available_end_ns=attempt.end_timestamp_ns,
                is_live=False,
                wall_start_ns=attempt.media_start_wall_time_ns or int(attempt.created_wall_time * 1_000_000_000),
                assist_start_ns=attempt.takeoff_analysis_start_ns,
                assist_end_ns=attempt.takeoff_analysis_end_ns,
                predicted_frame_ns=predicted_frame_ns,
                prediction_confidence=attempt.takeoff_confidence,
            )
        elif oldest and newest:
            packet = newest if self.playback.mode is PlaybackMode.LIVE else self.buffer.get(self.playback.live_seq)
            model = TimelineModel(
                oldest.timestamp_ns,
                newest.timestamp_ns,
                packet.timestamp_ns if packet else newest.timestamp_ns,
                newest.timestamp_ns,
                None,
                (),
                oldest.timestamp_ns,
                newest.timestamp_ns,
                self.playback.mode is PlaybackMode.LIVE,
                oldest.wall_time_ns,
            )
        else: model = None
        self.timeline.set_model(model)

    # ------------------------------------------------------------ competition
    def _refresh_competitor_selector(self) -> None:
        c = self.config.competition
        show_target = bool(c.enabled and c.show_competitor_selector)
        if show_target and not self.board_navigation.winfo_manager():
            self.board_navigation.pack(fill="x", pady=(0, 5), before=self.competition_board)
        elif not show_target and self.board_navigation.winfo_manager():
            self.board_navigation.pack_forget()
        group = self.competition.current_group()
        self.group_var.set(self._group_display(group))
        self.competitor_var.set(str(self.competition.current_competitor()))
        if c.enable_special_results and c.enabled:
            if not self.special_result_button.winfo_manager(): self.special_result_button.pack(side="right")
        elif self.special_result_button.winfo_manager():
            self.special_result_button.pack_forget()
        if c.wizard_button_visible and not self._operator_mode:
            if not self.wizard_button.winfo_manager(): self.wizard_button.pack(anchor="w", before=self.content_pane, pady=(0, 6))
        elif self.wizard_button.winfo_manager():
            self.wizard_button.pack_forget()
        if c.enabled and c.show_state_banner:
            if not self.competition_banner.winfo_manager(): self.competition_banner.pack(fill="x", before=self.content_pane, pady=(0, 6))
            self.competition_banner.configure(bg=self.palette["surface2"], fg=self.palette["text"])
        elif self.competition_banner.winfo_manager():
            self.competition_banner.pack_forget()
        self._refresh_current_try()

    def _refresh_current_try(self) -> None:
        attempts = self.attempts.attempts()
        assignment = self.competition.assignment_for_current(attempts)
        display_assignment = self._board_next_assignment if self.playback.mode is PlaybackMode.ATTEMPT and self._board_next_assignment else assignment
        if assignment:
            limit = self.competition.attempt_limit(assignment.group, assignment.competitor_number)
            self.current_try_var.set(self._t("competition.try", current=assignment.attempt_number, limit=limit))
            count = self.competition.competitor_count(assignment.group)
            phase_total = self.config.competition.final_attempts if assignment.phase == "final" else self.competition.qualification_limit(assignment.group, assignment.competitor_number)
            phase_round = assignment.attempt_number - self.competition.qualification_limit(assignment.group, assignment.competitor_number) if assignment.phase == "final" else assignment.attempt_number
            athlete_context = self.adjudication.athlete_for(assignment.group, assignment.competitor_number)
            identity = " · ".join(value for value in (athlete_context.bib, athlete_context.name) if value) or str(assignment.competitor_number)
            self.competition_banner_var.set(self._t("competition.banner", group=self._group_display(assignment.group), round=phase_round, total=phase_total, athlete=identity, count=count, attempt=assignment.attempt_number))
        else:
            self.current_try_var.set(self._t("competition.roster_disabled"))
            self.competition_banner_var.set("")
        if display_assignment:
            limit = self.competition.attempt_limit(display_assignment.group, display_assignment.competitor_number)
            self.board_target_var.set(
                self._t(
                    "board.target",
                    athlete=int(display_assignment.competitor_number),
                    attempt=display_assignment.attempt_number,
                    limit=limit,
                )
            )
        else:
            self.board_target_var.set(self._t("competition.roster_disabled"))
        self._refresh_competition_board(attempts, assignment)

    def _refresh_competition_board(self, attempts: list[AttemptSession], assignment: RosterAssignment | None) -> None:
        if not hasattr(self, "competition_board"):
            return
        group = self.competition.current_group()
        board_assignment = assignment
        if self.playback.mode is PlaybackMode.ATTEMPT and self.playback.attempt_id is not None:
            frozen_attempt = self.attempts.get_attempt(self.playback.attempt_id)
            if frozen_attempt and frozen_attempt.competitor_number > 0 and frozen_attempt.competitor_attempt_number > 0:
                board_assignment = RosterAssignment(
                    frozen_attempt.competitor_group, frozen_attempt.competitor_number,
                    frozen_attempt.competitor_attempt_number, frozen_attempt.competition_phase,
                )
        athlete = board_assignment.competitor_number if board_assignment else self.competition.current_competitor()
        # Keep the board focused on the first actionable cell at startup,
        # rather than leaving athlete 1 visually unselected until an attempt
        # has already been recorded.
        attempt_no = board_assignment.attempt_number if board_assignment else 1
        adjudication_by_attempt = {
            attempt.attempt_id: self.adjudication.get_for_attempt(attempt)
            for attempt in attempts
        }
        signature = (
            group, athlete, attempt_no, self.config.competition.enabled, self.config.competition.show_competition_board,
            self.config.general.language,
            self.config.competition.boys_competitors, self.config.competition.girls_competitors,
            self.config.competition.default_attempts_per_competitor, self.config.competition.final_round_enabled,
            self.config.competition.final_attempts, tuple(self.config.competition.finalist_numbers_by_group.get(group, [])),
            tuple(
                (
                    attempt.attempt_id,
                    attempt.decision.value,
                    attempt.competitor_number,
                    attempt.competitor_attempt_number,
                    adjudication_by_attempt[attempt.attempt_id].distance_cm
                    if adjudication_by_attempt[attempt.attempt_id]
                    else None,
                )
                for attempt in attempts
            ),
        )
        if signature == self._last_board_signature:
            return
        self._last_board_signature = signature
        athlete_labels: dict[int, str] = {}
        count = self.competition.competitor_count(group)
        for number in range(1, count + 1):
            context = self.adjudication.athlete_for(group, number)
            parts = [context.bib or f"#{number:02d}"]
            if context.name: parts.append(context.name)
            athlete_labels[number] = "  ".join(parts)
        attempt_values: dict[int, str] = {}
        for attempt in attempts:
            record = adjudication_by_attempt[attempt.attempt_id]
            if record and record.distance_cm is not None and attempt.decision is AttemptDecision.VALID:
                attempt_values[attempt.attempt_id] = str(record.distance_cm)
        self.competition_board.set_data(
            self.config.competition, group, attempts, athlete, attempt_no, self.config.general.language,
            athlete_labels=athlete_labels, attempt_values=attempt_values,
        )

    def _group_changed(self, _event=None) -> None:
        group = self._group_internal(self.group_var.get())
        try: self.competition.set_current(group, self.config.competition.current_competitor_by_group.get(group, 1))
        except ValueError: return
        self._board_next_assignment = None; self.competition_board.clear_focus()
        self.athlete_timer.reset(); self._update_athlete_timer_display()
        self._last_board_signature = None; self._refresh_competitor_selector(); self._save_config_safely()

    def _competitor_changed(self, _event=None) -> None:
        try: self.competition.set_current(self._group_internal(self.group_var.get()), int(self.competitor_var.get()))
        except (ValueError, TypeError): return
        self._board_next_assignment = None; self.competition_board.clear_focus()
        self.athlete_timer.reset(); self._update_athlete_timer_display()
        self._last_board_signature = None; self._refresh_current_try(); self._save_config_safely()

    def _select_competitor_delta(self, delta: int) -> None:
        if not self.config.competition.enabled: return
        group = self.competition.current_group(); count = self.competition.competitor_count(group)
        if count <= 0: return
        current = self.competition.current_competitor()
        self.competition.set_current(group, ((current - 1 + delta) % count) + 1)
        self._board_next_assignment = None; self.competition_board.clear_focus()
        self.athlete_timer.reset(); self._update_athlete_timer_display()
        self._last_board_signature = None; self._refresh_competitor_selector(); self._save_config_safely()

    def _select_cell_from_board(self, athlete: int, attempt_no: int) -> None:
        # An empty cell is a new target, not the previously opened recording.
        self._selected_action_attempt_id = None
        self._board_next_assignment = None
        group = self.competition.current_group()
        assignment = self.competition.select_attempt_cell(group, athlete, attempt_no)
        if assignment is None:
            try: self.competition.set_current(group, athlete)
            except ValueError:
                self._update_judging_controls()
                return
        self.athlete_timer.reset(); self._update_athlete_timer_display()
        self._last_board_signature = None; self._refresh_competitor_selector(); self._save_config_safely()
        self._update_judging_controls()

    def _open_attempt_from_board(self, attempt_id: int) -> None:
        self._cancel_scheduled_review()
        if self.playback.select_attempt(attempt_id):
            self._selected_action_attempt_id = attempt_id
            self._last_replay_key = None; self.timeline.detail_center_ns = None; self._clear_assist_warning(); self._refresh_attempts()
            self._update_judging_controls()

    def _mark_attempt_from_board(self, attempt_id: int, decision: AttemptDecision) -> None:
        attempt = self.attempts.get_attempt(attempt_id)
        if attempt is None:
            return
        try:
            record = self._ensure_adjudication_record(attempt)
            self.adjudication.record_verdict(
                record.record_id, decision.value,
                frame_index=record.selected_frame_index if record.selected_frame_index is not None else attempt.freeze_frame_index,
                frame_timestamp_ns=record.selected_frame_timestamp_ns or attempt.freeze_timestamp_ns,
                board_reference=self._board_reference_state(),
            )
        except (DurabilityError, KeyError) as exc:
            self._show_message(f"The verdict could not be stored safely: {exc}", 10)
            return
        if not self.attempts.set_decision(attempt_id, decision):
            return
        attempt = self.attempts.get_attempt(attempt_id)
        self._show_message(self._t("message.decision_marked", roster=self._attempt_roster_display(attempt), decision=self._decision_display(decision).upper()), 5)
        self._last_board_signature = None; self._last_attempts_refresh = 0; self._refresh_attempts()

    def _mark_empty_cell_from_board(self, athlete: int, attempt_no: int, decision: AttemptDecision) -> None:
        group = self.competition.current_group()
        existing = max((
            attempt for attempt in self.attempts.attempts()
            if attempt.competitor_group == group
            and attempt.competitor_number == athlete
            and attempt.competitor_attempt_number == attempt_no
        ), key=lambda attempt: attempt.created_wall_time, default=None)
        if existing is not None:
            self._mark_attempt_from_board(existing.attempt_id, decision)
            return
        qualification_limit = self.competition.qualification_limit(group, athlete)
        phase = "qualification" if attempt_no <= qualification_limit else "final"
        created = self.attempts.create_placeholder_attempt(group, athlete, attempt_no, decision, phase)
        try:
            record = self._ensure_adjudication_record(created)
            self.adjudication.record_verdict(
                record.record_id, decision.value, frame_index=None,
                frame_timestamp_ns=0, board_reference=self._board_reference_state(),
            )
        except (DurabilityError, KeyError) as exc:
            self.attempts.delete(created.attempt_id, force=True)
            self._show_message(f"The result could not be stored safely: {exc}", 10)
            return
        self._show_message(self._t(
            "message.decision_marked", roster=self._attempt_roster_display(created),
            decision=self._decision_display(decision).upper(),
        ), 5)
        self._last_board_signature = None; self._last_attempts_refresh = 0
        self._refresh_attempts(); self._refresh_current_try()

    def _delete_attempt_from_board(self, attempt_id: int) -> None:
        if self.config.general.confirm_destructive_actions and not ask_themed_yes_no(
            self.root, self._t("dialog.delete.title"), self._t("dialog.delete.text", attempt=attempt_id),
        ):
            return
        if self.playback.attempt_id == attempt_id:
            self._enter_live(complete_rotation=False)
        attempt = self.attempts.get_attempt(attempt_id)
        record = self.adjudication.get_for_attempt(attempt) if attempt else None
        if self.attempts.delete(attempt_id, force=True):
            if record:
                try: self.adjudication.mark_media_unavailable(record.record_id)
                except DurabilityError as exc: self._show_message(f"Result retained in memory; storage warning: {exc}", 8)
            self.competition_board.clear_focus(); self._last_board_signature = None; self._refresh_attempts(); self._refresh_current_try()
        else:
            self._show_message(self._t("board.delete_failed"), 5)

    # ------------------------------------------------------------ attempt log
    def _decision_tag(self, decision: AttemptDecision) -> str:
        if decision is AttemptDecision.VALID: return "valid"
        if decision is AttemptDecision.FOUL: return "foul"
        if decision is AttemptDecision.REVIEW: return "review"
        return "pending"

    def _attempt_roster_display(self, attempt: AttemptSession | None) -> str:
        if attempt is None:
            return self._t("roster.unassigned")
        if not attempt.competitor_group or attempt.competitor_number <= 0:
            return self._t("roster.unassigned")
        group = self._group_display(attempt.competitor_group)
        if attempt.competitor_attempt_number > 0:
            return self._t("roster.label", group=group, athlete=attempt.competitor_number, attempt=attempt.competitor_attempt_number)
        return f"{group} #{attempt.competitor_number}"

    def _media_state_display(self, state: AttemptState) -> str:
        return self._t({
            AttemptState.COLLECTING: "media.collecting", AttemptState.ENCODING: "media.encoding",
            AttemptState.READY: "media.ready", AttemptState.EXPORTING: "media.exporting",
            AttemptState.EXPORTED: "media.exported", AttemptState.ERROR: "media.error",
        }.get(state, "media.error"))

    def _decision_display(self, decision: AttemptDecision) -> str:
        mapping = {
            AttemptDecision.NOT_DECIDED: "status.not_decided", AttemptDecision.VALID: "status.valid",
            AttemptDecision.FOUL: "status.foul", AttemptDecision.REVIEW: "status.review",
            AttemptDecision.PASSED: "status.passed", AttemptDecision.MISSING: "status.missing",
            AttemptDecision.WITHDRAWN: "status.withdrawn", AttemptDecision.REATTEMPT: "status.reattempt",
        }
        return self._t(mapping.get(decision, "status.not_decided"))

    def _refresh_attempts(self) -> None:
        attempts = self.attempts.attempts()
        visible_attempts = attempts
        ids = {str(a.attempt_id) for a in visible_attempts}
        for item in self.attempt_tree.get_children():
            if item not in ids: self.attempt_tree.delete(item)
        p = self.palette
        self.attempt_tree.tag_configure("valid", background=p["valid_soft"])
        self.attempt_tree.tag_configure("foul", background=p["foul_soft"])
        self.attempt_tree.tag_configure("review", background=p["review_soft"])
        self.attempt_tree.tag_configure("pending", background=p["pending_soft"])
        now = time.time(); selected_id = None
        for row_index, attempt in enumerate(reversed(visible_attempts)):
            iid = str(attempt.attempt_id)
            created = time.strftime("%H:%M:%S", time.localtime(attempt.created_wall_time))
            ttl = "Saved" if attempt.persistent else (self._t("common.open") if attempt.selected else self._format_ttl(attempt.seconds_until_expiry(now)))
            media = "Saved" if attempt.persistent and attempt.state in {AttemptState.READY, AttemptState.EXPORTED} else self._media_state_display(attempt.state)
            if attempt.quality_warning: media = "⚠ " + media
            group = self._group_display(attempt.competitor_group)[:1] if attempt.competitor_group else "—"
            athlete = attempt.competitor_number if attempt.competitor_number else "—"
            try_no = attempt.competitor_attempt_number if attempt.competitor_attempt_number else "—"
            record = self.adjudication.get_for_attempt(attempt)
            distance = str(record.distance_cm) if record and record.distance_cm is not None else "—"
            wind = f"{record.wind_tenths / 10:+.1f}" if record and record.wind_tenths is not None else "—"
            duration = f"{attempt.duration_seconds:.1f}s"
            values = (f"#{attempt.attempt_id:02d}", group, athlete, try_no, self._decision_display(attempt.decision), distance, wind, created, duration, media, ttl)
            tag = self._decision_tag(attempt.decision)
            image = self._thumbnail_images.get(attempt.attempt_id, self._thumbnail_fallback)
            if self.attempt_tree.exists(iid): self.attempt_tree.item(iid, values=values, tags=(tag,), image=image)
            else: self.attempt_tree.insert("", "end", iid=iid, values=values, tags=(tag,), image=image)
            self.attempt_tree.move(iid, "", row_index)
            if attempt.selected: selected_id = iid
            self.thumbnail_worker.request(attempt.attempt_id, attempt.temp_video_path, self._preferred_thumbnail_frame(attempt))
        if selected_id and self.attempt_tree.selection() != (selected_id,):
            self.attempt_tree.selection_set(selected_id); self.attempt_tree.see(selected_id)
        decided = sum(a.decision in {AttemptDecision.VALID, AttemptDecision.FOUL, AttemptDecision.REVIEW} for a in attempts)
        summary = self._t("attempts.summary", count=len(attempts), decided=decided) if attempts else self._t("attempts.none")
        self.attempt_summary_var.set(summary)
        self._sync_recording_selection_style()
        self._refresh_competition_board(attempts, self.competition.assignment_for_current(attempts))

    @staticmethod
    def _preferred_thumbnail_frame(attempt: AttemptSession) -> int:
        if attempt.thumbnail_frame_index is not None:
            return int(attempt.thumbnail_frame_index)
        if attempt.takeoff_candidate_index is not None:
            return int(attempt.takeoff_candidate_index)
        return int(attempt.freeze_frame_index)

    def _sync_recording_selection_style(self) -> None:
        attempt = self.attempts.get_attempt(self._selected_recording_id() or -1)
        background = self.palette[{
            AttemptDecision.VALID: "valid_soft",
            AttemptDecision.FOUL: "foul_soft",
            AttemptDecision.REVIEW: "review_soft",
        }.get(attempt.decision if attempt else AttemptDecision.NOT_DECIDED, "pending_soft")]
        style = ttk.Style(self.root)
        style.map(
            "Recording.Treeview",
            background=[("selected", background)],
            foreground=[("selected", self.palette["text"])],
        )

    def _selected_recording_id(self) -> int | None:
        selection = self.attempt_tree.selection()
        if not selection:
            return None
        try:
            return int(selection[0])
        except (TypeError, ValueError):
            return None

    def _show_attempt_context_menu(self, event: tk.Event) -> str:
        row = self.attempt_tree.identify_row(event.y)
        if not row:
            return "break"
        return self._post_attempt_context_menu(row, event.x_root, event.y_root)

    def _post_attempt_context_menu(self, row: str, x_root: int, y_root: int) -> str:
        self.attempt_tree.selection_set(row)
        self.attempt_tree.focus(row)
        self._attempt_tree_selected(None)
        attempt_id = self._selected_recording_id()
        attempt = self.attempts.get_attempt(attempt_id or -1)
        if attempt is None:
            return "break"
        self.attempt_context_menu.entryconfigure(0, state="normal")
        self.attempt_context_menu.entryconfigure(1, state="normal")
        self.attempt_context_menu.entryconfigure(2, state="normal" if attempt.temp_video_path or attempt.state.name in {"COLLECTING", "ENCODING"} else "disabled")
        deletable = not attempt.protected and attempt.state.name not in {"COLLECTING", "ENCODING", "EXPORTING"}
        record = self.adjudication.get_for_attempt(attempt)
        can_measure = self._measurement_unavailable_reason(attempt, record) == ""
        self.attempt_context_menu.entryconfigure(self._recording_measurement_menu_index, state="normal" if can_measure else "disabled")
        self.attempt_context_menu.entryconfigure(self._recording_delete_menu_index, state="normal" if deletable else "disabled")
        if not can_measure:
            self._show_message(self._measurement_unavailable_reason(attempt, record), 6)
        try:
            self.attempt_context_menu.tk_popup(x_root, y_root)
        finally:
            self.attempt_context_menu.grab_release()
        return "break"

    def _show_attempt_keyboard_context_menu(self, _event: tk.Event) -> str:
        selection = self.attempt_tree.selection()
        if not selection:
            return "break"
        bbox = self.attempt_tree.bbox(selection[0])
        if not bbox:
            return "break"
        x, y, width, height = bbox
        return self._post_attempt_context_menu(
            selection[0],
            self.attempt_tree.winfo_rootx() + x + 4,
            self.attempt_tree.winfo_rooty() + y + height // 2,
        )

    def _open_attempt_from_recordings(self) -> None:
        attempt_id = self._selected_recording_id()
        if attempt_id is not None:
            self._open_attempt_from_board(attempt_id)

    def _open_attempt_editor_from_tree(self, _event: tk.Event | None = None) -> str:
        self._attempt_tree_selected(None)
        self._edit_attempt_from_recordings()
        return "break"

    def _edit_attempt_from_recordings(self) -> None:
        attempt_id = self._selected_recording_id()
        if attempt_id is not None:
            self._show_attempt_editor(attempt_id)

    def _mark_attempt_from_recordings(self, decision: AttemptDecision) -> None:
        attempt_id = self._selected_recording_id()
        if attempt_id is not None:
            self._mark_attempt_from_board(attempt_id, decision)

    def _export_attempt_from_recordings(self) -> None:
        attempt_id = self._selected_recording_id()
        if attempt_id is None:
            return
        self._selected_action_attempt_id = attempt_id
        self.export_current_attempt()

    def _delete_attempt_from_recordings(self) -> None:
        attempt_id = self._selected_recording_id()
        if attempt_id is None:
            return
        self._selected_action_attempt_id = attempt_id
        self.delete_current_attempt()

    def _edit_measurement_from_recordings(self) -> None:
        attempt_id = self._selected_recording_id()
        attempt = self.attempts.get_attempt(attempt_id or -1)
        record = self.adjudication.get_for_attempt(attempt) if attempt else None
        reason = self._measurement_unavailable_reason(attempt, record)
        if not reason and record:
            self._show_measurement_strip(record.record_id, continue_attempt_id=None)
        elif reason:
            self._show_message(reason, 7)

    def _edit_measurement_from_board(self, attempt_id: int) -> None:
        attempt = self.attempts.get_attempt(attempt_id)
        record = self.adjudication.get_for_attempt(attempt) if attempt else None
        reason = self._measurement_unavailable_reason(attempt, record)
        if not reason and record:
            self._show_measurement_popup(record.record_id)
        elif reason:
            self._show_message(reason, 7)

    def _measurement_unavailable_reason(self, attempt: AttemptSession | None, record=None) -> str:
        if not self.config.competition.enabled:
            return self._t("measurement.unavailable_judge_only")
        if attempt is None or record is None or record.verdict == AttemptDecision.NOT_DECIDED.value:
            return self._t("measurement.unavailable_undecided")
        if record.verdict != AttemptDecision.VALID.value:
            return self._t("measurement.unavailable_not_valid")
        return ""

    @staticmethod
    def _format_ttl(seconds: float) -> str:
        minutes, sec = divmod(max(0, int(seconds)), 60); return f"{minutes}:{sec:02d}"

    def _decision_color(self, decision: AttemptDecision) -> str:
        return {
            AttemptDecision.VALID: self.palette["live"], AttemptDecision.FOUL: self.palette["danger"],
            AttemptDecision.REVIEW: self.palette["warning"], AttemptDecision.NOT_DECIDED: self.palette["muted"],
            AttemptDecision.PASSED: self.palette["muted"], AttemptDecision.MISSING: self.palette["muted"],
            AttemptDecision.WITHDRAWN: self.palette["danger"], AttemptDecision.REATTEMPT: self.palette["warning"],
        }.get(decision, self.palette["muted"])

    # ----------------------------------------------------------- input/events
    def _process_action_queue(self) -> None:
        while True:
            try: action, amount = self.action_queue.get_nowait()
            except Empty: return
            if action == "step_frame": self.step_frame(amount)
            elif action == "select_attempt": self.select_relative_attempt(amount)
            elif action == "freeze_toggle": self.toggle_freeze()
            elif action == "return_live": self.return_live()
            elif action == "select_latest_capture": self.select_latest_capture()
            elif action == "hold_playback": self._set_hold_playback(bool(amount))
            elif action == "decision_not_decided": self.mark_decision(AttemptDecision.NOT_DECIDED)
            elif action == "decision_valid": self.mark_decision(AttemptDecision.VALID)
            elif action == "decision_foul": self.mark_decision(AttemptDecision.FOUL)
            elif action == "decision_review": self.mark_decision(AttemptDecision.REVIEW)
            elif action == "mark_passed": self.mark_special_result(AttemptDecision.PASSED)
            elif action == "previous_athlete": self._select_competitor_delta(-1)
            elif action == "next_athlete": self._select_competitor_delta(1)
            elif action == "add_marker": self.add_marker()
            elif action == "save_frame": self.save_current_frame()
            elif action == "export_attempt": self.export_current_attempt()

    def _process_event_queue(self) -> None:
        while True:
            try: event, payload = self.event_queue.get_nowait()
            except Empty: return
            if event == "attempt_created":
                self._show_message(self._t("message.attempt_pinned", attempt=int(payload)), 4); self._last_attempts_refresh = 0
            elif event == "attempt_ready":
                self._show_message(self._t("message.attempt_ready", attempt=int(payload)), 5); self._last_replay_key = None
            elif event == "attempt_exported":
                attempt_id, path = payload
                saved_path = str(Path(path).resolve())
                if str(self.status_progress.cget("mode")) == "determinate":
                    self.status_progress.configure(value=self.status_progress.cget("maximum"))
                self._end_busy()
                if trial_is_active():
                    try:
                        remaining = record_successful_export().exports_remaining
                        self._show_message(f"Attempt #{attempt_id:02d} saved to {saved_path} · trial exports remaining: {remaining}", 10)
                    except Exception as exc:
                        self._show_message(f"Attempt #{attempt_id:02d} exported, but trial state could not be updated: {exc}", 10)
                else:
                    self._show_message(f"Attempt #{attempt_id:02d} saved to {saved_path}", 10)
                self._update_judging_controls()
            elif event == "attempt_export_progress":
                attempt_id, copied, total = payload
                if total is None:
                    self.message_var.set(self._t("status.export_waiting", attempt=int(attempt_id)))
                    self.status_progress.stop(); self.status_progress.configure(mode="indeterminate")
                    self.status_progress.grid(); self.status_progress.start(12)
                else:
                    self.status_progress.stop()
                    maximum = max(1, int(total))
                    self.status_progress.configure(mode="determinate", maximum=maximum, value=min(int(copied), maximum - 1))
                    self.status_progress.grid()
                    self.message_var.set(self._t("status.export_bytes", copied=int(copied), total=int(total)))
            elif event == "attempt_error":
                attempt_id, error = payload; self._end_busy(); self._show_message(f"Attempt #{attempt_id:02d} error: {error}", 10)
            elif event == "takeoff_candidate":
                attempt_id, index, confidence = payload; self._handle_takeoff_candidate(int(attempt_id), int(index), float(confidence))
            elif event == "takeoff_failed":
                attempt_id, message = payload
                detail = str(message)
                self._set_assist_warning(int(attempt_id))
                self._show_message(detail, 8)
            elif event == "attempts_cleared":
                self._end_busy(); self._show_message(f"Cleared {int(payload)} temporary recording(s) and the live buffer.", 5)
            elif event == "recording_thumbnail_ready":
                attempt_id, path = payload
                try:
                    image = Image.open(path).convert("RGB")
                    self._thumbnail_images[int(attempt_id)] = ImageTk.PhotoImage(image)
                    item = str(int(attempt_id))
                    if self.attempt_tree.exists(item):
                        self.attempt_tree.item(item, image=self._thumbnail_images[int(attempt_id)])
                except (OSError, tk.TclError):
                    pass
            elif event == "recording_thumbnail_failed":
                # The neutral thumbnail remains visible; the media state and
                # the recording itself are still usable.
                self._logger.debug("recording_thumbnail_failed attempt=%s error=%s", payload[0], payload[1])
            elif event == "system_pause_complete":
                self._end_busy()
                self._system_pause_transition = False
                self.buffer.clear(); self.capture.latest.clear()
                self._displayed_bgr = None; self._displayed_timestamp_ns = 0
                self._last_live_index = -1; self._last_replay_key = None
                for canvas in self._all_video_canvases(): canvas.set_frame(None)
                self._set_system_paused_ui()
            elif event == "message": self._show_message(str(payload), 6)
            elif event in {"attempt_deleted", "attempt_updated", "attempt_selected"}: self._last_attempts_refresh = 0

    # ------------------------------------------------ durable adjudication
    def _board_reference_state(self) -> BoardReferenceState:
        display = self.config.display
        return BoardReferenceState(
            enabled=bool(display.guide_enabled),
            x_ratio=float(display.guide_x_ratio),
            y_ratio=float(display.guide_y_ratio),
            angle_deg=float(display.guide_angle_deg),
            width_px=int(display.guide_width_px),
            roi=[
                float(display.board_roi_x), float(display.board_roi_y),
                float(display.board_roi_width), float(display.board_roi_height),
            ],
        )

    def _ensure_adjudication_record(self, attempt: AttemptSession):
        record = self.adjudication.ensure_attempt(
            attempt,
            camera_source=self.capture.stats().source_description,
            board_reference=self._board_reference_state(),
        )
        if attempt.adjudication_record_id != record.record_id:
            self.attempts.set_adjudication_record_id(attempt.attempt_id, record.record_id)
        return record

    def _reconcile_adjudication_records(self) -> None:
        for attempt in self.attempts.attempts():
            try:
                self._ensure_adjudication_record(attempt)
            except DurabilityError as exc:
                self._durability_blocked_attempt_id = attempt.attempt_id
                self._logger.error("adjudication_recovery_failed attempt_id=%s error=%s", attempt.attempt_id, exc)

    def _show_measurement_strip(self, record_id: str, continue_attempt_id: int | None) -> None:
        record = self.adjudication.get(record_id)
        if record is None:
            return
        self._measurement_record_id = record_id
        self._measurement_continue_attempt_id = continue_attempt_id
        self.measurement_distance_var.set(str(record.distance_cm) if record.distance_cm is not None else "")
        self.measurement_wind_var.set(f"{record.wind_tenths / 10:+.1f}" if record.wind_tenths is not None else "")
        self.measurement_error_var.set("")
        if self.config.competition.prompt_wind_after_valid:
            self.measurement_wind_label.pack(side="left")
            self.measurement_wind_entry.pack(side="left", padx=(5, 12))
        else:
            self.measurement_wind_label.pack_forget()
            self.measurement_wind_entry.pack_forget()
        self.measurement_frame.grid()
        self.measurement_distance_entry.focus_set()
        self.measurement_distance_entry.selection_range(0, "end")

    def _hide_measurement_strip(self) -> tuple[str | None, int | None]:
        record_id = self._measurement_record_id
        continue_attempt_id = self._measurement_continue_attempt_id
        self._measurement_record_id = None
        self._measurement_continue_attempt_id = None
        self.measurement_error_var.set("")
        self.measurement_frame.grid_remove()
        try: self.root.focus_set()
        except tk.TclError: pass
        return record_id, continue_attempt_id

    def _save_measurement(self) -> None:
        if not self._measurement_record_id:
            return
        try:
            distance = parse_distance_centimetres(self.measurement_distance_var.get())
            wind = parse_wind_metres_per_second(self.measurement_wind_var.get()) if self.config.competition.prompt_wind_after_valid else None
            self.adjudication.set_measurement(self._measurement_record_id, distance_cm=distance, wind_tenths=wind)
        except (ValueError, KeyError, DurabilityError) as exc:
            self.measurement_error_var.set(self._t("measurement.invalid"))
            self._logger.warning("measurement_save_failed error=%s", exc)
            return
        _record_id, attempt_id = self._hide_measurement_strip()
        self._show_message(self._t("measurement.saved", distance=f"{distance} cm"), 4)
        self._last_attempts_refresh = 0
        if attempt_id is not None:
            self._finish_decision_workflow(attempt_id, force_next_athlete=True)

    def _skip_measurement(self) -> None:
        _record_id, attempt_id = self._hide_measurement_strip()
        if attempt_id is not None:
            self._finish_decision_workflow(attempt_id, force_next_athlete=True)

    def _finish_decision_workflow(self, attempt_id: int, force_next_athlete: bool = False) -> None:
        attempt = self.attempts.get_attempt(attempt_id)
        should_advance = force_next_athlete or self.config.competition.auto_advance_after_decision
        if self.config.competition.enabled and should_advance and attempt and not attempt.rotation_completed:
            self.attempts.set_rotation_completed(attempt_id, True)
            next_assignment = self.competition.advance(self.attempts.attempts())
            self._refresh_competitor_selector(); self._save_config_safely()
            if next_assignment and self.config.competition.next_athlete_overlay:
                self._show_next_athlete_overlay(next_assignment)
        self._last_attempts_refresh = 0; self._last_board_signature = None
        if force_next_athlete:
            if self._auto_live_job:
                try: self.root.after_cancel(self._auto_live_job)
                except tk.TclError: pass
                self._auto_live_job = None
            self._enter_live(complete_rotation=False)
            return
        if self.config.competition.auto_return_live:
            delay = max(0, int(self.config.competition.auto_return_delay_seconds * 1000))
            if self._auto_live_job:
                try: self.root.after_cancel(self._auto_live_job)
                except tk.TclError: pass
            self._auto_live_job = self.root.after(delay, self.return_live)

    def _show_measurement_popup(self, record_id: str) -> tk.Toplevel | None:
        record = self.adjudication.get(record_id)
        if record is None:
            return None
        if self._measurement_popup is not None and self._measurement_popup.winfo_exists():
            self._measurement_popup.destroy()
        dialog = tk.Toplevel(self.root)
        configure_popup(dialog, self.root)
        dialog.title(self._t("measurement.edit_title"))
        dialog.geometry("430x245")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        self._measurement_popup = dialog
        self._measurement_popup_distance_var = tk.StringVar(
            dialog, value=str(record.distance_cm) if record.distance_cm is not None else ""
        )
        self._measurement_popup_wind_var = tk.StringVar(
            dialog, value=f"{record.wind_tenths / 10:+.1f}" if record.wind_tenths is not None else ""
        )
        error_var = tk.StringVar(dialog, value="")

        card = ttk.Frame(dialog, style="Panel.TFrame", padding=18)
        card.pack(fill="both", expand=True, padx=12, pady=12)
        ttk.Label(card, text=self._t("measurement.edit_title"), style="PanelTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        ttk.Label(card, text=self._t("measurement.distance"), style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        distance_entry = ttk.Entry(card, textvariable=self._measurement_popup_distance_var, width=16)
        distance_entry.grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Label(card, text=self._t("measurement.wind"), style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(card, textvariable=self._measurement_popup_wind_var, width=16).grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Label(card, textvariable=error_var, style="Warning.TLabel").grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))
        actions = ttk.Frame(card, style="Panel.TFrame")
        actions.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))

        def close_popup() -> None:
            self._measurement_popup = None
            self._measurement_popup_save_button = None
            try: dialog.grab_release()
            except tk.TclError: pass
            dialog.destroy()

        def save_popup() -> None:
            try:
                distance = parse_distance_centimetres(self._measurement_popup_distance_var.get())
                wind = parse_wind_metres_per_second(self._measurement_popup_wind_var.get())
                self.adjudication.set_measurement(record_id, distance_cm=distance, wind_tenths=wind)
            except (ValueError, KeyError, DurabilityError) as exc:
                error_var.set(self._t("measurement.invalid"))
                self._logger.warning("measurement_popup_save_failed error=%s", exc)
                return
            close_popup()
            self._last_attempts_refresh = 0
            self._last_board_signature = None
            self._refresh_attempts()
            self._show_message(self._t("measurement.saved", distance=f"{distance} cm"), 4)

        ttk.Button(actions, text=self._t("settings.cancel"), command=close_popup).pack(side="right")
        self._measurement_popup_save_button = ttk.Button(
            actions, text=self._t("measurement.save_changes"), style="Accent.TButton", command=save_popup,
        )
        self._measurement_popup_save_button.pack(side="right", padx=(0, 7))
        dialog.protocol("WM_DELETE_WINDOW", close_popup)
        dialog.bind("<Escape>", lambda _event: close_popup())
        dialog.bind("<Return>", lambda _event: save_popup())
        card.columnconfigure(1, weight=1)
        distance_entry.focus_set()
        distance_entry.selection_range(0, "end")
        return dialog

    def _show_attempt_editor(self, attempt_id: int) -> tk.Toplevel | None:
        """Open the shared board/recordings editor for one synchronized attempt."""
        attempt = self.attempts.get_attempt(attempt_id)
        if attempt is None:
            return None
        self._open_attempt_from_board(attempt_id)
        attempt = self.attempts.get_attempt(attempt_id)
        if attempt is None:
            return None
        try:
            record = self._ensure_adjudication_record(attempt)
        except DurabilityError as exc:
            self._show_message(f"The attempt editor could not open safely: {exc}", 8)
            return None
        if self._attempt_editor is not None:
            try:
                if self._attempt_editor.winfo_exists():
                    self._attempt_editor.destroy()
            except tk.TclError:
                pass

        dialog = tk.Toplevel(self.root)
        configure_popup(dialog, self.root)
        dialog.title(self._t("attempt_editor.title", attempt=attempt_id))
        dialog.geometry("650x520")
        dialog.minsize(590, 480)
        dialog.transient(self.root)
        dialog.grab_set()
        self._attempt_editor = dialog

        verdict_var = tk.StringVar(dialog, value=self._decision_display(AttemptDecision(record.verdict)))
        distance_var = tk.StringVar(dialog, value=str(record.distance_cm) if record.distance_cm is not None else "")
        wind_var = tk.StringVar(dialog, value=f"{record.wind_tenths / 10:+.1f}" if record.wind_tenths is not None else "")
        helper_var = tk.StringVar(dialog, value="")
        error_var = tk.StringVar(dialog, value="")
        decisions = (
            AttemptDecision.NOT_DECIDED, AttemptDecision.VALID, AttemptDecision.FOUL,
            AttemptDecision.REVIEW, AttemptDecision.PASSED, AttemptDecision.MISSING,
            AttemptDecision.WITHDRAWN,
        )
        displays = tuple(self._decision_display(value) for value in decisions)

        body = ttk.Frame(dialog, style="App.TFrame", padding=16)
        body.pack(fill="both", expand=True)
        header = ttk.Frame(body, style="Panel.TFrame", padding=16)
        header.pack(fill="x")
        ttk.Label(header, text=self._t("attempt_editor.heading", attempt=attempt_id), style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text=f"{self._attempt_roster_display(attempt)}  ·  {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(attempt.created_wall_time))}  ·  {attempt.duration_seconds:.1f} s",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        details = ttk.Frame(body, style="Panel.TFrame", padding=16)
        details.pack(fill="both", expand=True, pady=(8, 0))
        details.columnconfigure(1, weight=1)
        media_path = str(attempt.temp_video_path.resolve()) if attempt.temp_video_path else self._t("attempt_editor.no_media")
        source = record.camera_source or self.capture.stats().source_description or "—"
        rows = (
            (self._t("attempt_editor.phase"), attempt.competition_phase.title()),
            (self._t("attempt_editor.media"), f"{self._media_state_display(attempt.state)}  ·  {attempt.frame_count} frames"),
            (self._t("attempt_editor.source"), source),
            (self._t("attempt_editor.path"), media_path),
        )
        row = 0
        for label, value in rows:
            ttk.Label(details, text=label, style="ContextTitle.TLabel").grid(row=row, column=0, sticky="nw", padx=(0, 14), pady=5)
            ttk.Label(details, text=value, style="Text.TLabel", wraplength=450, justify="left").grid(row=row, column=1, sticky="w", pady=5)
            row += 1

        ttk.Separator(details).grid(row=row, column=0, columnspan=2, sticky="ew", pady=10); row += 1
        ttk.Label(details, text=self._t("attempt_editor.verdict"), style="ContextTitle.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 14), pady=5)
        verdict_box = ttk.Combobox(details, state="readonly", values=displays, textvariable=verdict_var, width=24)
        verdict_box.grid(row=row, column=1, sticky="w", pady=5); row += 1
        ttk.Label(details, text=self._t("measurement.distance"), style="ContextTitle.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 14), pady=5)
        distance_entry = ttk.Entry(details, textvariable=distance_var, width=18)
        distance_entry.grid(row=row, column=1, sticky="w", pady=5); row += 1
        ttk.Label(details, text=self._t("measurement.wind"), style="ContextTitle.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 14), pady=5)
        wind_entry = ttk.Entry(details, textvariable=wind_var, width=18)
        wind_entry.grid(row=row, column=1, sticky="w", pady=5); row += 1
        ttk.Label(details, textvariable=helper_var, style="Muted.TLabel", wraplength=470, justify="left").grid(row=row, column=0, columnspan=2, sticky="w", pady=(5, 0)); row += 1
        ttk.Label(details, textvariable=error_var, style="Warning.TLabel").grid(row=row, column=0, columnspan=2, sticky="w", pady=(5, 0))

        def selected_decision() -> AttemptDecision:
            try:
                return decisions[displays.index(verdict_var.get())]
            except ValueError:
                return AttemptDecision.NOT_DECIDED

        def update_measurement_state(*_args) -> None:
            decision = selected_decision()
            enabled = self.config.competition.enabled and decision is AttemptDecision.VALID
            for widget in (distance_entry, wind_entry):
                widget.state(["!disabled"] if enabled else ["disabled"])
            if not self.config.competition.enabled:
                helper_var.set(self._t("measurement.unavailable_judge_only"))
            elif decision is AttemptDecision.NOT_DECIDED:
                helper_var.set(self._t("measurement.unavailable_undecided"))
            elif decision is not AttemptDecision.VALID:
                helper_var.set(self._t("measurement.unavailable_not_valid"))
            else:
                helper_var.set(self._t("attempt_editor.measurement_help"))

        def close_editor() -> None:
            self._attempt_editor = None
            try: dialog.grab_release()
            except tk.TclError: pass
            try: dialog.destroy()
            except tk.TclError: pass

        def save_editor() -> None:
            decision = selected_decision()
            distance = wind = None
            if self.config.competition.enabled and decision is AttemptDecision.VALID:
                try:
                    distance = parse_distance_centimetres(distance_var.get()) if distance_var.get().strip() else None
                    wind = parse_wind_metres_per_second(wind_var.get())
                except ValueError:
                    error_var.set(self._t("measurement.invalid"))
                    return
            self._mark_attempt_from_board(attempt_id, decision)
            fresh = self.attempts.get_attempt(attempt_id)
            fresh_record = self.adjudication.get_for_attempt(fresh) if fresh else None
            if fresh_record and self.config.competition.enabled and decision is AttemptDecision.VALID:
                try:
                    self.adjudication.set_measurement(fresh_record.record_id, distance_cm=distance, wind_tenths=wind)
                except (ValueError, KeyError, DurabilityError) as exc:
                    error_var.set(str(exc)); return
            self._last_attempts_refresh = 0; self._last_board_signature = None
            self._refresh_attempts()
            close_editor()

        def open_projection() -> None:
            close_editor()
            self.open_top_view_projection()

        footer = ttk.Frame(body, style="Toolbar.TFrame", padding=(10, 8))
        footer.pack(fill="x", pady=(8, 0))
        ttk.Button(footer, text=self._t("attempt_editor.projection"), command=open_projection, state="normal" if attempt.frame_count else "disabled").pack(side="left")
        ttk.Button(footer, text=self._t("attempt_editor.open_replay"), command=close_editor).pack(side="left", padx=(7, 0))
        ttk.Button(footer, text=self._t("attempts.export"), command=lambda: (close_editor(), self.export_current_attempt())).pack(side="left", padx=(7, 0))
        ttk.Button(footer, text=self._t("settings.cancel"), command=close_editor).pack(side="right")
        ttk.Button(footer, text=self._t("measurement.save_changes"), style="Accent.TButton", command=save_editor).pack(side="right", padx=(0, 7))

        verdict_var.trace_add("write", update_measurement_state)
        update_measurement_state()
        dialog.protocol("WM_DELETE_WINDOW", close_editor)
        dialog.bind("<Escape>", lambda _event: close_editor())
        return dialog

    # --------------------------------------------------------- core controls
    def _trial_action_allowed(self, capability: str, *, announce: bool = True) -> bool:
        if not self._evaluation_mode:
            return True
        if capabilities_for().permits(capability):
            return True
        if announce:
            self._show_message("The evaluation is locked. Activate a paid licence to continue.", 8)
        return False

    def _recording_assignment(self) -> RosterAssignment | None:
        assignment = self.competition.assignment_for_current(self.attempts.attempts())
        if self.config.competition.enabled and assignment is None and self._maybe_start_final_round():
            assignment = self.competition.assignment_for_current(self.attempts.attempts())
        return assignment

    def toggle_recording(self) -> None:
        if not self._trial_action_allowed("freeze") or self._system_paused:
            return
        self._cancel_scheduled_review()
        if self.attempts.is_recording:
            assignment = self._recording_assignment()
            attempt_id = self.attempts.stop_recording(
                competitor_group=assignment.group if assignment else "",
                competitor_number=assignment.competitor_number if assignment else 0,
                competitor_attempt_number=assignment.attempt_number if assignment else 0,
                competition_phase=assignment.phase if assignment else "qualification",
            )
            self._cancel_recording_auto_stop()
            self.recording_var.set("")
            if attempt_id is None:
                self._show_message("No encoded frames were available for this capture.", 5)
                return
            self._selected_action_attempt_id = attempt_id
            self.playback.select_attempt(attempt_id, at_freeze=False)
            attempt = self.attempts.get_attempt(attempt_id)
            if attempt is not None:
                try:
                    self._ensure_adjudication_record(attempt)
                    self._durability_blocked_attempt_id = None
                except DurabilityError as exc:
                    self._durability_blocked_attempt_id = attempt_id
                    self._show_message(f"Capture saved, but result storage is unavailable: {exc}", 10)
            self.competition_board.clear_focus()
            self.athlete_timer.stop(); self._update_athlete_timer_display()
            self._last_replay_key = None; self._last_board_signature = None
            self._refresh_attempts(); self._refresh_current_try()
            return
        assignment = self._recording_assignment()
        if self.config.competition.enabled and assignment is None:
            self._show_message("The selected athlete has completed all configured attempts. Select another athlete or configure the final round.", 7)
            return
        if not self.attempts.start_recording():
            return
        self.recording_var.set("● RECORDING")
        self._recording_auto_stop_job = self.root.after(
            max(1000, int(self.config.capture.max_duration_seconds * 1000)),
            self._auto_stop_recording,
        )
        self._show_message("Capture recording started.", 3)

    def _auto_stop_recording(self) -> None:
        self._recording_auto_stop_job = None
        if self.attempts.is_recording:
            self._show_message("Maximum capture duration reached; recording stopped.", 6)
            self.toggle_recording()

    def _cancel_recording_auto_stop(self) -> None:
        if self._recording_auto_stop_job:
            try: self.root.after_cancel(self._recording_auto_stop_job)
            except tk.TclError: pass
            self._recording_auto_stop_job = None

    def select_latest_capture(self) -> None:
        attempts = self.attempts.attempts()
        if attempts:
            self._open_attempt_from_board(attempts[-1].attempt_id)
            try: self.side_notebook.select(self.recordings_tab)
            except tk.TclError: pass

    def _set_hold_playback(self, pressed: bool) -> None:
        self._hold_playback = pressed
        if pressed:
            if self.playback.mode is not PlaybackMode.ATTEMPT:
                self.select_latest_capture()
            if self._hold_playback_job is None:
                self._hold_playback_tick()
        elif self._hold_playback_job:
            try: self.root.after_cancel(self._hold_playback_job)
            except tk.TclError: pass
            self._hold_playback_job = None

    def _hold_playback_tick(self) -> None:
        self._hold_playback_job = None
        if not self._hold_playback or self.playback.mode is not PlaybackMode.ATTEMPT:
            return
        self.step_frame(1)
        self._hold_playback_job = self.root.after(33, self._hold_playback_tick)

    def toggle_freeze(self) -> None:
        if self.config.capture.mode == "capture":
            self.toggle_recording()
            return
        if not self._trial_action_allowed("freeze"):
            return
        self._cancel_scheduled_review()
        if self._system_paused:
            self._show_message(self._t("system.paused_message"), 5)
            return
        if self.playback.mode is PlaybackMode.LIVE:
            assignment = self.competition.assignment_for_current(self.attempts.attempts())
            if self.config.competition.enabled and assignment is None:
                if self._maybe_start_final_round():
                    assignment = self.competition.assignment_for_current(self.attempts.attempts())
                if assignment is None:
                    self._show_message("The selected athlete has completed all configured attempts. Select another athlete or configure the final round.", 7)
                    return
            warning = self._capture_quality_warning() if self.config.display.show_capture_warnings else ""
            kwargs = dict(
                competitor_group=assignment.group if assignment else "",
                competitor_number=assignment.competitor_number if assignment else 0,
                competitor_attempt_number=assignment.attempt_number if assignment else 0,
                competition_phase=assignment.phase if assignment else "qualification",
                quality_warning=warning,
            )
            attempt_id = self.playback.freeze_to_new_attempt(**kwargs)
            if attempt_id is None:
                log_event(self._logger, "freeze_failed", reason="live_buffer_empty")
                self._show_message("The live buffer does not contain a frame yet.", 4); return
            self._selected_action_attempt_id = attempt_id
            attempt = self.attempts.get_attempt(attempt_id)
            if attempt is not None:
                try:
                    self._ensure_adjudication_record(attempt)
                    self._durability_blocked_attempt_id = None
                except DurabilityError as exc:
                    self._durability_blocked_attempt_id = attempt_id
                    log_event(self._logger, "adjudication_storage_failed", attempt_id=attempt_id, error=str(exc))
                    self._show_message("Critical: this attempt is pinned, but its result storage is unavailable. Do not advance until storage recovers.", 12)
            log_event(
                self._logger, "freeze_succeeded", attempt_id=attempt_id,
                competitor_number=assignment.competitor_number if assignment else 0,
                competitor_attempt_number=assignment.attempt_number if assignment else 0,
            )
            if assignment is not None and self.config.competition.auto_advance_on_attempt_complete:
                self._board_next_assignment = self.competition.next_assignment_after(self.attempts.attempts(), assignment)
            self.competition_board.clear_focus()
            self.athlete_timer.stop(); self._update_athlete_timer_display()
            self._last_replay_key = None; self._last_board_signature = None; self._refresh_attempts()
            self._clear_assist_warning()
            if self.config.takeoff_assist.enabled and self.config.display.board_roi_enabled:
                if self._takeoff_assist_entitled:
                    self._start_takeoff_analysis(attempt_id)
                else:
                    self._show_message("Take-off Assist is available with a Pro licence. Activate or upgrade to use it.", 8)
        else:
            self.return_live()

    def _complete_current_attempt_for_rotation(self) -> bool:
        if self.playback.mode is not PlaybackMode.ATTEMPT or self.playback.attempt_id is None:
            return True
        attempt = self.attempts.get_attempt(self.playback.attempt_id)
        if not attempt or not self.config.competition.enabled or attempt.competitor_number <= 0:
            return True
        if attempt.rotation_completed:
            return True
        if self._durability_blocked_attempt_id == attempt.attempt_id:
            try:
                self._ensure_adjudication_record(attempt)
                self._durability_blocked_attempt_id = None
            except DurabilityError:
                self._show_message("Result storage is still unavailable. The attempt remains pinned; retry before advancing.", 10)
                return False
        if self.config.competition.require_decision_before_continue and attempt.decision is AttemptDecision.NOT_DECIDED:
            self._show_message(self._t("dialog.decision_required"), 8)
            return False
        self.attempts.set_rotation_completed(attempt.attempt_id, True)
        if self.config.competition.auto_advance_on_attempt_complete:
            next_assignment = self.competition.advance(self.attempts.attempts())
            if next_assignment is None:
                self._maybe_start_final_round()
                next_assignment = self.competition.assignment_for_current(self.attempts.attempts())
            self._refresh_competitor_selector(); self._save_config_safely(); self._last_board_signature = None
            if next_assignment and self.config.competition.next_athlete_overlay:
                self._show_next_athlete_overlay(next_assignment)
        return True

    def _enter_live(self, complete_rotation: bool = True) -> bool:
        returning_from_replay = self.playback.mode is not PlaybackMode.LIVE
        if complete_rotation and not self._complete_current_attempt_for_rotation():
            return False
        self.playback.go_live(); self._last_replay_key = None
        if returning_from_replay:
            self.timeline.animate_return_to_live()
        else:
            self.timeline.detail_center_ns = None
        self._clear_assist_warning()
        self._selected_action_attempt_id = None
        self._board_next_assignment = None; self.competition_board.clear_focus(); self._last_board_signature = None
        if returning_from_replay:
            self.athlete_timer.reset(); self._update_athlete_timer_display()
        self._refresh_current_try()
        if returning_from_replay:
            log_event(self._logger, "returned_live", rotation_completed=complete_rotation)
        return True

    def return_live(self) -> None:
        if not self._trial_action_allowed("replay"):
            return
        if self._system_paused:
            self._show_message(self._t("system.paused_message"), 5); return
        if self._measurement_record_id:
            self._skip_measurement()
            return
        self._cancel_scheduled_review()
        self._enter_live(complete_rotation=True)

    def step_frame(self, delta: int) -> None:
        if not self._trial_action_allowed("replay"):
            return
        if self._system_paused:
            self._show_message(self._t("system.paused_message"), 5); return
        self._cancel_scheduled_review(); self.playback.step(delta); self._last_replay_key = None

    def select_relative_attempt(self, delta: int) -> None:
        if not self._trial_action_allowed("replay"):
            return
        self._cancel_scheduled_review()
        if self.playback.select_relative_attempt(delta):
            self._selected_action_attempt_id = self.playback.attempt_id
            self._last_replay_key = None; self.timeline.detail_center_ns = None; self._clear_assist_warning(); self._refresh_attempts()
            attempt = self.attempts.get_attempt(self.playback.attempt_id or -1)
            if attempt:
                self._show_message(f"{self._attempt_roster_display(attempt)} · {self._decision_display(attempt.decision)}", 2)

    def seek_timeline(self, timestamp_ns: int) -> None:
        if not self._trial_action_allowed("replay"):
            return
        self._cancel_scheduled_review(); self.playback.seek_timestamp(timestamp_ns); self._last_replay_key = None

    def _commit_timeline_zoom(self, seconds: float) -> None:
        value = max(60.0, min(3600.0, float(seconds)))
        if abs(self.config.timeline.detail_window_seconds - value) < .001:
            return
        self.config.timeline.detail_window_seconds = value
        self._save_config_safely()

    def _top_view_camera_signature(self) -> str:
        camera = self.config.camera
        file_path = str(Path(camera.file_path).resolve()) if camera.source_type == "file" and camera.file_path else ""
        return "|".join((camera.source_type, str(camera.device_index), camera.backend, camera.fourcc, file_path))

    def _stored_top_view_calibration(self) -> ProjectionCalibration | None:
        projection = self.config.top_view_projection
        if len(projection.board_corners) != 4 or len(projection.foul_line) != 2:
            return None
        try:
            return ProjectionCalibration(
                board_corners=tuple((float(point[0]), float(point[1])) for point in projection.board_corners),
                foul_line=tuple((float(point[0]), float(point[1])) for point in projection.foul_line),
                camera_signature=projection.camera_signature,
                reference_width=int(projection.reference_width), reference_height=int(projection.reference_height),
                pad_length_cm=float(projection.pad_length_cm), pad_width_cm=float(projection.pad_width_cm),
                shoe_width_cm=float(projection.shoe_width_cm),
                legal_side_flipped=bool(projection.legal_side_flipped),
                camera_profile=dict(projection.camera_profile) if projection.camera_profile else None,
            )
        except (IndexError, TypeError, ValueError):
            return None

    def _save_top_view_calibration(self, calibration: ProjectionCalibration) -> None:
        projection = self.config.top_view_projection
        projection.board_corners = [list(point) for point in calibration.board_corners]
        projection.foul_line = [list(point) for point in calibration.foul_line]
        projection.camera_signature = calibration.camera_signature
        projection.reference_width = calibration.reference_width
        projection.reference_height = calibration.reference_height
        projection.pad_length_cm = calibration.pad_length_cm
        projection.pad_width_cm = calibration.pad_width_cm
        projection.shoe_width_cm = calibration.shoe_width_cm
        projection.legal_side_flipped = calibration.legal_side_flipped
        projection.camera_profile = dict(calibration.camera_profile or {})
        self._save_config_safely()

    def _save_projection_foul_area(self, foul_area: tuple[tuple[float, float], ...]) -> None:
        if len(foul_area) != 4:
            return
        self.config.top_view_projection.foul_area = [list(point) for point in foul_area]
        self._sync_calibration_to_canvases()
        self._save_config_safely()

    def open_board_calibration(self, startup: bool = False, frame_bgr: np.ndarray | None = None) -> None:
        """Review saved geometry or auto-detect it from the current camera frame."""
        if self._closing:
            return
        if self._board_calibration_wizard is not None:
            try:
                self._board_calibration_wizard.window.lift()
                return
            except tk.TclError:
                self._board_calibration_wizard = None
        frame = frame_bgr if frame_bgr is not None else self._displayed_bgr
        if frame is None:
            if not startup:
                self._show_message(self._t("calibration.waiting_camera"), 5)
            return
        frame_size = (frame.shape[1], frame.shape[0])
        signature = self._top_view_camera_signature()
        stored = self._stored_top_view_calibration()
        previous = stored if calibration_matches(stored, signature, frame_size) else None
        projection = self.config.top_view_projection
        previous_foul_area = projection.foul_area if previous is not None else ()
        d = self.config.display
        self._board_calibration_wizard = BoardCalibrationWizard(
            self.root,
            self.palette,
            self.config.general.language,
            frame,
            (d.board_roi_x, d.board_roi_y, d.board_roi_width, d.board_roi_height),
            signature,
            previous,
            previous_foul_area,
            self._confirm_board_calibration,
            self._board_calibration_closed,
            lambda: (latest.copy() if (latest := self.capture.latest.get()[0]) is not None else None),
        )

    def _confirm_board_calibration(
        self,
        calibration: ProjectionCalibration,
        foul_area: tuple[tuple[float, float], ...],
    ) -> None:
        projection = self.config.top_view_projection
        projection.foul_area = [list(point) for point in foul_area]
        self._save_top_view_calibration(calibration)
        d = self.config.display
        x, y, width, height = board_search_roi(calibration.board_corners, margin_ratio=0.0)
        d.board_roi_x, d.board_roi_y = x, y
        d.board_roi_width, d.board_roi_height = width, height
        d.board_roi_enabled = True
        line = np.asarray(calibration.foul_line, dtype=np.float32)
        centre = line.mean(axis=0)
        vector = line[1] - line[0]
        d.guide_x_ratio, d.guide_y_ratio = float(centre[0]), float(centre[1])
        d.guide_angle_deg = float(math.degrees(math.atan2(float(vector[0]), float(vector[1]))))
        self._sync_calibration_to_canvases()
        self._save_config_safely()
        self._show_message(self._t("calibration.saved"), 5)

    def _board_calibration_closed(self) -> None:
        self._board_calibration_wizard = None

    def open_top_view_projection(self) -> None:
        if self.playback.mode is not PlaybackMode.ATTEMPT or self.playback.attempt_id is None:
            self._show_message(self._t("projection.freeze_first"), 5)
            return
        if self._top_view_loading_dialog is not None:
            try:
                self._top_view_loading_dialog.window.lift()
                return
            except tk.TclError:
                self._top_view_loading_dialog = None
        if self._top_view_window is not None:
            try:
                if self._top_view_window.window.winfo_exists():
                    self._top_view_window.window.lift()
                    self._top_view_window.window.focus_force()
                    return
            except tk.TclError:
                pass
            self._top_view_window = None
        attempt_id = int(self.playback.attempt_id)
        attempt = self.attempts.get_attempt(attempt_id)
        packets = self.attempts.packets_snapshot(attempt_id)
        if attempt is None or max(attempt.frame_count, len(packets)) <= 0:
            self._show_message(self._t("projection.no_frames"), 5)
            return
        frame_count = max(attempt.frame_count, len(packets))
        # Projection follows the frame currently shown to the operator.
        frame_index = self.playback.attempt_frame_index
        if frame_index is None:
            frame_index = attempt.freeze_frame_index
        frame_index = max(0, min(frame_count - 1, int(frame_index)))
        if self.attempts.set_thumbnail_frame(attempt_id, frame_index):
            self._thumbnail_images.pop(attempt_id, None)
            self._last_attempts_refresh = 0
        fps = max(1.0, float(attempt.fps))
        target_timestamp_ns = attempt.start_timestamp_ns + int(frame_index / fps * 1_000_000_000)
        candidate_frame_indices = (frame_index,)
        # Neighbours are hidden segmentation references only; they are never
        # offered as alternate frames to the operator.
        reference_indices = tuple(
            frame_index + delta
            for delta in (-3, -2, -1, 1, 2, 3)
            if 0 <= frame_index + delta < frame_count
        )
        current_signature = self._top_view_camera_signature()
        stored = self._stored_top_view_calibration()
        configured_roi = (self.config.display.board_roi_x, self.config.display.board_roi_y, self.config.display.board_roi_width, self.config.display.board_roi_height)
        loading_cancel = Event()
        self._top_view_loading_cancel = loading_cancel
        preview_frame = None if self._displayed_bgr is None else self._displayed_bgr.copy()
        if preview_frame is None:
            self._top_view_loading_cancel = None
            self._show_message(self._t("projection.no_decodable"), 6)
            return
        preview_size = (preview_frame.shape[1], preview_frame.shape[0])
        preview_matching = calibration_matches(stored, current_signature, preview_size)
        preview_calibration = stored if preview_matching else None
        preview_roi = board_search_roi(stored.board_corners) if preview_matching and stored is not None else configured_roi
        preview_warning = self._t("projection.camera_changed") if stored is not None and not preview_matching else ""
        preview_candidate = ProjectionCandidate(
            frame_index,
            self._displayed_timestamp_ns or target_timestamp_ns,
            preview_frame,
            1.0,
            0.0,
            0.0,
        )
        self._top_view_window = TopViewProjectionWindow(
            self.root, self.palette, self.config.general.language, attempt_id, packets, target_timestamp_ns,
            preview_roi, preview_calibration, preview_warning, current_signature,
            self._save_top_view_calibration,
            lambda selected_id: self._show_message(self._t("projection.ready_message").format(attempt=selected_id), 5),
            self._top_view_closed,
            candidates=(preview_candidate,), reference_frames=(), candidate_estimates={},
            foul_area=self.config.top_view_projection.foul_area if preview_calibration is not None else (),
            on_foul_area_saved=self._save_projection_foul_area,
            start_fullscreen=True,
            auto_start=False,
        )
        self._top_view_window.open_pending_review()
        result_queue: Queue[tuple[str, object]] = Queue()
        unique_references = tuple(index for index in dict.fromkeys(reference_indices) if index not in set(candidate_frame_indices))
        total_reads = max(1, len(candidate_frame_indices) + len(unique_references))

        def load_worker() -> None:
            decoded_frames: list[tuple[int, int, np.ndarray]] = []
            reference_frames: list[np.ndarray] = []
            read_count = 0
            for candidate_index in candidate_frame_indices:
                if loading_cancel.is_set(): return
                media = self.attempts.get_frame(attempt_id, candidate_index)
                read_count += 1
                if media.frame_bgr is not None:
                    decoded_frames.append((media.frame_index, media.timestamp_ns, media.frame_bgr))
                result_queue.put(("progress", (read_count / total_reads * 55.0, self._t("projection.decoding_detail").format(current=read_count, total=total_reads))))
            for reference_index in unique_references:
                if loading_cancel.is_set(): return
                media = self.attempts.get_frame(attempt_id, reference_index)
                read_count += 1
                if media.frame_bgr is not None:
                    reference_frames.append(media.frame_bgr)
                result_queue.put(("progress", (read_count / total_reads * 55.0, self._t("projection.decoding_detail").format(current=read_count, total=total_reads))))
            if not decoded_frames:
                result_queue.put(("error", self._t("projection.no_decodable"))); return
            local_target = next((timestamp for index, timestamp, _frame in decoded_frames if index == frame_index), target_timestamp_ns)
            frame_size = (decoded_frames[0][2].shape[1], decoded_frames[0][2].shape[0])
            matching = calibration_matches(stored, current_signature, frame_size)
            active_calibration = stored if matching else None
            projection_roi = board_search_roi(stored.board_corners) if matching and stored is not None else configured_roi
            result_queue.put(("progress", (72.0, self._t("projection.using_current_frame"))))
            candidates = [
                ProjectionCandidate(index, timestamp, frame, 1.0, 0.0, 0.0)
                for index, timestamp, frame in sorted(decoded_frames, key=lambda item: item[0])
            ]
            if not candidates:
                result_queue.put(("error", self._t("projection.no_decodable"))); return
            if not reference_frames:
                reference_frames = [frame for _index, _timestamp, frame in decoded_frames]
            estimates = {}
            warning = self._t("projection.camera_changed") if stored is not None and not matching else ""
            result_queue.put(("result", (candidates, reference_frames, estimates, local_target, projection_roi, active_calibration, warning)))

        def poll_loading() -> None:
            if loading_cancel.is_set(): return
            try:
                while True:
                    kind, payload = result_queue.get_nowait()
                    if kind == "progress" and self._top_view_window is not None:
                        value, detail = payload
                        self._top_view_window.update_loading_progress(float(value), str(detail))
                    elif kind == "error":
                        loading_cancel.set()
                        self._top_view_loading_cancel = None
                        if self._top_view_window is not None:
                            self._top_view_window._update_split_review_error(str(payload))
                        self._show_message(str(payload), 6)
                        return
                    elif kind == "result":
                        candidates, reference_frames, estimates, local_target, projection_roi, active_calibration, warning = payload
                        self._top_view_loading_dialog = None; self._top_view_loading_cancel = None
                        if self._top_view_window is not None:
                            self._top_view_window.begin_automatic_analysis(
                                candidates, reference_frames, estimates, local_target,
                                projection_roi, active_calibration, warning,
                            )
                        return
            except Empty:
                pass
            self.root.after(40, poll_loading)

        Thread(target=load_worker, name=f"projection-loader-{attempt_id}", daemon=True).start()
        self.root.after(40, poll_loading)

    def _top_view_closed(self) -> None:
        self._top_view_window = None

    def add_marker(self) -> None:
        if not self._trial_action_allowed("replay"):
            return
        if self._system_paused:
            self._show_message(self._t("system.paused_message"), 5); return
        if self.playback.mode is PlaybackMode.LIVE: self.toggle_freeze()
        if self.playback.mode is not PlaybackMode.ATTEMPT or self.playback.attempt_id is None:
            self._show_message("Markers belong to an attempt. Freeze first.", 4); return
        if self._displayed_timestamp_ns and self.attempts.add_marker(self.playback.attempt_id, self._displayed_timestamp_ns):
            self._show_message("Marker added.", 3); self._last_timeline_update = 0

    def mark_decision(self, decision: AttemptDecision) -> None:
        if not self._trial_action_allowed("judging", announce=False):
            self._show_message("Competition verdicts are disabled in the evaluation.", 6); return
        if self._system_paused:
            self._show_message(self._t("system.paused_message"), 5); return
        if not self.config.competition.decision_controls_enabled and not self.config.display.show_decision_controls: return
        if self.playback.mode is not PlaybackMode.ATTEMPT or self.playback.attempt_id is None:
            self._show_message("Freeze or select an attempt before recording a decision.", 5); return
        attempt_id = self.playback.attempt_id
        attempt = self.attempts.get_attempt(attempt_id)
        if attempt is None:
            return
        try:
            record = self._ensure_adjudication_record(attempt)
            record = self.adjudication.record_verdict(
                record.record_id,
                decision.value,
                frame_index=self.playback.attempt_frame_index,
                frame_timestamp_ns=self._displayed_timestamp_ns,
                board_reference=self._board_reference_state(),
            )
            self._durability_blocked_attempt_id = None
        except (DurabilityError, KeyError) as exc:
            self._durability_blocked_attempt_id = attempt_id
            log_event(self._logger, "verdict_storage_failed", attempt_id=attempt_id, error=str(exc))
            self._show_message("Critical: the verdict could not be stored safely. The attempt remains open; retry the verdict.", 12)
            return
        if not self.attempts.set_decision(attempt_id, decision): return
        log_event(self._logger, "decision_changed", attempt_id=attempt_id, decision=decision.value)
        attempt = self.attempts.get_attempt(attempt_id)
        if attempt and self.config.competition.auto_save_evidence and decision in {AttemptDecision.VALID, AttemptDecision.FOUL, AttemptDecision.REVIEW}:
            try:
                raw_path, annotated_path, metadata_path = self._save_evidence(attempt, decision)
                self.adjudication.set_evidence(
                    record.record_id,
                    raw_path=raw_path,
                    annotated_path=annotated_path,
                    metadata_path=metadata_path,
                )
            except Exception as exc: self._show_message(f"Evidence could not be saved: {exc}", 8)
        self._show_message(self._t("message.decision_marked", roster=self._attempt_roster_display(attempt) if attempt else f"#{attempt_id:02d}", decision=self._decision_display(decision).upper()), 5)
        if decision is AttemptDecision.VALID and self.config.competition.prompt_distance_after_valid:
            self._show_measurement_strip(record.record_id, continue_attempt_id=attempt_id)
        else:
            self._finish_decision_workflow(attempt_id)

    def mark_special_result(self, decision: AttemptDecision) -> None:
        if not self._trial_action_allowed("results", announce=False):
            self._show_message("Competition results are disabled in the evaluation.", 6); return
        if self._system_paused:
            self._show_message(self._t("system.paused_message"), 5); return
        if not self.config.competition.enabled or not self.config.competition.enable_special_results:
            self._show_message("Special competition results are disabled in Settings.", 5); return
        assignment = self.competition.assignment_for_current(self.attempts.attempts())
        if assignment is None:
            self._show_message("No pending attempt is available for the current athlete.", 5); return
        created = self.attempts.create_placeholder_attempt(assignment.group, assignment.competitor_number, assignment.attempt_number, decision, assignment.phase)
        try:
            record = self._ensure_adjudication_record(created)
            self.adjudication.record_verdict(record.record_id, decision.value, frame_index=None, frame_timestamp_ns=0, board_reference=self._board_reference_state())
        except (DurabilityError, KeyError) as exc:
            self.attempts.delete(created.attempt_id, force=True)
            self._show_message(f"The result could not be stored safely: {exc}", 10)
            return
        next_assignment = self.competition.advance(self.attempts.attempts())
        self._last_board_signature = None; self._refresh_competitor_selector(); self._refresh_attempts(); self._save_config_safely()
        if next_assignment and self.config.competition.next_athlete_overlay:
            self._show_next_athlete_overlay(next_assignment)

    def grant_reattempt(self) -> None:
        if not self._trial_action_allowed("judging", announce=False):
            self._show_message("Competition verdicts are disabled in the evaluation.", 6); return
        if self.playback.mode is not PlaybackMode.ATTEMPT or self.playback.attempt_id is None:
            self._show_message("Select the attempt that should be repeated.", 5); return
        attempt = self.attempts.get_attempt(self.playback.attempt_id)
        if not attempt or attempt.competitor_number <= 0:
            return
        try:
            record = self._ensure_adjudication_record(attempt)
            self.adjudication.record_verdict(
                record.record_id, AttemptDecision.REATTEMPT.value,
                frame_index=self.playback.attempt_frame_index,
                frame_timestamp_ns=self._displayed_timestamp_ns,
                board_reference=self._board_reference_state(),
            )
        except (DurabilityError, KeyError) as exc:
            self._show_message(f"The result could not be stored safely: {exc}", 10)
            return
        self.attempts.set_decision(attempt.attempt_id, AttemptDecision.REATTEMPT)
        self.attempts.set_counts_for_rotation(attempt.attempt_id, False)
        self.attempts.set_rotation_completed(attempt.attempt_id, True)
        self.competition.set_current(attempt.competitor_group, attempt.competitor_number)
        self.return_live(); self._last_board_signature = None; self._refresh_competitor_selector(); self._refresh_attempts()
        self._show_message(self._t("message.reattempt", roster=self._attempt_roster_display(attempt)), 5)

    def _maybe_start_final_round(self) -> bool:
        c = self.config.competition
        if not c.enabled or not c.final_round_enabled:
            return False
        group = self.competition.current_group()
        if self.competition.final_started(group):
            return False
        if not self.competition.qualification_complete(self.attempts.attempts(), group):
            return False
        if not c.finalist_numbers_by_group.get(group):
            self._open_finalist_selector(group)
        if c.finalist_numbers_by_group.get(group) and self.competition.start_final_round(group):
            self._show_message(f"{group} final round started with {len(c.finalist_numbers_by_group[group])} athlete(s).", 7)
            self._save_config_safely(); self._last_board_signature = None; self._refresh_competitor_selector()
            return True
        return False

    def _open_finalist_selector(self, group: str) -> None:
        dialog = tk.Toplevel(self.root); configure_popup(dialog, self.root); dialog.title("Select finalists"); dialog.geometry("430x560"); dialog.transient(self.root); dialog.grab_set()
        ttk.Label(dialog, text=f"Select up to {self.config.competition.finalists_count} {group} finalists", style="Title.TLabel").pack(anchor="w", padx=14, pady=(14, 6))
        ttk.Label(dialog, text="This replay tool does not measure distance, so qualification order is selected manually.", style="Muted.TLabel", wraplength=390, justify="left").pack(anchor="w", padx=14, pady=(0, 10))
        host = ttk.Frame(dialog, style="Panel.TFrame"); host.pack(fill="both", expand=True, padx=14)
        canvas = tk.Canvas(host, highlightthickness=0, background=self.palette["surface"]); bar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview); canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True); bar.pack(side="right", fill="y")
        inner = ttk.Frame(canvas, style="Panel.TFrame"); win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all"))); canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        def scroll(event=None, amount=None):
            delta = getattr(event, "delta", 0) if event is not None else 0
            units = amount if amount is not None else (-1 if delta >= 0 else 1)
            canvas.yview_scroll(units, "units")
            return "break"
        for widget in (canvas, inner):
            widget.bind("<MouseWheel>", scroll, add="+")
            widget.bind("<Button-4>", lambda _e: scroll(amount=-1), add="+")
            widget.bind("<Button-5>", lambda _e: scroll(amount=1), add="+")
        vars_: dict[int, tk.BooleanVar] = {}
        current = set(self.config.competition.finalist_numbers_by_group.get(group, []))
        for number in range(1, self.competition.competitor_count(group) + 1):
            var = tk.BooleanVar(value=number in current); vars_[number] = var
            check = ttk.Checkbutton(inner, text=f"Athlete #{number:02d}", variable=var); check.pack(anchor="w", pady=3, padx=8)
            check.bind("<MouseWheel>", scroll, add="+"); check.bind("<Button-4>", lambda _e: scroll(amount=-1), add="+"); check.bind("<Button-5>", lambda _e: scroll(amount=1), add="+")
        footer = ttk.Frame(dialog, style="Toolbar.TFrame", padding=8); footer.pack(fill="x", padx=14, pady=14)
        def apply_selection() -> None:
            selected = [n for n, var in vars_.items() if var.get()]
            if not selected:
                show_themed_info(dialog, "Select finalists", "Select at least one athlete."); return
            if len(selected) > self.config.competition.finalists_count:
                show_themed_info(dialog, "Select finalists", f"Select no more than {self.config.competition.finalists_count} athletes."); return
            self.competition.set_finalists(group, selected); dialog.destroy()
        ttk.Button(footer, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(footer, text="Use selected athletes", style="Accent.TButton", command=apply_selection).pack(side="right", padx=(0, 7))
        self.root.wait_window(dialog)

    def _show_next_athlete_overlay(self, assignment: RosterAssignment) -> None:
        self.center_overlay.configure(text=self._t("competition.next_overlay", group=self._group_display(assignment.group), athlete=assignment.competitor_number, attempt=assignment.attempt_number), bg=self.palette["surface2"], fg=self.palette["text"])
        self.center_overlay.place(relx=.5, rely=.5, anchor="center")
        self.root.after(1400, lambda: self.center_overlay.place_forget() if self.center_overlay.winfo_exists() else None)

    def save_current_frame(self) -> None:
        if self._evaluation_mode and not capabilities_for().permits("save_frame"):
            self._show_message("The evaluation is locked. Activate a paid licence to continue.", 8)
            return
        if self._displayed_bgr is None:
            self._show_message("No frame is available yet.", 4); return
        try:
            prefix = f"attempt_{self.playback.attempt_id:02d}" if self.playback.attempt_id else "live"
            path = save_bgr_png(self._displayed_bgr, self._exports_directory(), prefix=prefix)
            self._show_message(f"Frame saved: {path.name}", 6)
        except Exception as exc: show_themed_info(self.root, "Save frame", str(exc))

    def _save_evidence(self, attempt: AttemptSession, decision: AttemptDecision) -> tuple[Path | None, Path | None, Path]:
        frame_index = max(0, min(max(0, attempt.frame_count - 1), self.playback.attempt_frame_index))
        media = self.attempts.get_frame(attempt.attempt_id, frame_index)
        if media.frame_bgr is None:
            raise RuntimeError("The selected attempt frame is not available")
        # Resolve the frame from the selected attempt instead of trusting the
        # last GUI preview reference, which may belong to a different attempt
        # after a rapid selection change.
        frame = media.frame_bgr.copy()
        directory = self._evidence_directory(); directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")[:-3]
        roster = f"{attempt.competitor_group.lower()}-{attempt.competitor_number}_try-{attempt.competitor_attempt_number}" if attempt.competitor_number else f"attempt-{attempt.attempt_id}"
        base = directory / f"{roster}_{decision.value.lower()}_{stamp}"
        raw_path = None; annotated_path = None
        written: list[Path] = []
        try:
            if self.config.export.evidence_save_raw:
                raw_path = base.with_name(base.name + "_raw.png")
                self._write_evidence_png(frame, raw_path)
                written.append(raw_path)
            if self.config.export.evidence_include_overlay:
                annotated = frame.copy(); self._draw_evidence_overlay(annotated, attempt, decision, frame_index)
                annotated_path = base.with_name(base.name + "_annotated.png")
                self._write_evidence_png(annotated, annotated_path)
                written.append(annotated_path)
            metadata = {
                "attempt_id": attempt.attempt_id, "group": attempt.competitor_group, "competitor": attempt.competitor_number,
                "try": attempt.competitor_attempt_number, "decision": decision.value, "created_local": datetime.now().astimezone().isoformat(),
                "adjudication_record_id": attempt.adjudication_record_id,
                "frame_index": frame_index, "frame_timestamp_ns": media.timestamp_ns,
                "capture_fps": self.capture.stats().capture_fps, "quality_warning": attempt.quality_warning,
                "guide": {"x": self.config.display.guide_x_ratio, "y": self.config.display.guide_y_ratio, "angle_deg": self.config.display.guide_angle_deg},
                "board_roi": [self.config.display.board_roi_x, self.config.display.board_roi_y, self.config.display.board_roi_width, self.config.display.board_roi_height],
                "evidence_layers": {
                    "raw_file": "original camera pixels decoded from the retained attempt",
                    "annotated_file": "derived copy with software overlays",
                    "judge_metadata": "separate fields in this JSON document",
                },
                "raw_file": raw_path.name if raw_path else None, "annotated_file": annotated_path.name if annotated_path else None,
            }
            metadata_path = base.with_suffix(".json")
            metadata_temp = metadata_path.with_name(metadata_path.name + ".tmp")
            metadata_temp.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
            metadata_temp.replace(metadata_path)
            written.append(metadata_path)
        except Exception:
            for path in written:
                try: path.unlink(missing_ok=True)
                except OSError: pass
            raise
        self.attempts.set_evidence_paths(attempt.attempt_id, raw_path, annotated_path)
        return raw_path, annotated_path, metadata_path

    def _write_evidence_png(self, frame: np.ndarray, path: Path) -> None:
        temporary = path.with_name(path.name + ".tmp.png")
        try:
            if not cv2.imwrite(str(temporary), frame):
                raise RuntimeError("Could not write evidence PNG")
            temporary.replace(path)
        finally:
            try: temporary.unlink(missing_ok=True)
            except OSError: pass

    def _draw_evidence_overlay(self, frame: np.ndarray, attempt: AttemptSession, decision: AttemptDecision, frame_index: int | None = None) -> None:
        h, w = frame.shape[:2]; d = self.config.display
        gx, gy = int(d.guide_x_ratio * w), int(d.guide_y_ratio * h)
        angle = math.radians(d.guide_angle_deg); length = int(math.hypot(w, h))
        dx, dy = int(math.sin(angle) * length), int(math.cos(angle) * length)
        color = (70, 70, 255)
        cv2.line(frame, (gx - dx, gy - dy), (gx + dx, gy + dy), color, max(1, d.guide_width_px), cv2.LINE_AA)
        x0, y0 = int(d.board_roi_x * w), int(d.board_roi_y * h)
        x1, y1 = int((d.board_roi_x + d.board_roi_width) * w), int((d.board_roi_y + d.board_roi_height) * h)
        cv2.rectangle(frame, (x0, y0), (x1, y1), (0, 190, 230), 2, cv2.LINE_AA)
        overlay = frame.copy(); cv2.rectangle(overlay, (12, 12), (min(w - 12, 720), 82), (12, 16, 22), -1)
        cv2.addWeighted(overlay, .72, frame, .28, 0, frame)
        displayed_index = self.playback.attempt_frame_index if frame_index is None else frame_index
        label = f"{self._attempt_roster_display(attempt)}  |  {self._decision_display(decision).upper()}  |  {self._t("overlay.frame")} {displayed_index + 1}/{max(1, attempt.frame_count)}"
        cv2.putText(frame, label, (25, 44), cv2.FONT_HERSHEY_SIMPLEX, .72, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), (25, 70), cv2.FONT_HERSHEY_SIMPLEX, .52, (190, 200, 215), 1, cv2.LINE_AA)

    def export_current_attempt(self) -> None:
        if self._evaluation_mode and not capabilities_for().permits("video_export"):
            self._show_message("The free trial allows 3 successful exports. Activate a paid license for more.", 8)
            return
        attempt_id = self._selected_action_attempt_id
        if attempt_id is None or self.attempts.get_attempt(attempt_id) is None:
            self._show_message("Select or freeze an attempt before exporting.", 5); return
        if self.attempts.request_export(attempt_id, self._exports_directory()):
            self._begin_busy(self._t("status.exporting"))
            self._show_message(f"Export requested for attempt #{attempt_id:02d}.", 4)
        else: self._show_message("The attempt is not ready for export.", 5)

    def delete_current_attempt(self) -> None:
        attempt_id = self._selected_action_attempt_id
        if attempt_id is None: return
        attempt = self.attempts.get_attempt(attempt_id)
        if attempt is None: return
        kind = "saved recording" if attempt.persistent else "temporary attempt"
        if not ask_themed_yes_no(self.root, "Delete recording", f"Delete {kind} #{attempt_id:02d}?\nExported and evidence files are not removed."): return
        self._cancel_scheduled_review()
        self._enter_live(complete_rotation=False)
        record = self.adjudication.get_for_attempt(attempt) if attempt else None
        if not self.attempts.delete(attempt_id, force=True): self._show_message("This attempt cannot be deleted while it is being encoded or exported.", 5)
        elif record:
            try: self.adjudication.mark_media_unavailable(record.record_id)
            except DurabilityError as exc: self._show_message(f"Result retained in memory; storage warning: {exc}", 8)
        self._selected_action_attempt_id = None
        self._refresh_attempts()

    def _ask_clear_recordings_mode(self) -> str | None:
        if not self.config.general.confirm_destructive_actions:
            return "all"
        dialog = tk.Toplevel(self.root)
        configure_popup(dialog, self.root)
        dialog.title(self._t("dialog.clear.title"))
        dialog.geometry("520x330")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        result = tk.StringVar(value="")
        attempts = [attempt for attempt in self.attempts.attempts() if not attempt.persistent]
        unresolved = sum(a.decision in {AttemptDecision.NOT_DECIDED, AttemptDecision.REVIEW} for a in attempts)
        cache_mb = self.attempts.cache_size_bytes() / 1024**2
        live = self.buffer.stats()
        body = ttk.Frame(dialog, style="App.TFrame", padding=18)
        body.pack(fill="both", expand=True)
        title = "Clear temporary recordings?" if self.config.general.language != "cs" else "Vymazat dočasné záznamy?"
        ttk.Label(body, text=title, style="Title.TLabel").pack(anchor="w")
        details = (
            f"{len(attempts)} temporary recordings · {unresolved} unresolved\n"
            f"{cache_mb:.1f} MB cache · {live.duration_seconds:.1f} s live buffer\n\n"
            "Exported MP4 files and evidence images will not be deleted."
            if self.config.general.language != "cs" else
            f"{len(attempts)} dočasných záznamů · {unresolved} nerozhodnutých\n"
            f"{cache_mb:.1f} MB cache · {live.duration_seconds:.1f} s živého bufferu\n\n"
            "Exportovaná MP4 a důkazní snímky nebudou smazány."
        )
        ttk.Label(body, text=details, style="Muted.TLabel", justify="left").pack(anchor="w", pady=(7, 16))
        buttons = ttk.Frame(body, style="App.TFrame")
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Clear everything" if self.config.general.language != "cs" else "Vymazat vše", style="Danger.TButton", command=lambda: result.set("all")).pack(fill="x", pady=3)
        ttk.Button(buttons, text="Clear live buffer only" if self.config.general.language != "cs" else "Vymazat jen živý buffer", command=lambda: result.set("live")).pack(fill="x", pady=3)
        ttk.Button(buttons, text="Clear unresolved recordings" if self.config.general.language != "cs" else "Vymazat nerozhodnuté záznamy", command=lambda: result.set("unresolved")).pack(fill="x", pady=3)
        ttk.Button(buttons, text=self._t("settings.cancel"), command=lambda: result.set("cancel")).pack(fill="x", pady=(10, 0))
        dialog.protocol("WM_DELETE_WINDOW", lambda: result.set("cancel"))
        dialog.wait_variable(result)
        value = result.get()
        dialog.destroy()
        return None if value == "cancel" else value

    def _clear_recordings_mode(self, mode: str, ask: bool = True) -> int:
        if ask:
            selected = self._ask_clear_recordings_mode()
            if selected is None:
                return 0
            mode = selected
        self._cancel_scheduled_review()
        self._enter_live(complete_rotation=False)
        count = 0
        if mode == "all":
            records = [self.adjudication.get_for_attempt(attempt) for attempt in self.attempts.attempts() if not attempt.persistent]
            count = self.attempts.clear_all()
            for record in records:
                if record:
                    try: self.adjudication.mark_media_unavailable(record.record_id)
                    except DurabilityError: pass
            self.buffer.clear()
            # Clearing a session starts the board rotation from its first
            # editable cell, so an old clicked target cannot survive the wipe.
            groups = self.competition.enabled_groups()
            if groups:
                group = self.competition.current_group()
                if group not in groups:
                    group = groups[0]
                self.competition.set_current(group, 1)
                self._board_next_assignment = None
                self.competition_board.clear_focus()
        elif mode == "live":
            self.buffer.clear()
        elif mode == "unresolved":
            records = [
                self.adjudication.get_for_attempt(attempt) for attempt in self.attempts.attempts()
                if not attempt.persistent and attempt.decision in {AttemptDecision.NOT_DECIDED, AttemptDecision.REVIEW}
            ]
            count = self.attempts.clear_unresolved()
            for record in records:
                if record:
                    try: self.adjudication.mark_media_unavailable(record.record_id)
                    except DurabilityError: pass
        else:
            raise ValueError(f"Unsupported clear mode: {mode}")
        self._last_replay_key = None
        self._displayed_bgr = None
        self._displayed_timestamp_ns = 0
        self.timeline.set_model(None)
        self._last_board_signature = None
        self._refresh_attempts()
        self._refresh_current_try()
        if mode == "all" and self.competition.enabled_groups():
            self._refresh_competition_board(self.attempts.attempts(), self.competition.assignment_for_current(self.attempts.attempts()))
            self.competition_board.focus_cell((1, 1))
        if mode == "live":
            message = "Live buffer cleared. Capture continues." if self.config.general.language != "cs" else "Živý buffer vymazán. Záznam pokračuje."
        elif mode == "unresolved":
            message = f"Cleared {count} unresolved temporary recording(s)." if self.config.general.language != "cs" else f"Vymazáno {count} nerozhodnutých dočasných záznamů."
        else:
            message = f"Cleared {count} temporary recording(s). Capture continues with a fresh buffer." if self.config.general.language != "cs" else f"Vymazáno {count} dočasných záznamů. Kamera pokračuje s čistým bufferem."
        self._show_message(message, 5)
        return count

    def clear_all_recordings(self) -> None:
        self._clear_recordings_mode("all", ask=True)

    def _attempt_tree_selected(self, _event) -> None:
        selected = self.attempt_tree.selection()
        if not selected: return
        try: attempt_id = int(selected[0])
        except ValueError: return
        self._selected_action_attempt_id = attempt_id
        self._sync_recording_selection_style()
        if self.playback.attempt_id == attempt_id and self.playback.mode is PlaybackMode.ATTEMPT:
            self._update_judging_controls()
            return
        self._cancel_scheduled_review()
        if self.playback.select_attempt(attempt_id):
            self._last_replay_key = None; self.timeline.detail_center_ns = None
        self._update_judging_controls()

    # -------------------------------------------------------- Take-off Assist
    def _set_assist_warning(self, attempt_id: int) -> None:
        """Show a persistent, compact failure state for the active frozen attempt."""
        if self.playback.mode is not PlaybackMode.ATTEMPT or self.playback.attempt_id != attempt_id:
            return
        self._assist_warning_attempt_id = attempt_id
        self.assist_warning_var.set("! Take-off Assist failed")
        if not self.assist_warning_label.winfo_manager():
            self.assist_warning_label.pack(side="left", padx=(0, 12))

    def _clear_assist_warning(self) -> None:
        self._assist_warning_attempt_id = None
        if hasattr(self, "assist_warning_var"):
            self.assist_warning_var.set("")
        if hasattr(self, "assist_warning_label") and self.assist_warning_label.winfo_manager():
            self.assist_warning_label.pack_forget()

    def _start_takeoff_analysis(self, attempt_id: int) -> None:
        attempt = self.attempts.get_attempt(attempt_id)
        if not attempt: return
        d, a = self.config.display, self.config.takeoff_assist
        roi = (d.board_roi_x, d.board_roi_y, d.board_roi_width, d.board_roi_height)
        def worker() -> None:
            try:
                if a.analysis_seconds_after_freeze > 0:
                    time.sleep(a.analysis_seconds_after_freeze + .05)
                deadline = time.monotonic() + 1.25
                packets = self.attempts.packets_snapshot(attempt_id)
                while not packets and time.monotonic() < deadline and not self._closing:
                    time.sleep(.05)
                    packets = self.attempts.packets_snapshot(attempt_id)
                if not packets:
                    self.event_queue.put(("takeoff_failed", (attempt_id, "Take-off Assist failed: no recorded frames were available.")))
                    return
                candidate = detect_takeoff_candidate(packets, attempt.freeze_timestamp_ns, roi,
                                                     a.analysis_seconds_before_freeze, a.analysis_seconds_after_freeze,
                                                     a.downscale_width)
                if candidate:
                    lead = int(a.seek_lead_frames)
                    selected_index = candidate.visible_frame_for_lead(lead)
                    cached_indices = tuple(
                        max(0, min(max(0, attempt.frame_count - 1), int(index)))
                        for index in candidate.usable_frame_indices
                    )
                    with self._takeoff_projection_lock:
                        self._takeoff_projection_indices[attempt_id] = tuple(sorted(set(cached_indices)))
                    self.attempts.set_takeoff_candidate(
                        attempt_id,
                        selected_index,
                        candidate.confidence,
                        candidate.analysis_start_ns,
                        candidate.analysis_end_ns,
                    )
                else:
                    self.event_queue.put(("takeoff_failed", (attempt_id, "Take-off Assist failed: no clear local motion peak was found.")))
            except Exception as exc:
                self.event_queue.put(("takeoff_failed", (attempt_id, f"Take-off Assist failed: {exc}")))
        Thread(target=worker, name=f"takeoff-assist-{attempt_id}", daemon=True).start()

    def _handle_takeoff_candidate(self, attempt_id: int, index: int, confidence: float) -> None:
        a = self.config.takeoff_assist
        if confidence < a.minimum_confidence:
            detail = f"Take-off Assist failed: candidate confidence was only {confidence:.0%}; playhead was not moved."
            self._set_assist_warning(attempt_id)
            self._show_message(detail, 6); return
        self._clear_assist_warning()
        self._show_message(f"Take-off Assist found a motion peak near the board ({confidence:.0%}).", 5)
        if self.playback.attempt_id != attempt_id: return
        if a.quick_review_enabled: self._start_quick_review(attempt_id, index)
        elif a.auto_seek_after_freeze:
            self.playback.attempt_frame_index = index; self._last_replay_key = None

    def _start_quick_review(self, attempt_id: int, candidate_index: int) -> None:
        attempt = self.attempts.get_attempt(attempt_id)
        if not attempt: return
        self._cancel_scheduled_review()
        fps = max(1.0, attempt.fps)
        start = max(0, candidate_index - int(.35 * fps)); end = min(max(0, attempt.frame_count - 1), candidate_index + int(.18 * fps))
        self.playback.select_attempt(attempt_id, at_freeze=False); self.playback.attempt_frame_index = start
        interval = max(12, int(1000 / max(1.0, fps * self.config.takeoff_assist.quick_review_speed)))
        def advance() -> None:
            self._quick_review_job = None
            if self._closing or self.playback.attempt_id != attempt_id: return
            if self.playback.attempt_frame_index >= end:
                self.playback.attempt_frame_index = candidate_index; self._last_replay_key = None; return
            self.playback.attempt_frame_index += 1; self._last_replay_key = None
            self._quick_review_job = self.root.after(interval, advance)
        self._quick_review_job = self.root.after(interval, advance)

    def _cancel_scheduled_review(self) -> None:
        if self._quick_review_job:
            try: self.root.after_cancel(self._quick_review_job)
            except tk.TclError: pass
            self._quick_review_job = None
        if self._auto_live_job:
            try: self.root.after_cancel(self._auto_live_job)
            except tk.TclError: pass
            self._auto_live_job = None

    # ----------------------------------------------------- calibration/views
    def toggle_calibration_mode(self) -> None:
        self._calibration_mode = not self._calibration_mode
        self.replay_canvas.set_calibration_mode(self._calibration_mode)
        self._show_message(self._t("calibration.enabled") if self._calibration_mode else self._t("calibration.saved"), 5)
        if not self._calibration_mode: self._save_config_safely()

    def _guide_changed(self, x: float, y: float | None = None, angle: float | None = None) -> None:
        d = self.config.display
        d.guide_x_ratio = x
        if y is not None: d.guide_y_ratio = y
        if angle is not None: d.guide_angle_deg = angle
        self._sync_calibration_to_canvases(except_canvas=self.replay_canvas)

    def _calibration_changed(self, values: dict[str, float]) -> None:
        d = self.config.display
        for key, value in values.items(): setattr(d, key, value)
        self._sync_calibration_to_canvases(except_canvas=self.replay_canvas)

    def _sync_calibration_to_canvases(self, except_canvas: VideoCanvas | None = None) -> None:
        d = self.config.display; roi = (d.board_roi_x, d.board_roi_y, d.board_roi_width, d.board_roi_height)
        projection = self.config.top_view_projection
        board = tuple(tuple(point) for point in projection.board_corners)
        foul_area = tuple(tuple(point) for point in projection.foul_area)
        for canvas in (self.replay_canvas, self.live_canvas):
            if canvas is except_canvas: continue
            canvas.set_calibration(d.guide_x_ratio, d.guide_y_ratio, d.guide_angle_deg, roi, d.board_roi_enabled, d.board_roi_visible, d.guide_width_px)
            canvas.set_projection_overlay(board, foul_area)

    def toggle_guide(self) -> None:
        enabled = not self.replay_canvas.guide_enabled; self.config.display.guide_enabled = enabled
        self.var_show_foul_area.set(enabled)
        self.replay_canvas.set_guide_enabled(enabled); self.live_canvas.set_guide_enabled(enabled); self._save_config_safely()

    def toggle_foul_overlay(self) -> None:
        enabled = bool(self.var_show_foul_area.get())
        self.config.display.guide_enabled = enabled
        self.replay_canvas.set_guide_enabled(enabled); self.live_canvas.set_guide_enabled(enabled)
        self._save_config_safely()

    def toggle_board_overlay(self) -> None:
        visible = bool(self.var_show_board_outline.get())
        self.config.display.board_roi_visible = visible
        self._sync_calibration_to_canvases()
        self._save_config_safely()

    def toggle_comparison(self) -> None:
        if not self.config.display.comparison_enabled:
            self._show_message("Comparison view is disabled in Settings.", 4); return
        self.config.display.layout = "replay_pip" if self.config.display.layout == "comparison" else "comparison"
        self.var_layout.set(self.config.display.layout); self._apply_layout(); self._save_config_safely()

    def toggle_fullscreen(self) -> None: self.root.attributes("-fullscreen", not bool(self.root.attributes("-fullscreen")))
    def reset_video_views(self) -> None:
        for canvas in self._all_video_canvases(): canvas.reset_view()

    def _hotkey_toggle_attempts(self) -> None: self.var_show_attempts.set(not self.var_show_attempts.get()); self.toggle_attempts_panel()
    def _hotkey_toggle_board(self) -> None: self.var_show_board.set(not self.var_show_board.get()); self.toggle_competition_board()
    def _hotkey_toggle_timeline(self) -> None: self.var_show_timeline.set(not self.var_show_timeline.get()); self.toggle_timeline()
    def _hotkey_toggle_live(self) -> None: self.var_show_live.set(not self.var_show_live.get()); self.toggle_live_preview()

    def toggle_attempts_panel(self) -> None:
        self.config.display.show_attempts_panel = bool(self.var_show_attempts.get()); self._apply_visibility(); self._save_config_safely()
    def toggle_competition_board(self) -> None:
        if self._evaluation_mode:
            self.var_show_board.set(False)
            self._show_message("The competition board is disabled in the evaluation.", 6)
            return
        self.config.competition.show_competition_board = bool(self.var_show_board.get())
        self._apply_visibility(); self._save_config_safely()
    def toggle_timeline(self) -> None:
        self.config.display.show_timeline = bool(self.var_show_timeline.get())
        if self.config.display.show_timeline:
            self.config.display.timeline_height = max(MIN_TIMELINE_HEIGHT, self.config.display.timeline_height)
        self._apply_visibility(); self._save_config_safely()
    def toggle_live_preview(self) -> None:
        self.config.display.show_live_preview = bool(self.var_show_live.get()); self._apply_layout(); self._save_config_safely()
    def toggle_status_bar(self) -> None:
        self.config.display.show_status_bar = bool(self.var_show_status.get()); self._apply_visibility(); self._save_config_safely()

    def _apply_visibility(self) -> None:
        show_attempts = bool(self.var_show_attempts.get())
        if show_attempts and not self._attempts_pane_added:
            self.content_pane.add(self.attempts_panel, weight=1); self._attempts_pane_added = True
            self.root.after_idle(self._set_attempts_sash)
            self.root.after(180, self._set_attempts_sash)
        elif not show_attempts and self._attempts_pane_added:
            self.content_pane.forget(self.attempts_panel); self._attempts_pane_added = False
        show_timeline = bool(self.var_show_timeline.get())
        if show_timeline and not self._timeline_pane_added:
            self.media_pane.add(self.timeline_wrap, weight=1); self._timeline_pane_added = True
            self.root.after_idle(self._set_timeline_sash)
            self.root.after(180, self._set_timeline_sash)
        elif not show_timeline and self._timeline_pane_added:
            self.media_pane.forget(self.timeline_wrap); self._timeline_pane_added = False
        show_status = bool(self.var_show_status.get())
        if show_status and not self.status_bar.winfo_manager(): self.status_bar.grid(row=3, column=0, sticky="ew", pady=(5, 0))
        elif not show_status and self.status_bar.winfo_manager(): self.status_bar.grid_remove()
        show_decisions = bool(
            self.config.competition.enabled
            and self.config.competition.decision_controls_enabled
            and self.config.display.show_decision_controls
        )
        if show_decisions and not self.decision_frame.winfo_manager(): self.decision_frame.pack(side="left")
        elif not show_decisions and self.decision_frame.winfo_manager(): self.decision_frame.pack_forget()
        show_board = bool(self.config.competition.enabled and self.config.competition.show_competition_board and self.var_show_board.get())
        tabs = set(self.side_notebook.tabs())
        board_id = str(self.board_tab)
        if show_board:
            if board_id not in tabs:
                self.side_notebook.add(self.board_tab, text=self._t("board.title").title())
            else:
                self.side_notebook.tab(self.board_tab, state="normal", text=self._t("board.title").title())
        elif not show_board and board_id in tabs:
            if self.side_notebook.select() == board_id:
                self.side_notebook.select(self.recordings_tab)
            self.side_notebook.hide(self.board_tab)
        self._refresh_competitor_selector()

    def _set_attempts_sash(self) -> None:
        try:
            # Keep enough judging workspace for the review canvas even when
            # the recordings footer contains its full action labels.
            total = self.content_pane.winfo_width(); self.content_pane.sashpos(0, max(450, total - self.config.display.attempts_panel_width))
        except tk.TclError: pass

    def _set_timeline_sash(self) -> None:
        if not self._timeline_pane_added: return
        try:
            total = self.media_pane.winfo_height()
            # Startup builds the interface while the root is withdrawn. Sash
            # coordinates applied against that 1 px placeholder can maximize
            # the timeline when the real fullscreen geometry appears.
            if not self.root.winfo_viewable() or total < self.VIDEO_USABLE_HEIGHT + MIN_TIMELINE_HEIGHT:
                self.root.after(120, self._set_timeline_sash)
                return
            desired = min(
                MAX_TIMELINE_HEIGHT,
                max(MIN_TIMELINE_HEIGHT, self.config.display.timeline_height),
                max(MIN_TIMELINE_HEIGHT, total - self.VIDEO_USABLE_HEIGHT),
            )
            sash = min(total - MIN_TIMELINE_HEIGHT, max(self.VIDEO_USABLE_HEIGHT, total - desired))
            self.media_pane.sashpos(0, sash)
        except tk.TclError: pass

    def _apply_layout(self) -> None:
        layout = self.config.display.layout; show_live = self.config.display.show_live_preview and bool(self.var_show_live.get())
        for canvas in self._all_video_canvases(): canvas.place_forget()
        if layout == "live_only": self.live_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        elif layout == "replay_only" or not show_live and layout not in {"comparison", "board_detail"}:
            self.replay_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        elif layout == "side_by_side":
            self.replay_canvas.place(relx=0, rely=0, relwidth=.66, relheight=1); self.live_canvas.place(relx=.665, rely=0, relwidth=.335, relheight=1)
        elif layout == "board_detail":
            self.replay_canvas.place(relx=0, rely=0, relwidth=.66, relheight=1); self.board_canvas.place(relx=.665, rely=0, relwidth=.335, relheight=1)
        elif layout == "comparison" and self.config.display.comparison_enabled:
            self.comparison_prev_canvas.place(relx=0, rely=0, relwidth=.245, relheight=1)
            self.replay_canvas.place(relx=.25, rely=0, relwidth=.50, relheight=1)
            self.comparison_next_canvas.place(relx=.755, rely=0, relwidth=.245, relheight=1)
        else:
            self.replay_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
            if show_live:
                self.live_canvas.place(relx=.735, rely=.035, relwidth=.245, relheight=.29); self.live_canvas.tk.call("raise", self.live_canvas._w)
        self._update_auxiliary_views()

    def _menu_layout_changed(self) -> None: self.config.display.layout = self.var_layout.get(); self._apply_layout(); self._save_config_safely()
    def _menu_theme_changed(self) -> None: self.config.display.theme = self.var_theme.get(); self._apply_theme(); self._save_config_safely()

    def _apply_theme(self) -> None:
        self.palette = self.theme.apply(self.config.display.theme)
        for canvas in self._all_video_canvases(): canvas.apply_palette(self.palette)
        self.timeline.apply_palette(self.palette)
        if hasattr(self, "competition_board"):
            self.competition_board.apply_palette(self.palette)
        self._style_all_menus()
        self._refresh_attempts(); self._update_video_labels()
        self._update_athlete_timer_display()

    # -------------------------------------------------------------- settings
    def open_settings(self) -> SettingsDialog:
        return SettingsDialog(
            self.root,
            self.config,
            self.apply_settings,
            self.open_camera_diagnostic,
            self.show_onboarding,
            self.check_for_updates,
        )

    def _prompt_recording_mode(self) -> None:
        if self._closing or self.config.general.recording_mode_prompted:
            return
        if self._board_calibration_wizard is not None:
            self.root.after(500, self._prompt_recording_mode)
            return
        dialog = tk.Toplevel(self.root)
        configure_popup(dialog, self.root)
        dialog.title("Choose recording mode")
        dialog.geometry("560x330")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        body = ttk.Frame(dialog, style="App.TFrame", padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Choose how LongJumpReplay records", style="SettingsHeroTitle.TLabel").pack(anchor="w")
        ttk.Label(body, text="This choice controls whether the live rolling buffer is used. You can change it later in Settings; a restart is required.", style="SettingsHeroDesc.TLabel", wraplength=500, justify="left").pack(anchor="w", pady=(6, 16))
        mode = tk.StringVar(dialog, value=self.config.capture.mode)
        ttk.Radiobutton(body, text="Buffer mode — keep the current rolling replay and Freeze workflow", variable=mode, value="buffer").pack(anchor="w", pady=5)
        ttk.Radiobutton(body, text="Capture mode — no rolling buffer; use Record and Stop", variable=mode, value="capture").pack(anchor="w", pady=5)
        actions = ttk.Frame(body, style="App.TFrame")
        actions.pack(fill="x", pady=(20, 0))
        def finish() -> None:
            self.config.capture.mode = mode.get()
            self.config.general.recording_mode_prompted = True
            save_config(self._config_for_persistence(self.config), self.config_path)
            dialog.destroy()
            self._show_message("Recording mode saved. Restart LongJumpReplay to apply it.", 8)
        ttk.Button(actions, text="Save choice", style="Accent.TButton", command=finish).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", finish)

    def restart_now(self, startup_camera_index: int | None = None) -> None:
        """Launch the same command line again, then use the normal bounded shutdown."""
        self._save_config_safely()
        try:
            if getattr(sys, "frozen", False):
                command = [sys.executable, *sys.argv[1:]]
            else:
                command = [sys.executable, str(Path(sys.argv[0]).resolve()), *sys.argv[1:]]
            if startup_camera_index is not None:
                command.extend(("--startup-camera-index", str(startup_camera_index)))
            subprocess.Popen(command, cwd=str(Path.cwd()))
        except OSError as exc:
            show_themed_info(
                self.root,
                "Restart failed" if self.config.general.language != "cs" else "Restart se nezdařil",
                str(exc),
            )
            return
        self.close()

    def show_onboarding(self) -> None:
        if self._board_calibration_wizard is not None:
            self.root.after(300, self.show_onboarding)
            return
        if getattr(self, "_onboarding_window", None) is not None:
            try:
                self._onboarding_window.lift(); return
            except tk.TclError:
                self._onboarding_window = None
        lang = self.config.general.language
        steps = [
            ("Live and Freeze", "Watch the live preview. Press Space or Freeze to pin an attempt for review.", "Živě a Zmrazit", "Sleduj živý náhled. Mezerníkem nebo tlačítkem Zmrazit připni pokus ke kontrole."),
            ("Review the attempt", "Use Left/Right or the timeline to inspect frames. Home returns to Live.", "Kontrola pokusu", "Pomocí šipek nebo časové osy procházej snímky. Home se vrátí na Živě."),
            ("Judge and record", "Choose Valid, Foul, Review, or Not decided. The board keeps the athlete and attempt visible.", "Rozhodni a ulož", "Vyber Platný, Přešlap, Kontrola nebo Nerozhodnuto. Tabulka zachová závodníka a pokus."),
            ("Make it yours", "Settings contains hotkeys, camera, board calibration, and the tutorial can be opened again anytime.", "Nastav si aplikaci", "Nastavení obsahuje zkratky, kameru, kalibraci prkna a výukový program lze kdykoli spustit znovu."),
        ]
        win = tk.Toplevel(self.root); configure_popup(win, self.root); self._onboarding_window = win
        win.title("Getting started" if lang == "en" else "Začínáme"); win.geometry("560x340"); win.resizable(False, False); win.transient(self.root); win.grab_set()
        body = ttk.Frame(win, style="App.TFrame", padding=26); body.pack(fill="both", expand=True)
        title = ttk.Label(body, style="SettingsHeroTitle.TLabel", font=("Segoe UI Semibold", 19)); title.pack(anchor="w")
        progress = ttk.Label(body, style="Muted.TLabel"); progress.pack(anchor="w", pady=(4, 18))
        copy = ttk.Label(body, style="Text.TLabel", wraplength=500, justify="left", font=("Segoe UI", 11)); copy.pack(anchor="w", fill="x", expand=True)
        buttons = ttk.Frame(body, style="App.TFrame"); buttons.pack(fill="x", pady=(18, 0))
        index = {"value": 0}
        def render() -> None:
            i = index["value"]; en_title, en_copy, cs_title, cs_copy = steps[i]
            title.configure(text=cs_title if lang == "cs" else en_title); copy.configure(text=cs_copy if lang == "cs" else en_copy)
            progress.configure(text=(f"Step {i + 1} of {len(steps)}" if lang == "en" else f"Krok {i + 1} z {len(steps)}"))
            back.configure(state="normal" if i else "disabled")
            next_button.configure(text=("Finish" if i == len(steps) - 1 else "Next") if lang == "en" else ("Dokončit" if i == len(steps) - 1 else "Další"))
        def finish() -> None:
            self.config.general.onboarding_completed = True; self._save_config_safely()
            try: win.grab_release(); win.destroy()
            except tk.TclError: pass
            self._onboarding_window = None
        def skip() -> None: finish()
        def previous() -> None: index["value"] = max(0, index["value"] - 1); render()
        def next_step() -> None:
            if index["value"] >= len(steps) - 1: finish()
            else: index["value"] += 1; render()
        ttk.Button(buttons, text="Skip" if lang == "en" else "Přeskočit", command=skip).pack(side="left")
        back = ttk.Button(buttons, text="Back" if lang == "en" else "Zpět", command=previous); back.pack(side="right", padx=(8, 0))
        next_button = ttk.Button(buttons, style="Accent.TButton", command=next_step); next_button.pack(side="right")
        win.protocol("WM_DELETE_WINDOW", finish); render()

    def _refresh_ui_language(self) -> None:
        """Refresh static labels after a runtime language change."""
        self.translator.set_language(self.config.general.language)
        if hasattr(self, "timeline"):
            self.timeline.set_language(self.config.general.language)
            self.timeline_hint_label.configure(text="")
        if hasattr(self, "replay_canvas"):
            for canvas in self._all_video_canvases():
                canvas.set_language(self.config.general.language)
        self.root.title(self._t("app.title"))
        self.header_title.configure(text=self._t("app.header"))
        self._update_athlete_timer_display()
        self.file_menu_button.configure(text=self._t("menu.file"))
        self.camera_menu_button.configure(text=self._t("menu.camera"))
        self.view_menu_button.configure(text=self._t("menu.view"))
        self.help_menu_button.configure(text=self._t("menu.help"))
        self.freeze_button.configure(text=self._t("button.freeze"))
        self.system_pause_button.configure(text=self._t("button.resume_system") if self._system_paused else self._t("button.pause_system"))
        self.prev_frame_button.configure(text=self._t("button.previous_frame"))
        self.next_frame_button.configure(text=self._t("button.next_frame"))
        self.top_view_button.configure(text=self._t("button.top_view"))
        self.not_decided_button.configure(text=self._t("button.not_decided"))
        self.valid_button.configure(text=self._t("button.valid"))
        self.foul_button.configure(text=self._t("button.foul"))
        self.review_button.configure(text=self._t("button.review"))
        self.frame_group_label.configure(text=self._t("controls.frame_review"))
        self.decision_group_label.configure(text=self._t("controls.judging"))
        self.wizard_button.configure(text=self._t("button.wizard"))
        self.special_result_button.configure(text=self._t("button.more"))
        self.board_target_title_label.configure(text=self._t("board.next_target"))
        self.board_keyboard_hint.configure(text=self._t("board.keyboard_hint"))
        for key, label in (("recording", self._t("table.recording")), ("group", self._t("table.group")), ("athlete", "#"), ("try", self._t("table.attempt")), ("result", self._t("table.result")), ("distance", self._t("table.distance")), ("wind", self._t("table.wind")), ("time", self._t("table.time")), ("duration", self._t("table.duration")), ("media", self._t("table.media")), ("keep", self._t("table.keep"))):
            self.attempt_tree.heading(key, text=label)
        self.attempts_title_label.configure(text=self._t("attempts.title"))
        self.open_attempt_button.configure(text=self._t("attempts.open"))
        self.export_button.configure(text=self._t("attempts.export"))
        self.delete_button.configure(text=self._t("attempts.delete"))
        self.clear_button.configure(text=self._t("attempts.clear"))
        self.attempt_context_menu.entryconfigure(0, label=self._t("attempts.open"))
        self.attempt_context_menu.entryconfigure(1, label=self._t("attempts.edit"))
        self.attempt_context_menu.entryconfigure(2, label=self._t("attempts.export"))
        for index, decision in zip(self._recording_verdict_indices, (
            AttemptDecision.NOT_DECIDED, AttemptDecision.VALID, AttemptDecision.FOUL,
            AttemptDecision.REVIEW, AttemptDecision.PASSED, AttemptDecision.MISSING,
            AttemptDecision.WITHDRAWN,
        )):
            self.attempt_context_menu.entryconfigure(index, label=self._decision_display(decision))
        self.attempt_context_menu.entryconfigure(self._recording_measurement_menu_index, label=self._t("attempts.measurement"))
        self.attempt_context_menu.entryconfigure(self._recording_delete_menu_index, label=self._t("attempts.delete"))
        self.measurement_title_label.configure(text=self._t("measurement.title"))
        self.measurement_distance_label.configure(text=self._t("measurement.distance"))
        self.measurement_wind_label.configure(text=self._t("measurement.wind"))
        self.measurement_save_button.configure(text=self._t("measurement.save"))
        self.measurement_skip_button.configure(text=self._t("measurement.skip"))
        try:
            self.side_notebook.tab(self.recordings_tab, text=self._t("captures.title").title())
            self.side_notebook.tab(self.board_tab, text=self._t("board.title").title())
        except tk.TclError:
            pass
        # Recreate popup menus only on an actual language/settings change, not
        # in the video loop. The header buttons are then pointed at the new menus.
        self._build_menu()
        self.file_menu_button.configure(menu=self.file_menu)
        self.camera_menu_button.configure(menu=self.camera_menu)
        self.view_menu_button.configure(menu=self.view_menu)
        self.help_menu_button.configure(menu=self.help_menu)
        self._refresh_competitor_selector()
        self._refresh_attempts()

    def apply_settings(self, new_config: AppConfig) -> None:
        preserved_timeline_height: int | None = None
        try:
            if self._timeline_pane_added and self.media_pane.winfo_height() > 10:
                measured = self.media_pane.winfo_height() - int(self.media_pane.sashpos(0))
                if MIN_TIMELINE_HEIGHT <= measured <= MAX_TIMELINE_HEIGHT:
                    preserved_timeline_height = measured
        except tk.TclError:
            pass
        if self._evaluation_mode:
            new_config.competition.enabled = False
            new_config.competition.show_competition_board = False
            new_config.competition.decision_controls_enabled = False
            new_config.competition.event_export_enabled = False
            new_config.competition.auto_save_evidence = False
            new_config.display.show_decision_controls = False
        camera_changed = new_config.camera != self.config.camera or new_config.buffer != self.config.buffer
        requested_capture_mode = new_config.capture.mode
        capture_mode_changed = requested_capture_mode != self.config.capture.mode
        language_changed = new_config.general.language != self.config.general.language
        timer_duration_changed = new_config.athlete_timer.duration_seconds != self.config.athlete_timer.duration_seconds
        if self._persistent_camera_source_type is not None and new_config.camera.source_type != self.config.camera.source_type:
            self._persistent_camera_source_type = new_config.camera.source_type
        if capture_mode_changed:
            new_config = deepcopy(new_config)
            new_config.capture.mode = self.config.capture.mode
        self.config = new_config
        if preserved_timeline_height is not None:
            self.config.display.timeline_height = preserved_timeline_height
        if timer_duration_changed:
            self.athlete_timer.set_duration(new_config.athlete_timer.duration_seconds)
            self._update_athlete_timer_display()
        self.attempts.config = new_config.attempts
        self.attempts.export_config = new_config.export
        self.competition.update_config(new_config.competition)
        self.var_show_attempts.set(new_config.display.show_attempts_panel)
        self.var_show_timeline.set(new_config.display.show_timeline)
        self.var_show_status.set(new_config.display.show_status_bar)
        self.var_show_live.set(new_config.display.show_live_preview)
        self.var_show_board.set(new_config.competition.show_competition_board)
        self.var_layout.set(new_config.display.layout)
        self.var_theme.set(new_config.display.theme)
        self._sync_calibration_to_canvases()
        self.replay_canvas.board_roi_visible = new_config.display.board_roi_visible
        self._apply_theme()
        self._apply_layout()
        self._apply_visibility()
        if language_changed:
            self._refresh_ui_language()
        else:
            # Menu contents depend on optional feature toggles.
            self._build_menu()
            self.file_menu_button.configure(menu=self.file_menu)
            self.camera_menu_button.configure(menu=self.camera_menu)
            self.view_menu_button.configure(menu=self.view_menu)
            self.help_menu_button.configure(menu=self.help_menu)
        self._refresh_competitor_selector()
        # _apply_visibility positions the sash when the timeline is newly
        # shown. Leave an already-visible sash untouched so merely applying
        # Settings cannot resize the operator's timeline.
        self._install_hotkeys()
        self.shuttle.stop()
        self.shuttle = ShuttleHIDPoller(new_config.shuttle, self.action_queue)
        self.shuttle.start()
        persisted_config = self._config_for_persistence(new_config)
        if capture_mode_changed:
            persisted_config.capture.mode = requested_capture_mode
            persisted_config.general.recording_mode_prompted = True
        save_config(persisted_config, self.config_path)
        if capture_mode_changed:
            self._show_message("Recording mode changed in Settings. Restart LongJumpReplay to apply it.", 8)
        if camera_changed:
            language_is_en = new_config.general.language != "cs"
            restart = ask_themed_yes_no(
                self.root,
                "Restart required" if language_is_en else "Je nutný restart",
                "Camera or live-buffer changes need a restart. Restart Long Jump Replay now?"
                if language_is_en
                else "Změny kamery nebo živého bufferu vyžadují restart. Restartovat Long Jump Replay nyní?",
                yes="Restart" if language_is_en else "Restartovat",
                no="Later" if language_is_en else "Později",
            )
            if restart:
                self.restart_now(new_config.camera.device_index if new_config.camera.source_type == "camera" else None)

    # ------------------------------------------------------ competition setup
    def start_competition_wizard(self) -> None:
        if not self._trial_action_allowed("competition_setup", announce=False):
            self._show_message("Competition setup is disabled in the evaluation.", 6); return
        CompetitionWizard(
            self.root,
            self.config,
            self._finish_competition_wizard,
            readiness_provider=self._competition_wizard_readiness,
            on_open_settings=self.open_settings,
            on_camera_help=self.show_camera_help,
        )

    def _competition_wizard_readiness(self) -> WizardReadiness:
        capture = self.capture.stats()
        buffer = self.buffer.stats()
        return WizardReadiness(
            language=self.config.general.language,
            capture_running=self.capture.is_running,
            captured_frames=capture.captured_frames,
            capture_fps=capture.capture_fps,
            requested_fps=self.config.camera.fps,
            source_description=capture.source_description,
            last_error=capture.last_error,
            buffer_frame_count=buffer.frame_count,
            buffer_seconds=buffer.duration_seconds,
            cache_bytes=self.attempts.cache_size_bytes(),
            cache_limit_bytes=int(self.config.attempts.max_cache_gb * 1024 ** 3),
            temporary_recording_count=len(self.attempts.attempts()),
        )

    def _finish_competition_wizard(self, competition: CompetitionConfig, disposition: RecordingDisposition) -> None:
        # Merge only competition choices into the latest configuration. Settings
        # may have changed camera/language values while the wizard was open.
        new_config = merge_competition_setup(self.config, competition)
        if disposition == "clear":
            self._clear_recordings_mode("all", ask=False)
        self.apply_settings(new_config)
        self._last_board_signature = None
        self._refresh_competitor_selector()
        self._show_message(
            "Competition started." if self.config.general.language != "cs" else "Soutěž byla spuštěna.",
            5,
        )

    def toggle_operator_mode(self) -> None:
        self._operator_mode = not self._operator_mode
        self._apply_visibility()
        self._refresh_competitor_selector()
        self._show_message(
            self._t("operator.operator") if self._operator_mode else self._t("operator.setup"),
            4,
        )
        self._build_menu()
        self.file_menu_button.configure(menu=self.file_menu)
        self.camera_menu_button.configure(menu=self.camera_menu)
        self.view_menu_button.configure(menu=self.view_menu)
        self.help_menu_button.configure(menu=self.help_menu)

    def _check_recovered_session(self) -> None:
        if self._recovery_checked or self._closing:
            return
        self._recovery_checked = True
        recovered = self.attempts.attempts()
        if self.adjudication.recovery_warnings:
            self._show_message(
                f"Adjudication recovery: {len(self.adjudication.recovery_warnings)} warning(s). Decisions were recovered where possible.",
                10,
            )
        if not recovered or not self.config.competition.recovery_prompt_enabled:
            return
        keep = ask_themed_yes_no(
            self.root,
            "Restore previous session" if self.config.general.language != "cs" else "Obnovit předchozí relaci",
            (f"Found {len(recovered)} temporary recording(s) from an earlier session. Keep and restore them?"
             if self.config.general.language != "cs"
             else f"Bylo nalezeno {len(recovered)} dočasných záznamů z předchozí relace. Zachovat je a obnovit?"),
            yes="Keep" if self.config.general.language != "cs" else "Ponechat",
            no="Clear" if self.config.general.language != "cs" else "Vymazat",
        )
        if not keep:
            self._clear_recordings_mode("all", ask=False)
        else:
            self._refresh_attempts()
            self._show_message(
                f"Restored {len(recovered)} temporary recording(s)."
                if self.config.general.language != "cs"
                else f"Obnoveno {len(recovered)} dočasných záznamů.",
                6,
            )

    def export_competition_package(self) -> None:
        if not self._trial_action_allowed("competition_package", announce=False):
            self._show_message("Competition packages are disabled in the evaluation.", 7); return
        if trial_is_active() and trial_exports_remaining() <= 0:
            self._show_message("The free trial allows 3 successful exports. Activate a paid license for more.", 8)
            return
        if not self.config.competition.event_export_enabled:
            self._show_message(
                "Competition package export is disabled in Settings."
                if self.config.general.language != "cs"
                else "Export balíčku soutěže je vypnutý v Nastavení.",
                5,
            )
            return
        attempts = self.attempts.attempts()
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output = self._exports_directory() / f"competition_{stamp}.zip"
        rows = []
        for attempt in attempts:
            rows.append({
                "attempt_id": attempt.attempt_id,
                "group": attempt.competitor_group,
                "athlete": attempt.competitor_number,
                "attempt": attempt.competitor_attempt_number,
                "phase": attempt.competition_phase,
                "decision": attempt.decision.value,
                "created": datetime.fromtimestamp(attempt.created_wall_time).astimezone().isoformat(),
                "quality_warning": attempt.quality_warning,
                "temporary_video": attempt.temp_video_path.name if attempt.temp_video_path else "",
                "evidence_raw": attempt.evidence_raw_path.name if attempt.evidence_raw_path else "",
                "evidence_annotated": attempt.evidence_annotated_path.name if attempt.evidence_annotated_path else "",
            })
        csv_path = self._exports_directory() / f"competition_{stamp}_attempts.csv"
        with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["attempt_id", "group", "athlete", "attempt", "phase", "decision", "created", "quality_warning", "temporary_video", "evidence_raw", "evidence_annotated"])
            writer.writeheader()
            writer.writerows(rows)
        config_path = self._exports_directory() / f"competition_{stamp}_config.json"
        config_path.write_text(json.dumps(asdict(self.config), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(csv_path, "attempts.csv")
            archive.write(config_path, "config.json")
            for attempt in attempts:
                for source, folder in (
                    (attempt.temp_video_path, "recordings"),
                    (attempt.temp_metadata_path, "metadata"),
                    (attempt.evidence_raw_path, "evidence"),
                    (attempt.evidence_annotated_path, "evidence"),
                ):
                    if source and source.exists():
                        archive.write(source, f"{folder}/{attempt.attempt_id:04d}_{source.name}")
        csv_path.unlink(missing_ok=True)
        config_path.unlink(missing_ok=True)
        self._show_message(
            f"Competition package exported: {output.name}"
            if self.config.general.language != "cs"
            else f"Balíček soutěže exportován: {output.name}",
            8,
        )
        if trial_is_active():
            try:
                remaining = record_successful_export().exports_remaining
                self._show_message(f"Competition package exported: {output.name} · trial exports remaining: {remaining}", 8)
            except Exception as exc:
                self._show_message(f"Export completed, but trial state could not be updated: {exc}", 10)

    def export_adjudication_package(self) -> None:
        """Create an explicit, standalone evidence and decision package."""
        if not self._trial_action_allowed("evidence_package", announce=False):
            self._show_message("Evidence packages are disabled in the evaluation.", 7); return
        if trial_is_active() and trial_exports_remaining() <= 0:
            self._show_message("The free trial allows 3 successful exports. Activate a paid license for more.", 8)
            return
        records = self.adjudication.records()
        if not records:
            self._show_message("There are no adjudication records to export.", 5)
            return
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        export_dir = self._exports_directory()
        csv_path = export_dir / f"adjudication_{stamp}.csv"
        json_path = export_dir / f"adjudication_{stamp}.json"
        report_path = export_dir / f"adjudication_{stamp}_session-report.json"
        output = export_dir / f"adjudication_{stamp}_evidence.zip"
        temporary = output.with_suffix(output.suffix + ".tmp")
        try:
            CsvExportAdapter().export(records, csv_path)
            JsonExportAdapter().export(records, json_path)
            report = self.adjudication.session_report()
            report["runtime"] = asdict(self._telemetry.snapshot(self.capture.stats(), self.buffer.stats()))
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(csv_path, "decisions.csv")
                archive.write(json_path, "decisions.json")
                archive.write(report_path, "session-report.json")
                included: set[Path] = set()
                for record in records:
                    for value in (
                        record.evidence.raw_path, record.evidence.annotated_path,
                        record.evidence.metadata_path, record.evidence.clip_path,
                    ):
                        source = Path(value) if value else None
                        if source and source.exists() and source not in included:
                            included.add(source)
                            archive.write(source, f"evidence/{record.record_id}/{source.name}")
            temporary.replace(output)
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            self._show_message(f"Evidence package could not be exported: {exc}", 10)
            return
        finally:
            csv_path.unlink(missing_ok=True)
            json_path.unlink(missing_ok=True)
            report_path.unlink(missing_ok=True)
        self._show_message(f"Evidence package exported: {output.name}", 8)
        if trial_is_active():
            try: record_successful_export()
            except Exception as exc: self._show_message(f"Export completed, but trial state could not be updated: {exc}", 10)

    def import_roster(self) -> None:
        """Preview and atomically commit a generic roster into the active group."""
        if not self._trial_action_allowed("competition_setup", announce=False):
            self._show_message("Roster import is disabled in the evaluation.", 6); return
        selected = filedialog.askopenfilename(
            parent=self.root,
            title=self._t("menu.import_roster"),
            filetypes=(("Roster files", "*.csv *.tsv *.txt *.xlsx *.json"), ("All files", "*.*")),
        )
        if not selected:
            return
        source = Path(selected)
        try:
            draft = adapter_for_path(source).parse(source)
        except Exception as exc:
            show_themed_info(self.root, self._t("menu.import_roster"), f"The roster could not be parsed:\n{exc}")
            return
        if draft.issues:
            details = "\n".join(f"Row {issue.row}: {issue.message}" for issue in draft.issues[:12])
            show_themed_info(self.root, self._t("menu.import_roster"), f"Nothing was changed. Fix the import and try again:\n\n{details}")
            return
        group = self.competition.current_group()
        prepared = []
        for number, athlete in enumerate(sorted(draft.athletes, key=lambda item: item.start_order), start=1):
            athlete.group = group
            athlete.competitor_number = number
            athlete.start_order = number
            athlete.athlete_id = athlete.external_id or f"{group}:{number}:{athlete.bib or athlete.name}"
            prepared.append(athlete)
        preview = "\n".join(
            f"{item.start_order:02d}  {item.bib or '—'}  {item.name}  {item.club}" for item in prepared[:10]
        )
        if len(prepared) > 10:
            preview += f"\n… and {len(prepared) - 10} more"
        if not ask_themed_yes_no(
            self.root,
            self._t("menu.import_roster"),
            f"Replace the {self._group_display(group)} roster with {len(prepared)} athletes?\n\n{preview}\n\nNo active data changes until you confirm.",
            yes="Import", no=self._t("settings.cancel"),
        ):
            return
        retained = [item for item in self.adjudication.roster() if item.group != group]
        try:
            self.adjudication.replace_roster([*retained, *prepared])
        except DurabilityError as exc:
            show_themed_info(self.root, self._t("menu.import_roster"), f"Nothing was changed because the roster could not be saved safely:\n{exc}")
            return
        if group == "Boys":
            self.config.competition.boys_competitors = len(prepared)
        else:
            self.config.competition.girls_competitors = len(prepared)
        self.competition.update_config(self.config.competition)
        self._save_config_safely()
        self._last_board_signature = None
        self._refresh_competitor_selector(); self._refresh_attempts()
        self._show_message(f"Imported {len(prepared)} athletes into {self._group_display(group)}.", 6)

    def show_camera_help(self) -> tk.Toplevel:
        if self._camera_help_dialog is not None and self._camera_help_dialog.winfo_exists():
            self._camera_help_dialog.lift()
            return self._camera_help_dialog
        dialog = tk.Toplevel(self.root)
        configure_popup(dialog, self.root)
        self._camera_help_dialog = dialog
        dialog.title(self._t("camera.help_title"))
        dialog.geometry("650x500")
        dialog.minsize(560, 430)
        dialog.transient(self.root)
        dialog.configure(bg=self.palette["bg"])
        dialog.protocol("WM_DELETE_WINDOW", lambda: (setattr(self, "_camera_help_dialog", None), dialog.destroy()))

        card = ttk.Frame(dialog, style="Panel.TFrame", padding=(20, 18))
        card.pack(fill="both", expand=True, padx=14, pady=14)
        ttk.Label(card, text=self._t("camera.help_title"), style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(card, text=self._t("camera.help_intro"), style="Muted.TLabel", wraplength=580, justify="left").pack(anchor="w", pady=(5, 12))
        ttk.Label(
            card,
            text=self._t("camera.help_current", source=self.config.camera.source_type.upper(), index=self.config.camera.device_index),
            style="ContextValue.TLabel",
        ).pack(anchor="w", pady=(0, 12))

        advice = ttk.Frame(card, style="Panel.TFrame")
        advice.pack(fill="both", expand=True)
        for number, key in enumerate((
            "camera.help_source", "camera.help_index", "camera.help_close_other",
            "camera.help_permissions", "camera.help_mode",
        ), 1):
            row = ttk.Frame(advice, style="Panel.TFrame")
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=f"{number}.", style="ContextTitle.TLabel", width=3).pack(side="left", anchor="n")
            ttk.Label(row, text=self._t(key), style="Muted.TLabel", wraplength=540, justify="left").pack(side="left", fill="x", expand=True)

        footer = ttk.Frame(card, style="Toolbar.TFrame", padding=(10, 8))
        footer.pack(fill="x", pady=(14, 0))
        def open_settings() -> None:
            dialog.destroy(); self._camera_help_dialog = None; self.open_settings()
        ttk.Button(footer, text=self._t("camera.help_open_settings"), command=open_settings).pack(side="left")
        def close_help() -> None:
            self._camera_help_dialog = None
            dialog.destroy()
        ttk.Button(footer, text=self._t("camera.help_close"), command=close_help).pack(side="right")
        return dialog

    def open_camera_diagnostic(self) -> None:
        dialog = tk.Toplevel(self.root)
        configure_popup(dialog, self.root)
        dialog.title("Camera diagnostic" if self.config.general.language != "cs" else "Diagnostika kamery")
        dialog.geometry("600x430")
        dialog.minsize(520, 360)
        dialog.transient(self.root)
        text = tk.Text(dialog, wrap="word", relief="flat", padx=14, pady=14)
        text.pack(fill="both", expand=True, padx=12, pady=(12, 6))

        def refresh() -> None:
            capture = self.capture.stats()
            buffer = self.buffer.stats()
            target = max(1.0, self.config.camera.fps)
            ratio = capture.capture_fps / target if capture.capture_fps else 0.0
            if capture.queue_drops or ratio < .75:
                recommended = "Quiet / Low-power"
            elif ratio < .95 or capture.average_encode_ms > (1000 / target) * .6:
                recommended = "Balanced"
            else:
                recommended = self.config.performance.preset.title()
            lines = [
                f"Source: {capture.source_description}",
                f"Requested mode: {self.config.camera.width} × {self.config.camera.height} @ {self.config.camera.fps:.2f} FPS",
                f"Measured capture: {capture.capture_fps:.2f} FPS",
                f"JPEG buffer: {capture.encode_fps:.2f} FPS",
                f"Average JPEG encode: {capture.average_encode_ms:.2f} ms",
                f"Queue drops: {capture.queue_drops}",
                f"Live buffer: {buffer.frame_count} frames / {buffer.duration_seconds:.2f} s / {buffer.memory_bytes / 1024**2:.1f} MB",
                f"Last error: {capture.last_error or 'None'}",
                "",
                f"Recommended performance preset: {recommended}",
                "The preview workload can be reduced without changing exported evidence quality.",
            ]
            text.configure(state="normal")
            text.delete("1.0", "end")
            text.insert("1.0", "\n".join(lines))
            text.configure(state="disabled")

        footer = ttk.Frame(dialog, style="Toolbar.TFrame", padding=8)
        footer.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(footer, text="Refresh", command=refresh).pack(side="left")
        ttk.Button(footer, text="Close", command=dialog.destroy).pack(side="right")
        refresh()

    # ---------------------------------------------------------- files/help
    def _exports_directory(self) -> Path:
        path = self.data_paths.exports
        path.mkdir(parents=True, exist_ok=True)
        return path
    def _evidence_directory(self) -> Path:
        path = self.data_paths.evidence
        path.mkdir(parents=True, exist_ok=True)
        return path
    def open_exports_folder(self) -> None: self._open_directory(self._exports_directory())
    def open_recordings_folder(self) -> None: self._open_directory(self.data_paths.recordings)
    def _open_directory(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        if os.name == "nt": os.startfile(path)  # type: ignore[attr-defined]
        else: self._show_message(str(path), 8)

    def show_controls(self) -> None:
        show_themed_info(
            self.root,
            "Controls",
            "Space: Freeze / return live\nHome: Return live\nLeft / Right: one frame\n"
            "Ctrl+Page Up / Ctrl+Page Down: previous / next attempt\nV: Valid\nF: Foul\nU: Review\n"
            "P: Save frame\nE: Export attempt\nCtrl+Delete: clear temporary recordings\nC: comparison view\n\n"
            "Board calibration: drag the line centre; drag its yellow handle to rotate; Shift-drag a new board ROI; Ctrl+wheel fine-rotates the guide.\n\n"
            "Top-down projection: freeze an attempt, open Top-down projection, review the calibrated board/foul area and shoe outline, then inspect the unified result.\n\n"
            "ShuttleXpress: jog wheel steps frames; outer ring selects attempts; five buttons are configurable in Settings.",
        )

    def show_diagnostics(self) -> None:
        c, b = self.capture.stats(), self.buffer.stats(); devices = list_shuttle_devices(self.config.shuttle)
        runtime = self._telemetry.snapshot(c, b)
        adjudication_report = self.adjudication.session_report()
        shuttle = "\n".join(f"{d.product} · VID {d.vendor_id:04X} PID {d.product_id:04X}" for d in devices) or "No direct-HID Shuttle detected"
        show_themed_info(
            self.root,
            "Diagnostics",
            f"Source: {c.source_description}\nCapture FPS: {c.capture_fps:.2f}\nBuffered FPS: {c.encode_fps:.2f}\n"
            f"JPEG time: {c.average_encode_ms:.2f} ms\nQueue drops: {c.queue_drops}\n"
            f"{self._t('diagnostics.ui_tick', average=runtime.ui_average_ms, p95=runtime.ui_p95_ms, maximum=runtime.ui_max_ms)}\n"
            f"{self._t('diagnostics.ui_stalls', count=runtime.ui_stalls_over_100ms)}\n"
            f"{self._t('diagnostics.uptime', seconds=runtime.uptime_seconds)}\n"
            f"Live buffer: {b.duration_seconds:.2f} s / {b.frame_count} frames / {b.memory_bytes / 1024 ** 2:.1f} MB\n"
            f"Temporary recordings: {sum(not attempt.persistent for attempt in self.attempts.attempts())}\n"
            f"Saved recordings: {sum(attempt.persistent for attempt in self.attempts.attempts())}\n"
            f"Durable adjudications: {adjudication_report['attempts_processed']}\n"
            f"Verdict corrections: {adjudication_report['operator_corrections']}\nMedian decision time: {adjudication_report['median_decision_seconds'] or 0:.2f} s\n"
            f"Evidence gaps: {adjudication_report['evidence_failures']}\nCache: {self.attempts.cache_size_bytes() / 1024 ** 2:.1f} MB\n"
            f"Shuttle status: {self.shuttle.status}\n{shuttle}\n\nLast camera error: {c.last_error or 'None'}",
        )

    def _show_message(self, text: str, seconds: float = 5.0) -> None:
        self.message_var.set(text); self._message_until = time.perf_counter() + max(0, seconds)
    def _save_config_safely(self) -> None:
        try:
            save_config(self._config_for_persistence(self.config), self.config_path)
        except (OSError, TypeError, ValueError) as exc:
            self._logger.warning("config_save_failed path=%s error=%s", self.config_path, exc)

    def _config_for_persistence(self, config: AppConfig) -> AppConfig:
        if self._persistent_camera_source_type is None:
            return config
        persistent = deepcopy(config)
        persistent.camera.source_type = self._persistent_camera_source_type
        return persistent

    # -------------------------------------------------------------- shutdown
    def close(self) -> None:
        if self._closing: return
        self._closing = True; self._cancel_scheduled_review()
        if self._top_view_loading_cancel is not None:
            self._top_view_loading_cancel.set()
        if self._top_view_loading_dialog is not None:
            self._top_view_loading_dialog.close()
            self._top_view_loading_dialog = None
        if self._top_view_window is not None:
            self._top_view_window.close()
        if self._board_calibration_wizard is not None:
            self._board_calibration_wizard.close()
            self._board_calibration_wizard = None
        self._cancel_recording_auto_stop()
        if self.attempts.is_recording:
            self.attempts.stop_recording()
        self._camera_probe_generation += 1
        self._camera_probe_stop.set()
        log_event(self._logger, "shutdown_requested", playback_mode=self.playback.mode.value)
        if self._tick_job:
            try: self.root.after_cancel(self._tick_job)
            except tk.TclError: pass
        if self._window_interaction_job:
            try: self.root.after_cancel(self._window_interaction_job)
            except tk.TclError: pass
            self._window_interaction_job = None
        if self.config.display.remember_geometry and not bool(self.root.attributes("-fullscreen")):
            try:
                window_state = self.root.state()
                self.config.display.window_maximized = window_state == "zoomed"
                if window_state == "normal":
                    self.config.display.window_geometry = self.root.geometry()
            except tk.TclError: pass
        try:
            if self._attempts_pane_added and self.content_pane.winfo_width() > 10:
                self.config.display.attempts_panel_width = max(220, self.content_pane.winfo_width() - int(self.content_pane.sashpos(0)))
            if self._timeline_pane_added and self.media_pane.winfo_height() > 10:
                measured_timeline_height = self.media_pane.winfo_height() - int(self.media_pane.sashpos(0))
                if MIN_TIMELINE_HEIGHT <= measured_timeline_height <= MAX_TIMELINE_HEIGHT:
                    self.config.display.timeline_height = measured_timeline_height
                else:
                    clamp_display_panel_sizes(self.config.display)
        except tk.TclError: pass
        self._save_config_safely(); self.mode_var.set("CLOSING"); self.message_var.set("Stopping camera and background workers…")
        for child in self.root.winfo_children():
            try: child.configure(cursor="watch")
            except (tk.TclError, AttributeError): pass
        self._shutdown_started = time.perf_counter()
        def worker() -> None:
            alive = []
            try: self.adjudication.close()
            except Exception as exc: self._logger.error("adjudication_close_failed error=%s", exc)
            try: self.hotkeys.close()
            except Exception: pass
            try: alive.extend(self.shuttle.stop(timeout=.8))
            except Exception: pass
            try: self.thumbnail_worker.stop(timeout=.8)
            except Exception: pass
            try: alive.extend(self.capture.stop(timeout=2.0))
            except Exception: pass
            # Persistent Capture Mode media must finish its staged encode
            # before the process exits; temporary attempts can still be
            # cancelled inside the same manager.
            try: alive.extend(self.attempts.stop(timeout=8.0))
            except Exception: pass
            self.event_queue.put(("shutdown_done", alive))
        Thread(target=worker, name="shutdown-manager", daemon=True).start(); self.root.after(40, self._poll_shutdown)

    def _poll_shutdown(self) -> None:
        done = False
        while True:
            try: event, _payload = self.event_queue.get_nowait()
            except Empty: break
            if event == "shutdown_done": done = True
        if done or time.perf_counter() - self._shutdown_started > 12.0:
            log_event(self._logger, "shutdown_complete", timed_out=not done, duration_ms=round((time.perf_counter() - self._shutdown_started) * 1000, 2))
            try: self.root.destroy()
            except tk.TclError: pass
            return
        self.root.after(40, self._poll_shutdown)
