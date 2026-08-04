from __future__ import annotations

import csv
import json
import math
import os
import shutil
import zipfile
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
import time
import tkinter as tk
from tkinter import messagebox, ttk

import cv2
import numpy as np

from .attempts import AttemptManager
from .athlete_timer import AthleteTimerController, AthleteTimerState, format_countdown
from .capture import CaptureEngine
from .competition import CompetitionSession, RosterAssignment
from .competition_board import CompetitionBoard
from .competition_wizard import CompetitionWizard
from .config import AppConfig, save_config
from .i18n import Translator
from .exporter import save_bgr_png
from .hotkeys import HotkeyRouter
from .models import AttemptDecision, AttemptSession, AttemptState, TimelineModel
from .playback import PlaybackController, PlaybackMode
from .portable_paths import resolve_user_path
from .ring_buffer import TimeRingBuffer
from .settings_dialog import SettingsDialog
from .shuttle_hid import ShuttleHIDPoller, list_shuttle_devices
from .takeoff_assist import detect_takeoff_candidate
from .theme import ThemeManager
from .timeline import ProfessionalTimeline
from .video_canvas import VideoCanvas


class MainWindow:
    def __init__(self, root: tk.Tk, config: AppConfig, config_path: Path) -> None:
        self.root = root
        self.config = config
        self.config_path = config_path
        self.translator = Translator(config.general.language)
        self.root.title(self.translator("app.title"))
        self.root.minsize(1100, 700)
        if config.display.window_geometry:
            try: self.root.geometry(config.display.window_geometry)
            except tk.TclError: pass

        self.action_queue: Queue[tuple[str, int]] = Queue()
        self.event_queue: Queue[tuple[str, object]] = Queue()
        self.buffer = TimeRingBuffer(config.buffer.duration_seconds, config.buffer.max_memory_mb)
        self.capture = CaptureEngine(config.camera, config.buffer, self.buffer)
        self.attempts = AttemptManager(
            self.buffer,
            config.attempts,
            config.export,
            resolve_user_path(config_path, config.attempts.cache_directory),
            self.event_queue,
        )
        self.playback = PlaybackController(self.buffer, self.attempts)
        self.athlete_timer = AthleteTimerController(config.athlete_timer.duration_seconds)
        self.competition = CompetitionSession(config.competition)
        self.shuttle = ShuttleHIDPoller(config.shuttle, self.action_queue)

        self.theme = ThemeManager(root)
        self.palette = self.theme.apply(config.display.theme)
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
        self._warning_active = False
        self._last_video_update = 0.0
        self._menu_active_until = 0.0
        self._operator_mode = bool(config.competition.operator_mode_enabled)
        self._recovery_checked = False
        self._last_board_signature: object = None
        self._board_next_assignment: RosterAssignment | None = None
        self._last_timer_render_signature: object = None
        self._system_paused = False
        self._system_pause_transition = False

        self._build_variables()
        self._build_menu()
        self._build_layout()
        self.hotkeys = HotkeyRouter(root)
        self._install_hotkeys()
        self._apply_layout()
        self._apply_visibility()
        self._refresh_competitor_selector()
        if config.display.fullscreen:
            self.root.attributes("-fullscreen", True)
        else:
            self.root.after_idle(self._apply_initial_window_state)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Configure>", self._on_root_configure, add="+")

        self.attempts.start()
        self.root.after(150, self._check_recovered_session)
        self.capture.start()
        self.shuttle.start()
        self._schedule_tick()

    # ------------------------------------------------------------------ UI
    def _build_variables(self) -> None:
        d = self.config.display
        self.var_show_attempts = tk.BooleanVar(value=d.show_attempts_panel)
        self.var_show_timeline = tk.BooleanVar(value=d.show_timeline)
        self.var_show_status = tk.BooleanVar(value=d.show_status_bar)
        self.var_show_live = tk.BooleanVar(value=d.show_live_preview)
        self.var_show_board = tk.BooleanVar(value=self.config.competition.show_competition_board)
        self.var_layout = tk.StringVar(value=d.layout)
        self.var_theme = tk.StringVar(value=d.theme)
        self.camera_var = tk.StringVar(value="Starting camera…")
        self.clock_var = tk.StringVar(value="")
        self.timer_prefix_var = tk.StringVar(value=self._t("timer.ready"))
        self.timer_value_var = tk.StringVar(value=format_countdown(self.config.athlete_timer.duration_seconds))
        self.mode_var = tk.StringVar(value=self._t("mode.live"))
        self.status_var = tk.StringVar(value="Initialising…")
        self.message_var = tk.StringVar(value="")
        self.warning_var = tk.StringVar(value="")
        self.attempt_summary_var = tk.StringVar(value=self._t("attempts.none"))
        self.competition_banner_var = tk.StringVar(value="")
        self.group_var = tk.StringVar(value=self.config.competition.active_group)
        self.competitor_var = tk.StringVar(value=str(self.config.competition.current_competitor_by_group.get(self.config.competition.active_group, 1)))
        self.current_try_var = tk.StringVar(value="Try 1")

    def _t(self, key: str, **kwargs) -> str:
        return self.translator(key, **kwargs)

    def _group_display(self, group: str) -> str:
        return self._t("competition.boys") if group == "Boys" else self._t("competition.girls")

    def _group_internal(self, display: str) -> str:
        return "Boys" if display in {"Boys", "Chlapci", self._t("competition.boys")} else "Girls"

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
        self.file_menu.add_command(label=self._t("menu.wizard") + "\tCtrl+N", command=self.start_competition_wizard)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self._t("menu.export") + "\tE", command=self.export_current_attempt)
        self.file_menu.add_command(label=self._t("menu.save_frame") + "\tP", command=self.save_current_frame)
        if self.config.competition.event_export_enabled:
            self.file_menu.add_command(label=self._t("menu.export_event"), command=self.export_competition_package)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self._t("menu.clear") + "\tCtrl+Delete", command=self.clear_all_recordings)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self._t("menu.exports"), command=self.open_exports_folder)
        self.file_menu.add_command(label=self._t("menu.cache"), command=self.open_cache_folder)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self._t("menu.settings"), command=self.open_settings)
        self.file_menu.add_separator()
        self.file_menu.add_command(label=self._t("menu.exit"), command=self.close)

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
        self.view_menu.add_checkbutton(label=self._t("menu.board") + "\tB", variable=self.var_show_board, command=self.toggle_competition_board)
        self.view_menu.add_checkbutton(label=self._t("menu.timeline") + "\tT", variable=self.var_show_timeline, command=self.toggle_timeline)
        self.view_menu.add_checkbutton(label=self._t("menu.live") + "\tL", variable=self.var_show_live, command=self.toggle_live_preview)
        self.view_menu.add_checkbutton(label=self._t("menu.status"), variable=self.var_show_status, command=self.toggle_status_bar)
        self.view_menu.add_separator()
        self.theme_menu = tk.Menu(self.view_menu, tearoff=False, postcommand=self._begin_menu_interaction)
        for value, key in [("system", "theme.system"), ("dark", "theme.dark"), ("light", "theme.light")]:
            self.theme_menu.add_radiobutton(label=self._t(key), variable=self.var_theme, value=value, command=self._menu_theme_changed)
        self.view_menu.add_cascade(label=self._t("menu.theme"), menu=self.theme_menu)
        self.view_menu.add_separator()
        self.view_menu.add_command(label=self._t("menu.calibration"), command=self.toggle_calibration_mode)
        self.view_menu.add_command(label=self._t("menu.comparison") + "\tC", command=self.toggle_comparison)
        self.view_menu.add_command(label=self._t("menu.fullscreen") + "\tF11", command=self.toggle_fullscreen)
        self.view_menu.add_command(label=self._t("menu.reset") + "\tR", command=self.reset_video_views)
        self.view_menu.add_command(label=self._t("menu.guide") + "\tG", command=self.toggle_guide)
        if self.config.competition.operator_mode_enabled:
            self.view_menu.add_separator()
            self.view_menu.add_command(label=self._t("operator.setup") if self._operator_mode else self._t("operator.operator"), command=self.toggle_operator_mode)

        self.help_menu = tk.Menu(self.root, tearoff=False, postcommand=self._begin_menu_interaction)
        self.help_menu.add_command(label=self._t("menu.controls"), command=self.show_controls)
        self.help_menu.add_command(label=self._t("menu.diagnostics"), command=self.show_diagnostics)
        if self.config.competition.camera_diagnostic_enabled:
            self.help_menu.add_command(label="Camera diagnostic", command=self.open_camera_diagnostic)
        self.help_menu.add_separator()
        self.help_menu.add_command(label=self._t("menu.about"), command=lambda: messagebox.showinfo(self._t("menu.about"), "Long Jump Replay 2.3\nLive video review for long-jump take-off decisions."))
        self._style_all_menus()

    def _style_all_menus(self) -> None:
        for name in ("file_menu", "view_menu", "layout_menu", "theme_menu", "help_menu", "special_result_menu"):
            menu = getattr(self, name, None)
            if isinstance(menu, tk.Menu):
                self.theme.style_menu(menu)

    def _attach_header_menus(self, header: ttk.Frame) -> None:
        self.header_menu_frame = ttk.Frame(header, style="Panel.TFrame")
        self.header_menu_frame.pack(side="left", padx=(22, 0))
        self.file_menu_button = ttk.Menubutton(self.header_menu_frame, text=self._t("menu.file"), menu=self.file_menu, style="Header.TMenubutton")
        self.view_menu_button = ttk.Menubutton(self.header_menu_frame, text=self._t("menu.view"), menu=self.view_menu, style="Header.TMenubutton")
        self.help_menu_button = ttk.Menubutton(self.header_menu_frame, text=self._t("menu.help"), menu=self.help_menu, style="Header.TMenubutton")
        for button in (self.file_menu_button, self.view_menu_button, self.help_menu_button):
            button.pack(side="left", padx=1)
            button.bind("<ButtonPress-1>", lambda _e: self._begin_menu_interaction(), add="+")

    def _build_layout(self) -> None:
        self.outer = ttk.Frame(self.root, style="App.TFrame", padding=(12, 10, 12, 10))
        self.outer.pack(fill="both", expand=True)

        header = ttk.Frame(self.outer, style="JudgeHeader.TFrame", padding=(14, 9))
        header.pack(fill="x", pady=(0, 8))
        header_brand = ttk.Frame(header, style="Panel.TFrame")
        header_brand.pack(side="left")
        self.header_title = ttk.Label(header_brand, text=self._t("app.header"), style="Brand.TLabel")
        self.header_title.pack(anchor="w")
        self.header_subtitle = ttk.Label(header_brand, text=self._t("app.subtitle"), style="BrandSub.TLabel")
        self.header_subtitle.pack(anchor="w")
        self._attach_header_menus(header)
        ttk.Label(header, textvariable=self.camera_var, style="Muted.TLabel").pack(side="left", padx=(18, 0), pady=(3, 0))
        self.timer_frame = tk.Frame(header, borderwidth=0, highlightthickness=1, cursor="hand2")
        self.timer_frame.pack(side="right", padx=(12, 0), pady=(1, 0))
        self.timer_prefix_label = tk.Label(self.timer_frame, textvariable=self.timer_prefix_var, borderwidth=0, cursor="hand2", font=("Segoe UI Semibold", 10))
        self.timer_prefix_label.pack(side="left", padx=(6, 5), pady=3)
        self.timer_value_label = tk.Label(self.timer_frame, textvariable=self.timer_value_var, borderwidth=0, cursor="hand2", font=("Consolas", 12, "bold"))
        self.timer_value_label.pack(side="left", padx=(0, 6), pady=3)
        for widget in (self.timer_frame, self.timer_prefix_label, self.timer_value_label):
            widget.bind("<Button-1>", lambda _event: self.toggle_athlete_timer())
        self.system_pause_button = ttk.Button(header, text=self._t("button.pause_system"), style="SystemPause.TButton", command=self.toggle_system_pause)
        self.system_pause_button.pack(side="right", padx=(12, 0), pady=(1, 0))
        self.mode_badge = tk.Label(header, textvariable=self.mode_var, padx=10, pady=4, borderwidth=0, font=("Segoe UI Semibold", 9))
        self.mode_badge.pack(side="right", padx=(10, 0))
        ttk.Label(header, textvariable=self.clock_var, style="Muted.TLabel").pack(side="right", pady=(3, 0))
        self._update_athlete_timer_display()

        self.warning_banner = tk.Label(self.outer, textvariable=self.warning_var, anchor="w", padx=10, pady=5, font=("Segoe UI Semibold", 9))
        self.competition_banner = tk.Label(self.outer, textvariable=self.competition_banner_var, anchor="center", padx=10, pady=5, font=("Segoe UI Semibold", 9))

        self.competition_bar = ttk.Frame(self.outer, style="Toolbar.TFrame", padding=(12, 8))
        self.current_athlete_label = ttk.Label(self.competition_bar, text=self._t("competition.current"), style="ContextTitle.TLabel")
        self.current_athlete_label.pack(side="left", padx=(0, 8))
        self.group_combo = ttk.Combobox(self.competition_bar, textvariable=self.group_var, state="readonly", width=9)
        self.group_combo.pack(side="left"); self.group_combo.bind("<<ComboboxSelected>>", self._group_changed)
        self.competitor_combo = ttk.Combobox(self.competition_bar, textvariable=self.competitor_var, state="readonly", width=7)
        self.competitor_combo.pack(side="left", padx=(6, 8)); self.competitor_combo.bind("<<ComboboxSelected>>", self._competitor_changed)
        ttk.Label(self.competition_bar, textvariable=self.current_try_var, style="ContextValue.TLabel").pack(side="left")
        self.prev_athlete_button = ttk.Button(self.competition_bar, text=self._t("competition.previous"), style="Control.TButton", command=lambda: self._select_competitor_delta(-1))
        self.prev_athlete_button.pack(side="right", padx=(5, 0))
        self.next_athlete_button = ttk.Button(self.competition_bar, text=self._t("competition.next"), style="Control.TButton", command=lambda: self._select_competitor_delta(1))
        self.next_athlete_button.pack(side="right")
        self.special_result_button = ttk.Menubutton(self.competition_bar, text=self._t("button.more"))
        self.special_result_menu = tk.Menu(self.special_result_button, tearoff=False)
        self.special_result_menu.add_command(label=self._t("status.passed"), command=lambda: self.mark_special_result(AttemptDecision.PASSED))
        self.special_result_menu.add_command(label=self._t("status.missing"), command=lambda: self.mark_special_result(AttemptDecision.MISSING))
        self.special_result_menu.add_command(label=self._t("status.withdrawn"), command=lambda: self.mark_special_result(AttemptDecision.WITHDRAWN))
        self.special_result_menu.add_separator()
        self.special_result_menu.add_command(label=self._t("status.reattempt"), command=self.grant_reattempt)
        self.special_result_button.configure(menu=self.special_result_menu)
        self.theme.style_menu(self.special_result_menu)
        self.special_result_button.pack(side="right", padx=(0, 8))
        self.competition_bar.pack(fill="x", pady=(0, 6))
        self.wizard_button = ttk.Button(self.outer, text=self._t("button.wizard"), style="Accent.TButton", command=self.start_competition_wizard)
        self.wizard_button.pack(anchor="w", pady=(0, 6))

        self.content_pane = ttk.Panedwindow(self.outer, orient="horizontal")
        self.content_pane.pack(fill="both", expand=True)
        self.workspace = ttk.Frame(self.content_pane, style="App.TFrame")
        self.attempts_panel = self._build_attempts_panel(self.content_pane)
        self.content_pane.add(self.workspace, weight=5)

        self.media_pane = ttk.Panedwindow(self.workspace, orient="vertical")
        self.media_pane.pack(fill="both", expand=True)
        self.video_host = ttk.Frame(self.media_pane, style="Panel.TFrame", height=520)
        kwargs = self._video_calibration_kwargs()
        self.replay_canvas = VideoCanvas(self.video_host, self.palette, guide_changed=self._guide_changed, calibration_changed=self._calibration_changed, language=self.config.general.language, **kwargs)
        self.live_canvas = VideoCanvas(self.video_host, self.palette, compact=True, language=self.config.general.language, **kwargs)
        self.board_canvas = VideoCanvas(self.video_host, self.palette, compact=True, guide_enabled=False, board_roi_enabled=False, board_roi_visible=False, language=self.config.general.language)
        self.comparison_prev_canvas = VideoCanvas(self.video_host, self.palette, compact=True, guide_enabled=False, board_roi_enabled=False, board_roi_visible=False, language=self.config.general.language)
        self.comparison_next_canvas = VideoCanvas(self.video_host, self.palette, compact=True, guide_enabled=False, board_roi_enabled=False, board_roi_visible=False, language=self.config.general.language)

        self.timeline_wrap = ttk.Frame(self.workspace, style="Panel.TFrame", padding=(8, 7), height=max(165, self.config.display.timeline_height))
        self.timeline = ProfessionalTimeline(
            self.timeline_wrap, self.palette, self.seek_timeline,
            detail_window_seconds=self.config.timeline.detail_window_seconds,
            min_detail_seconds=self.config.timeline.min_detail_seconds,
            max_detail_seconds=self.config.timeline.max_detail_seconds,
            language=self.config.general.language,
        )
        self.timeline.pack(fill="both", expand=True)
        self.media_pane.add(self.video_host, weight=5)
        self.media_pane.add(self.timeline_wrap, weight=1)
        self._timeline_pane_added = True
        self.root.after_idle(self._set_timeline_sash)
        self.root.after(180, self._set_timeline_sash)

        self.controls = ttk.Frame(self.workspace, style="ControlDock.TFrame", padding=(10, 8))
        self.controls.pack(fill="x", pady=(8, 0))
        self.freeze_button = ttk.Button(self.controls, text=self._t("button.freeze"), style="PrimaryJudge.TButton", command=self.toggle_freeze)
        self.freeze_button.pack(side="left")
        self.live_button = ttk.Button(self.controls, text=self._t("button.live"), style="LiveJudge.TButton", command=self.return_live)
        self.live_button.pack(side="left", padx=(6, 12))
        self.prev_frame_button = ttk.Button(self.controls, text=self._t("button.previous_frame"), width=10, style="Control.TButton", command=lambda: self.step_frame(-1))
        self.prev_frame_button.pack(side="left", padx=2)
        self.next_frame_button = ttk.Button(self.controls, text=self._t("button.next_frame"), width=10, style="Control.TButton", command=lambda: self.step_frame(1))
        self.next_frame_button.pack(side="left", padx=2)
        ttk.Separator(self.controls, orient="vertical").pack(side="left", fill="y", padx=10)

        self.decision_frame = ttk.Frame(self.controls, style="Panel.TFrame")
        self.not_decided_button = ttk.Button(self.decision_frame, text=self._t("button.not_decided"), width=12, style="Control.TButton", command=lambda: self.mark_decision(AttemptDecision.NOT_DECIDED))
        self.not_decided_button.pack(side="left", padx=2)
        self.valid_button = ttk.Button(self.decision_frame, text=self._t("button.valid"), width=8, style="JudgeValid.TButton", command=lambda: self.mark_decision(AttemptDecision.VALID))
        self.valid_button.pack(side="left", padx=2)
        self.foul_button = ttk.Button(self.decision_frame, text=self._t("button.foul"), width=8, style="JudgeFoul.TButton", command=lambda: self.mark_decision(AttemptDecision.FOUL))
        self.foul_button.pack(side="left", padx=2)
        self.review_button = ttk.Button(self.decision_frame, text=self._t("button.review"), width=8, style="JudgeReview.TButton", command=lambda: self.mark_decision(AttemptDecision.REVIEW))
        self.review_button.pack(side="left", padx=2)
        self.decision_frame.pack(side="left")

        self.board_setup_button = ttk.Button(self.controls, text=self._t("button.board_setup"), width=12, style="Control.TButton", command=self.toggle_calibration_mode)
        self.board_setup_button.pack(side="right", padx=(6, 0))

        self.center_overlay = tk.Label(self.video_host, text="", justify="center", padx=18, pady=10, font=("Segoe UI Semibold", 14), borderwidth=0)

        self.status_bar = ttk.Frame(self.workspace, style="Toolbar.TFrame", padding=(10, 5))
        self.status_bar.pack(fill="x", pady=(5, 0))
        ttk.Label(self.status_bar, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
        ttk.Label(self.status_bar, textvariable=self.message_var, style="Status.TLabel").pack(side="right")

    def _video_calibration_kwargs(self) -> dict:
        d = self.config.display
        return dict(
            guide_enabled=d.guide_enabled,
            guide_x_ratio=d.guide_x_ratio,
            guide_y_ratio=d.guide_y_ratio,
            guide_angle_deg=d.guide_angle_deg,
            board_roi=(d.board_roi_x, d.board_roi_y, d.board_roi_width, d.board_roi_height),
            board_roi_enabled=d.board_roi_enabled,
            board_roi_visible=d.board_roi_visible,
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
        self.side_notebook.add(self.recordings_tab, text=self._t("attempts.title").title())
        self.side_notebook.add(self.board_tab, text=self._t("board.title").title())

        tree = ttk.Treeview(self.recordings_tab, columns=("group", "athlete", "try", "result", "time", "media", "keep"), show="headings", selectmode="browse")
        specs = [
            ("group", self._t("table.group"), 54), ("athlete", "#", 30), ("try", self._t("table.attempt"), 50),
            ("result", self._t("table.result"), 82), ("time", self._t("table.time"), 58), ("media", self._t("table.media"), 65), ("keep", self._t("table.keep"), 54),
        ]
        for key, label, width in specs:
            tree.heading(key, text=label); tree.column(key, width=width, anchor="center", stretch=key in {"result", "media"})
        tree.pack(fill="both", expand=True)
        tree.bind("<<TreeviewSelect>>", self._attempt_tree_selected)
        tree.bind("<Double-1>", lambda _e: self._attempt_tree_selected(None))
        self.attempt_tree = tree

        self.competition_board = CompetitionBoard(self.board_tab, self.palette, self._open_attempt_from_board, self._select_cell_from_board)
        self.competition_board.pack(fill="both", expand=True)

        footer = ttk.Frame(frame, style="Panel.TFrame")
        footer.pack(fill="x", pady=(6, 0))
        row = ttk.Frame(footer, style="Panel.TFrame"); row.pack(fill="x")
        self.export_button = ttk.Button(row, text=self._t("attempts.export"), command=self.export_current_attempt, style="Control.TButton")
        self.export_button.pack(side="left", fill="x", expand=True)
        self.delete_button = ttk.Button(row, text=self._t("attempts.delete"), command=self.delete_current_attempt, style="Control.TButton")
        self.delete_button.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.clear_button = ttk.Button(footer, text=self._t("attempts.clear"), command=self.clear_all_recordings, style="Danger.TButton")
        self.clear_button.pack(fill="x", pady=(5, 0))
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
        }
        if not (self.config.competition.enabled and self.config.competition.keyboard_competition_controls):
            for name in ("previous_athlete", "next_athlete", "mark_passed"):
                actions.pop(name, None)
        self.hotkeys.attach_tree()
        if self.config.hotkeys.enabled:
            self.hotkeys.install(self.config.hotkeys.bindings, actions)

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
        interval = max(4, round(1000 / self._effective_preview_hz()))
        self._tick_job = self.root.after(interval, self._tick)

    def _preview_frame(self, frame: np.ndarray) -> np.ndarray:
        scale = float(self.config.performance.preview_scale)
        if scale >= .995:
            return frame
        h, w = frame.shape[:2]
        return cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)

    def _tick(self) -> None:
        if self._closing: return
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
        p = self.palette; stats = self.capture.stats()
        if self._system_paused:
            self.mode_var.set(self._t("mode.paused")); self.mode_badge.configure(bg=p["muted"], fg="#ffffff")
            self.live_canvas.set_status(self._t("mode.paused"), p["muted"])
            self.replay_canvas.set_status(self._t("mode.paused"), p["muted"], self._t("system.paused_status"))
            return
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
                secondary = f"{self._attempt_roster_display(attempt)} · {self._t("overlay.frame")} {self.playback.attempt_frame_index + 1}/{max(1, attempt.frame_count)} · {rel:+.3f} s · {self._decision_display(attempt.decision)}{assist}"
                color = self._decision_color(attempt.decision)
                self.replay_canvas.set_status(label, color, secondary)

    def _update_status(self) -> None:
        if self._system_paused:
            self.camera_var.set(self._t("mode.paused")); self.clock_var.set(time.strftime("%H:%M:%S"))
            self.status_var.set(self._t("system.paused_status"))
            if self._warning_active:
                self.warning_banner.pack_forget(); self.warning_var.set(""); self._warning_active = False
            return
        capture, buffer = self.capture.stats(), self.buffer.stats()
        cache_gb = self.attempts.cache_size_bytes() / 1024 ** 3
        self.camera_var.set(capture.source_description); self.clock_var.set(time.strftime("%H:%M:%S"))
        self.status_var.set(
            f"CAP {capture.capture_fps:5.1f} fps  ·  BUFFER {capture.encode_fps:5.1f} fps / {buffer.duration_seconds:4.1f} s  ·  "
            f"RAM {buffer.memory_bytes / 1024 ** 2:,.0f} MB  ·  drops {capture.queue_drops}  ·  cache {cache_gb:.2f} GB"
        )
        warning = self._capture_quality_warning(capture)
        if self.config.display.show_capture_warnings and warning:
            self.warning_var.set(f"⚠ {warning}")
            self.warning_banner.configure(bg=self.palette["warning"], fg="#111111")
            if not self.warning_banner.winfo_manager(): self.warning_banner.pack(fill="x", after=self.outer.winfo_children()[0], pady=(0, 6))
            self._warning_active = True
        elif self._warning_active:
            self.warning_banner.pack_forget(); self.warning_var.set(""); self._warning_active = False
        if time.perf_counter() >= self._message_until: self.message_var.set(self.shuttle.status)
        if capture.last_error and capture.last_error != self._last_error:
            self._last_error = capture.last_error; self._show_message(f"Camera: {capture.last_error}", 8)

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
        signature = (snapshot.state, snapshot.remaining_seconds, prefix, prefix_visible, prefix_color, value_color, background, p["border"])
        if signature == self._last_timer_render_signature:
            return
        self._last_timer_render_signature = signature
        self.timer_frame.configure(highlightbackground=p["border"], highlightcolor=p["accent"])
        self.timer_frame.configure(bg=background)
        self.timer_prefix_label.configure(bg=background)
        self.timer_value_label.configure(bg=background)
        self.timer_value_var.set(format_countdown(snapshot.remaining_seconds))
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

    def _set_system_paused_ui(self) -> None:
        paused_or_stopping = self._system_paused or self._system_pause_transition
        self.system_pause_button.configure(
            text=self._t("button.resume_system") if self._system_paused and not self._system_pause_transition else self._t("button.pause_system"),
            style="SystemResume.TButton" if self._system_paused and not self._system_pause_transition else "SystemPause.TButton",
        )
        self.system_pause_button.state(["disabled"] if self._system_pause_transition else ["!disabled"])
        state = ["disabled"] if paused_or_stopping else ["!disabled"]
        for button in (
            self.freeze_button, self.live_button, self.prev_frame_button, self.next_frame_button,
            self.not_decided_button, self.valid_button, self.foul_button, self.review_button,
        ):
            button.state(state)
        self._update_video_labels()
        self._update_status()

    def toggle_system_pause(self) -> None:
        if self._system_pause_transition:
            return
        if self._system_paused:
            self.capture.start()
            self._system_paused = False
            self._last_live_index = -1
            self._last_replay_key = None
            self._set_system_paused_ui()
            self._show_message(self._t("system.resumed"), 5)
            return

        self._cancel_scheduled_review()
        self._system_paused = True
        self._system_pause_transition = True
        self.playback.go_live()
        self.athlete_timer.reset(); self._update_athlete_timer_display()
        self._show_message(self._t("system.pausing"), 5)
        self._set_system_paused_ui()

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

    def _update_timeline(self) -> None:
        oldest, newest = self.buffer.oldest(), self.buffer.newest()
        if self.playback.mode is PlaybackMode.ATTEMPT and self.playback.attempt_id is not None:
            attempt = self.attempts.get_attempt(self.playback.attempt_id)
            if not attempt or attempt.frame_count <= 0: return
            playhead = self._displayed_timestamp_ns or (attempt.start_timestamp_ns + int(self.playback.attempt_frame_index / max(1.0, attempt.fps) * 1e9))
            markers = [m.timestamp_ns for m in attempt.markers]
            if attempt.takeoff_candidate_index is not None:
                markers.append(attempt.start_timestamp_ns + int(attempt.takeoff_candidate_index / max(1.0, attempt.fps) * 1e9))
            model = TimelineModel(attempt.start_timestamp_ns, max(attempt.start_timestamp_ns + 1, attempt.end_timestamp_ns), playhead,
                                  attempt.freeze_timestamp_ns, attempt.freeze_timestamp_ns, tuple(markers),
                                  attempt.start_timestamp_ns, attempt.end_timestamp_ns, False)
        elif oldest and newest:
            packet = newest if self.playback.mode is PlaybackMode.LIVE else self.buffer.get(self.playback.live_seq)
            model = TimelineModel(oldest.timestamp_ns, newest.timestamp_ns, packet.timestamp_ns if packet else newest.timestamp_ns,
                                  newest.timestamp_ns, None, (), oldest.timestamp_ns, newest.timestamp_ns,
                                  self.playback.mode is PlaybackMode.LIVE)
        else: model = None
        self.timeline.set_model(model)

    # ------------------------------------------------------------ competition
    def _refresh_competitor_selector(self) -> None:
        c = self.config.competition
        visible = c.enabled and c.show_competitor_selector and not self._operator_mode
        if visible and not self.competition_bar.winfo_manager(): self.competition_bar.pack(fill="x", before=self.content_pane, pady=(0, 6))
        elif not visible and self.competition_bar.winfo_manager(): self.competition_bar.pack_forget()
        groups = self.competition.enabled_groups()
        self.group_combo.configure(values=[self._group_display(value) for value in groups])
        group = self.competition.current_group()
        self.group_var.set(self._group_display(group))
        count = self.competition.competitor_count(group)
        values = [str(i) for i in range(1, count + 1)]
        self.competitor_combo.configure(values=values)
        self.competitor_var.set(str(self.competition.current_competitor()))
        if c.enable_special_results and visible:
            if not self.special_result_button.winfo_manager(): self.special_result_button.pack(side="right", padx=(0, 8))
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
        if assignment:
            limit = self.competition.attempt_limit(assignment.group, assignment.competitor_number)
            self.current_try_var.set(self._t("competition.try", current=assignment.attempt_number, limit=limit))
            count = self.competition.competitor_count(assignment.group)
            phase_total = self.config.competition.final_attempts if assignment.phase == "final" else self.competition.qualification_limit(assignment.group, assignment.competitor_number)
            phase_round = assignment.attempt_number - self.competition.qualification_limit(assignment.group, assignment.competitor_number) if assignment.phase == "final" else assignment.attempt_number
            self.competition_banner_var.set(self._t("competition.banner", group=self._group_display(assignment.group), round=phase_round, total=phase_total, athlete=assignment.competitor_number, count=count, attempt=assignment.attempt_number))
        else:
            self.current_try_var.set(self._t("competition.roster_disabled"))
            self.competition_banner_var.set("")
        self._refresh_competition_board(attempts, assignment)

    def _refresh_competition_board(self, attempts: list[AttemptSession], assignment: RosterAssignment | None) -> None:
        if not hasattr(self, "competition_board"):
            return
        group = self.competition.current_group()
        board_assignment = self._board_next_assignment if self.playback.mode is PlaybackMode.ATTEMPT and self._board_next_assignment else assignment
        athlete = board_assignment.competitor_number if board_assignment else self.competition.current_competitor()
        attempt_no = board_assignment.attempt_number if board_assignment else 0
        signature = (
            group, athlete, attempt_no, self.config.competition.enabled, self.config.competition.show_competition_board,
            self.config.competition.boys_competitors, self.config.competition.girls_competitors,
            self.config.competition.default_attempts_per_competitor, self.config.competition.final_round_enabled,
            self.config.competition.final_attempts, tuple(self.config.competition.finalist_numbers_by_group.get(group, [])),
            tuple((a.attempt_id, a.decision.value, a.competitor_number, a.competitor_attempt_number) for a in attempts),
        )
        if signature == self._last_board_signature:
            return
        self._last_board_signature = signature
        self.competition_board.set_data(self.config.competition, group, attempts, athlete, attempt_no, self.config.general.language)

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
        self._board_next_assignment = None
        group = self.competition.current_group()
        assignment = self.competition.select_attempt_cell(group, athlete, attempt_no)
        if assignment is None:
            try: self.competition.set_current(group, athlete)
            except ValueError: return
        self.athlete_timer.reset(); self._update_athlete_timer_display()
        self._last_board_signature = None; self._refresh_competitor_selector(); self._save_config_safely()

    def _open_attempt_from_board(self, attempt_id: int) -> None:
        self._cancel_scheduled_review()
        if self.playback.select_attempt(attempt_id):
            self._last_replay_key = None; self.timeline.detail_center_ns = None; self._refresh_attempts()

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
        attempts = self.attempts.attempts(); ids = {str(a.attempt_id) for a in attempts}
        for item in self.attempt_tree.get_children():
            if item not in ids: self.attempt_tree.delete(item)
        p = self.palette
        self.attempt_tree.tag_configure("valid", background=p["valid_soft"])
        self.attempt_tree.tag_configure("foul", background=p["foul_soft"])
        self.attempt_tree.tag_configure("review", background=p["review_soft"])
        self.attempt_tree.tag_configure("pending", background=p["pending_soft"])
        now = time.time(); selected_id = None
        for row_index, attempt in enumerate(reversed(attempts)):
            iid = str(attempt.attempt_id)
            created = time.strftime("%H:%M:%S", time.localtime(attempt.created_wall_time))
            ttl = self._t("common.open") if attempt.selected else self._format_ttl(attempt.seconds_until_expiry(now))
            media = self._media_state_display(attempt.state)
            if attempt.quality_warning: media = "⚠ " + media
            group = self._group_display(attempt.competitor_group)[:1] if attempt.competitor_group else "—"
            athlete = attempt.competitor_number if attempt.competitor_number else "—"
            try_no = attempt.competitor_attempt_number if attempt.competitor_attempt_number else "—"
            values = (group, athlete, try_no, self._decision_display(attempt.decision), created, media, ttl)
            tag = self._decision_tag(attempt.decision)
            if self.attempt_tree.exists(iid): self.attempt_tree.item(iid, values=values, tags=(tag,))
            else: self.attempt_tree.insert("", "end", iid=iid, values=values, tags=(tag,))
            self.attempt_tree.move(iid, "", row_index)
            if attempt.selected: selected_id = iid
        if selected_id and self.attempt_tree.selection() != (selected_id,):
            self.attempt_tree.selection_set(selected_id); self.attempt_tree.see(selected_id)
        decided = sum(a.decision in {AttemptDecision.VALID, AttemptDecision.FOUL, AttemptDecision.REVIEW} for a in attempts)
        self.attempt_summary_var.set(self._t("attempts.summary", count=len(attempts), decided=decided) if attempts else self._t("attempts.none"))
        self._refresh_competition_board(attempts, self.competition.assignment_for_current(attempts))

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
                attempt_id, path = payload; self._show_message(f"Attempt #{attempt_id:02d} exported: {Path(path).name}", 7)
            elif event == "attempt_error":
                attempt_id, error = payload; self._show_message(f"Attempt #{attempt_id:02d} error: {error}", 10)
            elif event == "takeoff_candidate":
                attempt_id, index, confidence = payload; self._handle_takeoff_candidate(int(attempt_id), int(index), float(confidence))
            elif event == "attempts_cleared":
                self._show_message(f"Cleared {int(payload)} temporary recording(s) and the live buffer.", 5)
            elif event == "system_pause_complete":
                self._system_pause_transition = False
                self.buffer.clear(); self.capture.latest.clear()
                self._displayed_bgr = None; self._displayed_timestamp_ns = 0
                self._last_live_index = -1; self._last_replay_key = None
                for canvas in self._all_video_canvases(): canvas.set_frame(None)
                self._set_system_paused_ui()
            elif event == "message": self._show_message(str(payload), 6)
            elif event in {"attempt_deleted", "attempt_updated", "attempt_selected"}: self._last_attempts_refresh = 0

    # --------------------------------------------------------- core controls
    def toggle_freeze(self) -> None:
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
                self._show_message("The live buffer does not contain a frame yet.", 4); return
            if assignment is not None and self.config.competition.auto_advance_on_attempt_complete:
                self._board_next_assignment = self.competition.next_assignment_after(self.attempts.attempts(), assignment)
            self.competition_board.clear_focus()
            self.athlete_timer.stop(); self._update_athlete_timer_display()
            self._last_replay_key = None; self._last_board_signature = None; self._refresh_attempts()
            if self.config.takeoff_assist.enabled and self.config.display.board_roi_enabled:
                self._start_takeoff_analysis(attempt_id)
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
        self.playback.go_live(); self._last_replay_key = None; self.timeline.detail_center_ns = None
        self._board_next_assignment = None; self.competition_board.clear_focus(); self._last_board_signature = None
        if returning_from_replay:
            self.athlete_timer.reset(); self._update_athlete_timer_display()
        self._refresh_current_try()
        return True

    def return_live(self) -> None:
        if self._system_paused:
            self._show_message(self._t("system.paused_message"), 5); return
        self._cancel_scheduled_review()
        self._enter_live(complete_rotation=True)

    def step_frame(self, delta: int) -> None:
        if self._system_paused:
            self._show_message(self._t("system.paused_message"), 5); return
        self._cancel_scheduled_review(); self.playback.step(delta); self._last_replay_key = None

    def select_relative_attempt(self, delta: int) -> None:
        self._cancel_scheduled_review()
        if self.playback.select_relative_attempt(delta):
            self._last_replay_key = None; self.timeline.detail_center_ns = None; self._refresh_attempts()
            attempt = self.attempts.get_attempt(self.playback.attempt_id or -1)
            if attempt:
                self._show_message(f"{self._attempt_roster_display(attempt)} · {self._decision_display(attempt.decision)}", 2)

    def seek_timeline(self, timestamp_ns: int) -> None:
        self._cancel_scheduled_review(); self.playback.seek_timestamp(timestamp_ns); self._last_replay_key = None

    def add_marker(self) -> None:
        if self._system_paused:
            self._show_message(self._t("system.paused_message"), 5); return
        if self.playback.mode is PlaybackMode.LIVE: self.toggle_freeze()
        if self.playback.mode is not PlaybackMode.ATTEMPT or self.playback.attempt_id is None:
            self._show_message("Markers belong to an attempt. Freeze first.", 4); return
        if self._displayed_timestamp_ns and self.attempts.add_marker(self.playback.attempt_id, self._displayed_timestamp_ns):
            self._show_message("Marker added.", 3); self._last_timeline_update = 0

    def mark_decision(self, decision: AttemptDecision) -> None:
        if self._system_paused:
            self._show_message(self._t("system.paused_message"), 5); return
        if not self.config.competition.decision_controls_enabled and not self.config.display.show_decision_controls: return
        if self.playback.mode is not PlaybackMode.ATTEMPT or self.playback.attempt_id is None:
            self._show_message("Freeze or select an attempt before recording a decision.", 5); return
        attempt_id = self.playback.attempt_id
        if not self.attempts.set_decision(attempt_id, decision): return
        attempt = self.attempts.get_attempt(attempt_id)
        if attempt and self.config.competition.auto_save_evidence and decision in {AttemptDecision.VALID, AttemptDecision.FOUL, AttemptDecision.REVIEW}:
            try: self._save_evidence(attempt, decision)
            except Exception as exc: self._show_message(f"Evidence could not be saved: {exc}", 8)
        self._show_message(self._t("message.decision_marked", roster=self._attempt_roster_display(attempt) if attempt else f"#{attempt_id:02d}", decision=self._decision_display(decision).upper()), 5)
        if self.config.competition.enabled and self.config.competition.auto_advance_after_decision and attempt and not attempt.rotation_completed:
            self.attempts.set_rotation_completed(attempt_id, True)
            next_assignment = self.competition.advance(self.attempts.attempts())
            self._refresh_competitor_selector(); self._save_config_safely()
            if next_assignment and self.config.competition.next_athlete_overlay:
                self._show_next_athlete_overlay(next_assignment)
        self._last_attempts_refresh = 0; self._last_board_signature = None
        if self.config.competition.auto_return_live:
            delay = max(0, int(self.config.competition.auto_return_delay_seconds * 1000))
            if self._auto_live_job:
                try: self.root.after_cancel(self._auto_live_job)
                except tk.TclError: pass
            self._auto_live_job = self.root.after(delay, self.return_live)

    def mark_special_result(self, decision: AttemptDecision) -> None:
        if self._system_paused:
            self._show_message(self._t("system.paused_message"), 5); return
        if not self.config.competition.enabled or not self.config.competition.enable_special_results:
            self._show_message("Special competition results are disabled in Settings.", 5); return
        assignment = self.competition.assignment_for_current(self.attempts.attempts())
        if assignment is None:
            self._show_message("No pending attempt is available for the current athlete.", 5); return
        self.attempts.create_placeholder_attempt(assignment.group, assignment.competitor_number, assignment.attempt_number, decision, assignment.phase)
        next_assignment = self.competition.advance(self.attempts.attempts())
        self._last_board_signature = None; self._refresh_competitor_selector(); self._refresh_attempts(); self._save_config_safely()
        if next_assignment and self.config.competition.next_athlete_overlay:
            self._show_next_athlete_overlay(next_assignment)

    def grant_reattempt(self) -> None:
        if self.playback.mode is not PlaybackMode.ATTEMPT or self.playback.attempt_id is None:
            self._show_message("Select the attempt that should be repeated.", 5); return
        attempt = self.attempts.get_attempt(self.playback.attempt_id)
        if not attempt or attempt.competitor_number <= 0:
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
        dialog = tk.Toplevel(self.root); dialog.title("Select finalists"); dialog.geometry("430x560"); dialog.transient(self.root); dialog.grab_set()
        ttk.Label(dialog, text=f"Select up to {self.config.competition.finalists_count} {group} finalists", style="Title.TLabel").pack(anchor="w", padx=14, pady=(14, 6))
        ttk.Label(dialog, text="This replay tool does not measure distance, so qualification order is selected manually.", style="Muted.TLabel", wraplength=390, justify="left").pack(anchor="w", padx=14, pady=(0, 10))
        host = ttk.Frame(dialog, style="Panel.TFrame"); host.pack(fill="both", expand=True, padx=14)
        canvas = tk.Canvas(host, highlightthickness=0, background=self.palette["surface"]); bar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview); canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True); bar.pack(side="right", fill="y")
        inner = ttk.Frame(canvas, style="Panel.TFrame"); win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all"))); canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        vars_: dict[int, tk.BooleanVar] = {}
        current = set(self.config.competition.finalist_numbers_by_group.get(group, []))
        for number in range(1, self.competition.competitor_count(group) + 1):
            var = tk.BooleanVar(value=number in current); vars_[number] = var
            ttk.Checkbutton(inner, text=f"Athlete #{number:02d}", variable=var).pack(anchor="w", pady=3, padx=8)
        footer = ttk.Frame(dialog, style="Toolbar.TFrame", padding=8); footer.pack(fill="x", padx=14, pady=14)
        def apply_selection() -> None:
            selected = [n for n, var in vars_.items() if var.get()]
            if not selected:
                messagebox.showerror("Select finalists", "Select at least one athlete.", parent=dialog); return
            if len(selected) > self.config.competition.finalists_count:
                messagebox.showerror("Select finalists", f"Select no more than {self.config.competition.finalists_count} athletes.", parent=dialog); return
            self.competition.set_finalists(group, selected); dialog.destroy()
        ttk.Button(footer, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(footer, text="Use selected athletes", style="Accent.TButton", command=apply_selection).pack(side="right", padx=(0, 7))
        self.root.wait_window(dialog)

    def _show_next_athlete_overlay(self, assignment: RosterAssignment) -> None:
        self.center_overlay.configure(text=self._t("competition.next_overlay", group=self._group_display(assignment.group), athlete=assignment.competitor_number, attempt=assignment.attempt_number), bg=self.palette["surface2"], fg=self.palette["text"])
        self.center_overlay.place(relx=.5, rely=.5, anchor="center")
        self.root.after(1400, lambda: self.center_overlay.place_forget() if self.center_overlay.winfo_exists() else None)

    def save_current_frame(self) -> None:
        if self._displayed_bgr is None:
            self._show_message("No frame is available yet.", 4); return
        try:
            prefix = f"attempt_{self.playback.attempt_id:02d}" if self.playback.attempt_id else "live"
            path = save_bgr_png(self._displayed_bgr, self._exports_directory(), prefix=prefix)
            self._show_message(f"Frame saved: {path.name}", 6)
        except Exception as exc: messagebox.showerror("Save frame", str(exc))

    def _save_evidence(self, attempt: AttemptSession, decision: AttemptDecision) -> None:
        frame = self._displayed_bgr
        if frame is None: return
        directory = self._evidence_directory(); directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")[:-3]
        roster = f"{attempt.competitor_group.lower()}-{attempt.competitor_number}_try-{attempt.competitor_attempt_number}" if attempt.competitor_number else f"attempt-{attempt.attempt_id}"
        base = directory / f"{roster}_{decision.value.lower()}_{stamp}"
        raw_path = None; annotated_path = None
        if self.config.export.evidence_save_raw:
            raw_path = base.with_name(base.name + "_raw.png")
            if not cv2.imwrite(str(raw_path), frame): raise RuntimeError("Could not write raw evidence PNG")
        if self.config.export.evidence_include_overlay:
            annotated = frame.copy(); self._draw_evidence_overlay(annotated, attempt, decision)
            annotated_path = base.with_name(base.name + "_annotated.png")
            if not cv2.imwrite(str(annotated_path), annotated): raise RuntimeError("Could not write annotated evidence PNG")
        metadata = {
            "attempt_id": attempt.attempt_id, "group": attempt.competitor_group, "competitor": attempt.competitor_number,
            "try": attempt.competitor_attempt_number, "decision": decision.value, "created_local": datetime.now().astimezone().isoformat(),
            "frame_index": self.playback.attempt_frame_index, "frame_timestamp_ns": self._displayed_timestamp_ns,
            "capture_fps": self.capture.stats().capture_fps, "quality_warning": attempt.quality_warning,
            "guide": {"x": self.config.display.guide_x_ratio, "y": self.config.display.guide_y_ratio, "angle_deg": self.config.display.guide_angle_deg},
            "board_roi": [self.config.display.board_roi_x, self.config.display.board_roi_y, self.config.display.board_roi_width, self.config.display.board_roi_height],
            "raw_file": raw_path.name if raw_path else None, "annotated_file": annotated_path.name if annotated_path else None,
        }
        base.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        self.attempts.set_evidence_paths(attempt.attempt_id, raw_path, annotated_path)

    def _draw_evidence_overlay(self, frame: np.ndarray, attempt: AttemptSession, decision: AttemptDecision) -> None:
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
        label = f"{self._attempt_roster_display(attempt)}  |  {self._decision_display(decision).upper()}  |  {self._t("overlay.frame")} {self.playback.attempt_frame_index + 1}/{max(1, attempt.frame_count)}"
        cv2.putText(frame, label, (25, 44), cv2.FONT_HERSHEY_SIMPLEX, .72, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), (25, 70), cv2.FONT_HERSHEY_SIMPLEX, .52, (190, 200, 215), 1, cv2.LINE_AA)

    def export_current_attempt(self) -> None:
        if self.playback.mode is not PlaybackMode.ATTEMPT or self.playback.attempt_id is None:
            self._show_message("Select or freeze an attempt before exporting.", 5); return
        if self.attempts.request_export(self.playback.attempt_id, self._exports_directory()):
            self._show_message(f"Export requested for attempt #{self.playback.attempt_id:02d}.", 4)
        else: self._show_message("The attempt is not ready for export.", 5)

    def delete_current_attempt(self) -> None:
        attempt_id = self.playback.attempt_id
        if attempt_id is None: return
        if not messagebox.askyesno("Delete attempt", f"Delete temporary attempt #{attempt_id:02d}?\nExported and evidence files are not removed."): return
        self._cancel_scheduled_review()
        self._enter_live(complete_rotation=False)
        if not self.attempts.delete(attempt_id, force=True): self._show_message("This attempt cannot be deleted while it is being encoded or exported.", 5)
        self._refresh_attempts()

    def _ask_clear_recordings_mode(self) -> str | None:
        if not self.config.general.confirm_destructive_actions:
            return "all"
        dialog = tk.Toplevel(self.root)
        dialog.title(self._t("dialog.clear.title"))
        dialog.geometry("520x330")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        result = tk.StringVar(value="")
        attempts = self.attempts.attempts()
        unresolved = sum(a.decision in {AttemptDecision.NOT_DECIDED, AttemptDecision.REVIEW} for a in attempts)
        cache_mb = self.attempts.cache_size_bytes() / 1024**2
        live = self.buffer.stats()
        body = ttk.Frame(dialog, style="App.TFrame", padding=18)
        body.pack(fill="both", expand=True)
        title = "Clear temporary recordings?" if self.config.general.language == "en" else "Vymazat dočasné záznamy?"
        ttk.Label(body, text=title, style="Title.TLabel").pack(anchor="w")
        details = (
            f"{len(attempts)} temporary recordings · {unresolved} unresolved\n"
            f"{cache_mb:.1f} MB cache · {live.duration_seconds:.1f} s live buffer\n\n"
            "Exported MP4 files and evidence images will not be deleted."
            if self.config.general.language == "en" else
            f"{len(attempts)} dočasných záznamů · {unresolved} nerozhodnutých\n"
            f"{cache_mb:.1f} MB cache · {live.duration_seconds:.1f} s živého bufferu\n\n"
            "Exportovaná MP4 a důkazní snímky nebudou smazány."
        )
        ttk.Label(body, text=details, style="Muted.TLabel", justify="left").pack(anchor="w", pady=(7, 16))
        buttons = ttk.Frame(body, style="App.TFrame")
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Clear everything" if self.config.general.language == "en" else "Vymazat vše", style="Danger.TButton", command=lambda: result.set("all")).pack(fill="x", pady=3)
        ttk.Button(buttons, text="Clear live buffer only" if self.config.general.language == "en" else "Vymazat jen živý buffer", command=lambda: result.set("live")).pack(fill="x", pady=3)
        ttk.Button(buttons, text="Clear unresolved recordings" if self.config.general.language == "en" else "Vymazat nerozhodnuté záznamy", command=lambda: result.set("unresolved")).pack(fill="x", pady=3)
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
            count = self.attempts.clear_all()
            self.buffer.clear()
        elif mode == "live":
            self.buffer.clear()
        elif mode == "unresolved":
            count = self.attempts.clear_unresolved()
        else:
            raise ValueError(f"Unsupported clear mode: {mode}")
        self._last_replay_key = None
        self._displayed_bgr = None
        self._displayed_timestamp_ns = 0
        self.timeline.set_model(None)
        self._last_board_signature = None
        self._refresh_attempts()
        self._refresh_current_try()
        if mode == "live":
            message = "Live buffer cleared. Capture continues." if self.config.general.language == "en" else "Živý buffer vymazán. Záznam pokračuje."
        elif mode == "unresolved":
            message = f"Cleared {count} unresolved temporary recording(s)." if self.config.general.language == "en" else f"Vymazáno {count} nerozhodnutých dočasných záznamů."
        else:
            message = f"Cleared {count} temporary recording(s). Capture continues with a fresh buffer." if self.config.general.language == "en" else f"Vymazáno {count} dočasných záznamů. Kamera pokračuje s čistým bufferem."
        self._show_message(message, 5)
        return count

    def clear_all_recordings(self) -> None:
        self._clear_recordings_mode("all", ask=True)

    def _attempt_tree_selected(self, _event) -> None:
        selected = self.attempt_tree.selection()
        if not selected: return
        try: attempt_id = int(selected[0])
        except ValueError: return
        if self.playback.attempt_id == attempt_id and self.playback.mode is PlaybackMode.ATTEMPT: return
        self._cancel_scheduled_review()
        if self.playback.select_attempt(attempt_id):
            self._last_replay_key = None; self.timeline.detail_center_ns = None

    # -------------------------------------------------------- Take-off Assist
    def _start_takeoff_analysis(self, attempt_id: int) -> None:
        attempt = self.attempts.get_attempt(attempt_id)
        if not attempt: return
        d, a = self.config.display, self.config.takeoff_assist
        roi = (d.board_roi_x, d.board_roi_y, d.board_roi_width, d.board_roi_height)
        def worker() -> None:
            try:
                if a.analysis_seconds_after_freeze > 0:
                    time.sleep(a.analysis_seconds_after_freeze + .05)
                packets = self.attempts.packets_snapshot(attempt_id)
                if not packets:
                    return
                candidate = detect_takeoff_candidate(packets, attempt.freeze_timestamp_ns, roi,
                                                     a.analysis_seconds_before_freeze, a.analysis_seconds_after_freeze,
                                                     a.downscale_width)
                if candidate:
                    self.attempts.set_takeoff_candidate(attempt_id, candidate.frame_index + a.seek_lead_frames, candidate.confidence)
                else: self.event_queue.put(("message", "Take-off Assist did not find a clear local motion peak."))
            except Exception as exc: self.event_queue.put(("message", f"Take-off Assist error: {exc}"))
        Thread(target=worker, name=f"takeoff-assist-{attempt_id}", daemon=True).start()

    def _handle_takeoff_candidate(self, attempt_id: int, index: int, confidence: float) -> None:
        a = self.config.takeoff_assist
        if confidence < a.minimum_confidence:
            self._show_message(f"Take-off Assist candidate was uncertain ({confidence:.0%}); playhead was not moved.", 5); return
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
        for canvas in (self.replay_canvas, self.live_canvas):
            if canvas is except_canvas: continue
            canvas.set_calibration(d.guide_x_ratio, d.guide_y_ratio, d.guide_angle_deg, roi, d.board_roi_enabled, d.board_roi_visible)

    def toggle_guide(self) -> None:
        enabled = not self.replay_canvas.guide_enabled; self.config.display.guide_enabled = enabled
        self.replay_canvas.set_guide_enabled(enabled); self.live_canvas.set_guide_enabled(enabled); self._save_config_safely()

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
        self.config.competition.show_competition_board = bool(self.var_show_board.get())
        self._apply_visibility(); self._save_config_safely()
    def toggle_timeline(self) -> None:
        self.config.display.show_timeline = bool(self.var_show_timeline.get()); self._apply_visibility(); self._save_config_safely()
    def toggle_live_preview(self) -> None:
        self.config.display.show_live_preview = bool(self.var_show_live.get()); self._apply_layout(); self._save_config_safely()
    def toggle_status_bar(self) -> None:
        self.config.display.show_status_bar = bool(self.var_show_status.get()); self._apply_visibility(); self._save_config_safely()

    def _apply_visibility(self) -> None:
        show_attempts = bool(self.var_show_attempts.get())
        if show_attempts and not self._attempts_pane_added:
            self.content_pane.add(self.attempts_panel, weight=1); self._attempts_pane_added = True
            self.root.after_idle(self._set_attempts_sash)
        elif not show_attempts and self._attempts_pane_added:
            self.content_pane.forget(self.attempts_panel); self._attempts_pane_added = False
        show_timeline = bool(self.var_show_timeline.get())
        if show_timeline and not self._timeline_pane_added:
            self.media_pane.add(self.timeline_wrap, weight=1); self._timeline_pane_added = True; self.root.after_idle(self._set_timeline_sash)
        elif not show_timeline and self._timeline_pane_added:
            self.media_pane.forget(self.timeline_wrap); self._timeline_pane_added = False
        show_status = bool(self.var_show_status.get())
        if show_status and not self.status_bar.winfo_manager(): self.status_bar.pack(fill="x", pady=(4, 0))
        elif not show_status and self.status_bar.winfo_manager(): self.status_bar.pack_forget()
        show_decisions = self.config.competition.decision_controls_enabled and self.config.display.show_decision_controls
        if show_decisions and not self.decision_frame.winfo_manager(): self.decision_frame.pack(side="left")
        elif not show_decisions and self.decision_frame.winfo_manager(): self.decision_frame.pack_forget()
        show_board = bool(self.config.competition.enabled and self.config.competition.show_competition_board and self.var_show_board.get())
        tabs = set(self.side_notebook.tabs())
        board_id = str(self.board_tab)
        if show_board and board_id not in tabs:
            self.side_notebook.add(self.board_tab, text=self._t("board.title").title())
        elif not show_board and board_id in tabs:
            if self.side_notebook.select() == board_id:
                self.side_notebook.select(self.recordings_tab)
            self.side_notebook.hide(self.board_tab)
        self._refresh_competitor_selector()

    def _set_attempts_sash(self) -> None:
        try:
            total = self.content_pane.winfo_width(); self.content_pane.sashpos(0, max(400, total - self.config.display.attempts_panel_width))
        except tk.TclError: pass

    def _set_timeline_sash(self) -> None:
        if not self._timeline_pane_added: return
        try:
            total = self.media_pane.winfo_height(); self.media_pane.sashpos(0, max(240, total - max(165, self.config.display.timeline_height)))
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
    def open_settings(self) -> None:
        SettingsDialog(self.root, self.config, self.apply_settings, self.open_camera_diagnostic)

    def _refresh_ui_language(self) -> None:
        """Refresh static labels after a runtime language change."""
        self.translator.set_language(self.config.general.language)
        if hasattr(self, "timeline"):
            self.timeline.set_language(self.config.general.language)
        if hasattr(self, "replay_canvas"):
            for canvas in self._all_video_canvases():
                canvas.set_language(self.config.general.language)
        self.root.title(self._t("app.title"))
        self.header_title.configure(text=self._t("app.header"))
        self.header_subtitle.configure(text=self._t("app.subtitle"))
        self._update_athlete_timer_display()
        self.file_menu_button.configure(text=self._t("menu.file"))
        self.view_menu_button.configure(text=self._t("menu.view"))
        self.help_menu_button.configure(text=self._t("menu.help"))
        self.freeze_button.configure(text=self._t("button.freeze"))
        self.system_pause_button.configure(text=self._t("button.resume_system") if self._system_paused else self._t("button.pause_system"))
        self.live_button.configure(text=self._t("button.live"))
        self.prev_frame_button.configure(text=self._t("button.previous_frame"))
        self.next_frame_button.configure(text=self._t("button.next_frame"))
        self.not_decided_button.configure(text=self._t("button.not_decided"))
        self.valid_button.configure(text=self._t("button.valid"))
        self.foul_button.configure(text=self._t("button.foul"))
        self.review_button.configure(text=self._t("button.review"))
        self.board_setup_button.configure(text=self._t("button.board_setup"))
        self.wizard_button.configure(text=self._t("button.wizard"))
        self.special_result_button.configure(text=self._t("button.more"))
        for key, label in (("group", self._t("table.group")), ("athlete", "#"), ("try", self._t("table.attempt")), ("result", self._t("table.result")), ("time", self._t("table.time")), ("media", self._t("table.media")), ("keep", self._t("table.keep"))):
            self.attempt_tree.heading(key, text=label)
        self.current_athlete_label.configure(text=self._t("competition.current"))
        self.prev_athlete_button.configure(text=self._t("competition.previous"))
        self.next_athlete_button.configure(text=self._t("competition.next"))
        self.attempts_title_label.configure(text=self._t("attempts.title"))
        self.export_button.configure(text=self._t("attempts.export"))
        self.delete_button.configure(text=self._t("attempts.delete"))
        self.clear_button.configure(text=self._t("attempts.clear"))
        try:
            self.side_notebook.tab(self.recordings_tab, text=self._t("attempts.title").title())
            self.side_notebook.tab(self.board_tab, text=self._t("board.title").title())
        except tk.TclError:
            pass
        # Recreate popup menus only on an actual language/settings change, not
        # in the video loop. The header buttons are then pointed at the new menus.
        self._build_menu()
        self.file_menu_button.configure(menu=self.file_menu)
        self.view_menu_button.configure(menu=self.view_menu)
        self.help_menu_button.configure(menu=self.help_menu)
        self._refresh_competitor_selector()
        self._refresh_attempts()

    def apply_settings(self, new_config: AppConfig) -> None:
        camera_changed = new_config.camera != self.config.camera or new_config.buffer != self.config.buffer
        language_changed = new_config.general.language != self.config.general.language
        timer_duration_changed = new_config.athlete_timer.duration_seconds != self.config.athlete_timer.duration_seconds
        self.config = new_config
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
            self.view_menu_button.configure(menu=self.view_menu)
            self.help_menu_button.configure(menu=self.help_menu)
        self._refresh_competitor_selector()
        self.root.after_idle(self._set_timeline_sash)
        self._install_hotkeys()
        self.shuttle.stop()
        self.shuttle = ShuttleHIDPoller(new_config.shuttle, self.action_queue)
        self.shuttle.start()
        save_config(new_config, self.config_path)
        if camera_changed:
            messagebox.showinfo(
                "Camera settings" if new_config.general.language == "en" else "Nastavení kamery",
                "Camera or live-buffer changes will take effect after restarting Long Jump Replay."
                if new_config.general.language == "en"
                else "Změny kamery nebo živého bufferu se projeví po restartu Long Jump Replay.",
                parent=self.root,
            )

    # ------------------------------------------------------ competition setup
    def start_competition_wizard(self) -> None:
        CompetitionWizard(self.root, self.config, self._finish_competition_wizard)

    def _finish_competition_wizard(self, new_config: AppConfig, clear_previous: bool) -> None:
        c = new_config.competition
        c.current_competitor_by_group = {"Boys": 1, "Girls": 1}
        c.finalist_numbers_by_group = {"Boys": [], "Girls": []}
        c.final_round_started_by_group = {"Boys": False, "Girls": False}
        if clear_previous:
            self._clear_recordings_mode("all", ask=False)
        self.apply_settings(new_config)
        self._last_board_signature = None
        self._refresh_competitor_selector()
        self._show_message(
            "Competition started." if self.config.general.language == "en" else "Soutěž byla spuštěna.",
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
        self.view_menu_button.configure(menu=self.view_menu)
        self.help_menu_button.configure(menu=self.help_menu)

    def _check_recovered_session(self) -> None:
        if self._recovery_checked or self._closing:
            return
        self._recovery_checked = True
        recovered = self.attempts.attempts()
        if not recovered or not self.config.competition.recovery_prompt_enabled:
            return
        keep = messagebox.askyesno(
            "Restore previous session" if self.config.general.language == "en" else "Obnovit předchozí relaci",
            (f"Found {len(recovered)} temporary recording(s) from an earlier session. Keep and restore them?"
             if self.config.general.language == "en"
             else f"Bylo nalezeno {len(recovered)} dočasných záznamů z předchozí relace. Zachovat je a obnovit?"),
            parent=self.root,
        )
        if not keep:
            self._clear_recordings_mode("all", ask=False)
        else:
            self._refresh_attempts()
            self._show_message(
                f"Restored {len(recovered)} temporary recording(s)."
                if self.config.general.language == "en"
                else f"Obnoveno {len(recovered)} dočasných záznamů.",
                6,
            )

    def export_competition_package(self) -> None:
        if not self.config.competition.event_export_enabled:
            self._show_message(
                "Competition package export is disabled in Settings."
                if self.config.general.language == "en"
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
            if self.config.general.language == "en"
            else f"Balíček soutěže exportován: {output.name}",
            8,
        )

    def open_camera_diagnostic(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Camera diagnostic" if self.config.general.language == "en" else "Diagnostika kamery")
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
        path = resolve_user_path(self.config_path, self.config.export.directory); path.mkdir(parents=True, exist_ok=True); return path
    def _evidence_directory(self) -> Path:
        path = self._exports_directory() / self.config.export.evidence_directory; path.mkdir(parents=True, exist_ok=True); return path
    def open_exports_folder(self) -> None: self._open_directory(self._exports_directory())
    def open_cache_folder(self) -> None: self._open_directory(resolve_user_path(self.config_path, self.config.attempts.cache_directory))
    def _open_directory(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        if os.name == "nt": os.startfile(path)  # type: ignore[attr-defined]
        else: self._show_message(str(path), 8)

    def show_controls(self) -> None:
        messagebox.showinfo(
            "Controls",
            "Space: Freeze / return live\nHome: Return live\nLeft / Right: one frame\n"
            "Ctrl+Page Up / Ctrl+Page Down: previous / next attempt\nV: Valid\nF: Foul\nU: Review\n"
            "P: Save frame\nE: Export attempt\nCtrl+Delete: clear temporary recordings\nC: comparison view\n\n"
            "Board calibration: drag the line centre; drag its yellow handle to rotate; Shift-drag a new board ROI; Ctrl+wheel fine-rotates the guide.\n\n"
            "ShuttleXpress: jog wheel steps frames; outer ring selects attempts; five buttons are configurable in Settings.",
        )

    def show_diagnostics(self) -> None:
        c, b = self.capture.stats(), self.buffer.stats(); devices = list_shuttle_devices(self.config.shuttle)
        shuttle = "\n".join(f"{d.product} · VID {d.vendor_id:04X} PID {d.product_id:04X}" for d in devices) or "No direct-HID Shuttle detected"
        messagebox.showinfo(
            "Diagnostics",
            f"Source: {c.source_description}\nCapture FPS: {c.capture_fps:.2f}\nBuffered FPS: {c.encode_fps:.2f}\n"
            f"JPEG time: {c.average_encode_ms:.2f} ms\nQueue drops: {c.queue_drops}\n"
            f"Live buffer: {b.duration_seconds:.2f} s / {b.frame_count} frames / {b.memory_bytes / 1024 ** 2:.1f} MB\n"
            f"Attempts: {len(self.attempts.attempts())}\nCache: {self.attempts.cache_size_bytes() / 1024 ** 2:.1f} MB\n"
            f"Shuttle status: {self.shuttle.status}\n{shuttle}\n\nLast camera error: {c.last_error or 'None'}",
        )

    def _show_message(self, text: str, seconds: float = 5.0) -> None:
        self.message_var.set(text); self._message_until = time.perf_counter() + max(0, seconds)
    def _save_config_safely(self) -> None:
        try: save_config(self.config, self.config_path)
        except OSError: pass

    # -------------------------------------------------------------- shutdown
    def close(self) -> None:
        if self._closing: return
        self._closing = True; self._cancel_scheduled_review()
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
                self.config.display.timeline_height = max(100, self.media_pane.winfo_height() - int(self.media_pane.sashpos(0)))
        except tk.TclError: pass
        self._save_config_safely(); self.mode_var.set("CLOSING"); self.message_var.set("Stopping camera and background workers…")
        for child in self.root.winfo_children():
            try: child.configure(cursor="watch")
            except (tk.TclError, AttributeError): pass
        self._shutdown_started = time.perf_counter()
        def worker() -> None:
            alive = []
            try: self.hotkeys.close()
            except Exception: pass
            try: alive.extend(self.shuttle.stop(timeout=.8))
            except Exception: pass
            try: alive.extend(self.attempts.stop(timeout=1.0))
            except Exception: pass
            try: alive.extend(self.capture.stop(timeout=2.0))
            except Exception: pass
            self.event_queue.put(("shutdown_done", alive))
        Thread(target=worker, name="shutdown-manager", daemon=True).start(); self.root.after(40, self._poll_shutdown)

    def _poll_shutdown(self) -> None:
        done = False
        while True:
            try: event, _payload = self.event_queue.get_nowait()
            except Empty: break
            if event == "shutdown_done": done = True
        if done or time.perf_counter() - self._shutdown_started > 4.0:
            try: self.root.destroy()
            except tk.TclError: pass
            return
        self.root.after(40, self._poll_shutdown)
