"""
File browser panel for navigating and selecting EM data files (nhdf, dm3, dm4).
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeView, QLineEdit,
    QPushButton, QFileSystemModel, QHeaderView, QMenu,
    QAbstractItemView, QComboBox, QLabel
)
from PySide6.QtCore import Qt, Signal, QDir, QModelIndex, QSortFilterProxyModel, QMimeData
from PySide6.QtGui import QAction, QDrag

import pathlib
from typing import Optional


class DraggableTreeView(QTreeView):
    """Tree view that supports dragging files."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)

    def startDrag(self, supportedActions):
        """Start a drag operation."""
        index = self.currentIndex()
        if not index.isValid():
            return

        # Get the model (proxy model)
        proxy_model = self.model()
        if not proxy_model:
            return

        # Get source model and index
        source_model = proxy_model.sourceModel()
        source_index = proxy_model.mapToSource(index)

        # Get file path
        file_path = source_model.filePath(source_index)

        # Only allow dragging of supported EM files
        supported_extensions = ('.nhdf', '.dm3', '.dm4')
        if not file_path.lower().endswith(supported_extensions):
            return

        # Create mime data
        mime_data = QMimeData()
        mime_data.setText(file_path)

        # Also add as URL for compatibility
        from PySide6.QtCore import QUrl
        mime_data.setUrls([QUrl.fromLocalFile(file_path)])

        # Create drag
        drag = QDrag(self)
        drag.setMimeData(mime_data)

        # Execute drag
        drag.exec(Qt.CopyAction)


class EMFileFilterProxyModel(QSortFilterProxyModel):
    """Proxy model to filter for EM data files (nhdf, dm3, dm4) and directories."""

    # Supported file extensions
    SUPPORTED_EXTENSIONS = ('.nhdf', '.dm3', '.dm4')

    def __init__(self, parent=None):
        super().__init__(parent)
        self._show_all_files = False

    def set_show_all_files(self, show: bool):
        """Toggle between showing all files or only EM data files."""
        self._show_all_files = show
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """Filter to show only directories and supported EM files."""
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)

        if model.isDir(index):
            return True

        if self._show_all_files:
            return True

        file_path = model.filePath(index)
        return file_path.lower().endswith(self.SUPPORTED_EXTENSIONS)


# Keep old name for backwards compatibility
NHDFFilterProxyModel = EMFileFilterProxyModel


