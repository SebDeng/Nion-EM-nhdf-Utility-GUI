"""
Display panel for visualizing nhdf data with frame navigation.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QPushButton, QSpinBox, QComboBox, QFrame, QSizePolicy,
    QGroupBox, QDoubleSpinBox, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont

import numpy as np
from typing import Optional

import pyqtgraph as pg
from pyqtgraph import functions as fn
from matplotlib import colormaps as mpl_colormaps

from src.core.nhdf_reader import NHDFData
from src.gui.line_profile_overlay import LineProfileOverlay, LineProfileData


class ScaleBarItem(pg.GraphicsObject):
    """
    A scale bar overlay for the image display.
    Positioned at bottom-right, with high contrast (white bar + black outline).
    Includes a text label showing the scale value.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scale_per_pixel = 1.0  # units per pixel
        self._units = ""
        self._image_width = 100  # pixels
        self._image_height = 100  # pixels
        self._bar_length_pixels = 0
        self._bar_length_value = 0
        self._visible = True
        self._text = ""

    def set_scale(self, scale_per_pixel: float, units: str, image_width: int, image_height: int = None):
        """Set the scale information."""
        self._scale_per_pixel = abs(scale_per_pixel) if scale_per_pixel != 0 else 1.0
        self._units = units
        self._image_width = image_width
        self._image_height = image_height if image_height else image_width
        self._calculate_bar()
        self.update()

    def _calculate_bar(self):
        """Calculate appropriate scale bar length."""
        if self._scale_per_pixel == 0 or self._image_width == 0:
            self._bar_length_pixels = 0
            self._bar_length_value = 0
            self._text = ""
            return

        # Target bar length: ~15-25% of image width
        target_pixels = self._image_width * 0.2
        target_value = target_pixels * self._scale_per_pixel

        # Find a "nice" value (1, 2, 5, 10, 20, 50, etc.)
        nice_value = self._find_nice_value(target_value)

        self._bar_length_value = nice_value
        self._bar_length_pixels = nice_value / self._scale_per_pixel

        # Format the label
        if nice_value >= 1000:
            # Convert to larger unit if possible
            if self._units == "nm":
                self._text = f"{nice_value/1000:.4g} µm"
            elif self._units == "µm":
                self._text = f"{nice_value/1000:.4g} mm"
            else:
                self._text = f"{nice_value:.4g} {self._units}"
        elif nice_value < 0.01:
            self._text = f"{nice_value:.2e} {self._units}"
        else:
            self._text = f"{nice_value:.4g} {self._units}"

    def _find_nice_value(self, target: float) -> float:
        """Find a 'nice' round value close to target."""
        if target <= 0:
            return 1.0

        # Find the order of magnitude
        exponent = np.floor(np.log10(target))
        base = 10 ** exponent

        # Nice values: 1, 2, 5, 10
        nice_factors = [1, 2, 5, 10]
        nice_values = [f * base for f in nice_factors]

        # Find closest nice value
        best = nice_values[0]
        best_diff = abs(target - best)
        for v in nice_values[1:]:
            diff = abs(target - v)
            if diff < best_diff:
                best = v
                best_diff = diff

        return best

    def boundingRect(self):
        """Return bounding rectangle in data coordinates."""
        return pg.QtCore.QRectF(0, 0, self._image_width, self._image_height)

    def paint(self, painter, option, widget):
        """Paint the scale bar with label."""
        if not self._visible or self._bar_length_pixels <= 0 or not self._text:
            return

        # Save painter state
        painter.save()

        # Margins as percentage of image size
        margin_x = self._image_width * 0.03  # 3% margin from right
        margin_y = self._image_height * 0.05  # 5% margin from bottom

        # Bar dimensions in data coordinates (pixels)
        bar_thickness = max(self._image_height * 0.015, 5)  # 1.5% of height, min 5 pixels

        # Position at bottom-right (note: in image coords, Y=0 is top, Y=height is bottom)
        # But pyqtgraph flips the image, so we need to position near Y=0 for bottom
        bar_x_end = self._image_width - margin_x
        bar_x_start = bar_x_end - self._bar_length_pixels
        bar_y = margin_y  # Near the bottom (which is low Y values after flip)

        # Draw black background/outline for the bar (thicker)
        painter.setPen(pg.QtCore.Qt.NoPen)
        painter.setBrush(pg.mkBrush(color=(0, 0, 0, 200)))
        outline_rect = pg.QtCore.QRectF(
            bar_x_start - bar_thickness * 0.5,
            bar_y - bar_thickness,
            self._bar_length_pixels + bar_thickness,
            bar_thickness * 2
        )
        painter.drawRect(outline_rect)

        # Draw white bar (filled rectangle for better visibility)
        painter.setBrush(pg.mkBrush(color='w'))
        bar_rect = pg.QtCore.QRectF(
            bar_x_start,
            bar_y - bar_thickness / 2,
            self._bar_length_pixels,
            bar_thickness
        )
        painter.drawRect(bar_rect)

        # Draw text label above the bar
        # We need to flip the text since the coordinate system is flipped
        font = painter.font()
        font_size = max(int(self._image_height * 0.035), 10)  # 3.5% of height, min 10
        font.setPixelSize(font_size)
        font.setBold(True)
        painter.setFont(font)

        # Calculate text center position
        text_center_x = (bar_x_start + bar_x_end) / 2
        text_center_y = bar_y + bar_thickness + font_size * 0.8

        # Apply transform to flip text right-side up
        painter.translate(text_center_x, text_center_y)
        painter.scale(1, -1)  # Flip vertically to correct text orientation

        # Text rect centered at origin after transform
        text_width = self._bar_length_pixels * 1.5
        text_height = font_size * 1.5
        text_rect = pg.QtCore.QRectF(
            -text_width / 2,
            -text_height / 2,
            text_width,
            text_height
        )

        # Draw text shadow/outline (black)
        painter.setPen(pg.mkPen(color=(0, 0, 0, 200), width=3))
        for dx, dy in [(-1, -1), (-1, 1), (1, -1), (1, 1), (0, -1), (0, 1), (-1, 0), (1, 0)]:
            offset_rect = text_rect.translated(dx, dy)
            painter.drawText(offset_rect, pg.QtCore.Qt.AlignCenter, self._text)

        # Draw text (white)
        painter.setPen(pg.mkPen(color='w'))
        painter.drawText(text_rect, pg.QtCore.Qt.AlignCenter, self._text)

        # Restore painter state
        painter.restore()

    def setVisible(self, visible: bool):
        """Set visibility."""
        self._visible = visible
        self.update()


