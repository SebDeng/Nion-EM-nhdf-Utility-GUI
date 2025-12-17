"""
Electron dose calculator dialog.

Calculates electron dose and flux from probe current and scan parameters.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QDoubleSpinBox, QComboBox, QPushButton,
    QGroupBox, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from typing import Optional, Dict, Any
from src.core.nhdf_reader import NHDFData


class DoseCalculatorDialog(QDialog):
    """
    Dialog for calculating electron dose and flux.

    Shows scan parameters and allows user to input probe current
    to calculate dose in e⁻/nm² or e⁻/Å².
    """

    # Signal emitted when calculation is updated
    dose_calculated = Signal(dict)
    # Signal emitted when user wants to add result to panel
    add_to_panel = Signal(dict, bool)  # (dose_data, use_angstrom)

    # Default probe current in pA
    DEFAULT_PROBE_CURRENT = 15.0

    def __init__(self, data: Optional[NHDFData] = None, frame_index: int = 0, parent=None):
        super().__init__(parent)
        self._data = data
        self._frame_index = frame_index
        self._last_result: Optional[Dict[str, float]] = None

        self.setWindowTitle("Electron Dose Calculator")
        self.setMinimumWidth(400)

        self._setup_ui()
        self._update_display()

    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title
        title = QLabel("Electron Dose Calculator")
        title.setFont(QFont("sans-serif", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Scan Parameters Group
        params_group = QGroupBox("Scan Parameters (from metadata)")
        params_layout = QGridLayout(params_group)
        params_layout.setColumnStretch(1, 1)

        # Pixel size
        params_layout.addWidget(QLabel("Pixel Size:"), 0, 0)
        self._pixel_size_label = QLabel("--")
        self._pixel_size_label.setStyleSheet("font-family: monospace;")
        params_layout.addWidget(self._pixel_size_label, 0, 1)

        # Pixel time
        params_layout.addWidget(QLabel("Pixel Dwell Time:"), 1, 0)
        self._pixel_time_label = QLabel("--")
        self._pixel_time_label.setStyleSheet("font-family: monospace;")
        params_layout.addWidget(self._pixel_time_label, 1, 1)

        # FOV
        params_layout.addWidget(QLabel("Field of View:"), 2, 0)
        self._fov_label = QLabel("--")
        self._fov_label.setStyleSheet("font-family: monospace;")
        params_layout.addWidget(self._fov_label, 2, 1)

        # Image size
        params_layout.addWidget(QLabel("Image Size:"), 3, 0)
        self._image_size_label = QLabel("--")
        self._image_size_label.setStyleSheet("font-family: monospace;")
        params_layout.addWidget(self._image_size_label, 3, 1)

        layout.addWidget(params_group)

        # Input Group
        input_group = QGroupBox("Input")
        input_layout = QHBoxLayout(input_group)

        input_layout.addWidget(QLabel("Probe Current:"))
        self._probe_current_spin = QDoubleSpinBox()
        self._probe_current_spin.setRange(0.1, 10000.0)
        self._probe_current_spin.setValue(self.DEFAULT_PROBE_CURRENT)
        self._probe_current_spin.setSuffix(" pA")
        self._probe_current_spin.setDecimals(1)
        self._probe_current_spin.setFixedWidth(120)
        self._probe_current_spin.valueChanged.connect(self._on_calculate)
        input_layout.addWidget(self._probe_current_spin)

        input_layout.addStretch()

        # Unit selector
        input_layout.addWidget(QLabel("Display Units:"))
        self._unit_combo = QComboBox()
        self._unit_combo.addItems(["e⁻/nm²", "e⁻/Ų"])
        self._unit_combo.currentIndexChanged.connect(self._update_results_display)
        input_layout.addWidget(self._unit_combo)

        layout.addWidget(input_group)

        # Results Group - Dose and Flux
        results_group = QGroupBox("Dose & Flux")
        results_layout = QGridLayout(results_group)
        results_layout.setColumnStretch(1, 1)

        # Electrons per pixel
        results_layout.addWidget(QLabel("Electrons per Pixel:"), 0, 0)
        self._electrons_per_pixel_label = QLabel("--")
        self._electrons_per_pixel_label.setStyleSheet("font-family: monospace; font-weight: bold;")
        results_layout.addWidget(self._electrons_per_pixel_label, 0, 1)

        # Electron dose (per frame)
        results_layout.addWidget(QLabel("Electron Dose:"), 1, 0)
        self._dose_label = QLabel("--")
        self._dose_label.setStyleSheet("font-family: monospace; font-weight: bold; color: #4a9eff;")
        results_layout.addWidget(self._dose_label, 1, 1)

        # Electron dose (series) = dose × num_frames
        results_layout.addWidget(QLabel("Electron Dose (Series):"), 2, 0)
        self._dose_series_label = QLabel("--")
        self._dose_series_label.setStyleSheet("font-family: monospace; font-weight: bold; color: #ff6a9e;")
        results_layout.addWidget(self._dose_series_label, 2, 1)

        # Electron flux
        results_layout.addWidget(QLabel("Electron Flux:"), 3, 0)
        self._flux_label = QLabel("--")
        self._flux_label.setStyleSheet("font-family: monospace; font-weight: bold; color: #4aff9e;")
        results_layout.addWidget(self._flux_label, 3, 1)

        layout.addWidget(results_group)

        # Electron Counts Group
        counts_group = QGroupBox("Electron Counts")
        counts_layout = QGridLayout(counts_group)
        counts_layout.setColumnStretch(1, 1)

        # Electrons per frame
        counts_layout.addWidget(QLabel("Electrons per Frame:"), 0, 0)
        self._electrons_per_frame_label = QLabel("--")
        self._electrons_per_frame_label.setStyleSheet("font-family: monospace; font-weight: bold; color: #ffaa4a;")
        counts_layout.addWidget(self._electrons_per_frame_label, 0, 1)

        # Total electrons (series)
        counts_layout.addWidget(QLabel("Total Electrons (Series):"), 1, 0)
        self._total_electrons_label = QLabel("--")
        self._total_electrons_label.setStyleSheet("font-family: monospace; font-weight: bold; color: #ff6a9e;")
        counts_layout.addWidget(self._total_electrons_label, 1, 1)

        # Frame area
        counts_layout.addWidget(QLabel("Frame Area:"), 2, 0)
        self._frame_area_label = QLabel("--")
        self._frame_area_label.setStyleSheet("font-family: monospace;")
        counts_layout.addWidget(self._frame_area_label, 2, 1)

        # Number of frames (for context)
        counts_layout.addWidget(QLabel("Number of Frames:"), 3, 0)
        self._num_frames_label = QLabel("--")
        self._num_frames_label.setStyleSheet("font-family: monospace;")
        counts_layout.addWidget(self._num_frames_label, 3, 1)

        layout.addWidget(counts_group)

        # Formula info
        formula_frame = QFrame()
        formula_frame.setFrameStyle(QFrame.StyledPanel)
        formula_layout = QVBoxLayout(formula_frame)
        formula_layout.setContentsMargins(8, 8, 8, 8)

        formula_title = QLabel("Formulas:")
        formula_title.setStyleSheet("font-weight: bold;")
        formula_layout.addWidget(formula_title)

        formula_text = QLabel(
            "• Electrons/pixel = (Probe Current × Pixel Time) / e\n"
            "• Dose = Electrons/pixel / Pixel Area\n"
            "• Dose (Series) = Dose × Num Frames\n"
            "• Flux = Dose / Pixel Time\n"
            "• Electrons/frame = Electrons/pixel × Num Pixels\n"
            "• Total (Series) = Electrons/frame × Num Frames\n"
            "\n"
            "Where e = 1.602 × 10⁻¹⁹ C (electron charge)"
        )
        formula_text.setStyleSheet("font-size: 11px; color: #888;")
        formula_layout.addWidget(formula_text)

        layout.addWidget(formula_frame)

        # Buttons
        button_layout = QHBoxLayout()

        # Add to Panel button
        self._add_to_panel_btn = QPushButton("Add to Panel")
        self._add_to_panel_btn.setToolTip("Add dose result as floating label on the image panel")
        self._add_to_panel_btn.clicked.connect(self._on_add_to_panel)
        self._add_to_panel_btn.setEnabled(False)  # Disabled until calculation done
        button_layout.addWidget(self._add_to_panel_btn)

        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def set_data(self, data: Optional[NHDFData], frame_index: int = 0):
        """Set the data to calculate dose for."""
        self._data = data
        self._frame_index = frame_index
        self._update_display()

    def set_frame_index(self, frame_index: int):
        """Set the current frame index for per-frame FOV calculation."""
        self._frame_index = frame_index
        self._update_display()

    def _update_display(self):
        """Update the display with current data."""
        if self._data is None:
            self._pixel_size_label.setText("No data loaded")
            self._pixel_time_label.setText("--")
            self._fov_label.setText("--")
            self._image_size_label.setText("--")
            self._clear_results()
            return

        # Check for variable FOV
        has_variable_fov = hasattr(self._data, 'has_variable_fov') and self._data.has_variable_fov

        # Pixel size - use per-frame if variable FOV
        if has_variable_fov:
            pixel_size = self._data.get_frame_pixel_size_nm(self._frame_index)
            fov_nm = self._data.get_frame_fov_nm(self._frame_index)
        else:
            pixel_size = self._data.pixel_size_nm
            fov_nm = self._data.context_fov_nm

        if pixel_size is not None:
            self._pixel_size_label.setText(f"{pixel_size:.4f} nm ({pixel_size * 10:.3f} Å)")
        else:
            self._pixel_size_label.setText("Not available")

        # Pixel time
        pixel_time = self._data.pixel_time_us
        if pixel_time is not None:
            self._pixel_time_label.setText(f"{pixel_time:.2f} µs")
        else:
            self._pixel_time_label.setText("Not available")

        # FOV - use per-frame if variable FOV
        if has_variable_fov and fov_nm is not None:
            # Show per-frame FOV with frame indicator and warning
            fov_text = f"{fov_nm:.2f} nm (frame {self._frame_index})"
            # Add warning about variable FOV
            transitions = self._data.get_fov_transitions()
            if len(transitions) > 1:
                fov_text += " ⚠️ Variable FOV!"
            self._fov_label.setText(fov_text)
            self._fov_label.setToolTip(
                "This file has variable FOV during acquisition.\n"
                f"FOV transitions: {transitions}\n"
                "Dose calculation uses the current frame's FOV."
            )
        elif pixel_size is not None and self._data.is_2d_image:
            shape = self._data.frame_shape
            fov_x = pixel_size * shape[1]
            fov_y = pixel_size * shape[0]
            if abs(fov_x - fov_y) < 0.01:
                self._fov_label.setText(f"{fov_x:.2f} nm")
            else:
                self._fov_label.setText(f"{fov_x:.2f} × {fov_y:.2f} nm")
            self._fov_label.setToolTip("")
        else:
            actual_fov = self._data.actual_fov
            if actual_fov:
                self._fov_label.setText(f"{actual_fov[0]:.1f} × {actual_fov[1]:.1f} {actual_fov[2]}")
            else:
                self._fov_label.setText("Not available")
            self._fov_label.setToolTip("")

        # Image size
        if self._data.is_2d_image:
            shape = self._data.frame_shape
            self._image_size_label.setText(f"{shape[1]} × {shape[0]} pixels")
        else:
            self._image_size_label.setText("Not a 2D image")

        # Calculate dose
        self._on_calculate()

    def _on_calculate(self):
        """Calculate dose with current parameters."""
        if self._data is None:
            self._clear_results()
            return

        probe_current = self._probe_current_spin.value()
        result = self._data.calculate_electron_dose(probe_current, frame_index=self._frame_index)

        if result is None:
            self._clear_results()
            return

        self._last_result = result
        self._update_results_display()
        self._add_to_panel_btn.setEnabled(True)
        self.dose_calculated.emit(result)

    def _on_add_to_panel(self):
        """Handle add to panel button click."""
        if self._last_result:
            use_angstrom = self._unit_combo.currentIndex() == 1
            self.add_to_panel.emit(self._last_result, use_angstrom)

    def _update_results_display(self):
        """Update results labels with current unit selection."""
        if self._last_result is None:
            self._clear_results()
            return

        result = self._last_result
        use_angstrom = self._unit_combo.currentIndex() == 1

        # Electrons per pixel
        e_per_px = result['electrons_per_pixel']
        self._electrons_per_pixel_label.setText(f"{e_per_px:.2f} e⁻/pixel")

        # Dose (per frame)
        num_frames = result.get('num_frames', 1)
        if use_angstrom:
            dose = result['dose_e_per_A2']
            self._dose_label.setText(f"{dose:.4f} e⁻/Ų")
            dose_series = dose * num_frames
            self._dose_series_label.setText(f"{dose_series:.4f} e⁻/Ų ({num_frames} frames)")
        else:
            dose = result['dose_e_per_nm2']
            self._dose_label.setText(f"{dose:.2f} e⁻/nm²")
            dose_series = dose * num_frames
            self._dose_series_label.setText(f"{dose_series:.2e} e⁻/nm² ({num_frames} frames)")

        # Flux
        if use_angstrom:
            flux = result['flux_e_per_A2_s']
            self._flux_label.setText(f"{flux:.2e} e⁻/Ų/s")
        else:
            flux = result['flux_e_per_nm2_s']
            self._flux_label.setText(f"{flux:.2e} e⁻/nm²/s")

        # Electron counts
        e_per_frame = result.get('electrons_per_frame', 0)
        total_e = result.get('total_electrons_series', 0)
        # num_frames already defined above for dose_series calculation

        # Format electron counts with appropriate notation
        self._electrons_per_frame_label.setText(f"{e_per_frame:.3e} e⁻")

        # Format total electrons - highlight if multi-frame
        if num_frames > 1:
            self._total_electrons_label.setText(f"{total_e:.3e} e⁻ ({num_frames} frames)")
        else:
            self._total_electrons_label.setText(f"{total_e:.3e} e⁻ (single frame)")

        # Frame area
        if use_angstrom:
            frame_area = result.get('frame_area_A2', 0)
            self._frame_area_label.setText(f"{frame_area:.2e} Ų")
        else:
            frame_area = result.get('frame_area_nm2', 0)
            self._frame_area_label.setText(f"{frame_area:.2e} nm²")

        # Number of frames
        self._num_frames_label.setText(f"{num_frames}")

    def _clear_results(self):
        """Clear result labels."""
        self._electrons_per_pixel_label.setText("--")
        self._dose_label.setText("--")
        self._dose_series_label.setText("--")
        self._flux_label.setText("--")
        self._electrons_per_frame_label.setText("--")
        self._total_electrons_label.setText("--")
        self._frame_area_label.setText("--")
        self._num_frames_label.setText("--")
        self._last_result = None
        self._add_to_panel_btn.setEnabled(False)

    def get_probe_current(self) -> float:
        """Get the current probe current value."""
        return self._probe_current_spin.value()

    def set_probe_current(self, value: float):
        """Set the probe current value."""
        self._probe_current_spin.setValue(value)

    def get_last_result(self) -> Optional[Dict[str, float]]:
        """Get the last calculation result."""
        return self._last_result
