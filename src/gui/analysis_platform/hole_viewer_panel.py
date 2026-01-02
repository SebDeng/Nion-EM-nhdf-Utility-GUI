"""
Hole Viewer Panel.

Embedded panel showing the original before/after hole images from a workspace session.
Auto-updates when a point is selected in the scatter plot.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QSplitter
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

import pyqtgraph as pg
import numpy as np
import json
import os
from typing import Optional, Dict, Any, Tuple, List

from src.core.nhdf_reader import read_em_file


class HoleViewerPanel(QWidget):
    """Embedded panel to view original hole data from a workspace session."""

    # Maximum number of images to cache (to limit memory usage)
    MAX_IMAGE_CACHE_SIZE = 10

    def __init__(self, parent=None):
        super().__init__(parent)

        self._session_path: Optional[str] = None
        self._pairing_id: Optional[str] = None
        self._session_data: Optional[Dict] = None
        self._pairing_data: Optional[Dict] = None
        self._before_panel_info: Optional[Dict] = None
        self._after_panel_info: Optional[Dict] = None
        self._before_panel_id: Optional[str] = None
        self._after_panel_id: Optional[str] = None

        # Cache for loaded session data (avoid reloading same session)
        self._cached_session_path: Optional[str] = None
        self._cached_session_data: Optional[Dict] = None

        # Cache for loaded images: {(file_path, frame_num): image_data}
        self._image_cache: Dict[Tuple[str, int], np.ndarray] = {}
        self._image_cache_order: List[Tuple[str, int]] = []  # Track order for LRU eviction

        self._setup_ui()

    def _setup_ui(self):
        """Setup the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Title
        title_label = QLabel("Hole Viewer")
        title_label.setStyleSheet("font-weight: bold; font-size: 12px; padding: 4px;")
        layout.addWidget(title_label)

        # Info label
        self._info_label = QLabel("Select a point to view hole images")
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("font-size: 10px; color: #666; padding: 2px;")
        layout.addWidget(self._info_label)

        # Splitter for before/after images (vertical stacking)
        splitter = QSplitter(Qt.Vertical)

        # Before image
        before_widget = QWidget()
        before_layout = QVBoxLayout(before_widget)
        before_layout.setContentsMargins(2, 2, 2, 2)
        before_layout.setSpacing(2)

        before_title = QLabel("Before")
        before_title.setStyleSheet("font-weight: bold; font-size: 11px;")
        before_layout.addWidget(before_title)

        self._before_plot = pg.PlotWidget()
        self._before_plot.setAspectLocked(True)
        self._before_plot.getAxis('left').setLabel('Y (px)')
        self._before_plot.getAxis('bottom').setLabel('X (px)')
        self._before_plot.setMinimumHeight(150)
        before_layout.addWidget(self._before_plot)

        self._before_info = QLabel("-")
        self._before_info.setStyleSheet("font-size: 9px; color: #888;")
        self._before_info.setWordWrap(True)
        before_layout.addWidget(self._before_info)

        splitter.addWidget(before_widget)

        # After image
        after_widget = QWidget()
        after_layout = QVBoxLayout(after_widget)
        after_layout.setContentsMargins(2, 2, 2, 2)
        after_layout.setSpacing(2)

        after_title = QLabel("After")
        after_title.setStyleSheet("font-weight: bold; font-size: 11px;")
        after_layout.addWidget(after_title)

        self._after_plot = pg.PlotWidget()
        self._after_plot.setAspectLocked(True)
        self._after_plot.getAxis('left').setLabel('Y (px)')
        self._after_plot.getAxis('bottom').setLabel('X (px)')
        self._after_plot.setMinimumHeight(150)
        after_layout.addWidget(self._after_plot)

        self._after_info = QLabel("-")
        self._after_info.setStyleSheet("font-size: 9px; color: #888;")
        self._after_info.setWordWrap(True)
        after_layout.addWidget(self._after_info)

        splitter.addWidget(after_widget)

        layout.addWidget(splitter, 1)

    def set_point(self, session_path: str, pairing_id: str):
        """
        Set the point to display.

        Args:
            session_path: Path to the workspace session JSON file
            pairing_id: The pairing ID to display
        """
        if not session_path or not pairing_id:
            self.clear()
            return

        self._session_path = session_path
        self._pairing_id = pairing_id

        self._load_and_display()

    def clear(self):
        """Clear the display."""
        self._session_path = None
        self._pairing_id = None
        self._session_data = None
        self._pairing_data = None
        self._before_panel_info = None
        self._after_panel_info = None

        self._before_plot.clear()
        self._after_plot.clear()
        self._info_label.setText("Select a point to view hole images")
        self._before_info.setText("-")
        self._after_info.setText("-")

    def _load_and_display(self):
        """Load session data and display the hole."""
        try:
            # Check if session exists
            if not os.path.exists(self._session_path):
                self._show_error(f"Session not found: {os.path.basename(self._session_path)}")
                return

            # Load session (use cache if same session)
            if self._cached_session_path == self._session_path and self._cached_session_data:
                self._session_data = self._cached_session_data
            else:
                with open(self._session_path, 'r', encoding='utf-8') as f:
                    self._session_data = json.load(f)
                self._cached_session_path = self._session_path
                self._cached_session_data = self._session_data

            # Find the pairing
            self._pairing_data, workspace_idx = self._find_pairing()

            if not self._pairing_data:
                self._show_error(f"Pairing '{self._pairing_id}' not found")
                return

            # Find panel info
            self._find_panel_info(workspace_idx)

            # Update info label
            session_name = self._session_data.get('name', os.path.basename(self._session_path))
            self._info_label.setText(f"<b>{self._pairing_id}</b> from {session_name}")

            # Display images and holes
            self._display_hole('before', self._before_plot, self._before_info)
            self._display_hole('after', self._after_plot, self._after_info)

        except Exception as e:
            self._show_error(f"Error: {e}")

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
        self._before_panel_info = None
        self._after_panel_info = None

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

        # Try to load image (with caching)
        image_data = None
        file_path = None
        frame_num = 0

        if panel_info:
            file_path = panel_info.get('file_path')
            frame_num = panel_info.get('frame', 0)

            if file_path:
                image_data = self._get_cached_image(file_path, frame_num)

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

        # Update info label
        info_parts = [f"Area: {area_nm2:.2f} nm²"]
        if file_path:
            file_name = os.path.basename(file_path)
            if image_data is not None:
                info_parts.append(f"{file_name}")
            else:
                info_parts.append(f"{file_name} (not loaded)")

        info_label.setText(" | ".join(info_parts))

    def _get_cached_image(self, file_path: str, frame_num: int) -> Optional[np.ndarray]:
        """
        Get image from cache or load it.

        Uses LRU (Least Recently Used) eviction when cache is full.
        """
        cache_key = (file_path, frame_num)

        # Check if image is in cache
        if cache_key in self._image_cache:
            # Move to end of order (most recently used)
            if cache_key in self._image_cache_order:
                self._image_cache_order.remove(cache_key)
            self._image_cache_order.append(cache_key)
            return self._image_cache[cache_key]

        # Not in cache - load it
        if not os.path.exists(file_path):
            return None

        try:
            nhdf_data = read_em_file(file_path)
            if nhdf_data:
                if nhdf_data.num_frames > 1 and frame_num < nhdf_data.num_frames:
                    image_data = nhdf_data.get_frame(frame_num)
                else:
                    image_data = nhdf_data.get_frame(0)

                # Add to cache
                self._image_cache[cache_key] = image_data
                self._image_cache_order.append(cache_key)

                # Evict oldest if cache is full
                while len(self._image_cache) > self.MAX_IMAGE_CACHE_SIZE:
                    oldest_key = self._image_cache_order.pop(0)
                    if oldest_key in self._image_cache:
                        del self._image_cache[oldest_key]

                return image_data
        except Exception as e:
            print(f"Error loading image from {file_path}: {e}")

        return None

    def _show_error(self, message: str):
        """Show error message in the panel."""
        self._info_label.setText(f"<span style='color: #c00;'>{message}</span>")
        self._before_info.setText("-")
        self._after_info.setText("-")
        self._before_plot.clear()
        self._after_plot.clear()
