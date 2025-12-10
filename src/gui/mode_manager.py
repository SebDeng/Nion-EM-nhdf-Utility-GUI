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

        # Import and create the new ProcessingModeWidgetV3
        from src.gui.processing_mode.processing_mode_widget_v3 import ProcessingModeWidgetV3

        self._processing_widget = ProcessingModeWidgetV3()
        self.tab_widget.addTab(self._processing_widget, "Processing")

        # Connect processing widget signals
        if hasattr(self._processing_widget, 'file_loaded'):
            self._processing_widget.file_loaded.connect(self._on_processing_file_loaded)

        # Connect send to preview signal
        if hasattr(self._processing_widget, 'send_to_preview_requested'):
            self._processing_widget.send_to_preview_requested.connect(self._on_send_to_preview)

    def _on_tab_changed(self, index: int):
        """Handle tab change."""
        if index == 0:
            self.current_mode = "preview"
            self.mode_changed.emit("preview")
        elif index == 1:
            self.current_mode = "processing"
            self.mode_changed.emit("processing")

            # Don't auto-load - wait for explicit request

    def _on_preview_file_loaded(self, file_path: str, data: 'NHDFData'):
        """Handle file loaded in preview mode."""
        self.current_file = file_path
        self.current_data = data
        self.file_loaded.emit(file_path, data)

    def _on_processing_file_loaded(self, file_path: str, data: 'NHDFData'):
        """Handle file loaded in processing mode."""
        self.current_file = file_path
        self.current_data = data
        self.file_loaded.emit(file_path, data)

    def _on_send_to_preview(self, file_path: str, data: 'NHDFData'):
        """Handle send to preview request from processing mode."""
        self.switch_to_preview(file_path, data)

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

    def switch_to_preview(self, file_path: str = None, data: 'NHDFData' = None):
        """Switch to preview mode with optional data to load."""
        if file_path and data:
            self.current_file = file_path
            self.current_data = data

            # Load in preview widget
            if self._preview_widget and hasattr(self._preview_widget, 'load_processed_data'):
                self._preview_widget.load_processed_data(file_path, data)

        # Switch to preview tab
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