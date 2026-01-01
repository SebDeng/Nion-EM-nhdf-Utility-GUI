"""
Hole Viewer Dialog.

Shows the original before/after hole images from a workspace session.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QSplitter, QMessageBox, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

import pyqtgraph as pg
import numpy as np
import json
import os
from typing import Optional, Dict, Any, Tuple, List

from src.core.nhdf_reader import read_em_file


class HoleViewerDialog(QDialog):
    """Dialog to view original hole data from a workspace session."""

    def __init__(self, session_path: str, pairing_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Hole Viewer - {pairing_id}")
        self.setMinimumSize(900, 500)

        self._session_path = session_path
        self._pairing_id = pairing_id
        self._session_data = None
        self._pairing_data = None
        self._before_panel_info = None
        self._after_panel_info = None

        self._setup_ui()
        self._load_and_display()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # Info label
        self._info_label = QLabel()
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("font-size: 11px; color: #666; padding: 5px;")
        layout.addWidget(self._info_label)

        # Splitter for before/after images
        splitter = QSplitter(Qt.Horizontal)

        # Before image
        before_group = QGroupBox("Before")
        before_layout = QVBoxLayout(before_group)
        self._before_plot = pg.PlotWidget()
        self._before_plot.setAspectLocked(True)
        self._before_plot.getAxis('left').setLabel('Y (px)')
        self._before_plot.getAxis('bottom').setLabel('X (px)')
        before_layout.addWidget(self._before_plot)
        self._before_info = QLabel("-")
        self._before_info.setStyleSheet("font-size: 10px;")
        before_layout.addWidget(self._before_info)
        splitter.addWidget(before_group)

        # After image
        after_group = QGroupBox("After")
        after_layout = QVBoxLayout(after_group)
        self._after_plot = pg.PlotWidget()
        self._after_plot.setAspectLocked(True)
        self._after_plot.getAxis('left').setLabel('Y (px)')
        self._after_plot.getAxis('bottom').setLabel('X (px)')
        after_layout.addWidget(self._after_plot)
        self._after_info = QLabel("-")
        self._after_info.setStyleSheet("font-size: 10px;")
        after_layout.addWidget(self._after_info)
        splitter.addWidget(after_group)

        layout.addWidget(splitter)

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _load_and_display(self):
        """Load session data and display the hole."""
        try:
            # Load session
            if not os.path.exists(self._session_path):
                self._show_error(f"Session file not found:\n{self._session_path}")
                return

            with open(self._session_path, 'r', encoding='utf-8') as f:
                self._session_data = json.load(f)

            # Find the pairing
            self._pairing_data, workspace_idx = self._find_pairing()

            if not self._pairing_data:
                self._show_error(f"Pairing '{self._pairing_id}' not found in session.")
                return

            # Find panel info
            self._find_panel_info(workspace_idx)

            # Update info label
            session_name = self._session_data.get('name', os.path.basename(self._session_path))
            self._info_label.setText(
                f"<b>Session:</b> {session_name} | "
                f"<b>Pairing:</b> {self._pairing_id}"
            )

            # Display images and holes
            self._display_hole('before', self._before_plot, self._before_info)
            self._display_hole('after', self._after_plot, self._after_info)

        except Exception as e:
            self._show_error(f"Error loading session: {e}")

    def _find_pairing(self) -> Tuple[Optional[Dict], int]:
        """Find the pairing data in the session."""
        workspaces = self._session_data.get('workspaces', [])

        for ws_idx, workspace in enumerate(workspaces):
            hole_pairing = workspace.get('hole_pairing_session')
            if not hole_pairing:
                continue

            # Check sessions dict
            sessions = hole_pairing.get('sessions', {})
            for session_key, session_data in sessions.items():
                pairings = session_data.get('sink_pairings', [])
                for pairing in pairings:
                    if pairing.get('pairing_id') == self._pairing_id:
                        # Also store panel IDs from the session
                        self._before_panel_id = session_data.get('before_panel_id')
                        self._after_panel_id = session_data.get('after_panel_id')
                        return pairing, ws_idx

            # Also check current_session for backwards compatibility
            current_session = hole_pairing.get('current_session')
            if current_session:
                pairings = current_session.get('sink_pairings', [])
                for pairing in pairings:
                    if pairing.get('pairing_id') == self._pairing_id:
                        self._before_panel_id = current_session.get('before_panel_id')
                        self._after_panel_id = current_session.get('after_panel_id')
                        return pairing, ws_idx

        return None, -1

    def _find_panel_info(self, workspace_idx: int):
        """Find panel info (file paths) for before and after panels."""
        if workspace_idx < 0:
            return

        workspace = self._session_data.get('workspaces', [])[workspace_idx]

        # Panels are stored in a nested layout structure (splitters contain panels)
        # We need to recursively search for them
        layout = workspace.get('layout', {})
        panels = self._extract_panels_from_layout(layout)

        for panel in panels:
            panel_id = panel.get('panel_id')
            if panel_id == self._before_panel_id:
                self._before_panel_info = panel
            elif panel_id == self._after_panel_id:
                self._after_panel_info = panel

    def _extract_panels_from_layout(self, layout: Dict) -> List[Dict]:
        """Recursively extract all panels from a layout structure."""
        panels = []

        if not layout:
            return panels

        layout_type = layout.get('type', '')

        if layout_type in ('panel', 'display_panel'):
            panels.append(layout)
        elif layout_type == 'splitter':
            for child in layout.get('children', []):
                panels.extend(self._extract_panels_from_layout(child))

        return panels

    def _display_hole(self, which: str, plot_widget: pg.PlotWidget, info_label: QLabel):
        """Display the hole in the plot widget."""
        is_before = (which == 'before')
        hole_key = 'before_hole' if is_before else 'after_hole'
        panel_info = self._before_panel_info if is_before else self._after_panel_info

        hole_data = self._pairing_data.get(hole_key)
        if not hole_data:
            info_label.setText("No hole data")
            return

        # Get hole info
        centroid = hole_data.get('centroid', [0, 0])
        area_nm2 = hole_data.get('area_nm2', 0)
        vertices = hole_data.get('vertices', [])
        polygon_id = hole_data.get('polygon_id', 0)

        # Try to load image
        image_data = None
        file_path = None
        frame_num = 0

        if panel_info:
            file_path = panel_info.get('file_path')
            frame_num = panel_info.get('frame', 0)

            if file_path:
                if os.path.exists(file_path):
                    try:
                        nhdf_data = read_em_file(file_path)
                        if nhdf_data:
                            if nhdf_data.num_frames > 1 and frame_num < nhdf_data.num_frames:
                                image_data = nhdf_data.get_frame(frame_num)
                            else:
                                image_data = nhdf_data.get_frame(0)
                    except Exception as e:
                        print(f"Error loading image from {file_path}: {e}")
                else:
                    print(f"Image file not found: {file_path}")

        # Clear plot
        plot_widget.clear()

        # Display image if available
        if image_data is not None:
            img_item = pg.ImageItem(image_data)
            img_item.setOpts(axisOrder='row-major')
            plot_widget.addItem(img_item)

            # Set colormap
            cmap = pg.colormap.get('viridis')
            img_item.setColorMap(cmap)

            # Set view to show whole image
            plot_widget.setRange(xRange=[0, image_data.shape[1]], yRange=[0, image_data.shape[0]])

        # Draw polygon if vertices available
        if vertices and len(vertices) >= 3:
            # Close the polygon
            verts = vertices + [vertices[0]]
            xs = [v[0] for v in verts]
            ys = [v[1] for v in verts]

            # Draw polygon outline
            color = QColor('#00FF00') if is_before else QColor('#FF6600')
            pen = pg.mkPen(color, width=3)
            plot_widget.plot(xs, ys, pen=pen)

            # Draw filled polygon with transparency
            fill_brush = pg.mkBrush(color.red(), color.green(), color.blue(), 50)
            fill_item = pg.PlotDataItem(xs, ys, fillLevel=0, brush=fill_brush)
            # Note: fillLevel doesn't work well for arbitrary polygons, so we use just outline

        # Draw centroid marker
        if centroid:
            cx, cy = centroid
            scatter = pg.ScatterPlotItem(
                [cx], [cy],
                size=15,
                pen=pg.mkPen('#FFFFFF', width=2),
                brush=pg.mkBrush('#FF0000'),
                symbol='+'
            )
            plot_widget.addItem(scatter)

            # Zoom to centroid area with some padding
            padding = 50  # pixels
            plot_widget.setRange(
                xRange=[cx - padding, cx + padding],
                yRange=[cy - padding, cy + padding]
            )

        # Update info label
        info_parts = [
            f"ID: {polygon_id}",
            f"Area: {area_nm2:.4f} nm²",
            f"Centroid: ({centroid[0]:.1f}, {centroid[1]:.1f})"
        ]
        if file_path:
            file_name = os.path.basename(file_path)
            if image_data is not None:
                info_parts.append(f"File: {file_name} (frame {frame_num})")
            else:
                info_parts.append(f"File: {file_name} (not loaded)")
        else:
            info_parts.append("No image file linked")

        info_label.setText(" | ".join(info_parts))

    def _show_error(self, message: str):
        """Show error message in the dialog."""
        self._info_label.setText(f"<span style='color: red;'>{message}</span>")
        self._before_info.setText("Error")
        self._after_info.setText("Error")
