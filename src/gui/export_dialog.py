"""
Export dialog for configuring export settings.
"""

import pathlib
from typing import Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QGroupBox, QRadioButton, QButtonGroup, QFileDialog,
    QProgressBar, QMessageBox, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QThread

from src.core.nhdf_reader import NHDFData
from src.core.exporter import Exporter, ExportSettings


class ExportWorker(QThread):
    """Worker thread for export operation."""
    progress = Signal(int, int, str)  # current, total, message
    finished = Signal(object)  # result path or error
    error = Signal(str)

    def __init__(self, exporter: Exporter, settings: ExportSettings):
        super().__init__()
        self._exporter = exporter
        self._settings = settings

    def run(self):
        try:
            result_path = self._exporter.export(
                self._settings,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m)
            )
            self.finished.emit(result_path)
        except Exception as e:
            self.error.emit(str(e))


class ExportDialog(QDialog):
    """Dialog for configuring and executing export."""

    def __init__(self, data: NHDFData, parent=None,
                 current_colormap: str = "viridis",
                 display_range: tuple = None):
        super().__init__(parent)
        self._data = data
        self._current_colormap = current_colormap
        self._display_range = display_range or (0.0, 1.0)
        self._worker: Optional[ExportWorker] = None

        self._setup_ui()
        self._connect_signals()
        self._update_ui_state()

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Export Data")
        self.setMinimumWidth(500)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Output location
        location_group = QGroupBox("Output Location")
        location_layout = QGridLayout(location_group)

        location_layout.addWidget(QLabel("Directory:"), 0, 0)
        self._dir_edit = QLineEdit()
        self._dir_edit.setText(str(self._data.file_path.parent))
        location_layout.addWidget(self._dir_edit, 0, 1)
        self._browse_btn = QPushButton("Browse...")
        self._browse_btn.setFixedWidth(80)
        location_layout.addWidget(self._browse_btn, 0, 2)

        location_layout.addWidget(QLabel("Folder Name:"), 1, 0)
        self._folder_edit = QLineEdit()
        self._folder_edit.setText(self._data.file_path.stem)
        self._folder_edit.setPlaceholderText("Output folder name")
        location_layout.addWidget(self._folder_edit, 1, 1, 1, 2)

        layout.addWidget(location_group)

        # Image options
        image_group = QGroupBox("Image Export")
        image_layout = QGridLayout(image_group)

        # Export images checkbox
        self._export_images_check = QCheckBox("Export image(s)")
        self._export_images_check.setChecked(True)
        image_layout.addWidget(self._export_images_check, 0, 0, 1, 3)

        # Format selection
        self._format_label = QLabel("Format:")
        image_layout.addWidget(self._format_label, 1, 0)
        format_layout = QHBoxLayout()
        self._format_group = QButtonGroup(self)
        self._tiff_radio = QRadioButton("TIFF")
        self._png_radio = QRadioButton("PNG")
        self._jpg_radio = QRadioButton("JPG")
        self._tiff_radio.setChecked(True)
        self._format_group.addButton(self._tiff_radio, 0)
        self._format_group.addButton(self._png_radio, 1)
        self._format_group.addButton(self._jpg_radio, 2)
        format_layout.addWidget(self._tiff_radio)
        format_layout.addWidget(self._png_radio)
        format_layout.addWidget(self._jpg_radio)
        format_layout.addStretch()
        image_layout.addLayout(format_layout, 1, 1, 1, 2)

        # Bit depth
        self._bit_depth_label = QLabel("Bit Depth:")
        image_layout.addWidget(self._bit_depth_label, 2, 0)
        self._bit_depth_combo = QComboBox()
        self._bit_depth_combo.addItems(["8-bit", "16-bit", "32-bit (TIFF only)"])
        self._bit_depth_combo.setCurrentIndex(1)  # Default 16-bit
        image_layout.addWidget(self._bit_depth_combo, 2, 1, 1, 2)

        # Frame selection (only if sequence)
        if self._data.num_frames > 1:
            self._frames_label = QLabel("Frames:")
            image_layout.addWidget(self._frames_label, 3, 0)
            frame_layout = QHBoxLayout()
            self._frame_group = QButtonGroup(self)
            self._current_frame_radio = QRadioButton("Current frame only")
            self._all_frames_radio = QRadioButton(f"All frames ({self._data.num_frames})")
            self._current_frame_radio.setChecked(True)
            self._frame_group.addButton(self._current_frame_radio, 0)
            self._frame_group.addButton(self._all_frames_radio, 1)
            frame_layout.addWidget(self._current_frame_radio)
            frame_layout.addWidget(self._all_frames_radio)
            frame_layout.addStretch()
            image_layout.addLayout(frame_layout, 3, 1, 1, 2)
        else:
            self._frames_label = None
            self._current_frame_radio = None
            self._all_frames_radio = None

        # Colormap option
        self._colormap_check = QCheckBox("Apply colormap")
        self._colormap_check.setChecked(False)
        image_layout.addWidget(self._colormap_check, 4, 0, 1, 2)

        self._colormap_combo = QComboBox()
        self._colormap_combo.addItems([
            'viridis', 'plasma', 'inferno', 'magma', 'cividis',
            'Greys', 'gray', 'hot', 'cool', 'jet', 'turbo'
        ])
        # Set to current colormap if available
        idx = self._colormap_combo.findText(self._current_colormap)
        if idx >= 0:
            self._colormap_combo.setCurrentIndex(idx)
        self._colormap_combo.setEnabled(False)
        image_layout.addWidget(self._colormap_combo, 4, 2)

        # Intensity scaling
        self._use_display_range_check = QCheckBox("Use current display intensity range")
        self._use_display_range_check.setChecked(True)
        image_layout.addWidget(self._use_display_range_check, 5, 0, 1, 3)

        # Scale bar option
        self._scale_bar_check = QCheckBox("Include scale bar (burned into image)")
        self._scale_bar_check.setChecked(False)
        self._scale_bar_check.setToolTip("Burn the scale bar directly into the exported image for presentations")
        image_layout.addWidget(self._scale_bar_check, 6, 0, 1, 3)

        layout.addWidget(image_group)

        # Video export options (only if sequence)
        if self._data.num_frames > 1:
            video_group = QGroupBox("Video Export")
            video_layout = QGridLayout(video_group)

            self._video_check = QCheckBox("Export as MP4 video")
            self._video_check.setChecked(False)
            self._video_check.setToolTip("Export all frames as an MP4 video file")
            video_layout.addWidget(self._video_check, 0, 0, 1, 3)

            video_layout.addWidget(QLabel("Frame Rate:"), 1, 0)
            self._fps_spin = QSpinBox()
            self._fps_spin.setRange(1, 60)
            self._fps_spin.setValue(10)
            self._fps_spin.setSuffix(" fps")
            self._fps_spin.setEnabled(False)
            video_layout.addWidget(self._fps_spin, 1, 1)

            video_layout.addWidget(QLabel("Quality:"), 2, 0)
            self._quality_spin = QSpinBox()
            self._quality_spin.setRange(1, 10)
            self._quality_spin.setValue(8)
            self._quality_spin.setToolTip("1 = lowest quality (smallest file), 10 = highest quality (largest file)")
            self._quality_spin.setEnabled(False)
            video_layout.addWidget(self._quality_spin, 2, 1)

            layout.addWidget(video_group)
        else:
            self._video_check = None
            self._fps_spin = None
            self._quality_spin = None

        # Metadata options
        meta_group = QGroupBox("Metadata Export")
        meta_layout = QVBoxLayout(meta_group)

        self._json_check = QCheckBox("JSON (full metadata, machine-readable)")
        self._json_check.setChecked(True)
        meta_layout.addWidget(self._json_check)

        self._txt_check = QCheckBox("TXT (human-readable summary)")
        self._txt_check.setChecked(False)
        meta_layout.addWidget(self._txt_check)

        self._csv_check = QCheckBox("CSV (tabular format)")
        self._csv_check.setChecked(False)
        meta_layout.addWidget(self._csv_check)

        layout.addWidget(meta_group)

        # Progress bar (hidden initially)
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._progress_label = QLabel("")
        self._progress_label.setVisible(False)
        self._progress_label.setStyleSheet("color: #888;")
        layout.addWidget(self._progress_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(80)
        button_layout.addWidget(self._cancel_btn)

        self._export_btn = QPushButton("Export")
        self._export_btn.setFixedWidth(80)
        self._export_btn.setDefault(True)
        button_layout.addWidget(self._export_btn)

        layout.addLayout(button_layout)

    def _connect_signals(self):
        """Connect UI signals."""
        self._browse_btn.clicked.connect(self._on_browse)
        self._cancel_btn.clicked.connect(self.reject)
        self._export_btn.clicked.connect(self._on_export)

        self._colormap_check.toggled.connect(self._colormap_combo.setEnabled)
        self._format_group.buttonClicked.connect(self._update_ui_state)
        self._export_images_check.toggled.connect(self._on_export_images_toggled)

        # Video option signals
        if self._video_check:
            self._video_check.toggled.connect(self._on_video_check_toggled)

    def _update_ui_state(self):
        """Update UI based on current selections."""
        # Update bit depth options based on format
        format_id = self._format_group.checkedId()

        if format_id == 2:  # JPG
            # JPG is always 8-bit
            self._bit_depth_combo.setCurrentIndex(0)
            self._bit_depth_combo.setEnabled(False)
        elif format_id == 1:  # PNG
            # PNG supports 8-bit and 16-bit
            if self._bit_depth_combo.currentIndex() == 2:  # 32-bit selected
                self._bit_depth_combo.setCurrentIndex(1)  # Fall back to 16-bit
            self._bit_depth_combo.setEnabled(True)
        else:  # TIFF
            self._bit_depth_combo.setEnabled(True)

    def _on_export_images_toggled(self, checked: bool):
        """Handle export images checkbox toggle."""
        self._format_label.setEnabled(checked)
        self._tiff_radio.setEnabled(checked)
        self._png_radio.setEnabled(checked)
        self._jpg_radio.setEnabled(checked)
        self._bit_depth_label.setEnabled(checked)
        self._bit_depth_combo.setEnabled(checked)
        if self._frames_label:
            self._frames_label.setEnabled(checked)
        if self._current_frame_radio:
            self._current_frame_radio.setEnabled(checked)
        if self._all_frames_radio:
            self._all_frames_radio.setEnabled(checked)

    def _on_video_check_toggled(self, checked: bool):
        """Handle video checkbox toggle."""
        if self._fps_spin:
            self._fps_spin.setEnabled(checked)
        if self._quality_spin:
            self._quality_spin.setEnabled(checked)

    def _on_browse(self):
        """Handle browse button click."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            self._dir_edit.text()
        )
        if dir_path:
            self._dir_edit.setText(dir_path)

    def _get_settings(self) -> ExportSettings:
        """Build ExportSettings from current UI state."""
        # Get format
        format_id = self._format_group.checkedId()
        format_map = {0: "tiff", 1: "png", 2: "jpg"}
        image_format = format_map.get(format_id, "tiff")

        # Get bit depth
        bit_depth_map = {0: 8, 1: 16, 2: 32}
        bit_depth = bit_depth_map.get(self._bit_depth_combo.currentIndex(), 16)

        # Get frame selection
        export_all = False
        if self._all_frames_radio and self._all_frames_radio.isChecked():
            export_all = True

        # Video settings
        export_video = self._video_check.isChecked() if self._video_check else False
        video_fps = self._fps_spin.value() if self._fps_spin else 10
        video_quality = self._quality_spin.value() if self._quality_spin else 8

        return ExportSettings(
            output_dir=pathlib.Path(self._dir_edit.text()),
            folder_name=self._folder_edit.text() or self._data.file_path.stem,
            export_images=self._export_images_check.isChecked(),
            image_format=image_format,
            bit_depth=bit_depth,
            export_all_frames=export_all,
            apply_colormap=self._colormap_check.isChecked(),
            colormap_name=self._colormap_combo.currentText(),
            include_scale_bar=self._scale_bar_check.isChecked(),
            export_video=export_video,
            video_fps=video_fps,
            video_quality=video_quality,
            use_display_range=self._use_display_range_check.isChecked(),
            display_min=self._display_range[0],
            display_max=self._display_range[1],
            export_json=self._json_check.isChecked(),
            export_txt=self._txt_check.isChecked(),
            export_csv=self._csv_check.isChecked()
        )

    def _on_export(self):
        """Start export operation."""
        # Validate
        output_dir = pathlib.Path(self._dir_edit.text())
        if not output_dir.exists():
            QMessageBox.warning(
                self, "Invalid Directory",
                "The output directory does not exist."
            )
            return

        folder_name = self._folder_edit.text().strip()
        if not folder_name:
            QMessageBox.warning(
                self, "Invalid Folder Name",
                "Please enter a folder name."
            )
            return

        # Check if folder already exists
        output_folder = output_dir / folder_name
        if output_folder.exists():
            result = QMessageBox.question(
                self, "Folder Exists",
                f"The folder '{folder_name}' already exists. Files may be overwritten. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if result != QMessageBox.Yes:
                return

        # Disable UI during export
        self._set_ui_enabled(False)
        self._progress_bar.setVisible(True)
        self._progress_label.setVisible(True)
        self._progress_bar.setValue(0)
        self._progress_label.setText("Starting export...")

        # Create and start worker
        settings = self._get_settings()
        exporter = Exporter(self._data)

        self._worker = ExportWorker(exporter, settings)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _set_ui_enabled(self, enabled: bool):
        """Enable/disable UI elements."""
        self._dir_edit.setEnabled(enabled)
        self._browse_btn.setEnabled(enabled)
        self._folder_edit.setEnabled(enabled)
        # Image export controls
        self._export_images_check.setEnabled(enabled)
        images_enabled = enabled and self._export_images_check.isChecked()
        self._format_label.setEnabled(images_enabled)
        self._tiff_radio.setEnabled(images_enabled)
        self._png_radio.setEnabled(images_enabled)
        self._jpg_radio.setEnabled(images_enabled)
        self._bit_depth_label.setEnabled(images_enabled)
        self._bit_depth_combo.setEnabled(images_enabled)
        if self._frames_label:
            self._frames_label.setEnabled(images_enabled)
        if self._current_frame_radio:
            self._current_frame_radio.setEnabled(images_enabled)
        if self._all_frames_radio:
            self._all_frames_radio.setEnabled(images_enabled)
        self._colormap_check.setEnabled(enabled)
        self._colormap_combo.setEnabled(enabled and self._colormap_check.isChecked())
        self._use_display_range_check.setEnabled(enabled)
        self._scale_bar_check.setEnabled(enabled)
        # Video controls
        if self._video_check:
            self._video_check.setEnabled(enabled)
        if self._fps_spin:
            self._fps_spin.setEnabled(enabled and (self._video_check.isChecked() if self._video_check else False))
        if self._quality_spin:
            self._quality_spin.setEnabled(enabled and (self._video_check.isChecked() if self._video_check else False))
        self._json_check.setEnabled(enabled)
        self._txt_check.setEnabled(enabled)
        self._csv_check.setEnabled(enabled)
        self._export_btn.setEnabled(enabled)

    def _on_progress(self, current: int, total: int, message: str):
        """Handle progress update."""
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._progress_label.setText(message)

    def _on_finished(self, result_path):
        """Handle export completion."""
        self._worker = None
        self._set_ui_enabled(True)
        self._progress_bar.setVisible(False)
        self._progress_label.setVisible(False)

        QMessageBox.information(
            self, "Export Complete",
            f"Data exported successfully to:\n{result_path}"
        )
        self.accept()

    def _on_error(self, error_msg: str):
        """Handle export error."""
        self._worker = None
        self._set_ui_enabled(True)
        self._progress_bar.setVisible(False)
        self._progress_label.setVisible(False)

        QMessageBox.critical(
            self, "Export Failed",
            f"Export failed with error:\n{error_msg}"
        )

    def reject(self):
        """Handle dialog rejection (cancel)."""
        if self._worker and self._worker.isRunning():
            # TODO: Implement proper cancellation
            pass
        super().reject()
