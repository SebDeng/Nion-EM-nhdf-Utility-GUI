"""
Speckmann Thermal Diffusion Analysis Dialog.

Side-by-side frame comparison for void evolution analysis.
Compare frame 0 (initial) vs user-selected frame (final).
"""

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QPushButton, QGroupBox, QDoubleSpinBox, QSpinBox, QWidget,
    QComboBox, QListWidget, QListWidgetItem, QSplitter, QFileDialog,
    QCheckBox, QMessageBox, QScrollArea, QFrame
)
from PySide6.QtGui import QColor, QBrush
import pyqtgraph as pg
import numpy as np
from typing import Optional, Tuple, List, Dict, Any
import os

from .speckmann_analysis_data import (
    VoidType, VoidSnapshot, VoidPairing, ExperimentAnalysis, SpeckmannSession,
    extract_temperature_from_path, get_subscan_center, calculate_proper_centroid,
    calculate_polygon_area, euclidean_distance, match_voids, export_session_to_csv,
    MatchingDebugInfo
)
from .pipette_detector import PipetteDetector
from .pipette_dialog import PipettePreviewDialog


class FramePreviewWidget(QWidget):
    """
    Single frame preview with polygon overlay.
    Used for both initial and final frame views.
    """

    # Signal when user clicks on image (for pipette detection)
    image_clicked = Signal(float, float)  # x, y in image coords

    def __init__(self, title: str = "Frame", parent=None):
        super().__init__(parent)
        self._title = title
        self._image_data = None
        self._calibration_scale = 1.0
        self._polygons = []  # List of polygon vertices
        self._polygon_items = []  # pyqtgraph items
        self._highlight_items = []  # Highlight markers
        self._pipette_mode = False

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Title label
        self._title_label = QLabel(self._title)
        self._title_label.setAlignment(Qt.AlignCenter)
        self._title_label.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self._title_label)

        # pyqtgraph widget
        self._graphics_widget = pg.GraphicsLayoutWidget()
        self._graphics_widget.setBackground('k')
        layout.addWidget(self._graphics_widget, stretch=1)

        # Create plot
        self._plot = self._graphics_widget.addPlot()
        self._plot.setAspectLocked(True)
        self._plot.hideAxis('left')
        self._plot.hideAxis('bottom')

        # Image item
        self._image_item = pg.ImageItem()
        self._plot.addItem(self._image_item)

        # Connect mouse click
        self._image_item.mouseClickEvent = self._on_image_click

    def _on_image_click(self, event):
        """Handle mouse click on image."""
        if self._pipette_mode and event.button() == Qt.LeftButton:
            pos = event.pos()
            self.image_clicked.emit(pos.x(), pos.y())
            event.accept()

    def set_image(self, data: np.ndarray, calibration_scale: float = 1.0):
        """Set the image data to display."""
        self._image_data = data
        self._calibration_scale = calibration_scale

        if data is not None:
            # Handle RGB vs grayscale
            if len(data.shape) == 3:
                display_data = np.mean(data, axis=2)
            else:
                display_data = data

            self._image_item.setImage(display_data.T)
            self._plot.autoRange()

    def set_pipette_mode(self, enabled: bool):
        """Enable/disable pipette click detection."""
        self._pipette_mode = enabled
        if enabled:
            self._graphics_widget.setCursor(Qt.CrossCursor)
        else:
            self._graphics_widget.setCursor(Qt.ArrowCursor)

    def add_polygon(self, vertices: List[Tuple[float, float]], color='c', label: str = None):
        """Add a polygon overlay to the preview."""
        if not vertices or len(vertices) < 3:
            return

        self._polygons.append(vertices)

        # Create polygon ROI (simplified - just draw outline)
        xs = [v[0] for v in vertices] + [vertices[0][0]]
        ys = [v[1] for v in vertices] + [vertices[0][1]]

        pen = pg.mkPen(color, width=2)
        plot_item = self._plot.plot(xs, ys, pen=pen)
        self._polygon_items.append(plot_item)

        # Add centroid marker
        centroid = calculate_proper_centroid(vertices)
        marker = pg.ScatterPlotItem(
            pos=[centroid],
            size=10,
            pen=pg.mkPen(color, width=2),
            brush=pg.mkBrush(color),
            symbol='o'
        )
        self._plot.addItem(marker)
        self._polygon_items.append(marker)

        # Add label if provided
        if label:
            text = pg.TextItem(label, color=color, anchor=(0.5, 1))
            text.setPos(centroid[0], centroid[1] - 5)
            self._plot.addItem(text)
            self._polygon_items.append(text)

    def clear_polygons(self):
        """Remove all polygon overlays."""
        for item in self._polygon_items:
            self._plot.removeItem(item)
        self._polygon_items.clear()
        self._polygons.clear()

    def get_polygons(self) -> List[List[Tuple[float, float]]]:
        """Get all polygon vertices."""
        return self._polygons.copy()

    def set_title(self, title: str):
        """Update the title label."""
        self._title = title
        self._title_label.setText(title)

    def highlight_void(self, centroid: Tuple[float, float], color='#FFFF00', label: str = None):
        """Add a highlight marker at a void's centroid."""
        self.clear_highlights()

        # Create large ring marker at centroid
        marker = pg.ScatterPlotItem(
            pos=[centroid],
            size=30,
            pen=pg.mkPen(color, width=3),
            brush=pg.mkBrush(None),
            symbol='o'
        )
        marker.setZValue(2000)
        self._plot.addItem(marker)
        self._highlight_items.append(marker)

        # Add label
        if label:
            text = pg.TextItem(label, color=color, anchor=(0.5, 2.0))
            text.setPos(centroid[0], centroid[1])
            text.setZValue(2001)
            font = text.textItem.font()
            font.setPointSize(12)
            font.setBold(True)
            text.textItem.setFont(font)
            self._plot.addItem(text)
            self._highlight_items.append(text)

    def clear_highlights(self):
        """Clear all highlight markers."""
        for item in self._highlight_items:
            try:
                self._plot.removeItem(item)
            except Exception:
                pass
        self._highlight_items.clear()


