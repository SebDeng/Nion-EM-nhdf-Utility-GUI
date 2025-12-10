"""
Measurement overlay for display panels.
Provides distance measurement tools with visual feedback.
"""

from PySide6.QtCore import Signal, QObject, Qt
from PySide6.QtGui import QPen, QColor, QFont
from PySide6.QtWidgets import QApplication
import pyqtgraph as pg
import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass


class SnapIndicator(pg.GraphicsObject):
    """
    Visual indicator showing when a handle is near a snap point.
    Displays a pulsing/highlighted ring around the snap point.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._snap_pos: Optional[Tuple[float, float]] = None
        self._visible = False
        self._ring_size = 12  # Size of the snap indicator ring

    def set_snap_position(self, pos: Optional[Tuple[float, float]]):
        """Set the position of the snap indicator, or None to hide it."""
        self._snap_pos = pos
        self._visible = pos is not None
        self.update()

    def boundingRect(self):
        """Return bounding rectangle."""
        if self._snap_pos is None:
            return pg.QtCore.QRectF(0, 0, 0, 0)
        margin = self._ring_size + 5
        return pg.QtCore.QRectF(
            self._snap_pos[0] - margin,
            self._snap_pos[1] - margin,
            margin * 2,
            margin * 2
        )

    def paint(self, painter, option, widget):
        """Paint the snap indicator."""
        if not self._visible or self._snap_pos is None:
            return

        x, y = self._snap_pos

        # Draw outer glow ring (larger, semi-transparent)
        glow_color = pg.mkColor(0, 255, 255, 100)  # Cyan glow
        painter.setPen(pg.mkPen(glow_color, width=4))
        painter.setBrush(pg.QtCore.Qt.NoBrush)
        painter.drawEllipse(pg.QtCore.QPointF(x, y), self._ring_size, self._ring_size)

        # Draw inner ring (brighter)
        ring_color = pg.mkColor(0, 255, 255, 220)  # Bright cyan
        painter.setPen(pg.mkPen(ring_color, width=2))
        painter.drawEllipse(pg.QtCore.QPointF(x, y), self._ring_size * 0.6, self._ring_size * 0.6)

        # Draw center dot
        painter.setBrush(pg.mkBrush(ring_color))
        painter.setPen(pg.QtCore.Qt.NoPen)
        painter.drawEllipse(pg.QtCore.QPointF(x, y), 3, 3)


class ConstrainedLineSegmentROI(pg.LineSegmentROI):
    """
    LineSegmentROI with Shift-key constraint support.
    When Shift is held during handle drag, constrains to horizontal or vertical.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def movePoint(self, handle, pos, modifiers=None, finish=True, coords='parent'):
        """Override movePoint to add Shift-constraint for horizontal/vertical lines."""
        # Check if Shift is held
        shift_held = bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)

        if shift_held and coords == 'parent':
            # Get handle info - find which handle index is being moved
            handle_info = None
            other_handle_info = None
            for info in self.handles:
                if info['item'] is handle:
                    handle_info = info
                else:
                    other_handle_info = info

            if handle_info and other_handle_info:
                # Get other handle's current position in parent coordinates
                other_handle_item = other_handle_info['item']
                other_pos = other_handle_item.pos()

                # pos is in parent (local) coordinates
                new_x = pos.x()
                new_y = pos.y()

                # Calculate differences
                dx = abs(new_x - other_pos.x())
                dy = abs(new_y - other_pos.y())

                # Constrain to horizontal or vertical based on which is closer
                if dx > dy:
                    # More horizontal - lock Y to other handle's Y
                    new_y = other_pos.y()
                else:
                    # More vertical - lock X to other handle's X
                    new_x = other_pos.x()

                # Create constrained position
                pos = pg.QtCore.QPointF(new_x, new_y)

        # Call parent implementation
        return super().movePoint(handle, pos, modifiers, finish, coords)