class SubscanAreaOverlay(pg.GraphicsObject):
    """
    An overlay that shows the typical subscan area on a full context scan.
    Draws a centered rectangle indicating where subscans would be taken.
    Only shown for full context images (not subscans themselves).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image_width = 100  # pixels
        self._image_height = 100  # pixels
        self._subscan_ratio = 0.25  # Default: subscan is 25% of context
        self._visible = False
        self._is_context_scan = False  # Only show for context scans (not subscans)

    def set_geometry(self, image_width: int, image_height: int,
                     subscan_ratio: float = 0.25, is_context_scan: bool = False):
        """
        Set the overlay geometry.

        Args:
            image_width: Width of the image in pixels
            image_height: Height of the image in pixels
            subscan_ratio: Ratio of subscan size to context size (0.0-1.0)
            is_context_scan: True if this is a full context scan (not a subscan)
        """
        self._image_width = image_width
        self._image_height = image_height
        self._subscan_ratio = max(0.05, min(0.95, subscan_ratio))  # Clamp to valid range
        self._is_context_scan = is_context_scan
        self.update()

    def boundingRect(self):
        """Return bounding rectangle in data coordinates."""
        return pg.QtCore.QRectF(0, 0, self._image_width, self._image_height)

    def paint(self, painter, option, widget):
        """Paint the subscan area rectangle."""
        if not self._visible or not self._is_context_scan:
            return

        # Save painter state
        painter.save()

        # Calculate subscan rectangle (centered)
        subscan_width = self._image_width * self._subscan_ratio
        subscan_height = self._image_height * self._subscan_ratio

        # Center position
        center_x = self._image_width / 2
        center_y = self._image_height / 2

        rect_x = center_x - subscan_width / 2
        rect_y = center_y - subscan_height / 2

        # Draw the subscan area rectangle
        # Orange/yellow color to make it visible
        pen_color = pg.mkColor(255, 165, 0, 200)  # Orange with some transparency
        fill_color = pg.mkColor(255, 165, 0, 30)  # Very transparent fill

        # Draw filled rectangle with semi-transparent fill
        painter.setBrush(pg.mkBrush(fill_color))
        painter.setPen(pg.mkPen(pen_color, width=2, style=pg.QtCore.Qt.DashLine))

        subscan_rect = pg.QtCore.QRectF(rect_x, rect_y, subscan_width, subscan_height)
        painter.drawRect(subscan_rect)

        # Draw corner markers for better visibility
        corner_size = min(subscan_width, subscan_height) * 0.1
        painter.setPen(pg.mkPen(pen_color, width=3))
        painter.setBrush(pg.QtCore.Qt.NoBrush)

        # Top-left corner
        painter.drawLine(pg.QtCore.QPointF(rect_x, rect_y),
                        pg.QtCore.QPointF(rect_x + corner_size, rect_y))
        painter.drawLine(pg.QtCore.QPointF(rect_x, rect_y),
                        pg.QtCore.QPointF(rect_x, rect_y + corner_size))

        # Top-right corner
        painter.drawLine(pg.QtCore.QPointF(rect_x + subscan_width, rect_y),
                        pg.QtCore.QPointF(rect_x + subscan_width - corner_size, rect_y))
        painter.drawLine(pg.QtCore.QPointF(rect_x + subscan_width, rect_y),
                        pg.QtCore.QPointF(rect_x + subscan_width, rect_y + corner_size))

        # Bottom-left corner
        painter.drawLine(pg.QtCore.QPointF(rect_x, rect_y + subscan_height),
                        pg.QtCore.QPointF(rect_x + corner_size, rect_y + subscan_height))
        painter.drawLine(pg.QtCore.QPointF(rect_x, rect_y + subscan_height),
                        pg.QtCore.QPointF(rect_x, rect_y + subscan_height - corner_size))

        # Bottom-right corner
        painter.drawLine(pg.QtCore.QPointF(rect_x + subscan_width, rect_y + subscan_height),
                        pg.QtCore.QPointF(rect_x + subscan_width - corner_size, rect_y + subscan_height))
        painter.drawLine(pg.QtCore.QPointF(rect_x + subscan_width, rect_y + subscan_height),
                        pg.QtCore.QPointF(rect_x + subscan_width, rect_y + subscan_height - corner_size))

        # Draw label "Subscan Area" at the top edge of the rectangle
        font = painter.font()
        # Font size proportional to subscan area, not full image
        font_size = max(int(subscan_height * 0.08), 8)  # 8% of subscan height, min 8px
        font_size = min(font_size, int(subscan_width * 0.15))  # Cap at 15% of width
        font.setPixelSize(font_size)
        font.setBold(True)
        painter.setFont(font)

        # Position label at the top edge of the rectangle (just above it)
        label_x = rect_x + subscan_width / 2  # Center horizontally
        label_y = rect_y + subscan_height + font_size * 0.3  # Just above top edge

        # Transform for text (flip to correct orientation)
        painter.translate(label_x, label_y)
        painter.scale(1, -1)

        # Draw text with shadow - compact text rect
        text = "Subscan Area"
        text_rect = pg.QtCore.QRectF(-subscan_width * 0.6, -font_size * 0.6,
                                      subscan_width * 1.2, font_size * 1.2)

        # Shadow (thinner for smaller text)
        painter.setPen(pg.mkPen(color=(0, 0, 0, 200), width=1))
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            painter.drawText(text_rect.translated(dx, dy), pg.QtCore.Qt.AlignCenter, text)

        # Text in bright yellow for visibility
        yellow_color = pg.mkColor(255, 255, 0, 255)  # Bright yellow
        painter.setPen(pg.mkPen(yellow_color))
        painter.drawText(text_rect, pg.QtCore.Qt.AlignCenter, text)

        # Restore painter state
        painter.restore()

    def setVisible(self, visible: bool):
        """Set visibility."""
        self._visible = visible
        self.update()

    def is_available(self) -> bool:
        """Check if this overlay is available (i.e., the image is a context scan)."""
        return self._is_context_scan


def get_colormap(name: str) -> pg.ColorMap:
    """Get a colormap by name, supporting both pyqtgraph and matplotlib colormaps."""
    # Try pyqtgraph first
    try:
        return pg.colormap.get(name)
    except (FileNotFoundError, KeyError):
        pass

    # Fall back to matplotlib
    try:
        mpl_cmap = mpl_colormaps.get_cmap(name)
        # Convert matplotlib colormap to pyqtgraph
        colors = mpl_cmap(np.linspace(0, 1, 256))
        return pg.ColorMap(pos=np.linspace(0, 1, 256), color=(colors * 255).astype(np.uint8))
    except Exception:
        pass

    # Last resort: return viridis
    return pg.colormap.get('viridis')


class FrameControls(QWidget):
    """Widget for frame navigation controls."""

    frame_changed = Signal(int)
    play_state_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._num_frames = 1
        self._current_frame = 0
        self._is_playing = False
        self._play_timer = QTimer()
        self._play_timer.timeout.connect(self._on_play_tick)

        self._setup_ui()

    def _setup_ui(self):
        """Set up the frame control UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Frame label
        self._frame_label = QLabel("Frame:")
        layout.addWidget(self._frame_label)

        # Previous button
        self._prev_btn = QPushButton("<")
        self._prev_btn.setFixedWidth(30)
        self._prev_btn.setToolTip("Previous frame")
        self._prev_btn.clicked.connect(self._go_prev)
        layout.addWidget(self._prev_btn)

        # Frame slider
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(0)
        self._slider.setValue(0)
        self._slider.valueChanged.connect(self._on_slider_changed)
        self._slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self._slider, 1)

        # Next button
        self._next_btn = QPushButton(">")
        self._next_btn.setFixedWidth(30)
        self._next_btn.setToolTip("Next frame")
        self._next_btn.clicked.connect(self._go_next)
        layout.addWidget(self._next_btn)

        # Frame spinbox
        self._frame_spin = QSpinBox()
        self._frame_spin.setMinimum(1)
        self._frame_spin.setMaximum(1)
        self._frame_spin.setValue(1)
        self._frame_spin.setFixedWidth(70)
        self._frame_spin.valueChanged.connect(self._on_spin_changed)
        layout.addWidget(self._frame_spin)

        # Total frames label
        self._total_label = QLabel("/ 1")
        layout.addWidget(self._total_label)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # Play/Pause button
        self._play_btn = QPushButton("Play")
        self._play_btn.setFixedWidth(60)
        self._play_btn.setCheckable(True)
        self._play_btn.clicked.connect(self._on_play_clicked)
        layout.addWidget(self._play_btn)

        # Speed control
        layout.addWidget(QLabel("Speed:"))
        self._speed_combo = QComboBox()
        self._speed_combo.addItems(["0.5x", "1x", "2x", "5x", "10x"])
        self._speed_combo.setCurrentIndex(1)  # Default 1x
        self._speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        self._speed_combo.setFixedWidth(60)
        layout.addWidget(self._speed_combo)

        # Loop checkbox
        self._loop_check = QCheckBox("Loop")
        self._loop_check.setChecked(True)
        layout.addWidget(self._loop_check)

        self._update_enabled_state()

    def set_num_frames(self, num_frames: int):
        """Set the total number of frames."""
        self._num_frames = max(1, num_frames)
        self._slider.setMaximum(self._num_frames - 1)
        self._frame_spin.setMaximum(self._num_frames)
        self._total_label.setText(f"/ {self._num_frames}")
        self._update_enabled_state()

    def set_current_frame(self, frame: int):
        """Set the current frame index (0-based)."""
        frame = max(0, min(frame, self._num_frames - 1))
        if frame != self._current_frame:
            self._current_frame = frame
            self._slider.blockSignals(True)
            self._frame_spin.blockSignals(True)
            self._slider.setValue(frame)
            self._frame_spin.setValue(frame + 1)
            self._slider.blockSignals(False)
            self._frame_spin.blockSignals(False)
            self.frame_changed.emit(frame)

    def _update_enabled_state(self):
        """Update enabled state based on number of frames."""
        has_multiple = self._num_frames > 1
        self._slider.setEnabled(has_multiple)
        self._prev_btn.setEnabled(has_multiple)
        self._next_btn.setEnabled(has_multiple)
        self._frame_spin.setEnabled(has_multiple)
        self._play_btn.setEnabled(has_multiple)
        self._speed_combo.setEnabled(has_multiple)
        self._loop_check.setEnabled(has_multiple)

    def _on_slider_changed(self, value: int):
        """Handle slider value change."""
        self.set_current_frame(value)

    def _on_spin_changed(self, value: int):
        """Handle spinbox value change."""
        self.set_current_frame(value - 1)

    def _go_prev(self):
        """Go to previous frame."""
        if self._current_frame > 0:
            self.set_current_frame(self._current_frame - 1)
        elif self._loop_check.isChecked():
            self.set_current_frame(self._num_frames - 1)

    def _go_next(self):
        """Go to next frame."""
        if self._current_frame < self._num_frames - 1:
            self.set_current_frame(self._current_frame + 1)
        elif self._loop_check.isChecked():
            self.set_current_frame(0)

    def _on_play_clicked(self, checked: bool):
        """Handle play button click."""
        self._is_playing = checked
        self._play_btn.setText("Pause" if checked else "Play")

        if checked:
            self._start_playback()
        else:
            self._stop_playback()

        self.play_state_changed.emit(checked)

    def _start_playback(self):
        """Start automatic playback."""
        interval = self._get_play_interval()
        self._play_timer.start(interval)

    def _stop_playback(self):
        """Stop automatic playback."""
        self._play_timer.stop()

    def _on_play_tick(self):
        """Handle play timer tick."""
        if self._current_frame < self._num_frames - 1:
            self.set_current_frame(self._current_frame + 1)
        elif self._loop_check.isChecked():
            self.set_current_frame(0)
        else:
            self._play_btn.setChecked(False)
            self._on_play_clicked(False)

    def _on_speed_changed(self, index: int):
        """Handle speed combo change."""
        if self._is_playing:
            interval = self._get_play_interval()
            self._play_timer.setInterval(interval)

    def _get_play_interval(self) -> int:
        """Get playback interval in ms based on speed setting."""
        speed_map = {0: 200, 1: 100, 2: 50, 3: 20, 4: 10}  # 0.5x, 1x, 2x, 5x, 10x
        return speed_map.get(self._speed_combo.currentIndex(), 100)

    def stop_playback(self):
        """Stop playback if active."""
        if self._is_playing:
            self._play_btn.setChecked(False)
            self._on_play_clicked(False)