class SpeckmannAnalysisDialog(QDialog):
    """
    Main dialog for Speckmann thermal diffusion analysis.

    Provides side-by-side comparison of initial (frame 0) and final frames,
    with void detection, matching, and CSV export.
    """

    def __init__(self, workspace=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Speckmann Thermal Diffusion Analysis")
        self.setMinimumSize(1200, 800)

        self._workspace = workspace
        self._current_panel = None
        self._nhdf_data = None
        self._calibration_scale = 1.0

        # Analysis state
        self._initial_voids: List[VoidSnapshot] = []
        self._final_voids: List[VoidSnapshot] = []
        self._pairings: List[VoidPairing] = []
        self._final_frame_index = 0

        # Pipette detector
        self._detector = PipetteDetector()

        # Session for batch accumulation
        self._session = SpeckmannSession()

        # Pipette state
        self._pipette_target = None  # 'initial' or 'final'

        self._setup_ui()

        # Populate panel dropdown if workspace provided
        if workspace:
            self._populate_panels()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Header: Panel selection and file info
        header = self._create_header()
        layout.addWidget(header)

        # Main content: Side-by-side previews
        content_splitter = QSplitter(Qt.Horizontal)

        # Left: Initial frame
        initial_container = QWidget()
        initial_layout = QVBoxLayout(initial_container)
        initial_layout.setContentsMargins(0, 0, 0, 0)

        self._initial_preview = FramePreviewWidget("Initial Frame (0)")
        self._initial_preview.image_clicked.connect(self._on_initial_click)
        initial_layout.addWidget(self._initial_preview, stretch=1)

        # Initial frame controls
        initial_ctrl = QHBoxLayout()
        self._initial_pipette_btn = QPushButton("Pipette")
        self._initial_pipette_btn.setCheckable(True)
        self._initial_pipette_btn.clicked.connect(lambda: self._start_pipette('initial'))
        initial_ctrl.addWidget(self._initial_pipette_btn)

        self._initial_count_label = QLabel("Voids: 0")
        initial_ctrl.addWidget(self._initial_count_label)

        initial_ctrl.addStretch()

        self._clear_initial_btn = QPushButton("Clear")
        self._clear_initial_btn.clicked.connect(self._clear_initial_voids)
        initial_ctrl.addWidget(self._clear_initial_btn)

        initial_layout.addLayout(initial_ctrl)
        content_splitter.addWidget(initial_container)

        # Right: Final frame
        final_container = QWidget()
        final_layout = QVBoxLayout(final_container)
        final_layout.setContentsMargins(0, 0, 0, 0)

        self._final_preview = FramePreviewWidget("Final Frame")
        self._final_preview.image_clicked.connect(self._on_final_click)
        final_layout.addWidget(self._final_preview, stretch=1)

        # Final frame controls with slider
        final_ctrl = QVBoxLayout()

        # Frame slider
        slider_layout = QHBoxLayout()
        slider_layout.addWidget(QLabel("Frame:"))
        self._frame_slider = QSlider(Qt.Horizontal)
        self._frame_slider.setMinimum(0)
        self._frame_slider.setMaximum(100)
        self._frame_slider.valueChanged.connect(self._on_frame_changed)
        slider_layout.addWidget(self._frame_slider, stretch=1)

        self._frame_label = QLabel("0 / 0")
        self._frame_label.setMinimumWidth(80)
        slider_layout.addWidget(self._frame_label)

        final_ctrl.addLayout(slider_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        self._final_pipette_btn = QPushButton("Pipette")
        self._final_pipette_btn.setCheckable(True)
        self._final_pipette_btn.clicked.connect(lambda: self._start_pipette('final'))
        btn_layout.addWidget(self._final_pipette_btn)

        self._final_count_label = QLabel("Voids: 0")
        btn_layout.addWidget(self._final_count_label)

        btn_layout.addStretch()

        self._clear_final_btn = QPushButton("Clear")
        self._clear_final_btn.clicked.connect(self._clear_final_voids)
        btn_layout.addWidget(self._clear_final_btn)

        final_ctrl.addLayout(btn_layout)
        final_layout.addLayout(final_ctrl)

        content_splitter.addWidget(final_container)
        layout.addWidget(content_splitter, stretch=1)

        # Controls section
        controls_container = QWidget()
        controls_layout = QHBoxLayout(controls_container)

        # Left controls: Matching
        left_controls = QVBoxLayout()

        # Matching parameters
        match_group = QGroupBox("Matching")
        match_layout = QHBoxLayout(match_group)

        match_layout.addWidget(QLabel("Tolerance:"))
        self._tolerance_spin = QDoubleSpinBox()
        self._tolerance_spin.setRange(0.1, 100.0)
        self._tolerance_spin.setValue(10.0)  # Higher default for drift compensation
        self._tolerance_spin.setSuffix(" nm")
        self._tolerance_spin.setSingleStep(1.0)
        self._tolerance_spin.setToolTip(
            "Maximum centroid distance for matching voids.\n"
            "Increase if image drift causes matching failures.\n"
            "Default: 10 nm. Typical range: 5-30 nm."
        )
        match_layout.addWidget(self._tolerance_spin)

        match_layout.addWidget(QLabel("Growth threshold:"))
        self._growth_spin = QDoubleSpinBox()
        self._growth_spin.setRange(0.1, 5.0)
        self._growth_spin.setValue(0.5)
        self._growth_spin.setSuffix(" nm²")
        self._growth_spin.setSingleStep(0.1)
        match_layout.addWidget(self._growth_spin)

        match_layout.addStretch()

        self._match_btn = QPushButton("Auto-Match")
        self._match_btn.clicked.connect(self._run_matching)
        match_layout.addWidget(self._match_btn)

        left_controls.addWidget(match_group)

        controls_layout.addLayout(left_controls)

        # Right side: Results and Manual Classification
        right_controls = QVBoxLayout()

        # Results list
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout(results_group)

        # Stats row
        self._stats_label = QLabel("Grew: 0 | New: 0 | Unchanged: 0 | Disappeared: 0")
        results_layout.addWidget(self._stats_label)

        # Pairings list
        self._results_list = QListWidget()
        self._results_list.setMaximumHeight(120)
        self._results_list.itemClicked.connect(self._on_result_clicked)
        results_layout.addWidget(self._results_list)

        right_controls.addWidget(results_group)

        # Manual Classification
        manual_group = QGroupBox("Manual Classification")
        manual_layout = QVBoxLayout(manual_group)

        # Void selection row
        void_select_layout = QHBoxLayout()
        void_select_layout.addWidget(QLabel("Initial:"))
        self._initial_void_combo = QComboBox()
        self._initial_void_combo.setMinimumWidth(80)
        self._initial_void_combo.currentIndexChanged.connect(self._on_initial_void_selected)
        void_select_layout.addWidget(self._initial_void_combo)

        void_select_layout.addWidget(QLabel("Final:"))
        self._final_void_combo = QComboBox()
        self._final_void_combo.setMinimumWidth(80)
        self._final_void_combo.currentIndexChanged.connect(self._on_final_void_selected)
        void_select_layout.addWidget(self._final_void_combo)

        manual_layout.addLayout(void_select_layout)

        # Manual actions
        action_layout = QHBoxLayout()

        self._create_pair_btn = QPushButton("Create Pair")
        self._create_pair_btn.setToolTip("Match selected initial and final voids")
        self._create_pair_btn.clicked.connect(self._create_manual_pair)
        action_layout.addWidget(self._create_pair_btn)

        self._mark_new_btn = QPushButton("Mark New")
        self._mark_new_btn.setToolTip("Mark selected final void as newly nucleated")
        self._mark_new_btn.clicked.connect(self._mark_as_new)
        action_layout.addWidget(self._mark_new_btn)

        self._mark_merged_btn = QPushButton("Mark Merged")
        self._mark_merged_btn.setToolTip("Mark selected initial void as merged into final void")
        self._mark_merged_btn.clicked.connect(self._mark_as_merged)
        action_layout.addWidget(self._mark_merged_btn)

        manual_layout.addLayout(action_layout)

        # Delete pairing button
        delete_layout = QHBoxLayout()
        self._delete_pairing_btn = QPushButton("Delete Selected Pairing")
        self._delete_pairing_btn.clicked.connect(self._delete_selected_pairing)
        delete_layout.addWidget(self._delete_pairing_btn)
        delete_layout.addStretch()
        manual_layout.addLayout(delete_layout)

        right_controls.addWidget(manual_group)

        controls_layout.addLayout(right_controls, stretch=1)

        layout.addWidget(controls_container)

        # Bottom buttons
        button_layout = QHBoxLayout()

        # Save Session button - saves current state to workspace
        self._save_session_btn = QPushButton("Save Session")
        self._save_session_btn.setToolTip("Save current analysis to panel and trigger workspace save")
        self._save_session_btn.clicked.connect(self._save_session)
        button_layout.addWidget(self._save_session_btn)

        # Add to CSV directly (appends to temp-specific file)
        self._add_csv_btn = QPushButton("Add to CSV...")
        self._add_csv_btn.setToolTip("Append this analysis to a CSV file (organized by temperature)")
        self._add_csv_btn.clicked.connect(self._add_to_csv)
        button_layout.addWidget(self._add_csv_btn)

        self._add_batch_btn = QPushButton("Add to Batch")
        self._add_batch_btn.setToolTip("Add to in-memory batch for later export")
        self._add_batch_btn.clicked.connect(self._add_to_batch)
        button_layout.addWidget(self._add_batch_btn)

        self._batch_label = QLabel("Batch: 0 experiments")
        button_layout.addWidget(self._batch_label)

        button_layout.addStretch()

        self._export_btn = QPushButton("Export Batch...")
        self._export_btn.clicked.connect(self._export_csv)
        button_layout.addWidget(self._export_btn)

        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self._on_close)
        button_layout.addWidget(self._close_btn)

        layout.addLayout(button_layout)

    def _create_header(self) -> QWidget:
        """Create the header with panel selection and file info."""
        header = QWidget()
        layout = QHBoxLayout(header)

        layout.addWidget(QLabel("Panel:"))
        self._panel_combo = QComboBox()
        self._panel_combo.setMinimumWidth(200)
        self._panel_combo.currentIndexChanged.connect(self._on_panel_selected)
        layout.addWidget(self._panel_combo)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._populate_panels)
        layout.addWidget(self._refresh_btn)

        layout.addStretch()

        self._file_label = QLabel("File: --")
        layout.addWidget(self._file_label)

        self._temp_label = QLabel("Temp: --")
        self._temp_label.setStyleSheet("font-weight: bold; color: #ff9900;")
        layout.addWidget(self._temp_label)

        return header

    def _populate_panels(self):
        """Populate panel dropdown from workspace."""
        self._panel_combo.clear()
        self._panel_combo.addItem("-- Select Panel --", None)

        if not self._workspace:
            return

        # Get all panels from workspace
        panels = self._workspace.panels
        for i, panel in enumerate(panels):
            # Check if panel has a loaded file
            file_path = getattr(panel, 'current_file_path', None)
            if file_path:
                filename = os.path.basename(file_path)
                label = f"Panel {i+1}: {filename}"
            else:
                label = f"Panel {i+1} (empty)"

            self._panel_combo.addItem(label, panel)

    def _on_panel_selected(self, index: int):
        """Handle panel selection change."""
        # Save current panel state before switching
        if self._current_panel is not None:
            self._save_to_panel()

        panel = self._panel_combo.itemData(index)
        if panel is None:
            self._clear_all()
            return

        self._current_panel = panel
        display_panel = getattr(panel, 'display_panel', None) or getattr(panel, '_display_panel', None)

        if not display_panel:
            return

        # Get the data - it's stored as _data, not _nhdf_data
        self._nhdf_data = getattr(display_panel, '_data', None)
        if self._nhdf_data is None:
            return

        # Get calibration
        calibrations = getattr(self._nhdf_data, 'dimensional_calibrations', None)
        if calibrations and len(calibrations) > 0:
            self._calibration_scale = calibrations[-1].scale
        else:
            self._calibration_scale = 1.0

        # Update file info - use panel's file path as primary source
        filepath = getattr(panel, 'current_file_path', '') or getattr(self._nhdf_data, 'filepath', '')
        filename = os.path.basename(filepath) if filepath else ''
        self._file_label.setText(f"File: {filename}" if filename else "File: --")

        # Extract temperature from path
        temp = extract_temperature_from_path(filepath)
        if temp:
            self._temp_label.setText(f"Temp: {temp}°C")
        else:
            self._temp_label.setText("Temp: --")

        # Setup frame slider
        num_frames = getattr(self._nhdf_data, 'num_frames', 1)
        self._frame_slider.setMaximum(max(0, num_frames - 1))
        self._frame_slider.setValue(num_frames - 1)  # Default to last frame
        self._frame_label.setText(f"{num_frames - 1} / {num_frames - 1}")

        # Load initial frame (frame 0)
        self._load_frame(0, self._initial_preview, "Initial Frame (0)")

        # Load final frame
        self._final_frame_index = num_frames - 1
        self._load_frame(self._final_frame_index, self._final_preview,
                        f"Final Frame ({self._final_frame_index})")

        # Try to load saved analysis from panel
        self._load_from_panel()

        # Update void combos
        self._update_void_combos()

    def _load_frame(self, frame_index: int, preview: FramePreviewWidget, title: str):
        """Load a specific frame into a preview widget."""
        if self._nhdf_data is None:
            return

        data = self._nhdf_data.data
        if data is None:
            return

        # Extract frame
        if len(data.shape) == 2:
            frame_data = data
        elif len(data.shape) == 3:
            # Could be (frames, h, w) or (h, w, channels)
            if data.shape[2] <= 4:  # Likely RGB/RGBA
                frame_data = data
            else:  # Likely (frames, h, w)
                frame_data = data[frame_index] if frame_index < data.shape[0] else data[0]
        elif len(data.shape) == 4:
            # (frames, h, w, channels) - take frame
            frame_data = data[frame_index] if frame_index < data.shape[0] else data[0]
        else:
            frame_data = data

        preview.set_image(frame_data, self._calibration_scale)
        preview.set_title(title)

    def _on_frame_changed(self, value: int):
        """Handle frame slider change."""
        num_frames = self._frame_slider.maximum() + 1
        self._frame_label.setText(f"{value} / {num_frames - 1}")
        self._final_frame_index = value

        # Update final preview
        self._load_frame(value, self._final_preview, f"Final Frame ({value})")

        # Re-draw existing voids
        self._redraw_final_voids()

    def _start_pipette(self, target: str):
        """Start pipette detection mode for a target."""
        # Reset all buttons
        self._initial_pipette_btn.setChecked(target == 'initial')
        self._final_pipette_btn.setChecked(target == 'final')

        self._pipette_target = target if any([
            self._initial_pipette_btn.isChecked(),
            self._final_pipette_btn.isChecked()
        ]) else None

        # Enable pipette mode on appropriate preview
        self._initial_preview.set_pipette_mode(target == 'initial')
        self._final_preview.set_pipette_mode(target == 'final')

    def _on_initial_click(self, x: float, y: float):
        """Handle click on initial frame preview."""
        if self._pipette_target == 'initial':
            self._detect_void_at(x, y, 0, 'initial')

    def _on_final_click(self, x: float, y: float):
        """Handle click on final frame preview."""
        if self._pipette_target == 'final':
            self._detect_void_at(x, y, self._final_frame_index, 'final')

    def _detect_void_at(self, x: float, y: float, frame_index: int, target: str):
        """Detect void at click position using pipette with preview dialog."""
        if self._nhdf_data is None:
            return

        # Get frame data
        data = self._nhdf_data.data
        if len(data.shape) == 2:
            frame_data = data
        elif len(data.shape) >= 3:
            if data.shape[2] <= 4:
                frame_data = data
            else:
                frame_data = data[frame_index] if frame_index < data.shape[0] else data[0]
        else:
            return

        # Get calibration for the dialog
        calibrations = getattr(self._nhdf_data, 'dimensional_calibrations', None)
        calibration = calibrations[-1] if calibrations and len(calibrations) > 0 else None

        # Open pipette preview dialog for threshold adjustment
        dialog = PipettePreviewDialog(
            image_data=frame_data,
            click_x=x,
            click_y=y,
            calibration=calibration,
            parent=self
        )

        # Store target for use in callback
        self._pending_pipette_target = target
        self._pending_pipette_frame = frame_index

        # Connect signal and show dialog
        dialog.polygon_confirmed.connect(self._on_pipette_confirmed)

        if dialog.exec() != QDialog.Accepted:
            # User cancelled
            self._pending_pipette_target = None
            self._pending_pipette_frame = None

    def _on_pipette_confirmed(self, vertices: List[Tuple[float, float]]):
        """Handle confirmed polygon from pipette dialog."""
        if not vertices or len(vertices) < 3:
            return

        target = self._pending_pipette_target
        frame_index = self._pending_pipette_frame

        if target is None:
            return

        # Calculate metrics
        centroid = calculate_proper_centroid(vertices)
        area_px = calculate_polygon_area(vertices)
        area_nm2 = area_px * self._calibration_scale * self._calibration_scale
        centroid_nm = (centroid[0] * self._calibration_scale, centroid[1] * self._calibration_scale)

        # Create void snapshot
        if target == 'initial':
            void_id = f"I{len(self._initial_voids)+1:03d}"
            void = VoidSnapshot(
                void_id=void_id,
                frame_index=frame_index,
                centroid=centroid,
                centroid_nm=centroid_nm,
                area_px=area_px,
                area_nm2=area_nm2,
                vertices=vertices
            )
            self._initial_voids.append(void)
            self._initial_preview.add_polygon(vertices, color='lime', label=void_id)
            self._initial_count_label.setText(f"Voids: {len(self._initial_voids)}")
        elif target == 'final':
            void_id = f"F{len(self._final_voids)+1:03d}"
            void = VoidSnapshot(
                void_id=void_id,
                frame_index=frame_index,
                centroid=centroid,
                centroid_nm=centroid_nm,
                area_px=area_px,
                area_nm2=area_nm2,
                vertices=vertices
            )
            self._final_voids.append(void)
            self._final_preview.add_polygon(vertices, color='cyan', label=void_id)
            self._final_count_label.setText(f"Voids: {len(self._final_voids)}")

        # Clear pending state
        self._pending_pipette_target = None
        self._pending_pipette_frame = None

        # Update void combos for manual classification
        self._update_void_combos()

    def _clear_initial_voids(self):
        """Clear all initial voids."""
        self._initial_voids.clear()
        self._initial_preview.clear_polygons()
        self._initial_count_label.setText("Voids: 0")
        self._pairings.clear()
        self._update_results()

    def _clear_final_voids(self):
        """Clear all final voids."""
        self._final_voids.clear()
        self._final_preview.clear_polygons()
        self._final_count_label.setText("Voids: 0")
        self._pairings.clear()
        self._update_results()

    def _redraw_final_voids(self):
        """Redraw final voids after frame change."""
        self._final_preview.clear_polygons()

        # Redraw voids
        for void in self._final_voids:
            self._final_preview.add_polygon(void.vertices, color='cyan', label=void.void_id)

    def _run_matching(self):
        """Run automatic void matching."""
        if not self._initial_voids and not self._final_voids:
            QMessageBox.information(self, "No Voids", "Please detect voids in both frames first.")
            return

        # Get source center
        if self._nhdf_data:
            source_center = get_subscan_center(self._nhdf_data)
        else:
            source_center = (0, 0)

        # Run matching with debug info
        result = match_voids(
            initial_voids=self._initial_voids,
            final_voids=self._final_voids,
            source_center_nm=source_center,
            tolerance_nm=self._tolerance_spin.value(),
            growth_threshold_nm2=self._growth_spin.value(),
            return_debug=True
        )

        self._pairings, debug_info = result

        self._update_results()

        # Show debug summary if there were unmatched voids
        n_matched = len(debug_info.matched_pairs)
        n_initial = len(self._initial_voids)
        n_final = len(self._final_voids)

        if n_matched < min(n_initial, n_final) and n_initial > 0 and n_final > 0:
            # Some voids weren't matched - show debug info
            msg = f"Matching Results:\n\n"
            msg += f"Initial voids: {n_initial}\n"
            msg += f"Final voids: {n_final}\n"
            msg += f"Matched pairs: {n_matched}\n"
            msg += f"Tolerance used: {debug_info.tolerance_used:.1f} nm\n\n"

            if debug_info.min_distance < float('inf'):
                msg += f"Distance range: {debug_info.min_distance:.2f} - {debug_info.max_distance:.2f} nm\n\n"

            if debug_info.matched_pairs:
                msg += "Matched:\n"
                for i_id, f_id, dist in debug_info.matched_pairs[:5]:  # Show first 5
                    msg += f"  {i_id} ↔ {f_id}: {dist:.2f} nm\n"

            # Show closest unmatched pairs
            unmatched_dists = [(i, f, d) for i, f, d in debug_info.distance_matrix
                              if d > debug_info.tolerance_used]
            if unmatched_dists:
                unmatched_dists.sort(key=lambda x: x[2])
                msg += "\nClosest unmatched (increase tolerance?):\n"
                for i_id, f_id, dist in unmatched_dists[:3]:
                    msg += f"  {i_id} → {f_id}: {dist:.2f} nm\n"

            QMessageBox.information(self, "Matching Debug", msg)

    def _update_results(self):
        """Update the results display."""
        self._results_list.clear()

        # Count by type
        n_grew = n_new = n_unchanged = n_disappeared = 0

        for p in self._pairings:
            if p.void_type == VoidType.GREW:
                n_grew += 1
                color = QColor(0, 200, 0)
                text = f"{p.pairing_id}: grew ΔA={p.delta_A_nm2:.2f}nm² r={p.distance_to_source_nm:.1f}nm"
            elif p.void_type == VoidType.NEW:
                n_new += 1
                color = QColor(0, 150, 255)
                text = f"{p.pairing_id}: new A={p.final.area_nm2:.2f}nm² r={p.distance_to_source_nm:.1f}nm"
            elif p.void_type == VoidType.UNCHANGED:
                n_unchanged += 1
                color = QColor(150, 150, 150)
                text = f"{p.pairing_id}: unchanged ΔA={p.delta_A_nm2:.2f}nm²"
            else:  # DISAPPEARED
                n_disappeared += 1
                color = QColor(255, 100, 100)
                text = f"{p.pairing_id}: disappeared A₀={p.initial.area_nm2:.2f}nm²"

            # Add notes (contains distance info for troubleshooting)
            if p.notes:
                text += f" ({p.notes})"

            item = QListWidgetItem(text)
            item.setForeground(QBrush(color))
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, p.pairing_id)
            self._results_list.addItem(item)

        self._stats_label.setText(
            f"Grew: {n_grew} | New: {n_new} | Unchanged: {n_unchanged} | Disappeared: {n_disappeared}"
        )

    def _add_to_batch(self):
        """Add current analysis to batch."""
        if not self._pairings:
            QMessageBox.information(self, "No Results", "Please run matching first.")
            return

        if self._nhdf_data is None:
            return

        # Create experiment analysis
        filepath = getattr(self._nhdf_data, 'filepath', '')
        temp = extract_temperature_from_path(filepath)
        source_center = get_subscan_center(self._nhdf_data)
        fov = getattr(self._nhdf_data, 'context_fov_nm', None) or 2.0

        # Get timeseries for frame time
        ts = getattr(self._nhdf_data, 'timeseries', None)
        frame_time = 0.0
        if ts and len(ts) > 1:
            timestamps = [entry.get('timestamp', 0) for entry in ts]
            if len(timestamps) > 1:
                frame_time = (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1)

        exp = ExperimentAnalysis(
            experiment_id=f"E{len(self._session.experiments)+1:03d}",
            filename=os.path.basename(filepath),
            filepath=filepath,
            temperature_C=temp,
            subscan_center_x_nm=source_center[0],
            subscan_center_y_nm=source_center[1],
            subscan_fov_nm=fov,
            total_frames=getattr(self._nhdf_data, 'num_frames', 1),
            analyzed_frame=self._final_frame_index,
            frame_time_s=frame_time,
            electron_dose_e_per_nm2=None,  # Could calculate if probe current known
            initial_voids=self._initial_voids.copy(),
            final_voids=self._final_voids.copy(),
            pairings=self._pairings.copy()
        )
        exp.compute_statistics()

        self._session.experiments.append(exp)
        self._batch_label.setText(f"Batch: {len(self._session.experiments)} experiments")

        QMessageBox.information(self, "Added", f"Added {exp.experiment_id} to batch.")

    def _export_csv(self):
        """Export batch to CSV."""
        if not self._session.experiments:
            QMessageBox.information(self, "No Data", "Please add experiments to batch first.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "", "CSV Files (*.csv)"
        )

        if filepath:
            if not filepath.endswith('.csv'):
                filepath += '.csv'

            try:
                export_session_to_csv(self._session, filepath)
                QMessageBox.information(self, "Exported",
                                       f"Exported {len(self._session.experiments)} experiments to:\n{filepath}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))

    def _clear_all(self):
        """Clear all analysis state."""
        self._initial_voids.clear()
        self._final_voids.clear()
        self._pairings.clear()

        self._initial_preview.clear_polygons()
        self._final_preview.clear_polygons()

        self._initial_count_label.setText("Voids: 0")
        self._final_count_label.setText("Voids: 0")

        self._results_list.clear()
        self._stats_label.setText("Grew: 0 | New: 0 | Unchanged: 0 | Disappeared: 0")

        self._file_label.setText("File: --")
        self._temp_label.setText("Temp: --")

    def set_workspace(self, workspace):
        """Set the workspace reference."""
        self._workspace = workspace
        self._populate_panels()

    # ========================================================================
    # Visual Highlight Methods
    # ========================================================================

    def _on_result_clicked(self, item: QListWidgetItem):
        """Handle click on result list item - highlight the void(s)."""
        pairing_id = item.data(Qt.UserRole)
        if not pairing_id:
            return

        # Find the pairing
        pairing = None
        for p in self._pairings:
            if p.pairing_id == pairing_id:
                pairing = p
                break

        if not pairing:
            return

        # Highlight on previews
        if pairing.initial:
            self._initial_preview.highlight_void(
                pairing.initial.centroid,
                color='#FFFF00',
                label=pairing.initial.void_id
            )
        else:
            self._initial_preview.clear_highlights()

        if pairing.final:
            self._final_preview.highlight_void(
                pairing.final.centroid,
                color='#FFFF00',
                label=pairing.final.void_id
            )
        else:
            self._final_preview.clear_highlights()

    # ========================================================================
    # Manual Classification Methods
    # ========================================================================

    def _update_void_combos(self):
        """Update the void selection comboboxes."""
        # Save current selections
        curr_initial = self._initial_void_combo.currentData()
        curr_final = self._final_void_combo.currentData()

        # Update initial combo
        self._initial_void_combo.clear()
        self._initial_void_combo.addItem("-- Select --", None)
        for void in self._initial_voids:
            self._initial_void_combo.addItem(
                f"{void.void_id} ({void.area_nm2:.2f}nm²)",
                void.void_id
            )

        # Update final combo
        self._final_void_combo.clear()
        self._final_void_combo.addItem("-- Select --", None)
        for void in self._final_voids:
            self._final_void_combo.addItem(
                f"{void.void_id} ({void.area_nm2:.2f}nm²)",
                void.void_id
            )

        # Restore selections if still valid
        if curr_initial:
            idx = self._initial_void_combo.findData(curr_initial)
            if idx >= 0:
                self._initial_void_combo.setCurrentIndex(idx)
        if curr_final:
            idx = self._final_void_combo.findData(curr_final)
            if idx >= 0:
                self._final_void_combo.setCurrentIndex(idx)

    def _on_initial_void_selected(self, index: int):
        """Handle initial void selection - highlight it."""
        void_id = self._initial_void_combo.currentData()
        if void_id:
            for void in self._initial_voids:
                if void.void_id == void_id:
                    self._initial_preview.highlight_void(void.centroid, color='#00FF00', label=void_id)
                    break
        else:
            self._initial_preview.clear_highlights()

    def _on_final_void_selected(self, index: int):
        """Handle final void selection - highlight it."""
        void_id = self._final_void_combo.currentData()
        if void_id:
            for void in self._final_voids:
                if void.void_id == void_id:
                    self._final_preview.highlight_void(void.centroid, color='#00FFFF', label=void_id)
                    break
        else:
            self._final_preview.clear_highlights()

    def _get_source_center(self) -> Tuple[float, float]:
        """Get source center for distance calculations."""
        if self._nhdf_data:
            return get_subscan_center(self._nhdf_data)
        return (0, 0)

    def _create_manual_pair(self):
        """Create a manual pairing between selected initial and final voids."""
        initial_id = self._initial_void_combo.currentData()
        final_id = self._final_void_combo.currentData()

        if not initial_id or not final_id:
            QMessageBox.warning(self, "Select Voids",
                               "Please select both an initial and final void.")
            return

        # Find the voids
        initial_void = None
        final_void = None
        for v in self._initial_voids:
            if v.void_id == initial_id:
                initial_void = v
                break
        for v in self._final_voids:
            if v.void_id == final_id:
                final_void = v
                break

        if not initial_void or not final_void:
            return

        # Check if either is already paired
        for p in self._pairings:
            if p.initial and p.initial.void_id == initial_id:
                QMessageBox.warning(self, "Already Paired",
                                   f"{initial_id} is already paired.")
                return
            if p.final and p.final.void_id == final_id:
                QMessageBox.warning(self, "Already Paired",
                                   f"{final_id} is already paired.")
                return

        # Calculate metrics
        source_center = self._get_source_center()
        delta_A = final_void.area_nm2 - initial_void.area_nm2
        avg_centroid = (
            (initial_void.centroid_nm[0] + final_void.centroid_nm[0]) / 2,
            (initial_void.centroid_nm[1] + final_void.centroid_nm[1]) / 2
        )
        dist_to_source = euclidean_distance(avg_centroid, source_center)

        # Determine type
        growth_threshold = self._growth_spin.value()
        if delta_A > growth_threshold:
            void_type = VoidType.GREW
        elif delta_A < -growth_threshold:
            void_type = VoidType.GREW
        else:
            void_type = VoidType.UNCHANGED

        # Calculate sqrt(A0)/r
        sqrt_A0_over_r = None
        if initial_void.area_nm2 > 0 and dist_to_source > 0:
            sqrt_A0_over_r = np.sqrt(initial_void.area_nm2) / dist_to_source

        # Create pairing
        pairing = VoidPairing(
            pairing_id=f"P{len(self._pairings)+1:03d}",
            initial=initial_void,
            final=final_void,
            void_type=void_type,
            delta_A_nm2=delta_A,
            distance_to_source_nm=dist_to_source,
            sqrt_A0_over_r=sqrt_A0_over_r,
            near_contamination=False,
            notes="Manual pairing"
        )

        self._pairings.append(pairing)
        self._update_results()
        self._update_void_combos()

    def _mark_as_new(self):
        """Mark selected final void as newly nucleated."""
        final_id = self._final_void_combo.currentData()

        if not final_id:
            QMessageBox.warning(self, "Select Void",
                               "Please select a final void to mark as new.")
            return

        # Find the void
        final_void = None
        for v in self._final_voids:
            if v.void_id == final_id:
                final_void = v
                break

        if not final_void:
            return

        # Check if already paired
        for p in self._pairings:
            if p.final and p.final.void_id == final_id:
                QMessageBox.warning(self, "Already Paired",
                                   f"{final_id} is already in a pairing.")
                return

        # Calculate metrics
        source_center = self._get_source_center()
        dist_to_source = euclidean_distance(final_void.centroid_nm, source_center)

        # Create pairing
        pairing = VoidPairing(
            pairing_id=f"P{len(self._pairings)+1:03d}",
            initial=None,
            final=final_void,
            void_type=VoidType.NEW,
            delta_A_nm2=final_void.area_nm2,
            distance_to_source_nm=dist_to_source,
            sqrt_A0_over_r=None,
            near_contamination=False,
            notes="Manually marked as new"
        )

        self._pairings.append(pairing)
        self._update_results()
        self._update_void_combos()

    def _mark_as_merged(self):
        """Mark selected initial void as merged into selected final void."""
        initial_id = self._initial_void_combo.currentData()
        final_id = self._final_void_combo.currentData()

        if not initial_id:
            QMessageBox.warning(self, "Select Void",
                               "Please select an initial void that disappeared (merged).")
            return

        # Find the void
        initial_void = None
        for v in self._initial_voids:
            if v.void_id == initial_id:
                initial_void = v
                break

        if not initial_void:
            return

        # Check if already paired
        for p in self._pairings:
            if p.initial and p.initial.void_id == initial_id:
                QMessageBox.warning(self, "Already Paired",
                                   f"{initial_id} is already in a pairing.")
                return

        # Calculate metrics
        source_center = self._get_source_center()
        dist_to_source = euclidean_distance(initial_void.centroid_nm, source_center)

        # Build notes
        notes = "Manually marked as merged"
        if final_id:
            notes += f" into {final_id}"

        # Create pairing
        pairing = VoidPairing(
            pairing_id=f"P{len(self._pairings)+1:03d}",
            initial=initial_void,
            final=None,
            void_type=VoidType.DISAPPEARED,
            delta_A_nm2=-initial_void.area_nm2,
            distance_to_source_nm=dist_to_source,
            sqrt_A0_over_r=None,
            near_contamination=False,
            notes=notes
        )

        self._pairings.append(pairing)
        self._update_results()
        self._update_void_combos()

    def _delete_selected_pairing(self):
        """Delete the selected pairing from results list."""
        current_item = self._results_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Selection",
                               "Please select a pairing to delete.")
            return

        pairing_id = current_item.data(Qt.UserRole)
        if not pairing_id:
            return

        # Remove from pairings
        self._pairings = [p for p in self._pairings if p.pairing_id != pairing_id]

        self._update_results()
        self._update_void_combos()
        self._initial_preview.clear_highlights()
        self._final_preview.clear_highlights()

    # ========================================================================
    # CSV Export Methods
    # ========================================================================

    def _add_to_csv(self):
        """Add current analysis directly to a CSV file in the session directory."""
        if not self._pairings:
            QMessageBox.information(self, "No Results",
                                   "Please create pairings first (auto-match or manual).")
            return

        if self._nhdf_data is None:
            return

        # Get temperature for default filename
        filepath = getattr(self._current_panel, 'current_file_path', '') or \
                   getattr(self._nhdf_data, 'filepath', '')
        temp = extract_temperature_from_path(filepath)
        csv_filename = f"speckmann_{temp}C.csv" if temp else "speckmann_analysis.csv"

        # Get session directory from main window
        csv_dir = None
        if self._workspace:
            main_window = self._workspace.window()
            if main_window and hasattr(main_window, '_session_manager'):
                session_path = main_window._session_manager.current_session_path
                if session_path:
                    csv_dir = os.path.dirname(session_path)

        # If no session directory, use the file's directory
        if not csv_dir:
            csv_dir = os.path.dirname(filepath) if filepath else os.getcwd()

        csv_path = os.path.join(csv_dir, csv_filename)

        # Create experiment
        exp = self._create_experiment_analysis()
        if not exp:
            return

        # Check if file exists - append or create
        import csv
        file_exists = os.path.exists(csv_path)

        try:
            with open(csv_path, 'a', newline='') as f:
                writer = csv.writer(f)

                # Write headers if new file
                if not file_exists:
                    writer.writerow(['# Speckmann Analysis Results'])
                    writer.writerow(['# Temperature: ' + (f'{temp}°C' if temp else 'Unknown')])
                    writer.writerow([])
                    writer.writerow([
                        'filename', 'temperature_C',
                        'void_id', 'void_type', 'initial_area_nm2', 'final_area_nm2',
                        'delta_A_nm2', 'distance_to_source_nm', 'sqrt_A0_over_r',
                        'notes'
                    ])

                # Write pairings
                for p in exp.pairings:
                    void_id = p.final.void_id if p.final else p.initial.void_id
                    writer.writerow([
                        exp.filename,
                        exp.temperature_C if exp.temperature_C else '',
                        void_id,
                        p.void_type.value,
                        f"{p.initial.area_nm2:.3f}" if p.initial else '0',
                        f"{p.final.area_nm2:.3f}" if p.final else '0',
                        f"{p.delta_A_nm2:.3f}",
                        f"{p.distance_to_source_nm:.2f}",
                        f"{p.sqrt_A0_over_r:.4f}" if p.sqrt_A0_over_r else '',
                        p.notes
                    ])

            action = "Appended to" if file_exists else "Created"
            QMessageBox.information(self, "Success",
                                   f"{action} CSV:\n{csv_path}\n\n"
                                   f"Added {len(exp.pairings)} pairings.")

        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _create_experiment_analysis(self) -> Optional[ExperimentAnalysis]:
        """Create an ExperimentAnalysis from current state."""
        if self._nhdf_data is None:
            return None

        filepath = getattr(self._current_panel, 'current_file_path', '') or \
                   getattr(self._nhdf_data, 'filepath', '')
        temp = extract_temperature_from_path(filepath)
        source_center = get_subscan_center(self._nhdf_data)
        fov = getattr(self._nhdf_data, 'context_fov_nm', None) or 2.0

        # Get timeseries for frame time
        ts = getattr(self._nhdf_data, 'timeseries', None)
        frame_time = 0.0
        if ts and len(ts) > 1:
            timestamps = [entry.get('timestamp', 0) for entry in ts]
            if len(timestamps) > 1:
                frame_time = (timestamps[-1] - timestamps[0]) / (len(timestamps) - 1)

        exp = ExperimentAnalysis(
            experiment_id=f"E{len(self._session.experiments)+1:03d}",
            filename=os.path.basename(filepath),
            filepath=filepath,
            temperature_C=temp,
            subscan_center_x_nm=source_center[0],
            subscan_center_y_nm=source_center[1],
            subscan_fov_nm=fov,
            total_frames=getattr(self._nhdf_data, 'num_frames', 1),
            analyzed_frame=self._final_frame_index,
            frame_time_s=frame_time,
            electron_dose_e_per_nm2=None,
            initial_voids=self._initial_voids.copy(),
            final_voids=self._final_voids.copy(),
            pairings=self._pairings.copy()
        )
        exp.compute_statistics()
        return exp

    # ========================================================================
    # Panel State Persistence
    # ========================================================================

    def _save_to_panel(self):
        """Save analysis state to the current panel for persistence."""
        if not self._current_panel:
            return

        # Create state dict
        state = {
            'initial_voids': [v.to_dict() for v in self._initial_voids],
            'final_voids': [v.to_dict() for v in self._final_voids],
            'pairings': [p.to_dict() for p in self._pairings],
            'final_frame_index': self._final_frame_index,
            'tolerance_nm': self._tolerance_spin.value(),
            'growth_threshold_nm2': self._growth_spin.value(),
        }

        # Store on panel
        self._current_panel.speckmann_analysis_state = state

    def _load_from_panel(self):
        """Load analysis state from the current panel."""
        if not self._current_panel:
            return

        state = getattr(self._current_panel, 'speckmann_analysis_state', None)
        if not state:
            # No saved state - clear everything
            self._initial_voids = []
            self._final_voids = []
            self._pairings = []
            self._initial_preview.clear_polygons()
            self._final_preview.clear_polygons()
            self._initial_count_label.setText("Voids: 0")
            self._final_count_label.setText("Voids: 0")
            self._results_list.clear()
            self._stats_label.setText("Grew: 0 | New: 0 | Unchanged: 0 | Disappeared: 0")
            return

        # Restore state
        self._initial_voids = [VoidSnapshot.from_dict(d) for d in state.get('initial_voids', [])]
        self._final_voids = [VoidSnapshot.from_dict(d) for d in state.get('final_voids', [])]
        self._pairings = [VoidPairing.from_dict(d) for d in state.get('pairings', [])]
        self._final_frame_index = state.get('final_frame_index', 0)

        # Restore parameters
        self._tolerance_spin.setValue(state.get('tolerance_nm', 10.0))
        self._growth_spin.setValue(state.get('growth_threshold_nm2', 0.5))

        # Update frame slider and reload final frame
        self._frame_slider.blockSignals(True)
        self._frame_slider.setValue(self._final_frame_index)
        self._frame_slider.blockSignals(False)
        self._frame_label.setText(f"{self._final_frame_index} / {self._frame_slider.maximum()}")

        # Reload final frame with correct frame index
        self._load_frame(self._final_frame_index, self._final_preview,
                        f"Final Frame ({self._final_frame_index})")

        # Redraw all polygons on both previews
        self._redraw_all_polygons()
        self._update_results()
        self._update_void_combos()

        # Update counts
        self._initial_count_label.setText(f"Voids: {len(self._initial_voids)}")
        self._final_count_label.setText(f"Voids: {len(self._final_voids)}")

    def _redraw_all_polygons(self):
        """Redraw all polygons on both previews."""
        # Clear
        self._initial_preview.clear_polygons()
        self._final_preview.clear_polygons()

        # Redraw initial voids
        for void in self._initial_voids:
            self._initial_preview.add_polygon(void.vertices, color='lime', label=void.void_id)

        # Redraw final voids
        for void in self._final_voids:
            self._final_preview.add_polygon(void.vertices, color='cyan', label=void.void_id)

    def _save_session(self):
        """Save current analysis to panel and trigger workspace save."""
        # Save to panel
        self._save_to_panel()

        # Trigger workspace save via parent window
        if self._workspace:
            main_window = self._workspace.window()
            if main_window and hasattr(main_window, '_on_save_session'):
                # Call the save session method
                success = main_window._on_save_session()
                if success:
                    QMessageBox.information(self, "Saved",
                                           "Analysis saved to panel and workspace session saved.")
                else:
                    QMessageBox.information(self, "Saved",
                                           "Analysis saved to panel.\n"
                                           "Session save was cancelled or failed.")
            else:
                QMessageBox.information(self, "Saved",
                                       "Analysis saved to panel.\n"
                                       "Use File > Save Session to save workspace.")
        else:
            QMessageBox.information(self, "Saved", "Analysis saved to panel.")

    def _on_close(self):
        """Handle close button - save state and close."""
        self._save_to_panel()
        self.accept()