@dataclass
class MeasurementData:
    """Data structure for measurement results."""
    start_point: Tuple[float, float]
    end_point: Tuple[float, float]
    distance_px: float  # Distance in pixels
    distance_nm: Optional[float]  # Distance in nm (if calibration available)
    measurement_id: str = ""
    calibration: Optional[float] = None  # nm per pixel


class MeasurementLine(pg.GraphicsObject):
    """
    A single measurement line with distance label.
    """

    def __init__(self, start_pos, end_pos, measurement_id: str, color='lime', parent=None):
        super().__init__(parent)
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.measurement_id = measurement_id
        self.color = color
        self.distance_px = 0.0
        self.distance_nm = None
        self.calibration = None
        self._calculate_distance()

    def _calculate_distance(self):
        """Calculate the distance between start and end points."""
        dx = self.end_pos[0] - self.start_pos[0]
        dy = self.end_pos[1] - self.start_pos[1]
        self.distance_px = np.sqrt(dx**2 + dy**2)
        if self.calibration:
            self.distance_nm = self.distance_px * self.calibration
        else:
            self.distance_nm = None

    def set_calibration(self, calibration: float):
        """Set the calibration value (nm per pixel)."""
        self.calibration = calibration
        self._calculate_distance()
        self.update()

    def boundingRect(self):
        """Return the bounding rectangle."""
        x1, y1 = self.start_pos
        x2, y2 = self.end_pos
        margin = 50  # Extra margin for text label
        return pg.QtCore.QRectF(
            min(x1, x2) - margin,
            min(y1, y2) - margin,
            abs(x2 - x1) + 2 * margin,
            abs(y2 - y1) + 2 * margin
        )

    def paint(self, painter, option, widget):
        """Paint the measurement line and label."""
        x1, y1 = self.start_pos
        x2, y2 = self.end_pos

        # Draw the main line
        pen = QPen(QColor(self.color))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Draw endpoint markers (small circles)
        marker_size = 6
        brush = pg.mkBrush(self.color)
        painter.setBrush(brush)
        painter.drawEllipse(int(x1 - marker_size/2), int(y1 - marker_size/2), marker_size, marker_size)
        painter.drawEllipse(int(x2 - marker_size/2), int(y2 - marker_size/2), marker_size, marker_size)

        # Draw distance label at midpoint
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2

        # Format the distance text
        if self.distance_nm is not None:
            if self.distance_nm >= 1000:
                text = f"{self.distance_nm/1000:.2f} μm"
            elif self.distance_nm >= 1:
                text = f"{self.distance_nm:.2f} nm"
            else:
                text = f"{self.distance_nm:.3f} nm"
        else:
            text = f"{self.distance_px:.1f} px"

        # Draw text background for visibility
        font = QFont("Arial", 10)
        painter.setFont(font)

        # Calculate text position (offset from line)
        # Get perpendicular direction
        dx = x2 - x1
        dy = y2 - y1
        length = np.sqrt(dx**2 + dy**2)
        if length > 0:
            # Perpendicular offset (15 pixels away from line)
            perp_x = -dy / length * 15
            perp_y = dx / length * 15
        else:
            perp_x, perp_y = 0, -15

        text_x = mid_x + perp_x
        text_y = mid_y + perp_y

        # Draw text background
        text_rect = painter.fontMetrics().boundingRect(text)
        bg_rect = pg.QtCore.QRectF(
            text_x - text_rect.width()/2 - 4,
            text_y - text_rect.height()/2 - 2,
            text_rect.width() + 8,
            text_rect.height() + 4
        )
        painter.setBrush(pg.mkBrush(0, 0, 0, 180))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(bg_rect, 3, 3)

        # Draw text
        painter.setPen(QPen(QColor(self.color)))
        painter.drawText(
            int(text_x - text_rect.width()/2),
            int(text_y + text_rect.height()/4),
            text
        )


