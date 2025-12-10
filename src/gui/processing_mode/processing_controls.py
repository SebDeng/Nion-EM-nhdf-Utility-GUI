"""
Control panel for image processing operations.
Provides sliders and controls for adjustments and filters.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QSlider, QPushButton, QSpinBox, QDoubleSpinBox,
    QCheckBox, QTabWidget, QScrollArea, QFrame, QGridLayout,
    QComboBox
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

        # Local Normalization control
        local_norm_group = QGroupBox("Local Normalization")
        local_norm_layout = QGridLayout(local_norm_group)
        local_norm_layout.setColumnStretch(2, 1)

        self.local_norm_check = QCheckBox("Enable")
        self.local_norm_check.setToolTip("Normalize intensity within local blocks to equalize contrast across the image")
        local_norm_layout.addWidget(self.local_norm_check, 0, 0, 1, 3)

        # Block size control
        local_norm_layout.addWidget(QLabel("Block size:"), 1, 0)
        self.local_norm_block_size = QSpinBox()
        self.local_norm_block_size.setRange(8, 256)
        self.local_norm_block_size.setValue(45)
        self.local_norm_block_size.setSingleStep(5)
        self.local_norm_block_size.setEnabled(False)
        self.local_norm_block_size.setSuffix(" px")
        self.local_norm_block_size.setMinimumWidth(80)
        self.local_norm_block_size.setToolTip("Size of blocks for local normalization (larger = smoother)")
        local_norm_layout.addWidget(self.local_norm_block_size, 1, 1)

        # Physical unit display for block size
        self.local_norm_nm_label = QLabel("= ? nm")
        self.local_norm_nm_label.setStyleSheet("QLabel { color: #888; }")
        self.local_norm_nm_label.setToolTip("Equivalent size in physical units")
        local_norm_layout.addWidget(self.local_norm_nm_label, 1, 2)

        # Connect signals
        self.local_norm_check.toggled.connect(self.local_norm_block_size.setEnabled)
        self.local_norm_check.toggled.connect(self._on_adjustment_changed)
        self.local_norm_block_size.valueChanged.connect(self._on_adjustment_changed)
        self.local_norm_block_size.valueChanged.connect(self._update_local_norm_nm_label)

        layout.addWidget(local_norm_group)

        layout.addStretch()

        return widget

    def _create_filters_tab(self) -> QWidget:
        """Create the filters tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Store pixel scale for unit conversion (will be set when data is loaded)
        self._pixel_scale_nm = None  # nm per pixel

        # Gaussian Blur
        gaussian_group = QGroupBox("Gaussian Blur")
        gaussian_layout = QGridLayout(gaussian_group)
        gaussian_layout.setColumnStretch(3, 1)  # Make fourth column stretch

        self.gaussian_check = QCheckBox("Enable")
        gaussian_layout.addWidget(self.gaussian_check, 0, 0, 1, 4)

        # Sigma in pixels
        gaussian_layout.addWidget(QLabel("Sigma:"), 1, 0)

        self.gaussian_sigma = QDoubleSpinBox()
        self.gaussian_sigma.setRange(0.1, 50.0)
        self.gaussian_sigma.setValue(1.0)
        self.gaussian_sigma.setSingleStep(0.5)
        self.gaussian_sigma.setDecimals(2)
        self.gaussian_sigma.setEnabled(False)
        self.gaussian_sigma.setSuffix(" px")
        self.gaussian_sigma.setMinimumWidth(90)
        self.gaussian_sigma.setToolTip("Gaussian kernel standard deviation in pixels")
        gaussian_layout.addWidget(self.gaussian_sigma, 1, 1)

        # Physical unit display (nm)
        self.gaussian_nm_label = QLabel("= ? nm")
        self.gaussian_nm_label.setStyleSheet("QLabel { color: #888; }")
        self.gaussian_nm_label.setToolTip("Equivalent size in physical units (based on image calibration)")
        gaussian_layout.addWidget(self.gaussian_nm_label, 1, 2, 1, 2)

        # Connect sigma change to update nm label
        self.gaussian_sigma.valueChanged.connect(self._update_gaussian_nm_label)

        layout.addWidget(gaussian_group)

        # Median Filter
        median_group = QGroupBox("Median Filter")
        median_layout = QGridLayout(median_group)
        median_layout.setColumnStretch(3, 1)

        self.median_check = QCheckBox("Enable")
        median_layout.addWidget(self.median_check, 0, 0, 1, 4)

        median_layout.addWidget(QLabel("Size:"), 1, 0)

        self.median_size = QSpinBox()
        self.median_size.setRange(3, 51)
        self.median_size.setValue(3)
        self.median_size.setSingleStep(2)  # Keep odd numbers
        self.median_size.setEnabled(False)
        self.median_size.setSuffix(" px")
        self.median_size.setMinimumWidth(80)
        self.median_size.setToolTip("Median filter kernel size in pixels (odd numbers)")
        median_layout.addWidget(self.median_size, 1, 1)

        # Physical unit display for median
        self.median_nm_label = QLabel("= ? nm")
        self.median_nm_label.setStyleSheet("QLabel { color: #888; }")
        self.median_nm_label.setToolTip("Equivalent size in physical units")
        median_layout.addWidget(self.median_nm_label, 1, 2, 1, 2)

        # Connect size change to update nm label
        self.median_size.valueChanged.connect(self._update_median_nm_label)

        layout.addWidget(median_group)

        # Unsharp Mask
        unsharp_group = QGroupBox("Unsharp Mask")
        unsharp_layout = QGridLayout(unsharp_group)
        unsharp_layout.setColumnStretch(3, 1)

        # Enable checkbox
        self.unsharp_check = QCheckBox("Enable")
        unsharp_layout.addWidget(self.unsharp_check, 0, 0, 1, 4)

        # Amount control (mask weight)
        unsharp_layout.addWidget(QLabel("Amount:"), 1, 0)

        self.unsharp_amount = QDoubleSpinBox()
        self.unsharp_amount.setRange(0.1, 5.0)
        self.unsharp_amount.setValue(0.5)
        self.unsharp_amount.setSingleStep(0.1)
        self.unsharp_amount.setEnabled(False)
        self.unsharp_amount.setMinimumWidth(80)
        self.unsharp_amount.setToolTip("Sharpening strength (mask weight)")
        unsharp_layout.addWidget(self.unsharp_amount, 1, 1, 1, 3)

        # Radius control (sigma)
        unsharp_layout.addWidget(QLabel("Radius:"), 2, 0)

        self.unsharp_radius = QDoubleSpinBox()
        self.unsharp_radius.setRange(0.1, 20.0)
        self.unsharp_radius.setValue(1.0)
        self.unsharp_radius.setSingleStep(0.5)
        self.unsharp_radius.setDecimals(2)
        self.unsharp_radius.setEnabled(False)
        self.unsharp_radius.setSuffix(" px")
        self.unsharp_radius.setMinimumWidth(90)
        self.unsharp_radius.setToolTip("Gaussian blur radius (sigma) in pixels")
        unsharp_layout.addWidget(self.unsharp_radius, 2, 1)

        # Physical unit display for unsharp radius
        self.unsharp_nm_label = QLabel("= ? nm")
        self.unsharp_nm_label.setStyleSheet("QLabel { color: #888; }")
        self.unsharp_nm_label.setToolTip("Equivalent size in physical units")
        unsharp_layout.addWidget(self.unsharp_nm_label, 2, 2, 1, 2)

        # Connect radius change to update nm label
        self.unsharp_radius.valueChanged.connect(self._update_unsharp_nm_label)

        layout.addWidget(unsharp_group)

        # Apply filters button
        self.apply_filters_btn = QPushButton("Apply Filters")
        self.apply_filters_btn.setMinimumWidth(100)
        self.apply_filters_btn.setEnabled(False)
        layout.addWidget(self.apply_filters_btn)

        layout.addStretch()

        return widget

    def _create_advanced_tab(self) -> QWidget:
        """Create the advanced processing tab with ImageJ-style filters."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Rolling Ball Background Subtraction (ImageJ-style)
        rolling_ball_group = QGroupBox("Rolling Ball Background Subtraction")
        rolling_ball_layout = QGridLayout(rolling_ball_group)
        rolling_ball_layout.setColumnStretch(2, 1)

        # Enable checkbox
        self.rolling_ball_check = QCheckBox("Enable")
        self.rolling_ball_check.setToolTip("Subtract background using ImageJ-style rolling ball algorithm")
        rolling_ball_layout.addWidget(self.rolling_ball_check, 0, 0, 1, 3)

        # Ball radius
        rolling_ball_layout.addWidget(QLabel("Radius:"), 1, 0)
        self.rolling_ball_radius = QSpinBox()
        self.rolling_ball_radius.setRange(1, 500)
        self.rolling_ball_radius.setValue(50)
        self.rolling_ball_radius.setEnabled(False)
        self.rolling_ball_radius.setToolTip("Rolling ball radius in pixels (larger = smoother background)")
        self.rolling_ball_radius.setSuffix(" px")
        self.rolling_ball_radius.setMinimumWidth(80)
        rolling_ball_layout.addWidget(self.rolling_ball_radius, 1, 1)

        # Physical unit display for radius
        self.rolling_ball_nm_label = QLabel("= ? nm")
        self.rolling_ball_nm_label.setStyleSheet("QLabel { color: #888; }")
        self.rolling_ball_nm_label.setToolTip("Equivalent size in physical units")
        rolling_ball_layout.addWidget(self.rolling_ball_nm_label, 1, 2)

        # Light background checkbox (for images with light background)
        self.rolling_ball_light_bg = QCheckBox("Light background")
        self.rolling_ball_light_bg.setChecked(False)
        self.rolling_ball_light_bg.setEnabled(False)
        self.rolling_ball_light_bg.setToolTip("Check if image has light background (inverts algorithm)")
        rolling_ball_layout.addWidget(self.rolling_ball_light_bg, 2, 0, 1, 3)

        # Create background only checkbox
        self.rolling_ball_create_bg = QCheckBox("Create background (don't subtract)")
        self.rolling_ball_create_bg.setChecked(False)
        self.rolling_ball_create_bg.setEnabled(False)
        self.rolling_ball_create_bg.setToolTip("Output the estimated background instead of subtracting it")
        rolling_ball_layout.addWidget(self.rolling_ball_create_bg, 3, 0, 1, 3)

        layout.addWidget(rolling_ball_group)

        # Connect signals for rolling ball
        self.rolling_ball_check.toggled.connect(self._on_rolling_ball_toggled)
        self.rolling_ball_check.toggled.connect(self._update_advanced_button)
        self.rolling_ball_radius.valueChanged.connect(self._on_advanced_changed)
        self.rolling_ball_radius.valueChanged.connect(self._update_rolling_ball_nm_label)
        self.rolling_ball_light_bg.toggled.connect(self._on_advanced_changed)
        self.rolling_ball_create_bg.toggled.connect(self._on_advanced_changed)

        # Bandpass Filter (ImageJ-style)
        bandpass_group = QGroupBox("FFT Bandpass Filter (ImageJ-style)")
        bandpass_layout = QGridLayout(bandpass_group)
        bandpass_layout.setColumnStretch(2, 1)

        # Enable checkbox
        self.bandpass_check = QCheckBox("Enable")
        self.bandpass_check.setToolTip("Apply ImageJ-style FFT bandpass filtering")
        bandpass_layout.addWidget(self.bandpass_check, 0, 0, 1, 3)

        # Filter large structures (high-pass cutoff)
        bandpass_layout.addWidget(QLabel("Filter large:"), 1, 0)
        self.bandpass_large = QSpinBox()
        self.bandpass_large.setRange(0, 1000)
        self.bandpass_large.setValue(40)
        self.bandpass_large.setEnabled(False)
        self.bandpass_large.setToolTip("Filter large structures down to X pixels (0 = off)")
        self.bandpass_large.setSuffix(" px")
        self.bandpass_large.setMinimumWidth(80)
        bandpass_layout.addWidget(self.bandpass_large, 1, 1, 1, 2)

        # Filter small structures (low-pass cutoff)
        bandpass_layout.addWidget(QLabel("Filter small:"), 2, 0)
        self.bandpass_small = QSpinBox()
        self.bandpass_small.setRange(0, 100)
        self.bandpass_small.setValue(3)
        self.bandpass_small.setEnabled(False)
        self.bandpass_small.setToolTip("Filter small structures up to X pixels (0 = off)")
        self.bandpass_small.setSuffix(" px")
        self.bandpass_small.setMinimumWidth(80)
        bandpass_layout.addWidget(self.bandpass_small, 2, 1, 1, 2)

        # Suppress stripes
        bandpass_layout.addWidget(QLabel("Suppress stripes:"), 3, 0)
        self.bandpass_stripes = QComboBox()
        self.bandpass_stripes.addItems(["None", "Horizontal", "Vertical"])
        self.bandpass_stripes.setEnabled(False)
        self.bandpass_stripes.setToolTip("Suppress horizontal or vertical stripes")
        self.bandpass_stripes.setMinimumWidth(80)
        bandpass_layout.addWidget(self.bandpass_stripes, 3, 1, 1, 2)

        # Tolerance for stripe suppression
        bandpass_layout.addWidget(QLabel("Tolerance:"), 4, 0)
        self.bandpass_tolerance = QSpinBox()
        self.bandpass_tolerance.setRange(1, 20)
        self.bandpass_tolerance.setValue(5)
        self.bandpass_tolerance.setEnabled(False)
        self.bandpass_tolerance.setToolTip("Direction tolerance for stripe suppression (%)")
        self.bandpass_tolerance.setSuffix(" %")
        self.bandpass_tolerance.setMinimumWidth(80)
        bandpass_layout.addWidget(self.bandpass_tolerance, 4, 1, 1, 2)

        # Autoscale checkbox
        self.bandpass_autoscale = QCheckBox("Autoscale after filtering")
        self.bandpass_autoscale.setChecked(True)
        self.bandpass_autoscale.setEnabled(False)
        self.bandpass_autoscale.setToolTip("Automatically scale output to original range")
        bandpass_layout.addWidget(self.bandpass_autoscale, 5, 0, 1, 3)

        # Saturate checkbox
        self.bandpass_saturate = QCheckBox("Saturate when autoscaling")
        self.bandpass_saturate.setChecked(False)
        self.bandpass_saturate.setEnabled(False)
        self.bandpass_saturate.setToolTip("Clip values to original min/max range")
        bandpass_layout.addWidget(self.bandpass_saturate, 6, 0, 1, 3)

        layout.addWidget(bandpass_group)

        # Connect signals
        self.bandpass_check.toggled.connect(self._on_bandpass_toggled)
        self.bandpass_check.toggled.connect(self._update_advanced_button)

        # Live update for bandpass when values change
        self.bandpass_large.valueChanged.connect(self._on_advanced_changed)
        self.bandpass_small.valueChanged.connect(self._on_advanced_changed)
        self.bandpass_stripes.currentIndexChanged.connect(self._on_advanced_changed)
        self.bandpass_tolerance.valueChanged.connect(self._on_advanced_changed)
        self.bandpass_autoscale.toggled.connect(self._on_advanced_changed)
        self.bandpass_saturate.toggled.connect(self._on_advanced_changed)

        # Apply advanced button
        self.apply_advanced_btn = QPushButton("Apply Advanced Filters")
        self.apply_advanced_btn.setMinimumWidth(100)
        self.apply_advanced_btn.setEnabled(False)
        self.apply_advanced_btn.clicked.connect(self._apply_advanced)
        layout.addWidget(self.apply_advanced_btn)

        layout.addStretch()

        return widget

    def _on_rolling_ball_toggled(self, enabled: bool):
        """Handle rolling ball enable/disable."""
        self.rolling_ball_radius.setEnabled(enabled)
        self.rolling_ball_light_bg.setEnabled(enabled)
        self.rolling_ball_create_bg.setEnabled(enabled)

    def _on_bandpass_toggled(self, enabled: bool):
        """Handle bandpass filter enable/disable."""
        self.bandpass_large.setEnabled(enabled)
        self.bandpass_small.setEnabled(enabled)
        self.bandpass_stripes.setEnabled(enabled)
        self.bandpass_tolerance.setEnabled(enabled)
        self.bandpass_autoscale.setEnabled(enabled)
        self.bandpass_saturate.setEnabled(enabled)

    def _update_advanced_button(self):
        """Update the state of the apply advanced button."""
        any_advanced_enabled = (
            self.rolling_ball_check.isChecked() or
            self.bandpass_check.isChecked()
        )
        self.apply_advanced_btn.setEnabled(any_advanced_enabled)

    def _on_advanced_changed(self):
        """Handle advanced filter changes with debouncing."""
        if self.bandpass_check.isChecked():
            self.update_timer.stop()
            self.update_timer.start(100)

    def _apply_advanced(self):
        """Apply advanced filters."""
        # Emit combined parameters with adjustment_changed to trigger processing
        self.adjustment_changed.emit(self.get_current_parameters())

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

        # Reset advanced filters (ImageJ-style bandpass)
        if hasattr(self, 'bandpass_check'):
            self.bandpass_check.setChecked(False)
            self.bandpass_large.setValue(40)
            self.bandpass_small.setValue(3)
            self.bandpass_stripes.setCurrentIndex(0)  # None
            self.bandpass_tolerance.setValue(5)
            self.bandpass_autoscale.setChecked(True)
            self.bandpass_saturate.setChecked(False)

        # Reset rolling ball background subtraction
        if hasattr(self, 'rolling_ball_check'):
            self.rolling_ball_check.setChecked(False)
            self.rolling_ball_radius.setValue(50)
            self.rolling_ball_light_bg.setChecked(False)
            self.rolling_ball_create_bg.setChecked(False)

        # Reset local normalization
        if hasattr(self, 'local_norm_check'):
            self.local_norm_check.setChecked(False)
            self.local_norm_block_size.setValue(45)

        # Emit reset signal to trigger processing reset
        self.reset_requested.emit()

    def get_current_parameters(self) -> Dict[str, Any]:
        """Get all current processing parameters directly from controls."""
        # Read directly from controls instead of cached dict to ensure up-to-date values
        params = {
            'brightness': self.brightness_value.value(),
            'contrast': self.contrast_value.value(),
            'gamma': self.gamma_value.value()
        }

        # Add filter parameters if enabled
        if self.gaussian_check.isChecked():
            params['gaussian_enabled'] = True
            params['gaussian_sigma'] = self.gaussian_sigma.value()

        if self.median_check.isChecked():
            params['median_enabled'] = True
            params['median_size'] = self.median_size.value()

        if self.unsharp_check.isChecked():
            params['unsharp_enabled'] = True
            params['unsharp_amount'] = self.unsharp_amount.value()
            params['unsharp_radius'] = self.unsharp_radius.value()

        # Add advanced filter parameters if enabled (ImageJ-style bandpass)
        if hasattr(self, 'bandpass_check') and self.bandpass_check.isChecked():
            params['bandpass_enabled'] = True
            params['bandpass_large'] = self.bandpass_large.value()
            params['bandpass_small'] = self.bandpass_small.value()
            params['bandpass_suppress_stripes'] = self.bandpass_stripes.currentText()
            params['bandpass_tolerance'] = self.bandpass_tolerance.value()
            params['bandpass_autoscale'] = self.bandpass_autoscale.isChecked()
            params['bandpass_saturate'] = self.bandpass_saturate.isChecked()

        # Add rolling ball background subtraction parameters
        if hasattr(self, 'rolling_ball_check') and self.rolling_ball_check.isChecked():
            params['rolling_ball_enabled'] = True
            params['rolling_ball_radius'] = self.rolling_ball_radius.value()
            params['rolling_ball_light_bg'] = self.rolling_ball_light_bg.isChecked()
            params['rolling_ball_create_bg'] = self.rolling_ball_create_bg.isChecked()

        # Add local normalization parameters
        if hasattr(self, 'local_norm_check') and self.local_norm_check.isChecked():
            params['local_norm_enabled'] = True
            params['local_norm_block_size'] = self.local_norm_block_size.value()

        return params

    def set_pixel_scale(self, scale_nm: float, unit: str = "nm"):
        """
        Set the pixel scale for physical unit conversion.

        Args:
            scale_nm: Scale in nm per pixel (or other unit per pixel)
            unit: Unit string (default "nm")
        """
        self._pixel_scale_nm = scale_nm
        self._pixel_unit = unit

        # Update all nm labels
        self._update_gaussian_nm_label()
        self._update_median_nm_label()
        self._update_unsharp_nm_label()
        self._update_bandpass_nm_labels()
        self._update_rolling_ball_nm_label()
        self._update_local_norm_nm_label()

    def _format_physical_value(self, pixels: float) -> str:
        """Format a pixel value as physical units."""
        if self._pixel_scale_nm is None:
            return "= ? nm"

        physical = pixels * self._pixel_scale_nm
        unit = getattr(self, '_pixel_unit', 'nm')

        # Use appropriate precision based on magnitude
        if physical >= 100:
            return f"= {physical:.1f} {unit}"
        elif physical >= 10:
            return f"= {physical:.2f} {unit}"
        elif physical >= 1:
            return f"= {physical:.3f} {unit}"
        else:
            return f"= {physical:.4f} {unit}"

    def _update_gaussian_nm_label(self):
        """Update the Gaussian sigma nm label."""
        if hasattr(self, 'gaussian_nm_label'):
            self.gaussian_nm_label.setText(
                self._format_physical_value(self.gaussian_sigma.value())
            )

    def _update_median_nm_label(self):
        """Update the Median size nm label."""
        if hasattr(self, 'median_nm_label'):
            self.median_nm_label.setText(
                self._format_physical_value(self.median_size.value())
            )

    def _update_unsharp_nm_label(self):
        """Update the Unsharp radius nm label."""
        if hasattr(self, 'unsharp_nm_label'):
            self.unsharp_nm_label.setText(
                self._format_physical_value(self.unsharp_radius.value())
            )

    def _update_bandpass_nm_labels(self):
        """Update bandpass filter nm labels (for filter_large and filter_small)."""
        # Bandpass uses pixel sizes, so we can show physical equivalents
        if hasattr(self, 'bandpass_large'):
            # These are already in pixels, convert to physical units
            pass  # Bandpass filter sizes are structure sizes, not kernel sizes

    def _update_rolling_ball_nm_label(self):
        """Update the Rolling Ball radius nm label."""
        if hasattr(self, 'rolling_ball_nm_label'):
            self.rolling_ball_nm_label.setText(
                self._format_physical_value(self.rolling_ball_radius.value())
            )

    def _update_local_norm_nm_label(self):
        """Update the Local Normalization block size nm label."""
        if hasattr(self, 'local_norm_nm_label'):
            self.local_norm_nm_label.setText(
                self._format_physical_value(self.local_norm_block_size.value())
            )