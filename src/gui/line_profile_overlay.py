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
    width: float = 1.0  # Width in pixels for averaging


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
        self.line_width = 5  # Default width in pixels for averaging

        # Visual indicators for line width
        self.width_lines = []  # Lines showing the width boundaries
        self.width_fill = None  # Filled area showing the width region

    def create_default_line(self):
        """Create a default line profile that can be dragged to the desired position."""
        if self.image_item.image is None:
            return

        # Remove any existing line and reset profile ID for new line
        if self.line_roi is not None:
            self.plot_item.removeItem(self.line_roi)
            self.line_roi = None

        # Reset profile ID for new line
        if hasattr(self, '_current_profile_id'):
            delattr(self, '_current_profile_id')

        # Get image dimensions
        img_shape = self.image_item.image.shape
        height, width = img_shape[0], img_shape[1] if len(img_shape) > 1 else img_shape[0]

        # Create a horizontal line across the middle from 20% to 80% of the image
        start_x = width * 0.2
        start_y = height * 0.5
        end_x = width * 0.8
        end_y = height * 0.5

        # Create LineSegmentROI with more visible settings and default width
        self.line_roi = pg.LineSegmentROI(
            [[start_x, start_y],
             [end_x, end_y]],
            pen=pg.mkPen(color='yellow', width=3, style=Qt.SolidLine),  # Thicker line
            hoverPen=pg.mkPen(color='cyan', width=4),
            handlePen=pg.mkPen(color='yellow', width=10),
            handleHoverPen=pg.mkPen(color='cyan', width=10),
            movable=True  # Explicitly enable dragging
        )

        # The line width is controlled by the line thickness (perpendicular to the line direction)

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

        # Create width indicators
        self._update_width_indicators()

        # Extract and emit profile data
        self._extract_profile()

    def _on_line_changed(self):
        """Handle changes to the line ROI."""
        if self.line_roi is not None:
            self._update_width_indicators()
            self._extract_profile()

    def _extract_profile(self):
        """Extract the line profile data from the image with width averaging."""
        if self.line_roi is None or self.image_item.image is None:
            return

        import scipy.ndimage as ndimage

        # Get line endpoints
        handles = self.line_roi.getLocalHandlePositions()
        if len(handles) < 2:
            return

        p1 = handles[0][1]
        p2 = handles[1][1]

        # Get image data
        image = self.image_item.image

        # Calculate line parameters
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()
        line_length = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)

        if line_length == 0:
            return

        # Number of points to sample along the line
        num_points = int(line_length * 2)  # Sample at ~0.5 pixel resolution

        # Create coordinates along the line
        x_coords = np.linspace(x1, x2, num_points)
        y_coords = np.linspace(y1, y2, num_points)

        # Calculate perpendicular direction for width sampling
        dx = x2 - x1
        dy = y2 - y1
        # Perpendicular vector (rotated 90 degrees)
        perp_dx = -dy / line_length
        perp_dy = dx / line_length

        # Sample points across the width
        if self.line_width > 1:
            # Create offset positions perpendicular to the line
            profile_values = []
            half_width = self.line_width / 2.0
            width_samples = max(1, int(self.line_width))

            for offset in np.linspace(-half_width, half_width, width_samples):
                # Offset the line perpendicular to its direction
                offset_x = x_coords + offset * perp_dx
                offset_y = y_coords + offset * perp_dy

                # Interpolate values along this offset line
                try:
                    values = ndimage.map_coordinates(
                        image,
                        [offset_y, offset_x],
                        order=1,  # Linear interpolation
                        mode='constant',
                        cval=np.nan
                    )
                    profile_values.append(values)
                except:
                    pass

            # Average across the width
            if profile_values:
                data = np.nanmean(profile_values, axis=0)
            else:
                # Fallback to single line
                data = ndimage.map_coordinates(
                    image,
                    [y_coords, x_coords],
                    order=1,
                    mode='constant',
                    cval=np.nan
                )
        else:
            # Single line profile (no width averaging)
            data = ndimage.map_coordinates(
                image,
                [y_coords, x_coords],
                order=1,
                mode='constant',
                cval=np.nan
            )

        if data is None or data.size == 0:
            return

        # Calculate distances along the line
        start_point = (x1, y1)
        end_point = (x2, y2)
        distances = np.linspace(0, line_length, len(data))

        # Use consistent profile_id for updates (don't increment on drag)
        if not hasattr(self, '_current_profile_id'):
            self.profile_id_counter += 1
            self._current_profile_id = f"Profile_{self.profile_id_counter}"

        profile_data = LineProfileData(
            start_point=start_point,
            end_point=end_point,
            values=data,
            distances=distances,
            unit="px",
            profile_id=self._current_profile_id,
            width=self.line_width
        )

        # Emit signal for live updates
        self.profile_created.emit(profile_data)

    def _update_width_indicators(self):
        """Update the visual indicators showing the line width."""
        # Clear existing indicators
        for line in self.width_lines:
            self.plot_item.removeItem(line)
        self.width_lines.clear()

        if self.width_fill is not None:
            self.plot_item.removeItem(self.width_fill)
            self.width_fill = None

        if self.line_roi is None or self.line_width <= 1:
            return

        # Get line endpoints
        handles = self.line_roi.getLocalHandlePositions()
        if len(handles) < 2:
            return

        p1 = handles[0][1]
        p2 = handles[1][1]
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()

        # Calculate perpendicular direction
        dx = x2 - x1
        dy = y2 - y1
        length = np.sqrt(dx**2 + dy**2)
        if length == 0:
            return

        # Perpendicular unit vector
        perp_dx = -dy / length
        perp_dy = dx / length

        # Calculate offset for width boundaries
        half_width = self.line_width / 2.0

        # Create boundary lines (parallel to main line)
        # Upper boundary
        upper_x = [x1 + half_width * perp_dx, x2 + half_width * perp_dx]
        upper_y = [y1 + half_width * perp_dy, y2 + half_width * perp_dy]

        # Lower boundary
        lower_x = [x1 - half_width * perp_dx, x2 - half_width * perp_dx]
        lower_y = [y1 - half_width * perp_dy, y2 - half_width * perp_dy]

        # Create filled polygon to show the width area
        # Vertices: upper-left, upper-right, lower-right, lower-left (closed polygon)
        polygon_x = [upper_x[0], upper_x[1], lower_x[1], lower_x[0], upper_x[0]]
        polygon_y = [upper_y[0], upper_y[1], lower_y[1], lower_y[0], upper_y[0]]

        # Create semi-transparent fill
        fill_brush = pg.mkBrush(color=(0, 255, 255, 30))  # Cyan with 30/255 alpha
        # Use PlotCurveItem for filled polygon
        self.width_fill = pg.PlotCurveItem(polygon_x, polygon_y, fillLevel='enclosed', fillBrush=fill_brush, pen=None)
        self.plot_item.addItem(self.width_fill)
        self.width_fill.setZValue(998)  # Below the boundary lines

        # Create the boundary lines with dashed style
        pen = pg.mkPen(color='cyan', width=1, style=Qt.DashLine)

        upper_line = pg.PlotDataItem(upper_x, upper_y, pen=pen)
        lower_line = pg.PlotDataItem(lower_x, lower_y, pen=pen)

        # Add connecting lines at the ends
        left_cap_x = [upper_x[0], lower_x[0]]
        left_cap_y = [upper_y[0], lower_y[0]]
        right_cap_x = [upper_x[1], lower_x[1]]
        right_cap_y = [upper_y[1], lower_y[1]]

        left_cap = pg.PlotDataItem(left_cap_x, left_cap_y, pen=pen)
        right_cap = pg.PlotDataItem(right_cap_x, right_cap_y, pen=pen)

        # Add all lines to the plot
        for line in [upper_line, lower_line, left_cap, right_cap]:
            self.plot_item.addItem(line)
            line.setZValue(999)  # Just below the main line
            self.width_lines.append(line)

    def clear_profile(self):
        """Clear the current line profile."""
        # Clear width indicators
        for line in self.width_lines:
            self.plot_item.removeItem(line)
        self.width_lines.clear()

        if self.width_fill is not None:
            self.plot_item.removeItem(self.width_fill)
            self.width_fill = None

        if self.line_roi is not None:
            self.plot_item.removeItem(self.line_roi)
            self.line_roi = None

        # Reset profile ID
        if hasattr(self, '_current_profile_id'):
            delattr(self, '_current_profile_id')

    def clear_all(self):
        """Clear all line profiles."""
        self.clear_profile()

    def set_line_width(self, width: int):
        """
        Set the width of the line profile for averaging.

        Args:
            width: Width in pixels (1 = no averaging, >1 = average across width)
        """
        self.line_width = max(1, int(width))
        # Update visual indicators and re-extract profile if a line exists
        if self.line_roi is not None:
            self._update_width_indicators()
            self._extract_profile()