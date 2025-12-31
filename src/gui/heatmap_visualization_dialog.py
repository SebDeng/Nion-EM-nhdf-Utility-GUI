"""
Heat Map Visualization Dialog for Hole Pairing Tool.

Generates a heat map showing ΔA (area change) for paired holes using
an ice-fire colormap. Blue = shrinking, White = neutral, Red = growing.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QGroupBox, QDoubleSpinBox, QSpinBox,
    QCheckBox, QSplitter, QWidget, QFileDialog, QMessageBox,
    QSlider
)
from PySide6.QtCore import Qt

import numpy as np
from typing import Optional, List, Tuple
import os

# matplotlib imports for rendering
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.collections import PatchCollection
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm, Normalize

from src.gui.hole_pairing_data import PairingSession, HoleReference


class HeatMapVisualizationDialog(QDialog):
    """
    Dialog for visualizing ΔA (area change) as a heat map overlay on images.

    Features:
    - Ice-fire colormap: Blue (shrinking) → White (zero) → Red (growing)
    - Filled polygon overlays with adjustable opacity
    - Unpaired holes shown in gray
    - Colorbar legend showing ΔA scale
    - Export to PNG
    """

    def __init__(self, session: PairingSession, workspace, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ΔA Heat Map Visualization")
        self.setMinimumSize(1000, 700)
        self.setModal(True)

        self._session = session
        self._workspace = workspace

        # Create ice-fire colormap
        self._cmap = self._create_ice_fire_cmap()

        # Regenerate missing vertices from panel polygons
        self._regenerate_missing_vertices()

        # Setup UI
        self._setup_ui()
        self._connect_signals()

        # Initial preview
        self._update_preview()

    def _regenerate_missing_vertices(self):
        """Regenerate vertices for pairings that are missing them."""
        # Get all holes from both panels
        before_holes = {}
        after_holes = {}

        if self._session.before_panel_id:
            for hole in self._get_all_holes_from_panel(self._session.before_panel_id):
                before_holes[hole.polygon_id] = hole.vertices

        if self._session.after_panel_id:
            for hole in self._get_all_holes_from_panel(self._session.after_panel_id):
                after_holes[hole.polygon_id] = hole.vertices

        # Update pairings with missing vertices
        for pairing in self._session.sink_pairings:
            if pairing.before_hole:
                if not pairing.before_hole.vertices or len(pairing.before_hole.vertices) < 3:
                    if pairing.before_hole.polygon_id in before_holes:
                        pairing.before_hole.vertices = before_holes[pairing.before_hole.polygon_id]

            if pairing.after_hole:
                if not pairing.after_hole.vertices or len(pairing.after_hole.vertices) < 3:
                    if pairing.after_hole.polygon_id in after_holes:
                        pairing.after_hole.vertices = after_holes[pairing.after_hole.polygon_id]

    def _create_ice_fire_cmap(self) -> LinearSegmentedColormap:
        """Create a diverging ice-fire colormap: blue → white → red."""
        colors = ['#0077FF', '#FFFFFF', '#FF3300']  # ice (blue) - neutral - fire (red)
        return LinearSegmentedColormap.from_list('ice_fire', colors, N=256)

    def _setup_ui(self):
        """Setup the dialog UI with controls and preview."""
        layout = QVBoxLayout(self)

        # Main splitter: controls | preview
        splitter = QSplitter(Qt.Horizontal)

        # === Left Panel: Controls ===
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(10, 10, 10, 10)

        # Panel Selection Group
        panel_group = QGroupBox("Image Source")
        panel_layout = QVBoxLayout(panel_group)

        panel_row = QHBoxLayout()
        panel_row.addWidget(QLabel("Show:"))
        self._panel_combo = QComboBox()
        self._panel_combo.addItem("Before Panel", "before")
        self._panel_combo.addItem("After Panel", "after")
        panel_row.addWidget(self._panel_combo)
        panel_layout.addLayout(panel_row)

        controls_layout.addWidget(panel_group)

        # Color Options Group
        color_group = QGroupBox("Color Options")
        color_layout = QVBoxLayout(color_group)

        # Opacity slider
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Opacity:"))
        self._opacity_slider = QSlider(Qt.Horizontal)
        self._opacity_slider.setRange(10, 100)
        self._opacity_slider.setValue(70)
        self._opacity_slider.setTickPosition(QSlider.TicksBelow)
        self._opacity_slider.setTickInterval(10)
        opacity_row.addWidget(self._opacity_slider)
        self._opacity_label = QLabel("70%")
        self._opacity_label.setMinimumWidth(40)
        opacity_row.addWidget(self._opacity_label)
        color_layout.addLayout(opacity_row)

        # Show unpaired checkbox
        self._show_unpaired_cb = QCheckBox("Show unpaired holes (gray)")
        self._show_unpaired_cb.setChecked(True)
        color_layout.addWidget(self._show_unpaired_cb)

        # Show colorbar checkbox
        self._show_colorbar_cb = QCheckBox("Show colorbar legend")
        self._show_colorbar_cb.setChecked(True)
        color_layout.addWidget(self._show_colorbar_cb)

        controls_layout.addWidget(color_group)

        # Export Options Group
        export_group = QGroupBox("Export Options")
        export_layout = QVBoxLayout(export_group)

        # Width
        width_row = QHBoxLayout()
        width_row.addWidget(QLabel("Width:"))
        self._width_spin = QSpinBox()
        self._width_spin.setRange(400, 4000)
        self._width_spin.setValue(1200)
        self._width_spin.setSuffix(" px")
        width_row.addWidget(self._width_spin)
        export_layout.addLayout(width_row)

        # Height
        height_row = QHBoxLayout()
        height_row.addWidget(QLabel("Height:"))
        self._height_spin = QSpinBox()
        self._height_spin.setRange(400, 4000)
        self._height_spin.setValue(1000)
        self._height_spin.setSuffix(" px")
        height_row.addWidget(self._height_spin)
        export_layout.addLayout(height_row)

        # DPI
        dpi_row = QHBoxLayout()
        dpi_row.addWidget(QLabel("DPI:"))
        self._dpi_spin = QSpinBox()
        self._dpi_spin.setRange(72, 600)
        self._dpi_spin.setValue(150)
        dpi_row.addWidget(self._dpi_spin)
        export_layout.addLayout(dpi_row)

        controls_layout.addWidget(export_group)

        # Statistics Label
        self._stats_label = QLabel("No data")
        self._stats_label.setWordWrap(True)
        self._stats_label.setStyleSheet("color: #888; font-size: 11px; padding: 8px;")
        controls_layout.addWidget(self._stats_label)

        controls_layout.addStretch()

        # Export Button
        self._export_btn = QPushButton("Export PNG...")
        self._export_btn.setStyleSheet("font-weight: bold; padding: 8px;")
        controls_layout.addWidget(self._export_btn)

        # Close Button
        self._close_btn = QPushButton("Close")
        controls_layout.addWidget(self._close_btn)

        splitter.addWidget(controls_widget)

        # === Right Panel: Preview ===
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        # matplotlib figure and canvas
        self._figure = Figure(figsize=(8, 6), dpi=100)
        self._canvas = FigureCanvas(self._figure)
        preview_layout.addWidget(self._canvas)

        splitter.addWidget(preview_widget)

        # Set splitter sizes (30% controls, 70% preview)
        splitter.setSizes([300, 700])

        layout.addWidget(splitter)

    def _connect_signals(self):
        """Connect UI signals."""
        self._panel_combo.currentIndexChanged.connect(self._update_preview)
        self._opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self._show_unpaired_cb.stateChanged.connect(self._update_preview)
        self._show_colorbar_cb.stateChanged.connect(self._update_preview)
        self._export_btn.clicked.connect(self._export_image)
        self._close_btn.clicked.connect(self.close)

    def _on_opacity_changed(self, value: int):
        """Handle opacity slider change."""
        self._opacity_label.setText(f"{value}%")
        self._update_preview()

    def _get_panel_image(self, panel_id: str) -> Optional[np.ndarray]:
        """Get the image data from a panel."""
        if not self._workspace:
            return None

        panel = self._workspace.get_panel_by_id(panel_id)
        if not panel:
            return None

        display_panel = getattr(panel, 'display_panel', None) or getattr(panel, '_display_panel', None)
        if not display_panel:
            return None

        nhdf_data = getattr(display_panel, '_data', None)
        if not nhdf_data:
            return None

        data = nhdf_data.data
        if data is None:
            return None

        # Get current frame
        current_frame = getattr(display_panel, '_current_frame', 0)

        # Extract 2D frame
        if len(data.shape) == 2:
            return data
        elif len(data.shape) == 3:
            if data.shape[2] <= 4:  # RGB/RGBA
                return np.mean(data, axis=2)  # Convert to grayscale
            else:  # (frames, h, w)
                return data[current_frame] if current_frame < data.shape[0] else data[0]
        elif len(data.shape) == 4:
            frame = data[current_frame] if current_frame < data.shape[0] else data[0]
            if frame.shape[2] <= 4:
                return np.mean(frame, axis=2)
            return frame

        return data

    def _get_all_holes_from_panel(self, panel_id: str) -> List[HoleReference]:
        """Get all polygon holes from a panel's measurement overlay."""
        if not self._workspace:
            return []

        panel = self._workspace.get_panel_by_id(panel_id)
        if not panel:
            return []

        display_panel = getattr(panel, 'display_panel', None) or getattr(panel, '_display_panel', None)
        if not display_panel:
            return []

        measurement_overlay = getattr(display_panel, '_measurement_overlay', None)
        if not measurement_overlay:
            return []

        # Get calibration
        calibration = getattr(measurement_overlay, 'calibration', None)
        cal_scale = calibration.scale if calibration and hasattr(calibration, 'scale') else 1.0

        # Get polygons
        polygon_rois = getattr(measurement_overlay, 'active_polygon_rois', [])
        holes = []

        for roi in polygon_rois:
            vertices = []
            try:
                handles = roi.getLocalHandlePositions()
                roi_pos = roi.pos()
                for _, handle_pos in handles:
                    x = roi_pos.x() + handle_pos.x()
                    y = roi_pos.y() + handle_pos.y()
                    vertices.append((x, y))
            except Exception:
                continue

            if len(vertices) < 3:
                continue

            polygon_id = getattr(roi, '_polygon_id', None) or getattr(roi, '_measurement_id', 0)

            # Calculate area
            area_px = self._calculate_polygon_area(vertices)
            area_nm2 = area_px * (cal_scale ** 2)

            # Calculate centroid
            centroid = self._calculate_centroid(vertices)

            holes.append(HoleReference(
                panel_id=panel_id,
                polygon_id=polygon_id,
                centroid=centroid,
                area_nm2=area_nm2,
                area_px=area_px,
                vertices=vertices
            ))

        return holes

    def _calculate_polygon_area(self, vertices: List[Tuple[float, float]]) -> float:
        """Calculate polygon area using shoelace formula."""
        n = len(vertices)
        if n < 3:
            return 0.0

        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += vertices[i][0] * vertices[j][1]
            area -= vertices[j][0] * vertices[i][1]

        return abs(area) / 2.0

    def _calculate_centroid(self, vertices: List[Tuple[float, float]]) -> Tuple[float, float]:
        """Calculate polygon centroid."""
        n = len(vertices)
        if n == 0:
            return (0.0, 0.0)
        if n < 3:
            return (sum(v[0] for v in vertices) / n, sum(v[1] for v in vertices) / n)

        signed_area = 0.0
        cx = cy = 0.0

        for i in range(n):
            j = (i + 1) % n
            cross = vertices[i][0] * vertices[j][1] - vertices[j][0] * vertices[i][1]
            signed_area += cross
            cx += (vertices[i][0] + vertices[j][0]) * cross
            cy += (vertices[i][1] + vertices[j][1]) * cross

        signed_area *= 0.5
        if abs(signed_area) < 1e-10:
            return (sum(v[0] for v in vertices) / n, sum(v[1] for v in vertices) / n)

        cx /= (6.0 * signed_area)
        cy /= (6.0 * signed_area)

        return (cx, cy)

    def _update_preview(self):
        """Update the matplotlib preview."""
        self._figure.clear()

        # Get selected panel
        panel_type = self._panel_combo.currentData()
        panel_id = self._session.before_panel_id if panel_type == "before" else self._session.after_panel_id

        if not panel_id:
            ax = self._figure.add_subplot(111)
            ax.text(0.5, 0.5, "No panel selected", ha='center', va='center', fontsize=14)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            self._canvas.draw()
            return

        # Get image
        image = self._get_panel_image(panel_id)
        if image is None:
            ax = self._figure.add_subplot(111)
            ax.text(0.5, 0.5, "No image data", ha='center', va='center', fontsize=14)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            self._canvas.draw()
            return

        # Create subplot
        ax = self._figure.add_subplot(111)

        # Display image in grayscale
        ax.imshow(image, cmap='gray', origin='upper')

        # Get confirmed pairings
        confirmed_pairings = self._session.get_confirmed_pairings()

        # Collect ΔA values for normalization
        delta_values = [p.area_change_nm2 for p in confirmed_pairings]

        if delta_values:
            # Get min/max for normalization
            vmin = min(delta_values)
            vmax = max(delta_values)

            # Handle edge cases
            if vmin >= 0:
                vmin = -max(abs(vmax), 0.1)
            if vmax <= 0:
                vmax = max(abs(vmin), 0.1)

            # Use TwoSlopeNorm for diverging colormap centered at 0
            norm = TwoSlopeNorm(vmin=vmin, vcenter=0, vmax=vmax)
        else:
            norm = Normalize(vmin=-1, vmax=1)

        # Opacity
        alpha = self._opacity_slider.value() / 100.0

        # Draw paired polygons with colors
        paired_patches = []
        paired_colors = []

        for pairing in confirmed_pairings:
            # Get the appropriate hole based on panel selection
            hole = pairing.before_hole if panel_type == "before" else pairing.after_hole
            if hole and hole.vertices:
                polygon = MplPolygon(hole.vertices, closed=True)
                paired_patches.append(polygon)
                paired_colors.append(pairing.area_change_nm2)

        if paired_patches:
            collection = PatchCollection(
                paired_patches,
                cmap=self._cmap,
                norm=norm,
                alpha=alpha,
                edgecolor='black',
                linewidth=1.5,
                match_original=False  # Required for colormap to control facecolors
            )
            collection.set_array(np.array(paired_colors))
            collection.set_clim(vmin=norm.vmin, vmax=norm.vmax)
            ax.add_collection(collection)

            # Add colorbar if enabled
            if self._show_colorbar_cb.isChecked():
                cbar = self._figure.colorbar(collection, ax=ax, shrink=0.8, pad=0.02)
                cbar.set_label('ΔA (nm²)', fontsize=10)

        # Draw unpaired holes in gray if enabled
        if self._show_unpaired_cb.isChecked():
            # Get all holes from the panel
            all_holes = self._get_all_holes_from_panel(panel_id)

            # Find paired polygon IDs
            paired_ids = set()
            for pairing in confirmed_pairings:
                hole = pairing.before_hole if panel_type == "before" else pairing.after_hole
                if hole:
                    paired_ids.add(hole.polygon_id)

            # Draw unpaired holes
            unpaired_patches = []
            for hole in all_holes:
                if hole.polygon_id not in paired_ids and hole.vertices:
                    polygon = MplPolygon(hole.vertices, closed=True)
                    unpaired_patches.append(polygon)

            if unpaired_patches:
                unpaired_collection = PatchCollection(
                    unpaired_patches,
                    facecolor='#888888',
                    alpha=alpha * 0.7,
                    edgecolor='#666666',
                    linewidth=1
                )
                ax.add_collection(unpaired_collection)

        # Set axis properties
        ax.set_xlim(0, image.shape[1])
        ax.set_ylim(0, image.shape[0])  # Y axis: 0 at bottom, height at top
        ax.set_aspect('equal')
        ax.axis('off')

        # Update statistics
        n_paired = len(confirmed_pairings)
        n_growing = sum(1 for p in confirmed_pairings if p.area_change_nm2 > 0)
        n_shrinking = sum(1 for p in confirmed_pairings if p.area_change_nm2 < 0)

        # Count how many pairings have vertices stored
        n_with_vertices = 0
        for p in confirmed_pairings:
            hole = p.before_hole if panel_type == "before" else p.after_hole
            if hole and hole.vertices and len(hole.vertices) >= 3:
                n_with_vertices += 1

        if delta_values:
            avg_delta = np.mean(delta_values)
            stats_text = (
                f"Paired holes: {n_paired}\n"
                f"With vertices: {n_with_vertices}\n"
                f"Growing (red): {n_growing}\n"
                f"Shrinking (blue): {n_shrinking}\n"
                f"Avg ΔA: {avg_delta:.2f} nm²\n"
                f"Range: [{min(delta_values):.2f}, {max(delta_values):.2f}] nm²"
            )
        else:
            stats_text = "No paired holes to display"

        self._stats_label.setText(stats_text)

        self._figure.tight_layout()
        self._canvas.draw()

    def _export_image(self):
        """Export the visualization to a PNG file."""
        # Get save path
        default_name = "delta_a_heatmap.png"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Heat Map",
            default_name,
            "PNG Images (*.png);;All Files (*)"
        )

        if not file_path:
            return

        if not file_path.lower().endswith('.png'):
            file_path += '.png'

        try:
            # Get export dimensions
            width = self._width_spin.value()
            height = self._height_spin.value()
            dpi = self._dpi_spin.value()

            # Create a new figure for export with specified dimensions
            fig_width = width / dpi
            fig_height = height / dpi

            export_fig = Figure(figsize=(fig_width, fig_height), dpi=dpi)

            # Recreate the plot on the export figure
            self._render_to_figure(export_fig)

            # Save
            export_fig.savefig(file_path, dpi=dpi, bbox_inches='tight', pad_inches=0.1)

            QMessageBox.information(
                self,
                "Export Complete",
                f"Heat map exported to:\n{file_path}"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export image:\n{str(e)}"
            )

    def _render_to_figure(self, fig: Figure):
        """Render the visualization to a given figure."""
        fig.clear()

        # Get selected panel
        panel_type = self._panel_combo.currentData()
        panel_id = self._session.before_panel_id if panel_type == "before" else self._session.after_panel_id

        if not panel_id:
            return

        # Get image
        image = self._get_panel_image(panel_id)
        if image is None:
            return

        # Create subplot
        ax = fig.add_subplot(111)

        # Display image in grayscale
        ax.imshow(image, cmap='gray', origin='upper')

        # Get confirmed pairings
        confirmed_pairings = self._session.get_confirmed_pairings()

        # Collect ΔA values for normalization
        delta_values = [p.area_change_nm2 for p in confirmed_pairings]

        if delta_values:
            vmin = min(delta_values)
            vmax = max(delta_values)

            if vmin >= 0:
                vmin = -max(abs(vmax), 0.1)
            if vmax <= 0:
                vmax = max(abs(vmin), 0.1)

            norm = TwoSlopeNorm(vmin=vmin, vcenter=0, vmax=vmax)
        else:
            norm = Normalize(vmin=-1, vmax=1)

        alpha = self._opacity_slider.value() / 100.0

        # Draw paired polygons
        paired_patches = []
        paired_colors = []

        for pairing in confirmed_pairings:
            hole = pairing.before_hole if panel_type == "before" else pairing.after_hole
            if hole and hole.vertices:
                polygon = MplPolygon(hole.vertices, closed=True)
                paired_patches.append(polygon)
                paired_colors.append(pairing.area_change_nm2)

        if paired_patches:
            collection = PatchCollection(
                paired_patches,
                cmap=self._cmap,
                norm=norm,
                alpha=alpha,
                edgecolor='black',
                linewidth=1.5,
                match_original=False  # Required for colormap to control facecolors
            )
            collection.set_array(np.array(paired_colors))
            collection.set_clim(vmin=norm.vmin, vmax=norm.vmax)
            ax.add_collection(collection)

            if self._show_colorbar_cb.isChecked():
                cbar = fig.colorbar(collection, ax=ax, shrink=0.8, pad=0.02)
                cbar.set_label('ΔA (nm²)', fontsize=10)

        # Draw unpaired holes in gray
        if self._show_unpaired_cb.isChecked():
            all_holes = self._get_all_holes_from_panel(panel_id)

            paired_ids = set()
            for pairing in confirmed_pairings:
                hole = pairing.before_hole if panel_type == "before" else pairing.after_hole
                if hole:
                    paired_ids.add(hole.polygon_id)

            unpaired_patches = []
            for hole in all_holes:
                if hole.polygon_id not in paired_ids and hole.vertices:
                    polygon = MplPolygon(hole.vertices, closed=True)
                    unpaired_patches.append(polygon)

            if unpaired_patches:
                unpaired_collection = PatchCollection(
                    unpaired_patches,
                    facecolor='#888888',
                    alpha=alpha * 0.7,
                    edgecolor='#666666',
                    linewidth=1
                )
                ax.add_collection(unpaired_collection)

        ax.set_xlim(0, image.shape[1])
        ax.set_ylim(0, image.shape[0])  # Y axis: 0 at bottom, height at top
        ax.set_aspect('equal')
        ax.axis('off')

        fig.tight_layout()
