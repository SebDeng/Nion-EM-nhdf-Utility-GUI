"""
Floating memo pad widget for display panels.

Provides draggable sticky-note style text annotations that float over images.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QFrame, QSizeGrip
)
from PySide6.QtCore import Qt, Signal, QPoint, QSize
from PySide6.QtGui import QFont, QColor, QPalette, QMouseEvent

from typing import Optional, Dict, Any
import uuid


class MemoPad(QFrame):
    """
    A floating, draggable memo pad widget.

    Features:
    - Semi-transparent sticky note appearance
    - Draggable by title bar
    - Resizable via corner grip
    - Editable text content
    - Close button
    """

    # Signals
    closed = Signal(str)  # Emits memo_id when closed
    content_changed = Signal(str)  # Emits memo_id when content changes

    # Class constants
    DEFAULT_WIDTH = 200
    DEFAULT_HEIGHT = 150
    MIN_WIDTH = 120
    MIN_HEIGHT = 80
    MAX_MEMOS_PER_PANEL = 2

    # Color schemes for different memo indices
    COLORS = [
        {'bg': 'rgba(255, 255, 150, 200)', 'title_bg': 'rgba(255, 230, 100, 220)', 'border': '#d4c84a'},  # Yellow
        {'bg': 'rgba(150, 220, 255, 200)', 'title_bg': 'rgba(100, 190, 230, 220)', 'border': '#4a9ed4'},  # Blue
    ]

    def __init__(self, memo_id: Optional[str] = None, color_index: int = 0, parent=None):
        super().__init__(parent)

        self.memo_id = memo_id or str(uuid.uuid4())
        self._color_index = color_index % len(self.COLORS)
        self._drag_position: Optional[QPoint] = None
        self._is_dark_theme = True

        self._setup_ui()
        self._apply_style()

        # Set initial size
        self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)

    def _setup_ui(self):
        """Set up the memo pad UI."""
        self.setWindowFlags(Qt.SubWindow)
        self.setFrameStyle(QFrame.Box | QFrame.Raised)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar (draggable area)
        self._title_bar = QWidget()
        self._title_bar.setFixedHeight(24)
        self._title_bar.setCursor(Qt.OpenHandCursor)

        title_layout = QHBoxLayout(self._title_bar)
        title_layout.setContentsMargins(8, 2, 4, 2)
        title_layout.setSpacing(4)

        # Title label
        self._title_label = QLabel("Memo")
        self._title_label.setFont(QFont("sans-serif", 10, QFont.Bold))
        title_layout.addWidget(self._title_label)

        title_layout.addStretch()

        # Close button
        self._close_btn = QPushButton("×")
        self._close_btn.setFixedSize(18, 18)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.clicked.connect(self._on_close)
        title_layout.addWidget(self._close_btn)

        layout.addWidget(self._title_bar)

        # Content area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(4, 4, 4, 4)

        # Text edit
        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText("Enter notes here...")
        self._text_edit.setFont(QFont("sans-serif", 10))
        self._text_edit.textChanged.connect(self._on_text_changed)
        content_layout.addWidget(self._text_edit)

        # Bottom bar with resize grip
        bottom_bar = QWidget()
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(4, 0, 0, 0)
        bottom_layout.setSpacing(0)

        bottom_layout.addStretch()

        # Size grip for resizing
        self._size_grip = QSizeGrip(self)
        self._size_grip.setFixedSize(16, 16)
        bottom_layout.addWidget(self._size_grip)

        content_layout.addWidget(bottom_bar)

        layout.addWidget(content_widget)

        # Install event filter for dragging
        self._title_bar.installEventFilter(self)

    def _apply_style(self):
        """Apply the semi-transparent sticky note style."""
        colors = self.COLORS[self._color_index]

        # Adjust colors for dark theme
        if self._is_dark_theme:
            text_color = '#1a1a1a'
            placeholder_color = '#555555'
        else:
            text_color = '#1a1a1a'
            placeholder_color = '#777777'

        self.setStyleSheet(f"""
            MemoPad {{
                background-color: {colors['bg']};
                border: 2px solid {colors['border']};
                border-radius: 6px;
            }}
        """)

        self._title_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {colors['title_bg']};
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QLabel {{
                color: {text_color};
                background: transparent;
            }}
        """)

        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: none;
                color: {text_color};
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 0, 0, 100);
                color: white;
                border-radius: 9px;
            }}
        """)

        self._text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: transparent;
                border: none;
                color: {text_color};
            }}
            QTextEdit::placeholder {{
                color: {placeholder_color};
            }}
        """)

    def set_theme(self, is_dark: bool):
        """Update theme."""
        self._is_dark_theme = is_dark
        self._apply_style()

    def eventFilter(self, obj, event):
        """Handle dragging via title bar."""
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
        self.closed.emit(self.memo_id)
        self.hide()
        self.deleteLater()

    def _on_text_changed(self):
        """Handle text content change."""
        self.content_changed.emit(self.memo_id)

    # --- Public API ---

    def get_text(self) -> str:
        """Get the memo text content."""
        return self._text_edit.toPlainText()

    def set_text(self, text: str):
        """Set the memo text content."""
        self._text_edit.setPlainText(text)

    def set_title(self, title: str):
        """Set the memo title."""
        self._title_label.setText(title)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize memo to dictionary."""
        return {
            'memo_id': self.memo_id,
            'color_index': self._color_index,
            'text': self.get_text(),
            'title': self._title_label.text(),
            'x': self.x(),
            'y': self.y(),
            'width': self.width(),
            'height': self.height()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], parent=None) -> 'MemoPad':
        """Create memo from dictionary."""
        memo = cls(
            memo_id=data.get('memo_id'),
            color_index=data.get('color_index', 0),
            parent=parent
        )
        memo.set_text(data.get('text', ''))
        memo.set_title(data.get('title', 'Memo'))
        memo.move(data.get('x', 20), data.get('y', 20))
        memo.resize(
            data.get('width', cls.DEFAULT_WIDTH),
            data.get('height', cls.DEFAULT_HEIGHT)
        )
        return memo


class MemoPadManager:
    """
    Manages memo pads for a display panel.

    Handles creation, deletion, and serialization of memo pads.
    """

    def __init__(self, parent_widget: QWidget):
        self._parent = parent_widget
        self._memos: Dict[str, MemoPad] = {}
        self._is_dark_theme = True

    @property
    def memo_count(self) -> int:
        """Get the number of active memos."""
        return len(self._memos)

    @property
    def can_add_memo(self) -> bool:
        """Check if more memos can be added."""
        return self.memo_count < MemoPad.MAX_MEMOS_PER_PANEL

    def create_memo(self, x: int = 20, y: int = 20) -> Optional[MemoPad]:
        """
        Create a new memo pad.

        Returns:
            The created MemoPad, or None if max memos reached.
        """
        if not self.can_add_memo:
            return None

        # Use alternating colors
        color_index = self.memo_count

        memo = MemoPad(color_index=color_index, parent=self._parent)
        memo.set_theme(self._is_dark_theme)
        memo.set_title(f"Memo {self.memo_count + 1}")

        # Position with offset for multiple memos
        offset = self.memo_count * 30
        memo.move(x + offset, y + offset)

        # Connect signals
        memo.closed.connect(self._on_memo_closed)

        self._memos[memo.memo_id] = memo
        memo.show()
        memo.raise_()

        return memo

    def _on_memo_closed(self, memo_id: str):
        """Handle memo closure."""
        if memo_id in self._memos:
            del self._memos[memo_id]

    def remove_memo(self, memo_id: str):
        """Remove a memo by ID."""
        if memo_id in self._memos:
            memo = self._memos[memo_id]
            memo.closed.disconnect(self._on_memo_closed)
            memo.hide()
            memo.deleteLater()
            del self._memos[memo_id]

    def clear_all(self):
        """Remove all memos."""
        for memo_id in list(self._memos.keys()):
            self.remove_memo(memo_id)

    def set_theme(self, is_dark: bool):
        """Update theme for all memos."""
        self._is_dark_theme = is_dark
        for memo in self._memos.values():
            memo.set_theme(is_dark)

    def to_list(self) -> list:
        """Serialize all memos to list of dictionaries."""
        return [memo.to_dict() for memo in self._memos.values()]

    def from_list(self, data: list):
        """Restore memos from list of dictionaries."""
        self.clear_all()
        for memo_data in data[:MemoPad.MAX_MEMOS_PER_PANEL]:
            memo = MemoPad.from_dict(memo_data, parent=self._parent)
            memo.set_theme(self._is_dark_theme)
            memo.closed.connect(self._on_memo_closed)
            self._memos[memo.memo_id] = memo
            memo.show()
