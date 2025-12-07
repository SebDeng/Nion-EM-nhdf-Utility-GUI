"""
Line profile overlay for display panels.
"""

from PySide6.QtCore import Signal, QObject, QPointF
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

        # Drawing state
        self.is_drawing = False
        self.start_pos: Optional[QPointF] = None
        self.start_marker = None

        # Tool state
        self.tool_active = False

    def set_tool_active(self, active: bool):
        """Enable or disable the line profile tool."""
        self.tool_active = active

        if active:
            self._connect_events()
        else:
            self._disconnect_events()
            self.cancel_drawing()

    def _connect_events(self):
        """Connect mouse events for drawing."""
        # Connect to the ViewBox mouse press events directly
        self.view_box.mouseClickEvent = self._mouse_click_event

    def _disconnect_events(self):
        """Disconnect mouse events."""
        # Restore default mouse behavior
        self.view_box.mouseClickEvent = pg.ViewBox.mouseClickEvent

    def _mouse_click_event(self, event):
        """Handle mouse click events in the ViewBox."""
        if not self.tool_active or self.image_item.image is None:
            # Call the parent implementation if tool not active
            pg.ViewBox.mouseClickEvent(self.view_box, event)
            return

        # Only handle left clicks
        if event.button() != 1:  # Not left button
            pg.ViewBox.mouseClickEvent(self.view_box, event)
            return

        # Get position in view coordinates
        pos = self.view_box.mapSceneToView(event.scenePos())

        if not self.is_drawing:
            # Start drawing a new line
            self.start_drawing(pos)
        else:
            # Complete the line
            self.complete_drawing(pos)

        # Accept the event to prevent further processing
        event.accept()

    def start_drawing(self, pos: QPointF):
        """Start drawing a new line profile."""
        self.is_drawing = True
        self.start_pos = pos

        # Remove any existing line
        if self.line_roi is not None:
            self.plot_item.removeItem(self.line_roi)
            self.line_roi = None

        # Add a temporary marker to show where the line starts
        self.start_marker = pg.ScatterPlotItem(
            pos=[pos],
            size=10,
            pen=pg.mkPen('yellow', width=2),
            brush=pg.mkBrush('yellow')
        )
        self.plot_item.addItem(self.start_marker)

    def complete_drawing(self, end_pos: QPointF):
        """Complete drawing and create the line profile."""
        if not self.is_drawing or self.start_pos is None:
            return

        # Remove the temporary start marker
        if self.start_marker is not None:
            self.plot_item.removeItem(self.start_marker)
            self.start_marker = None

        # Create LineSegmentROI
        self.line_roi = pg.LineSegmentROI(
            [[self.start_pos.x(), self.start_pos.y()],
             [end_pos.x(), end_pos.y()]],
            pen=pg.mkPen(color='yellow', width=2),
            hoverPen=pg.mkPen(color='cyan', width=2),
            handlePen=pg.mkPen(color='yellow', width=8),
            handleHoverPen=pg.mkPen(color='cyan', width=8)
        )

        # Add to plot
        self.plot_item.addItem(self.line_roi)

        # Connect to ROI changes
        self.line_roi.sigRegionChanged.connect(self._on_line_changed)

        # Extract and emit profile data
        self._extract_profile()

        # Reset drawing state
        self.is_drawing = False
        self.start_pos = None

    def cancel_drawing(self):
        """Cancel current drawing operation."""
        self.is_drawing = False
        self.start_pos = None

        # Remove the temporary start marker if it exists
        if self.start_marker is not None:
            self.plot_item.removeItem(self.start_marker)
            self.start_marker = None

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