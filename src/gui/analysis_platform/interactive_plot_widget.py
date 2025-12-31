"""
Interactive Plot Widget for Analysis Platform.

Provides a scatter plot with clickable points, axis selection,
linear regression, and hover tooltips.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QPushButton, QToolTip
)
from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import QColor

import pyqtgraph as pg
import numpy as np
from scipy import stats
from typing import List, Dict, Optional, Tuple

from .dataset_manager import DatasetManager, Dataset, DataPoint, PLOT_VARIABLES


class InteractivePlotWidget(QWidget):
    """Interactive scatter plot with axis selection and click detection."""

    # Signals
    point_clicked = Signal(str, str)      # (dataset_id, pairing_id)
    point_hovered = Signal(str, str)      # (dataset_id, pairing_id) or ("", "") when leaving

    def __init__(self, dataset_manager: DatasetManager, parent=None):
        super().__init__(parent)
        self._manager = dataset_manager

        # State
        self._scatter_items: Dict[str, pg.ScatterPlotItem] = {}  # dataset_id -> scatter
        self._fit_lines: Dict[str, pg.PlotDataItem] = {}         # dataset_id -> line
        self._point_data: Dict[str, List[DataPoint]] = {}        # dataset_id -> points list
        self._selected_point: Optional[Tuple[str, str]] = None   # (dataset_id, pairing_id)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Setup the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Controls row
        controls_layout = QHBoxLayout()

        # X axis selector
        controls_layout.addWidget(QLabel("X:"))
        self._x_combo = QComboBox()
        for var_id, var_label, var_desc in PLOT_VARIABLES:
            self._x_combo.addItem(var_label, var_id)
        self._x_combo.setCurrentIndex(3)  # sqrt_A0_over_r
        self._x_combo.setToolTip("Select variable for X axis")
        controls_layout.addWidget(self._x_combo)

        controls_layout.addSpacing(20)

        # Y axis selector
        controls_layout.addWidget(QLabel("Y:"))
        self._y_combo = QComboBox()
        for var_id, var_label, var_desc in PLOT_VARIABLES:
            self._y_combo.addItem(var_label, var_id)
        self._y_combo.setCurrentIndex(0)  # delta_area_nm2
        self._y_combo.setToolTip("Select variable for Y axis")
        controls_layout.addWidget(self._y_combo)

        controls_layout.addSpacing(20)

        # Show fit lines checkbox
        self._show_fit_cb = QCheckBox("Show Fit Lines")
        self._show_fit_cb.setChecked(True)
        controls_layout.addWidget(self._show_fit_cb)

        # Show legend checkbox
        self._show_legend_cb = QCheckBox("Show Legend")
        self._show_legend_cb.setChecked(True)
        controls_layout.addWidget(self._show_legend_cb)

        controls_layout.addStretch()

        layout.addLayout(controls_layout)

        # Plot widget
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground('w')
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._plot_widget.setMouseEnabled(x=True, y=True)

        # Add zero lines
        self._zero_x_line = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen('#888888', width=1, style=Qt.DashLine))
        self._zero_y_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen('#888888', width=1, style=Qt.DashLine))
        self._plot_widget.addItem(self._zero_x_line)
        self._plot_widget.addItem(self._zero_y_line)

        # Legend
        self._legend = self._plot_widget.addLegend(offset=(10, 10))

        layout.addWidget(self._plot_widget)

        # Statistics row
        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet("color: #666; font-size: 11px; padding: 4px;")
        self._stats_label.setWordWrap(True)
        layout.addWidget(self._stats_label)

    def _connect_signals(self):
        """Connect signals."""
        self._x_combo.currentIndexChanged.connect(self._update_plot)
        self._y_combo.currentIndexChanged.connect(self._update_plot)
        self._show_fit_cb.stateChanged.connect(self._update_fit_visibility)
        self._show_legend_cb.stateChanged.connect(self._update_legend_visibility)
        self._manager.datasets_changed.connect(self._update_plot)

        # Mouse events for click detection
        self._plot_widget.scene().sigMouseClicked.connect(self._on_mouse_clicked)
        self._plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

    def _update_plot(self):
        """Update the plot with current data and axis selections."""
        # Clear existing items
        for scatter in self._scatter_items.values():
            self._plot_widget.removeItem(scatter)
        for line in self._fit_lines.values():
            self._plot_widget.removeItem(line)

        self._scatter_items.clear()
        self._fit_lines.clear()
        self._point_data.clear()

        # Clear legend
        self._legend.clear()

        # Get axis variables
        x_var = self._x_combo.currentData()
        y_var = self._y_combo.currentData()

        if not x_var or not y_var:
            return

        # Update axis labels
        x_label = self._x_combo.currentText()
        y_label = self._y_combo.currentText()
        self._plot_widget.setLabel('bottom', x_label)
        self._plot_widget.setLabel('left', y_label)

        stats_parts = []

        # Plot each dataset
        for dataset in self._manager.datasets:
            if not dataset.visible or not dataset.data_points:
                continue

            # Get data
            x_data = []
            y_data = []
            points = []

            for point in dataset.data_points:
                x_val = point.get_value(x_var)
                y_val = point.get_value(y_var)

                # Skip invalid values
                if np.isnan(x_val) or np.isnan(y_val) or np.isinf(x_val) or np.isinf(y_val):
                    continue

                x_data.append(x_val)
                y_data.append(y_val)
                points.append(point)

            if not x_data:
                continue

            self._point_data[dataset.dataset_id] = points

            # Create scatter plot
            symbol = self._get_symbol(dataset.symbol)
            color = QColor(dataset.color)

            scatter = pg.ScatterPlotItem(
                x=x_data,
                y=y_data,
                size=10,
                pen=pg.mkPen(color.darker(120), width=1),
                brush=pg.mkBrush(color),
                symbol=symbol,
                name=f"{dataset.name} (n={len(x_data)})"
            )
            scatter.setZValue(100)
            self._plot_widget.addItem(scatter)
            self._scatter_items[dataset.dataset_id] = scatter

            # Linear regression
            if len(x_data) >= 2:
                x_arr = np.array(x_data)
                y_arr = np.array(y_data)

                slope, intercept, r_value, p_value, std_err = stats.linregress(x_arr, y_arr)

                # Create fit line
                x_fit = np.array([min(x_arr), max(x_arr)])
                y_fit = slope * x_fit + intercept

                fit_line = pg.PlotDataItem(
                    x_fit, y_fit,
                    pen=pg.mkPen(color, width=2, style=Qt.DashLine)
                )
                fit_line.setZValue(50)
                self._plot_widget.addItem(fit_line)
                self._fit_lines[dataset.dataset_id] = fit_line

                # Statistics
                r_squared = r_value ** 2
                stats_parts.append(f"{dataset.name}: n={len(x_data)}, m={slope:.2f}, R²={r_squared:.3f}")

        # Update fit line visibility
        self._update_fit_visibility()
        self._update_legend_visibility()

        # Update statistics label
        if stats_parts:
            self._stats_label.setText(" | ".join(stats_parts))
        else:
            self._stats_label.setText("No data to display")

    def _get_symbol(self, symbol_code: str) -> str:
        """Convert symbol code to pyqtgraph symbol."""
        mapping = {
            'o': 'o',      # circle
            's': 's',      # square
            't': 't',      # triangle
            'd': 'd',      # diamond
            'p': 'p',      # pentagon
            'h': 'h',      # hexagon
            'star': 'star',
            '+': '+',
        }
        return mapping.get(symbol_code, 'o')

    def _update_fit_visibility(self):
        """Update fit line visibility based on checkbox."""
        visible = self._show_fit_cb.isChecked()
        for line in self._fit_lines.values():
            line.setVisible(visible)

    def _update_legend_visibility(self):
        """Update legend visibility based on checkbox."""
        visible = self._show_legend_cb.isChecked()
        if visible:
            self._legend.show()
        else:
            self._legend.hide()

    def _on_mouse_clicked(self, event):
        """Handle mouse click to select point."""
        if event.button() != Qt.LeftButton:
            return

        # Get click position in view coordinates
        pos = event.scenePos()
        if not self._plot_widget.sceneBoundingRect().contains(pos):
            return

        view_pos = self._plot_widget.plotItem.vb.mapSceneToView(pos)

        # Find nearest point
        nearest = self._find_nearest_point(view_pos.x(), view_pos.y())

        if nearest:
            dataset_id, point = nearest
            self._selected_point = (dataset_id, point.pairing_id)
            self.point_clicked.emit(dataset_id, point.pairing_id)
            self._highlight_point(dataset_id, point.pairing_id)
        else:
            self._selected_point = None
            self._clear_highlight()

    def _on_mouse_moved(self, pos):
        """Handle mouse move for hover tooltip."""
        if not self._plot_widget.sceneBoundingRect().contains(pos):
            self.point_hovered.emit("", "")
            return

        view_pos = self._plot_widget.plotItem.vb.mapSceneToView(pos)

        # Find nearest point
        nearest = self._find_nearest_point(view_pos.x(), view_pos.y(), threshold=0.05)

        if nearest:
            dataset_id, point = nearest
            self.point_hovered.emit(dataset_id, point.pairing_id)

            # Show tooltip
            dataset = self._manager.get_dataset(dataset_id)
            if dataset:
                x_var = self._x_combo.currentData()
                y_var = self._y_combo.currentData()
                tooltip = (
                    f"{dataset.name}\n"
                    f"ID: {point.pairing_id}\n"
                    f"{self._x_combo.currentText()}: {point.get_value(x_var):.4f}\n"
                    f"{self._y_combo.currentText()}: {point.get_value(y_var):.4f}"
                )
                QToolTip.showText(self._plot_widget.mapToGlobal(pos.toPoint()), tooltip)
        else:
            self.point_hovered.emit("", "")
            QToolTip.hideText()

    def _find_nearest_point(self, x: float, y: float, threshold: float = 0.1) -> Optional[Tuple[str, DataPoint]]:
        """Find the nearest data point to the given coordinates."""
        x_var = self._x_combo.currentData()
        y_var = self._y_combo.currentData()

        if not x_var or not y_var:
            return None

        # Get data range for normalization
        all_x = []
        all_y = []
        for points in self._point_data.values():
            for p in points:
                all_x.append(p.get_value(x_var))
                all_y.append(p.get_value(y_var))

        if not all_x:
            return None

        x_range = max(all_x) - min(all_x) if len(all_x) > 1 else 1
        y_range = max(all_y) - min(all_y) if len(all_y) > 1 else 1

        if x_range == 0:
            x_range = 1
        if y_range == 0:
            y_range = 1

        best_dist = float('inf')
        best_point = None
        best_dataset_id = None

        for dataset_id, points in self._point_data.items():
            for point in points:
                px = point.get_value(x_var)
                py = point.get_value(y_var)

                # Normalized distance
                dx = (x - px) / x_range
                dy = (y - py) / y_range
                dist = (dx ** 2 + dy ** 2) ** 0.5

                if dist < best_dist and dist < threshold:
                    best_dist = dist
                    best_point = point
                    best_dataset_id = dataset_id

        if best_point:
            return (best_dataset_id, best_point)
        return None

    def _highlight_point(self, dataset_id: str, pairing_id: str):
        """Highlight a specific point."""
        # For now, we'll just update the selection state
        # In the future, we could add a visual highlight
        pass

    def _clear_highlight(self):
        """Clear point highlight."""
        pass

    def select_point(self, dataset_id: str, pairing_id: str):
        """Programmatically select a point."""
        self._selected_point = (dataset_id, pairing_id)
        self._highlight_point(dataset_id, pairing_id)

    def get_statistics(self) -> List[Dict]:
        """Get regression statistics for all visible datasets."""
        stats_list = []

        x_var = self._x_combo.currentData()
        y_var = self._y_combo.currentData()

        for dataset in self._manager.datasets:
            if not dataset.visible or not dataset.data_points:
                continue

            x_data = []
            y_data = []

            for point in dataset.data_points:
                x_val = point.get_value(x_var)
                y_val = point.get_value(y_var)

                if np.isnan(x_val) or np.isnan(y_val) or np.isinf(x_val) or np.isinf(y_val):
                    continue

                x_data.append(x_val)
                y_data.append(y_val)

            if len(x_data) >= 2:
                x_arr = np.array(x_data)
                y_arr = np.array(y_data)

                slope, intercept, r_value, p_value, std_err = stats.linregress(x_arr, y_arr)

                stats_list.append({
                    'dataset_name': dataset.name,
                    'dataset_id': dataset.dataset_id,
                    'light_intensity_mA': dataset.light_intensity_mA,
                    'n': len(x_data),
                    'slope': slope,
                    'intercept': intercept,
                    'r_squared': r_value ** 2,
                    'p_value': p_value,
                    'std_err': std_err,
                    'x_variable': x_var,
                    'y_variable': y_var,
                })

        return stats_list

    def export_plot_image(self, path: str, width: int = 1200, height: int = 800):
        """Export plot to image file."""
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        # Create matplotlib figure
        fig = Figure(figsize=(width/100, height/100), dpi=100)
        ax = fig.add_subplot(111)

        x_var = self._x_combo.currentData()
        y_var = self._y_combo.currentData()

        for dataset in self._manager.datasets:
            if not dataset.visible or not dataset.data_points:
                continue

            x_data = []
            y_data = []

            for point in dataset.data_points:
                x_val = point.get_value(x_var)
                y_val = point.get_value(y_var)

                if np.isnan(x_val) or np.isnan(y_val):
                    continue

                x_data.append(x_val)
                y_data.append(y_val)

            if not x_data:
                continue

            # Plot scatter
            marker = {'o': 'o', 's': 's', 't': '^', 'd': 'd', 'p': 'p', 'h': 'h'}.get(dataset.symbol, 'o')
            ax.scatter(x_data, y_data, c=dataset.color, marker=marker,
                      label=f"{dataset.name} (n={len(x_data)})", alpha=0.8, s=50)

            # Plot fit line
            if self._show_fit_cb.isChecked() and len(x_data) >= 2:
                x_arr = np.array(x_data)
                y_arr = np.array(y_data)
                slope, intercept, r_value, _, _ = stats.linregress(x_arr, y_arr)

                x_fit = np.array([min(x_arr), max(x_arr)])
                y_fit = slope * x_fit + intercept
                ax.plot(x_fit, y_fit, color=dataset.color, linestyle='--', linewidth=2,
                       label=f"m={slope:.2f}, R²={r_value**2:.3f}")

        ax.set_xlabel(self._x_combo.currentText())
        ax.set_ylabel(self._y_combo.currentText())
        ax.axhline(y=0, color='gray', linestyle='--', linewidth=0.5)
        ax.axvline(x=0, color='gray', linestyle='--', linewidth=0.5)
        ax.legend(loc='best')
        ax.grid(True, alpha=0.3)

        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches='tight')
