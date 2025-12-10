"""
Version 3 of Processing Mode with controls on the right and better snapshot comparison.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QLabel, QPushButton, QMessageBox, QScrollArea,
    QFrame, QFileDialog, QSlider, QSpinBox, QGridLayout
)
from PySide6.QtCore import Qt, Signal, QSettings, QTimer, QEvent
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPalette
import pyqtgraph as pg
import numpy as np
from typing import Optional, List

from src.core.nhdf_reader import NHDFData, read_em_file
from .processing_controls import ProcessingControlsPanel
from .processing_engine import ProcessingEngine, ProcessingState
from .node_graph_widget import NodeGraphWidget
from .processing_export import ProcessingExportDialog


class SnapshotPanel(QFrame):
    """Panel for displaying a snapshot."""

    load_requested = Signal(str)  # snapshot_id
    compare_requested = Signal(str)  # snapshot_id
    delete_requested = Signal(str)  # snapshot_id
    export_requested = Signal(str)  # snapshot_id

    def __init__(self, snapshot: ProcessingState, parent=None):
        super().__init__(parent)
        self.snapshot = snapshot
        self.current_frame = 0

        self.setFrameStyle(QFrame.Box)
        self.setMinimumSize(150, 150)  # Reduced to allow more flexibility

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Header
        header = QWidget()
        header.setMaximumHeight(30)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel(self.snapshot.name)
        title.setStyleSheet("font-weight: bold; font-size: 11px;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # Delete button
        delete_btn = QPushButton("×")
        delete_btn.setMaximumSize(20, 20)
        delete_btn.setToolTip("Delete snapshot")
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.snapshot.id))
        header_layout.addWidget(delete_btn)

        layout.addWidget(header)

        # Image display
        self.image_view = pg.ImageView()
        self.image_view.ui.menuBtn.hide()
        self.image_view.ui.roiBtn.hide()
        self.image_view.ui.histogram.hide()
        self.image_view.ui.roiPlot.hide()
        self.image_view.view.setMouseEnabled(x=False, y=False)
        # Use theme-aware background - get color from palette
        bg_color = self.palette().window().color()
        self.image_view.view.setBackgroundColor(bg_color)

        layout.addWidget(self.image_view)

        # Frame controls for multi-frame
        self.frame_controls = QWidget()
        frame_layout = QHBoxLayout(self.frame_controls)
        frame_layout.setContentsMargins(0, 0, 0, 0)

        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.valueChanged.connect(self._on_frame_changed)

        self.frame_label = QLabel("0")
        self.frame_label.setMinimumWidth(30)

        frame_layout.addWidget(QLabel("Frame:"))
        frame_layout.addWidget(self.frame_label)
        frame_layout.addWidget(self.frame_slider)

        layout.addWidget(self.frame_controls)

        # Buttons
        btn_layout = QHBoxLayout()

        load_btn = QPushButton("Load")
        load_btn.clicked.connect(lambda: self.load_requested.emit(self.snapshot.id))
        btn_layout.addWidget(load_btn)

        compare_btn = QPushButton("Compare")
        compare_btn.clicked.connect(lambda: self.compare_requested.emit(self.snapshot.id))
        btn_layout.addWidget(compare_btn)

        export_btn = QPushButton("Export")
        export_btn.setToolTip("Export this snapshot")
        export_btn.clicked.connect(lambda: self.export_requested.emit(self.snapshot.id))
        btn_layout.addWidget(export_btn)

        layout.addLayout(btn_layout)

        # Initialize display
        self._update_display()

    def _update_display(self):
        """Update the displayed image."""
        frame_data = self.snapshot.get_frame(self.current_frame)
        if frame_data is not None:
            # Transpose and flip x for correct orientation to match Preview mode
            self.image_view.setImage(np.fliplr(frame_data.T))

            # Setup frame controls if multi-frame
            if self.snapshot.processed_data is not None and len(self.snapshot.processed_data.shape) == 3:
                num_frames = self.snapshot.processed_data.shape[0]
                self.frame_slider.setRange(0, num_frames - 1)
                self.frame_controls.show()
            else:
                self.frame_controls.hide()

    def _on_frame_changed(self, value):
        """Handle frame change."""
        self.current_frame = value
        self.frame_label.setText(str(value))
        self._update_display()

    def changeEvent(self, event):
        """Handle change events including palette/theme changes."""
        if event.type() == QEvent.PaletteChange:
            bg_color = self.palette().window().color()
            self.image_view.view.setBackgroundColor(bg_color)
        super().changeEvent(event)


class ProcessingModeWidgetV3(QWidget):
    """
    Version 3: Controls on right, multiple snapshot comparison panels.
    """

    # Signals
    file_loaded = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Processing engine
        self.engine = ProcessingEngine()
        self.engine.on_processing_complete = self._on_processing_complete

        # Data
        self.current_file: Optional[str] = None
        self.nhdf_data: Optional[NHDFData] = None
        self.current_frame: int = 0

        # Original data display range (for consistent display when processing)
        self._original_min: float = 0
        self._original_max: float = 1

        # Snapshot panels
        self.snapshot_panels: List[SnapshotPanel] = []

        # Settings
        self._settings = QSettings("NionUtility", "ProcessingModeV3")

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

        # Main horizontal splitter
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(6)  # Wider handle for easier grabbing

        # Left: Vertical splitter for image panels and snapshots
        self.left_splitter = QSplitter(Qt.Vertical)
        self.left_splitter.setChildrenCollapsible(False)

        # Top row: Original and Preview (horizontal splitter)
        top_splitter = QSplitter(Qt.Horizontal)
        top_splitter.setChildrenCollapsible(False)

        # Original panel
        self.original_panel = self._create_display_panel("Original (Reference)")
        top_splitter.addWidget(self.original_panel)

        # Preview panel
        self.preview_panel = self._create_display_panel("Live Preview")
        top_splitter.addWidget(self.preview_panel)

        top_splitter.setSizes([500, 500])
        self.left_splitter.addWidget(top_splitter)

        # Bottom: Snapshots area
        snapshots_container = QWidget()
        snapshots_layout = QVBoxLayout(snapshots_container)
        snapshots_layout.setContentsMargins(0, 0, 0, 0)

        # Snapshots header
        snapshots_header = QWidget()
        snapshots_header.setMaximumHeight(35)
        header_layout = QHBoxLayout(snapshots_header)
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

        snapshots_layout.addWidget(snapshots_header)

        # Snapshots in a horizontal splitter for resizable panels
        self.snapshots_scroll = QScrollArea()
        self.snapshots_scroll.setWidgetResizable(True)
        self.snapshots_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.snapshots_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Use a horizontal splitter instead of grid for resizable snapshots
        self.snapshots_splitter = QSplitter(Qt.Horizontal)
        self.snapshots_splitter.setChildrenCollapsible(False)
        self.snapshots_splitter.setHandleWidth(4)
        self.snapshots_scroll.setWidget(self.snapshots_splitter)

        snapshots_layout.addWidget(self.snapshots_scroll)

        self.left_splitter.addWidget(snapshots_container)

        # Set initial sizes (60% top panels, 40% snapshots)
        self.left_splitter.setSizes([400, 250])

        self.main_splitter.addWidget(self.left_splitter)

        # Right: Controls and Tree in vertical splitter
        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.setMinimumWidth(200)  # Reduced minimum to allow more flexibility

        # Controls panel
        self.controls = ProcessingControlsPanel()
        right_splitter.addWidget(self.controls)

        # Node graph panel (replaces tree widget)
        self.node_graph = NodeGraphWidget()
        self.node_graph.node_selected.connect(self._on_graph_node_selected)
        self.node_graph.node_activated.connect(self._on_graph_node_activated)

        right_splitter.addWidget(self.node_graph)
        right_splitter.setSizes([400, 200])  # 2/3 controls, 1/3 tree

        self.main_splitter.addWidget(right_splitter)

        # Set splitter sizes (75% panels, 25% controls)
        self.main_splitter.setSizes([900, 300])

        main_layout.addWidget(self.main_splitter)

        # Frame controls at bottom
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

        # Export button
        self.export_btn = QPushButton("Export All...")
        self.export_btn.setMinimumWidth(100)
        self.export_btn.setToolTip("Export processed data from all snapshots")
        self.export_btn.clicked.connect(self._show_export_dialog)
        self.export_btn.setEnabled(False)
        layout.addWidget(self.export_btn)

        # Processing status
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("QLabel { color: #4a90d9; }")
        layout.addWidget(self.status_label)

        return toolbar

    def _create_display_panel(self, title: str) -> QWidget:
        """Create a display panel with pyqtgraph ImageView."""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Box)
        panel.setAcceptDrops(True)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)

        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(title_label)

        # Image view
        image_view = pg.ImageView()
        image_view.ui.menuBtn.hide()
        image_view.ui.roiBtn.hide()
        image_view.ui.histogram.hide()  # Hide the histogram panel
        image_view.ui.roiPlot.hide()
        # Use theme-aware background - get color from palette
        bg_color = self.palette().window().color()
        image_view.view.setBackgroundColor(bg_color)

        layout.addWidget(image_view)

        # Store image view reference
        panel.image_view = image_view
        panel.title = title

        # Connect drag and drop
        panel.dragEnterEvent = lambda e: self._panel_drag_enter(e, panel)
        panel.dragLeaveEvent = lambda e: self._panel_drag_leave(e, panel)
        panel.dropEvent = lambda e: self._panel_drop(e)

        return panel

    def _create_frame_controls(self) -> QWidget:
        """Create frame controls."""
        container = QWidget()
        container.setMaximumHeight(40)
        container.setVisible(False)

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
        """Connect signals."""
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

        # Store original data range for consistent display
        self._original_min = float(np.min(data.data))
        self._original_max = float(np.max(data.data))

        # Set pixel scale for physical unit conversion in filters
        # Get calibration from the data (typically X or Y dimension)
        calibrations = data.dimensional_calibrations
        if calibrations and len(calibrations) >= 2:
            # Use X calibration (last dimension for images)
            x_cal = calibrations[-1]
            if x_cal and hasattr(x_cal, 'scale') and x_cal.scale > 0:
                scale = x_cal.scale
                unit = x_cal.units if hasattr(x_cal, 'units') and x_cal.units else 'nm'
                # Convert common units to nm for consistency
                if unit == 'µm' or unit == 'um':
                    scale *= 1000
                    unit = 'nm'
                elif unit == 'm':
                    scale *= 1e9
                    unit = 'nm'
                self.controls.set_pixel_scale(scale, unit)

        # Display in panels (transpose and flip x for correct orientation to match Preview mode)
        frame_data = data.data[0] if len(data.data.shape) == 3 else data.data
        display_data = np.fliplr(frame_data.T)  # Flip left-right only

        # Set images with fixed levels based on original data range
        self.original_panel.image_view.setImage(display_data, levels=(self._original_min, self._original_max))
        self.preview_panel.image_view.setImage(display_data, levels=(self._original_min, self._original_max))

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

        # Clear node graph (except root)
        self.node_graph.clear_nodes()

        self.file_loaded.emit(file_path, data)

    def _on_adjustment_changed(self, params: dict):
        """Handle adjustment changes."""
        self.status_label.setText("Processing...")

        # Debounce for smooth interaction
        self.update_timer.stop()
        self.update_timer.start(50)

    def _on_filter_applied(self, params: dict):
        """Handle filter application."""
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

        self.engine.apply_processing(current_params)

    def _apply_current_processing(self):
        """Apply current processing parameters."""
        params = self.controls.get_current_parameters()
        self.engine.apply_processing(params, real_time=True)

    def _on_processing_complete(self, processed_data: np.ndarray):
        """Handle processing completion."""
        if processed_data is not None:
            # Update preview panel (transpose and flip x for correct orientation)
            # Use fixed levels from original data so brightness/contrast changes are visible
            if len(processed_data.shape) == 3:
                display_data = np.fliplr(processed_data[self.current_frame].T)
            else:
                display_data = np.fliplr(processed_data.T)

            self.preview_panel.image_view.setImage(
                display_data,
                levels=(self._original_min, self._original_max)
            )

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

        # Update displays (transpose and flip x for correct orientation)
        # Use fixed levels from original data for consistent display
        if self.nhdf_data and len(self.nhdf_data.data.shape) == 3:
            # Original
            self.original_panel.image_view.setImage(
                np.fliplr(self.nhdf_data.data[frame].T),
                levels=(self._original_min, self._original_max)
            )

            # Preview with processed frame
            processed_frame = self.engine.get_current_frame(frame)
            if processed_frame is not None:
                self.preview_panel.image_view.setImage(
                    np.fliplr(processed_frame.T),
                    levels=(self._original_min, self._original_max)
                )

    def _create_snapshot(self):
        """Create a snapshot."""
        if self.engine.current_processed_data is None:
            return

        # Create snapshot
        snapshot = self.engine.create_snapshot()

        # Add to UI
        self._add_snapshot_panel(snapshot)

        # Add to node graph
        self._add_snapshot_to_graph(snapshot)

        self.status_label.setText(f"Created {snapshot.name}")

    def _add_snapshot_panel(self, snapshot: ProcessingState):
        """Add a snapshot panel to the grid."""
        panel = SnapshotPanel(snapshot)
        panel.load_requested.connect(self._load_snapshot)
        panel.compare_requested.connect(self._compare_snapshot)
        panel.delete_requested.connect(self._delete_snapshot)
        panel.export_requested.connect(self._export_single_snapshot)

        # Add to horizontal splitter
        self.snapshots_splitter.addWidget(panel)

        self.snapshot_panels.append(panel)

        # Enable export button when we have snapshots
        self.export_btn.setEnabled(True)

    def _load_snapshot(self, snapshot_id: str):
        """Load a snapshot."""
        self.engine.load_snapshot(snapshot_id)
        # Select the loaded snapshot in the graph so subsequent snapshots branch from it
        self.node_graph.select_node(snapshot_id)
        self.status_label.setText(f"Loaded snapshot {snapshot_id}")

    def _compare_snapshot(self, snapshot_id: str):
        """Compare with snapshot."""
        # TODO: Implement comparison
        QMessageBox.information(self, "Compare", f"Comparison for {snapshot_id}")

    def _delete_snapshot(self, snapshot_id: str):
        """Delete a snapshot."""
        # Find and remove panel
        for panel in self.snapshot_panels:
            if panel.snapshot.id == snapshot_id:
                panel.deleteLater()
                self.snapshot_panels.remove(panel)
                break

        # Remove from node graph
        self._remove_snapshot_from_graph(snapshot_id)

        # No need to rearrange with splitter - deletion handles it automatically

    def _clear_snapshots(self):
        """Clear all snapshots."""
        for panel in self.snapshot_panels:
            panel.deleteLater()

        self.snapshot_panels.clear()

        # Disable export button when no snapshots
        self.export_btn.setEnabled(False)

    def _reset_to_original(self):
        """Reset to original image and clear all processing."""
        # Note: Controls are already reset if called from controls.reset_requested signal
        # Reset engine - this will trigger on_processing_complete which updates preview
        self.engine.reset_to_original()

        # Select the Original node in the graph
        self.node_graph.select_node('root')

        # Clear panel highlights
        for panel in self.snapshot_panels:
            panel.setStyleSheet("")

        self.status_label.setText("Reset to original")

    def _open_file(self):
        """Open file dialog."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open File for Processing",
            "",
            "EM Files (*.nhdf *.dm3 *.dm4);;All Files (*)"
        )

        if file_path:
            self._load_file(file_path)

    def _load_file(self, file_path: str):
        """Load a file."""
        try:
            import pathlib
            data = read_em_file(pathlib.Path(file_path))
            if data:
                self.load_file(file_path, data)
        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Error", f"Failed to load file:\n{str(e)}")

    def _add_snapshot_to_graph(self, snapshot: ProcessingState):
        """Add a snapshot to the node graph."""
        # Use the parent_id from the snapshot itself (set by engine based on current_state_id)
        # This ensures proper branching: if we're working from Snapshot 1, new snapshot branches from it
        parent_id = snapshot.parent_id

        # Add to graph
        self.node_graph.add_node(
            node_id=snapshot.id,
            name=snapshot.name,
            parent_id=parent_id,
            params=snapshot.parameters
        )

        # Select the new snapshot so subsequent snapshots branch from it
        self.node_graph.select_node(snapshot.id)

    def _remove_snapshot_from_graph(self, snapshot_id: str):
        """Remove a snapshot from the node graph."""
        self.node_graph.remove_node(snapshot_id)

    def _on_graph_node_selected(self, node_id: str):
        """Handle graph node click - highlight corresponding panel."""
        if node_id and node_id != 'root':
            # Highlight corresponding snapshot panel
            for panel in self.snapshot_panels:
                if panel.snapshot.id == node_id:
                    panel.setStyleSheet("QFrame { border: 2px solid #4a90d9; }")
                else:
                    panel.setStyleSheet("")
        else:
            # Clear all highlights
            for panel in self.snapshot_panels:
                panel.setStyleSheet("")

    def _on_graph_node_activated(self, node_id: str):
        """Handle graph node double-click - load snapshot."""
        if node_id == 'root':
            self._reset_to_original()
        elif node_id:
            self._load_snapshot(node_id)

    def _panel_drag_enter(self, event: QDragEnterEvent, panel):
        """Handle drag enter on panel."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if path.lower().endswith(('.nhdf', '.dm3', '.dm4')):
                        event.acceptProposedAction()
                        panel.setStyleSheet("QFrame { border: 2px solid #4a90d9; }")
                        return

    def _panel_drag_leave(self, event, panel):
        """Handle drag leave on panel."""
        panel.setStyleSheet("")
        panel.setFrameStyle(QFrame.Box)

    def _panel_drop(self, event: QDropEvent):
        """Handle drop on panel."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith(('.nhdf', '.dm3', '.dm4')):
                        self._load_file(file_path)
                        event.acceptProposedAction()
                        return

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if path.lower().endswith(('.nhdf', '.dm3', '.dm4')):
                        event.acceptProposedAction()
                        return

    def dropEvent(self, event: QDropEvent):
        """Handle drop."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith(('.nhdf', '.dm3', '.dm4')):
                        self._load_file(file_path)
                        event.acceptProposedAction()
                        return

    def changeEvent(self, event):
        """Handle change events including palette/theme changes."""
        if event.type() == QEvent.PaletteChange:
            # Update all panel backgrounds when theme changes
            self._update_panel_backgrounds()
        super().changeEvent(event)

    def _update_panel_backgrounds(self):
        """Update all image panel backgrounds to match current theme."""
        bg_color = self.palette().window().color()

        # Update main panels
        if hasattr(self, 'original_panel') and self.original_panel:
            self.original_panel.image_view.view.setBackgroundColor(bg_color)
        if hasattr(self, 'preview_panel') and self.preview_panel:
            self.preview_panel.image_view.view.setBackgroundColor(bg_color)

        # Update snapshot panels
        for panel in self.snapshot_panels:
            panel.image_view.view.setBackgroundColor(bg_color)

    def _get_scale_info(self):
        """Get scale information from the loaded data."""
        if not self.nhdf_data:
            return None

        # Get calibration from the data
        calibrations = self.nhdf_data.dimensional_calibrations
        if calibrations and len(calibrations) >= 2:
            x_cal = calibrations[-1]
            if x_cal and hasattr(x_cal, 'scale') and x_cal.scale > 0:
                scale = x_cal.scale
                unit = x_cal.units if hasattr(x_cal, 'units') and x_cal.units else 'px'

                # Get image dimensions
                frame_shape = self.nhdf_data.frame_shape
                height, width = frame_shape if len(frame_shape) == 2 else (frame_shape[0], frame_shape[1])

                return (scale, unit, width, height)
        return None

    def _show_export_dialog(self, preselected_id: str = None):
        """Show the export dialog for all snapshots."""
        if not self.engine.states:
            QMessageBox.information(
                self, "No Snapshots",
                "Create some snapshots first before exporting."
            )
            return

        # Get scale info
        scale_info = self._get_scale_info()

        # Get original file path
        import pathlib
        file_path = pathlib.Path(self.current_file) if self.current_file else None

        # Create dialog
        dialog = ProcessingExportDialog(
            snapshots=self.engine.states,
            original_file_path=file_path,
            scale_info=scale_info,
            parent=self
        )

        # If preselected, only check that one
        if preselected_id:
            for item in dialog._snapshot_items:
                if item.snapshot.id == preselected_id:
                    item.checkbox.setChecked(True)
                else:
                    item.checkbox.setChecked(False)

        dialog.exec()

    def _export_single_snapshot(self, snapshot_id: str):
        """Export a single snapshot."""
        self._show_export_dialog(preselected_id=snapshot_id)