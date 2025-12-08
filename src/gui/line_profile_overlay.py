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
    distances: np.ndarray  # In pixels
    unit: str = "px"
    profile_id: str = ""
    width: float = 1.0  # Width in pixels for averaging
    calibration: Optional[float] = None  # nm per pixel (if available)


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

        # Calibration info (set by display panel)
        self.calibration = None  # Will be set as CalibrationInfo if available

        # Reference markers for correlation with plot
        self.reference_markers = []  # List of reference markers
        self.reference_colors = ['red', 'green', 'blue', 'magenta', 'cyan', 'orange']

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

        # Create LineSegmentROI with special configuration
        self.line_roi = pg.LineSegmentROI(
            [[start_x, start_y],
             [end_x, end_y]],
            pen=pg.mkPen(color='yellow', width=3, style=Qt.SolidLine),
            hoverPen=pg.mkPen(color='cyan', width=4),
            handlePen=pg.mkPen(color='yellow', width=10),
            handleHoverPen=pg.mkPen(color='cyan', width=10),
            movable=False  # This prevents the body from being dragged
        )

        # Make handles more visible with distinct colors for head and tail
        handles = self.line_roi.getHandles()
        for i, handle in enumerate(handles):
            handle.radius = 10  # Bigger handles for easier grabbing
            if i == 0:
                # Start handle (head) - Green square
                handle.pen = pg.mkPen('green', width=3)
                handle.brush = pg.mkBrush('green')
                handle.symbol = 's'  # Square for start
            else:
                # End handle (tail) - Red circle
                handle.pen = pg.mkPen('red', width=3)
                handle.brush = pg.mkBrush('red')
                handle.symbol = 'o'  # Circle for end
            # Ensure handles remain interactive even though body isn't movable
            handle.setAcceptedMouseButtons(Qt.LeftButton)

        # Override the line ROI mouse drag event to prevent body movement
        original_mouse_drag = self.line_roi.mouseDragEvent
        def no_body_drag(ev):
            # Check if we're dragging a handle
            for handle in self.line_roi.getHandles():
                if handle.isMoving:
                    # Allow handle movement
                    return original_mouse_drag(ev)
            # Ignore body drag attempts
            ev.ignore()

        self.line_roi.mouseDragEvent = no_body_drag

        # Add to plot with proper Z-order (on top of image)
        self.plot_item.addItem(self.line_roi)
        self.line_roi.setZValue(1000)  # High Z-value to ensure it's on top

        # Connect to ROI changes (both during and after movement)
        self.line_roi.sigRegionChanged.connect(self._on_line_changed)
        self.line_roi.sigRegionChangeFinished.connect(self._on_line_changed)

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
                # Filter out empty arrays before averaging
                valid_profiles = [p for p in profile_values if p.size > 0 and not np.all(np.isnan(p))]
                if valid_profiles and len(valid_profiles) > 0:
                    # Suppress warnings completely for this operation
                    with np.errstate(all='ignore'):
                        data = np.nanmean(np.array(valid_profiles), axis=0)
                        # Replace any remaining NaN with 0
                        data = np.nan_to_num(data, nan=0.0)
                else:
                    # All profiles were empty, use single line as fallback
                    data = ndimage.map_coordinates(
                        image,
                        [y_coords, x_coords],
                        order=1,
                        mode='constant',
                        cval=0
                    )
            else:
                # Fallback to single line
                data = ndimage.map_coordinates(
                    image,
                    [y_coords, x_coords],
                    order=1,
                    mode='constant',
                    cval=0
                )
        else:
            # Single line profile (no width averaging)
            data = ndimage.map_coordinates(
                image,
                [y_coords, x_coords],
                order=1,
                mode='constant',
                cval=0
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

        # Get calibration value if available
        cal_value = None
        if self.calibration and hasattr(self.calibration, 'scale'):
            cal_value = self.calibration.scale  # nm per pixel (or other unit per pixel)

        profile_data = LineProfileData(
            start_point=start_point,
            end_point=end_point,
            values=data,
            distances=distances,
            unit="px",
            profile_id=self._current_profile_id,
            width=self.line_width,
            calibration=cal_value
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
        # getLocalHandlePositions returns LOCAL positions relative to the ROI
        # We need to transform them to plot coordinates

        handles = self.line_roi.getLocalHandlePositions()
        if len(handles) < 2:
            return

        p1 = handles[0][1]
        p2 = handles[1][1]

        # Transform local to scene coordinates by adding ROI position
        roi_pos = self.line_roi.pos()
        x1 = roi_pos.x() + p1.x()
        y1 = roi_pos.y() + p1.y()
        x2 = roi_pos.x() + p2.x()
        y2 = roi_pos.y() + p2.y()

        # Calculate perpendicular direction
        dx = x2 - x1
        dy = y2 - y1
        length = np.sqrt(dx**2 + dy**2)
        if length == 0:
            return

        # Perpendicular unit vector (rotate 90 degrees counter-clockwise)
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

    def add_reference_marker(self, x: float, y: float, index: int = None):
        """
        Add a marker at the reference position on the image.

        Args:
            x: X coordinate on the image
            y: Y coordinate on the image
            index: Color index for the marker
        """
        # Get color based on index
        if index is None:
            index = len(self.reference_markers)
        color = self.reference_colors[index % len(self.reference_colors)]

        # Convert color name to RGB for brush
        color_map = {
            'red': (255, 0, 0),
            'green': (0, 255, 0),
            'blue': (0, 0, 255),
            'magenta': (255, 0, 255),
            'cyan': (0, 255, 255),
            'orange': (255, 165, 0)
        }
        rgb = color_map.get(color, (255, 0, 0))

        # Create a crosshair marker
        marker = pg.ScatterPlotItem(
            pos=[(x, y)],
            size=15,
            pen=pg.mkPen(color, width=2),
            brush=pg.mkBrush(*rgb, 120),
            symbol='+'
        )
        self.plot_item.addItem(marker)
        marker.setZValue(1001)  # Above the line profile
        self.reference_markers.append(marker)

    def clear_reference_markers(self):
        """Clear all reference markers."""
        for marker in self.reference_markers:
            self.plot_item.removeItem(marker)
        self.reference_markers.clear()

    def show_reference_marker(self, x: float, y: float):
        """Legacy method - adds a reference marker."""
        if x < 0 and y < 0:
            self.clear_reference_markers()
        else:
            self.add_reference_marker(x, y)

    def hide_reference_marker(self):
        """Legacy method - clears all reference markers."""
        self.clear_reference_markers()

    def get_line_endpoints(self):
        """
        Get the current line endpoints.

        Returns:
            Tuple of (start_point, end_point) or None if no line exists
        """
        if self.line_roi is None:
            return None

        handles = self.line_roi.getLocalHandlePositions()
        if len(handles) < 2:
            return None

        p1 = handles[0][1]
        p2 = handles[1][1]

        # Transform to scene coordinates
        roi_pos = self.line_roi.pos()
        x1 = roi_pos.x() + p1.x()
        y1 = roi_pos.y() + p1.y()
        x2 = roi_pos.x() + p2.x()
        y2 = roi_pos.y() + p2.y()

        return ((x1, y1), (x2, y2))