"""PySide6 desktop interface for the task calendar."""

from __future__ import annotations

import argparse
import calendar
import sys
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Sequence

from .config import database_url_from_env
from .models import Task
from .storage import TaskRepository

APP_TITLE = "Календарь задач"
MONTH_NAMES = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}
WEEKDAY_NAMES = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


@dataclass
class TaskTimerState:
    """Runtime timer state bound to one task."""

    seconds_left: int
    total_seconds: int
    is_running: bool = False


class MissingPySideError(RuntimeError):
    """Raised when PySide6 is not installed in the current environment."""


def _load_qt() -> tuple[object, object, object]:
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError as error:
        raise MissingPySideError(
            "PySide6 не установлен. Выполните `python -m pip install -r requirements.txt`."
        ) from error
    return QtCore, QtGui, QtWidgets


def _create_timer_ring_class(QtCore: object, QtGui: object, QtWidgets: object) -> type:
    class TimerRing(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.progress = 0.0
            self.text = "00:00"
            self.setMinimumSize(124, 124)

        def set_timer(self, seconds_left: int, total_seconds: int) -> None:
            self.text = _format_seconds(seconds_left)
            if total_seconds <= 0:
                self.progress = 0.0
            else:
                self.progress = max(0.0, min(1.0, seconds_left / total_seconds))
            self.update()

        def paintEvent(self, event: object) -> None:
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

            side = min(self.width(), self.height()) - 18
            rect = QtCore.QRectF(
                (self.width() - side) / 2,
                (self.height() - side) / 2,
                side,
                side,
            )

            base_pen = QtGui.QPen(QtGui.QColor("#e2e8f0"), 12)
            base_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            painter.setPen(base_pen)
            painter.drawArc(rect, 0, 360 * 16)

            progress_pen = QtGui.QPen(QtGui.QColor("#2563eb"), 12)
            progress_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            painter.setPen(progress_pen)
            painter.drawArc(rect, 90 * 16, int(-360 * 16 * self.progress))

            painter.setPen(QtGui.QColor("#0f172a"))
            font = painter.font()
            font.setPointSize(19)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, self.text)

    return TimerRing


def _create_main_window_class(QtWidgets: object) -> type:
    class ResizableMainWindow(QtWidgets.QMainWindow):
        def __init__(self, on_resize: object) -> None:
            super().__init__()
            self.on_resize = on_resize

        def resizeEvent(self, event: object) -> None:
            super().resizeEvent(event)
            self.on_resize()

    return ResizableMainWindow


