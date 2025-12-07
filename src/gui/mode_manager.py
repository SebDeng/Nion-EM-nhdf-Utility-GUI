"""
Central mode manager that coordinates between Preview and Processing modes.
This prevents circular imports by serving as the single point of coordination.
"""

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QTabWidget, QWidget
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.nhdf_reader import NHDFData


class ModeManager(QObject):
    """
    Manages switching between Preview and Processing modes.
    Acts as a central coordinator to prevent circular imports.
    """

    # Signals
    mode_changed = Signal(str)  # Emits "preview" or "processing"
    file_loaded = Signal(str, object)  # Emits (file_path, NHDFData)
    processing_requested = Signal(str, object)  # Emits (file_path, NHDFData) for processing mode

    def __init__(self, parent=None):
        super().__init__(parent)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Lazy-loaded mode widgets
        self._preview_widget: Optional[QWidget] = None
        self._processing_widget: Optional[QWidget] = None

        # Current state
        self.current_mode = "preview"
        self.current_file: Optional[str] = None
        self.current_data: Optional['NHDFData'] = None

        # Initialize both modes so tabs are visible
        self._init_preview_mode()
        self._init_processing_mode()

    def _init_preview_mode(self):
        """Initialize preview mode (always loaded)."""
        from src.gui.workspace_widget import WorkspaceWidget

        self._preview_widget = WorkspaceWidget()
        self.tab_widget.addTab(self._preview_widget, "Preview")

        # Connect preview widget signals
        if hasattr(self._preview_widget, 'file_loaded'):
            self._preview_widget.file_loaded.connect(self._on_preview_file_loaded)

    def _init_processing_mode(self):
        """Initialize processing mode."""
        if self._processing_widget is not None:
            return

        # Create a placeholder with label for now
        from PySide6.QtWidgets import QLabel, QVBoxLayout

        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        label = QLabel("Processing Mode\n(To be implemented)")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("QLabel { font-size: 18px; color: #888; }")
        layout.addWidget(label)

        self._processing_widget = placeholder
        self.tab_widget.addTab(self._processing_widget, "Processing")

    def _on_tab_changed(self, index: int):
        """Handle tab change."""
        if index == 0:
            self.current_mode = "preview"
            self.mode_changed.emit("preview")
        elif index == 1:
            self.current_mode = "processing"
            self.mode_changed.emit("processing")

            # If we have a file loaded, send it to processing mode
            if self.current_file and self.current_data:
                self.processing_requested.emit(self.current_file, self.current_data)

    def _on_preview_file_loaded(self, file_path: str, data: 'NHDFData'):
        """Handle file loaded in preview mode."""
        self.current_file = file_path
        self.current_data = data
        self.file_loaded.emit(file_path, data)

    def get_widget(self) -> QTabWidget:
        """Get the tab widget for embedding in main window."""
        return self.tab_widget

    def load_file(self, file_path: str, data: 'NHDFData'):
        """Load a file in the current mode."""
        self.current_file = file_path
        self.current_data = data

        if self.current_mode == "preview" and self._preview_widget:
            # Pass to preview widget
            if hasattr(self._preview_widget, 'load_file'):
                self._preview_widget.load_file(file_path, data)
        elif self.current_mode == "processing" and self._processing_widget:
            # Pass to processing widget
            if hasattr(self._processing_widget, 'load_file'):
                self._processing_widget.load_file(file_path, data)

        self.file_loaded.emit(file_path, data)

    def switch_to_processing(self, file_path: str = None, data: 'NHDFData' = None):
        """Switch to processing mode with optional file."""
        if file_path and data:
            self.current_file = file_path
            self.current_data = data

        # Switch to processing tab
        self.tab_widget.setCurrentIndex(1)

    def switch_to_preview(self):
        """Switch back to preview mode."""
        self.tab_widget.setCurrentIndex(0)

    def get_current_mode(self) -> str:
        """Get the current mode."""
        return self.current_mode

    def get_preview_widget(self) -> Optional[QWidget]:
        """Get the preview widget if initialized."""
        return self._preview_widget

    def get_processing_widget(self) -> Optional[QWidget]:
        """Get the processing widget if initialized."""
        return self._processing_widget