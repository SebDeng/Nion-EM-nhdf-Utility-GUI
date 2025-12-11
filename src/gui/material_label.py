"""
Floating material atom count label for display panels.

Shows atom count calculation results as a draggable overlay on images.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QFont

from typing import Optional, Dict, Any
import uuid


class MaterialLabel(QFrame):
    """
    A floating, draggable material atom count label.

    Displays atom count calculation results as a compact overlay.
    Features:
    - Semi-transparent appearance
    - Draggable by title bar
    - Close button
    - Compact display of material and atom counts
    """

    # Signals
    closed = Signal(str)  # Emits label_id when closed

    # Class constants
    DEFAULT_WIDTH = 200
    DEFAULT_HEIGHT = 100
    MAX_MATERIAL_LABELS_PER_PANEL = 2

    def __init__(self, label_id: Optional[str] = None, parent=None):
        super().__init__(parent)

        self.label_id = label_id or str(uuid.uuid4())
        self._drag_position: Optional[QPoint] = None
        self._is_dark_theme = True

        # Store calculation data
        self._material_data: Dict[str, Any] = {}

        self._setup_ui()
        self._apply_style()

        # Set initial size
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)

    def _setup_ui(self):
        """Set up the material label UI."""
        self.setWindowFlags(Qt.SubWindow)
        self.setFrameStyle(QFrame.Box | QFrame.Raised)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar (draggable area)
        self._title_bar = QWidget()
        self._title_bar.setFixedHeight(20)
        self._title_bar.setCursor(Qt.OpenHandCursor)
        self._title_bar.setObjectName("MaterialLabelTitleBar")

        title_layout = QHBoxLayout(self._title_bar)
        title_layout.setContentsMargins(6, 2, 4, 2)
        title_layout.setSpacing(4)

        # Title label
        self._title_label = QLabel("Atoms")
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
        self._content_widget.setObjectName("MaterialLabelContent")
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(6, 4, 6, 4)
        content_layout.setSpacing(2)

        # Material label
        self._material_label = QLabel("Material: --")
        self._material_label.setFont(QFont("monospace", 9))
        content_layout.addWidget(self._material_label)

        # Area label
        self._area_label = QLabel("Area: --")
        self._area_label.setFont(QFont("monospace", 9))
        content_layout.addWidget(self._area_label)

        # Atom count labels (will show primary element)
        self._atoms_label = QLabel("Atoms: --")
        self._atoms_label.setFont(QFont("monospace", 10))
        content_layout.addWidget(self._atoms_label)

        # Total atoms label
        self._total_label = QLabel("Total: --")
        self._total_label.setFont(QFont("monospace", 10))
        content_layout.addWidget(self._total_label)

        layout.addWidget(self._content_widget)

        # Install event filter for dragging
        self._title_bar.installEventFilter(self)

    def _apply_style(self):
        """Apply the visual style based on current theme."""
        # Green-tinted semi-transparent background
        self.setStyleSheet("""
            MaterialLabel {
                background-color: rgba(200, 255, 220, 200);
                border: 1px solid #55aa77;
                border-radius: 5px;
            }
            QWidget#MaterialLabelTitleBar {
                background-color: rgba(60, 160, 100, 220);
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QWidget#MaterialLabelTitleBar QLabel {
                background-color: transparent;
                color: #ffffff;
            }
            QWidget#MaterialLabelContent {
                background-color: transparent;
            }
            QWidget#MaterialLabelContent QLabel {
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

    def set_material_data(self, data: Dict[str, Any]):
        """
        Set the material calculation data to display.

        Args:
            data: Dictionary from calculate_atoms_in_area()
        """
        self._material_data = data
        self._update_display()

    def _update_display(self):
        """Update the display labels with current data."""
        if not self._material_data:
            self._material_label.setText("Material: --")
            self._area_label.setText("Area: --")
            self._atoms_label.setText("Atoms: --")
            self._total_label.setText("Total: --")
            return

        material = self._material_data.get('material', '--')
        area_nm2 = self._material_data.get('area_nm2', 0)
        atoms = self._material_data.get('atoms', {})
        total = self._material_data.get('total_atoms', 0)

        # Update title with material name
        self._title_label.setText(material)

        # Material name
        self._material_label.setText(f"{material}")

        # Format area
        if area_nm2 >= 1e6:
            self._area_label.setText(f"Area: {area_nm2:.2e} nm²")
        else:
            self._area_label.setText(f"Area: {area_nm2:.1f} nm²")

        # Show atom counts (format nicely)
        atom_strs = []
        for element, count in atoms.items():
            atom_strs.append(f"{element}: {count:.2e}")
        self._atoms_label.setText(" | ".join(atom_strs))

        # Total atoms
        self._total_label.setText(f"Total: {total:.2e}")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize material label to dictionary."""
        return {
            'label_id': self.label_id,
            'material_data': self._material_data,
            'x': self.x(),
            'y': self.y()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], parent=None) -> 'MaterialLabel':
        """Create material label from dictionary."""
        label = cls(
            label_id=data.get('label_id'),
            parent=parent
        )
        label.set_material_data(data.get('material_data', {}))
        label.move(data.get('x', 20), data.get('y', 20))
        return label


class MaterialLabelManager:
    """
    Manages material labels for a display panel.

    Handles creation, deletion, and serialization of material labels.
    """

    def __init__(self, parent_widget: QWidget):
        self._parent = parent_widget
        self._labels: Dict[str, MaterialLabel] = {}
        self._is_dark_theme = True

    @property
    def label_count(self) -> int:
        """Get the number of active material labels."""
        return len(self._labels)

    @property
    def can_add_label(self) -> bool:
        """Check if more material labels can be added."""
        return self.label_count < MaterialLabel.MAX_MATERIAL_LABELS_PER_PANEL

    def create_label(self, material_data: Dict[str, Any],
                     x: int = 20, y: int = 20) -> Optional[MaterialLabel]:
        """
        Create a new material label.

        Args:
            material_data: Dictionary from calculate_atoms_in_area()
            x, y: Initial position

        Returns:
            The created MaterialLabel, or None if max reached
        """
        if not self.can_add_label:
            return None

        # Offset position for multiple labels
        offset = self.label_count * 30
        label = MaterialLabel(parent=self._parent)
        label.set_material_data(material_data)
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
        """Remove all material labels."""
        for label in list(self._labels.values()):
            label.hide()
            label.deleteLater()
        self._labels.clear()

    def set_theme(self, is_dark: bool):
        """Set theme for all material labels."""
        self._is_dark_theme = is_dark
        for label in self._labels.values():
            label.set_theme(is_dark)

    def to_list(self) -> list:
        """Serialize all material labels to list."""
        return [label.to_dict() for label in self._labels.values()]

    def from_list(self, data_list: list):
        """Restore material labels from list."""
        self.clear_all()
        for item in data_list:
            label = MaterialLabel.from_dict(item, self._parent)
            label.set_theme(self._is_dark_theme)
            label.closed.connect(self._on_label_closed)
            label.show()
            self._labels[label.label_id] = label
