"""
Measurement toolbar for preview mode.
Provides distance measurement tools with controls.
"""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton, QCheckBox, QSpinBox
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


def create_polygon_icon(size: int = 24, color: QColor = None) -> QIcon:
    """Create a minimalist polygon/area measurement icon."""
    if color is None:
        color = QColor(200, 200, 200)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    pen = QPen(color)
    pen.setWidth(2)
    painter.setPen(pen)

    # Draw a pentagon shape
    margin = 4
    center_x = size / 2
    center_y = size / 2
    radius = (size - 2 * margin) / 2

    import math
    points = []
    num_vertices = 5
    for i in range(num_vertices):
        angle = 2 * math.pi * i / num_vertices - math.pi / 2
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        points.append((int(x), int(y)))

    # Draw the polygon
    for i in range(num_vertices):
        j = (i + 1) % num_vertices
        painter.drawLine(points[i][0], points[i][1], points[j][0], points[j][1])

    # Draw vertex circles
    painter.setBrush(color)
    circle_radius = 2
    for x, y in points:
        painter.drawEllipse(x - circle_radius, y - circle_radius,
                            circle_radius * 2, circle_radius * 2)

    painter.end()
    return QIcon(pixmap)


def create_dose_icon(size: int = 24, color: QColor = None) -> QIcon:
    """Create an electron dose / radiation icon."""
    if color is None:
        color = QColor(200, 200, 200)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    pen = QPen(color)
    pen.setWidth(2)
    painter.setPen(pen)

    center_x = size // 2
    center_y = size // 2
    radius = size // 2 - 4

    # Draw outer circle (atom symbol)
    painter.drawEllipse(center_x - radius, center_y - radius, radius * 2, radius * 2)

    # Draw inner filled circle (nucleus)
    inner_radius = 3
    painter.setBrush(color)
    painter.drawEllipse(center_x - inner_radius, center_y - inner_radius,
                        inner_radius * 2, inner_radius * 2)

    # Draw electron orbits (3 small circles on the ring)
    import math
    orbit_radius = 2
    for angle in [0, 120, 240]:
        rad = math.radians(angle - 90)
        ex = center_x + int(radius * math.cos(rad))
        ey = center_y + int(radius * math.sin(rad))
        painter.drawEllipse(ex - orbit_radius, ey - orbit_radius,
                            orbit_radius * 2, orbit_radius * 2)

    painter.end()
    return QIcon(pixmap)


def create_pipette_icon(size: int = 24, color: QColor = None) -> QIcon:
    """Create a pipette/eyedropper icon for auto-detection."""
    if color is None:
        color = QColor(200, 200, 200)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    pen = QPen(color)
    pen.setWidth(2)
    painter.setPen(pen)

    # Draw pipette shape (diagonal dropper)
    # Tip at bottom-left, bulb at top-right
    margin = 3

    # Pipette body (diagonal rectangle)
    from PySide6.QtGui import QPolygonF
    from PySide6.QtCore import QPointF

    # Draw the pipette tube
    painter.drawLine(margin + 4, size - margin - 4, size - margin - 4, margin + 4)

    # Draw pipette tip (small triangle at bottom-left)
    tip_points = [
        QPointF(margin, size - margin),
        QPointF(margin + 6, size - margin - 4),
        QPointF(margin + 4, size - margin - 6),
    ]
    painter.setBrush(color)
    painter.drawPolygon(QPolygonF(tip_points))

    # Draw bulb at top-right (circle)
    bulb_x = size - margin - 6
    bulb_y = margin + 2
    bulb_radius = 4
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(int(bulb_x - bulb_radius), int(bulb_y - bulb_radius),
                        bulb_radius * 2, bulb_radius * 2)

    # Draw small drop inside tip
    painter.setBrush(color)
    drop_radius = 2
    painter.drawEllipse(margin + 2 - drop_radius, size - margin - 2 - drop_radius,
                        drop_radius * 2, drop_radius * 2)

    painter.end()
    return QIcon(pixmap)


