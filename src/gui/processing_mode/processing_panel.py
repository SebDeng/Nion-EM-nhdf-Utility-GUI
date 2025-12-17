"""
Individual panel widget for displaying images in Processing Mode.
Can be used for Original, Live Preview, or Snapshot panels.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QSpinBox, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QDragEnterEvent, QDropEvent
import pyqtgraph as pg
import numpy as np
from typing import Optional, Dict, Any

from src.core.nhdf_reader import NHDFData


class ProcessingPanel(QFrame):
    """
    Panel for displaying and optionally editing images in Processing Mode.
    """

    # Signals
    frame_changed = Signal(int)
    data_updated = Signal(object)  # Emits processed numpy array
    file_dropped = Signal(str)  # Emits file path when file is dropped

    def __init__(self, title: str, read_only: bool = True, compact: bool = False, parent=None):
        super().__init__(parent)

        self.title = title
        self.read_only = read_only
        self.compact = compact

        # Data
        self.nhdf_data: Optional[NHDFData] = None
        self.current_data: Optional[np.ndarray] = None
        self.current_frame = 0
        self.file_path: Optional[str] = None

        # Processing state
        self.current_processing: Optional[Dict[str, Any]] = None
        self.snapshot_id: Optional[str] = None  # For snapshot panels
        self.processed_frames: Optional[np.ndarray] = None  # For multi-frame processed data

        # UI components
        self.image_view: Optional[pg.ImageView] = None

        self._setup_ui()

        # Enable drag and drop for loading files (only for non-snapshot panels)
        if not compact:
            self.setAcceptDrops(True)

    def _setup_ui(self):
        """Set up the panel UI."""
        self.setFrameStyle(QFrame.Box)
        self.setLineWidth(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2 if self.compact else 5)

        # Title bar
        title_widget = QWidget()
        title_widget.setMaximumHeight(25 if self.compact else 30)
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel(self.title)
        if not self.compact:
            font = QFont()
            font.setBold(True)
            title_label.setFont(font)
        title_layout.addWidget(title_label)

        title_layout.addStretch()

        # Add action buttons
        if not self.read_only:
            snapshot_btn = QPushButton("Snapshot")
            snapshot_btn.setMinimumWidth(75)
            snapshot_btn.setMaximumHeight(22)
            snapshot_btn.clicked.connect(self._request_snapshot)
            title_layout.addWidget(snapshot_btn)

        layout.addWidget(title_widget)

        # Image display
        self.image_view = pg.ImageView()
        self.image_view.ui.menuBtn.hide()
        self.image_view.ui.roiBtn.hide()

        # Configure for read-only mode
        if self.read_only:
            self.image_view.view.setMouseEnabled(x=False, y=False)
            self.image_view.ui.histogram.hide()
        else:
            # Allow interaction for preview panel
            self.image_view.ui.histogram.setLevels(0, 255)

        # Hide time axis controls for single images
        self.image_view.ui.roiPlot.hide()

        # Compact mode adjustments
        if self.compact:
            self.image_view.setMinimumHeight(150)
            self.image_view.ui.histogram.setMaximumWidth(50)
        else:
            self.image_view.setMinimumHeight(300)

        layout.addWidget(self.image_view)

        # Frame controls (if multi-frame data)
        self.frame_controls = QWidget()
        self.frame_controls.hide()
        frame_layout = QHBoxLayout(self.frame_controls)
        frame_layout.setContentsMargins(0, 0, 0, 0)

        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.valueChanged.connect(self._on_frame_changed)

        self.frame_spinbox = QSpinBox()
        self.frame_spinbox.setMinimum(0)
        self.frame_spinbox.valueChanged.connect(self._on_frame_changed)

        self.frame_label = QLabel("Frame:")

        frame_layout.addWidget(self.frame_label)
        frame_layout.addWidget(self.frame_spinbox)
        frame_layout.addWidget(self.frame_slider, 1)

        layout.addWidget(self.frame_controls)

        # Processing info (for snapshots)
        if self.compact:
            self.info_label = QLabel()
            self.info_label.setWordWrap(True)
            self.info_label.setMaximumHeight(40)
            self.info_label.setStyleSheet("QLabel { color: #888; font-size: 10px; }")
            layout.addWidget(self.info_label)
            self.info_label.hide()

    def load_data(self, data: NHDFData, file_path: str):
        """Load nhdf data into the panel."""
        self.nhdf_data = data
        self.file_path = file_path
        self.current_frame = 0
        self.current_processing = None
        self.processed_frames = None  # Clear any existing processed frames

        # Handle multi-dimensional data
        if len(data.data.shape) == 3:
            # Show frame controls
            self.frame_controls.show()
            self.frame_slider.setMaximum(data.data.shape[0] - 1)
            self.frame_spinbox.setMaximum(data.data.shape[0] - 1)
            self.frame_label.setText(f"Frame (0-{data.data.shape[0]-1}):")

            # Display first frame
            self.current_data = data.data[0]
            self.image_view.setImage(self.current_data)
        else:
            # Single image
            self.current_data = data.data
            self.image_view.setImage(self.current_data)

        # Auto-scale
        self._auto_scale()

    def load_snapshot(self, snapshot):
        """Load a snapshot into the panel."""
        from .snapshot_manager import ProcessingSnapshot

        if not isinstance(snapshot, ProcessingSnapshot):
            return

        self.snapshot_id = snapshot.id
        self.current_data = snapshot.processed_data
        self.current_processing = snapshot.processing_params

        # Update display
        self.image_view.setImage(self.current_data)
        self._auto_scale()

        # Update title
        self.setTitle(f"Snapshot {snapshot.id}")

        # Show processing info in compact mode
        if self.compact and hasattr(self, 'info_label'):
            info_text = self._format_processing_info(snapshot.processing_params)
            self.info_label.setText(info_text)
            self.info_label.show()

    def update_display(self, data: np.ndarray):
        """Update the displayed image data."""
        self.current_data = data
        self.image_view.setImage(data)

        # Maintain current levels unless auto-scale is needed
        if not self.read_only:
            self._auto_scale()

    def get_current_data(self) -> Optional[np.ndarray]:
        """Get the currently displayed data."""
        return self.current_data

    def set_frame(self, frame: int):
        """Set the current frame (for multi-frame data)."""
        if self.nhdf_data and len(self.nhdf_data.data.shape) == 3:
            self.current_frame = frame
            self.frame_slider.blockSignals(True)
            self.frame_spinbox.blockSignals(True)
            self.frame_slider.setValue(frame)
            self.frame_spinbox.setValue(frame)
            self.frame_slider.blockSignals(False)
            self.frame_spinbox.blockSignals(False)

            # Update display - use processed frames if available
            if self.processed_frames is not None and frame < len(self.processed_frames):
                self.current_data = self.processed_frames[frame]
            else:
                self.current_data = self.nhdf_data.data[frame]
            self.image_view.setImage(self.current_data)

    def setTitle(self, title: str):
        """Update the panel title."""
        self.title = title
        # Update title label if it exists
        title_label = self.findChild(QLabel)
        if title_label:
            title_label.setText(title)

    def _on_frame_changed(self, value: int):
        """Handle frame change."""
        if self.nhdf_data and len(self.nhdf_data.data.shape) == 3:
            self.current_frame = value
            self.frame_slider.blockSignals(True)
            self.frame_spinbox.blockSignals(True)
            self.frame_slider.setValue(value)
            self.frame_spinbox.setValue(value)
            self.frame_slider.blockSignals(False)
            self.frame_spinbox.blockSignals(False)

            # Update display - use processed frames if available
            if self.processed_frames is not None and value < len(self.processed_frames):
                self.current_data = self.processed_frames[value]
            else:
                self.current_data = self.nhdf_data.data[value]
            self.image_view.setImage(self.current_data)

            # Emit signal
            self.frame_changed.emit(value)

    def _auto_scale(self):
        """Auto-scale the image display."""
        if self.current_data is not None:
            # Calculate reasonable levels
            data_min = np.min(self.current_data)
            data_max = np.max(self.current_data)

            # Use percentiles for better auto-scaling
            if data_max > data_min:
                low = np.percentile(self.current_data, 1)
                high = np.percentile(self.current_data, 99)
                self.image_view.setLevels(low, high)

    def _request_snapshot(self):
        """Request snapshot creation (for preview panel)."""
        # This will be connected to the main widget's snapshot creation
        pass

    def _format_processing_info(self, params: Dict[str, Any]) -> str:
        """Format processing parameters for display."""
        if not params:
            return "No processing"

        info_parts = []
        if 'brightness' in params:
            info_parts.append(f"Brightness: {params['brightness']:.1f}")
        if 'contrast' in params:
            info_parts.append(f"Contrast: {params['contrast']:.2f}")
        if 'gamma' in params:
            info_parts.append(f"Gamma: {params['gamma']:.2f}")
        if 'gaussian_sigma' in params:
            info_parts.append(f"Gaussian σ: {params['gaussian_sigma']:.1f}")
        if 'median_size' in params:
            info_parts.append(f"Median: {params['median_size']}")

        return " | ".join(info_parts[:3])  # Limit to 3 items for space

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events."""
        if event.mimeData().hasUrls():
            # Check if any of the URLs are supported files
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith(('.nhdf', '.ndata1', '.dm3', '.dm4')):
                        event.acceptProposedAction()
                        # Visual feedback
                        self.setStyleSheet("""
                            ProcessingPanel {
                                border: 2px solid #4a90d9;
                                background-color: rgba(74, 144, 217, 0.1);
                            }
                        """)
                        return

    def dragLeaveEvent(self, event):
        """Handle drag leave events."""
        # Remove visual feedback but keep the frame style
        self.setStyleSheet("")
        self.setFrameStyle(QFrame.Box)
        self.setLineWidth(1)

    def dropEvent(self, event: QDropEvent):
        """Handle drop events."""
        # Remove visual feedback
        self.setStyleSheet("")
        self.setFrameStyle(QFrame.Box)
        self.setLineWidth(1)

        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if file_path.lower().endswith(('.nhdf', '.ndata1', '.dm3', '.dm4')):
                        self.file_dropped.emit(file_path)
                        event.acceptProposedAction()
                        return