class DisplayPanel(QWidget):
    """Panel for displaying nhdf data with frame navigation."""

    frame_changed = Signal(int)
    line_profile_created = Signal(LineProfileData)  # Emitted when a line profile is created

    def __init__(self, parent=None, show_controls=True):
        super().__init__(parent)
        self._data: Optional[NHDFData] = None
        self._current_frame = 0
        self._show_controls = show_controls
        self._line_profile_overlay: Optional[LineProfileOverlay] = None

        self._setup_ui()

    def _setup_ui(self):
        """Set up the display panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Image display area using pyqtgraph
        self._graphics_widget = pg.GraphicsLayoutWidget()
        self._graphics_widget.setBackground('#1e1e1e')  # Default dark background

        # Create plot item for image display
        self._plot_item = self._graphics_widget.addPlot()
        self._plot_item.setAspectLocked(True)
        self._plot_item.hideAxis('left')
        self._plot_item.hideAxis('bottom')
        self._plot_item.getViewBox().setBackgroundColor('#1e1e1e')  # Set ViewBox background too

        # Image item
        self._image_item = pg.ImageItem()
        self._plot_item.addItem(self._image_item)

        # Scale bar
        self._scale_bar = ScaleBarItem()
        self._plot_item.addItem(self._scale_bar)

        # Subscan area overlay
        self._subscan_overlay = SubscanAreaOverlay()
        self._plot_item.addItem(self._subscan_overlay)

        # Line profile overlay
        self._line_profile_overlay = LineProfileOverlay(self._plot_item, self._image_item)
        self._line_profile_overlay.profile_created.connect(self.line_profile_created.emit)

        # Color bar
        self._colorbar = pg.ColorBarItem(
            values=(0, 1),
            colorMap=pg.colormap.get('viridis'),
            interactive=True,
            orientation='right'
        )
        self._colorbar.setImageItem(self._image_item)

        layout.addWidget(self._graphics_widget, 1)

        # Display controls bar (only if show_controls is True)
        if self._show_controls:
            controls_frame = QFrame()
            controls_frame.setFrameShape(QFrame.StyledPanel)
            controls_layout = QHBoxLayout(controls_frame)
            controls_layout.setContentsMargins(8, 4, 8, 4)
            controls_layout.setSpacing(12)

            # Colormap selector
            controls_layout.addWidget(QLabel("Colormap:"))
            self._colormap_combo = QComboBox()
            # Use matplotlib colormap names (more comprehensive)
            self._colormap_combo.addItems([
                'viridis', 'plasma', 'inferno', 'magma', 'cividis',
                'Greys', 'gray', 'hot', 'cool', 'jet', 'turbo',
                'Blues', 'Reds', 'Greens', 'copper'
            ])
            self._colormap_combo.currentTextChanged.connect(self._on_colormap_changed)
            self._colormap_combo.setFixedWidth(100)
            controls_layout.addWidget(self._colormap_combo)

            # Auto scale checkbox
            self._auto_scale_check = QCheckBox("Auto Scale")
            self._auto_scale_check.setChecked(True)
            self._auto_scale_check.toggled.connect(self._on_auto_scale_changed)
            controls_layout.addWidget(self._auto_scale_check)

            # Manual scale controls
            controls_layout.addWidget(QLabel("Min:"))
            self._min_spin = QDoubleSpinBox()
            self._min_spin.setRange(-1e10, 1e10)
            self._min_spin.setDecimals(2)
            self._min_spin.setEnabled(False)
            self._min_spin.valueChanged.connect(self._on_scale_changed)
            self._min_spin.setFixedWidth(100)
            controls_layout.addWidget(self._min_spin)

            controls_layout.addWidget(QLabel("Max:"))
            self._max_spin = QDoubleSpinBox()
            self._max_spin.setRange(-1e10, 1e10)
            self._max_spin.setDecimals(2)
            self._max_spin.setEnabled(False)
            self._max_spin.valueChanged.connect(self._on_scale_changed)
            self._max_spin.setFixedWidth(100)
            controls_layout.addWidget(self._max_spin)

            # Scale bar checkbox
            self._scalebar_check = QCheckBox("Scale Bar")
            self._scalebar_check.setChecked(True)
            self._scalebar_check.toggled.connect(self._on_scalebar_toggled)
            controls_layout.addWidget(self._scalebar_check)

            controls_layout.addStretch()

            # Data info label
            self._info_label = QLabel("")
            self._info_label.setStyleSheet("color: #888;")
            controls_layout.addWidget(self._info_label)

            layout.addWidget(controls_frame)
        else:
            # Still create the widgets but don't add them to layout
            # This ensures the unified control panel can access them
            self._colormap_combo = QComboBox()
            self._colormap_combo.addItems([
                'viridis', 'plasma', 'inferno', 'magma', 'cividis',
                'Greys', 'gray', 'hot', 'cool', 'jet', 'turbo',
                'Blues', 'Reds', 'Greens', 'copper'
            ])
            self._colormap_combo.currentTextChanged.connect(self._on_colormap_changed)

            self._auto_scale_check = QCheckBox("Auto Scale")
            self._auto_scale_check.setChecked(True)
            self._auto_scale_check.toggled.connect(self._on_auto_scale_changed)

            self._min_spin = QDoubleSpinBox()
            self._min_spin.setRange(-1e10, 1e10)
            self._min_spin.setDecimals(2)
            self._min_spin.setEnabled(False)
            self._min_spin.valueChanged.connect(self._on_scale_changed)

            self._max_spin = QDoubleSpinBox()
            self._max_spin.setRange(-1e10, 1e10)
            self._max_spin.setDecimals(2)
            self._max_spin.setEnabled(False)
            self._max_spin.valueChanged.connect(self._on_scale_changed)

            self._scalebar_check = QCheckBox("Scale Bar")
            self._scalebar_check.setChecked(True)
            self._scalebar_check.toggled.connect(self._on_scalebar_toggled)

            self._info_label = QLabel("")

        # Store current colormap
        self._current_cmap = get_colormap('viridis')

        # Frame controls (at bottom)
        # Always create frame controls but only add to layout if showing controls
        self._frame_controls = FrameControls()
        self._frame_controls.frame_changed.connect(self._on_frame_changed)

        # Only add to layout if showing controls
        if self._show_controls:
            layout.addWidget(self._frame_controls)
        else:
            # Hide the frame controls when not showing controls
            self._frame_controls.setVisible(False)

        # Placeholder for empty state
        self._show_placeholder()

    def _show_placeholder(self):
        """Show placeholder when no data is loaded."""
        if hasattr(self, '_info_label'):
            self._info_label.setText("No data loaded - Open an nhdf file to view")

    def set_data(self, data: NHDFData):
        """Set the data to display."""
        self._data = data
        self._current_frame = 0

        # Configure frame controls
        self._frame_controls.set_num_frames(data.num_frames)
        self._frame_controls.set_current_frame(0)

        # Set calibration on line profile overlay if available
        if self._line_profile_overlay and data.dimensional_calibrations:
            # Get the first spatial calibration (usually x-axis)
            # Skip sequence dimension if present
            spatial_cals = data.dimensional_calibrations
            if data.data_descriptor.is_sequence and len(spatial_cals) > 1:
                spatial_cals = spatial_cals[1:]  # Skip sequence dimension
            if spatial_cals:
                self._line_profile_overlay.calibration = spatial_cals[0]

        # Update display
        self._update_display()

    def _update_display(self):
        """Update the image display with current frame."""
        if self._data is None:
            return

        # Get current frame data
        frame_data = self._data.get_frame(self._current_frame)

        if self._data.is_2d_image:
            # Display as image
            self._image_item.setImage(frame_data.T)  # Transpose for correct orientation

            # Apply current colormap
            self._image_item.setLookupTable(self._current_cmap.getLookupTable(nPts=256))

            # Update scale
            if self._auto_scale_check.isChecked():
                self._auto_scale()
            else:
                self._apply_manual_scale()

            # Update scale bar
            self._update_scale_bar()

            # Update info
            self._update_info_label()

        elif self._data.is_1d_data:
            # TODO: Display as line plot
            if hasattr(self, '_info_label'):
                self._info_label.setText("1D data display not yet implemented")

        else:
            # Multi-dimensional data
            if hasattr(self, '_info_label'):
                self._info_label.setText(f"Data shape: {frame_data.shape}")

    def _auto_scale(self):
        """Auto-scale the display to data range."""
        if self._data is None:
            return

        frame_data = self._data.get_frame(self._current_frame)

        # Calculate percentile-based scaling for better visualization
        vmin = np.nanpercentile(frame_data, 1)
        vmax = np.nanpercentile(frame_data, 99)

        # Update spinboxes (without triggering events)
        self._min_spin.blockSignals(True)
        self._max_spin.blockSignals(True)
        self._min_spin.setValue(vmin)
        self._max_spin.setValue(vmax)
        self._min_spin.blockSignals(False)
        self._max_spin.blockSignals(False)

        # Apply levels
        self._image_item.setLevels([vmin, vmax])
        self._colorbar.setLevels((vmin, vmax))

    def _apply_manual_scale(self):
        """Apply manual scale values."""
        vmin = self._min_spin.value()
        vmax = self._max_spin.value()
        self._image_item.setLevels([vmin, vmax])
        self._colorbar.setLevels((vmin, vmax))

    def _update_info_label(self):
        """Update the info label with current data info."""
        if self._data is None or not hasattr(self, '_info_label'):
            return

        frame_data = self._data.get_frame(self._current_frame)
        info_parts = [
            f"Shape: {frame_data.shape}",
            f"Type: {frame_data.dtype}",
            f"Range: [{frame_data.min():.2g}, {frame_data.max():.2g}]"
        ]
        self._info_label.setText(" | ".join(info_parts))

    def _on_frame_changed(self, frame: int):
        """Handle frame change from controls."""
        self._current_frame = frame
        self._update_display()
        self.frame_changed.emit(frame)

    def _on_colormap_changed(self, name: str):
        """Handle colormap change."""
        self._current_cmap = get_colormap(name)
        self._image_item.setLookupTable(self._current_cmap.getLookupTable(nPts=256))
        self._colorbar.setColorMap(self._current_cmap)

    def _on_auto_scale_changed(self, checked: bool):
        """Handle auto scale toggle."""
        self._min_spin.setEnabled(not checked)
        self._max_spin.setEnabled(not checked)

        if checked:
            self._auto_scale()
        else:
            self._apply_manual_scale()

    def _on_scale_changed(self):
        """Handle manual scale value change."""
        if not self._auto_scale_check.isChecked():
            self._apply_manual_scale()

    def _on_scalebar_toggled(self, checked: bool):
        """Handle scale bar visibility toggle."""
        self._scale_bar.setVisible(checked)

    def _update_scale_bar(self):
        """Update the scale bar based on current data calibration."""
        if self._data is None or not self._data.is_2d_image:
            self._scale_bar.setVisible(False)
            return

        # Get spatial calibrations
        fov_info = self._data.actual_fov
        if fov_info is None:
            self._scale_bar.setVisible(False)
            return

        fov_y, fov_x, units = fov_info
        ny, nx = self._data.frame_shape

        # Calculate scale per pixel (use x dimension)
        scale_per_pixel = fov_x / nx if nx > 0 else 1.0

        # Update scale bar with both width and height
        self._scale_bar.set_scale(scale_per_pixel, units, nx, ny)
        self._scale_bar.setVisible(self._scalebar_check.isChecked())

        # Also update subscan overlay geometry when data changes
        self._update_subscan_overlay()

    def _update_subscan_overlay(self):
        """Update the subscan area overlay based on current data."""
        if self._data is None or not self._data.is_2d_image:
            self._subscan_overlay.set_geometry(100, 100, 0.125, False)
            return

        ny, nx = self._data.frame_shape

        # Check if this is a context scan (NOT a subscan)
        # A context scan is one where is_subscan is False
        is_context_scan = not self._data.is_subscan

        # Calculate the subscan ratio
        # For context scans: typical subscan is ~12.5% (10nm out of 80nm context)
        # Based on real data: subscans are typically 512 pixels out of 4096 context = 12.5%
        subscan_ratio = 0.125  # Default 12.5% (10nm / 80nm)

        # Try to get a more accurate ratio from metadata if available
        fov_info = self._data.actual_fov
        context_fov = self._data.context_fov_nm

        if fov_info and context_fov and context_fov > 0:
            actual_fov = fov_info[0]  # Use Y dimension FOV
            if is_context_scan:
                # This is a context scan, so actual_fov == context_fov
                # Use the typical subscan ratio of 12.5%
                subscan_ratio = 0.125
            else:
                # This is a subscan - we could calculate the ratio if needed
                # but we don't show the overlay for subscans anyway
                subscan_ratio = actual_fov / context_fov if context_fov > 0 else 0.125

        # Update the overlay geometry
        self._subscan_overlay.set_geometry(nx, ny, subscan_ratio, is_context_scan)

    def _on_subscan_overlay_toggled(self, checked: bool):
        """Handle subscan overlay visibility toggle."""
        self._subscan_overlay.setVisible(checked)

    def is_subscan_overlay_available(self) -> bool:
        """Check if the subscan overlay is available for the current data."""
        return self._subscan_overlay.is_available()

    def set_subscan_overlay_visible(self, visible: bool):
        """Set the visibility of the subscan overlay."""
        if self._subscan_overlay.is_available():
            self._subscan_overlay.setVisible(visible)

    def clear(self):
        """Clear the display."""
        self._data = None
        self._current_frame = 0
        self._image_item.clear()
        self._scale_bar.setVisible(False)
        self._subscan_overlay.setVisible(False)
        self._subscan_overlay.set_geometry(100, 100, 0.125, False)
        self._frame_controls.stop_playback()
        self._frame_controls.set_num_frames(1)
        self._show_placeholder()

    @property
    def current_frame(self) -> int:
        """Get the current frame index."""
        return self._current_frame

    @property
    def data(self) -> Optional[NHDFData]:
        """Get the current data."""
        return self._data

    def get_current_colormap(self) -> str:
        """Get the current colormap name."""
        return self._colormap_combo.currentText() if hasattr(self, '_colormap_combo') else "viridis"

    def get_display_range(self) -> tuple:
        """Get the current display range (min, max)."""
        if hasattr(self, '_min_spin') and hasattr(self, '_max_spin'):
            return (self._min_spin.value(), self._max_spin.value())
        return None

    def set_theme(self, is_dark: bool):
        """Set the display panel theme."""
        if is_dark:
            bg_color = '#1e1e1e'
            fg_color = '#d4d4d4'
        else:
            bg_color = '#ffffff'
            fg_color = '#000000'

        # Update graphics widget background
        if hasattr(self, '_graphics_widget'):
            self._graphics_widget.setBackground(bg_color)

        # Update plot item background
        if hasattr(self, '_plot_item'):
            self._plot_item.getViewBox().setBackgroundColor(bg_color)

            # Update axes colors if they are visible
            for axis in ['left', 'bottom', 'top', 'right']:
                axis_item = self._plot_item.getAxis(axis)
                if axis_item:
                    axis_item.setPen(fg_color)
                    axis_item.setTextPen(fg_color)

    def create_line_profile(self):
        """Create a default line profile that can be dragged."""
        if self._line_profile_overlay:
            self._line_profile_overlay.create_default_line()

    def clear_analysis_overlays(self):
        """Clear all analysis overlays."""
        if self._line_profile_overlay:
            self._line_profile_overlay.clear_all()
