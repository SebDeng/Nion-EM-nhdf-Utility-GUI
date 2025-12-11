"""
Measurement overlay for display panels.
Provides distance measurement tools with visual feedback.
"""

from PySide6.QtCore import Signal, QObject, Qt, QPointF
from PySide6.QtGui import QPen, QColor, QFont, QPainterPath
from PySide6.QtWidgets import QApplication, QGraphicsItem
import pyqtgraph as pg
import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass


class LargeHandlePolyLineROI(pg.PolyLineROI):
    """
    Custom PolyLineROI with larger handles for easier selection.
    Automatically resizes all handles including newly added ones.
    """

    HANDLE_RADIUS = 10  # Larger than default ~5

    def __init__(self, positions, closed=False, pos=None, **args):
        # Initialize handle color BEFORE super().__init__ because addHandle is called during init
        self._handle_color = QColor('lime')  # Default, will be set later
        super().__init__(positions, closed=closed, pos=pos, **args)
        # Resize initial handles (some may not have been caught by addHandle override)
        self._resize_all_handles()

    def set_handle_color(self, color: QColor):
        """Set the color for handles."""
        self._handle_color = color
        self._resize_all_handles()

    def _resize_all_handles(self):
        """Resize all handles to the larger size."""
        for handle in self.getHandles():
            handle.radius = self.HANDLE_RADIUS
            handle.pen = pg.mkPen(self._handle_color, width=2)
            handle.brush = pg.mkBrush(self._handle_color)
            handle.buildPath()
            handle.update()

    def addHandle(self, info, index=None):
        """Override to ensure new handles are also large."""
        handle = super().addHandle(info, index)
        # Resize the newly added handle
        if handle:
            handle.radius = self.HANDLE_RADIUS
            handle.pen = pg.mkPen(self._handle_color, width=2)
            handle.brush = pg.mkBrush(self._handle_color)
            handle.buildPath()
            handle.update()
        return handle

    def segmentClicked(self, segment, ev=None, pos=None):
        """Override to resize handle after segment click adds new vertex."""
        super().segmentClicked(segment, ev, pos)
        # Resize all handles after a new one is added
        self._resize_all_handles()


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