def create_delete_icon(size: int = 24, color: QColor = None) -> QIcon:
    """Create a trash/delete icon."""
    if color is None:
        color = QColor(255, 100, 100)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    pen = QPen(color)
    pen.setWidth(2)
    painter.setPen(pen)

    margin = 4
    # Draw trash can body
    body_top = margin + 5
    body_bottom = size - margin
    body_left = margin + 2
    body_right = size - margin - 2

    # Body outline
    painter.drawLine(body_left, body_top, body_left + 2, body_bottom)
    painter.drawLine(body_right, body_top, body_right - 2, body_bottom)
    painter.drawLine(body_left + 2, body_bottom, body_right - 2, body_bottom)

    # Lid
    lid_y = margin + 3
    painter.drawLine(margin, lid_y, size - margin, lid_y)

    # Handle on lid
    handle_width = 6
    handle_x = size // 2 - handle_width // 2
    painter.drawLine(handle_x, lid_y, handle_x, margin)
    painter.drawLine(handle_x, margin, handle_x + handle_width, margin)
    painter.drawLine(handle_x + handle_width, margin, handle_x + handle_width, lid_y)

    # Vertical lines inside trash
    mid_x = size // 2
    painter.drawLine(mid_x, body_top + 3, mid_x, body_bottom - 3)
    painter.drawLine(mid_x - 4, body_top + 3, mid_x - 3, body_bottom - 3)
    painter.drawLine(mid_x + 4, body_top + 3, mid_x + 3, body_bottom - 3)

    painter.end()
    return QIcon(pixmap)


def create_memo_icon(size: int = 24, color: QColor = None) -> QIcon:
    """Create a sticky note / memo pad icon."""
    if color is None:
        color = QColor(200, 200, 200)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    margin = 3
    note_width = size - 2 * margin
    note_height = size - 2 * margin
    fold_size = 5

    # Draw the sticky note shape (rectangle with folded corner)
    pen = QPen(color)
    pen.setWidth(2)
    painter.setPen(pen)

    # Main rectangle (without top-right corner)
    from PySide6.QtGui import QPolygonF
    from PySide6.QtCore import QPointF
    points = [
        QPointF(margin, margin),  # Top-left
        QPointF(margin + note_width - fold_size, margin),  # Top (before fold)
        QPointF(margin + note_width, margin + fold_size),  # After fold
        QPointF(margin + note_width, margin + note_height),  # Bottom-right
        QPointF(margin, margin + note_height),  # Bottom-left
    ]
    painter.drawPolygon(QPolygonF(points))

    # Draw the fold line
    painter.drawLine(
        int(margin + note_width - fold_size), margin,
        int(margin + note_width - fold_size), int(margin + fold_size)
    )
    painter.drawLine(
        int(margin + note_width - fold_size), int(margin + fold_size),
        int(margin + note_width), int(margin + fold_size)
    )

    # Draw text lines inside
    line_y = margin + 7
    line_margin = 5
    painter.setPen(QPen(color, 1))
    for i in range(3):
        if line_y + 3 < margin + note_height - 3:
            painter.drawLine(
                int(margin + line_margin), int(line_y),
                int(margin + note_width - line_margin - 2), int(line_y)
            )
            line_y += 4

    painter.end()
    return QIcon(pixmap)


