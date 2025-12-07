"""
View mode toolbar with grid layout buttons similar to Nion Swift.
"""

from PySide6.QtWidgets import (
    QToolBar, QToolButton, QWidget, QHBoxLayout, QButtonGroup
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPainter, QIcon, QPixmap, QPen, QColor, QBrush, QPainterPath

from typing import Tuple, List


class ThemeIcon:
    """Helper class to generate theme toggle icons."""

    @staticmethod
    def create_sun(size: int = 24) -> QIcon:
        """Create a sun icon for light mode."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Sun color
        sun_color = QColor(255, 200, 50)
        painter.setPen(QPen(sun_color, 2))
        painter.setBrush(QBrush(sun_color))

        # Center circle
        center = size // 2
        radius = size // 5
        painter.drawEllipse(center - radius, center - radius, radius * 2, radius * 2)

        # Sun rays
        painter.setPen(QPen(sun_color, 2))
        for angle in range(0, 360, 45):
            import math
            radian = math.radians(angle)
            x1 = center + (radius + 3) * math.cos(radian)
            y1 = center + (radius + 3) * math.sin(radian)
            x2 = center + (radius + 6) * math.cos(radian)
            y2 = center + (radius + 6) * math.sin(radian)
            painter.drawLine(x1, y1, x2, y2)

        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def create_moon(size: int = 24) -> QIcon:
        """Create a moon icon for dark mode."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Moon color
        moon_color = QColor(200, 200, 255)
        painter.setPen(QPen(moon_color, 2))
        painter.setBrush(QBrush(moon_color))

        # Draw crescent moon
        center = size // 2
        radius = size // 3

        path = QPainterPath()
        path.addEllipse(center - radius, center - radius, radius * 2, radius * 2)

        # Cut out part to make crescent
        cut_path = QPainterPath()
        cut_path.addEllipse(center - radius + 4, center - radius - 2, radius * 2, radius * 2)

        moon_path = path.subtracted(cut_path)
        painter.drawPath(moon_path)

        painter.end()
        return QIcon(pixmap)


class GridIcon:
    """Helper class to generate grid layout icons."""

    @staticmethod
    def create(rows: int, cols: int, size: int = 24) -> QIcon:
        """Create a grid icon with the specified rows and columns."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # Colors for the grid (simpler, cleaner look)
        border_color = QColor(150, 150, 150)
        fill_color = QColor(100, 100, 100)

        # Calculate cell size with padding
        padding = 4
        cell_width = (size - padding * 2) / cols
        cell_height = (size - padding * 2) / rows

        # Draw grid cells
        for row in range(rows):
            for col in range(cols):
                x = padding + col * cell_width
                y = padding + row * cell_height

                # Draw filled rectangle
                painter.fillRect(x + 1, y + 1,
                               cell_width - 2, cell_height - 2,
                               fill_color)

                # Draw border
                painter.setPen(QPen(border_color, 1))
                painter.drawRect(x, y, cell_width - 1, cell_height - 1)

        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def create_custom(layout: List[List[bool]], size: int = 24) -> QIcon:
        """Create a custom grid icon based on a boolean layout."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        border_color = QColor(150, 150, 150)
        fill_color = QColor(100, 100, 100)

        rows = len(layout)
        cols = len(layout[0]) if rows > 0 else 0

        padding = 4
        cell_width = (size - padding * 2) / cols if cols > 0 else 0
        cell_height = (size - padding * 2) / rows if rows > 0 else 0

        for row in range(rows):
            for col in range(cols):
                if col < len(layout[row]) and layout[row][col]:
                    x = padding + col * cell_width
                    y = padding + row * cell_height

                    painter.fillRect(x + 1, y + 1,
                                   cell_width - 2, cell_height - 2,
                                   fill_color)

                    painter.setPen(QPen(border_color, 1))
                    painter.drawRect(x, y, cell_width - 1, cell_height - 1)

        painter.end()
        return QIcon(pixmap)


class ViewModeToolBar(QToolBar):
    """Toolbar with grid layout buttons for workspace view modes."""

    # Signal emitted when a layout is selected
    layout_selected = Signal(str)  # Emits layout ID
    # Signal emitted when theme is toggled
    theme_changed = Signal(bool)  # True for dark mode, False for light mode

    def __init__(self, parent=None):
        super().__init__("View Mode", parent)

        self.setMovable(False)
        self.setIconSize(QSize(24, 24))  # Smaller icons like Nion Swift

        # Button group for exclusive selection
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        self._is_dark_mode = True  # Start in dark mode
        self._apply_theme_styles()  # Apply theme-specific styles
        self._setup_buttons()

    def _apply_theme_styles(self):
        """Apply theme-specific styling to the toolbar."""
        if self._is_dark_mode:
            # Dark theme
            self.setStyleSheet("""
                QToolBar {
                    background-color: #353535;
                    border: none;
                    padding: 2px;
                    spacing: 2px;
                }
                QToolButton {
                    background-color: transparent;
                    border: 1px solid transparent;
                    border-radius: 2px;
                    padding: 2px;
                    margin: 1px;
                    color: #cccccc;
                }
                QToolButton:hover {
                    background-color: #505050;
                    border: 1px solid #606060;
                }
                QToolButton:checked {
                    background-color: #2a82da;
                    border: 1px solid #3a92ea;
                }
                QToolButton:pressed {
                    background-color: #1a72ca;
                }
            """)
        else:
            # Light theme
            self.setStyleSheet("""
                QToolBar {
                    background-color: #f0f0f0;
                    border: none;
                    padding: 2px;
                    spacing: 2px;
                }
                QToolButton {
                    background-color: transparent;
                    border: 1px solid transparent;
                    border-radius: 2px;
                    padding: 2px;
                    margin: 1px;
                    color: #333333;
                }
                QToolButton:hover {
                    background-color: #e0e0e0;
                    border: 1px solid #c0c0c0;
                }
                QToolButton:checked {
                    background-color: #2a82da;
                    border: 1px solid #3a92ea;
                    color: white;
                }
                QToolButton:pressed {
                    background-color: #1a72ca;
                }
            """)

    def _setup_buttons(self):
        """Set up the view mode buttons."""

        # Define layouts with (rows, cols, id, tooltip)
        # Icons match actual layout (horizontal = side by side, vertical = stacked)
        layouts = [
            (1, 1, "single", "Single Panel"),
            (1, 2, "h2", "2 Panels Horizontal"),  # Horizontal = side by side (1 row, 2 cols)
            (2, 1, "v2", "2 Panels Vertical"),    # Vertical = stacked (2 rows, 1 col)
            (2, 2, "grid4", "4 Panel Grid (2×2)"),
            (1, 3, "h3", "3 Panels Horizontal"),  # Horizontal = side by side (1 row, 3 cols)
            (3, 1, "v3", "3 Panels Vertical"),    # Vertical = stacked (3 rows, 1 col)
            (3, 3, "grid9", "9 Panel Grid (3×3)"),
            (2, 3, "grid6", "6 Panel Grid (2×3)"),
            (3, 2, "grid6_v", "6 Panel Grid (3×2)"),
        ]

        # Add buttons for each layout
        for rows, cols, layout_id, tooltip in layouts:
            icon = GridIcon.create(rows, cols)
            button = QToolButton()
            button.setIcon(icon)
            button.setToolTip(tooltip)
            button.setCheckable(True)
            button.setProperty("layout_id", layout_id)
            button.setProperty("rows", rows)
            button.setProperty("cols", cols)

            # Connect button click
            button.clicked.connect(lambda checked, lid=layout_id:
                                 self._on_button_clicked(lid))

            self._button_group.addButton(button)
            self.addWidget(button)

            # Select first button by default
            if layout_id == "single":
                button.setChecked(True)

        # Add separator before theme toggle
        self.addSeparator()

        # Add theme toggle button
        self._theme_button = QToolButton()
        self._theme_button.setIcon(ThemeIcon.create_moon())  # Start with moon icon (dark mode)
        self._theme_button.setToolTip("Toggle Dark/Light Mode")
        self._theme_button.setCheckable(False)
        self._theme_button.clicked.connect(self._toggle_theme)
        self.addWidget(self._theme_button)

    def _on_button_clicked(self, layout_id: str):
        """Handle button click."""
        self.layout_selected.emit(layout_id)

    def _toggle_theme(self):
        """Toggle between dark and light mode."""
        self._is_dark_mode = not self._is_dark_mode

        # Update toolbar's own styles
        self._apply_theme_styles()

        # Update icon
        if self._is_dark_mode:
            self._theme_button.setIcon(ThemeIcon.create_moon())
            self._theme_button.setToolTip("Switch to Light Mode")
        else:
            self._theme_button.setIcon(ThemeIcon.create_sun())
            self._theme_button.setToolTip("Switch to Dark Mode")

        # Emit signal
        self.theme_changed.emit(self._is_dark_mode)

    def set_theme(self, is_dark: bool):
        """Set the theme programmatically."""
        if self._is_dark_mode != is_dark:
            self._is_dark_mode = is_dark
            self._apply_theme_styles()

            # Update icon
            if self._is_dark_mode:
                self._theme_button.setIcon(ThemeIcon.create_moon())
                self._theme_button.setToolTip("Switch to Light Mode")
            else:
                self._theme_button.setIcon(ThemeIcon.create_sun())
                self._theme_button.setToolTip("Switch to Dark Mode")

    def select_layout(self, layout_id: str):
        """Programmatically select a layout button."""
        for button in self._button_group.buttons():
            if button.property("layout_id") == layout_id:
                button.setChecked(True)
                break

    def get_layout_config(self, layout_id: str) -> dict:
        """Get the configuration for a layout ID."""
        for button in self._button_group.buttons():
            if button.property("layout_id") == layout_id:
                if button.property("custom_layout"):
                    return {
                        "type": "custom",
                        "pattern": button.property("custom_layout")
                    }
                else:
                    return {
                        "type": "grid",
                        "rows": button.property("rows"),
                        "cols": button.property("cols")
                    }
        return None