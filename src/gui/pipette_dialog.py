"""
Pipette preview dialog for adjusting threshold before creating polygon.
Shows live preview of detected region with adjustable threshold.
"""

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QPushButton, QGroupBox, QDoubleSpinBox, QWidget
)
from PySide6.QtGui import QColor
import pyqtgraph as pg
import numpy as np
from typing import Optional, Tuple, List

from .pipette_detector import PipetteDetector, DetectionResult, get_threshold_range


class PipettePreviewDialog(QDialog):
    """
    Dialog for previewing and adjusting pipette polygon detection.
    Shows image with overlay of detected region and threshold slider.
    """

    # Signal emitted when user confirms polygon creation
    # Emits list of (x, y) vertex tuples
    polygon_confirmed = Signal(list)

    def __init__(
        self,
        image_data: np.ndarray,
        click_x: float,
        click_y: float,
        calibration=None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Pipette Region Detection")
        self.setMinimumSize(500, 600)

        # Store data
        self._image_data = image_data
        self._click_x = click_x
        self._click_y = click_y
        self._calibration = calibration
        self._detector = PipetteDetector()
        self._current_result: Optional[DetectionResult] = None

        # Get image range for threshold slider
        self._data_min, self._data_max = get_threshold_range(image_data)
        self._data_range = self._data_max - self._data_min

        # Debounce timer for slider updates (prevents lag during drag)
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._do_debounced_detection)
        self._pending_threshold = None

        # Setup UI
        self._setup_ui()

        # Perform initial detection
        self._do_initial_detection()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Preview area with pyqtgraph
        self._setup_preview_widget()
        layout.addWidget(self._preview_widget, stretch=1)

        # Controls group
        controls_group = QGroupBox("Detection Settings")
        controls_layout = QVBoxLayout(controls_group)

        # Threshold slider
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("Threshold:"))

        self._threshold_slider = QSlider(Qt.Horizontal)
        self._threshold_slider.setMinimum(0)
        self._threshold_slider.setMaximum(1000)  # Will map to actual range
        self._threshold_slider.setValue(150)  # 15% default
        self._threshold_slider.valueChanged.connect(self._on_threshold_changed)
        threshold_layout.addWidget(self._threshold_slider, stretch=1)

        self._threshold_value_label = QLabel("--")
        self._threshold_value_label.setMinimumWidth(80)
        threshold_layout.addWidget(self._threshold_value_label)

        controls_layout.addLayout(threshold_layout)

        # Tolerance spinbox (for fine adjustment)
        tolerance_layout = QHBoxLayout()
        tolerance_layout.addWidget(QLabel("Tolerance %:"))

        self._tolerance_spin = QDoubleSpinBox()
        self._tolerance_spin.setRange(1.0, 100.0)
        self._tolerance_spin.setValue(10.0)
        self._tolerance_spin.setSingleStep(1.0)
        self._tolerance_spin.setSuffix("%")
        self._tolerance_spin.valueChanged.connect(self._on_tolerance_changed)
        tolerance_layout.addWidget(self._tolerance_spin)

        tolerance_layout.addStretch()
        controls_layout.addLayout(tolerance_layout)

        layout.addWidget(controls_group)

        # Info display
        info_group = QGroupBox("Detection Info")
        info_layout = QVBoxLayout(info_group)

        self._info_label = QLabel("Click detected region info will appear here")
        self._info_label.setWordWrap(True)
        info_layout.addWidget(self._info_label)

        layout.addWidget(info_group)

        # Buttons
        button_layout = QHBoxLayout()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self._cancel_btn)

        button_layout.addStretch()

        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setDefault(True)
        self._apply_btn.clicked.connect(self._on_apply)
        button_layout.addWidget(self._apply_btn)

        layout.addLayout(button_layout)

    def _setup_preview_widget(self):
        """Setup pyqtgraph preview widget."""
        self._preview_widget = pg.GraphicsLayoutWidget()
        self._preview_widget.setBackground('k')

        # Create plot for image display
        self._plot = self._preview_widget.addPlot()
        self._plot.setAspectLocked(True)
        self._plot.hideAxis('left')
        self._plot.hideAxis('bottom')

        # Image item
        self._image_item = pg.ImageItem()
        self._plot.addItem(self._image_item)

        # Overlay for detected region (semi-transparent)
        self._overlay_item = pg.ImageItem()
        self._overlay_item.setZValue(10)
        self._overlay_item.setOpacity(0.5)
        self._plot.addItem(self._overlay_item)

        # Click point marker
        self._click_marker = pg.ScatterPlotItem(
            pos=[(self._click_x, self._click_y)],
            size=15,
            pen=pg.mkPen('w', width=2),
            brush=pg.mkBrush(255, 255, 0, 150),
            symbol='x'
        )
        self._click_marker.setZValue(20)
        self._plot.addItem(self._click_marker)

        # Display image
        display_data = self._image_data
        if len(display_data.shape) == 3:
            display_data = np.mean(display_data, axis=2)

        self._image_item.setImage(display_data.T)  # Transpose for pyqtgraph
        self._plot.autoRange()

    def _do_initial_detection(self):
        """Perform initial detection with default tolerance."""
        tolerance = self._tolerance_spin.value() / 100.0
        self._current_result = self._detector.detect_region(
            self._image_data,
            self._click_x,
            self._click_y,
            tolerance
        )

        self._update_display()

    def _on_threshold_changed(self, value: int):
        """Handle threshold slider change with debouncing."""
        # Map slider value (0-1000) to actual threshold
        fraction = value / 1000.0
        absolute_threshold = self._data_min + (self._data_range * fraction)

        # Update threshold label immediately
        self._threshold_value_label.setText(f"{absolute_threshold:.1f}")

        # Debounce the detection (wait 50ms after last change)
        self._pending_threshold = absolute_threshold
        self._debounce_timer.start(50)

    def _do_debounced_detection(self):
        """Perform detection after debounce delay."""
        if self._pending_threshold is None:
            return

        # Detect with absolute threshold
        self._current_result = self._detector.detect_with_threshold(
            self._image_data,
            self._click_x,
            self._click_y,
            self._pending_threshold
        )

        self._update_display()

    def _on_tolerance_changed(self, value: float):
        """Handle tolerance spinbox change."""
        tolerance = value / 100.0

        # Calculate and set slider position
        if self._current_result:
            clicked_value = self._current_result.clicked_value
        else:
            # Get clicked value directly
            img = self._image_data
            if len(img.shape) == 3:
                img = np.mean(img, axis=2)
            click_y = int(np.clip(self._click_y, 0, img.shape[0] - 1))
            click_x = int(np.clip(self._click_x, 0, img.shape[1] - 1))
            clicked_value = img[click_y, click_x]

        threshold = clicked_value + (self._data_range * tolerance)
        slider_value = int((threshold - self._data_min) / self._data_range * 1000)
        slider_value = max(0, min(1000, slider_value))

        # Block signals to prevent recursion
        self._threshold_slider.blockSignals(True)
        self._threshold_slider.setValue(slider_value)
        self._threshold_slider.blockSignals(False)

        # Update threshold label
        self._threshold_value_label.setText(f"{threshold:.1f}")

        # Detect with tolerance
        self._current_result = self._detector.detect_region(
            self._image_data,
            self._click_x,
            self._click_y,
            tolerance
        )

        self._update_display()

    def _update_display(self):
        """Update the preview display with current detection result."""
        if self._current_result is None:
            # No detection - clear overlay
            self._overlay_item.clear()
            self._info_label.setText("No region detected. Try adjusting the threshold.")
            self._apply_btn.setEnabled(False)
            return

        result = self._current_result

        # Get original image dimensions for scaling mask
        orig_img = self._image_data
        if len(orig_img.shape) == 3:
            orig_h, orig_w = orig_img.shape[:2]
        else:
            orig_h, orig_w = orig_img.shape

        # Create overlay at original image size
        overlay = np.zeros((orig_h, orig_w, 4), dtype=np.uint8)

        # Scale mask to original size if needed
        mask = result.mask
        mask_h, mask_w = mask.shape

        if mask_h != orig_h or mask_w != orig_w:
            # Mask is from downsampled image - scale it up
            from scipy.ndimage import zoom
            scale_h = orig_h / mask_h
            scale_w = orig_w / mask_w
            # Use nearest neighbor for binary mask
            mask = zoom(mask.astype(np.float32), (scale_h, scale_w), order=0) > 0.5

        # Cyan color for detected region
        overlay[mask, 0] = 0    # R
        overlay[mask, 1] = 255  # G
        overlay[mask, 2] = 255  # B
        overlay[mask, 3] = 128  # A (semi-transparent)

        # Transpose for pyqtgraph display
        self._overlay_item.setImage(overlay.transpose(1, 0, 2))

        # Update info
        area_px = result.area_px
        num_vertices = len(result.vertices)

        info_text = f"Area: {area_px:.0f} px\u00b2"

        # Add calibrated area if available
        if self._calibration and hasattr(self._calibration, 'scale'):
            area_nm2 = area_px * (self._calibration.scale ** 2)
            if area_nm2 >= 1e6:
                info_text += f" ({area_nm2/1e6:.2f} \u03bcm\u00b2)"
            else:
                info_text += f" ({area_nm2:.1f} nm\u00b2)"

        info_text += f"\nVertices: {num_vertices}"
        info_text += f"\nClicked intensity: {result.clicked_value:.1f}"
        info_text += f"\nThreshold: {result.threshold:.1f}"

        self._info_label.setText(info_text)
        self._apply_btn.setEnabled(True)

    def _on_apply(self):
        """Handle apply button - emit polygon vertices and close."""
        if self._current_result is None:
            self.reject()
            return

        # Emit vertices
        self.polygon_confirmed.emit(list(self._current_result.vertices))
        self.accept()

    def get_result(self) -> Optional[DetectionResult]:
        """Get the current detection result."""
        return self._current_result