class MeasurementToolBar(QFrame):
    """
    Toolbar for measurement tools in preview mode.
    Shows distance measurement info and controls.
    """

    # Signals
    create_measurement = Signal()  # Emitted when create measurement is clicked
    create_polygon = Signal()  # Emitted when create polygon is clicked
    create_pipette = Signal()  # Emitted when pipette auto-detect is clicked
    create_memo = Signal()  # Emitted when create memo is clicked
    open_dose_calculator = Signal()  # Emitted when dose calculator is clicked
    confirm_measurement = Signal()  # Emitted when confirm button is clicked
    clear_all = Signal()  # Emitted when clear all button is clicked
    clear_last = Signal()  # Emitted when clear last button is clicked
    toggle_labels = Signal(bool)  # Emitted when show labels checkbox is toggled
    font_size_changed = Signal(int)  # Emitted when font size is changed
    delete_mode_changed = Signal(bool)  # Emitted when delete mode is toggled

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

        # Create measurement line button with icon
        self._create_btn = QToolButton()
        self._create_btn.setIcon(create_measurement_icon(24, QColor(200, 200, 200)))
        self._create_btn.setIconSize(QSize(20, 20))
        self._create_btn.setToolTip("Add measurement line (M)\nHold Shift while dragging for H/V constraint")
        self._create_btn.setShortcut("M")
        self._create_btn.clicked.connect(self._on_create_measurement)
        layout.addWidget(self._create_btn)

        # Create polygon area button with icon
        self._create_polygon_btn = QToolButton()
        self._create_polygon_btn.setIcon(create_polygon_icon(24, QColor(200, 200, 200)))
        self._create_polygon_btn.setIconSize(QSize(20, 20))
        self._create_polygon_btn.setToolTip("Add polygon for area measurement (P)")
        self._create_polygon_btn.setShortcut("P")
        self._create_polygon_btn.clicked.connect(self._on_create_polygon)
        layout.addWidget(self._create_polygon_btn)

        # Create pipette auto-detect button with icon
        self._create_pipette_btn = QToolButton()
        self._create_pipette_btn.setIcon(create_pipette_icon(24, QColor(100, 255, 200)))  # Cyan-green
        self._create_pipette_btn.setIconSize(QSize(20, 20))
        self._create_pipette_btn.setToolTip("Auto-detect polygon (I)\nClick on dark region to detect boundary")
        self._create_pipette_btn.setShortcut("I")
        self._create_pipette_btn.clicked.connect(self._on_create_pipette)
        layout.addWidget(self._create_pipette_btn)

        # Create memo pad button with icon
        self._create_memo_btn = QToolButton()
        self._create_memo_btn.setIcon(create_memo_icon(24, QColor(255, 255, 150)))  # Yellow for memo
        self._create_memo_btn.setIconSize(QSize(20, 20))
        self._create_memo_btn.setToolTip("Add memo pad (N)\nRight-click on image for more options")
        self._create_memo_btn.setShortcut("N")
        self._create_memo_btn.clicked.connect(self._on_create_memo)
        layout.addWidget(self._create_memo_btn)

        # Dose calculator button with icon
        self._dose_calc_btn = QToolButton()
        self._dose_calc_btn.setIcon(create_dose_icon(24, QColor(100, 200, 255)))  # Light blue for dose
        self._dose_calc_btn.setIconSize(QSize(20, 20))
        self._dose_calc_btn.setToolTip("Electron Dose Calculator (D)")
        self._dose_calc_btn.setShortcut("D")
        self._dose_calc_btn.clicked.connect(self._on_dose_calculator)
        layout.addWidget(self._dose_calc_btn)

        # Delete mode toggle button
        self._delete_mode_btn = QToolButton()
        self._delete_mode_btn.setIcon(create_delete_icon(24, QColor(255, 100, 100)))
        self._delete_mode_btn.setIconSize(QSize(20, 20))
        self._delete_mode_btn.setToolTip("Delete mode (X)\nClick on measurement/polygon to delete it")
        self._delete_mode_btn.setShortcut("X")
        self._delete_mode_btn.setCheckable(True)
        self._delete_mode_btn.toggled.connect(self._on_delete_mode_toggled)
        layout.addWidget(self._delete_mode_btn)

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

        # Measurement display label (shows both distance and area)
        self._distance_label = QLabel("--")
        self._distance_label.setMinimumWidth(180)
        self._distance_label.setStyleSheet("font-family: monospace; font-size: 12px;")
        layout.addWidget(self._distance_label)

        # Total polygon area display label
        self._total_area_label = QLabel("")
        self._total_area_label.setMinimumWidth(160)
        self._total_area_label.setStyleSheet("font-family: monospace; font-size: 12px; color: #4CAF50;")
        self._total_area_label.setToolTip("Total area of all polygons")
        self._total_area_label.setVisible(False)  # Hidden until we have polygons
        layout.addWidget(self._total_area_label)

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

        # Separator
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.VLine)
        sep3.setStyleSheet("color: #555;")
        layout.addWidget(sep3)

        # Show labels checkbox
        self._show_labels_cb = QCheckBox("Show Labels")
        self._show_labels_cb.setChecked(True)
        self._show_labels_cb.setToolTip("Show/hide floating distance labels\nDouble-click label to reset position")
        self._show_labels_cb.toggled.connect(self._on_toggle_labels)
        layout.addWidget(self._show_labels_cb)

        # Font size label
        font_label = QLabel("Size:")
        font_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(font_label)

        # Font size spinbox
        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(8, 32)
        self._font_size_spin.setValue(12)
        self._font_size_spin.setSuffix(" pt")
        self._font_size_spin.setToolTip("Label font size")
        self._font_size_spin.setFixedWidth(70)
        self._font_size_spin.valueChanged.connect(self._on_font_size_changed)
        layout.addWidget(self._font_size_spin)

        # Add stretch to push everything to the left
        layout.addStretch()

    def _on_create_measurement(self):
        """Handle create measurement button click."""
        self._measurement_count += 1
        self._count_label.setText(str(self._measurement_count))
        self.create_measurement.emit()

    def _on_create_polygon(self):
        """Handle create polygon button click."""
        self._measurement_count += 1
        self._count_label.setText(str(self._measurement_count))
        self.create_polygon.emit()

    def _on_create_pipette(self):
        """Handle create pipette button click."""
        # Don't increment count here - it will be incremented when polygon is created
        self.create_pipette.emit()

    def _on_create_memo(self):
        """Handle create memo button click."""
        self.create_memo.emit()

    def _on_dose_calculator(self):
        """Handle dose calculator button click."""
        self.open_dose_calculator.emit()

    def _on_delete_mode_toggled(self, checked: bool):
        """Handle delete mode toggle."""
        self.delete_mode_changed.emit(checked)
        # Update button appearance when checked
        if checked:
            self._delete_mode_btn.setStyleSheet("""
                QToolButton {
                    background-color: #cc3333;
                    border: 2px solid #ff5555;
                }
            """)
        else:
            self._delete_mode_btn.setStyleSheet("")

    def is_delete_mode_active(self) -> bool:
        """Check if delete mode is currently active."""
        return self._delete_mode_btn.isChecked()

    def set_delete_mode(self, active: bool):
        """Set delete mode state."""
        self._delete_mode_btn.setChecked(active)

    def _on_clear_last(self):
        """Handle clear last button click."""
        if self._measurement_count > 0:
            self._measurement_count -= 1
            self._count_label.setText(str(self._measurement_count))
        self.clear_last.emit()

    def _on_clear_all(self):
        """Handle clear all button click."""
        self._distance_label.setText("--")
        self._measurement_count = 0
        self._count_label.setText("0")
        self.clear_all.emit()

    def _on_toggle_labels(self, checked: bool):
        """Handle show labels checkbox toggle."""
        self.toggle_labels.emit(checked)

    def _on_font_size_changed(self, size: int):
        """Handle font size spinbox change."""
        self.font_size_changed.emit(size)

    def set_measurement_count(self, count: int):
        """Update the measurement count display."""
        self._measurement_count = count
        self._count_label.setText(str(count))

    def update_distance(self, distance_px: float, distance_nm: float = None):
        """Update the distance display."""
        if distance_nm is not None:
            if distance_nm >= 1000:
                text = f"Dist: {distance_nm/1000:.3f} μm ({distance_px:.1f} px)"
            elif distance_nm >= 1:
                text = f"Dist: {distance_nm:.2f} nm ({distance_px:.1f} px)"
            else:
                text = f"Dist: {distance_nm:.3f} nm ({distance_px:.1f} px)"
        else:
            text = f"Dist: {distance_px:.1f} px"

        self._distance_label.setText(text)

    def update_area(self, area_px: float, area_nm2: float = None):
        """Update the area display for polygon measurements."""
        if area_nm2 is not None:
            if area_nm2 >= 1e6:
                text = f"Area: {area_nm2/1e6:.2f} μm² ({area_px:.0f} px²)"
            elif area_nm2 >= 1:
                text = f"Area: {area_nm2:.1f} nm² ({area_px:.0f} px²)"
            else:
                text = f"Area: {area_nm2:.3f} nm² ({area_px:.0f} px²)"
        else:
            text = f"Area: {area_px:.0f} px²"

        self._distance_label.setText(text)

    def update_total_polygon_area(self, area_px: float, area_nm2: float = None):
        """Update the total polygon area display."""
        # Hide label if no area (no polygons)
        if area_px <= 0:
            self._total_area_label.setVisible(False)
            return

        # Show label and format text
        self._total_area_label.setVisible(True)

        if area_nm2 is not None:
            if area_nm2 >= 1e6:
                text = f"Σ: {area_nm2/1e6:.2f} μm²"
            elif area_nm2 >= 1:
                text = f"Σ: {area_nm2:.1f} nm²"
            else:
                text = f"Σ: {area_nm2:.3f} nm²"
        else:
            text = f"Σ: {area_px:.0f} px²"

        self._total_area_label.setText(text)

    def clear_display(self):
        """Clear the measurement display."""
        self._distance_label.setText("--")
        self._total_area_label.setVisible(False)

    def clear_distance(self):
        """Clear the distance display (alias for clear_display)."""
        self.clear_display()

    def set_theme(self, is_dark: bool):
        """Update toolbar theme."""
        self._is_dark_mode = is_dark
        self._apply_theme()

    def _apply_theme(self):
        """Apply the current theme to the toolbar."""
        # Update icon color based on theme
        icon_color = QColor(200, 200, 200) if self._is_dark_mode else QColor(80, 80, 80)
        self._create_btn.setIcon(create_measurement_icon(24, icon_color))
        self._create_polygon_btn.setIcon(create_polygon_icon(24, icon_color))
        # Pipette icon uses cyan-green for visibility
        pipette_color = QColor(100, 255, 200) if self._is_dark_mode else QColor(0, 180, 120)
        self._create_pipette_btn.setIcon(create_pipette_icon(24, pipette_color))
        # Memo icon stays yellow/gold for sticky note appearance
        memo_color = QColor(255, 220, 100) if self._is_dark_mode else QColor(200, 170, 50)
        self._create_memo_btn.setIcon(create_memo_icon(24, memo_color))
        # Dose icon uses light blue / darker blue
        dose_color = QColor(100, 200, 255) if self._is_dark_mode else QColor(50, 120, 180)
        self._dose_calc_btn.setIcon(create_dose_icon(24, dose_color))

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
                QCheckBox {
                    color: #e0e0e0;
                    spacing: 5px;
                }
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                    border: 1px solid #555;
                    border-radius: 3px;
                    background-color: #3a3a3a;
                }
                QCheckBox::indicator:checked {
                    background-color: #0d7377;
                    border-color: #0d7377;
                }
                QCheckBox::indicator:hover {
                    border-color: #666;
                }
                QSpinBox {
                    background-color: #3a3a3a;
                    border: 1px solid #555;
                    border-radius: 3px;
                    padding: 2px 4px;
                    color: #e0e0e0;
                    font-size: 11px;
                }
                QSpinBox:hover {
                    border-color: #666;
                }
                QSpinBox::up-button, QSpinBox::down-button {
                    background-color: #454545;
                    border: none;
                    width: 16px;
                }
                QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                    background-color: #555;
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
                QCheckBox {
                    color: #333;
                    spacing: 5px;
                }
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                    border: 1px solid #bbb;
                    border-radius: 3px;
                    background-color: #e0e0e0;
                }
                QCheckBox::indicator:checked {
                    background-color: #14a085;
                    border-color: #14a085;
                }
                QCheckBox::indicator:hover {
                    border-color: #999;
                }
                QSpinBox {
                    background-color: #fff;
                    border: 1px solid #bbb;
                    border-radius: 3px;
                    padding: 2px 4px;
                    color: #333;
                    font-size: 11px;
                }
                QSpinBox:hover {
                    border-color: #999;
                }
                QSpinBox::up-button, QSpinBox::down-button {
                    background-color: #e0e0e0;
                    border: none;
                    width: 16px;
                }
                QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                    background-color: #d0d0d0;
                }
            """)