def _create_schedule_board_class(QtCore: object, QtGui: object, QtWidgets: object) -> type:
    class ScheduleBoard(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.start_date = date.today()
            self.visible_days = 7
            self.setObjectName("dayScheduleBoard")
            self.setMinimumWidth(_schedule_board_width(self.visible_days))
            self.setMinimumHeight(_day_board_height())

        def set_start_date(self, value: date, visible_days: int) -> None:
            self.start_date = value
            self.visible_days = visible_days
            self.update()

        def paintEvent(self, event: object) -> None:
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            painter.fillRect(self.rect(), QtGui.QColor("#ffffff"))

            day_width = _day_column_width(self.visible_days)
            grid_width = day_width * self.visible_days
            header_rect = QtCore.QRectF(
                _time_column_width(),
                0,
                grid_width,
                _day_header_height(),
            )
            painter.fillRect(header_rect, QtGui.QColor("#f8fafc"))

            grid_pen = QtGui.QPen(QtGui.QColor("#e2e8f0"), 1)
            text_pen = QtGui.QPen(QtGui.QColor("#64748b"))
            strong_pen = QtGui.QPen(QtGui.QColor("#0f172a"))

            for day_index in range(self.visible_days):
                current_date = self.start_date + timedelta(days=day_index)
                x = _time_column_width() + day_index * day_width
                day_rect = QtCore.QRectF(x, 0, day_width, _day_header_height())
                painter.setPen(strong_pen)
                font = painter.font()
                font.setPointSize(10)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(
                    day_rect,
                    QtCore.Qt.AlignmentFlag.AlignCenter,
                    f"{WEEKDAY_NAMES[current_date.weekday()]}\n{current_date:%d.%m}",
                )
                painter.setPen(grid_pen)
                painter.drawLine(
                    x,
                    0,
                    x,
                    _day_header_height() + _hour_height() * 24,
                )

            painter.setPen(grid_pen)
            painter.drawLine(
                _time_column_width() + grid_width,
                0,
                _time_column_width() + grid_width,
                _day_header_height() + _hour_height() * 24,
            )

            font = painter.font()
            font.setPointSize(9)
            font.setBold(False)
            painter.setFont(font)
            for hour in range(24):
                y = _day_header_height() + hour * _hour_height()
                painter.setPen(text_pen)
                painter.drawText(
                    QtCore.QRectF(0, y - 10, _time_column_width() - 10, 20),
                    QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter,
                    f"{hour:02d}:00",
                )
                painter.setPen(grid_pen)
                painter.drawLine(
                    _time_column_width(),
                    y,
                    _time_column_width() + grid_width,
                    y,
                )

    return ScheduleBoard


class MainWindow:
    """Main PySide6 window for task planning."""

    def __init__(self, repository: TaskRepository) -> None:
        self.QtCore, self.QtGui, self.QtWidgets = _load_qt()
        self.repository = repository
        self.selected_date = date.today()
        self.selected_task_id: int | None = None
        self.selected_task_title: str | None = None
        self.visible_year = self.selected_date.year
        self.visible_month = self.selected_date.month
        self.month_calendar = calendar.Calendar(firstweekday=0)
        self.schedule_mode = "week"
        self.effective_visible_days = 7

        self.task_timers: dict[int, TaskTimerState] = {}
        self.task_by_id: dict[int, Task] = {}
        self._ui_ready = False

        ResizableMainWindow = _create_main_window_class(self.QtWidgets)
        self.window = ResizableMainWindow(self._handle_window_resize)
        self.calendar_grid = self.QtWidgets.QGridLayout()
        ScheduleBoard = _create_schedule_board_class(self.QtCore, self.QtGui, self.QtWidgets)
        self.day_schedule_board = ScheduleBoard()
        self.day_header_label = self.QtWidgets.QLabel()
        self.selected_task_label = self.QtWidgets.QLabel("Задача не выбрана")
        self.day_mode_button = self.QtWidgets.QPushButton("День")
        self.week_mode_button = self.QtWidgets.QPushButton("Неделя")
        self.task_list = self.QtWidgets.QListWidget()
        self.title_input = self.QtWidgets.QLineEdit()
        self.description_input = self.QtWidgets.QPlainTextEdit()
        self.start_time_input = self.QtWidgets.QTimeEdit()
        self.end_time_input = self.QtWidgets.QTimeEdit()
        self.month_title = self.QtWidgets.QLabel()
        self.selected_date_sidebar_label = self.QtWidgets.QLabel()
        self.selected_date_form_label = self.QtWidgets.QLabel()
        self.counter_label = self.QtWidgets.QLabel()
        self.timer_label = self.QtWidgets.QLabel("00:00")
        self.timer_task_label = self.QtWidgets.QLabel("Выберите задачу")
        TimerRing = _create_timer_ring_class(self.QtCore, self.QtGui, self.QtWidgets)
        self.timer_ring = TimerRing()
        self.timer_minutes_input = self.QtWidgets.QSpinBox()
        self.timer = self.QtCore.QTimer()
        self.timer.timeout.connect(self._tick_timer)

        self._build_window()
        self.refresh()

    def show(self) -> None:
        self.window.show()

    def refresh(self) -> None:
        """Reload all tasks and redraw the screen."""
        tasks = self.repository.list_tasks(include_completed=True)
        self.task_by_id = {task.id: task for task in tasks}
        active_count = sum(not task.is_completed for task in tasks)
        completed_count = len(tasks) - active_count

        selected_date_text = f"Дата для новой задачи: {self.selected_date.strftime('%d.%m.%Y')}"
        self.selected_date_sidebar_label.setText(selected_date_text)
        self.selected_date_form_label.setText(selected_date_text)
        self.month_title.setText(_format_month_title(self.visible_year, self.visible_month))
        self.counter_label.setText(
            f"Активных: {active_count}   Выполнено: {completed_count}"
        )

        self._refresh_calendar()
        self._render_schedule_mode_controls()
        visible_days = self._visible_day_count()
        schedule_end_date = self.selected_date + timedelta(days=visible_days - 1)
        schedule_tasks = [
            task
            for task in tasks
            if task.due_date is not None
            and self.selected_date <= task.due_date <= schedule_end_date
        ]
        self._refresh_day_schedule(schedule_tasks)

    def _visible_day_count(self) -> int:
        if self.schedule_mode == "day":
            return 1
        return 1 if self.window.width() < 1120 else 7

    def _set_schedule_mode(self, mode: str) -> None:
        self.schedule_mode = mode
        self.effective_visible_days = self._visible_day_count()
        self.refresh()

    def _handle_window_resize(self) -> None:
        if not getattr(self, "_ui_ready", False):
            return
        visible_days = self._visible_day_count()
        if visible_days == self.effective_visible_days:
            return
        self.effective_visible_days = visible_days
        self.refresh()

    def _render_schedule_mode_controls(self) -> None:
        self.day_mode_button.setObjectName(
            "primaryButton" if self.schedule_mode == "day" else ""
        )
        self.week_mode_button.setObjectName(
            "primaryButton" if self.schedule_mode == "week" else ""
        )
        for button in (self.day_mode_button, self.week_mode_button):
            button.style().unpolish(button)
            button.style().polish(button)

    def _build_window(self) -> None:
        self.window.setWindowTitle(APP_TITLE)
        self.window.resize(1420, 820)
        self.window.setMinimumSize(900, 620)

        central = self.QtWidgets.QWidget()
        central.setObjectName("appRoot")
        root_layout = self.QtWidgets.QHBoxLayout(central)
        root_layout.setContentsMargins(22, 22, 22, 22)
        root_layout.setSpacing(18)

        sidebar = self._build_sidebar()
        sidebar.setMinimumWidth(330)
        sidebar.setMaximumWidth(410)
        root_layout.addWidget(sidebar)
        root_layout.addWidget(self._build_content(), 1)

        self.window.setCentralWidget(central)
        self.window.setStyleSheet(APP_STYLES)
        self._ui_ready = True

    def _build_sidebar(self) -> object:
        scroll_area = self.QtWidgets.QScrollArea()
        scroll_area.setObjectName("sidebarScroll")
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(self.QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        panel = self.QtWidgets.QFrame()
        panel.setObjectName("panel")
        layout = self.QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        title = self.QtWidgets.QLabel(APP_TITLE)
        title.setObjectName("appTitle")
        subtitle = self.QtWidgets.QLabel("Выберите дату для новой задачи")
        subtitle.setObjectName("mutedText")
        subtitle.setWordWrap(True)

        calendar_header = self.QtWidgets.QHBoxLayout()
        previous_month_button = self.QtWidgets.QPushButton("←")
        previous_month_button.setFixedWidth(44)
        previous_month_button.clicked.connect(lambda: self._shift_month(-1))
        next_month_button = self.QtWidgets.QPushButton("→")
        next_month_button.setFixedWidth(44)
        next_month_button.clicked.connect(lambda: self._shift_month(1))
        self.month_title.setObjectName("sidebarMonthTitle")
        calendar_header.addWidget(previous_month_button)
        calendar_header.addWidget(self.month_title, 1)
        calendar_header.addWidget(next_month_button)

        calendar_frame = self.QtWidgets.QFrame()
        calendar_frame.setObjectName("calendarPanel")
        self.calendar_grid = self.QtWidgets.QGridLayout(calendar_frame)
        self.calendar_grid.setContentsMargins(10, 10, 10, 10)
        self.calendar_grid.setSpacing(6)

        today_button = self.QtWidgets.QPushButton("Сегодня")
        today_button.setObjectName("primaryButton")
        today_button.clicked.connect(self._select_today)

        self.selected_date_sidebar_label.setObjectName("mutedText")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)
        layout.addLayout(calendar_header)
        layout.addWidget(calendar_frame)
        layout.addWidget(self.selected_date_sidebar_label)
        layout.addWidget(today_button)
        layout.addWidget(self._build_form())
        layout.addStretch()
        scroll_area.setWidget(panel)
        return scroll_area

    def _build_content(self) -> object:
        panel = self.QtWidgets.QFrame()
        panel.setObjectName("panel")
        layout = self.QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        title_block = self.QtWidgets.QVBoxLayout()
        section_title = self.QtWidgets.QLabel("Расписание")
        section_title.setObjectName("sectionTitle")
        self.day_header_label.setObjectName("dateTitle")
        list_note = self.QtWidgets.QLabel(
            "Перетаскивайте блок задачи вверх или вниз, чтобы изменить время."
        )
        list_note.setObjectName("mutedText")
        list_note.setWordWrap(True)
        self.counter_label.setObjectName("mutedText")
        self.selected_task_label.setObjectName("mutedText")
        title_block.addWidget(section_title)
        title_block.addWidget(self.day_header_label)
        title_block.addWidget(list_note)
        title_block.addWidget(self.counter_label)
        title_block.addWidget(self.selected_task_label)

        mode_layout = self.QtWidgets.QHBoxLayout()
        mode_layout.setSpacing(8)
        self.day_mode_button.clicked.connect(lambda: self._set_schedule_mode("day"))
        self.week_mode_button.clicked.connect(lambda: self._set_schedule_mode("week"))
        mode_layout.addWidget(self.day_mode_button)
        mode_layout.addWidget(self.week_mode_button)
        title_block.addLayout(mode_layout)

        header_layout = self.QtWidgets.QHBoxLayout()
        header_layout.setSpacing(16)
        header_layout.addLayout(title_block, 1)
        header_layout.addWidget(self._build_timer_panel())

        self.day_schedule_board.setObjectName("dayScheduleBoard")
        self.day_schedule_board.setFixedSize(
            _schedule_board_width(self._visible_day_count()),
            _day_board_height(),
        )
        schedule_scroll = self.QtWidgets.QScrollArea()
        schedule_scroll.setWidgetResizable(False)
        schedule_scroll.setObjectName("scheduleScroll")
        schedule_scroll.setWidget(self.day_schedule_board)

        layout.addLayout(header_layout)
        layout.addWidget(schedule_scroll, 1)
        return panel

    def _build_timer_panel(self) -> object:
        panel = self.QtWidgets.QFrame()
        panel.setObjectName("timerPanel")
        panel.setMinimumWidth(390)
        panel.setMaximumHeight(172)
        layout = self.QtWidgets.QHBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)

        title = self.QtWidgets.QLabel("Таймер задачи")
        title.setObjectName("formTitle")
        self.timer_task_label.setObjectName("mutedText")
        self.timer_label.setObjectName("timerLabel")
        self.timer_task_label.setWordWrap(True)

        self.timer_minutes_input.setRange(1, 240)
        self.timer_minutes_input.setValue(25)
        self.timer_minutes_input.setSuffix(" мин")
        self.timer_minutes_input.setButtonSymbols(
            self.QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons
        )

        start_button = self.QtWidgets.QPushButton("Старт")
        start_button.setObjectName("primaryButton")
        start_button.clicked.connect(self._start_timer)
        pause_button = self.QtWidgets.QPushButton("Пауза")
        pause_button.clicked.connect(self._pause_timer)
        reset_button = self.QtWidgets.QPushButton("Сброс")
        reset_button.clicked.connect(self._reset_timer)

        controls = self.QtWidgets.QGridLayout()
        controls.setSpacing(8)
        controls.addWidget(self.timer_minutes_input, 0, 0, 1, 3)
        controls.addWidget(start_button, 1, 0)
        controls.addWidget(pause_button, 1, 1)
        controls.addWidget(reset_button, 1, 2)

        info_layout = self.QtWidgets.QVBoxLayout()
        info_layout.setSpacing(8)
        info_layout.addWidget(title)
        info_layout.addWidget(self.timer_task_label)
        info_layout.addLayout(controls)

        layout.addWidget(self.timer_ring, alignment=self.QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(info_layout, 1)
        return panel

    def _build_form(self) -> object:
        form = self.QtWidgets.QFrame()
        form.setObjectName("formPanel")
        layout = self.QtWidgets.QVBoxLayout(form)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        form_title = self.QtWidgets.QLabel("Задача")
        form_title.setObjectName("formTitle")

        self.title_input.setPlaceholderText("Название задачи")
        self.description_input.setPlaceholderText("Описание или заметка")
        self.description_input.setFixedHeight(58)
        self.start_time_input.setDisplayFormat("HH:mm")
        self.start_time_input.setTime(self.QtCore.QTime(9, 0))
        self.start_time_input.setButtonSymbols(
            self.QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        self.end_time_input.setDisplayFormat("HH:mm")
        self.end_time_input.setTime(self.QtCore.QTime(10, 0))
        self.end_time_input.setButtonSymbols(
            self.QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons
        )

        time_layout = self.QtWidgets.QHBoxLayout()
        start_label = self.QtWidgets.QLabel("Начало")
        start_label.setObjectName("mutedText")
        end_label = self.QtWidgets.QLabel("Окончание")
        end_label.setObjectName("mutedText")
        time_layout.addWidget(start_label)
        time_layout.addWidget(self.start_time_input)
        time_layout.addWidget(end_label)
        time_layout.addWidget(self.end_time_input)

        add_button = self.QtWidgets.QPushButton("Добавить задачу")
        add_button.setObjectName("primaryButton")
        add_button.clicked.connect(self._add_task)
        update_button = self.QtWidgets.QPushButton("Сохранить изменения")
        update_button.clicked.connect(self._update_selected_task)
        clear_button = self.QtWidgets.QPushButton("Очистить")
        clear_button.clicked.connect(self._clear_task_form)
        complete_button = self.QtWidgets.QPushButton("Выполнить")
        complete_button.clicked.connect(self._complete_selected_task)
        delete_button = self.QtWidgets.QPushButton("Удалить")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self._delete_selected_task)

        edit_actions = self.QtWidgets.QGridLayout()
        edit_actions.setSpacing(8)
        edit_actions.addWidget(add_button, 0, 0, 1, 2)
        edit_actions.addWidget(update_button, 1, 0, 1, 2)
        edit_actions.addWidget(complete_button, 2, 0)
        edit_actions.addWidget(delete_button, 2, 1)
        edit_actions.addWidget(clear_button, 3, 0, 1, 2)

        self.selected_date_form_label.setObjectName("mutedText")

        layout.addWidget(form_title)
        layout.addWidget(self.selected_date_form_label)
        layout.addWidget(self.title_input)
        layout.addLayout(time_layout)
        layout.addWidget(self.description_input)
        layout.addLayout(edit_actions)
        return form

    def _refresh_calendar(self) -> None:
        _clear_layout(self.calendar_grid)

        for column, weekday in enumerate(WEEKDAY_NAMES):
            label = self.QtWidgets.QLabel(weekday)
            label.setObjectName("weekdayLabel")
            label.setAlignment(self.QtCore.Qt.AlignmentFlag.AlignCenter)
            self.calendar_grid.addWidget(label, 0, column)

        weeks = self.month_calendar.monthdatescalendar(self.visible_year, self.visible_month)
        counts = self.repository.count_tasks_by_date(weeks[0][0], weeks[-1][-1])
        today = date.today()
        for row_index, week in enumerate(weeks, start=1):
            for column_index, current_day in enumerate(week):
                if current_day.month != self.visible_month:
                    spacer = self.QtWidgets.QLabel("")
                    self.calendar_grid.addWidget(spacer, row_index, column_index)
                    continue

                count = counts.get(current_day, 0)
                label = str(current_day.day)
                if count:
                    label += f"\n{count}"
                button = self.QtWidgets.QPushButton(label)
                button.setMinimumHeight(42)
                if current_day == self.selected_date:
                    button.setObjectName("selectedDayButton")
                elif current_day == today:
                    button.setObjectName("todayDayButton")
                else:
                    button.setObjectName("dayButton")
                button.clicked.connect(lambda checked=False, day=current_day: self._select_date(day))
                self.calendar_grid.addWidget(button, row_index, column_index)

    def _refresh_day_schedule(self, tasks: list[Task]) -> None:
        _clear_widget_children(self.day_schedule_board)
        visible_days = self._visible_day_count()
        self.effective_visible_days = visible_days
        self.day_schedule_board.set_start_date(self.selected_date, visible_days)
        schedule_end_date = self.selected_date + timedelta(days=visible_days - 1)
        if visible_days == 1:
            self.day_header_label.setText(f"{self.selected_date:%d.%m.%Y}")
        else:
            self.day_header_label.setText(
                f"{self.selected_date:%d.%m.%Y} - {schedule_end_date:%d.%m.%Y}"
            )
        self.day_schedule_board.setFixedSize(
            _schedule_board_width(visible_days),
            _day_board_height(),
        )

        visible_dates = _visible_schedule_dates(self.selected_date, visible_days)
        visible_task_ids = {task.id for task in tasks if task.due_date in visible_dates}
        if self.selected_task_id not in visible_task_ids:
            self.selected_task_id = None
            self.selected_task_title = None
            self.title_input.clear()
            self.description_input.clear()

        for task in tasks:
            if task.due_date not in visible_dates:
                continue
            block = self._create_day_task_block(task)
            block.setGeometry(*self._day_task_geometry(task))
            block.show()

        self._render_selected_task_label()
        self._render_selected_timer()

    def _create_day_task_block(self, task: Task) -> object:
        app_window = self

        class DayTaskBlock(self.QtWidgets.QFrame):
            def __init__(block_self) -> None:
                super().__init__(app_window.day_schedule_board)
                block_self.drag_offset = app_window.QtCore.QPoint(0, 0)
                block_self.setObjectName(
                    "selectedScheduleTaskBlock"
                    if task.id == app_window.selected_task_id
                    else "scheduleTaskBlock"
                )
                block_self.setCursor(app_window.QtCore.Qt.CursorShape.OpenHandCursor)

                block_layout = app_window.QtWidgets.QVBoxLayout(block_self)
                block_layout.setContentsMargins(10, 6, 10, 6)
                block_layout.setSpacing(2)
                title_label = app_window.QtWidgets.QLabel(task.title)
                title_label.setObjectName("scheduleTaskTitle")
                title_label.setWordWrap(True)
                time_label = app_window.QtWidgets.QLabel(_format_task_schedule(task))
                time_label.setObjectName("scheduleTaskTime")
                block_layout.addWidget(title_label)
                block_layout.addWidget(time_label)

            def mousePressEvent(block_self, event: object) -> None:
                if event.button() == app_window.QtCore.Qt.MouseButton.LeftButton:
                    app_window._select_task(task)
                    block_self.drag_offset = event.position().toPoint()
                    block_self.setCursor(app_window.QtCore.Qt.CursorShape.ClosedHandCursor)
                super().mousePressEvent(event)

            def mouseMoveEvent(block_self, event: object) -> None:
                if not event.buttons() & app_window.QtCore.Qt.MouseButton.LeftButton:
                    super().mouseMoveEvent(event)
                    return
                next_position = block_self.mapToParent(
                    event.position().toPoint() - block_self.drag_offset
                )
                visible_days = app_window._visible_day_count()
                day_width = _day_column_width(visible_days)
                min_x = _time_column_width()
                max_x = _time_column_width() + day_width * visible_days - block_self.width()
                next_x = max(min_x, min(next_position.x(), max_x))
                next_y = next_position.y()
                min_y = _day_header_height()
                max_y = _day_header_height() + 24 * _hour_height() - block_self.height()
                block_self.move(next_x, max(min_y, min(next_y, max_y)))

            def mouseReleaseEvent(block_self, event: object) -> None:
                block_self.setCursor(app_window.QtCore.Qt.CursorShape.OpenHandCursor)
                if event.button() == app_window.QtCore.Qt.MouseButton.LeftButton:
                    app_window._move_task_to_position(task, block_self.x(), block_self.y())
                super().mouseReleaseEvent(event)

        block = DayTaskBlock()
        return block

    def _day_task_geometry(self, task: Task) -> tuple[int, int, int, int]:
        visible_days = self._visible_day_count()
        day_width = _day_column_width(visible_days)
        task_date = task.due_date or self.selected_date
        day_index = max(0, min((task_date - self.selected_date).days, visible_days - 1))
        start_minutes = _time_to_minutes(task.start_time or time(9, 0))
        end_minutes = _time_to_minutes(task.end_time or time(10, 0))
        if end_minutes <= start_minutes:
            end_minutes = min(24 * 60, start_minutes + 60)

        x = _time_column_width() + day_index * day_width + 10
        y = _day_header_height() + int(start_minutes * _hour_height() / 60) + 3
        width = day_width - 20
        height = max(36, int((end_minutes - start_minutes) * _hour_height() / 60) - 6)
        return x, y, width, height

    def _move_task_to_position(self, task: Task, x: int, y: int) -> None:
        visible_days = self._visible_day_count()
        day_width = _day_column_width(visible_days)
        day_index = max(0, min((x - _time_column_width() + day_width // 2) // day_width, visible_days - 1))
        target_date = self.selected_date + timedelta(days=day_index)
        start_minutes = int((y - _day_header_height()) * 60 / _hour_height())
        start_minutes = max(0, min(start_minutes, 23 * 60 + 45))
        start_minutes = _snap_minutes(start_minutes)
        duration = _task_duration_minutes(task)
        end_minutes = min(24 * 60, start_minutes + duration)
        if end_minutes <= start_minutes:
            end_minutes = min(24 * 60, start_minutes + 60)

        try:
            self.repository.update_task_schedule(
                task.id,
                target_date,
                _minutes_to_time(start_minutes),
                _minutes_to_time(end_minutes),
            )
        except ValueError as error:
            self.QtWidgets.QMessageBox.warning(
                self.window,
                APP_TITLE,
                _translate_storage_error(str(error)),
            )
            return

        if self.selected_task_id == task.id:
            start_value = _minutes_to_time(start_minutes)
            end_value = _minutes_to_time(end_minutes)
            self.start_time_input.setTime(
                self.QtCore.QTime(start_value.hour, start_value.minute)
            )
            self.end_time_input.setTime(
                self.QtCore.QTime(end_value.hour, end_value.minute)
            )
        self.refresh()

    def _render_selected_task_label(self) -> None:
        if self.selected_task_id is None:
            self.selected_task_label.setText("Задача не выбрана")
            return
        self.selected_task_label.setText(f"Выбрана: {self.selected_task_title}")

    def _select_task(self, task: Task) -> None:
        self.selected_task_id = task.id
        self.selected_task_title = task.title
        self.title_input.setText(task.title)
        self.description_input.setPlainText(task.description)
        self.start_time_input.setTime(
            self.QtCore.QTime(
                (task.start_time or time(9, 0)).hour,
                (task.start_time or time(9, 0)).minute,
            )
        )
        self.end_time_input.setTime(
            self.QtCore.QTime(
                (task.end_time or time(10, 0)).hour,
                (task.end_time or time(10, 0)).minute,
            )
        )
        self._render_selected_task_label()
        self._render_selected_timer()

    def _refresh_task_list(self, tasks: list[Task]) -> None:
        selected_task_id = self._selected_task_id()
        self.task_list.clear()
        if not tasks:
            item = self.QtWidgets.QListWidgetItem("Задач пока нет")
            item.setFlags(self.QtCore.Qt.ItemFlag.NoItemFlags)
            item.setForeground(self.QtGui.QColor("#64748B"))
            self.task_list.addItem(item)
            self._render_selected_timer()
            return

        restored_selection_row: int | None = None
        for task in tasks:
            status = "Выполнена" if task.is_completed else "Активна"
            marker = "✓" if task.is_completed else "•"
            due_date = task.due_date.strftime("%d.%m.%Y") if task.due_date else "Без даты"
            schedule = _format_task_schedule(task)
            timer_status = self._timer_status_text(task.id)
            timer_line = f"\n{timer_status}" if timer_status else ""
            item = self.QtWidgets.QListWidgetItem(
                f"{marker}  {task.title}\n{due_date} · {schedule} · {status}{timer_line}"
            )
            item.setData(self.QtCore.Qt.ItemDataRole.UserRole, task.id)
            item.setData(self._task_title_role(), task.title)
            item.setSizeHint(self.QtCore.QSize(0, 76 if timer_status else 58))
            if task.is_completed:
                item.setForeground(self.QtGui.QColor("#64748B"))
            self.task_list.addItem(item)
            if task.id == selected_task_id:
                restored_selection_row = self.task_list.count() - 1

        if restored_selection_row is not None:
            self.task_list.setCurrentRow(restored_selection_row)
        self._render_selected_timer()

    def _add_task(self) -> None:
        title = self.title_input.text()
        description = self.description_input.toPlainText().strip()
        start_time = _qtime_to_time(self.start_time_input.time())
        end_time = _qtime_to_time(self.end_time_input.time())
        try:
            self.repository.add_task(
                title,
                description,
                self.selected_date,
                start_time,
                end_time,
            )
        except ValueError as error:
            self.QtWidgets.QMessageBox.warning(
                self.window,
                APP_TITLE,
                _translate_storage_error(str(error)),
            )
            return

        self.title_input.clear()
        self.description_input.clear()
        self.refresh()

    def _update_selected_task(self) -> None:
        if self.selected_task_id is None:
            self._show_select_task_message()
            return
        title = self.title_input.text()
        description = self.description_input.toPlainText().strip()
        start_time = _qtime_to_time(self.start_time_input.time())
        end_time = _qtime_to_time(self.end_time_input.time())
        try:
            current_task = self.task_by_id.get(self.selected_task_id)
            target_date = (
                current_task.due_date
                if current_task is not None and current_task.due_date is not None
                else self.selected_date
            )
            was_updated = self.repository.update_task(
                self.selected_task_id,
                title,
                description,
                target_date,
                start_time,
                end_time,
            )
        except ValueError as error:
            self.QtWidgets.QMessageBox.warning(
                self.window,
                APP_TITLE,
                _translate_storage_error(str(error)),
            )
            return
        if not was_updated:
            self.QtWidgets.QMessageBox.information(
                self.window,
                APP_TITLE,
                "Выбранная задача не найдена.",
            )
            return
        self.selected_task_title = title.strip()
        self.refresh()

    def _clear_task_form(self) -> None:
        self.selected_task_id = None
        self.selected_task_title = None
        self.title_input.clear()
        self.description_input.clear()
        self.start_time_input.setTime(self.QtCore.QTime(9, 0))
        self.end_time_input.setTime(self.QtCore.QTime(10, 0))
        self._render_selected_task_label()
        self._render_selected_timer()
        self.refresh()

    def _complete_selected_task(self) -> None:
        task_id = self._selected_task_id()
        if task_id is None:
            self._show_select_task_message()
            return
        self.repository.complete_task(task_id)
        self.refresh()

    def _delete_selected_task(self) -> None:
        task_id = self._selected_task_id()
        if task_id is None:
            self._show_select_task_message()
            return
        self.repository.delete_task(task_id)
        self.task_timers.pop(task_id, None)
        self.selected_task_id = None
        self.selected_task_title = None
        self._clear_task_form()

    def _open_day_schedule(self) -> None:
        dialog = self.QtWidgets.QDialog(self.window)
        dialog.setObjectName("scheduleDialog")
        dialog.setWindowTitle("Календарь недели")
        dialog.resize(1040, 720)

        layout = self.QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        week_start = self.selected_date - timedelta(days=self.selected_date.weekday())
        hour_height = 58
        header_height = 54
        time_column_width = 64
        day_width = 128
        board_width = time_column_width + day_width * 7
        board_height = header_height + hour_height * 24 + 12

        header_row = self.QtWidgets.QHBoxLayout()
        previous_week_button = self.QtWidgets.QPushButton("← Неделя")
        next_week_button = self.QtWidgets.QPushButton("Неделя →")
        close_button = self.QtWidgets.QPushButton("Закрыть")
        header = self.QtWidgets.QLabel()
        header.setObjectName("sectionTitle")
        close_button.clicked.connect(dialog.accept)

        header_row.addWidget(previous_week_button)
        header_row.addWidget(header, 1)
        header_row.addWidget(next_week_button)
        header_row.addWidget(close_button)

        scroll_area = self.QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(False)
        scroll_area.setObjectName("scheduleScroll")
        board = self.QtWidgets.QWidget()
        board.setObjectName("scheduleBoard")
        board.setFixedSize(board_width, board_height)
        scroll_area.setWidget(board)

        layout.addLayout(header_row)
        layout.addWidget(scroll_area, 1)

        class ScheduleTaskBlock(self.QtWidgets.QFrame):
            def __init__(
                block_self,
                task: Task,
                parent: object,
                on_drop: object,
            ) -> None:
                super().__init__(parent)
                block_self.task = task
                block_self.on_drop = on_drop
                block_self.drag_offset = self.QtCore.QPoint(0, 0)
                block_self.setObjectName("scheduleTaskBlock")
                block_self.setCursor(self.QtCore.Qt.CursorShape.OpenHandCursor)

                block_layout = self.QtWidgets.QVBoxLayout(block_self)
                block_layout.setContentsMargins(8, 5, 8, 5)
                block_layout.setSpacing(1)
                title_label = self.QtWidgets.QLabel(task.title)
                title_label.setObjectName("scheduleTaskTitle")
                title_label.setWordWrap(True)
                time_label = self.QtWidgets.QLabel(_format_task_schedule(task))
                time_label.setObjectName("scheduleTaskTime")
                block_layout.addWidget(title_label)
                block_layout.addWidget(time_label)

            def mousePressEvent(block_self, event: object) -> None:
                if event.button() == self.QtCore.Qt.MouseButton.LeftButton:
                    block_self.drag_offset = event.position().toPoint()
                    block_self.setCursor(self.QtCore.Qt.CursorShape.ClosedHandCursor)
                super().mousePressEvent(event)

            def mouseMoveEvent(block_self, event: object) -> None:
                if not event.buttons() & self.QtCore.Qt.MouseButton.LeftButton:
                    super().mouseMoveEvent(event)
                    return

                next_position = block_self.mapToParent(event.position().toPoint() - block_self.drag_offset)
                min_x = time_column_width
                max_x = time_column_width + day_width * 7 - block_self.width()
                min_y = header_height
                max_y = header_height + hour_height * 24 - block_self.height()
                x = max(min_x, min(next_position.x(), max_x))
                y = max(min_y, min(next_position.y(), max_y))
                block_self.move(x, y)

            def mouseReleaseEvent(block_self, event: object) -> None:
                block_self.setCursor(self.QtCore.Qt.CursorShape.OpenHandCursor)
                if event.button() == self.QtCore.Qt.MouseButton.LeftButton:
                    block_self.on_drop(block_self.task, block_self.x(), block_self.y())
                super().mouseReleaseEvent(event)

        def update_header() -> None:
            week_end = week_start + timedelta(days=6)
            header.setText(
                f"{week_start.strftime('%d.%m.%Y')} - {week_end.strftime('%d.%m.%Y')}"
            )

        def clear_board() -> None:
            for child in board.findChildren(self.QtWidgets.QWidget):
                child.deleteLater()

        def draw_grid() -> None:
            for day_index, day in enumerate(_week_dates(week_start)):
                label = self.QtWidgets.QLabel(f"{WEEKDAY_NAMES[day_index]}\n{day.strftime('%d.%m')}", board)
                label.setObjectName("scheduleDayHeader")
                label.setAlignment(self.QtCore.Qt.AlignmentFlag.AlignCenter)
                label.setGeometry(
                    time_column_width + day_width * day_index,
                    0,
                    day_width,
                    header_height,
                )

            for hour in range(24):
                y = header_height + hour * hour_height
                hour_label = self.QtWidgets.QLabel(f"{hour:02d}:00", board)
                hour_label.setObjectName("scheduleHourLabel")
                hour_label.setGeometry(0, y - 8, time_column_width - 10, 18)

                line = self.QtWidgets.QFrame(board)
                line.setObjectName("scheduleHourLine")
                line.setGeometry(time_column_width, y, day_width * 7, 1)

        def task_geometry(task: Task) -> tuple[int, int, int, int]:
            task_date = task.due_date or week_start
            day_index = max(0, min((task_date - week_start).days, 6))
            start_minutes = _time_to_minutes(task.start_time or time(9, 0))
            end_minutes = _time_to_minutes(task.end_time or time(10, 0))
            if end_minutes <= start_minutes:
                end_minutes = min(24 * 60, start_minutes + 60)

            x = time_column_width + day_index * day_width + 6
            y = header_height + int(start_minutes * hour_height / 60) + 2
            width = day_width - 12
            height = max(34, int((end_minutes - start_minutes) * hour_height / 60) - 4)
            return x, y, width, height

        def move_task(task: Task, x: int, y: int) -> None:
            day_index = max(0, min((x - time_column_width + day_width // 2) // day_width, 6))
            target_date = week_start + timedelta(days=day_index)

            start_minutes = int((y - header_height) * 60 / hour_height)
            start_minutes = max(0, min(start_minutes, 23 * 60 + 45))
            start_minutes = _snap_minutes(start_minutes)
            duration = _task_duration_minutes(task)
            end_minutes = min(24 * 60, start_minutes + duration)
            if end_minutes <= start_minutes:
                end_minutes = min(24 * 60, start_minutes + 60)

            try:
                self.repository.update_task_schedule(
                    task.id,
                    target_date,
                    _minutes_to_time(start_minutes),
                    _minutes_to_time(end_minutes),
                )
            except ValueError as error:
                self.QtWidgets.QMessageBox.warning(dialog, APP_TITLE, _translate_storage_error(str(error)))
                return

            self.selected_date = target_date
            self.visible_year = target_date.year
            self.visible_month = target_date.month
            render_week()
            self.refresh()

        def render_week() -> None:
            clear_board()
            update_header()
            draw_grid()
            week_end = week_start + timedelta(days=6)
            tasks = [
                task
                for task in self.repository.list_tasks(include_completed=True)
                if task.due_date is not None and week_start <= task.due_date <= week_end
            ]

            for task in tasks:
                block = ScheduleTaskBlock(task, board, move_task)
                block.setGeometry(*task_geometry(task))
                block.show()

            board.update()

        def shift_week(days: int) -> None:
            nonlocal week_start
            week_start = week_start + timedelta(days=days)
            render_week()

        previous_week_button.clicked.connect(lambda: shift_week(-7))
        next_week_button.clicked.connect(lambda: shift_week(7))

        render_week()
        dialog.setStyleSheet(APP_STYLES)
        dialog.exec()

    def _selected_task_id(self) -> int | None:
        return self.selected_task_id

    def _start_timer(self) -> None:
        task_id = self._selected_task_id()
        if task_id is None:
            self._show_select_task_message()
            return
        state = self.task_timers.get(task_id)
        if state is None or state.seconds_left <= 0:
            total_seconds = self.timer_minutes_input.value() * 60
            state = TaskTimerState(
                seconds_left=total_seconds,
                total_seconds=total_seconds,
            )
            self.task_timers[task_id] = state
        state.is_running = True
        self._ensure_timer_running()
        self._render_selected_timer()
        self.refresh()

    def _pause_timer(self) -> None:
        task_id = self._selected_task_id()
        if task_id is None:
            self._show_select_task_message()
            return
        state = self.task_timers.get(task_id)
        if state is not None:
            state.is_running = False
        self._stop_tick_timer_if_idle()
        self._render_selected_timer()
        self.refresh()

    def _reset_timer(self) -> None:
        task_id = self._selected_task_id()
        if task_id is None:
            self._show_select_task_message()
            return
        self.task_timers.pop(task_id, None)
        self._stop_tick_timer_if_idle()
        self._render_selected_timer()
        self.refresh()

    def _tick_timer(self) -> None:
        completed_task_ids: list[int] = []
        for task_id, state in self.task_timers.items():
            if not state.is_running:
                continue
            state.seconds_left = max(0, state.seconds_left - 1)
            if state.seconds_left == 0:
                state.is_running = False
                completed_task_ids.append(task_id)

        self._render_selected_timer()
        self._stop_tick_timer_if_idle()

        for task_id in completed_task_ids:
            self.QtWidgets.QMessageBox.information(
                self.window,
                APP_TITLE,
                f"Время на задачу #{task_id} истекло.",
            )

    def _render_selected_timer(self) -> None:
        task_id = self._selected_task_id()
        if task_id is None:
            self.timer_task_label.setText("Выберите задачу")
            self._render_timer_seconds(0)
            self.timer_ring.set_timer(0, 0)
            return

        task_title = self._selected_task_title() or f"Задача #{task_id}"
        state = self.task_timers.get(task_id)
        if state is None:
            self.timer_task_label.setText(f"Таймер для: {task_title}")
            self._render_timer_seconds(0)
            self.timer_ring.set_timer(0, 0)
            return

        status = "идет" if state.is_running else "на паузе"
        self.timer_task_label.setText(f"Таймер для: {task_title} ({status})")
        self._render_timer_seconds(state.seconds_left)
        self.timer_ring.set_timer(state.seconds_left, state.total_seconds)

    def _render_timer_seconds(self, seconds_left: int) -> None:
        minutes, seconds = divmod(seconds_left, 60)
        self.timer_label.setText(f"{minutes:02d}:{seconds:02d}")

    def _timer_status_text(self, task_id: int) -> str:
        state = self.task_timers.get(task_id)
        if state is None:
            return ""
        minutes, seconds = divmod(state.seconds_left, 60)
        status = "идет" if state.is_running else "пауза"
        return f"Таймер: {minutes:02d}:{seconds:02d} · {status}"

    def _ensure_timer_running(self) -> None:
        if not self.timer.isActive():
            self.timer.start(1000)

    def _stop_tick_timer_if_idle(self) -> None:
        if not any(state.is_running for state in self.task_timers.values()):
            self.timer.stop()

    def _selected_task_title(self) -> str | None:
        return self.selected_task_title

    def _task_title_role(self) -> int:
        return self.QtCore.Qt.ItemDataRole.UserRole.value + 1

    def _task_schedule_role(self) -> int:
        return self.QtCore.Qt.ItemDataRole.UserRole.value + 2

    def _show_select_task_message(self) -> None:
        self.QtWidgets.QMessageBox.information(
            self.window,
            APP_TITLE,
            "Сначала выберите задачу.",
        )

    def _select_today(self) -> None:
        self._select_date(date.today())

    def _select_date(self, selected_date: date) -> None:
        self.selected_date = selected_date
        self.visible_year = selected_date.year
        self.visible_month = selected_date.month
        self.refresh()

    def _shift_month(self, months: int) -> None:
        month_number = self.visible_month - 1 + months
        self.visible_year += month_number // 12
        self.visible_month = month_number % 12 + 1
        self.refresh()


def main(argv: Sequence[str] | None = None) -> int:
    """Start the desktop application."""
    parser = argparse.ArgumentParser(description="Открыть календарь задач.")
    parser.add_argument(
        "--database-url",
        default=database_url_from_env(),
        help="Строка подключения к PostgreSQL.",
    )
    args = parser.parse_args(argv)

    try:
        _, _, QtWidgets = _load_qt()
    except MissingPySideError as error:
        print(error)
        return 1

    app = QtWidgets.QApplication(sys.argv[:1])
    app.setApplicationName(APP_TITLE)

    repository = TaskRepository(args.database_url)
    try:
        repository.initialize()
    except Exception as error:
        QtWidgets.QMessageBox.critical(
            None,
            APP_TITLE,
            f"Не удалось подключиться к PostgreSQL:\n{error}",
        )
        return 1

    window = MainWindow(repository)
    window.show()
    return app.exec()


def _format_month_title(year: int, month: int) -> str:
    return f"{MONTH_NAMES[month]} {year}"


def _time_column_width() -> int:
    return 70


def _day_column_width(visible_days: int) -> int:
    return 690 if visible_days == 1 else 136


def _hour_height() -> int:
    return 62


def _day_header_height() -> int:
    return 54


def _day_board_width() -> int:
    return _time_column_width() + _day_column_width(1)


def _schedule_board_width(visible_days: int) -> int:
    return _time_column_width() + _day_column_width(visible_days) * visible_days


def _day_board_height() -> int:
    return _day_header_height() + _hour_height() * 24 + 12


def _clear_layout(layout: object) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


def _clear_widget_children(widget: object) -> None:
    for child in widget.children():
        if hasattr(child, "setParent") and hasattr(child, "deleteLater"):
            child.setParent(None)
            child.deleteLater()


def _format_task_schedule(task: Task) -> str:
    if task.start_time is None and task.end_time is None:
        return "Без времени"
    if task.start_time is not None and task.end_time is not None:
        return f"{task.start_time.strftime('%H:%M')}-{task.end_time.strftime('%H:%M')}"
    if task.start_time is not None:
        return f"с {task.start_time.strftime('%H:%M')}"
    return f"до {task.end_time.strftime('%H:%M')}"


def _qtime_to_time(value: object) -> time:
    return time(value.hour(), value.minute())


def _week_dates(week_start: date) -> list[date]:
    return [week_start + timedelta(days=offset) for offset in range(7)]


def _visible_schedule_dates(start_date: date, visible_days: int) -> set[date]:
    return {start_date + timedelta(days=offset) for offset in range(visible_days)}


def _time_to_minutes(value: time) -> int:
    return value.hour * 60 + value.minute


def _minutes_to_time(value: int) -> time:
    value = max(0, min(value, 24 * 60 - 1))
    hours, minutes = divmod(value, 60)
    return time(hours, minutes)


def _format_seconds(value: int) -> str:
    minutes, seconds = divmod(max(0, value), 60)
    return f"{minutes:02d}:{seconds:02d}"


def _snap_minutes(value: int, step: int = 15) -> int:
    return round(value / step) * step


def _task_duration_minutes(task: Task) -> int:
    if task.start_time is None or task.end_time is None:
        return 60
    duration = _time_to_minutes(task.end_time) - _time_to_minutes(task.start_time)
    return max(15, duration)


def _translate_storage_error(message: str) -> str:
    if message == "Task title is required.":
        return "Введите название задачи."
    if message == "Task end time must be after start time.":
        return "Время окончания должно быть позже времени начала."
    return message


APP_STYLES = """
#appRoot {
    background: #edf2f7;
}

QDialog#scheduleDialog {
    background: #ffffff;
}

#panel {
    background: #ffffff;
    border: 1px solid #d9e2ec;
    border-radius: 14px;
}

#calendarPanel,
#formPanel,
#timerPanel {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}

#scheduleScroll {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}

#scheduleBoard {
    background: #ffffff;
}

#dayScheduleBoard {
    background: #ffffff;
}

#scheduleDayHeader {
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
    color: #0f172a;
    font-size: 13px;
    font-weight: 700;
}

#scheduleHourLabel {
    color: #64748b;
    font-size: 12px;
}

#scheduleHourLine {
    background: #e2e8f0;
}

#scheduleTaskBlock {
    background: #dbeafe;
    border: 1px solid #93c5fd;
    border-radius: 10px;
}

#selectedScheduleTaskBlock {
    background: #bfdbfe;
    border: 2px solid #2563eb;
    border-radius: 10px;
}

#scheduleTaskTitle {
    color: #1e3a8a;
    font-size: 13px;
    font-weight: 700;
}

#scheduleTaskTime {
    color: #2563eb;
    font-size: 12px;
}

#appTitle {
    color: #0f172a;
    font-size: 28px;
    font-weight: 800;
}

#sectionTitle {
    color: #334155;
    font-size: 15px;
    font-weight: 700;
}

#dateTitle {
    color: #0f172a;
    font-size: 24px;
    font-weight: 800;
}

#sidebarMonthTitle {
    color: #0f172a;
    font-size: 17px;
    font-weight: 800;
}

#formTitle {
    color: #0f172a;
    font-size: 15px;
    font-weight: 700;
}

#mutedText,
#weekdayLabel {
    color: #64748b;
    font-size: 13px;
}

#timerLabel {
    color: #0f172a;
    font-size: 24px;
    font-weight: 800;
    min-width: 76px;
}

QPushButton {
    background: #e2e8f0;
    border: none;
    border-radius: 9px;
    color: #0f172a;
    font-size: 14px;
    font-weight: 600;
    padding: 10px 14px;
}

QPushButton:hover {
    background: #cbd5e1;
}

QPushButton#primaryButton {
    background: #2563eb;
    color: white;
}

QPushButton#primaryButton:hover {
    background: #1d4ed8;
}

QPushButton#dangerButton {
    background: #fee2e2;
    color: #991b1b;
}

QPushButton#dangerButton:hover {
    background: #fecaca;
}

QPushButton#dayButton {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    padding: 7px;
}

QPushButton#todayDayButton {
    background: #eff6ff;
    border: 1px solid #93c5fd;
    color: #1d4ed8;
    padding: 7px;
}

QPushButton#selectedDayButton {
    background: #2563eb;
    border: 1px solid #2563eb;
    color: #ffffff;
    padding: 7px;
}

QLineEdit,
QPlainTextEdit,
QSpinBox,
QTimeEdit {
    background: white;
    border: 1px solid #cbd5e1;
    border-radius: 9px;
    color: #0f172a;
    font-size: 14px;
    padding: 9px 10px;
}

QLineEdit:focus,
QPlainTextEdit:focus,
QSpinBox:focus,
QTimeEdit:focus {
    border: 1px solid #2563eb;
}

QListWidget#taskList {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    color: #0f172a;
    font-size: 14px;
    outline: 0;
    padding: 6px;
}

QListWidget#taskList::item {
    border-radius: 9px;
    margin: 4px;
    padding: 9px;
}

QListWidget#taskList::item:selected {
    background: #dbeafe;
    color: #1e3a8a;
}
"""


if __name__ == "__main__":
    raise SystemExit(main())
