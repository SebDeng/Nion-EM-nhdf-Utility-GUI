"""
Ripening Analysis Tool for studying Ostwald ripening / defect capture.
Analyzes polygon annotations from before/after EM image panels.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import csv
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QGroupBox, QDoubleSpinBox, QWidget,
    QSplitter, QTextEdit, QFileDialog, QMessageBox
)
from PySide6.QtGui import QFont
import pyqtgraph as pg


@dataclass
class PolygonData:
    """Data for a single polygon annotation."""
    vertices: List[Tuple[float, float]]
    area_nm2: float
    centroid: Tuple[float, float]
    panel_id: str = ""


@dataclass
class SinkMatch:
    """Matched sink between before and after images."""
    before_polygon: PolygonData
    after_polygon: PolygonData
    growth_nm2: float
    captured_holes: List[PolygonData] = field(default_factory=list)
    capture_distances: List[float] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Complete analysis result."""
    sink_matches: List[SinkMatch]
    disappeared_holes: List[PolygonData]  # Small holes that disappeared
    survived_holes: List[PolygonData]  # Small holes that survived
    unmatched_before_sinks: List[PolygonData]
    unmatched_after_sinks: List[PolygonData]
    statistics: Dict


def get_polygon_centroid(vertices: List[Tuple[float, float]]) -> Tuple[float, float]:
    """Calculate centroid of polygon."""
    if not vertices:
        return (0.0, 0.0)
    x_coords = [v[0] for v in vertices]
    y_coords = [v[1] for v in vertices]
    return (np.mean(x_coords), np.mean(y_coords))


def get_polygon_area(vertices: List[Tuple[float, float]]) -> float:
    """Calculate polygon area using shoelace formula (in pixel units)."""
    if len(vertices) < 3:
        return 0.0
    n = len(vertices)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += vertices[i][0] * vertices[j][1]
        area -= vertices[j][0] * vertices[i][1]
    return abs(area) / 2.0