class FileBrowserPanel(QWidget):
    """Panel for browsing and selecting nhdf files."""

    # Signals
    file_selected = Signal(pathlib.Path)  # Single click
    file_double_clicked = Signal(pathlib.Path)  # Double click to open

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_path: Optional[pathlib.Path] = None
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Path bar
        path_layout = QHBoxLayout()
        path_layout.setSpacing(4)

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Path...")
        self._path_edit.returnPressed.connect(self._on_path_entered)
        path_layout.addWidget(self._path_edit)

        self._browse_btn = QPushButton("...")
        self._browse_btn.setFixedWidth(30)
        self._browse_btn.setToolTip("Browse for folder")
        self._browse_btn.clicked.connect(self._on_browse_clicked)
        path_layout.addWidget(self._browse_btn)

        layout.addLayout(path_layout)

        # Filter options
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(4)

        filter_layout.addWidget(QLabel("Filter:"))

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["nhdf files (*.nhdf)", "All files (*)"])
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self._filter_combo, 1)

        layout.addLayout(filter_layout)

        # File system model
        self._fs_model = QFileSystemModel()
        self._fs_model.setRootPath("")
        self._fs_model.setFilter(QDir.AllDirs | QDir.Files | QDir.NoDotAndDotDot)

        # Proxy model for filtering
        self._proxy_model = NHDFFilterProxyModel()
        self._proxy_model.setSourceModel(self._fs_model)
        self._proxy_model.setDynamicSortFilter(True)

        # Tree view
        self._tree_view = DraggableTreeView()
        self._tree_view.setModel(self._proxy_model)
        self._tree_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self._tree_view.setContextMenuPolicy(Qt.CustomContextMenu)

        # Configure columns
        self._tree_view.setHeaderHidden(False)
        self._tree_view.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self._tree_view.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._tree_view.setColumnHidden(2, True)  # Hide type column
        self._tree_view.setColumnHidden(3, True)  # Hide date column

        # Connect signals
        self._tree_view.clicked.connect(self._on_item_clicked)
        self._tree_view.doubleClicked.connect(self._on_item_double_clicked)
        self._tree_view.customContextMenuRequested.connect(self._on_context_menu)

        layout.addWidget(self._tree_view, 1)

        # Quick actions
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(4)

        self._home_btn = QPushButton("Home")
        self._home_btn.clicked.connect(self._go_home)
        actions_layout.addWidget(self._home_btn)

        self._up_btn = QPushButton("Up")
        self._up_btn.clicked.connect(self._go_up)
        actions_layout.addWidget(self._up_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._refresh)
        actions_layout.addWidget(self._refresh_btn)

        layout.addLayout(actions_layout)

        # Set initial path to home
        self._go_home()

    def _on_path_entered(self):
        """Handle path entered in the path edit."""
        path_text = self._path_edit.text().strip()
        if path_text:
            path = pathlib.Path(path_text).expanduser()
            if path.exists():
                if path.is_dir():
                    self.set_root_path(path)
                elif path.is_file() and path.suffix.lower() == '.nhdf':
                    self.set_root_path(path.parent)
                    self.file_double_clicked.emit(path)

    def _on_browse_clicked(self):
        """Handle browse button click."""
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder",
            str(self._current_path or pathlib.Path.home())
        )
        if folder:
            self.set_root_path(pathlib.Path(folder))

    def _on_filter_changed(self, index: int):
        """Handle filter combo change."""
        show_all = index == 1  # "All files"
        self._proxy_model.set_show_all_files(show_all)

    def _on_item_clicked(self, index: QModelIndex):
        """Handle single click on item."""
        source_index = self._proxy_model.mapToSource(index)
        path = pathlib.Path(self._fs_model.filePath(source_index))

        if path.is_file() and path.suffix.lower() == '.nhdf':
            self.file_selected.emit(path)

    def _on_item_double_clicked(self, index: QModelIndex):
        """Handle double click on item."""
        source_index = self._proxy_model.mapToSource(index)
        path = pathlib.Path(self._fs_model.filePath(source_index))

        if path.is_dir():
            self.set_root_path(path)
        elif path.is_file() and path.suffix.lower() == '.nhdf':
            self.file_double_clicked.emit(path)

    def _on_context_menu(self, pos):
        """Show context menu."""
        index = self._tree_view.indexAt(pos)
        if not index.isValid():
            return

        source_index = self._proxy_model.mapToSource(index)
        path = pathlib.Path(self._fs_model.filePath(source_index))

        menu = QMenu(self)

        if path.is_file() and path.suffix.lower() == '.nhdf':
            open_action = QAction("Open", self)
            open_action.triggered.connect(lambda: self.file_double_clicked.emit(path))
            menu.addAction(open_action)

        if path.is_dir():
            set_root_action = QAction("Open Folder", self)
            set_root_action.triggered.connect(lambda: self.set_root_path(path))
            menu.addAction(set_root_action)

        if not menu.isEmpty():
            menu.exec_(self._tree_view.viewport().mapToGlobal(pos))

    def _go_home(self):
        """Navigate to home directory."""
        self.set_root_path(pathlib.Path.home())

    def _go_up(self):
        """Navigate to parent directory."""
        if self._current_path and self._current_path.parent != self._current_path:
            self.set_root_path(self._current_path.parent)

    def _refresh(self):
        """Refresh the current view."""
        if self._current_path:
            self.set_root_path(self._current_path)

    def set_root_path(self, path: pathlib.Path):
        """Set the root path for the file browser."""
        path = pathlib.Path(path).resolve()
        if not path.exists() or not path.is_dir():
            return

        self._current_path = path
        self._path_edit.setText(str(path))

        # Set the root index
        source_index = self._fs_model.setRootPath(str(path))
        proxy_index = self._proxy_model.mapFromSource(source_index)
        self._tree_view.setRootIndex(proxy_index)

    @property
    def current_path(self) -> Optional[pathlib.Path]:
        """Get the current root path."""
        return self._current_path

    def get_selected_file(self) -> Optional[pathlib.Path]:
        """Get the currently selected file, if any."""
        indexes = self._tree_view.selectedIndexes()
        if indexes:
            source_index = self._proxy_model.mapToSource(indexes[0])
            path = pathlib.Path(self._fs_model.filePath(source_index))
            if path.is_file():
                return path
        return None
