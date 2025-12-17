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
    calculate_polygon_area, euclidean_distance, match_voids, export_session_to_csv
)
from .pipette_detector import PipetteDetector


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
        self._contamination_zones: List[List[Tuple[float, float]]] = []
        self._pairings: List[VoidPairing] = []
        self._final_frame_index = 0

        # Pipette detector
        self._detector = PipetteDetector()

        # Session for batch accumulation
        self._session = SpeckmannSession()

        # Pipette state
        self._pipette_target = None  # 'initial', 'final', or 'contamination'

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

        # Left controls: Contamination and Matching
        left_controls = QVBoxLayout()

        # Contamination zones
        contam_group = QGroupBox("Contamination Zones")
        contam_layout = QHBoxLayout(contam_group)

        self._contam_pipette_btn = QPushButton("Add Zone")
        self._contam_pipette_btn.setCheckable(True)
        self._contam_pipette_btn.clicked.connect(lambda: self._start_pipette('contamination'))
        contam_layout.addWidget(self._contam_pipette_btn)

        self._contam_count_label = QLabel("Zones: 0")
        contam_layout.addWidget(self._contam_count_label)

        contam_layout.addStretch()

        self._clear_contam_btn = QPushButton("Clear All")
        self._clear_contam_btn.clicked.connect(self._clear_contamination)
        contam_layout.addWidget(self._clear_contam_btn)

        left_controls.addWidget(contam_group)

        # Matching parameters
        match_group = QGroupBox("Matching")
        match_layout = QHBoxLayout(match_group)

        match_layout.addWidget(QLabel("Tolerance:"))
        self._tolerance_spin = QDoubleSpinBox()
        self._tolerance_spin.setRange(0.5, 20.0)
        self._tolerance_spin.setValue(3.0)
        self._tolerance_spin.setSuffix(" nm")
        self._tolerance_spin.setSingleStep(0.5)
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

        # Results list
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout(results_group)

        # Stats row
        self._stats_label = QLabel("Grew: 0 | New: 0 | Unchanged: 0 | Disappeared: 0")
        results_layout.addWidget(self._stats_label)

        # Pairings list
        self._results_list = QListWidget()
        self._results_list.setMaximumHeight(150)
        results_layout.addWidget(self._results_list)

        controls_layout.addWidget(results_group, stretch=1)

        layout.addWidget(controls_container)

        # Bottom buttons
        button_layout = QHBoxLayout()

        self._add_batch_btn = QPushButton("Add to Batch")
        self._add_batch_btn.clicked.connect(self._add_to_batch)
        button_layout.addWidget(self._add_batch_btn)

        self._batch_label = QLabel("Batch: 0 experiments")
        button_layout.addWidget(self._batch_label)

        button_layout.addStretch()

        self._export_btn = QPushButton("Export CSV...")
        self._export_btn.clicked.connect(self._export_csv)
        button_layout.addWidget(self._export_btn)

        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.accept)
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
        self._contam_pipette_btn.setChecked(target == 'contamination')

        self._pipette_target = target if any([
            self._initial_pipette_btn.isChecked(),
            self._final_pipette_btn.isChecked(),
            self._contam_pipette_btn.isChecked()
        ]) else None

        # Enable pipette mode on appropriate preview
        self._initial_preview.set_pipette_mode(target == 'initial')
        self._final_preview.set_pipette_mode(target in ['final', 'contamination'])

    def _on_initial_click(self, x: float, y: float):
        """Handle click on initial frame preview."""
        if self._pipette_target != 'initial':
            return

        self._detect_void_at(x, y, 0, 'initial')

    def _on_final_click(self, x: float, y: float):
        """Handle click on final frame preview."""
        if self._pipette_target == 'final':
            self._detect_void_at(x, y, self._final_frame_index, 'final')
        elif self._pipette_target == 'contamination':
            self._detect_contamination_at(x, y)

    def _detect_void_at(self, x: float, y: float, frame_index: int, target: str):
        """Detect void at click position using pipette."""
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

        # Detect region
        result = self._detector.detect_region(frame_data, x, y, threshold_tolerance=0.15)
        if result is None:
            return

        # Finalize polygon with adaptive vertices
        vertices = self._detector.finalize_polygon(result, original_shape=frame_data.shape[:2])

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
        else:  # final
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

    def _detect_contamination_at(self, x: float, y: float):
        """Detect contamination zone at click position."""
        if self._nhdf_data is None:
            return

        # Get frame data (use final frame)
        data = self._nhdf_data.data
        if len(data.shape) == 2:
            frame_data = data
        elif len(data.shape) >= 3:
            if data.shape[2] <= 4:
                frame_data = data
            else:
                frame_data = data[self._final_frame_index] if self._final_frame_index < data.shape[0] else data[0]
        else:
            return

        # Detect region with higher tolerance for contamination
        result = self._detector.detect_region(frame_data, x, y, threshold_tolerance=0.25)
        if result is None:
            return

        vertices = self._detector.finalize_polygon(result, original_shape=frame_data.shape[:2])

        # Convert to nm coordinates
        vertices_nm = [(v[0] * self._calibration_scale, v[1] * self._calibration_scale)
                       for v in vertices]
        self._contamination_zones.append(vertices_nm)

        # Show on both previews
        self._initial_preview.add_polygon(vertices, color='red', label=f"C{len(self._contamination_zones)}")
        self._final_preview.add_polygon(vertices, color='red', label=f"C{len(self._contamination_zones)}")

        self._contam_count_label.setText(f"Zones: {len(self._contamination_zones)}")

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

        # Redraw contamination zones
        for i, zone in enumerate(self._contamination_zones):
            # Convert back to pixels
            vertices_px = [(v[0] / self._calibration_scale, v[1] / self._calibration_scale)
                          for v in zone]
            self._final_preview.add_polygon(vertices_px, color='red', label=f"C{i+1}")

        # Redraw voids
        for void in self._final_voids:
            self._final_preview.add_polygon(void.vertices, color='cyan', label=void.void_id)

    def _clear_contamination(self):
        """Clear all contamination zones."""
        self._contamination_zones.clear()

        # Redraw previews without contamination
        self._initial_preview.clear_polygons()
        for void in self._initial_voids:
            self._initial_preview.add_polygon(void.vertices, color='lime', label=void.void_id)

        self._final_preview.clear_polygons()
        for void in self._final_voids:
            self._final_preview.add_polygon(void.vertices, color='cyan', label=void.void_id)

        self._contam_count_label.setText("Zones: 0")

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

        # Run matching
        self._pairings = match_voids(
            initial_voids=self._initial_voids,
            final_voids=self._final_voids,
            source_center_nm=source_center,
            tolerance_nm=self._tolerance_spin.value(),
            growth_threshold_nm2=self._growth_spin.value(),
            contamination_zones=self._contamination_zones
        )

        self._update_results()

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

            if p.near_contamination:
                text += " ⚠️"

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
            pairings=self._pairings.copy(),
            contamination_zones=self._contamination_zones.copy()
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
        self._contamination_zones.clear()
        self._pairings.clear()

        self._initial_preview.clear_polygons()
        self._final_preview.clear_polygons()

        self._initial_count_label.setText("Voids: 0")
        self._final_count_label.setText("Voids: 0")
        self._contam_count_label.setText("Zones: 0")

        self._results_list.clear()
        self._stats_label.setText("Grew: 0 | New: 0 | Unchanged: 0 | Disappeared: 0")

        self._file_label.setText("File: --")
        self._temp_label.setText("Temp: --")

    def set_workspace(self, workspace):
        """Set the workspace reference."""
        self._workspace = workspace
        self._populate_panels()
