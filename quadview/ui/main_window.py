"""Compact controller UI; native browser operations belong to SessionWorker."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QRect, QRectF, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from ..core.config_manager import ConfigManager
from ..core.link_discovery import extract_good_links
from ..core.models import AppConfig, DEFAULT_SOURCE_URL, Monitor, Rect, SessionState, SessionUpdate
from ..core.url_validation import normalize_url
from .session_worker import SessionWorker


def make_icon() -> QIcon:
    """Draw the application mark without image files or extra dependencies."""
    icon = QIcon()
    colors = ("#6fbaff", "#459ce5", "#459ce5", "#6fbaff")
    for size in (16, 32, 48, 64, 128):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#172839"))
        painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.23, size * 0.23)
        inset, gap = size * 0.21, size * 0.08
        cell = (size - 2 * inset - gap) / 2
        for index, color in enumerate(colors):
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(
                QRectF(inset + (index % 2) * (cell + gap), inset + (index // 2) * (cell + gap), cell, cell),
                size * 0.035, size * 0.035,
            )
        painter.end()
        icon.addPixmap(pixmap)
    return icon


_STYLESHEET = """
QMainWindow, QScrollArea, QWidget#page { background: #10151c; color: #e4edf6; }
QWidget { font-family: 'Segoe UI'; font-size: 13px; color: #e4edf6; }
QScrollArea { border: none; }
QLabel { background: transparent; }
QLabel#title { font-size: 27px; font-weight: 650; letter-spacing: -0.5px; }
QLabel#subtitle, QLabel#hint, QLabel#browserStatus { color: #95a4b5; font-size: 12px; }
QLabel#sectionTitle { font-size: 14px; font-weight: 600; }
QLabel#badge { color: #afc5da; background: #202c39; border-radius: 11px; padding: 5px 11px; font-size: 11px; font-weight: 600; }
QLabel#badge[state='ACTIVE'] { background: #163b32; color: #85dfba; }
QLabel#badge[state='ERROR'] { background: #472d30; color: #ffbcc1; }
QFrame#panel { background: #18202a; border: 1px solid #2a3542; border-radius: 12px; }
QFrame#websiteCard { background: #1c2632; border: 1px solid #303c4c; border-radius: 9px; }
QLabel#number { background: #253e54; color: #86c8ff; border-radius: 6px; font-size: 12px; font-weight: 700; }
QLineEdit, QComboBox { background: #111923; border: 1px solid #354457; border-radius: 6px; padding: 9px 10px; selection-background-color: #276ca8; }
QLineEdit:focus, QComboBox:focus { border-color: #65b5ff; }
QLineEdit[invalid='true'] { border-color: #ed919d; }
QLineEdit:disabled, QComboBox:disabled { color: #7c8c9d; background: #19212b; }
QComboBox { padding-right: 24px; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: #1d2936; border: 1px solid #425267; selection-background-color: #285177; padding: 5px; }
QListWidget { background: #111923; border: 1px solid #354457; border-radius: 6px; padding: 5px; }
QListWidget::item { padding: 8px 5px; border-bottom: 1px solid #253344; }
QListWidget::item:selected { background: #253e54; }
QPushButton { background: #273445; border: 1px solid #3b4b5d; border-radius: 7px; padding: 9px 12px; font-weight: 600; }
QPushButton:hover { background: #324459; border-color: #62798f; }
QPushButton:pressed { background: #213044; }
QPushButton:disabled { background: #1d2733; color: #697c90; border-color: #2b3745; }
QPushButton#launchButton { background: #5eaff3; border-color: #6cbaff; color: #0c2032; }
QPushButton#launchButton:hover { background: #83c3f9; }
QPushButton#launchButton:disabled { background: #2d526f; border-color: #38586f; color: #9baebc; }
QPushButton#helpButton { border: none; background: transparent; color: #80c1f7; padding: 4px 0; font-weight: 500; text-align: left; }
QLabel#message { color: #b9c9d9; background: #18232e; border: 1px solid #2b3a48; border-radius: 8px; padding: 10px 12px; }
QLabel#message[error='true'] { color: #ffd0d3; background: #34242c; border-color: #65404b; }
QLabel#notice { color: #e0c8a0; background: #332c22; border: 1px solid #574a32; border-radius: 7px; padding: 8px 10px; font-size: 12px; }
QProgressBar { border: none; background: #1d2936; }
QProgressBar::chunk { background: #68b8fb; }
QToolTip { color: #e4edf6; background: #253344; border: 1px solid #506378; }
QMenu { background: #1b2734; border: 1px solid #3a4c60; padding: 5px; }
QMenu::item { padding: 7px 18px; }
QMenu::item:selected { background: #2c4b68; }
QMessageBox { background: #18202a; }
QScrollBar:vertical { background: #10151c; width: 9px; margin: 0; }
QScrollBar::handle:vertical { background: #405266; min-height: 28px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
"""


class MainWindow(QMainWindow):
    request = Signal(str, object)

    def __init__(
        self,
        config_manager: ConfigManager,
        config: AppConfig,
        *,
        worker: SessionWorker | None = None,
        start_worker: bool = True,
    ) -> None:
        super().__init__()
        self.config_manager = config_manager
        self.config = replace(config, urls=config.urls.copy())
        if not self.config.source_url:
            self.config.source_url = DEFAULT_SOURCE_URL
        # Every launch and every fetch starts with an explicit fresh selection.
        self._selected_urls: list[str] = []
        self._last_valid_source = self._safe_url(self.config.source_url)
        self._monitors: list[Monitor] = []
        self._state = SessionState.IDLE
        self._managed_count = 0
        self._running = False
        self._detected = False
        self._inflight: str | None = None
        self._exiting = False
        self._allow_close = False
        self._tray_notified = False
        self._restoring = True
        self._started_worker = start_worker
        self._worker = worker or SessionWorker()
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)

        self.setWindowTitle("QuadView")
        self.setWindowIcon(make_icon())
        self.setMinimumSize(660, 480)
        self.resize(660, 820)
        self.setStyleSheet(_STYLESHEET)
        self._build_ui()
        self._restore_geometry(config.window_geometry)
        self._restoring = False

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(650)
        self._save_timer.timeout.connect(self._save_settings)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(2500)
        self._refresh_timer.timeout.connect(self._poll_session)

        self.request.connect(self._worker.perform, Qt.ConnectionType.QueuedConnection)
        self._worker.update.connect(self._on_update)
        self._worker.completed.connect(self._on_completed)
        self._worker.finished.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._on_thread_finished)
        self._create_tray()
        app = QApplication.instance()
        if app is not None:
            app.setQuitOnLastWindowClosed(False)
        if config_manager.last_warning:
            self._notice(config_manager.last_warning)
        self._sync_controls()
        if start_worker:
            self._thread.start()
            self._refresh_timer.start()
            QTimer.singleShot(0, self._inspect)

    @staticmethod
    def _safe_url(value: str) -> str:
        try:
            return normalize_url(value)
        except ValueError:
            return ""

    def _build_ui(self) -> None:
        container = QWidget()
        container.setObjectName("page")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(17)

        header = QHBoxLayout()
        header.setSpacing(12)
        mark = QLabel()
        mark.setPixmap(make_icon().pixmap(46, 46))
        mark.setFixedSize(46, 46)
        header.addWidget(mark)
        heading = QVBoxLayout()
        heading.setSpacing(1)
        title = QLabel("QuadView")
        title.setObjectName("title")
        subtitle = QLabel("Pick your streams. Arrange your screen.")
        subtitle.setObjectName("subtitle")
        heading.addWidget(title)
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch()
        self.state_badge = QLabel("READY")
        self.state_badge.setObjectName("badge")
        header.addWidget(self.state_badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        self.notice_label = QLabel()
        self.notice_label.setObjectName("notice")
        self.notice_label.setWordWrap(True)
        self.notice_label.hide()
        layout.addWidget(self.notice_label)

        display_panel, display_layout = self._panel()
        display_header = QHBoxLayout()
        display_header.addWidget(self._section("Display"))
        display_header.addStretch()
        self.layout_label = QLabel("Select 1–4 links")
        self.layout_label.setObjectName("hint")
        display_header.addWidget(self.layout_label)
        display_layout.addLayout(display_header)
        monitor_row = QHBoxLayout()
        self.monitor_combo = QComboBox()
        self.monitor_combo.setObjectName("monitor_combo")
        self.monitor_combo.setMinimumContentsLength(18)
        self.monitor_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.monitor_combo.addItem("Checking connected monitors…", None)
        self.monitor_combo.currentIndexChanged.connect(self._schedule_save)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setToolTip("Refresh monitor and LibreWolf detection")
        self.refresh_button.clicked.connect(self._inspect)
        monitor_row.addWidget(self.monitor_combo, 1)
        monitor_row.addWidget(self.refresh_button)
        display_layout.addLayout(monitor_row)
        layout.addWidget(display_panel)

        websites_panel, websites_layout = self._panel()
        websites_layout.addWidget(self._section("Stream links"))
        source_row = QHBoxLayout()
        self.source_input = QLineEdit(self.config.source_url)
        self.source_input.setObjectName("source_input")
        self.source_input.setPlaceholderText("Page containing your stream links")
        self.source_input.setAccessibleName("Source page address")
        self.source_input.textEdited.connect(lambda _text: self._url_edited(self.source_input))
        self.source_input.returnPressed.connect(self._fetch)
        self.fetch_button = QPushButton("Fetch Links")
        self.fetch_button.clicked.connect(self._fetch)
        source_row.addWidget(self.source_input, 1)
        source_row.addWidget(self.fetch_button)
        websites_layout.addLayout(source_row)
        self.link_list = QListWidget()
        self.link_list.setObjectName("link_list")
        self.link_list.setAccessibleName("Available stream links")
        self.link_list.setMinimumHeight(170)
        self.link_list.setMaximumHeight(300)
        self.link_list.itemChanged.connect(self._link_changed)
        websites_layout.addWidget(self.link_list)
        self.selection_hint = QLabel()
        self.selection_hint.setObjectName("hint")
        self.selection_hint.setWordWrap(True)
        websites_layout.addWidget(self.selection_hint)
        self._render_selection()
        layout.addWidget(websites_panel)

        browser_panel, browser_layout = self._panel()
        browser_header = QHBoxLayout()
        browser_header.addWidget(self._section("LibreWolf"))
        browser_header.addStretch()
        self.browser_status = QLabel("Checking installation…")
        self.browser_status.setObjectName("browserStatus")
        browser_header.addWidget(self.browser_status)
        browser_layout.addLayout(browser_header)
        browser_row = QHBoxLayout()
        self.executable_input = QLineEdit(self.config.executable_path)
        self.executable_input.setObjectName("executable_input")
        self.executable_input.setPlaceholderText("Select librewolf.exe")
        self.executable_input.setAccessibleName("LibreWolf executable")
        self.executable_input.textEdited.connect(self._executable_edited)
        self.browse_button = QPushButton("Browse…")
        self.browse_button.clicked.connect(self._browse_executable)
        browser_row.addWidget(self.executable_input, 1)
        browser_row.addWidget(self.browse_button)
        browser_layout.addLayout(browser_row)
        help_button = QPushButton("Fullscreen setup")
        help_button.setObjectName("helpButton")
        help_button.clicked.connect(self._show_fullscreen_help)
        browser_layout.addWidget(help_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(browser_panel)
        layout.addStretch(1)
        scroll.setWidget(page)
        container_layout.addWidget(scroll, 1)

        # Session actions and their outcome remain reachable on short screens.
        footer = QWidget()
        footer.setObjectName("page")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(24, 0, 24, 20)
        footer_layout.setSpacing(12)

        buttons = QHBoxLayout()
        buttons.setSpacing(9)
        self.launch_button = QPushButton("Launch QuadView")
        self.launch_button.setObjectName("launchButton")
        self.launch_button.clicked.connect(self._launch)
        self.reapply_button = QPushButton("Reapply Layout")
        self.reapply_button.setObjectName("reapply_button")
        self.reapply_button.clicked.connect(self._reapply)
        self.close_session_button = QPushButton("Close QuadView Session")
        self.close_session_button.setObjectName("close_session_button")
        self.close_session_button.clicked.connect(lambda: self._send("close"))
        self.close_session_button.setToolTip("Ask only the managed LibreWolf windows to close normally")
        buttons.addWidget(self.launch_button, 1)
        buttons.addWidget(self.reapply_button)
        buttons.addWidget(self.close_session_button)
        footer_layout.addLayout(buttons)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.hide()
        footer_layout.addWidget(self.progress)
        self.message_label = QLabel("Fetch links from a page, select up to four, then launch.")
        self.message_label.setObjectName("message")
        self.message_label.setWordWrap(True)
        self.message_label.setMinimumHeight(52)
        self.message_label.setTextFormat(Qt.TextFormat.PlainText)
        self.message_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        footer_layout.addWidget(self.message_label)
        container_layout.addWidget(footer)
        self.setCentralWidget(container)

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    @staticmethod
    def _panel() -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 14, 15, 14)
        layout.setSpacing(11)
        return frame, layout

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _notice(self, text: str) -> None:
        self.notice_label.setText(text)
        self.notice_label.setVisible(bool(text))

    def _message(self, text: str, *, error: bool = False) -> None:
        self.message_label.setText(text)
        self.message_label.setProperty("error", error)
        self._repolish(self.message_label)

    def _url_edited(self, field: QLineEdit) -> None:
        field.setProperty("invalid", False)
        field.setToolTip("")
        self._repolish(field)
        self._schedule_save()

    def _validate_field(self, field: QLineEdit) -> bool:
        try:
            normalize_url(field.text())
        except ValueError as exc:
            field.setProperty("invalid", bool(field.text()))
            field.setToolTip(str(exc))
            self._repolish(field)
            return False
        field.setProperty("invalid", False)
        field.setToolTip("")
        self._repolish(field)
        return True

    def _set_available_links(self, links: dict[str, str]) -> None:
        available: list[tuple[str, str]] = []
        # All picker entries use the user's exact filter and naming rule,
        # including callers other than the normal fetch worker.
        for name, url in extract_good_links(list(links.values())).items():
            try:
                validated = normalize_url(url)
            except ValueError:
                continue
            available.append((name, validated))
        self._selected_urls = []
        self.link_list.blockSignals(True)
        self.link_list.clear()
        for name, url in available:
            item = QListWidgetItem(name or "(unnamed link)")
            item.setData(Qt.ItemDataRole.UserRole, url)
            item.setData(Qt.ItemDataRole.UserRole + 1, name)
            item.setToolTip(url)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if url in self._selected_urls else Qt.CheckState.Unchecked)
            self.link_list.addItem(item)
        self.link_list.blockSignals(False)
        self._render_selection()

    def _link_changed(self, item: QListWidgetItem) -> None:
        url = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked and url not in self._selected_urls:
            if len(self._selected_urls) == 4:
                self.link_list.blockSignals(True)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.link_list.blockSignals(False)
                self._message("Choose up to four links. Uncheck one before selecting another.", error=True)
                return
            self._selected_urls.append(url)
        elif item.checkState() != Qt.CheckState.Checked and url in self._selected_urls:
            self._selected_urls.remove(url)
        self._render_selection()
        self._sync_controls()
        self._schedule_save()

    def _render_selection(self) -> None:
        self.link_list.blockSignals(True)
        for index in range(self.link_list.count()):
            item = self.link_list.item(index)
            url = item.data(Qt.ItemDataRole.UserRole)
            name = item.data(Qt.ItemDataRole.UserRole + 1) or "(unnamed link)"
            prefix = f"{self._selected_urls.index(url) + 1} · " if url in self._selected_urls else ""
            item.setText(prefix + name)
        self.link_list.blockSignals(False)
        count = len(self._selected_urls)
        layouts = ("Select 1–4 links", "Full screen", "Side by side", "Priority left + two right", "2 × 2 quadrants")
        self.layout_label.setText(layouts[count])
        self.selection_hint.setText(
            f"{count} of 4 selected · Pick order sets window order. "
            "For three streams, selection 1 gets the left half."
        )

    def _fetch(self) -> None:
        if self._inflight is not None or self._managed_count:
            return
        if not self._validate_field(self.source_input):
            self._message(self.source_input.toolTip(), error=True)
            self.source_input.setFocus()
            return
        source = normalize_url(self.source_input.text())
        self.source_input.setText(source)
        self._selected_urls = []
        self.link_list.blockSignals(True)
        for index in range(self.link_list.count()):
            self.link_list.item(index).setCheckState(Qt.CheckState.Unchecked)
        self.link_list.blockSignals(False)
        self._render_selection()
        self._save_settings()
        if self._send("fetch", source):
            self._message("Fetching visible stream links… The temporary browser will close when finished.")

    def _executable_edited(self, _text: str) -> None:
        self._detected = False
        self.browser_status.setText("Path will be checked at launch")
        self._schedule_save()
        self._sync_controls()

    def _browse_executable(self) -> None:
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self, "Select LibreWolf", self.executable_input.text(), "LibreWolf (librewolf.exe)"
        )
        if filename:
            self.executable_input.setText(filename)
            self._executable_edited(filename)
            self._inspect()

    def _collect_config(self) -> AppConfig:
        urls = [normalize_url(url) for url in self._selected_urls]
        text = self.source_input.text()
        try:
            source = normalize_url(text) if text else ""
        except ValueError:
            source = self._last_valid_source
        else:
            self._last_valid_source = source
        monitor = self.monitor_combo.currentData()
        geometry = self.normalGeometry() if self.isMaximized() else self.geometry()
        return AppConfig(
            urls=urls,
            source_url=source,
            executable_path=self.executable_input.text().strip(),
            monitor_id=monitor.identifier if isinstance(monitor, Monitor) else self.config.monitor_id,
            monitor_bounds=monitor.bounds if isinstance(monitor, Monitor) else self.config.monitor_bounds,
            window_geometry=Rect(geometry.x(), geometry.y(), geometry.x() + geometry.width(), geometry.y() + geometry.height()),
        )

    def _schedule_save(self, *_args: object) -> None:
        if not self._restoring and not self._exiting and hasattr(self, "_save_timer"):
            self._save_timer.start()

    @Slot()
    def _save_settings(self) -> None:
        try:
            candidate = self._collect_config()
            self.config_manager.save(candidate)
        except (OSError, ValueError):
            self._notice("Settings could not be saved. Your current session can still be used.")
        else:
            self.config = candidate

    def _restore_geometry(self, saved: Rect | None) -> None:
        screens = QApplication.screens()
        if not screens:
            return
        requested = QRect(saved.left, saved.top, saved.width, saved.height) if saved else QRect(0, 0, 660, 820)
        areas = [screen.availableGeometry() for screen in screens]
        area = max(areas, key=lambda item: item.intersected(requested).width() * item.intersected(requested).height())
        if not any(item.intersects(requested) for item in areas):
            primary = QApplication.primaryScreen()
            area = primary.availableGeometry() if primary is not None else areas[0]
        # Small displays still need a reachable controller; vertical scrolling
        # keeps the form usable when its preferred height does not fit.
        self.setMinimumSize(min(self.minimumWidth(), area.width()), min(self.minimumHeight(), area.height()))
        width = min(max(requested.width(), self.minimumWidth()), area.width())
        height = min(max(requested.height(), self.minimumHeight()), area.height())
        if saved:
            left = max(area.left(), min(requested.left(), area.right() - width + 1))
            top = max(area.top(), min(requested.top(), area.bottom() - height + 1))
        else:
            left = area.left() + (area.width() - width) // 2
            top = area.top() + (area.height() - height) // 2
        self.setGeometry(left, top, width, height)

    def moveEvent(self, event: object) -> None:
        super().moveEvent(event)
        self._schedule_save()

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        self._schedule_save()

    def _send(self, command: str, payload: object = None) -> bool:
        if self._exiting or self._inflight is not None or not self._started_worker:
            return False
        self._inflight = command
        self._sync_controls()
        self.request.emit(command, payload)
        return True

    def _inspect(self) -> None:
        self._send("inspect", self._collect_config())

    def _poll_session(self) -> None:
        self._send("refresh")

    def _launch(self) -> None:
        if not 1 <= len(self._selected_urls) <= 4:
            self._message("Select between one and four links before launching.", error=True)
            return
        if not self.executable_input.text().strip():
            self._message("Select the librewolf.exe in your existing installation.", error=True)
            return
        if not isinstance(self.monitor_combo.currentData(), Monitor):
            self._message("Select a connected monitor before launching.", error=True)
            return
        config = self._collect_config()
        self._save_settings()
        self._send("launch", config)

    def _reapply(self) -> None:
        monitor = self.monitor_combo.currentData()
        if not isinstance(monitor, Monitor):
            self._message("Select a connected monitor before reapplying the layout.", error=True)
            return
        self._save_settings()
        self._send("reapply", monitor.identifier)

    @Slot(object)
    def _on_update(self, update: SessionUpdate) -> None:
        self._state = update.state
        self._managed_count = update.managed_count
        if not self._exiting:
            self._message(update.message, error=update.state == SessionState.ERROR)
        self._sync_controls()

    @Slot(str, object, str)
    def _on_completed(self, command: str, result: object, error: str) -> None:
        self._inflight = None
        if command == "shutdown":
            if error:
                self._exiting = False
                self.showNormal()
                self._message("QuadView could not finish shutting down. Please try Exit again.", error=True)
                self._refresh_timer.start()
            self._sync_controls()
            return
        if self._exiting:
            return
        if error:
            self._message(error, error=True)
            if command == "inspect":
                self.browser_status.setText("Detection unavailable")
        elif isinstance(result, dict):
            if command in {"inspect", "refresh"}:
                self._running = bool(result.get("running", self._running))
            if command == "inspect":
                self._apply_inspection(result)
            elif command == "refresh":
                self._managed_count = int(result.get("managed_count", self._managed_count))
                self._state = result.get("state", self._state)
            elif command == "fetch":
                self._set_available_links(result)
                count = self.link_list.count()
                self._message(f"Found {count} stream links. Select up to four to launch." if count else "No visible HTTP/HTTPS links with '/stream/' in their path were found on this page.")
                self._schedule_save()
        self._sync_controls()

    def _apply_inspection(self, result: dict[str, object]) -> None:
        detected = str(result.get("executable", ""))
        requested = str(result.get("requested_executable", ""))
        if self.executable_input.text().strip() == requested:
            self.executable_input.setText(detected or requested)
            self._detected = bool(detected)
        old_monitor = self.monitor_combo.currentData()
        wanted_id = old_monitor.identifier if isinstance(old_monitor, Monitor) else self.config.monitor_id
        wanted_bounds = old_monitor.bounds if isinstance(old_monitor, Monitor) else self.config.monitor_bounds
        self._monitors = [item for item in result.get("monitors", []) if isinstance(item, Monitor)]
        selected = next((item for item in self._monitors if item.identifier == wanted_id), None)
        fallback = selected is None and bool(wanted_id)
        if selected is None:
            selected = next((item for item in self._monitors if item.bounds == wanted_bounds), None)
        if selected is None:
            selected = next((item for item in self._monitors if item.is_primary), None)
        if selected is None and self._monitors:
            selected = self._monitors[0]
        self.monitor_combo.blockSignals(True)
        self.monitor_combo.clear()
        for monitor in self._monitors:
            self.monitor_combo.addItem(monitor.label, monitor)
        if selected is not None:
            self.monitor_combo.setCurrentIndex(self._monitors.index(selected))
        else:
            self.monitor_combo.addItem("No connected monitor found", None)
        self.monitor_combo.blockSignals(False)
        if fallback and selected is not None:
            self._notice("The saved display is unavailable. A matching or primary display was selected; check it before launching or reapplying.")
        elif requested and detected and detected.casefold() != requested.casefold():
            self._notice("The saved browser path was unavailable. LibreWolf was detected at another location.")
        if not detected:
            self._message("LibreWolf was not detected. Use Browse to select your existing installation.", error=True)
        elif self._state == SessionState.IDLE and self._managed_count == 0:
            text = "LibreWolf is running. Close every LibreWolf window before launching." if self._running else "Ready. Fetch a page's links, select up to four, then launch."
            self._message(text)
        self._schedule_save()

    def _sync_controls(self) -> None:
        busy = self._inflight is not None or self._exiting
        managed = self._managed_count > 0
        has_monitor = isinstance(self.monitor_combo.currentData(), Monitor)
        self.launch_button.setEnabled(not busy and not managed and has_monitor and bool(self._selected_urls))
        self.reapply_button.setEnabled(not busy and managed and has_monitor)
        self.close_session_button.setEnabled(not busy and managed)
        self.refresh_button.setEnabled(not busy)
        self.browse_button.setEnabled(not busy and not managed)
        self.executable_input.setEnabled(not busy and not managed)
        self.monitor_combo.setEnabled(not busy)
        self.source_input.setEnabled(not busy and not managed)
        self.fetch_button.setEnabled(not busy and not managed)
        self.link_list.setEnabled(not busy and not managed)
        self.progress.setVisible(busy and self._inflight != "refresh")
        badge = "EXITING" if self._exiting else self._state.value
        if self._state == SessionState.IDLE and not self._exiting:
            badge = "READY"
        self.state_badge.setText(badge)
        self.state_badge.setProperty("state", self._state.value)
        self._repolish(self.state_badge)
        if managed:
            self.browser_status.setText(f"{self._managed_count} managed windows")
        elif self._running:
            self.browser_status.setText("Already running")
        elif self._detected:
            self.browser_status.setText("Installation detected")
        elif self.executable_input.text():
            self.browser_status.setText("Path will be checked at launch")
        elif self._inflight != "inspect":
            self.browser_status.setText("Not detected")

    def _show_fullscreen_help(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Fullscreen within each window")
        box.setIcon(QMessageBox.Icon.Information)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText("Enable the setting in LibreWolf yourself")
        box.setInformativeText(
            "1. Open LibreWolf and enter about:config.\n"
            "2. Accept the notice if it appears.\n"
            "3. Search for full-screen-api.ignore-widgets.\n"
            "4. Record its current value; toggle the existing Boolean to true.\n"
            "5. Close all LibreWolf windows, then launch QuadView.\n\n"
            "If the preference is missing or locked, stop and check your browser version. "
            "QuadView never edits your browser profile. The setting affects the profile, "
            "including other browser windows. Restore the recorded value to undo it.\n\n"
            "Use each video's fullscreen button. Check YouTube and another HTML5 player, "
            "including switching among all four windows. Manual use was reported working; "
            "compatibility still depends on your browser and the player."
        )
        box.exec()

    def _create_tray(self) -> None:
        self._tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(self.windowIcon(), self)
        tray.setToolTip("QuadView")
        menu = QMenu(self)
        show_action = QAction("Show QuadView", menu)
        show_action.triggered.connect(self._show_from_tray)
        menu.addAction(show_action)
        menu.addSeparator()
        exit_action = QAction("Exit QuadView — leave browsers open", menu)
        exit_action.triggered.connect(self._begin_exit)
        menu.addAction(exit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        tray.show()
        self._tray = tray

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show_from_tray()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._allow_close:
            event.accept()
            return
        event.ignore()
        if self._exiting:
            return
        active = self._managed_count > 0 or self._inflight in {"launch", "reapply", "close"}
        if active and self._tray is not None:
            self._save_settings()
            self.hide()
            if not self._tray_notified:
                self._tray.showMessage("QuadView is in the tray", "Your browser windows stay open. Use the tray menu to show or exit QuadView.")
                self._tray_notified = True
            return
        if active:
            box = QMessageBox(self)
            box.setWindowTitle("Leave browser windows open?")
            box.setText("Exiting QuadView leaves the browser windows open and ends layout management.")
            leave = box.addButton("Leave browsers open and exit", QMessageBox.ButtonRole.AcceptRole)
            cancel = box.addButton(QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(cancel)
            box.exec()
            if box.clickedButton() is not leave:
                return
        self._begin_exit()

    @Slot()
    def _begin_exit(self) -> None:
        if self._exiting:
            return
        self._save_timer.stop()
        self._refresh_timer.stop()
        self._save_settings()
        self._exiting = True
        self._message("Exiting QuadView. Browser windows will stay open.")
        self._sync_controls()
        if self._thread.isRunning():
            self._worker.cancel()
            # This queued call runs after any current native operation returns.
            self.request.emit("shutdown", None)
        else:
            self._on_thread_finished()

    @Slot()
    def _on_thread_finished(self) -> None:
        if not self._exiting:
            return
        self._allow_close = True
        if self._tray is not None:
            self._tray.hide()
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()
