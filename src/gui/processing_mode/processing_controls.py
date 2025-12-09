"""
Control panel for image processing operations.
Provides sliders and controls for adjustments and filters.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QSlider, QPushButton, QSpinBox, QDoubleSpinBox,
    QCheckBox, QTabWidget, QScrollArea, QFrame, QGridLayout
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from typing import Dict, Any


class ProcessingControlsPanel(QWidget):
    """
    Control panel with tabs for different processing operations.
    """

    # Signals
    adjustment_changed = Signal(dict)  # Emits adjustment parameters
    filter_applied = Signal(dict)  # Emits filter parameters
    snapshot_requested = Signal()  # Request snapshot creation
    reset_requested = Signal()  # Reset to original

    def __init__(self, parent=None):
        super().__init__(parent)

        # Debounce timer for live updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._emit_adjustments)
        self.update_timer.setSingleShot(True)

        # Current values
        self.current_adjustments = {
            'brightness': 0,
            'contrast': 1.0,
            'gamma': 1.0
        }
        self.current_filters = {}

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the control panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Header with title and action buttons
        header = QWidget()
        header.setMaximumHeight(35)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("Processing Controls")
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        title.setFont(font)
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Action buttons
        self.snapshot_btn = QPushButton("Create Snapshot")
        self.snapshot_btn.setMinimumWidth(120)
        self.snapshot_btn.setToolTip("Save current processing state")
        header_layout.addWidget(self.snapshot_btn)

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setMinimumWidth(70)
        self.reset_btn.setToolTip("Reset to original image")
        header_layout.addWidget(self.reset_btn)

        layout.addWidget(header)

        # Tab widget for different processing categories
        self.tabs = QTabWidget()

        # Basic Adjustments tab
        self.adjustments_tab = self._create_adjustments_tab()
        self.tabs.addTab(self.adjustments_tab, "Adjustments")

        # Filters tab
        self.filters_tab = self._create_filters_tab()
        self.tabs.addTab(self.filters_tab, "Filters")

        # Advanced tab (placeholder for future)
        self.advanced_tab = self._create_advanced_tab()
        self.tabs.addTab(self.advanced_tab, "Advanced")

        layout.addWidget(self.tabs)

        # Set minimum size for better usability
        self.setMinimumHeight(200)
        # Remove maximum height to allow resizing

    def _create_adjustments_tab(self) -> QWidget:
        """Create the basic adjustments tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)

        # Brightness control
        brightness_group = QGroupBox("Brightness")
        brightness_layout = QHBoxLayout(brightness_group)

        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setRange(-100, 100)
        self.brightness_slider.setValue(0)
        self.brightness_slider.setTickInterval(50)
        self.brightness_slider.setTickPosition(QSlider.TicksBelow)

        self.brightness_value = QSpinBox()
        self.brightness_value.setRange(-100, 100)
        self.brightness_value.setValue(0)
        self.brightness_value.setSuffix("")

        brightness_layout.addWidget(self.brightness_slider)
        brightness_layout.addWidget(self.brightness_value)

        layout.addWidget(brightness_group)

        # Contrast control
        contrast_group = QGroupBox("Contrast")
        contrast_layout = QHBoxLayout(contrast_group)

        self.contrast_slider = QSlider(Qt.Horizontal)
        self.contrast_slider.setRange(10, 300)  # 0.1 to 3.0
        self.contrast_slider.setValue(100)  # 1.0
        self.contrast_slider.setTickInterval(50)
        self.contrast_slider.setTickPosition(QSlider.TicksBelow)

        self.contrast_value = QDoubleSpinBox()
        self.contrast_value.setRange(0.1, 3.0)
        self.contrast_value.setValue(1.0)
        self.contrast_value.setSingleStep(0.1)
        self.contrast_value.setDecimals(1)

        contrast_layout.addWidget(self.contrast_slider)
        contrast_layout.addWidget(self.contrast_value)

        layout.addWidget(contrast_group)

        # Gamma control
        gamma_group = QGroupBox("Gamma")
        gamma_layout = QHBoxLayout(gamma_group)

        self.gamma_slider = QSlider(Qt.Horizontal)
        self.gamma_slider.setRange(10, 300)  # 0.1 to 3.0
        self.gamma_slider.setValue(100)  # 1.0
        self.gamma_slider.setTickInterval(50)
        self.gamma_slider.setTickPosition(QSlider.TicksBelow)

        self.gamma_value = QDoubleSpinBox()
        self.gamma_value.setRange(0.1, 3.0)
        self.gamma_value.setValue(1.0)
        self.gamma_value.setSingleStep(0.1)
        self.gamma_value.setDecimals(1)

        gamma_layout.addWidget(self.gamma_slider)
        gamma_layout.addWidget(self.gamma_value)

        layout.addWidget(gamma_group)

        layout.addStretch()

        return widget

    def _create_filters_tab(self) -> QWidget:
        """Create the filters tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Gaussian Blur
        gaussian_group = QGroupBox("Gaussian Blur")
        gaussian_layout = QGridLayout(gaussian_group)
        gaussian_layout.setColumnStretch(2, 1)  # Make third column stretch

        self.gaussian_check = QCheckBox("Enable")
        gaussian_layout.addWidget(self.gaussian_check, 0, 0)

        gaussian_layout.addWidget(QLabel("Sigma:"), 0, 1)

        self.gaussian_sigma = QDoubleSpinBox()
        self.gaussian_sigma.setRange(0.1, 10.0)
        self.gaussian_sigma.setValue(1.0)
        self.gaussian_sigma.setSingleStep(0.5)
        self.gaussian_sigma.setEnabled(False)
        self.gaussian_sigma.setMinimumWidth(80)

        gaussian_layout.addWidget(self.gaussian_sigma, 0, 2)

        layout.addWidget(gaussian_group)

        # Median Filter
        median_group = QGroupBox("Median Filter")
        median_layout = QGridLayout(median_group)
        median_layout.setColumnStretch(2, 1)

        self.median_check = QCheckBox("Enable")
        median_layout.addWidget(self.median_check, 0, 0)

        median_layout.addWidget(QLabel("Size:"), 0, 1)

        self.median_size = QSpinBox()
        self.median_size.setRange(3, 21)
        self.median_size.setValue(3)
        self.median_size.setSingleStep(2)  # Keep odd numbers
        self.median_size.setEnabled(False)
        self.median_size.setMinimumWidth(80)

        median_layout.addWidget(self.median_size, 0, 2)

        layout.addWidget(median_group)

        # Unsharp Mask
        unsharp_group = QGroupBox("Unsharp Mask")
        unsharp_layout = QGridLayout(unsharp_group)
        unsharp_layout.setColumnStretch(2, 1)

        # Enable checkbox
        self.unsharp_check = QCheckBox("Enable")
        unsharp_layout.addWidget(self.unsharp_check, 0, 0, 1, 3)

        # Amount control
        unsharp_layout.addWidget(QLabel("Amount:"), 1, 0)

        self.unsharp_amount = QDoubleSpinBox()
        self.unsharp_amount.setRange(0.1, 5.0)
        self.unsharp_amount.setValue(0.5)
        self.unsharp_amount.setSingleStep(0.1)
        self.unsharp_amount.setEnabled(False)
        self.unsharp_amount.setMinimumWidth(80)

        unsharp_layout.addWidget(self.unsharp_amount, 1, 1, 1, 2)

        # Radius control
        unsharp_layout.addWidget(QLabel("Radius:"), 2, 0)

        self.unsharp_radius = QDoubleSpinBox()
        self.unsharp_radius.setRange(0.1, 10.0)
        self.unsharp_radius.setValue(1.0)
        self.unsharp_radius.setSingleStep(0.5)
        self.unsharp_radius.setEnabled(False)
        self.unsharp_radius.setMinimumWidth(80)

        unsharp_layout.addWidget(self.unsharp_radius, 2, 1, 1, 2)

        layout.addWidget(unsharp_group)

        # Apply filters button
        self.apply_filters_btn = QPushButton("Apply Filters")
        self.apply_filters_btn.setMinimumWidth(100)
        self.apply_filters_btn.setEnabled(False)
        layout.addWidget(self.apply_filters_btn)

        layout.addStretch()

        return widget

    def _create_advanced_tab(self) -> QWidget:
        """Create the advanced processing tab (placeholder)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)

        placeholder = QLabel("Advanced processing options\ncoming soon...")
        placeholder.setAlignment(Qt.AlignCenter)
        placeholder.setStyleSheet("QLabel { color: #888; }")

        layout.addWidget(placeholder)

        return widget

    def _connect_signals(self):
        """Connect internal signals."""
        # Adjustments - connect sliders to spinboxes
        self.brightness_slider.valueChanged.connect(self.brightness_value.setValue)
        self.brightness_value.valueChanged.connect(self.brightness_slider.setValue)

        self.contrast_slider.valueChanged.connect(
            lambda v: self.contrast_value.setValue(v / 100.0))
        self.contrast_value.valueChanged.connect(
            lambda v: self.contrast_slider.setValue(int(v * 100)))

        self.gamma_slider.valueChanged.connect(
            lambda v: self.gamma_value.setValue(v / 100.0))
        self.gamma_value.valueChanged.connect(
            lambda v: self.gamma_slider.setValue(int(v * 100)))

        # Live update for adjustments
        self.brightness_slider.valueChanged.connect(self._on_adjustment_changed)
        self.contrast_slider.valueChanged.connect(self._on_adjustment_changed)
        self.gamma_slider.valueChanged.connect(self._on_adjustment_changed)

        # Filter checkboxes
        self.gaussian_check.toggled.connect(self.gaussian_sigma.setEnabled)
        self.gaussian_check.toggled.connect(self._update_filter_button)

        self.median_check.toggled.connect(self.median_size.setEnabled)
        self.median_check.toggled.connect(self._update_filter_button)

        self.unsharp_check.toggled.connect(self.unsharp_amount.setEnabled)
        self.unsharp_check.toggled.connect(self.unsharp_radius.setEnabled)
        self.unsharp_check.toggled.connect(self._update_filter_button)

        # Apply filters button
        self.apply_filters_btn.clicked.connect(self._apply_filters)

        # Action buttons
        self.snapshot_btn.clicked.connect(self.snapshot_requested.emit)
        self.reset_btn.clicked.connect(self._reset_controls)

    def _on_adjustment_changed(self):
        """Handle adjustment changes with debouncing."""
        # Start/restart the timer for debounced updates
        self.update_timer.stop()
        self.update_timer.start(100)  # 100ms debounce

    def _emit_adjustments(self):
        """Emit current adjustment values."""
        self.current_adjustments = {
            'brightness': self.brightness_value.value(),
            'contrast': self.contrast_value.value(),
            'gamma': self.gamma_value.value()
        }
        self.adjustment_changed.emit(self.current_adjustments)

    def _apply_filters(self):
        """Apply selected filters."""
        filters = {}

        if self.gaussian_check.isChecked():
            filters['gaussian_sigma'] = self.gaussian_sigma.value()

        if self.median_check.isChecked():
            filters['median_size'] = self.median_size.value()

        if self.unsharp_check.isChecked():
            filters['unsharp_amount'] = self.unsharp_amount.value()
            filters['unsharp_radius'] = self.unsharp_radius.value()

        self.current_filters = filters
        self.filter_applied.emit(filters)

    def _update_filter_button(self):
        """Update the state of the apply filters button."""
        any_filter_enabled = (
            self.gaussian_check.isChecked() or
            self.median_check.isChecked() or
            self.unsharp_check.isChecked()
        )
        self.apply_filters_btn.setEnabled(any_filter_enabled)

    def _reset_controls(self):
        """Reset all controls to default values."""
        # Block signals to prevent cascading updates
        self.brightness_slider.blockSignals(True)
        self.contrast_slider.blockSignals(True)
        self.gamma_slider.blockSignals(True)
        self.brightness_value.blockSignals(True)
        self.contrast_value.blockSignals(True)
        self.gamma_value.blockSignals(True)

        # Reset adjustments
        self.brightness_slider.setValue(0)
        self.contrast_slider.setValue(100)
        self.gamma_slider.setValue(100)

        # Update value displays
        self.brightness_value.setValue(0)
        self.contrast_value.setValue(1.0)
        self.gamma_value.setValue(1.0)

        # Unblock signals
        self.brightness_slider.blockSignals(False)
        self.contrast_slider.blockSignals(False)
        self.gamma_slider.blockSignals(False)
        self.brightness_value.blockSignals(False)
        self.contrast_value.blockSignals(False)
        self.gamma_value.blockSignals(False)

        # Reset current adjustments dict
        self.current_adjustments = {
            'brightness': 0,
            'contrast': 1.0,
            'gamma': 1.0
        }

        # Reset filters
        self.gaussian_check.setChecked(False)
        self.median_check.setChecked(False)
        self.unsharp_check.setChecked(False)

    def get_current_parameters(self) -> Dict[str, Any]:
        """Get all current processing parameters."""
        params = self.current_adjustments.copy()
        params.update(self.current_filters)
        return params