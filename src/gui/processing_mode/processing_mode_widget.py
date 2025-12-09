"""
Main widget for Processing Mode with 3-panel layout:
1. Original (immutable reference)
2. Live Preview (current adjustments)
3. Snapshots (saved processing states)
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QLabel, QPushButton, QMessageBox, QScrollArea,
    QFrame, QFileDialog
)
from PySide6.QtCore import Qt, Signal, QSettings
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from typing import Optional, List, Dict
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime

from src.core.nhdf_reader import NHDFData, read_em_file
from .processing_panel import ProcessingPanel
from .processing_controls import ProcessingControlsPanel
from .snapshot_manager import SnapshotManager, ProcessingSnapshot


class ProcessingModeWidget(QWidget):
    """
    Main widget for Processing Mode.
    Manages the 3-panel layout and processing workflow.
    """

    # Signals
    file_loaded = Signal(str, object)  # (file_path, NHDFData)
    snapshot_created = Signal(object)  # ProcessingSnapshot
    processing_applied = Signal(dict)  # Processing parameters

    def __init__(self, parent=None):
        super().__init__(parent)

        # State management
        self.current_file: Optional[str] = None
        self.original_data: Optional[NHDFData] = None
        self.current_frame: int = 0

        # Snapshot management
        self.snapshot_manager = SnapshotManager()

        # Settings
        self._settings = QSettings("NionUtility", "ProcessingMode")

        self._setup_ui()
        self._connect_signals()
        self._restore_state()

        # Enable drag and drop
        self.setAcceptDrops(True)

    def _setup_ui(self):
        """Set up the UI with 3-panel layout and controls."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Add toolbar at the top
        toolbar_widget = QWidget()
        toolbar_widget.setMaximumHeight(40)
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(5, 2, 5, 2)

        # Open file button
        self.open_btn = QPushButton("Open File")
        self.open_btn.setMinimumWidth(100)
        self.open_btn.clicked.connect(self._open_file)
        toolbar_layout.addWidget(self.open_btn)

        # Current file label
        self.file_label = QLabel("No file loaded")
        self.file_label.setStyleSheet("QLabel { color: #888; margin-left: 10px; }")
        toolbar_layout.addWidget(self.file_label)
        toolbar_layout.addStretch()

        # Instructions label
        instructions = QLabel("Load a file to begin processing")
        instructions.setStyleSheet("QLabel { color: #888; font-style: italic; }")
        toolbar_layout.addWidget(instructions)

        main_layout.addWidget(toolbar_widget)

        # Add separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)

        # Create main horizontal splitter for panels
        self.main_splitter = QSplitter(Qt.Horizontal)

        # Panel 1: Original (immutable reference)
        self.original_panel = ProcessingPanel("Original (Reference)", read_only=True)
        self.original_panel.setMinimumWidth(300)
        self.original_panel.file_dropped.connect(self._on_file_dropped)
        self.main_splitter.addWidget(self.original_panel)

        # Panel 2: Live Preview
        self.preview_panel = ProcessingPanel("Live Preview", read_only=False)
        self.preview_panel.setMinimumWidth(300)
        self.preview_panel.file_dropped.connect(self._on_file_dropped)
        self.main_splitter.addWidget(self.preview_panel)

        # Panel 3: Snapshots container (will hold multiple snapshot panels)
        self.snapshots_container = QWidget()
        snapshots_layout = QVBoxLayout(self.snapshots_container)
        snapshots_layout.setContentsMargins(0, 0, 0, 0)

        # Snapshots header
        snapshots_header = QWidget()
        snapshots_header.setMaximumHeight(30)
        header_layout = QHBoxLayout(snapshots_header)
        header_layout.setContentsMargins(5, 2, 5, 2)

        snapshots_label = QLabel("Snapshots")
        snapshots_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(snapshots_label)
        header_layout.addStretch()

        self.compare_btn = QPushButton("Compare")
        self.compare_btn.setMinimumWidth(80)
        self.compare_btn.setEnabled(False)
        header_layout.addWidget(self.compare_btn)

        snapshots_layout.addWidget(snapshots_header)

        # Scrollable area for snapshot panels
        self.snapshots_scroll = QScrollArea()
        self.snapshots_scroll.setWidgetResizable(True)
        self.snapshots_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Container for snapshot panels (horizontal layout)
        self.snapshots_widget = QWidget()
        self.snapshots_layout = QHBoxLayout(self.snapshots_widget)
        self.snapshots_layout.setAlignment(Qt.AlignLeft)
        self.snapshots_scroll.setWidget(self.snapshots_widget)

        snapshots_layout.addWidget(self.snapshots_scroll)

        self.snapshots_container.setMinimumWidth(300)
        self.main_splitter.addWidget(self.snapshots_container)

        # Set initial splitter sizes (40%, 40%, 20%)
        self.main_splitter.setSizes([400, 400, 200])

        # Create vertical splitter for panels and controls
        self.vertical_splitter = QSplitter(Qt.Vertical)
        self.vertical_splitter.addWidget(self.main_splitter)

        # Bottom controls panel
        self.controls_panel = ProcessingControlsPanel()
        self.vertical_splitter.addWidget(self.controls_panel)

        # Set initial vertical sizes (70% panels, 30% controls)
        self.vertical_splitter.setSizes([700, 300])

        # Add vertical splitter to main layout
        main_layout.addWidget(self.vertical_splitter, 1)

    def _connect_signals(self):
        """Connect internal signals."""
        # Connect control panel signals
        self.controls_panel.adjustment_changed.connect(self._apply_adjustment)
        self.controls_panel.filter_applied.connect(self._apply_filter)
        self.controls_panel.snapshot_requested.connect(self._create_snapshot)
        self.controls_panel.reset_requested.connect(self._reset_to_original)

        # Connect panel signals
        self.preview_panel.frame_changed.connect(self._on_frame_changed)

        # Connect snapshot manager signals
        self.snapshot_manager.snapshot_created.connect(self._add_snapshot_panel)
        self.snapshot_manager.snapshot_deleted.connect(self._remove_snapshot_panel)

        # Compare button
        self.compare_btn.clicked.connect(self._open_comparison)

    def load_file(self, file_path: str, data: NHDFData):
        """Load a file for processing."""
        self.current_file = file_path
        self.original_data = data
        self.current_frame = 0

        # Update file label
        import os
        self.file_label.setText(f"File: {os.path.basename(file_path)}")

        # Load in original panel (read-only)
        self.original_panel.load_data(data, file_path)

        # Load in preview panel (editable)
        self.preview_panel.load_data(data, file_path)

        # Clear snapshots
        self._clear_snapshots()

        # Reset snapshot manager
        self.snapshot_manager.reset()

        # Enable controls
        self.controls_panel.setEnabled(True)

        # Emit signal
        self.file_loaded.emit(file_path, data)

    def _apply_adjustment(self, adjustment_params: dict):
        """Apply adjustment to live preview."""
        if not self.original_data:
            return

        # Apply to all frames if multi-frame data
        if len(self.original_data.data.shape) == 3:
            # Process all frames
            processed_data = np.zeros_like(self.original_data.data)
            for i in range(self.original_data.data.shape[0]):
                processed_data[i] = self._process_image(
                    self.original_data.data[i].copy().astype(np.float64),
                    adjustment_params
                )
            # Update preview with current frame
            self.preview_panel.update_display(processed_data[self.current_frame])
            # Store all processed frames for later use
            self.preview_panel.processed_frames = processed_data
        else:
            # Single frame
            original_frame = self.original_data.data.copy().astype(np.float64)
            processed_frame = self._process_image(original_frame, adjustment_params)
            self.preview_panel.update_display(processed_frame)

        # Store current processing state
        self.preview_panel.current_processing = adjustment_params

    def _apply_filter(self, filter_params: dict):
        """Apply filter to live preview."""
        if not self.original_data:
            return

        # Apply to all frames if multi-frame data
        if len(self.original_data.data.shape) == 3:
            # Process all frames
            processed_data = np.zeros_like(self.original_data.data, dtype=np.float64)
            for i in range(self.original_data.data.shape[0]):
                if self.preview_panel.current_processing:
                    # Apply existing adjustments first
                    base_frame = self._process_image(
                        self.original_data.data[i].copy().astype(np.float64),
                        self.preview_panel.current_processing
                    )
                else:
                    base_frame = self.original_data.data[i].copy().astype(np.float64)

                # Apply filter
                processed_data[i] = self._apply_filter_operation(base_frame, filter_params)

            # Update preview with current frame
            self.preview_panel.update_display(processed_data[self.current_frame])
            # Store all processed frames
            self.preview_panel.processed_frames = processed_data
        else:
            # Single frame
            if self.preview_panel.current_processing:
                base_frame = self._process_image(
                    self.original_data.data.copy().astype(np.float64),
                    self.preview_panel.current_processing
                )
            else:
                base_frame = self.original_data.data.copy().astype(np.float64)

            # Apply filter
            processed_frame = self._apply_filter_operation(base_frame, filter_params)
            self.preview_panel.update_display(processed_frame)

        # Update processing history
        if self.preview_panel.current_processing is None:
            self.preview_panel.current_processing = {}
        self.preview_panel.current_processing.update(filter_params)

    def _process_image(self, image: np.ndarray, params: dict) -> np.ndarray:
        """Apply processing parameters to image."""
        result = image.astype(np.float64)

        # Get original data range for scaling
        orig_min = np.min(image)
        orig_max = np.max(image)
        data_range = orig_max - orig_min if orig_max > orig_min else 1.0

        # Apply brightness (scaled to data range)
        if 'brightness' in params and params['brightness'] != 0:
            # Scale brightness to be proportional to data range
            brightness_scale = data_range * (params['brightness'] / 100.0)
            result = result + brightness_scale

        # Apply contrast
        if 'contrast' in params and params['contrast'] != 1.0:
            mean = np.mean(result)
            result = (result - mean) * params['contrast'] + mean

        # Apply gamma
        if 'gamma' in params and params['gamma'] != 1.0:
            # Normalize to 0-1 range
            min_val, max_val = np.min(result), np.max(result)
            if max_val > min_val:
                normalized = (result - min_val) / (max_val - min_val)
                # Apply gamma
                normalized = np.power(normalized, params['gamma'])
                # Rescale back
                result = normalized * (max_val - min_val) + min_val

        return result

    def _apply_filter_operation(self, image: np.ndarray, params: dict) -> np.ndarray:
        """Apply filter operations to image."""
        from scipy import ndimage
        result = image.copy()

        # Gaussian blur
        if 'gaussian_sigma' in params:
            result = ndimage.gaussian_filter(result, sigma=params['gaussian_sigma'])

        # Median filter
        if 'median_size' in params:
            result = ndimage.median_filter(result, size=params['median_size'])

        # Unsharp mask
        if 'unsharp_amount' in params and 'unsharp_radius' in params:
            # Create blurred version
            blurred = ndimage.gaussian_filter(result, sigma=params['unsharp_radius'])
            # Apply unsharp mask: original + amount * (original - blurred)
            result = result + params['unsharp_amount'] * (result - blurred)

        return result

    def _create_snapshot(self):
        """Create a snapshot of current preview state."""
        if not self.preview_panel.current_processing:
            QMessageBox.information(self, "No Changes",
                                  "No processing has been applied to create a snapshot.")
            return

        # Get current processed image
        processed_data = self.preview_panel.get_current_data()

        if processed_data is None:
            return

        # Create snapshot
        snapshot = self.snapshot_manager.create_snapshot(
            processed_data,
            self.preview_panel.current_processing,
            self.current_frame
        )

        # Emit signal
        self.snapshot_created.emit(snapshot)

    def _add_snapshot_panel(self, snapshot: ProcessingSnapshot):
        """Add a new snapshot panel to the UI."""
        # Create mini panel for snapshot
        snapshot_panel = ProcessingPanel(
            f"Snapshot {snapshot.id}",
            read_only=True,
            compact=True
        )

        # Load snapshot data
        snapshot_panel.load_snapshot(snapshot)

        # Add to layout
        self.snapshots_layout.addWidget(snapshot_panel)

        # Enable compare button if we have 2+ snapshots
        if self.snapshot_manager.get_snapshot_count() >= 2:
            self.compare_btn.setEnabled(True)

    def _remove_snapshot_panel(self, snapshot_id: str):
        """Remove a snapshot panel from the UI."""
        # Find and remove the panel
        for i in range(self.snapshots_layout.count()):
            widget = self.snapshots_layout.itemAt(i).widget()
            if isinstance(widget, ProcessingPanel) and widget.snapshot_id == snapshot_id:
                widget.deleteLater()
                self.snapshots_layout.removeWidget(widget)
                break

        # Disable compare button if less than 2 snapshots
        if self.snapshot_manager.get_snapshot_count() < 2:
            self.compare_btn.setEnabled(False)

    def _clear_snapshots(self):
        """Clear all snapshot panels."""
        while self.snapshots_layout.count():
            widget = self.snapshots_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()

        self.compare_btn.setEnabled(False)

    def _reset_to_original(self):
        """Reset preview to original image."""
        if not self.original_data:
            return

        # Reset preview panel
        self.preview_panel.load_data(self.original_data, self.current_file)
        self.preview_panel.current_processing = None
        self.preview_panel.processed_frames = None  # Clear processed frames

    def _on_frame_changed(self, frame: int):
        """Handle frame change."""
        self.current_frame = frame

        # Update all panels
        if self.original_data:
            self.original_panel.set_frame(frame)

            # Update preview panel with processed frame if available
            if hasattr(self.preview_panel, 'processed_frames') and self.preview_panel.processed_frames is not None:
                if frame < len(self.preview_panel.processed_frames):
                    self.preview_panel.set_frame(frame)
            elif self.preview_panel.current_processing:
                # Reapply processing if no processed frames stored
                self._apply_adjustment(self.preview_panel.current_processing)

    def _open_comparison(self):
        """Open comparison dialog for snapshots."""
        # TODO: Implement comparison dialog
        QMessageBox.information(self, "Compare Snapshots",
                              "Snapshot comparison dialog will be implemented here.")

    def _restore_state(self):
        """Restore previous state from settings."""
        # Restore splitter sizes
        sizes = self._settings.value("processing_mode/splitter_sizes")
        if sizes:
            self.main_splitter.setSizes([int(s) for s in sizes])

    def save_state(self):
        """Save current state to settings."""
        # Save splitter sizes
        self._settings.setValue("processing_mode/splitter_sizes",
                              self.main_splitter.sizes())

    def _open_file(self):
        """Open a file dialog to select a file for processing."""
        from PySide6.QtWidgets import QFileDialog
        import pathlib

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open File for Processing",
            "",
            "EM Files (*.nhdf *.dm3 *.dm4);;nhdf Files (*.nhdf);;DM Files (*.dm3 *.dm4);;All Files (*)"
        )

        if file_path:
            try:
                # Read the file
                data = read_em_file(pathlib.Path(file_path))
                if data:
                    self.load_file(file_path, data)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load file:\n{str(e)}")

    def _on_file_dropped(self, file_path: str):
        """Handle file dropped on a panel."""
        try:
            import pathlib
            # Read the file
            data = read_em_file(pathlib.Path(file_path))
            if data:
                self.load_file(file_path, data)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load dropped file:\n{str(e)}")

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events."""
        if event.mimeData().hasUrls():
            # Check if any of the URLs are supported files
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith(('.nhdf', '.dm3', '.dm4')):
                        event.acceptProposedAction()
                        # Visual feedback
                        self.setStyleSheet("""
                            ProcessingModeWidget {
                                border: 2px solid #4a90d9;
                                background-color: rgba(74, 144, 217, 0.1);
                            }
                        """)
                        return

    def dragLeaveEvent(self, event):
        """Handle drag leave events."""
        # Remove visual feedback
        self.setStyleSheet("")

    def dropEvent(self, event: QDropEvent):
        """Handle drop events."""
        # Remove visual feedback
        self.setStyleSheet("")

        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith(('.nhdf', '.dm3', '.dm4')):
                        try:
                            import pathlib
                            # Read the file
                            data = read_em_file(pathlib.Path(file_path))
                            if data:
                                self.load_file(file_path, data)
                                event.acceptProposedAction()
                                return
                        except Exception as e:
                            QMessageBox.critical(self, "Error", f"Failed to load file:\n{str(e)}")