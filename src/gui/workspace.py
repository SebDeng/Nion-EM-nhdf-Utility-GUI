"""
Workspace manager for free-tiling window layout.
Inspired by Nion Swift's workspace implementation, adapted for PySide6/Qt.
"""

from PySide6.QtWidgets import (
    QWidget, QSplitter, QVBoxLayout, QHBoxLayout, QMenu,
    QLabel, QPushButton, QTabWidget, QToolButton
)
from PySide6.QtCore import Qt, Signal, QSettings, QMimeData, QUrl, QEvent
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QDragMoveEvent

import json
import uuid
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass

# Supported EM file extensions for drag-drop
SUPPORTED_EM_EXTENSIONS = ('.nhdf', '.dm3', '.dm4')


def is_supported_em_file(file_path: str) -> bool:
    """Check if file path is a supported EM file format."""
    return file_path.lower().endswith(SUPPORTED_EM_EXTENSIONS)


@dataclass
class WorkspaceLayout:
    """Represents a workspace layout configuration."""
    name: str
    layout: Dict[str, Any]
    workspace_id: str
    uuid: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkspaceLayout':
        return cls(
            name=data.get('name', 'Workspace'),
            layout=data.get('layout', {}),
            workspace_id=data.get('workspace_id', str(uuid.uuid4())),
            uuid=data.get('uuid', str(uuid.uuid4()))
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'layout': self.layout,
            'workspace_id': self.workspace_id,
            'uuid': self.uuid
        }


