"""
Floating electron dose result label for display panels.

Shows dose calculation results as a draggable overlay on images.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QFont

from typing import Optional, Dict, Any
import uuid


class DoseLabel(QFrame):
    """
    A floating, draggable dose result label.

    Displays electron dose calculation results as a compact overlay.
    Features:
    - Semi-transparent appearance
    - Draggable by title bar
    - Close button
    - Compact display of dose and flux
    """

    # Signals
    closed = Signal(str)  # Emits label_id when closed

    # Class constants
    DEFAULT_WIDTH = 220
    DEFAULT_HEIGHT = 85
    MAX_DOSE_LABELS_PER_PANEL = 2

    def __init__(self, label_id: Optional[str] = None, parent=None):
        super().__init__(parent)

        self.label_id = label_id or str(uuid.uuid4())
        self._drag_position: Optional[QPoint] = None
        self._is_dark_theme = True

        # Store calculation data
        self._dose_data: Dict[str, Any] = {}
        self._use_angstrom = False  # Default to nm²

        self._setup_ui()
        self._apply_style()

        # Set initial size
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)

    def _setup_ui(self):
        """Set up the dose label UI."""
        self.setWindowFlags(Qt.SubWindow)
        self.setFrameStyle(QFrame.Box | QFrame.Raised)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar (draggable area)
        self._title_bar = QWidget()
        self._title_bar.setFixedHeight(20)
        self._title_bar.setCursor(Qt.OpenHandCursor)
        self._title_bar.setObjectName("DoseLabelTitleBar")

        title_layout = QHBoxLayout(self._title_bar)
        title_layout.setContentsMargins(6, 2, 4, 2)
        title_layout.setSpacing(4)

        # Title label
        self._title_label = QLabel("e⁻ Dose")
        self._title_label.setFont(QFont("sans-serif", 9, QFont.Bold))
        title_layout.addWidget(self._title_label)

        title_layout.addStretch()

        # Close button
        self._close_btn = QPushButton("×")
        self._close_btn.setFixedSize(16, 16)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.clicked.connect(self._on_close)
        title_layout.addWidget(self._close_btn)

        layout.addWidget(self._title_bar)

        # Content area
        self._content_widget = QWidget()
        self._content_widget.setObjectName("DoseLabelContent")
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(6, 4, 6, 4)
        content_layout.setSpacing(2)

        # Dose label (blue)
        self._dose_label = QLabel("Dose: --")
        self._dose_label.setFont(QFont("monospace", 10))
        content_layout.addWidget(self._dose_label)

        # Flux label (green)
        self._flux_label = QLabel("Flux: --")
        self._flux_label.setFont(QFont("monospace", 10))
        content_layout.addWidget(self._flux_label)

        # Probe current label (smaller)
        self._probe_label = QLabel("I = -- pA")
        self._probe_label.setFont(QFont("monospace", 9))
        content_layout.addWidget(self._probe_label)

        layout.addWidget(self._content_widget)

        # Install event filter for dragging
        self._title_bar.installEventFilter(self)

    def _apply_style(self):
        """Apply the visual style based on current theme."""
        # Semi-transparent light background with black text
        self.setStyleSheet("""
            DoseLabel {
                background-color: rgba(240, 248, 255, 200);
                border: 1px solid #5599dd;
                border-radius: 5px;
            }
            QWidget#DoseLabelTitleBar {
                background-color: rgba(70, 140, 200, 220);
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QWidget#DoseLabelTitleBar QLabel {
                background-color: transparent;
                color: #ffffff;
            }
            QWidget#DoseLabelContent {
                background-color: transparent;
            }
            QWidget#DoseLabelContent QLabel {
                background-color: transparent;
                color: #000000;
            }
            QPushButton {
                background: transparent;
                border: none;
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                color: #ffff00;
            }
        """)

    def set_theme(self, is_dark: bool):
        """Set the theme (dark or light)."""
        self._is_dark_theme = is_dark
        self._apply_style()

    def eventFilter(self, obj, event):
        """Handle mouse events for dragging."""
        if obj == self._title_bar:
            if event.type() == event.Type.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    self._title_bar.setCursor(Qt.ClosedHandCursor)
                    return True

            elif event.type() == event.Type.MouseMove:
                if self._drag_position is not None:
                    new_pos = event.globalPosition().toPoint() - self._drag_position
                    # Constrain to parent
                    if self.parent():
                        parent_rect = self.parent().rect()
                        new_pos.setX(max(0, min(new_pos.x(), parent_rect.width() - self.width())))
                        new_pos.setY(max(0, min(new_pos.y(), parent_rect.height() - self.height())))
                    self.move(new_pos)
                    return True

            elif event.type() == event.Type.MouseButtonRelease:
                self._drag_position = None
                self._title_bar.setCursor(Qt.OpenHandCursor)
                return True

        return super().eventFilter(obj, event)

    def _on_close(self):
        """Handle close button click."""
        self.closed.emit(self.label_id)
        self.hide()
        self.deleteLater()

    # --- Public API ---

    def set_dose_data(self, data: Dict[str, Any], use_angstrom: bool = False):
        """
        Set the dose calculation data to display.

        Args:
            data: Dictionary from NHDFData.calculate_electron_dose()
            use_angstrom: If True, display in Ų units; otherwise nm²
        """
        self._dose_data = data
        self._use_angstrom = use_angstrom
        self._update_display()

    def _update_display(self):
        """Update the display labels with current data."""
        if not self._dose_data:
            self._dose_label.setText("Dose: --")
            self._flux_label.setText("Flux: --")
            self._probe_label.setText("I = -- pA")
            return

        if self._use_angstrom:
            dose = self._dose_data.get('dose_e_per_A2', 0)
            flux = self._dose_data.get('flux_e_per_A2_s', 0)
            unit = "Ų"
        else:
            dose = self._dose_data.get('dose_e_per_nm2', 0)
            flux = self._dose_data.get('flux_e_per_nm2_s', 0)
            unit = "nm²"

        probe_current = self._dose_data.get('probe_current_pA', 0)

        # Format dose
        if dose >= 1e6:
            dose_str = f"{dose:.2e}"
        else:
            dose_str = f"{dose:.1f}"
        self._dose_label.setText(f"Dose: {dose_str} e⁻/{unit}")

        # Format flux
        self._flux_label.setText(f"Flux: {flux:.2e} e⁻/{unit}/s")

        # Probe current
        self._probe_label.setText(f"I = {probe_current:.1f} pA")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize dose label to dictionary."""
        return {
            'label_id': self.label_id,
            'dose_data': self._dose_data,
            'use_angstrom': self._use_angstrom,
            'x': self.x(),
            'y': self.y()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], parent=None) -> 'DoseLabel':
        """Create dose label from dictionary."""
        label = cls(
            label_id=data.get('label_id'),
            parent=parent
        )
        label.set_dose_data(
            data.get('dose_data', {}),
            data.get('use_angstrom', False)
        )
        label.move(data.get('x', 20), data.get('y', 20))
        return label