class DraggableDistanceLabel(pg.GraphicsObject):
    """
    A draggable label that displays distance for a measurement line.
    Can be repositioned by the user while maintaining a connector line
    back to the measurement line's midpoint.
    """

    # Default font size
    DEFAULT_FONT_SIZE = 12

    def __init__(self, color: str = 'lime', parent=None):
        super().__init__(parent)
        self._color = color
        self._text = "--"
        self._label_pos = QPointF(0, 0)  # Label position (can be dragged)
        self._anchor_pos = QPointF(0, 0)  # Line midpoint (anchor for connector)
        self._is_dragging = False
        self._drag_offset = QPointF(0, 0)
        self._user_offset = QPointF(0, 0)  # User's drag offset from anchor
        self._visible = True
        self._font_size = self.DEFAULT_FONT_SIZE
        self._font = QFont("Arial", self._font_size, QFont.Bold)
        self._padding = 6
        self._show_connector = True  # Show line from label to anchor

        # Enable mouse interaction
        self.setFlag(QGraphicsItem.ItemIsMovable, False)  # We handle movement manually
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.LeftButton)

        # Important: Ignore transformations so text doesn't flip with image
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)

    def set_text(self, text: str, defer_update: bool = False):
        """Set the distance text to display."""
        if self._text == text:
            return  # Skip if unchanged
        self._text = text
        if not defer_update:
            self.update()

    def set_color(self, color: str):
        """Set the label color."""
        self._color = color
        self.update()

    def set_anchor_position(self, x: float, y: float, defer_update: bool = False):
        """Set the anchor position (measurement line midpoint) in item coordinates."""
        new_pos = QPointF(x, y)
        if self._anchor_pos == new_pos:
            return  # Skip if unchanged
        self._anchor_pos = new_pos
        # Update label position based on anchor + user offset
        self._label_pos = self._anchor_pos + self._user_offset
        # Move the item to the anchor position (for ItemIgnoresTransformations)
        self.setPos(self._anchor_pos)
        if not defer_update:
            self.prepareGeometryChange()
            self.update()

    def update_position_and_text(self, x: float, y: float, text: str):
        """Batch update position and text in a single repaint."""
        self._anchor_pos = QPointF(x, y)
        self._label_pos = self._anchor_pos + self._user_offset
        self.setPos(self._anchor_pos)
        self._text = text
        self.prepareGeometryChange()
        self.update()

    def reset_position(self):
        """Reset label to default position (at anchor with small offset)."""
        self._user_offset = QPointF(30, -30)  # Default offset above and to the right (in screen pixels)
        self._label_pos = self._anchor_pos + self._user_offset
        self.prepareGeometryChange()
        self.update()

    def set_visible(self, visible: bool):
        """Set label visibility."""
        self._visible = visible
        self.update()

    def is_visible(self) -> bool:
        """Check if label is visible."""
        return self._visible

    def set_show_connector(self, show: bool):
        """Set whether to show the connector line."""
        self._show_connector = show
        self.update()

    def set_font_size(self, size: int):
        """Set the font size for the label."""
        self._font_size = max(8, min(32, size))  # Clamp between 8 and 32
        self._font = QFont("Arial", self._font_size, QFont.Bold)
        self.prepareGeometryChange()
        self.update()

    def get_font_size(self) -> int:
        """Get the current font size."""
        return self._font_size

    def boundingRect(self):
        """Return bounding rectangle encompassing label and connector."""
        if not self._visible:
            return pg.QtCore.QRectF(0, 0, 0, 0)

        # Calculate text size
        fm = pg.QtGui.QFontMetrics(self._font)
        text_rect = fm.boundingRect(self._text)
        text_width = text_rect.width() + self._padding * 2
        text_height = text_rect.height() + self._padding * 2

        # With ItemIgnoresTransformations, we work in screen coordinates relative to anchor (0,0)
        offset_x = self._user_offset.x()
        offset_y = self._user_offset.y()

        # Label rectangle relative to anchor
        label_left = offset_x - text_width / 2
        label_top = offset_y - text_height / 2

        # Include anchor point (0,0) and connector in bounds
        min_x = min(label_left, 0) - 10
        min_y = min(label_top, 0) - 10
        max_x = max(label_left + text_width, 0) + 10
        max_y = max(label_top + text_height, 0) + 10

        return pg.QtCore.QRectF(min_x, min_y, max_x - min_x, max_y - min_y)

    def paint(self, painter, option, widget):
        """Paint the label and connector line."""
        if not self._visible:
            return

        color = QColor(self._color)
        painter.setFont(self._font)

        # Calculate text dimensions
        fm = painter.fontMetrics()
        text_rect = fm.boundingRect(self._text)
        text_width = text_rect.width() + self._padding * 2
        text_height = text_rect.height() + self._padding * 2

        # With ItemIgnoresTransformations, anchor is at (0,0), label is at user_offset
        label_x = self._user_offset.x()
        label_y = self._user_offset.y()

        # Draw connector line from anchor (0,0) to label
        if self._show_connector:
            offset_dist = (self._user_offset.x()**2 + self._user_offset.y()**2)**0.5
            if offset_dist > 15:  # Only show connector if label is far enough from anchor
                # Draw thin connector line
                connector_pen = QPen(color)
                connector_pen.setWidth(1)
                connector_pen.setStyle(Qt.DashLine)
                painter.setPen(connector_pen)
                painter.drawLine(0, 0, int(label_x), int(label_y))

                # Draw small circle at anchor point (0,0)
                painter.setBrush(pg.mkBrush(color))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(-3, -3, 6, 6)

        # Draw label background (rounded rectangle)
        bg_rect = pg.QtCore.QRectF(
            label_x - text_width / 2,
            label_y - text_height / 2,
            text_width,
            text_height
        )

        # Background with slight transparency
        bg_color = QColor(0, 0, 0, 200)
        painter.setBrush(pg.mkBrush(bg_color))
        border_pen = QPen(color)
        border_pen.setWidth(2)
        painter.setPen(border_pen)
        painter.drawRoundedRect(bg_rect, 4, 4)

        # Draw text
        painter.setPen(QPen(color))
        painter.drawText(
            int(label_x - text_rect.width() / 2),
            int(label_y + text_rect.height() / 4),
            self._text
        )

        # Draw drag handle indicator (small triangle at corner when hovered)
        if self._is_dragging or self.isUnderMouse():
            handle_size = 8
            handle_x = label_x + text_width / 2 - handle_size - 2
            handle_y = label_y + text_height / 2 - handle_size - 2

            path = QPainterPath()
            path.moveTo(handle_x + handle_size, handle_y)
            path.lineTo(handle_x + handle_size, handle_y + handle_size)
            path.lineTo(handle_x, handle_y + handle_size)
            path.closeSubpath()

            painter.setBrush(pg.mkBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawPath(path)

    def hoverEnterEvent(self, event):
        """Handle mouse hover enter."""
        self.setCursor(Qt.OpenHandCursor)
        self.update()

    def hoverLeaveEvent(self, event):
        """Handle mouse hover leave."""
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def mousePressEvent(self, event):
        """Handle mouse press for dragging."""
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            # Store offset from click position to label center
            self._drag_offset = event.pos() - QPointF(self._user_offset.x(), self._user_offset.y())
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging."""
        if self._is_dragging:
            # Calculate new offset from anchor
            new_offset = event.pos() - self._drag_offset
            self._user_offset = QPointF(new_offset.x(), new_offset.y())
            self.prepareGeometryChange()
            self.update()
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        """Handle mouse release."""
        if event.button() == Qt.LeftButton and self._is_dragging:
            self._is_dragging = False
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
        else:
            event.ignore()

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to reset position."""
        if event.button() == Qt.LeftButton:
            self.reset_position()
            event.accept()
        else:
            event.ignore()


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


@dataclass
class PolygonAreaData:
    """Data structure for polygon area measurement results."""
    vertices: List[Tuple[float, float]]  # List of (x, y) vertex coordinates
    area_px: float  # Area in square pixels
    area_nm2: Optional[float]  # Area in nm² (if calibration available)
    perimeter_px: float  # Perimeter in pixels
    perimeter_nm: Optional[float]  # Perimeter in nm
    centroid: Tuple[float, float]  # Center of the polygon
    measurement_id: str = ""
    calibration: Optional[float] = None  # nm per pixel


class DraggableAreaLabel(pg.GraphicsObject):
    """
    A draggable label that displays area for a polygon measurement.
    Similar to DraggableDistanceLabel but for area values.
    """

    DEFAULT_FONT_SIZE = 12

    def __init__(self, color: str = 'lime', parent=None):
        super().__init__(parent)
        self._color = color
        self._text = "--"
        self._label_pos = QPointF(0, 0)
        self._anchor_pos = QPointF(0, 0)  # Polygon centroid
        self._is_dragging = False
        self._drag_offset = QPointF(0, 0)
        self._user_offset = QPointF(0, 0)
        self._visible = True
        self._font_size = self.DEFAULT_FONT_SIZE
        self._font = QFont("Arial", self._font_size, QFont.Bold)
        self._padding = 6
        self._show_connector = True

        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)

    def set_text(self, text: str, defer_update: bool = False):
        """Set the area text to display."""
        if self._text == text:
            return  # Skip if unchanged
        self._text = text
        if not defer_update:
            self.update()

    def set_color(self, color: str):
        """Set the label color."""
        self._color = color
        self.update()

    def set_anchor_position(self, x: float, y: float, defer_update: bool = False):
        """Set the anchor position (polygon centroid)."""
        new_pos = QPointF(x, y)
        if self._anchor_pos == new_pos:
            return  # Skip if unchanged
        self._anchor_pos = new_pos
        self._label_pos = self._anchor_pos + self._user_offset
        self.setPos(self._anchor_pos)
        if not defer_update:
            self.prepareGeometryChange()
            self.update()

    def update_position_and_text(self, x: float, y: float, text: str):
        """Batch update position and text in a single repaint."""
        self._anchor_pos = QPointF(x, y)
        self._label_pos = self._anchor_pos + self._user_offset
        self.setPos(self._anchor_pos)
        self._text = text
        self.prepareGeometryChange()
        self.update()

    def reset_position(self):
        """Reset label to default position."""
        self._user_offset = QPointF(40, -40)
        self._label_pos = self._anchor_pos + self._user_offset
        self.prepareGeometryChange()
        self.update()

    def set_visible(self, visible: bool):
        """Set label visibility."""
        self._visible = visible
        self.update()

    def is_visible(self) -> bool:
        """Check if label is visible."""
        return self._visible

    def set_font_size(self, size: int):
        """Set the font size for the label."""
        self._font_size = max(8, min(32, size))
        self._font = QFont("Arial", self._font_size, QFont.Bold)
        self.prepareGeometryChange()
        self.update()

    def get_font_size(self) -> int:
        """Get the current font size."""
        return self._font_size

    def boundingRect(self):
        """Return bounding rectangle."""
        if not self._visible:
            return pg.QtCore.QRectF(0, 0, 0, 0)

        fm = pg.QtGui.QFontMetrics(self._font)
        text_rect = fm.boundingRect(self._text)
        text_width = text_rect.width() + self._padding * 2
        text_height = text_rect.height() + self._padding * 2

        offset_x = self._user_offset.x()
        offset_y = self._user_offset.y()

        label_left = offset_x - text_width / 2
        label_top = offset_y - text_height / 2

        min_x = min(label_left, 0) - 10
        min_y = min(label_top, 0) - 10
        max_x = max(label_left + text_width, 0) + 10
        max_y = max(label_top + text_height, 0) + 10

        return pg.QtCore.QRectF(min_x, min_y, max_x - min_x, max_y - min_y)

    def paint(self, painter, option, widget):
        """Paint the label and connector line."""
        if not self._visible:
            return

        color = QColor(self._color)
        painter.setFont(self._font)

        fm = painter.fontMetrics()
        text_rect = fm.boundingRect(self._text)
        text_width = text_rect.width() + self._padding * 2
        text_height = text_rect.height() + self._padding * 2

        label_x = self._user_offset.x()
        label_y = self._user_offset.y()

        # Draw connector line
        if self._show_connector:
            offset_dist = (self._user_offset.x()**2 + self._user_offset.y()**2)**0.5
            if offset_dist > 15:
                connector_pen = QPen(color)
                connector_pen.setWidth(1)
                connector_pen.setStyle(Qt.DashLine)
                painter.setPen(connector_pen)
                painter.drawLine(0, 0, int(label_x), int(label_y))

                painter.setBrush(pg.mkBrush(color))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(-3, -3, 6, 6)

        # Draw label background
        bg_rect = pg.QtCore.QRectF(
            label_x - text_width / 2,
            label_y - text_height / 2,
            text_width,
            text_height
        )

        bg_color = QColor(0, 0, 0, 200)
        painter.setBrush(pg.mkBrush(bg_color))
        border_pen = QPen(color)
        border_pen.setWidth(2)
        painter.setPen(border_pen)
        painter.drawRoundedRect(bg_rect, 4, 4)

        # Draw text
        painter.setPen(QPen(color))
        painter.drawText(
            int(label_x - text_rect.width() / 2),
            int(label_y + text_rect.height() / 4),
            self._text
        )

        # Draw drag handle indicator when hovered
        if self._is_dragging or self.isUnderMouse():
            handle_size = 8
            handle_x = label_x + text_width / 2 - handle_size - 2
            handle_y = label_y + text_height / 2 - handle_size - 2

            path = QPainterPath()
            path.moveTo(handle_x + handle_size, handle_y)
            path.lineTo(handle_x + handle_size, handle_y + handle_size)
            path.lineTo(handle_x, handle_y + handle_size)
            path.closeSubpath()

            painter.setBrush(pg.mkBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawPath(path)

    def hoverEnterEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        self.update()

    def hoverLeaveEvent(self, event):
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._drag_offset = event.pos() - QPointF(self._user_offset.x(), self._user_offset.y())
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            new_offset = event.pos() - self._drag_offset
            self._user_offset = QPointF(new_offset.x(), new_offset.y())
            self.prepareGeometryChange()
            self.update()
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._is_dragging:
            self._is_dragging = False
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
        else:
            event.ignore()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.reset_position()
            event.accept()
        else:
            event.ignore()


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
    Allows creating multiple distance measurement lines and polygon area measurements.
    """

    # Signals
    measurement_created = Signal(MeasurementData)  # Emitted when a measurement is created
    measurement_updated = Signal(MeasurementData)  # Emitted when measurement is updated
    measurements_cleared = Signal()  # Emitted when all measurements are cleared
    polygon_area_created = Signal(PolygonAreaData)  # Emitted when polygon area is measured

    def __init__(self, plot_item: pg.PlotItem, image_item: pg.ImageItem):
        super().__init__()

        self.plot_item = plot_item
        self.image_item = image_item
        self.view_box = plot_item.getViewBox()

        # List of active measurement line ROIs (supports multiple simultaneous measurements)
        self.active_line_rois: List[pg.LineSegmentROI] = []
        self.measurement_id_counter = 0

        # Dictionary mapping line ROI to its draggable label
        self._line_labels: dict = {}  # {line_roi: DraggableDistanceLabel}

        # Polygon area measurements
        self.active_polygon_rois: List[pg.PolyLineROI] = []
        self.polygon_id_counter = 0
        self._polygon_labels: dict = {}  # {polygon_roi: DraggableAreaLabel}

        # Whether to show floating labels (can be toggled)
        self._show_labels = True

        # Current font size for labels
        self._label_font_size = DraggableDistanceLabel.DEFAULT_FONT_SIZE

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

        # Create draggable distance label for this line
        label = DraggableDistanceLabel(color=color)
        label.set_font_size(self._label_font_size)  # Use current font size setting
        self.plot_item.addItem(label)
        label.setZValue(1500 + len(self.active_line_rois))  # Above lines but below snap indicator
        label.set_visible(self._show_labels)
        self._line_labels[line_roi] = label

        # Set initial label position at line midpoint
        mid_x = (start_x + end_x) / 2
        mid_y = (start_y + end_y) / 2
        label.set_anchor_position(mid_x, mid_y)
        label.reset_position()

        # Connect to ROI changes
        line_roi.sigRegionChanged.connect(lambda: self._on_line_changed(line_roi))
        line_roi.sigRegionChangeFinished.connect(lambda: self._on_line_change_finished(line_roi))

        # Emit initial measurement and update label
        self._emit_measurement_data_for_roi(line_roi)

    def _on_line_changed(self, line_roi: pg.LineSegmentROI):
        """Handle changes to a measurement line ROI - lightweight update during drag."""
        if line_roi in self.active_line_rois:
            # Lightweight label update only (no signal emission for performance)
            self._update_line_label_lightweight(line_roi)
            # Show snap indicator if near a snap point (during dragging)
            self._update_snap_indicator(line_roi)

    def _update_line_label_lightweight(self, line_roi: pg.LineSegmentROI):
        """Update line label position and text without emitting signals."""
        if line_roi not in self._line_labels:
            return

        # Get handle positions
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

        # Calculate midpoint
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2

        # Calculate distance
        distance_px = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        distance_nm = None
        if self.calibration and hasattr(self.calibration, 'scale'):
            distance_nm = distance_px * self.calibration.scale

        # Update label with batched update
        label = self._line_labels[line_roi]
        label.update_position_and_text(mid_x, mid_y, self._format_distance_text(distance_px, distance_nm))

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

        # Update the draggable label for this line
        if line_roi in self._line_labels:
            label = self._line_labels[line_roi]
            # Update anchor position to line midpoint
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2
            label.set_anchor_position(mid_x, mid_y)
            # Update label text
            label.set_text(self._format_distance_text(distance_px, distance_nm))

        self.measurement_created.emit(measurement_data)

    def _format_distance_text(self, distance_px: float, distance_nm: Optional[float]) -> str:
        """Format distance for display in label."""
        if distance_nm is not None:
            if distance_nm >= 1000:
                return f"{distance_nm/1000:.2f} μm"
            elif distance_nm >= 1:
                return f"{distance_nm:.2f} nm"
            else:
                return f"{distance_nm:.3f} nm"
        else:
            return f"{distance_px:.1f} px"

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
        """Clear all active (uncommitted) measurement lines and polygons."""
        # Clear lines
        for line_roi in self.active_line_rois:
            if line_roi in self._line_labels:
                label = self._line_labels.pop(line_roi)
                self.plot_item.removeItem(label)
            self.plot_item.removeItem(line_roi)
        self.active_line_rois.clear()

        # Clear polygons
        for polygon_roi in self.active_polygon_rois:
            if polygon_roi in self._polygon_labels:
                label = self._polygon_labels.pop(polygon_roi)
                self.plot_item.removeItem(label)
            self.plot_item.removeItem(polygon_roi)
        self.active_polygon_rois.clear()

    def clear_all(self):
        """Clear all measurements (active and completed)."""
        # Clear all active lines and polygons (and their labels)
        self.clear_active()

        # Clear completed measurements
        for measurement in self.completed_measurements:
            self.plot_item.removeItem(measurement)
        self.completed_measurements.clear()

        # Reset counters
        self.measurement_id_counter = 0
        self.polygon_id_counter = 0
        self.color_index = 0

        self.measurements_cleared.emit()

    def clear_last(self):
        """Remove the last measurement (line or polygon)."""
        # Determine which was added last by comparing IDs
        last_line_id = self.active_line_rois[-1]._measurement_id if self.active_line_rois else -1
        last_poly_id = self.active_polygon_rois[-1]._polygon_id if self.active_polygon_rois else -1

        # Remove the most recent one
        if last_poly_id > last_line_id and self.active_polygon_rois:
            last_roi = self.active_polygon_rois.pop()
            if last_roi in self._polygon_labels:
                label = self._polygon_labels.pop(last_roi)
                self.plot_item.removeItem(label)
            self.plot_item.removeItem(last_roi)
            if self.color_index > 0:
                self.color_index -= 1
        elif self.active_line_rois:
            last_roi = self.active_line_rois.pop()
            if last_roi in self._line_labels:
                label = self._line_labels.pop(last_roi)
                self.plot_item.removeItem(label)
            self.plot_item.removeItem(last_roi)
            if self.color_index > 0:
                self.color_index -= 1
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

        # Update all active measurement labels
        for line_roi in self.active_line_rois:
            self._emit_measurement_data_for_roi(line_roi)

    def set_labels_visible(self, visible: bool):
        """Show or hide all floating labels (distance and area)."""
        self._show_labels = visible
        for label in self._line_labels.values():
            label.set_visible(visible)
        for label in self._polygon_labels.values():
            label.set_visible(visible)

    def toggle_labels(self) -> bool:
        """Toggle label visibility and return new state."""
        self._show_labels = not self._show_labels
        self.set_labels_visible(self._show_labels)
        return self._show_labels

    def are_labels_visible(self) -> bool:
        """Check if labels are currently visible."""
        return self._show_labels

    def reset_all_label_positions(self):
        """Reset all labels to their default positions."""
        for label in self._line_labels.values():
            label.reset_position()
        for label in self._polygon_labels.values():
            label.reset_position()

    def set_label_font_size(self, size: int):
        """Set font size for all labels (and future labels)."""
        self._label_font_size = size
        for label in self._line_labels.values():
            label.set_font_size(size)
        for label in self._polygon_labels.values():
            label.set_font_size(size)

    def get_label_font_size(self) -> int:
        """Get the current label font size."""
        return self._label_font_size

    # ==================== Polygon Area Measurement Methods ====================

    def create_polygon_area(self):
        """Create a new polygon for area measurement."""
        if self.image_item.image is None:
            return

        # Get image dimensions
        img_shape = self.image_item.image.shape
        height, width = img_shape[0], img_shape[1] if len(img_shape) > 1 else img_shape[0]

        # Calculate initial polygon position (pentagon shape centered in image)
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) * 0.2  # 20% of smaller dimension

        # Offset for multiple polygons
        offset = len(self.active_polygon_rois) * 0.05 * min(width, height)
        center_x += offset
        center_y += offset

        # Create initial vertices (pentagon)
        num_vertices = 5
        vertices = []
        for i in range(num_vertices):
            angle = 2 * np.pi * i / num_vertices - np.pi / 2  # Start from top
            x = center_x + radius * np.cos(angle)
            y = center_y + radius * np.sin(angle)
            # Clamp to image bounds
            x = max(10, min(width - 10, x))
            y = max(10, min(height - 10, y))
            vertices.append([x, y])

        # Get color for this polygon
        color = self.get_next_color()
        qt_color = QColor(color)

        # Increment counter
        self.polygon_id_counter += 1
        self.measurement_id_counter += 1  # Use same counter for ordering

        # Create closed PolyLineROI with large handles
        polygon_roi = LargeHandlePolyLineROI(
            vertices,
            closed=True,
            pen=pg.mkPen(color=qt_color, width=2),
            hoverPen=pg.mkPen(color='white', width=3),
            handlePen=pg.mkPen(color=qt_color, width=2),
            handleHoverPen=pg.mkPen(color='white', width=3),
        )

        # Set handle color and store metadata
        polygon_roi.set_handle_color(qt_color)
        polygon_roi._polygon_color = color
        polygon_roi._polygon_id = self.measurement_id_counter

        # Add to plot
        self.plot_item.addItem(polygon_roi)
        polygon_roi.setZValue(900 + len(self.active_polygon_rois))
        self.active_polygon_rois.append(polygon_roi)

        # Create draggable area label
        label = DraggableAreaLabel(color=color)
        label.set_font_size(self._label_font_size)
        self.plot_item.addItem(label)
        label.setZValue(1500 + len(self.active_polygon_rois))
        label.set_visible(self._show_labels)
        self._polygon_labels[polygon_roi] = label

        # Calculate initial centroid and set label position
        centroid = self._calculate_polygon_centroid(vertices)
        label.set_anchor_position(centroid[0], centroid[1])
        label.reset_position()

        # Connect to ROI changes
        # Use lightweight update during drag, full emit on finish
        polygon_roi.sigRegionChanged.connect(lambda: self._on_polygon_changed_lightweight(polygon_roi))
        polygon_roi.sigRegionChangeFinished.connect(lambda: self._on_polygon_change_finished(polygon_roi))

        # Emit initial measurement
        self._emit_polygon_area_data(polygon_roi)

    def _on_polygon_changed_lightweight(self, polygon_roi: pg.PolyLineROI):
        """Lightweight update during polygon drag - only update label, no signal emission."""
        if polygon_roi not in self.active_polygon_rois:
            return

        # Get vertices and calculate area/centroid (fast operations)
        vertices = self._get_polygon_vertices(polygon_roi)
        if len(vertices) < 3:
            return

        area_px = self._calculate_polygon_area(vertices)
        centroid = self._calculate_polygon_centroid(vertices)

        # Get calibrated area if available
        area_nm2 = None
        if self.calibration and hasattr(self.calibration, 'scale'):
            area_nm2 = area_px * (self.calibration.scale ** 2)

        # Update label with batched update (single repaint)
        if polygon_roi in self._polygon_labels:
            label = self._polygon_labels[polygon_roi]
            label.update_position_and_text(
                centroid[0], centroid[1],
                self._format_area_text(area_px, area_nm2)
            )

    def _on_polygon_change_finished(self, polygon_roi: pg.PolyLineROI):
        """Handle when polygon ROI change is finished - emit full data."""
        if polygon_roi in self.active_polygon_rois:
            self._emit_polygon_area_data(polygon_roi)

    def _get_polygon_vertices(self, polygon_roi: pg.PolyLineROI) -> List[Tuple[float, float]]:
        """Get the vertices of a polygon ROI in data coordinates."""
        vertices = []
        handles = polygon_roi.getLocalHandlePositions()
        roi_pos = polygon_roi.pos()

        for _, handle_pos in handles:
            x = roi_pos.x() + handle_pos.x()
            y = roi_pos.y() + handle_pos.y()
            vertices.append((x, y))

        return vertices

    def _calculate_polygon_area(self, vertices: List[Tuple[float, float]]) -> float:
        """Calculate polygon area using the Shoelace formula."""
        n = len(vertices)
        if n < 3:
            return 0.0

        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += vertices[i][0] * vertices[j][1]
            area -= vertices[j][0] * vertices[i][1]

        return abs(area) / 2.0

    def _calculate_polygon_perimeter(self, vertices: List[Tuple[float, float]]) -> float:
        """Calculate polygon perimeter."""
        n = len(vertices)
        if n < 2:
            return 0.0

        perimeter = 0.0
        for i in range(n):
            j = (i + 1) % n
            dx = vertices[j][0] - vertices[i][0]
            dy = vertices[j][1] - vertices[i][1]
            perimeter += np.sqrt(dx**2 + dy**2)

        return perimeter

    def _calculate_polygon_centroid(self, vertices: List[Tuple[float, float]]) -> Tuple[float, float]:
        """Calculate the centroid of a polygon."""
        n = len(vertices)
        if n == 0:
            return (0.0, 0.0)

        cx = sum(v[0] for v in vertices) / n
        cy = sum(v[1] for v in vertices) / n
        return (cx, cy)

    def _emit_polygon_area_data(self, polygon_roi: pg.PolyLineROI):
        """Calculate and emit polygon area data."""
        if polygon_roi is None:
            return

        vertices = self._get_polygon_vertices(polygon_roi)
        if len(vertices) < 3:
            return

        # Calculate area and perimeter in pixels
        area_px = self._calculate_polygon_area(vertices)
        perimeter_px = self._calculate_polygon_perimeter(vertices)
        centroid = self._calculate_polygon_centroid(vertices)

        # Get calibration value if available
        cal_value = None
        area_nm2 = None
        perimeter_nm = None
        if self.calibration and hasattr(self.calibration, 'scale'):
            cal_value = self.calibration.scale
            area_nm2 = area_px * (cal_value ** 2)  # nm² = px² * (nm/px)²
            perimeter_nm = perimeter_px * cal_value

        # Get polygon ID
        polygon_id = f"Polygon_{getattr(polygon_roi, '_polygon_id', 0)}"

        polygon_data = PolygonAreaData(
            vertices=vertices,
            area_px=area_px,
            area_nm2=area_nm2,
            perimeter_px=perimeter_px,
            perimeter_nm=perimeter_nm,
            centroid=centroid,
            measurement_id=polygon_id,
            calibration=cal_value
        )

        # Update the label
        if polygon_roi in self._polygon_labels:
            label = self._polygon_labels[polygon_roi]
            label.set_anchor_position(centroid[0], centroid[1])
            label.set_text(self._format_area_text(area_px, area_nm2))

        self.polygon_area_created.emit(polygon_data)

    def _format_area_text(self, area_px: float, area_nm2: Optional[float]) -> str:
        """Format area for display in label."""
        if area_nm2 is not None:
            if area_nm2 >= 1e6:  # >= 1 μm²
                return f"{area_nm2/1e6:.2f} μm²"
            elif area_nm2 >= 1:
                return f"{area_nm2:.1f} nm²"
            else:
                return f"{area_nm2:.3f} nm²"
        else:
            return f"{area_px:.1f} px²"

    def get_polygon_count(self) -> int:
        """Get the number of active polygons."""
        return len(self.active_polygon_rois)

    def get_total_measurement_count(self) -> int:
        """Get total count of all measurements (lines + polygons)."""
        return len(self.active_line_rois) + len(self.active_polygon_rois) + len(self.completed_measurements)

    # --- Serialization and Restore Methods ---

    def restore_line_measurement(self, start: list, end: list, color: str = None):
        """
        Restore a line measurement from saved data.

        Args:
            start: [x, y] coordinates of start point
            end: [x, y] coordinates of end point
            color: Optional color string (uses next color if not provided)
        """
        if self.image_item.image is None:
            return

        # Get color
        if color is None:
            color = self.get_next_color()
        qt_color = QColor(color)

        # Increment counter
        self.measurement_id_counter += 1

        # Create the line ROI at the saved position
        line_roi = ConstrainedLineSegmentROI(
            [[start[0], start[1]],
             [end[0], end[1]]],
            pen=pg.mkPen(color=qt_color, width=2, style=Qt.SolidLine),
            hoverPen=pg.mkPen(color='white', width=3),
            handlePen=pg.mkPen(color=qt_color, width=8),
            handleHoverPen=pg.mkPen(color='white', width=10),
            movable=False
        )

        # Store metadata
        line_roi._measurement_color = color
        line_roi._measurement_id = self.measurement_id_counter

        # Make handles visible
        handles = line_roi.getHandles()
        for handle in handles:
            handle.radius = 8
            handle.pen = pg.mkPen(qt_color, width=2)
            handle.brush = pg.mkBrush(qt_color)
            handle.setAcceptedMouseButtons(Qt.LeftButton)

        # Prevent body drag
        original_mouse_drag = line_roi.mouseDragEvent
        def no_body_drag(ev, roi=line_roi):
            for handle in roi.getHandles():
                if handle.isMoving:
                    return original_mouse_drag(ev)
            ev.ignore()
        line_roi.mouseDragEvent = no_body_drag

        # Add to plot
        self.plot_item.addItem(line_roi)
        line_roi.setZValue(1000 + len(self.active_line_rois))
        self.active_line_rois.append(line_roi)

        # Create label
        label = DraggableDistanceLabel(color=color)
        label.set_font_size(self._label_font_size)
        self.plot_item.addItem(label)
        label.setZValue(1500 + len(self.active_line_rois))
        label.set_visible(self._show_labels)
        self._line_labels[line_roi] = label

        # Set label position
        mid_x = (start[0] + end[0]) / 2
        mid_y = (start[1] + end[1]) / 2
        label.set_anchor_position(mid_x, mid_y)
        label.reset_position()

        # Connect signals
        line_roi.sigRegionChanged.connect(lambda: self._on_line_changed(line_roi))
        line_roi.sigRegionChangeFinished.connect(lambda: self._on_line_change_finished(line_roi))

        # Update label with measurement
        self._emit_measurement_data_for_roi(line_roi)

    def restore_polygon_measurement(self, vertices: list, color: str = None):
        """
        Restore a polygon measurement from saved data.

        Args:
            vertices: List of [x, y] coordinates for each vertex
            color: Optional color string (uses next color if not provided)
        """
        if self.image_item.image is None or len(vertices) < 3:
            return

        # Get color
        if color is None:
            color = self.get_next_color()
        qt_color = QColor(color)

        # Increment counter
        self.polygon_id_counter += 1

        # Create polygon ROI
        polygon_roi = pg.PolyLineROI(
            vertices,
            closed=True,
            pen=pg.mkPen(color=qt_color, width=2),
            hoverPen=pg.mkPen(color='white', width=3),
            handlePen=pg.mkPen(color=qt_color, width=6),
            handleHoverPen=pg.mkPen(color='white', width=8),
            movable=False
        )

        # Store metadata
        polygon_roi._measurement_color = color
        polygon_roi._measurement_id = self.polygon_id_counter

        # Make handles visible
        handles = polygon_roi.getHandles()
        for handle in handles:
            handle.radius = 6
            handle.pen = pg.mkPen(qt_color, width=2)
            handle.brush = pg.mkBrush(qt_color)

        # Add to plot
        self.plot_item.addItem(polygon_roi)
        polygon_roi.setZValue(900 + len(self.active_polygon_rois))
        self.active_polygon_rois.append(polygon_roi)

        # Create area label
        label = DraggableAreaLabel(color=color)
        self.plot_item.addItem(label)
        label.setZValue(1400 + len(self.active_polygon_rois))
        label.set_visible(self._show_labels)
        self._polygon_labels[polygon_roi] = label

        # Calculate centroid for label position
        cx = sum(v[0] for v in vertices) / len(vertices)
        cy = sum(v[1] for v in vertices) / len(vertices)
        label.set_anchor_position(cx, cy)
        label.reset_position()

        # Connect signals
        polygon_roi.sigRegionChanged.connect(lambda: self._on_polygon_changed_lightweight(polygon_roi))
        polygon_roi.sigRegionChangeFinished.connect(lambda: self._on_polygon_change_finished(polygon_roi))

        # Update label
        self._update_polygon_label(polygon_roi)

    def restore_measurements(self, measurements: list):
        """
        Restore all measurements from saved data.

        Args:
            measurements: List of measurement dictionaries with 'type', 'start'/'end' or 'vertices'
        """
        for m in measurements:
            m_type = m.get('type')
            color = m.get('color')  # May be None

            if m_type == 'line':
                start = m.get('start')
                end = m.get('end')
                if start and end:
                    self.restore_line_measurement(start, end, color)

            elif m_type == 'polygon':
                vertices = m.get('vertices')
                if vertices and len(vertices) >= 3:
                    self.restore_polygon_measurement(vertices, color)