class WorkspacePanel(QWidget):
    """
    A panel that can display content (like an image viewer).
    This is the basic unit that can be split/tiled.
    """

    # Signals
    close_requested = Signal(object)  # Emits self when close is requested
    split_requested = Signal(object, str)  # Emits (self, direction) when split is requested
    content_changed = Signal(object)  # Emits self when content changes
    file_dropped = Signal(object, str)  # Emits (self, file_path) when file is dropped

    def __init__(self, panel_id: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.panel_id = panel_id or str(uuid.uuid4())
        self.content_widget: Optional[QWidget] = None
        self._selected = False
        self._is_dark_theme = True  # Default to dark theme

        # Enable drag and drop
        self.setAcceptDrops(True)

        self._setup_ui()

    def _setup_ui(self):
        """Set up the panel UI with a header bar and content area."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        self.header = QWidget()
        self.header.setMaximumHeight(30)
        self.header.setStyleSheet("""
            QWidget {
                background-color: #2b2b2b;
                border-bottom: 1px solid #3c3c3c;
            }
        """)

        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(4, 2, 4, 2)

        # Title label
        self.title_label = QLabel("Empty Panel")
        self.title_label.setStyleSheet("color: #cccccc;")
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        # Split buttons
        split_h_btn = QToolButton()
        split_h_btn.setText("⊟")  # Horizontal split icon
        split_h_btn.setToolTip("Split Horizontally")
        split_h_btn.clicked.connect(lambda: self.split_requested.emit(self, "horizontal"))
        header_layout.addWidget(split_h_btn)

        split_v_btn = QToolButton()
        split_v_btn.setText("⊞")  # Vertical split icon
        split_v_btn.setToolTip("Split Vertically")
        split_v_btn.clicked.connect(lambda: self.split_requested.emit(self, "vertical"))
        header_layout.addWidget(split_v_btn)

        # Close button
        close_btn = QToolButton()
        close_btn.setText("✕")
        close_btn.setToolTip("Close Panel")
        close_btn.clicked.connect(lambda: self.close_requested.emit(self))
        header_layout.addWidget(close_btn)

        layout.addWidget(self.header)

        # Content area
        self.content_area = QWidget()
        self.content_area.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                border: 1px solid #3c3c3c;
            }
        """)
        # Install event filter to catch clicks on content area
        self.content_area.installEventFilter(self)
        layout.addWidget(self.content_area, stretch=1)

    def set_content(self, widget: QWidget):
        """Set the content widget for this panel."""
        if self.content_widget:
            self.content_widget.setParent(None)

        self.content_widget = widget

        # Clear existing layout
        if self.content_area.layout():
            old_layout = self.content_area.layout()
            while old_layout.count():
                child = old_layout.takeAt(0)
                if child.widget():
                    child.widget().setParent(None)
            old_layout.setParent(None)

        # Add new content
        content_layout = QVBoxLayout(self.content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(widget)

        self.content_changed.emit(self)

    def set_title(self, title: str):
        """Set the panel title."""
        self.title_label.setText(title)

    def set_theme(self, is_dark: bool):
        """Update panel theme."""
        self._is_dark_theme = is_dark  # Store theme state

        if is_dark:
            # Dark theme
            self.header.setStyleSheet("""
                QWidget {
                    background-color: #2b2b2b;
                    border-bottom: 1px solid #3c3c3c;
                }
            """)
            self.title_label.setStyleSheet("color: #cccccc;")
            # Update content area based on selection state
            if self._selected:
                self.content_area.setStyleSheet("""
                    QWidget {
                        background-color: #1e1e1e;
                        border: 2px solid #0d7377;
                    }
                """)
            else:
                self.content_area.setStyleSheet("""
                    QWidget {
                        background-color: #1e1e1e;
                        border: 1px solid #3c3c3c;
                    }
                """)
        else:
            # Light theme
            self.header.setStyleSheet("""
                QWidget {
                    background-color: #e0e0e0;
                    border-bottom: 1px solid #b4b4b4;
                }
            """)
            self.title_label.setStyleSheet("color: #333333;")
            # Update content area based on selection state
            if self._selected:
                self.content_area.setStyleSheet("""
                    QWidget {
                        background-color: #ffffff;
                        border: 2px solid #0d7377;
                    }
                """)
            else:
                self.content_area.setStyleSheet("""
                    QWidget {
                        background-color: #ffffff;
                        border: 1px solid #b4b4b4;
                    }
                """)

        # Update pyqtgraph widgets if they exist in content
        if self.content_widget:
            # Import here to avoid circular dependencies
            try:
                import pyqtgraph as pg
                from pyqtgraph import ImageView

                # Configure pyqtgraph colors
                if is_dark:
                    pg.setConfigOption('background', '#1e1e1e')
                    pg.setConfigOption('foreground', '#d4d4d4')
                else:
                    pg.setConfigOption('background', 'w')
                    pg.setConfigOption('foreground', 'k')

                # Find and update any ImageView widgets
                self._update_child_image_views(self.content_widget, is_dark)
            except ImportError:
                pass

    def _update_child_image_views(self, widget, is_dark: bool):
        """Recursively update ImageView widgets."""
        from pyqtgraph import ImageView

        if isinstance(widget, ImageView):
            # Update the ImageView's background
            if is_dark:
                widget.setBackgroundColor('#1e1e1e')
            else:
                widget.setBackgroundColor('#ffffff')

        # Recursively check children
        for child in widget.findChildren(QWidget):
            self._update_child_image_views(child, is_dark)

    def set_selected(self, selected: bool):
        """Mark this panel as selected/active."""
        self._selected = selected
        # Use stored theme state, default to dark if not set
        is_dark = getattr(self, '_is_dark_theme', True)

        if selected:
            if is_dark:
                self.content_area.setStyleSheet("""
                    QWidget {
                        background-color: #1e1e1e;
                        border: 2px solid #0d7377;
                    }
                """)
            else:
                self.content_area.setStyleSheet("""
                    QWidget {
                        background-color: #ffffff;
                        border: 2px solid #0d7377;
                    }
                """)
        else:
            if is_dark:
                self.content_area.setStyleSheet("""
                    QWidget {
                        background-color: #1e1e1e;
                        border: 1px solid #3c3c3c;
                    }
                """)
            else:
                self.content_area.setStyleSheet("""
                    QWidget {
                        background-color: #ffffff;
                        border: 1px solid #b4b4b4;
                    }
                """)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize panel to dictionary."""
        return {
            'type': 'panel',
            'panel_id': self.panel_id,
            'title': self.title_label.text(),
            'selected': self._selected
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkspacePanel':
        """Create panel from dictionary."""
        panel = cls(panel_id=data.get('panel_id'))
        panel.set_title(data.get('title', 'Empty Panel'))
        panel.set_selected(data.get('selected', False))
        return panel

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events."""
        mime_data = event.mimeData()
        is_dark = getattr(self, '_is_dark_theme', True)

        # Check if the drag contains files
        if mime_data.hasUrls():
            urls = mime_data.urls()
            # Check if any of the files are .nhdf files
            for url in urls:
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if is_supported_em_file(file_path):
                        event.acceptProposedAction()
                        # Visual feedback - highlight the panel
                        if is_dark:
                            self.content_area.setStyleSheet("""
                                QWidget {
                                    background-color: rgba(13, 115, 119, 0.15);
                                    border: 2px solid #0d7377;
                                }
                            """)
                        else:
                            self.content_area.setStyleSheet("""
                                QWidget {
                                    background-color: rgba(42, 130, 218, 0.1);
                                    border: 2px solid #2a82da;
                                }
                            """)
                        return

        # Also accept internal file paths (from file browser)
        if mime_data.hasText():
            text = mime_data.text()
            if is_supported_em_file(text):
                event.acceptProposedAction()
                if is_dark:
                    self.content_area.setStyleSheet("""
                        QWidget {
                            background-color: rgba(13, 115, 119, 0.15);
                            border: 2px solid #0d7377;
                        }
                    """)
                else:
                    self.content_area.setStyleSheet("""
                        QWidget {
                            background-color: rgba(42, 130, 218, 0.1);
                            border: 2px solid #2a82da;
                        }
                    """)
                return

        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        """Handle drag move events."""
        # Keep accepting while moving over the panel
        mime_data = event.mimeData()

        if mime_data.hasUrls():
            urls = mime_data.urls()
            for url in urls:
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if is_supported_em_file(file_path):
                        event.acceptProposedAction()
                        return

        if mime_data.hasText():
            text = mime_data.text()
            if is_supported_em_file(text):
                event.acceptProposedAction()
                return

        event.ignore()

    def dragLeaveEvent(self, event):
        """Handle drag leave events."""
        # Reset visual feedback
        is_dark = getattr(self, '_is_dark_theme', True)

        if self._selected:
            if is_dark:
                self.content_area.setStyleSheet("""
                    QWidget {
                        background-color: #1e1e1e;
                        border: 2px solid #0d7377;
                    }
                """)
            else:
                self.content_area.setStyleSheet("""
                    QWidget {
                        background-color: #ffffff;
                        border: 2px solid #0d7377;
                    }
                """)
        else:
            if is_dark:
                self.content_area.setStyleSheet("""
                    QWidget {
                        background-color: #1e1e1e;
                        border: 1px solid #3c3c3c;
                    }
                """)
            else:
                self.content_area.setStyleSheet("""
                    QWidget {
                        background-color: #ffffff;
                        border: 1px solid #b4b4b4;
                    }
                """)

    def dropEvent(self, event: QDropEvent):
        """Handle drop events."""
        mime_data = event.mimeData()
        is_dark = getattr(self, '_is_dark_theme', True)

        # Handle file URLs
        if mime_data.hasUrls():
            urls = mime_data.urls()
            for url in urls:
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if is_supported_em_file(file_path):
                        event.acceptProposedAction()
                        # Reset visual feedback
                        if self._selected:
                            if is_dark:
                                self.content_area.setStyleSheet("""
                                    QWidget {
                                        background-color: #1e1e1e;
                                        border: 2px solid #0d7377;
                                    }
                                """)
                            else:
                                self.content_area.setStyleSheet("""
                                    QWidget {
                                        background-color: #ffffff;
                                        border: 2px solid #0d7377;
                                    }
                                """)
                        else:
                            if is_dark:
                                self.content_area.setStyleSheet("""
                                    QWidget {
                                        background-color: #1e1e1e;
                                        border: 1px solid #3c3c3c;
                                    }
                                """)
                            else:
                                self.content_area.setStyleSheet("""
                                    QWidget {
                                        background-color: #ffffff;
                                        border: 1px solid #b4b4b4;
                                    }
                                """)
                        # Emit signal with file path
                        self.file_dropped.emit(self, file_path)
                        return

        # Handle text (file paths from file browser)
        if mime_data.hasText():
            file_path = mime_data.text()
            if is_supported_em_file(file_path):
                event.acceptProposedAction()
                # Reset visual feedback
                if self._selected:
                    if is_dark:
                        self.content_area.setStyleSheet("""
                            QWidget {
                                background-color: #1e1e1e;
                                border: 2px solid #0d7377;
                            }
                        """)
                    else:
                        self.content_area.setStyleSheet("""
                            QWidget {
                                background-color: #ffffff;
                                border: 2px solid #0d7377;
                            }
                        """)
                else:
                    if is_dark:
                        self.content_area.setStyleSheet("""
                            QWidget {
                                background-color: #1e1e1e;
                                border: 1px solid #3c3c3c;
                            }
                        """)
                    else:
                        self.content_area.setStyleSheet("""
                            QWidget {
                                background-color: #ffffff;
                                border: 1px solid #b4b4b4;
                            }
                        """)
                # Emit signal with file path
                self.file_dropped.emit(self, file_path)
                return

        event.ignore()

    def eventFilter(self, obj, event):
        """Event filter to catch clicks on content area."""
        if obj == self.content_area and event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                # Trigger panel selection
                parent = self.parent()
                while parent and not isinstance(parent, WorkspaceWidget):
                    parent = parent.parent()

                if parent and isinstance(parent, WorkspaceWidget):
                    parent._select_panel(self)
                    parent.panel_selected.emit(self)
                return True

        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        """Handle mouse press to select this panel."""
        # Request selection when clicked
        if event.button() == Qt.LeftButton:
            # Get the workspace widget (parent tree)
            parent = self.parent()
            while parent and not isinstance(parent, WorkspaceWidget):
                parent = parent.parent()

            if parent and isinstance(parent, WorkspaceWidget):
                parent._select_panel(self)
                # Emit panel_selected signal so main window can update
                parent.panel_selected.emit(self)

        # Call base implementation
        super().mousePressEvent(event)


class WorkspaceWidget(QWidget):
    """
    The main workspace widget that manages the free-tiling layout.
    Uses QSplitter for splitting functionality.
    """

    # Signals
    panel_added = Signal(WorkspacePanel)
    panel_removed = Signal(WorkspacePanel)
    panel_selected = Signal(WorkspacePanel)
    layout_changed = Signal()
    file_dropped_on_panel = Signal(WorkspacePanel, str)  # Emits (panel, file_path)

    def __init__(self, parent=None, panel_factory=None):
        super().__init__(parent)
        self.panels: List[WorkspacePanel] = []
        self.selected_panel: Optional[WorkspacePanel] = None
        self.root_splitter: Optional[QSplitter] = None
        self._is_dark_theme = True  # Store current theme state
        # Panel factory allows customization of what type of panel is created
        # Default creates WorkspacePanel, but can be set to create WorkspaceDisplayPanel
        self._panel_factory = panel_factory or (lambda: WorkspacePanel())

        self._setup_ui()
        self._create_initial_panel()

    def set_panel_factory(self, factory):
        """Set a custom panel factory function.

        Args:
            factory: A callable that returns a new panel instance
        """
        self._panel_factory = factory

    def _create_panel(self) -> WorkspacePanel:
        """Create a new panel using the panel factory."""
        panel = self._panel_factory()
        panel.close_requested.connect(self._handle_panel_close)
        panel.split_requested.connect(self._handle_panel_split)
        panel.file_dropped.connect(self._handle_file_dropped)
        panel.set_theme(self._is_dark_theme)
        return panel

    def _setup_ui(self):
        """Set up the main workspace UI."""
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

    def _create_initial_panel(self):
        """Create the initial empty panel."""
        panel = self._create_panel()

        self.panels.append(panel)
        self.layout.addWidget(panel)
        self.root_splitter = None  # No splitter for single panel

        self._select_panel(panel)
        self.panel_added.emit(panel)

    def _select_panel(self, panel: WorkspacePanel):
        """Select a panel as the active one."""
        # Check if the previous selected panel is valid
        if self.selected_panel and self.selected_panel in self.panels:
            try:
                self.selected_panel.set_selected(False)
            except RuntimeError:
                # Panel was deleted, ignore
                pass

        self.selected_panel = panel
        if panel:
            panel.set_selected(True)
            self.panel_selected.emit(panel)

    def _handle_panel_close(self, panel: WorkspacePanel):
        """Handle panel close request."""
        if len(self.panels) <= 1:
            # Can't close the last panel
            return

        # Find the panel's parent splitter
        parent = panel.parent()
        if isinstance(parent, QSplitter):
            # Remove the panel
            self.panels.remove(panel)
            panel.setParent(None)
            panel.deleteLater()

            # If only one widget left in splitter, replace splitter with widget
            if parent.count() == 1:
                remaining_widget = parent.widget(0)
                grandparent = parent.parent()

                if isinstance(grandparent, QSplitter):
                    index = grandparent.indexOf(parent)
                    parent.setParent(None)
                    grandparent.insertWidget(index, remaining_widget)
                elif grandparent == self:
                    # Root level
                    parent.setParent(None)
                    self.layout.addWidget(remaining_widget)
                    self.root_splitter = None if not isinstance(remaining_widget, QSplitter) else remaining_widget

            self.panel_removed.emit(panel)
            self.layout_changed.emit()

            # Select another panel if needed
            if self.selected_panel == panel and self.panels:
                self._select_panel(self.panels[0])

    def _handle_panel_split(self, panel: WorkspacePanel, direction: str):
        """Handle panel split request."""
        # Create new panel using factory
        new_panel = self._create_panel()
        new_panel.set_title("Empty Panel")

        # Create splitter
        if direction == "horizontal":
            splitter = QSplitter(Qt.Vertical)
        else:  # vertical
            splitter = QSplitter(Qt.Horizontal)

        splitter.setChildrenCollapsible(False)

        # Get panel's parent
        parent = panel.parent()

        if parent == self:
            # Panel is at root level
            self.layout.removeWidget(panel)
            splitter.addWidget(panel)
            splitter.addWidget(new_panel)
            self.layout.addWidget(splitter)
            self.root_splitter = splitter
        elif isinstance(parent, QSplitter):
            # Panel is in a splitter
            index = parent.indexOf(panel)
            panel.setParent(None)
            splitter.addWidget(panel)
            splitter.addWidget(new_panel)
            parent.insertWidget(index, splitter)

        # Set equal sizes
        total_size = splitter.width() if direction == "vertical" else splitter.height()
        splitter.setSizes([total_size // 2, total_size // 2])

        self.panels.append(new_panel)
        self._select_panel(new_panel)

        self.panel_added.emit(new_panel)
        self.layout_changed.emit()

    def _handle_file_dropped(self, panel: WorkspacePanel, file_path: str):
        """Handle file dropped on panel."""
        # Propagate to parent window for handling
        self.file_dropped_on_panel.emit(panel, file_path)

    def set_theme(self, is_dark: bool):
        """Update theme for all panels."""
        self._is_dark_theme = is_dark
        for panel in self.panels:
            panel.set_theme(is_dark)

    def add_panel_at_position(self, position: str = "right"):
        """Add a new panel at the specified position relative to selected panel."""
        if not self.selected_panel:
            return

        direction = "vertical" if position in ["left", "right"] else "horizontal"
        self._handle_panel_split(self.selected_panel, direction)

    def get_panel_by_id(self, panel_id: str) -> Optional[WorkspacePanel]:
        """Get a panel by its ID."""
        for panel in self.panels:
            if panel.panel_id == panel_id:
                return panel
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize workspace to dictionary."""
        def serialize_widget(widget: QWidget) -> Dict[str, Any]:
            if isinstance(widget, WorkspacePanel):
                return widget.to_dict()
            elif isinstance(widget, QSplitter):
                children = []
                sizes = widget.sizes()
                for i in range(widget.count()):
                    children.append(serialize_widget(widget.widget(i)))
                return {
                    'type': 'splitter',
                    'orientation': 'horizontal' if widget.orientation() == Qt.Horizontal else 'vertical',
                    'sizes': sizes,
                    'children': children
                }
            return {}

        if self.root_splitter:
            return serialize_widget(self.root_splitter)
        elif self.panels:
            return self.panels[0].to_dict()
        return {}

    def from_dict(self, data: Dict[str, Any]):
        """Restore workspace from dictionary."""
        # Clear existing panels
        for panel in self.panels[:]:
            panel.setParent(None)
            panel.deleteLater()
        self.panels.clear()

        if self.root_splitter:
            self.root_splitter.setParent(None)
            self.root_splitter.deleteLater()
            self.root_splitter = None

        # Clear layout
        while self.layout.count():
            child = self.layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)

        # Reconstruct from data
        widget = self._reconstruct_widget(data)
        if widget:
            self.layout.addWidget(widget)
            if isinstance(widget, QSplitter):
                self.root_splitter = widget

    def _reconstruct_widget(self, data: Dict[str, Any]) -> Optional[QWidget]:
        """Reconstruct a widget from dictionary data."""
        if data.get('type') == 'panel' or data.get('type') == 'display_panel':
            # Check if it's a display panel or regular panel
            if data.get('type') == 'display_panel':
                from src.gui.workspace_display_panel import WorkspaceDisplayPanel
                panel = WorkspaceDisplayPanel.from_dict(data)
            else:
                panel = WorkspacePanel.from_dict(data)

            panel.close_requested.connect(self._handle_panel_close)
            panel.split_requested.connect(self._handle_panel_split)
            panel.file_dropped.connect(self._handle_file_dropped)

            # Apply current theme
            panel.set_theme(self._is_dark_theme)

            self.panels.append(panel)
            if data.get('selected'):
                self._select_panel(panel)
            return panel
        elif data.get('type') == 'splitter':
            orientation = Qt.Horizontal if data.get('orientation') == 'horizontal' else Qt.Vertical
            splitter = QSplitter(orientation)
            splitter.setChildrenCollapsible(False)

            for child_data in data.get('children', []):
                child_widget = self._reconstruct_widget(child_data)
                if child_widget:
                    splitter.addWidget(child_widget)

            # Restore sizes if available
            sizes = data.get('sizes')
            if sizes and len(sizes) == splitter.count():
                splitter.setSizes(sizes)

            return splitter
        return None

    def save_layout(self) -> Dict[str, Any]:
        """Save the current workspace layout."""
        try:
            return {
                'version': 1,
                'layout': self.to_dict()
            }
        except Exception as e:
            # Return a default layout if there's an error
            return {
                'version': 1,
                'layout': {'type': 'panel', 'title': 'Empty Panel'}
            }

    def load_layout(self, layout_data: Dict[str, Any]):
        """Load a workspace layout."""
        if layout_data.get('version') == 1:
            self.from_dict(layout_data.get('layout', {}))
            self.layout_changed.emit()

    def load_processed_data(self, file_path: str, data):
        """
        Load processed data directly into the selected panel.

        This is used when sending processed data from Processing Mode to Preview Mode
        without needing to save to a file first.

        Args:
            file_path: Virtual file path for display purposes
            data: NHDFData object to display
        """
        # Get the currently selected panel
        panel = self.selected_panel
        if not panel:
            # If no panel selected, use the first one
            if self.panels:
                panel = self.panels[0]
                self._select_panel(panel)
            else:
                return

        # Convert to WorkspaceDisplayPanel if needed
        from src.gui.workspace_display_panel import WorkspaceDisplayPanel
        if not isinstance(panel, WorkspaceDisplayPanel):
            # Create new display panel
            new_panel = WorkspaceDisplayPanel(panel.panel_id)
            new_panel.close_requested.connect(self._handle_panel_close)
            new_panel.split_requested.connect(self._handle_panel_split)
            new_panel.file_dropped.connect(self._handle_file_dropped)
            new_panel.set_theme(self._is_dark_theme)

            # Get parent and replace
            parent = panel.parent()
            from PySide6.QtWidgets import QSplitter
            if isinstance(parent, QSplitter):
                index = parent.indexOf(panel)
                panel.setParent(None)
                parent.insertWidget(index, new_panel)
            elif hasattr(self, 'layout'):
                self.layout.removeWidget(panel)
                self.layout.addWidget(new_panel)

            # Update references
            if panel in self.panels:
                idx = self.panels.index(panel)
                self.panels[idx] = new_panel
                if self.selected_panel == panel:
                    self.selected_panel = new_panel

            panel.deleteLater()
            panel = new_panel

        # Load the data into the panel
        panel.set_data(data, file_path)
        self._select_panel(panel)

        # Emit the file_loaded signal so the main window can update
        self.file_dropped_on_panel.emit(panel, file_path)