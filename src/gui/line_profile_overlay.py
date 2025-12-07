"""
Line profile overlay for display panels.
"""

from PySide6.QtCore import Signal, QObject, QPointF, Qt
from PySide6.QtGui import QPen, QColor
import pyqtgraph as pg
import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class LineProfileData:
    """Data structure for line profile results."""
    start_point: Tuple[float, float]
    end_point: Tuple[float, float]
    values: np.ndarray
    distances: np.ndarray
    unit: str = "px"
    profile_id: str = ""


class LineProfileOverlay(QObject):
    """
    Manages line profile drawing and data extraction on image displays.
    """

    # Signals
    profile_created = Signal(LineProfileData)  # Emitted when a line profile is created
    profile_updated = Signal(LineProfileData)  # Emitted when profile is updated

    def __init__(self, plot_item: pg.PlotItem, image_item: pg.ImageItem):
        super().__init__()

        self.plot_item = plot_item
        self.image_item = image_item
        self.view_box = plot_item.getViewBox()

        # Line ROI for profile
        self.line_roi: Optional[pg.LineSegmentROI] = None
        self.profile_id_counter = 0

    def create_default_line(self):
        """Create a default line profile that can be dragged to the desired position."""
        if self.image_item.image is None:
            return

        # Remove any existing line
        if self.line_roi is not None:
            self.plot_item.removeItem(self.line_roi)
            self.line_roi = None

        # Get image dimensions
        img_shape = self.image_item.image.shape
        height, width = img_shape[0], img_shape[1] if len(img_shape) > 1 else img_shape[0]

        # Create a horizontal line across the middle from 20% to 80% of the image
        start_x = width * 0.2
        start_y = height * 0.5
        end_x = width * 0.8
        end_y = height * 0.5

        # Create LineSegmentROI with more visible settings
        self.line_roi = pg.LineSegmentROI(
            [[start_x, start_y],
             [end_x, end_y]],
            pen=pg.mkPen(color='yellow', width=3, style=Qt.SolidLine),  # Thicker line
            hoverPen=pg.mkPen(color='cyan', width=4),
            handlePen=pg.mkPen(color='yellow', width=10),
            handleHoverPen=pg.mkPen(color='cyan', width=10),
            movable=True  # Explicitly enable dragging
        )

        # Make handles more visible
        for handle in self.line_roi.getHandles():
            handle.radius = 8  # Bigger handles
            handle.pen = pg.mkPen('yellow', width=2)
            handle.brush = pg.mkBrush('yellow')

        # Add to plot with proper Z-order (on top of image)
        self.plot_item.addItem(self.line_roi)
        self.line_roi.setZValue(1000)  # High Z-value to ensure it's on top

        # Connect to ROI changes
        self.line_roi.sigRegionChanged.connect(self._on_line_changed)

        # Extract and emit profile data
        self._extract_profile()

    def _on_line_changed(self):
        """Handle changes to the line ROI."""
        if self.line_roi is not None:
            self._extract_profile()

    def _extract_profile(self):
        """Extract the line profile data from the image."""
        if self.line_roi is None or self.image_item.image is None:
            return

        # Get the array data from the line ROI
        data = self.line_roi.getArrayRegion(self.image_item.image, self.image_item)

        if data is None or data.size == 0:
            return

        # Get line endpoints in image coordinates
        handles = self.line_roi.getLocalHandlePositions()
        if len(handles) >= 2:
            p1 = handles[0][1]
            p2 = handles[1][1]

            start_point = (p1.x(), p1.y())
            end_point = (p2.x(), p2.y())

            # Calculate distances along the line
            num_points = len(data)
            distances = np.linspace(0, np.sqrt((p2.x() - p1.x())**2 + (p2.y() - p1.y())**2), num_points)

            # Create profile data
            self.profile_id_counter += 1
            profile_data = LineProfileData(
                start_point=start_point,
                end_point=end_point,
                values=data,
                distances=distances,
                unit="px",
                profile_id=f"Profile_{self.profile_id_counter}"
            )

            print(f"[DEBUG] Emitting profile: {profile_data.profile_id}, values: {len(data)} points")
            # Emit signal
            self.profile_created.emit(profile_data)

    def clear_profile(self):
        """Clear the current line profile."""
        if self.line_roi is not None:
            self.plot_item.removeItem(self.line_roi)
            self.line_roi = None

        self.cancel_drawing()

    def clear_all(self):
        """Clear all line profiles."""
        self.clear_profile()