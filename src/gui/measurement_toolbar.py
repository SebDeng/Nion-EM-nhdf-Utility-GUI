"""
Measurement toolbar for preview mode.
Provides distance measurement tools with controls.
"""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QPainter, QPixmap, QPen, QColor


def create_measurement_icon(size: int = 24, color: QColor = None) -> QIcon:
    """Create a minimalist measurement line icon."""
    if color is None:
        color = QColor(200, 200, 200)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Draw diagonal line
    pen = QPen(color)
    pen.setWidth(2)
    painter.setPen(pen)

    margin = 4
    painter.drawLine(margin, size - margin, size - margin, margin)

    # Draw endpoint circles
    painter.setBrush(color)
    circle_radius = 3
    painter.drawEllipse(margin - circle_radius, size - margin - circle_radius,
                        circle_radius * 2, circle_radius * 2)
    painter.drawEllipse(size - margin - circle_radius, margin - circle_radius,
                        circle_radius * 2, circle_radius * 2)

    painter.end()
    return QIcon(pixmap)


class MeasurementToolBar(QFrame):
    """
    Toolbar for measurement tools in preview mode.
    Shows distance measurement info and controls.
    """

    # Signals
    create_measurement = Signal()  # Emitted when create measurement is clicked
    confirm_measurement = Signal()  # Emitted when confirm button is clicked
    clear_all = Signal()  # Emitted when clear all button is clicked
    clear_last = Signal()  # Emitted when clear last button is clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MeasurementToolBar")
        self._is_dark_mode = True
        self._measurement_count = 0  # Track number of active measurements

        self._setup_ui()
        self._apply_theme()

    def _setup_ui(self):
        """Set up the measurement toolbar UI."""
        self.setFrameShape(QFrame.NoFrame)
        self.setMaximumHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Create measurement button with icon
        self._create_btn = QToolButton()
        self._create_btn.setIcon(create_measurement_icon(24, QColor(200, 200, 200)))
        self._create_btn.setIconSize(QSize(20, 20))
        self._create_btn.setToolTip("Add measurement line (M)\nHold Shift while dragging for H/V constraint")
        self._create_btn.setShortcut("M")
        self._create_btn.clicked.connect(self._on_create_measurement)
        layout.addWidget(self._create_btn)

        # Measurement count label
        self._count_label = QLabel("0")
        self._count_label.setMinimumWidth(20)
        self._count_label.setStyleSheet("font-size: 11px; color: #888;")
        self._count_label.setToolTip("Number of measurements")
        layout.addWidget(self._count_label)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet("color: #555;")
        layout.addWidget(sep1)

        # Distance display label
        self._distance_label = QLabel("Distance: --")
        self._distance_label.setMinimumWidth(150)
        self._distance_label.setStyleSheet("font-family: monospace; font-size: 12px;")
        layout.addWidget(self._distance_label)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color: #555;")
        layout.addWidget(sep2)

        # Clear last button
        self._clear_last_btn = QPushButton("Clear Last")
        self._clear_last_btn.setToolTip("Remove the last measurement")
        self._clear_last_btn.clicked.connect(self._on_clear_last)
        layout.addWidget(self._clear_last_btn)

        # Clear all button
        self._clear_all_btn = QPushButton("Clear All")
        self._clear_all_btn.setToolTip("Remove all measurements")
        self._clear_all_btn.clicked.connect(self._on_clear_all)
        layout.addWidget(self._clear_all_btn)

        # Add stretch to push everything to the left
        layout.addStretch()

    def _on_create_measurement(self):
        """Handle create measurement button click."""
        self._measurement_count += 1
        self._count_label.setText(str(self._measurement_count))
        self.create_measurement.emit()

    def _on_clear_last(self):
        """Handle clear last button click."""
        if self._measurement_count > 0:
            self._measurement_count -= 1
            self._count_label.setText(str(self._measurement_count))
        self.clear_last.emit()

    def _on_clear_all(self):
        """Handle clear all button click."""
        self._distance_label.setText("Distance: --")
        self._measurement_count = 0
        self._count_label.setText("0")
        self.clear_all.emit()

    def set_measurement_count(self, count: int):
        """Update the measurement count display."""
        self._measurement_count = count
        self._count_label.setText(str(count))

    def update_distance(self, distance_px: float, distance_nm: float = None):
        """Update the distance display."""
        if distance_nm is not None:
            if distance_nm >= 1000:
                text = f"Distance: {distance_nm/1000:.3f} μm ({distance_px:.1f} px)"
            elif distance_nm >= 1:
                text = f"Distance: {distance_nm:.2f} nm ({distance_px:.1f} px)"
            else:
                text = f"Distance: {distance_nm:.3f} nm ({distance_px:.1f} px)"
        else:
            text = f"Distance: {distance_px:.1f} px"

        self._distance_label.setText(text)

    def clear_distance(self):
        """Clear the distance display."""
        self._distance_label.setText("Distance: --")

    def set_theme(self, is_dark: bool):
        """Update toolbar theme."""
        self._is_dark_mode = is_dark
        self._apply_theme()

    def _apply_theme(self):
        """Apply the current theme to the toolbar."""
        # Update icon color based on theme
        icon_color = QColor(200, 200, 200) if self._is_dark_mode else QColor(80, 80, 80)
        self._create_btn.setIcon(create_measurement_icon(24, icon_color))

        if self._is_dark_mode:
            # Dark theme
            self.setStyleSheet("""
                QFrame#MeasurementToolBar {
                    background-color: #2b2b2b;
                    border: none;
                }
                QLabel {
                    color: #e0e0e0;
                }
                QToolButton {
                    background-color: #3a3a3a;
                    border: 1px solid #555;
                    border-radius: 4px;
                    padding: 4px;
                }
                QToolButton:hover {
                    background-color: #454545;
                    border-color: #666;
                }
                QToolButton:pressed {
                    background-color: #0d7377;
                }
                QPushButton {
                    background-color: #3a3a3a;
                    border: 1px solid #555;
                    border-radius: 4px;
                    padding: 4px 10px;
                    color: #e0e0e0;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #454545;
                    border-color: #666;
                }
                QPushButton:pressed {
                    background-color: #0d7377;
                }
                QPushButton:disabled {
                    background-color: #2a2a2a;
                    color: #666;
                    border-color: #444;
                }
            """)
        else:
            # Light theme
            self.setStyleSheet("""
                QFrame#MeasurementToolBar {
                    background-color: #f5f5f5;
                    border: none;
                }
                QLabel {
                    color: #333;
                }
                QToolButton {
                    background-color: #e0e0e0;
                    border: 1px solid #bbb;
                    border-radius: 4px;
                    padding: 4px;
                }
                QToolButton:hover {
                    background-color: #d0d0d0;
                    border-color: #999;
                }
                QToolButton:pressed {
                    background-color: #14a085;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    border: 1px solid #bbb;
                    border-radius: 4px;
                    padding: 4px 10px;
                    color: #333;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #d0d0d0;
                    border-color: #999;
                }
                QPushButton:pressed {
                    background-color: #14a085;
                    color: white;
                }
                QPushButton:disabled {
                    background-color: #f0f0f0;
                    color: #999;
                    border-color: #ccc;
                }
            """)
