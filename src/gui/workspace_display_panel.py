"""
Display panel adapted for use in the workspace system.
Wraps the existing DisplayPanel for use in WorkspacePanel.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Signal

from typing import Optional
from src.core.nhdf_reader import NHDFData
from src.gui.display_panel import DisplayPanel
from src.gui.workspace import WorkspacePanel


class WorkspaceDisplayPanel(WorkspacePanel):
    """
    A workspace panel that contains a display panel for viewing nhdf data.
    """

    # Signals
    data_loaded = Signal(object)  # Emits NHDFData when data is loaded

    def __init__(self, panel_id: Optional[str] = None, parent=None):
        super().__init__(panel_id, parent)
        self.display_panel: Optional[DisplayPanel] = None
        self.current_data: Optional[NHDFData] = None
        self.current_file_path: Optional[str] = None

        self._setup_display_panel()

    def _setup_display_panel(self):
        """Set up the display panel within this workspace panel."""
        # Create display panel
        self.display_panel = DisplayPanel()

        # Set it as content
        self.set_content(self.display_panel)
        self.set_title("Empty Display")

    def set_data(self, data: Optional[NHDFData], file_path: Optional[str] = None):
        """Set the data to display."""
        self.current_data = data
        self.current_file_path = file_path

        if data:
            self.display_panel.set_data(data)
            # Update title with filename
            if file_path:
                import os
                filename = os.path.basename(file_path)
                self.set_title(filename)
            else:
                self.set_title("Display")

            self.data_loaded.emit(data)
        else:
            self.display_panel.clear()
            self.set_title("Empty Display")

    def get_current_colormap(self) -> str:
        """Get the current colormap from the display panel."""
        if self.display_panel:
            return self.display_panel.get_current_colormap()
        return "viridis"

    def get_display_range(self) -> tuple:
        """Get the current display range from the display panel."""
        if self.display_panel:
            return self.display_panel.get_display_range()
        return None

    def get_current_frame(self) -> Optional[int]:
        """Get the current frame index if displaying a sequence."""
        if self.display_panel and self.current_data and self.current_data.num_frames > 1:
            return self.display_panel._frame_slider.value() if hasattr(self.display_panel, '_frame_slider') else 0
        return None

    def to_dict(self) -> dict:
        """Serialize panel to dictionary."""
        data = super().to_dict()
        data['type'] = 'display_panel'
        data['file_path'] = self.current_file_path
        if self.display_panel:
            data['colormap'] = self.get_current_colormap()
            data['frame'] = self.get_current_frame()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'WorkspaceDisplayPanel':
        """Create panel from dictionary."""
        panel = cls(panel_id=data.get('panel_id'))
        # File loading would be handled by the main window after creation
        return panel


class WorkspaceMultiPanel(QWidget):
    """
    Widget that can manage multiple nhdf files in a workspace layout.
    """

    # Signals
    file_loaded = Signal(str, object)  # Emits (file_path, NHDFData)
    panel_selected = Signal(WorkspaceDisplayPanel)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.display_panels: dict[str, WorkspaceDisplayPanel] = {}
        self.selected_panel: Optional[WorkspaceDisplayPanel] = None

        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Placeholder for now - will be replaced by workspace widget
        self.placeholder = QWidget()
        layout.addWidget(self.placeholder)

    def add_display_panel(self, panel_id: str) -> WorkspaceDisplayPanel:
        """Add a new display panel."""
        panel = WorkspaceDisplayPanel(panel_id)
        self.display_panels[panel_id] = panel
        return panel

    def load_file_in_panel(self, panel: WorkspaceDisplayPanel, data: NHDFData, file_path: str):
        """Load a file in a specific panel."""
        panel.set_data(data, file_path)
        self.file_loaded.emit(file_path, data)

    def get_panel_by_file(self, file_path: str) -> Optional[WorkspaceDisplayPanel]:
        """Get panel displaying a specific file."""
        for panel in self.display_panels.values():
            if panel.current_file_path == file_path:
                return panel
        return None

    def select_panel(self, panel: WorkspaceDisplayPanel):
        """Select a panel as active."""
        if self.selected_panel:
            self.selected_panel.set_selected(False)

        self.selected_panel = panel
        panel.set_selected(True)
        self.panel_selected.emit(panel)