def distance_between_points(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Calculate Euclidean distance between two points."""
    return np.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)


def polygon_exists_in_list(
    polygon: PolygonData,
    polygon_list: List[PolygonData],
    tolerance_nm: float = 5.0
) -> Tuple[bool, Optional[PolygonData]]:
    """
    Check if a polygon exists in a list by centroid proximity.
    Returns (exists, matched_polygon).
    """
    for p in polygon_list:
        dist = distance_between_points(polygon.centroid, p.centroid)
        if dist < tolerance_nm:
            return True, p
    return False, None


def match_sinks_by_proximity(
    before_sinks: List[PolygonData],
    after_sinks: List[PolygonData],
    max_dist_nm: float = 20.0
) -> Tuple[List[SinkMatch], List[PolygonData], List[PolygonData]]:
    """
    Match sinks between before and after images by centroid proximity.
    Returns (matches, unmatched_before, unmatched_after).
    """
    matches = []
    used_after = set()
    unmatched_before = []

    for before in before_sinks:
        best_match = None
        best_dist = float('inf')
        best_idx = -1

        for idx, after in enumerate(after_sinks):
            if idx in used_after:
                continue
            dist = distance_between_points(before.centroid, after.centroid)
            if dist < best_dist and dist < max_dist_nm:
                best_dist = dist
                best_match = after
                best_idx = idx

        if best_match is not None:
            growth = best_match.area_nm2 - before.area_nm2
            matches.append(SinkMatch(
                before_polygon=before,
                after_polygon=best_match,
                growth_nm2=growth
            ))
            used_after.add(best_idx)
        else:
            unmatched_before.append(before)

    unmatched_after = [s for i, s in enumerate(after_sinks) if i not in used_after]

    return matches, unmatched_before, unmatched_after


def analyze_ripening(
    before_polygons: List[PolygonData],
    after_polygons: List[PolygonData],
    sink_threshold_nm2: float = 4.0,
    match_tolerance_nm: float = 20.0,
    hole_match_tolerance_nm: float = 5.0
) -> AnalysisResult:
    """
    Analyze Ostwald ripening between before and after images.

    Args:
        before_polygons: Polygons from before image
        after_polygons: Polygons from after image
        sink_threshold_nm2: Area threshold to identify sinks (larger holes)
        match_tolerance_nm: Max distance for sink matching
        hole_match_tolerance_nm: Max distance for small hole matching

    Returns:
        AnalysisResult with all analysis data
    """
    # Separate sinks (large) from small holes
    before_sinks = [p for p in before_polygons if p.area_nm2 >= sink_threshold_nm2]
    before_holes = [p for p in before_polygons if p.area_nm2 < sink_threshold_nm2]

    after_sinks = [p for p in after_polygons if p.area_nm2 >= sink_threshold_nm2]
    after_holes = [p for p in after_polygons if p.area_nm2 < sink_threshold_nm2]

    # Match sinks between images
    sink_matches, unmatched_before, unmatched_after = match_sinks_by_proximity(
        before_sinks, after_sinks, match_tolerance_nm
    )

    # Find disappeared holes (in before, not in after)
    disappeared_holes = []
    survived_holes = []

    for hole in before_holes:
        exists, _ = polygon_exists_in_list(hole, after_holes, hole_match_tolerance_nm)
        if exists:
            survived_holes.append(hole)
        else:
            disappeared_holes.append(hole)

    # Assign disappeared holes to nearest sink
    for hole in disappeared_holes:
        if not sink_matches:
            continue

        # Find nearest sink (use before position)
        best_match = None
        best_dist = float('inf')

        for match in sink_matches:
            dist = distance_between_points(hole.centroid, match.before_polygon.centroid)
            if dist < best_dist:
                best_dist = dist
                best_match = match

        if best_match is not None:
            best_match.captured_holes.append(hole)
            best_match.capture_distances.append(best_dist)

    # Calculate statistics
    all_capture_distances = []
    total_captured_area = 0.0

    for match in sink_matches:
        all_capture_distances.extend(match.capture_distances)
        total_captured_area += sum(h.area_nm2 for h in match.captured_holes)

    statistics = {
        'num_sinks_matched': len(sink_matches),
        'num_holes_captured': len(disappeared_holes),
        'num_holes_survived': len(survived_holes),
        'total_sink_growth': sum(m.growth_nm2 for m in sink_matches),
        'total_captured_area': total_captured_area,
        'mean_capture_distance': np.mean(all_capture_distances) if all_capture_distances else 0.0,
        'median_capture_distance': np.median(all_capture_distances) if all_capture_distances else 0.0,
        'max_capture_distance': max(all_capture_distances) if all_capture_distances else 0.0,
        'min_capture_distance': min(all_capture_distances) if all_capture_distances else 0.0,
    }

    return AnalysisResult(
        sink_matches=sink_matches,
        disappeared_holes=disappeared_holes,
        survived_holes=survived_holes,
        unmatched_before_sinks=unmatched_before,
        unmatched_after_sinks=unmatched_after,
        statistics=statistics
    )


class RipeningAnalysisDialog(QDialog):
    """
    Dialog for analyzing Ostwald ripening between before/after images.
    """

    def __init__(self, workspace_widget, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ripening Analysis")
        self.setMinimumSize(800, 700)

        self._workspace = workspace_widget
        self._result: Optional[AnalysisResult] = None

        self._setup_ui()
        self._populate_panel_dropdowns()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Panel selection group
        selection_group = QGroupBox("Panel Selection")
        selection_layout = QHBoxLayout(selection_group)

        # Before panel
        selection_layout.addWidget(QLabel("Before Panel:"))
        self._before_combo = QComboBox()
        self._before_combo.setMinimumWidth(200)
        selection_layout.addWidget(self._before_combo)

        selection_layout.addSpacing(20)

        # After panel
        selection_layout.addWidget(QLabel("After Panel:"))
        self._after_combo = QComboBox()
        self._after_combo.setMinimumWidth(200)
        selection_layout.addWidget(self._after_combo)

        selection_layout.addStretch()
        layout.addWidget(selection_group)

        # Settings group
        settings_group = QGroupBox("Analysis Settings")
        settings_layout = QHBoxLayout(settings_group)

        settings_layout.addWidget(QLabel("Sink Threshold:"))
        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setRange(0.1, 1000.0)
        self._threshold_spin.setValue(4.0)
        self._threshold_spin.setSuffix(" nm\u00b2")
        self._threshold_spin.setDecimals(1)
        settings_layout.addWidget(self._threshold_spin)

        settings_layout.addSpacing(20)

        settings_layout.addWidget(QLabel("Match Tolerance:"))
        self._match_tolerance_spin = QDoubleSpinBox()
        self._match_tolerance_spin.setRange(1.0, 100.0)
        self._match_tolerance_spin.setValue(20.0)
        self._match_tolerance_spin.setSuffix(" nm")
        self._match_tolerance_spin.setDecimals(1)
        settings_layout.addWidget(self._match_tolerance_spin)

        settings_layout.addStretch()

        self._analyze_btn = QPushButton("Analyze")
        self._analyze_btn.clicked.connect(self._on_analyze)
        settings_layout.addWidget(self._analyze_btn)

        layout.addWidget(settings_group)

        # Results area with splitter
        results_splitter = QSplitter(Qt.Vertical)

        # Charts area (horizontal splitter)
        charts_splitter = QSplitter(Qt.Horizontal)

        # Capture distance histogram
        histogram_widget = QWidget()
        histogram_layout = QVBoxLayout(histogram_widget)
        histogram_layout.setContentsMargins(0, 0, 0, 0)
        histogram_layout.addWidget(QLabel("Capture Distance Distribution"))

        self._histogram_plot = pg.PlotWidget()
        self._histogram_plot.setBackground('k')
        self._histogram_plot.setLabel('bottom', 'Distance', units='nm')
        self._histogram_plot.setLabel('left', 'Count')
        self._histogram_plot.showGrid(x=True, y=True, alpha=0.3)
        histogram_layout.addWidget(self._histogram_plot)

        charts_splitter.addWidget(histogram_widget)

        # Scatter plot: growth vs captured count
        scatter_widget = QWidget()
        scatter_layout = QVBoxLayout(scatter_widget)
        scatter_layout.setContentsMargins(0, 0, 0, 0)
        scatter_layout.addWidget(QLabel("Sink Growth vs Captured Holes"))

        self._scatter_plot = pg.PlotWidget()
        self._scatter_plot.setBackground('k')
        self._scatter_plot.setLabel('bottom', 'Captured Holes Count')
        self._scatter_plot.setLabel('left', 'Sink Growth', units='nm\u00b2')
        self._scatter_plot.showGrid(x=True, y=True, alpha=0.3)
        scatter_layout.addWidget(self._scatter_plot)

        charts_splitter.addWidget(scatter_widget)

        results_splitter.addWidget(charts_splitter)

        # Statistics text area
        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout(stats_group)

        self._stats_text = QTextEdit()
        self._stats_text.setReadOnly(True)
        self._stats_text.setMaximumHeight(150)
        font = QFont("Menlo", 11)
        self._stats_text.setFont(font)
        stats_layout.addWidget(self._stats_text)

        results_splitter.addWidget(stats_group)

        layout.addWidget(results_splitter, stretch=1)

        # Buttons
        button_layout = QHBoxLayout()

        self._export_btn = QPushButton("Export CSV")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._on_export)
        button_layout.addWidget(self._export_btn)

        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _populate_panel_dropdowns(self):
        """Populate panel selection dropdowns from workspace."""
        self._before_combo.clear()
        self._after_combo.clear()

        # Get all panels from workspace
        panels = self._get_all_panels()

        for i, panel in enumerate(panels):
            # Get panel info
            file_name = "Empty Panel"
            if hasattr(panel, '_current_file') and panel._current_file:
                file_name = os.path.basename(panel._current_file)
            elif hasattr(panel, 'get_display_title'):
                file_name = panel.get_display_title() or f"Panel {i+1}"

            # Count polygons
            polygon_count = 0
            if hasattr(panel, '_measurement_overlay') and panel._measurement_overlay:
                data = panel._measurement_overlay.get_measurements_data()
                polygon_count = len(data.get('polygons', []))

            label = f"{file_name} ({polygon_count} polygons)"
            self._before_combo.addItem(label, panel)
            self._after_combo.addItem(label, panel)

        # Default: select first two panels if available
        if self._before_combo.count() >= 2:
            self._before_combo.setCurrentIndex(0)
            self._after_combo.setCurrentIndex(1)

    def _get_all_panels(self) -> List:
        """Get all display panels from workspace."""
        panels = []

        def collect_panels(widget):
            if widget is None:
                return

            # Check if it's a display panel
            if hasattr(widget, '_measurement_overlay'):
                panels.append(widget)
                return

            # Check children for QSplitter
            if hasattr(widget, 'count'):
                for i in range(widget.count()):
                    child = widget.widget(i) if hasattr(widget, 'widget') else None
                    if child:
                        collect_panels(child)

        if self._workspace:
            collect_panels(self._workspace)

        return panels

    def _get_polygons_from_panel(self, panel) -> List[PolygonData]:
        """Extract polygon data from a panel's measurement overlay."""
        polygons = []

        if not hasattr(panel, '_measurement_overlay') or not panel._measurement_overlay:
            return polygons

        # Get calibration
        scale_nm = 1.0  # Default: pixels
        if hasattr(panel, '_nhdf_data') and panel._nhdf_data:
            calibs = panel._nhdf_data.dimensional_calibrations
            if calibs and len(calibs) >= 2:
                scale_nm = calibs[0].scale  # nm per pixel

        # Get measurement data
        data = panel._measurement_overlay.get_measurements_data()

        for poly_data in data.get('polygons', []):
            vertices = poly_data.get('vertices', [])
            if len(vertices) < 3:
                continue

            # Calculate area in nm^2
            area_px = get_polygon_area(vertices)
            area_nm2 = area_px * (scale_nm ** 2)

            # Calculate centroid in nm
            centroid_px = get_polygon_centroid(vertices)
            centroid_nm = (centroid_px[0] * scale_nm, centroid_px[1] * scale_nm)

            polygons.append(PolygonData(
                vertices=vertices,
                area_nm2=area_nm2,
                centroid=centroid_nm
            ))

        return polygons

    def _on_analyze(self):
        """Run the ripening analysis."""
        before_panel = self._before_combo.currentData()
        after_panel = self._after_combo.currentData()

        if before_panel is None or after_panel is None:
            QMessageBox.warning(self, "Error", "Please select both before and after panels.")
            return

        if before_panel is after_panel:
            QMessageBox.warning(self, "Error", "Please select different panels for before and after.")
            return

        # Get polygons
        before_polygons = self._get_polygons_from_panel(before_panel)
        after_polygons = self._get_polygons_from_panel(after_panel)

        if not before_polygons:
            QMessageBox.warning(self, "Error", "No polygons found in before panel.")
            return

        if not after_polygons:
            QMessageBox.warning(self, "Error", "No polygons found in after panel.")
            return

        # Run analysis
        threshold = self._threshold_spin.value()
        match_tolerance = self._match_tolerance_spin.value()

        self._result = analyze_ripening(
            before_polygons,
            after_polygons,
            sink_threshold_nm2=threshold,
            match_tolerance_nm=match_tolerance
        )

        # Update display
        self._update_histogram()
        self._update_scatter()
        self._update_statistics()

        self._export_btn.setEnabled(True)

    def _update_histogram(self):
        """Update capture distance histogram."""
        self._histogram_plot.clear()

        if self._result is None:
            return

        # Collect all capture distances
        distances = []
        for match in self._result.sink_matches:
            distances.extend(match.capture_distances)

        if not distances:
            # No data - show message
            text = pg.TextItem("No captured holes", anchor=(0.5, 0.5), color='w')
            self._histogram_plot.addItem(text)
            return

        # Create histogram
        bins = np.linspace(0, max(distances) * 1.1, 15)
        hist, bin_edges = np.histogram(distances, bins=bins)

        # Plot as bar chart
        bargraph = pg.BarGraphItem(
            x=bin_edges[:-1],
            height=hist,
            width=(bin_edges[1] - bin_edges[0]) * 0.9,
            brush=pg.mkBrush(100, 200, 255, 180),
            pen=pg.mkPen('w', width=1)
        )
        self._histogram_plot.addItem(bargraph)

        # Add mean line
        mean_dist = np.mean(distances)
        mean_line = pg.InfiniteLine(
            pos=mean_dist,
            angle=90,
            pen=pg.mkPen('r', width=2, style=Qt.DashLine)
        )
        self._histogram_plot.addItem(mean_line)

        # Add label for mean
        text = pg.TextItem(f"Mean: {mean_dist:.1f} nm", anchor=(0, 1), color='r')
        text.setPos(mean_dist, max(hist))
        self._histogram_plot.addItem(text)

    def _update_scatter(self):
        """Update scatter plot of growth vs captured count."""
        self._scatter_plot.clear()

        if self._result is None:
            return

        if not self._result.sink_matches:
            text = pg.TextItem("No sink matches", anchor=(0.5, 0.5), color='w')
            self._scatter_plot.addItem(text)
            return

        # Collect data points
        x_data = []  # Captured count
        y_data = []  # Growth

        for match in self._result.sink_matches:
            x_data.append(len(match.captured_holes))
            y_data.append(match.growth_nm2)

        # Create scatter plot
        scatter = pg.ScatterPlotItem(
            x=x_data,
            y=y_data,
            size=15,
            pen=pg.mkPen('w', width=1),
            brush=pg.mkBrush(255, 150, 50, 200),
            symbol='o'
        )
        self._scatter_plot.addItem(scatter)

        # Add trend line if we have enough points
        if len(x_data) >= 3:
            try:
                coeffs = np.polyfit(x_data, y_data, 1)
                x_line = np.array([min(x_data), max(x_data)])
                y_line = coeffs[0] * x_line + coeffs[1]

                trend_line = pg.PlotDataItem(
                    x_line, y_line,
                    pen=pg.mkPen('g', width=2, style=Qt.DashLine)
                )
                self._scatter_plot.addItem(trend_line)
            except Exception:
                pass  # Skip trend line on error

    def _update_statistics(self):
        """Update statistics display."""
        if self._result is None:
            self._stats_text.clear()
            return

        stats = self._result.statistics

        text = f"""Sink Matching:
  Sinks matched:         {stats['num_sinks_matched']}
  Unmatched (before):    {len(self._result.unmatched_before_sinks)}
  Unmatched (after):     {len(self._result.unmatched_after_sinks)}

Hole Capture:
  Holes captured:        {stats['num_holes_captured']}
  Holes survived:        {stats['num_holes_survived']}
  Total captured area:   {stats['total_captured_area']:.2f} nm\u00b2

Capture Distance:
  Mean:                  {stats['mean_capture_distance']:.2f} nm
  Median:                {stats['median_capture_distance']:.2f} nm
  Range:                 {stats['min_capture_distance']:.2f} - {stats['max_capture_distance']:.2f} nm

Sink Growth:
  Total growth:          {stats['total_sink_growth']:.2f} nm\u00b2"""

        self._stats_text.setText(text)

    def _on_export(self):
        """Export results to CSV."""
        if self._result is None:
            return

        # Choose file location
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Ripening Analysis",
            "ripening_analysis.csv",
            "CSV Files (*.csv)"
        )

        if not file_path:
            return

        try:
            with open(file_path, 'w', newline='') as f:
                writer = csv.writer(f)

                # Header
                writer.writerow(['Ripening Analysis Results'])
                writer.writerow([])

                # Statistics
                stats = self._result.statistics
                writer.writerow(['Statistics'])
                writer.writerow(['Metric', 'Value'])
                writer.writerow(['Sinks Matched', stats['num_sinks_matched']])
                writer.writerow(['Holes Captured', stats['num_holes_captured']])
                writer.writerow(['Holes Survived', stats['num_holes_survived']])
                writer.writerow(['Mean Capture Distance (nm)', f"{stats['mean_capture_distance']:.2f}"])
                writer.writerow(['Total Sink Growth (nm2)', f"{stats['total_sink_growth']:.2f}"])
                writer.writerow([])

                # Sink matches
                writer.writerow(['Sink Matches'])
                writer.writerow([
                    'Sink ID', 'Before Area (nm2)', 'After Area (nm2)',
                    'Growth (nm2)', 'Captured Count', 'Capture Distances (nm)'
                ])

                for i, match in enumerate(self._result.sink_matches):
                    distances_str = ', '.join(f"{d:.2f}" for d in match.capture_distances)
                    writer.writerow([
                        i + 1,
                        f"{match.before_polygon.area_nm2:.2f}",
                        f"{match.after_polygon.area_nm2:.2f}",
                        f"{match.growth_nm2:.2f}",
                        len(match.captured_holes),
                        distances_str
                    ])

                writer.writerow([])

                # Captured holes
                writer.writerow(['Captured Holes'])
                writer.writerow(['Hole ID', 'Area (nm2)', 'Centroid X (nm)', 'Centroid Y (nm)', 'Assigned Sink'])

                hole_id = 1
                for sink_idx, match in enumerate(self._result.sink_matches):
                    for hole in match.captured_holes:
                        writer.writerow([
                            hole_id,
                            f"{hole.area_nm2:.2f}",
                            f"{hole.centroid[0]:.2f}",
                            f"{hole.centroid[1]:.2f}",
                            sink_idx + 1
                        ])
                        hole_id += 1

            QMessageBox.information(self, "Export Complete", f"Results exported to:\n{file_path}")

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export:\n{str(e)}")