class MeasurementOverlay(QObject):
    """
    Manages measurement tools on image displays.
    Allows creating multiple distance measurement lines.
    """

    # Signals
    measurement_created = Signal(MeasurementData)  # Emitted when a measurement is created
    measurement_updated = Signal(MeasurementData)  # Emitted when measurement is updated
    measurements_cleared = Signal()  # Emitted when all measurements are cleared

    def __init__(self, plot_item: pg.PlotItem, image_item: pg.ImageItem):
        super().__init__()

        self.plot_item = plot_item
        self.image_item = image_item
        self.view_box = plot_item.getViewBox()

        # List of active measurement line ROIs (supports multiple simultaneous measurements)
        self.active_line_rois: List[pg.LineSegmentROI] = []
        self.measurement_id_counter = 0

        # List of completed measurements (for backwards compatibility, rarely used now)
        self.completed_measurements: List[MeasurementLine] = []

        # Colors for measurements (cycle through these)
        self.measurement_colors = ['lime', 'cyan', 'magenta', 'yellow', 'orange', 'red']
        self.color_index = 0

        # Calibration info (set by display panel)
        self.calibration = None  # Will be set as CalibrationInfo if available

        # Snap points for magnetic snapping (set by display panel)
        self.snap_points: List[Tuple[float, float]] = []
        self.snap_threshold = 15.0  # pixels

        # Snap indicator for visual feedback during dragging
        self._snap_indicator = SnapIndicator()
        self.plot_item.addItem(self._snap_indicator)
        self._snap_indicator.setZValue(2000)  # Above everything

    def get_next_color(self) -> str:
        """Get the next color in the cycle."""
        color = self.measurement_colors[self.color_index % len(self.measurement_colors)]
        self.color_index += 1
        return color

    def create_measurement_line(self):
        """Create a new measurement line that can be positioned by the user."""
        if self.image_item.image is None:
            return

        # Get image dimensions
        img_shape = self.image_item.image.shape
        height, width = img_shape[0], img_shape[1] if len(img_shape) > 1 else img_shape[0]

        # Calculate position offset based on number of existing lines
        offset = len(self.active_line_rois) * 0.05
        start_x = width * (0.3 + offset)
        start_y = height * (0.5 + offset)
        end_x = width * (0.7 + offset)
        end_y = height * (0.5 + offset)

        # Clamp to image bounds
        start_x = min(start_x, width * 0.9)
        start_y = min(start_y, height * 0.9)
        end_x = min(end_x, width * 0.95)
        end_y = min(end_y, height * 0.9)

        # Get the color for this measurement
        color = self.get_next_color()
        qt_color = QColor(color)

        # Increment counter
        self.measurement_id_counter += 1

        # Create ConstrainedLineSegmentROI (supports Shift for H/V constraint)
        line_roi = ConstrainedLineSegmentROI(
            [[start_x, start_y],
             [end_x, end_y]],
            pen=pg.mkPen(color=qt_color, width=2, style=Qt.SolidLine),
            hoverPen=pg.mkPen(color='white', width=3),
            handlePen=pg.mkPen(color=qt_color, width=8),
            handleHoverPen=pg.mkPen(color='white', width=10),
            movable=False  # Body not movable, only endpoints
        )

        # Store metadata on the ROI
        line_roi._measurement_color = color
        line_roi._measurement_id = self.measurement_id_counter

        # Make handles more visible
        handles = line_roi.getHandles()
        for handle in handles:
            handle.radius = 8
            handle.pen = pg.mkPen(qt_color, width=2)
            handle.brush = pg.mkBrush(qt_color)
            handle.setAcceptedMouseButtons(Qt.LeftButton)

        # Override mouse drag to prevent body movement but allow handle movement
        original_mouse_drag = line_roi.mouseDragEvent
        def no_body_drag(ev, roi=line_roi):
            for handle in roi.getHandles():
                if handle.isMoving:
                    return original_mouse_drag(ev)
            ev.ignore()

        line_roi.mouseDragEvent = no_body_drag

        # Add to plot and list
        self.plot_item.addItem(line_roi)
        line_roi.setZValue(1000 + len(self.active_line_rois))
        self.active_line_rois.append(line_roi)

        # Connect to ROI changes
        line_roi.sigRegionChanged.connect(lambda: self._on_line_changed(line_roi))
        line_roi.sigRegionChangeFinished.connect(lambda: self._on_line_change_finished(line_roi))

        # Emit initial measurement
        self._emit_measurement_data_for_roi(line_roi)

    def _on_line_changed(self, line_roi: pg.LineSegmentROI):
        """Handle changes to a measurement line ROI."""
        if line_roi in self.active_line_rois:
            self._emit_measurement_data_for_roi(line_roi)
            # Show snap indicator if near a snap point (during dragging)
            self._update_snap_indicator(line_roi)

    def _update_snap_indicator(self, line_roi: pg.LineSegmentROI):
        """Update snap indicator to show which snap point we're near."""
        if not self.snap_points:
            self._snap_indicator.set_snap_position(None)
            return

        # Get current handle positions
        handles = line_roi.getLocalHandlePositions()
        if len(handles) < 2:
            self._snap_indicator.set_snap_position(None)
            return

        p1 = handles[0][1]
        p2 = handles[1][1]

        roi_pos = line_roi.pos()
        x1 = roi_pos.x() + p1.x()
        y1 = roi_pos.y() + p1.y()
        x2 = roi_pos.x() + p2.x()
        y2 = roi_pos.y() + p2.y()

        # Check both endpoints for nearby snap points
        snap1 = self.find_nearest_snap_point((x1, y1))
        snap2 = self.find_nearest_snap_point((x2, y2))

        # Show indicator for the closest snap point (prefer snap1 if both exist)
        if snap1:
            self._snap_indicator.set_snap_position(snap1)
        elif snap2:
            self._snap_indicator.set_snap_position(snap2)
        else:
            self._snap_indicator.set_snap_position(None)

    def _on_line_change_finished(self, line_roi: pg.LineSegmentROI):
        """Handle when a measurement line ROI change is finished (snap to points)."""
        if line_roi not in self.active_line_rois:
            return

        # Hide snap indicator
        self._snap_indicator.set_snap_position(None)

        # Try to snap endpoints to snap points
        if self.snap_points:
            self._try_snap_line_endpoints(line_roi)

        # Emit updated measurement
        self._emit_measurement_data_for_roi(line_roi)

    def _try_snap_line_endpoints(self, line_roi: pg.LineSegmentROI):
        """Try to snap line endpoints to nearby snap points."""
        if not self.snap_points:
            return

        # Get current handle positions
        handles = line_roi.getLocalHandlePositions()
        if len(handles) < 2:
            return

        p1 = handles[0][1]
        p2 = handles[1][1]

        roi_pos = line_roi.pos()
        x1 = roi_pos.x() + p1.x()
        y1 = roi_pos.y() + p1.y()
        x2 = roi_pos.x() + p2.x()
        y2 = roi_pos.y() + p2.y()

        # Check if either endpoint should snap
        snap1 = self.find_nearest_snap_point((x1, y1))
        snap2 = self.find_nearest_snap_point((x2, y2))

        # Update handle positions if snapping
        if snap1 or snap2:
            # Block signals to prevent recursion
            line_roi.blockSignals(True)
            try:
                handle_items = line_roi.getHandles()
                if snap1 and len(handle_items) > 0:
                    # Convert snap point to local coordinates
                    local_x1 = snap1[0] - roi_pos.x()
                    local_y1 = snap1[1] - roi_pos.y()
                    handle_items[0].setPos(local_x1, local_y1)

                if snap2 and len(handle_items) > 1:
                    # Convert snap point to local coordinates
                    local_x2 = snap2[0] - roi_pos.x()
                    local_y2 = snap2[1] - roi_pos.y()
                    handle_items[1].setPos(local_x2, local_y2)
            finally:
                line_roi.blockSignals(False)
                # Update the ROI display
                line_roi.update()

    def _emit_measurement_data_for_roi(self, line_roi: pg.LineSegmentROI):
        """Calculate and emit measurement data for a specific line ROI."""
        if line_roi is None:
            return

        # Get line endpoints
        handles = line_roi.getLocalHandlePositions()
        if len(handles) < 2:
            return

        p1 = handles[0][1]
        p2 = handles[1][1]

        roi_pos = line_roi.pos()
        x1 = roi_pos.x() + p1.x()
        y1 = roi_pos.y() + p1.y()
        x2 = roi_pos.x() + p2.x()
        y2 = roi_pos.y() + p2.y()

        # Calculate distance
        dx = x2 - x1
        dy = y2 - y1
        distance_px = np.sqrt(dx**2 + dy**2)

        # Get calibration value if available
        cal_value = None
        distance_nm = None
        if self.calibration and hasattr(self.calibration, 'scale'):
            cal_value = self.calibration.scale
            distance_nm = distance_px * cal_value

        # Get measurement ID from the ROI
        measurement_id = f"Measurement_{getattr(line_roi, '_measurement_id', 0)}"

        measurement_data = MeasurementData(
            start_point=(x1, y1),
            end_point=(x2, y2),
            distance_px=distance_px,
            distance_nm=distance_nm,
            measurement_id=measurement_id,
            calibration=cal_value
        )

        self.measurement_created.emit(measurement_data)

    def set_snap_points(self, points: List[Tuple[float, float]]):
        """Set the snap points for magnetic snapping."""
        self.snap_points = points

    def find_nearest_snap_point(self, pos: Tuple[float, float]) -> Optional[Tuple[float, float]]:
        """Find the nearest snap point within threshold distance."""
        if not self.snap_points:
            return None

        min_dist = float('inf')
        nearest = None

        for snap_pos in self.snap_points:
            dx = pos[0] - snap_pos[0]
            dy = pos[1] - snap_pos[1]
            dist = np.sqrt(dx**2 + dy**2)
            if dist < min_dist and dist <= self.snap_threshold:
                min_dist = dist
                nearest = snap_pos

        return nearest

    def clear_active(self):
        """Clear all active (uncommitted) measurement lines."""
        for line_roi in self.active_line_rois:
            self.plot_item.removeItem(line_roi)
        self.active_line_rois.clear()

    def clear_all(self):
        """Clear all measurements (active and completed)."""
        # Clear all active lines
        self.clear_active()

        # Clear completed measurements
        for measurement in self.completed_measurements:
            self.plot_item.removeItem(measurement)
        self.completed_measurements.clear()

        # Reset counters
        self.measurement_id_counter = 0
        self.color_index = 0

        self.measurements_cleared.emit()

    def clear_last(self):
        """Remove the last measurement (active ROI first, then completed)."""
        # First remove from active ROIs if any exist
        if self.active_line_rois:
            last_roi = self.active_line_rois.pop()
            self.plot_item.removeItem(last_roi)
            if self.color_index > 0:
                self.color_index -= 1
        # Otherwise remove from completed measurements
        elif self.completed_measurements:
            last_measurement = self.completed_measurements.pop()
            self.plot_item.removeItem(last_measurement)
            if self.color_index > 0:
                self.color_index -= 1

    def has_active_measurement(self) -> bool:
        """Check if there are any active measurement lines."""
        return len(self.active_line_rois) > 0

    def get_measurement_count(self) -> int:
        """Get the total number of measurements (active + completed)."""
        return len(self.active_line_rois) + len(self.completed_measurements)

    def get_all_measurements(self) -> List[MeasurementData]:
        """Get all completed measurement data."""
        measurements = []
        for m in self.completed_measurements:
            measurements.append(MeasurementData(
                start_point=m.start_pos,
                end_point=m.end_pos,
                distance_px=m.distance_px,
                distance_nm=m.distance_nm,
                measurement_id=m.measurement_id,
                calibration=m.calibration
            ))
        return measurements

    def set_calibration(self, calibration):
        """Set calibration for all measurements."""
        self.calibration = calibration

        # Update all completed measurements
        if calibration and hasattr(calibration, 'scale'):
            for m in self.completed_measurements:
                m.set_calibration(calibration.scale)
