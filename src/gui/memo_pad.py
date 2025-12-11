"""
Floating memo pad widget for display panels.

Provides draggable sticky-note style text annotations that float over images.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QFrame, QSizeGrip
)
from PySide6.QtCore import Qt, Signal, QPoint, QSize
from PySide6.QtGui import QFont, QColor, QPalette, QMouseEvent, QKeySequence, QTextCharFormat, QShortcut

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
    minimized = Signal(str, bool)  # Emits (memo_id, is_minimized) when minimized/expanded

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
        self._is_minimized = False
        self._expanded_height = self.DEFAULT_HEIGHT  # Store height when expanded

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

        # Minimize button
        self._minimize_btn = QPushButton("_")  # Underscore for minimize
        self._minimize_btn.setFixedSize(18, 18)
        self._minimize_btn.setCursor(Qt.PointingHandCursor)
        self._minimize_btn.setToolTip("Minimize")
        self._minimize_btn.clicked.connect(self._on_toggle_minimize)
        title_layout.addWidget(self._minimize_btn)

        # Close button
        self._close_btn = QPushButton("x")  # Simple x for close
        self._close_btn.setFixedSize(18, 18)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.setToolTip("Close")
        self._close_btn.clicked.connect(self._on_close)
        title_layout.addWidget(self._close_btn)

        layout.addWidget(self._title_bar)

        # Content area
        self._content_widget = QWidget()
        self._content_widget.setObjectName("MemoContent")
        content_layout = QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(4, 4, 4, 4)

        # Text edit
        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText("Enter notes here...")
        self._text_edit.setFont(QFont("sans-serif", 10))
        self._text_edit.textChanged.connect(self._on_text_changed)
        content_layout.addWidget(self._text_edit)

        # Set up keyboard shortcuts for formatting
        self._setup_shortcuts()

        # Bottom bar with resize grip
        self._bottom_bar = QWidget()
        self._bottom_bar.setObjectName("MemoBottomBar")
        bottom_layout = QHBoxLayout(self._bottom_bar)
        bottom_layout.setContentsMargins(4, 0, 0, 0)
        bottom_layout.setSpacing(0)

        bottom_layout.addStretch()

        # Size grip for resizing
        self._size_grip = QSizeGrip(self)
        self._size_grip.setFixedSize(16, 16)
        bottom_layout.addWidget(self._size_grip)

        content_layout.addWidget(self._bottom_bar)

        layout.addWidget(self._content_widget)

        # Install event filter for dragging
        self._title_bar.installEventFilter(self)

    def _apply_style(self):
        """Apply the semi-transparent sticky note style."""
        colors = self.COLORS[self._color_index]

        # Text is always dark on the light-colored sticky note
        text_color = '#1a1a1a'
        placeholder_color = '#666666'

        self.setStyleSheet(f"""
            MemoPad {{
                background-color: {colors['bg']};
                border: 2px solid {colors['border']};
                border-radius: 6px;
            }}
            QWidget#MemoContent {{
                background-color: transparent;
            }}
            QWidget#MemoBottomBar {{
                background-color: transparent;
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

        # Minimize button - circular with visible background
        self._minimize_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0, 0, 0, 40);
                border: 1px solid rgba(0, 0, 0, 60);
                border-radius: 9px;
                color: {text_color};
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(100, 100, 100, 150);
                color: white;
            }}
        """)

        # Close button - circular with red hover
        self._close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(0, 0, 0, 40);
                border: 1px solid rgba(0, 0, 0, 60);
                border-radius: 9px;
                color: {text_color};
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 80, 80, 200);
                color: white;
            }}
        """)

        self._text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: transparent;
                border: none;
                color: {text_color};
            }}
        """)
        # Make the viewport transparent too
        self._text_edit.viewport().setStyleSheet("background-color: transparent;")

    def _setup_shortcuts(self):
        """Set up keyboard shortcuts for text formatting."""
        # Bold: Cmd+B (Mac) / Ctrl+B (Windows/Linux)
        bold_shortcut = QShortcut(QKeySequence.StandardKey.Bold, self._text_edit)
        bold_shortcut.activated.connect(self._toggle_bold)

        # Italic: Cmd+I (Mac) / Ctrl+I (Windows/Linux)
        italic_shortcut = QShortcut(QKeySequence.StandardKey.Italic, self._text_edit)
        italic_shortcut.activated.connect(self._toggle_italic)

        # Underline: Cmd+U (Mac) / Ctrl+U (Windows/Linux)
        underline_shortcut = QShortcut(QKeySequence.StandardKey.Underline, self._text_edit)
        underline_shortcut.activated.connect(self._toggle_underline)

    def _toggle_bold(self):
        """Toggle bold formatting on current selection or cursor position."""
        fmt = self._text_edit.currentCharFormat()
        if fmt.fontWeight() == QFont.Bold:
            fmt.setFontWeight(QFont.Normal)
        else:
            fmt.setFontWeight(QFont.Bold)
        self._text_edit.mergeCurrentCharFormat(fmt)

    def _toggle_italic(self):
        """Toggle italic formatting on current selection or cursor position."""
        fmt = self._text_edit.currentCharFormat()
        fmt.setFontItalic(not fmt.fontItalic())
        self._text_edit.mergeCurrentCharFormat(fmt)

    def _toggle_underline(self):
        """Toggle underline formatting on current selection or cursor position."""
        fmt = self._text_edit.currentCharFormat()
        fmt.setFontUnderline(not fmt.fontUnderline())
        self._text_edit.mergeCurrentCharFormat(fmt)

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

    def _on_toggle_minimize(self):
        """Handle minimize button click - toggle between minimized and expanded states."""
        if self._is_minimized:
            self._expand()
        else:
            self._minimize()

    def _minimize(self):
        """Minimize the memo to just show the title bar."""
        if self._is_minimized:
            return

        # Store current height before minimizing
        self._expanded_height = self.height()

        # Hide content area
        self._content_widget.hide()

        # Change button to expand indicator
        self._minimize_btn.setText("+")  # Plus sign for expand
        self._minimize_btn.setToolTip("Expand")

        # Resize to just the title bar height
        self.setFixedHeight(self._title_bar.height())
        self.setMinimumHeight(self._title_bar.height())

        self._is_minimized = True
        self.minimized.emit(self.memo_id, True)

    def _expand(self):
        """Expand the memo to show full content."""
        if not self._is_minimized:
            return

        # Restore minimum height
        self.setMinimumHeight(self.MIN_HEIGHT)
        self.setMaximumHeight(16777215)  # Default max

        # Show content area
        self._content_widget.show()

        # Change button back to minimize indicator
        self._minimize_btn.setText("_")
        self._minimize_btn.setToolTip("Minimize")

        # Restore height
        self.resize(self.width(), self._expanded_height)

        self._is_minimized = False
        self.minimized.emit(self.memo_id, False)

    def is_minimized(self) -> bool:
        """Check if memo is minimized."""
        return self._is_minimized

    def set_minimized(self, minimized: bool):
        """Set minimized state."""
        if minimized:
            self._minimize()
        else:
            self._expand()

    def _on_text_changed(self):
        """Handle text content change."""
        self.content_changed.emit(self.memo_id)

    # --- Public API ---

    def get_text(self) -> str:
        """Get the memo text content (plain text)."""
        return self._text_edit.toPlainText()

    def get_html(self) -> str:
        """Get the memo content as HTML (preserves formatting)."""
        return self._text_edit.toHtml()

    def set_text(self, text: str):
        """Set the memo text content (plain text, no formatting)."""
        self._text_edit.setPlainText(text)

    def set_html(self, html: str):
        """Set the memo content from HTML (preserves formatting)."""
        self._text_edit.setHtml(html)

    def set_title(self, title: str):
        """Set the memo title."""
        self._title_label.setText(title)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize memo to dictionary."""
        # If minimized, store the expanded height instead of current height
        height = self._expanded_height if self._is_minimized else self.height()
        return {
            'memo_id': self.memo_id,
            'color_index': self._color_index,
            'text': self.get_text(),  # Plain text for backward compatibility
            'html': self.get_html(),  # HTML to preserve formatting
            'title': self._title_label.text(),
            'x': self.x(),
            'y': self.y(),
            'width': self.width(),
            'height': height,
            'minimized': self._is_minimized
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], parent=None) -> 'MemoPad':
        """Create memo from dictionary."""
        memo = cls(
            memo_id=data.get('memo_id'),
            color_index=data.get('color_index', 0),
            parent=parent
        )
        # Prefer HTML content if available (preserves formatting), fall back to plain text
        if 'html' in data and data['html']:
            memo.set_html(data['html'])
        else:
            memo.set_text(data.get('text', ''))
        memo.set_title(data.get('title', 'Memo'))
        memo.move(data.get('x', 20), data.get('y', 20))

        # Set size first (expanded size)
        memo._expanded_height = data.get('height', cls.DEFAULT_HEIGHT)
        memo.resize(
            data.get('width', cls.DEFAULT_WIDTH),
            memo._expanded_height
        )

        # Then apply minimized state if needed
        if data.get('minimized', False):
            memo._minimize()
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
