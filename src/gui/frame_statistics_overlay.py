"""
Frame statistics ROI overlay for display panels.
Manages rectangle ROI for selecting regions to analyze frame statistics.
"""

from PySide6.QtCore import Signal, QObject, Qt
import pyqtgraph as pg
import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class FrameROIData:
    """Data structure for frame statistics ROI."""
    x: float  # X position (left edge)
    y: float  # Y position (bottom edge)
    width: float  # Width in pixels
    height: float  # Height in pixels
    roi_id: str = ""


class FrameStatisticsOverlay(QObject):
    """
    Manages rectangle ROI for frame statistics analysis on image displays.
    """

    # Signals
    roi_created = Signal(FrameROIData)  # Emitted when ROI is created
    roi_updated = Signal(FrameROIData)  # Emitted when ROI is updated
    roi_removed = Signal()  # Emitted when ROI is cleared

    def __init__(self, plot_item: pg.PlotItem, image_item: pg.ImageItem):
        super().__init__()

        self.plot_item = plot_item
        self.image_item = image_item
        self.view_box = plot_item.getViewBox()

        # Rectangle ROI
        self.rect_roi: Optional[pg.RectROI] = None
        self.roi_id_counter = 0

    def create_default_roi(self):
        """Create a default centered rectangle ROI."""
        if self.image_item.image is None:
            return

        # Remove any existing ROI
        self.clear_roi()

        # Get image dimensions
        img = self.image_item.image
        if img is None:
            return

        # Handle different image shapes
        if len(img.shape) == 2:
            height, width = img.shape
        elif len(img.shape) == 3:
            height, width = img.shape[0], img.shape[1]
        else:
            return

        # Create centered ROI at ~50% of image dimensions
        roi_width = width * 0.5
        roi_height = height * 0.5
        roi_x = (width - roi_width) / 2
        roi_y = (height - roi_height) / 2

        # Create RectROI with resize handles
        self.rect_roi = pg.RectROI(
            [roi_x, roi_y],
            [roi_width, roi_height],
            pen=pg.mkPen(color='lime', width=2, style=Qt.SolidLine),
            hoverPen=pg.mkPen(color='cyan', width=3),
            handlePen=pg.mkPen(color='lime', width=2),
            handleHoverPen=pg.mkPen(color='cyan', width=3),
            movable=True,
            resizable=True,
            rotatable=False
        )

        # Customize handles for better visibility
        self.rect_roi.addScaleHandle([0, 0], [1, 1])  # Bottom-left
        self.rect_roi.addScaleHandle([1, 0], [0, 1])  # Bottom-right
        self.rect_roi.addScaleHandle([0, 1], [1, 0])  # Top-left
        self.rect_roi.addScaleHandle([1, 1], [0, 0])  # Top-right
        self.rect_roi.addScaleHandle([0.5, 0], [0.5, 1])  # Bottom-center
        self.rect_roi.addScaleHandle([0.5, 1], [0.5, 0])  # Top-center
        self.rect_roi.addScaleHandle([0, 0.5], [1, 0.5])  # Left-center
        self.rect_roi.addScaleHandle([1, 0.5], [0, 0.5])  # Right-center

        # Add to plot
        self.plot_item.addItem(self.rect_roi)
        self.rect_roi.setZValue(1000)  # On top of image

        # Connect signals
        self.rect_roi.sigRegionChanged.connect(self._on_roi_changed)
        self.rect_roi.sigRegionChangeFinished.connect(self._on_roi_change_finished)

        # Generate ROI ID
        self.roi_id_counter += 1
        roi_id = f"roi_{self.roi_id_counter}"

        # Emit created signal
        roi_data = self._get_roi_data(roi_id)
        if roi_data:
            self.roi_created.emit(roi_data)

    def _on_roi_changed(self):
        """Handle ROI region change (during dragging)."""
        # Optional: emit during drag for live updates
        pass

    def _on_roi_change_finished(self):
        """Handle ROI region change finished."""
        roi_data = self._get_roi_data()
        if roi_data:
            self.roi_updated.emit(roi_data)

    def _get_roi_data(self, roi_id: str = None) -> Optional[FrameROIData]:
        """Get the current ROI data."""
        if self.rect_roi is None:
            return None

        # Get position and size
        pos = self.rect_roi.pos()
        size = self.rect_roi.size()

        # Ensure positive dimensions
        x = pos.x()
        y = pos.y()
        w = abs(size.x())
        h = abs(size.y())

        # Handle negative size (if user dragged in reverse)
        if size.x() < 0:
            x = x + size.x()
        if size.y() < 0:
            y = y + size.y()

        return FrameROIData(
            x=x,
            y=y,
            width=w,
            height=h,
            roi_id=roi_id or f"roi_{self.roi_id_counter}"
        )

    def get_roi_bounds(self) -> Optional[Tuple[int, int, int, int]]:
        """
        Get ROI bounds as integer pixel coordinates.

        Returns:
            Tuple of (x, y, width, height) in pixels, or None if no ROI.
        """
        if self.rect_roi is None:
            return None

        roi_data = self._get_roi_data()
        if roi_data is None:
            return None

        # Clip to image bounds
        img = self.image_item.image
        if img is None:
            return None

        if len(img.shape) == 2:
            img_height, img_width = img.shape
        elif len(img.shape) == 3:
            img_height, img_width = img.shape[0], img.shape[1]
        else:
            return None

        x = max(0, int(roi_data.x))
        y = max(0, int(roi_data.y))
        w = int(roi_data.width)
        h = int(roi_data.height)

        # Clip to image bounds
        if x + w > img_width:
            w = img_width - x
        if y + h > img_height:
            h = img_height - y

        # Ensure positive dimensions
        if w <= 0 or h <= 0:
            return None

        return (x, y, w, h)

    def has_active_roi(self) -> bool:
        """Check if there is an active ROI."""
        return self.rect_roi is not None

    def clear_roi(self):
        """Remove the ROI."""
        if self.rect_roi is not None:
            try:
                self.rect_roi.sigRegionChanged.disconnect(self._on_roi_changed)
                self.rect_roi.sigRegionChangeFinished.disconnect(self._on_roi_change_finished)
            except (TypeError, RuntimeError):
                pass  # Already disconnected

            self.plot_item.removeItem(self.rect_roi)
            self.rect_roi = None
            self.roi_removed.emit()

    def clear_all(self):
        """Clear the ROI (alias for clear_roi)."""
        self.clear_roi()

    def set_roi_visible(self, visible: bool):
        """Set the visibility of the ROI."""
        if self.rect_roi is not None:
            self.rect_roi.setVisible(visible)