class DoseLabelManager:
    """
    Manages dose labels for a display panel.

    Handles creation, deletion, and serialization of dose labels.
    """

    def __init__(self, parent_widget: QWidget):
        self._parent = parent_widget
        self._labels: Dict[str, DoseLabel] = {}
        self._is_dark_theme = True

    @property
    def label_count(self) -> int:
        """Get the number of active dose labels."""
        return len(self._labels)

    @property
    def can_add_label(self) -> bool:
        """Check if more dose labels can be added."""
        return self.label_count < DoseLabel.MAX_DOSE_LABELS_PER_PANEL

    def create_label(self, dose_data: Dict[str, Any], use_angstrom: bool = False,
                     x: int = 20, y: int = 20) -> Optional[DoseLabel]:
        """
        Create a new dose label.

        Args:
            dose_data: Dictionary from NHDFData.calculate_electron_dose()
            use_angstrom: If True, display in Ų units
            x, y: Initial position

        Returns:
            The created DoseLabel, or None if max reached
        """
        if not self.can_add_label:
            return None

        # Offset position for multiple labels
        offset = self.label_count * 30
        label = DoseLabel(parent=self._parent)
        label.set_dose_data(dose_data, use_angstrom)
        label.set_theme(self._is_dark_theme)
        label.move(x + offset, y + offset)
        label.show()

        # Connect close signal
        label.closed.connect(self._on_label_closed)

        self._labels[label.label_id] = label
        return label

    def _on_label_closed(self, label_id: str):
        """Handle label close."""
        if label_id in self._labels:
            del self._labels[label_id]

    def clear_all(self):
        """Remove all dose labels."""
        for label in list(self._labels.values()):
            label.hide()
            label.deleteLater()
        self._labels.clear()

    def set_theme(self, is_dark: bool):
        """Set theme for all dose labels."""
        self._is_dark_theme = is_dark
        for label in self._labels.values():
            label.set_theme(is_dark)

    def to_list(self) -> list:
        """Serialize all dose labels to list."""
        return [label.to_dict() for label in self._labels.values()]

    def from_list(self, data_list: list):
        """Restore dose labels from list."""
        self.clear_all()
        for item in data_list:
            label = DoseLabel.from_dict(item, self._parent)
            label.set_theme(self._is_dark_theme)
            label.closed.connect(self._on_label_closed)
            label.show()
            self._labels[label.label_id] = label
