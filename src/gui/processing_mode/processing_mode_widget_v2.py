"""
Redesigned Processing Mode Widget with proper frame handling and processing tree.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QLabel, QPushButton, QMessageBox, QScrollArea,
    QFrame, QFileDialog, QSlider, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QSettings, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent
import numpy as np
from typing import Optional

from src.core.nhdf_reader import NHDFData, read_em_file
from .processing_panel import ProcessingPanel
from .processing_controls import ProcessingControlsPanel
from .processing_engine import ProcessingEngine, ProcessingState


class ProcessingModeWidgetV2(QWidget):
    """
    Redesigned Processing Mode widget with proper processing pipeline.
    """

    # Signals
    file_loaded = Signal(str, object)  # (file_path, NHDFData)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Processing engine
        self.engine = ProcessingEngine()
        self.engine.on_processing_complete = self._on_processing_complete

        # Data
        self.current_file: Optional[str] = None
        self.nhdf_data: Optional[NHDFData] = None
        self.current_frame: int = 0

        # Settings
        self._settings = QSettings("NionUtility", "ProcessingModeV2")

        # Update timer for real-time processing
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._apply_current_processing)
        self.update_timer.setSingleShot(True)

        self._setup_ui()
        self._connect_signals()

        # Enable drag and drop
        self.setAcceptDrops(True)

    def _setup_ui(self):
        """Set up the UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar
        toolbar = self._create_toolbar()
        main_layout.addWidget(toolbar)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)

        # Main content: vertical splitter
        self.vertical_splitter = QSplitter(Qt.Vertical)

        # Top: Panels
        self.panels_splitter = QSplitter(Qt.Horizontal)

        # Original panel
        self.original_panel = ProcessingPanel("Original (Reference)", read_only=True)
        self.original_panel.setMinimumWidth(300)
        self.original_panel.file_dropped.connect(self._on_file_dropped)
        self.panels_splitter.addWidget(self.original_panel)

        # Live preview panel
        self.preview_panel = ProcessingPanel("Live Preview", read_only=True)
        self.preview_panel.setMinimumWidth(300)
        self.preview_panel.file_dropped.connect(self._on_file_dropped)
        self.panels_splitter.addWidget(self.preview_panel)

        # Snapshots container
        self.snapshots_container = self._create_snapshots_container()
        self.panels_splitter.addWidget(self.snapshots_container)

        # Set initial panel sizes
        self.panels_splitter.setSizes([400, 400, 300])

        self.vertical_splitter.addWidget(self.panels_splitter)

        # Bottom: Controls
        self.controls = ProcessingControlsPanel()
        self.vertical_splitter.addWidget(self.controls)

        # Set vertical sizes
        self.vertical_splitter.setSizes([700, 300])

        main_layout.addWidget(self.vertical_splitter)

        # Frame controls container
        self.frame_controls = self._create_frame_controls()
        main_layout.addWidget(self.frame_controls)

    def _create_toolbar(self) -> QWidget:
        """Create the toolbar."""
        toolbar = QWidget()
        toolbar.setMaximumHeight(40)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(5, 2, 5, 2)

        # Open file button
        self.open_btn = QPushButton("Open File")
        self.open_btn.setMinimumWidth(100)
        self.open_btn.clicked.connect(self._open_file)
        layout.addWidget(self.open_btn)

        # File label
        self.file_label = QLabel("No file loaded")
        self.file_label.setStyleSheet("QLabel { color: #888; }")
        layout.addWidget(self.file_label)

        layout.addStretch()

        # Processing status
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("QLabel { color: #4a90d9; }")
        layout.addWidget(self.status_label)

        return toolbar

    def _create_snapshots_container(self) -> QWidget:
        """Create the snapshots container."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QWidget()
        header.setMaximumHeight(30)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(5, 2, 5, 2)

        label = QLabel("Snapshots")
        label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(label)
        header_layout.addStretch()

        self.snapshot_btn = QPushButton("Create Snapshot")
        self.snapshot_btn.setMinimumWidth(110)
        self.snapshot_btn.clicked.connect(self._create_snapshot)
        self.snapshot_btn.setEnabled(False)
        header_layout.addWidget(self.snapshot_btn)

        layout.addWidget(header)

        # Snapshots scroll area
        self.snapshots_scroll = QScrollArea()
        self.snapshots_scroll.setWidgetResizable(True)

        self.snapshots_widget = QWidget()
        self.snapshots_layout = QVBoxLayout(self.snapshots_widget)
        self.snapshots_layout.setAlignment(Qt.AlignTop)
        self.snapshots_scroll.setWidget(self.snapshots_widget)

        layout.addWidget(self.snapshots_scroll)

        container.setMinimumWidth(300)
        return container

    def _create_frame_controls(self) -> QWidget:
        """Create frame controls for multi-frame data."""
        container = QWidget()
        container.setMaximumHeight(40)
        container.setVisible(False)  # Hidden by default

        layout = QHBoxLayout(container)
        layout.setContentsMargins(5, 2, 5, 2)

        # Frame label
        self.frame_label = QLabel("Frame:")
        layout.addWidget(self.frame_label)

        # Frame spinbox
        self.frame_spinbox = QSpinBox()
        self.frame_spinbox.valueChanged.connect(self._on_frame_changed)
        layout.addWidget(self.frame_spinbox)

        # Frame slider
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.valueChanged.connect(self._on_frame_changed)
        layout.addWidget(self.frame_slider, 1)

        # Frame info
        self.frame_info = QLabel("")
        layout.addWidget(self.frame_info)

        return container

    def _connect_signals(self):
        """Connect all signals."""
        # Controls - real-time updates
        self.controls.adjustment_changed.connect(self._on_adjustment_changed)
        self.controls.filter_applied.connect(self._on_filter_applied)
        self.controls.snapshot_requested.connect(self._create_snapshot)
        self.controls.reset_requested.connect(self._reset_to_original)

    def load_file(self, file_path: str, data: NHDFData):
        """Load a file for processing."""
        self.current_file = file_path
        self.nhdf_data = data
        self.current_frame = 0

        # Update UI
        import os
        self.file_label.setText(f"File: {os.path.basename(file_path)}")

        # Load into engine
        self.engine.load_data(data.data)

        # Load into panels
        self.original_panel.load_data(data, file_path)
        self.preview_panel.load_data(data, file_path)

        # Setup frame controls if multi-frame
        if len(data.data.shape) == 3:
            num_frames = data.data.shape[0]
            self.frame_controls.setVisible(True)
            self.frame_spinbox.setRange(0, num_frames - 1)
            self.frame_slider.setRange(0, num_frames - 1)
            self.frame_info.setText(f"/ {num_frames - 1}")
        else:
            self.frame_controls.setVisible(False)

        # Enable controls
        self.controls.setEnabled(True)
        self.snapshot_btn.setEnabled(True)

        # Clear snapshots
        self._clear_snapshots()

        self.file_loaded.emit(file_path, data)

    def _on_adjustment_changed(self, params: dict):
        """Handle adjustment changes with real-time updates."""
        self.status_label.setText("Processing...")

        # Debounce updates for smooth slider interaction
        self.update_timer.stop()
        self.update_timer.start(50)  # 50ms debounce

    def _on_filter_applied(self, params: dict):
        """Handle filter application."""
        # Get current adjustments and add filter params
        current_params = self.controls.get_current_parameters()

        # Mark filters as enabled
        if 'gaussian_sigma' in params:
            current_params['gaussian_enabled'] = True
            current_params['gaussian_sigma'] = params['gaussian_sigma']
        if 'median_size' in params:
            current_params['median_enabled'] = True
            current_params['median_size'] = params['median_size']
        if 'unsharp_amount' in params:
            current_params['unsharp_enabled'] = True
            current_params['unsharp_amount'] = params['unsharp_amount']
            current_params['unsharp_radius'] = params['unsharp_radius']

        # Apply all processing
        self.engine.apply_processing(current_params)

    def _apply_current_processing(self):
        """Apply current processing parameters (called after debounce)."""
        params = self.controls.get_current_parameters()
        self.engine.apply_processing(params, real_time=True)

    def _on_processing_complete(self, processed_data: np.ndarray):
        """Handle processing completion."""
        # Update preview panel with processed data
        if processed_data is not None:
            # Store processed frames in preview panel
            self.preview_panel.processed_frames = processed_data

            # Update current frame display
            frame_data = self.engine.get_current_frame(self.current_frame)
            if frame_data is not None:
                self.preview_panel.current_data = frame_data
                self.preview_panel.image_view.setImage(frame_data)

        self.status_label.setText("")

    def _on_frame_changed(self, frame: int):
        """Handle frame change."""
        self.current_frame = frame

        # Sync controls
        self.frame_slider.blockSignals(True)
        self.frame_spinbox.blockSignals(True)
        self.frame_slider.setValue(frame)
        self.frame_spinbox.setValue(frame)
        self.frame_slider.blockSignals(False)
        self.frame_spinbox.blockSignals(False)

        # Update original panel
        self.original_panel.set_frame(frame)

        # Update preview with processed frame
        processed_frame = self.engine.get_current_frame(frame)
        if processed_frame is not None:
            self.preview_panel.current_data = processed_frame
            self.preview_panel.image_view.setImage(processed_frame)
            # Also update the frame position in preview panel
            if hasattr(self.preview_panel, 'frame_slider'):
                self.preview_panel.frame_slider.blockSignals(True)
                self.preview_panel.frame_spinbox.blockSignals(True)
                self.preview_panel.frame_slider.setValue(frame)
                self.preview_panel.frame_spinbox.setValue(frame)
                self.preview_panel.frame_slider.blockSignals(False)
                self.preview_panel.frame_spinbox.blockSignals(False)

    def _create_snapshot(self):
        """Create a snapshot of current processing."""
        if self.engine.current_processed_data is None:
            return

        # Create snapshot
        snapshot = self.engine.create_snapshot()

        # Add to UI
        self._add_snapshot_to_ui(snapshot)

        QMessageBox.information(self, "Snapshot Created",
                              f"Snapshot '{snapshot.name}' created successfully")

    def _add_snapshot_to_ui(self, snapshot: ProcessingState):
        """Add snapshot to the UI."""
        # Create a compact panel for the snapshot
        snapshot_panel = QFrame()
        snapshot_panel.setFrameStyle(QFrame.Box)
        snapshot_panel.setMaximumHeight(150)

        layout = QVBoxLayout(snapshot_panel)

        # Title
        title = QLabel(snapshot.name)
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        # Info
        info = QLabel(f"ID: {snapshot.id}\nTime: {snapshot.timestamp.strftime('%H:%M:%S')}")
        info.setStyleSheet("font-size: 10px; color: #888;")
        layout.addWidget(info)

        # Buttons
        btn_layout = QHBoxLayout()

        load_btn = QPushButton("Load")
        load_btn.clicked.connect(lambda: self._load_snapshot(snapshot.id))
        btn_layout.addWidget(load_btn)

        compare_btn = QPushButton("Compare")
        compare_btn.clicked.connect(lambda: self._compare_snapshot(snapshot.id))
        btn_layout.addWidget(compare_btn)

        layout.addLayout(btn_layout)

        # Add to snapshots container
        self.snapshots_layout.addWidget(snapshot_panel)

    def _load_snapshot(self, snapshot_id: str):
        """Load a snapshot."""
        self.engine.load_snapshot(snapshot_id)
        self.status_label.setText(f"Loaded snapshot {snapshot_id}")

    def _compare_snapshot(self, snapshot_id: str):
        """Compare with a snapshot."""
        # TODO: Implement comparison view
        QMessageBox.information(self, "Compare",
                              f"Comparison view for {snapshot_id} will be implemented")

    def _clear_snapshots(self):
        """Clear all snapshots from UI."""
        while self.snapshots_layout.count():
            item = self.snapshots_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _reset_to_original(self):
        """Reset to original data."""
        self.engine.reset_to_original()
        self.controls._reset_controls()
        self.status_label.setText("Reset to original")

    def _open_file(self):
        """Open a file dialog."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open File for Processing",
            "",
            "EM Files (*.nhdf *.dm3 *.dm4);;All Files (*)"
        )

        if file_path:
            try:
                import pathlib
                data = read_em_file(pathlib.Path(file_path))
                if data:
                    self.load_file(file_path, data)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load file:\n{str(e)}")

    def _on_file_dropped(self, file_path: str):
        """Handle file dropped on a panel."""
        try:
            import pathlib
            data = read_em_file(pathlib.Path(file_path))
            if data:
                self.load_file(file_path, data)
            else:
                QMessageBox.warning(self, "Warning", f"Could not read file: {file_path}")
        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Error", f"Failed to load dropped file:\n{str(e)}\n\n{traceback.format_exc()}")

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if path.lower().endswith(('.nhdf', '.dm3', '.dm4')):
                        event.acceptProposedAction()
                        self.setStyleSheet("ProcessingModeWidgetV2 { border: 2px solid #4a90d9; }")
                        return

    def dragLeaveEvent(self, event):
        """Handle drag leave."""
        self.setStyleSheet("")

    def dropEvent(self, event: QDropEvent):
        """Handle drop."""
        self.setStyleSheet("")

        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith(('.nhdf', '.dm3', '.dm4')):
                        try:
                            import pathlib
                            data = read_em_file(pathlib.Path(file_path))
                            if data:
                                self.load_file(file_path, data)
                                event.acceptProposedAction()
                                return
                            else:
                                QMessageBox.warning(self, "Warning", f"Could not read file: {file_path}")
                        except Exception as e:
                            import traceback
                            QMessageBox.critical(self, "Error", f"Failed to load file:\n{str(e)}\n\n{traceback.format_exc()}")