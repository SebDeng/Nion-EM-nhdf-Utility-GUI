"""
Main application window with free-tiling workspace support.
Extends the basic MainWindow to add Nion Swift-style workspace functionality.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QDockWidget, QMenuBar, QMenu, QStatusBar, QFileDialog,
    QMessageBox, QApplication, QDialog, QLabel, QPushButton,
    QInputDialog
)
from PySide6.QtCore import Qt, Signal, QSettings
from PySide6.QtGui import QAction, QKeySequence, QPixmap

import pathlib
import json
from typing import Optional, Dict, List

from src.core.nhdf_reader import NHDFData, read_nhdf
from src.gui.file_browser import FileBrowserPanel
from src.gui.metadata_panel import MetadataPanel
from src.gui.export_dialog import ExportDialog
from src.gui.workspace import WorkspaceWidget, WorkspacePanel
from src.gui.workspace_display_panel import WorkspaceDisplayPanel


class WorkspaceMainWindow(QMainWindow):
    """Main application window with free-tiling workspace support."""

    # Signals
    file_loaded = Signal(object)  # Emits NHDFData when file is loaded

    def __init__(self):
        super().__init__()

        self._loaded_files: Dict[str, NHDFData] = {}  # path -> data mapping
        self._settings = QSettings("NionUtility", "nhdfGUI")
        self._workspace_layouts: List[Dict] = []  # Saved layouts

        self._setup_ui()
        self._setup_menus()
        self._setup_statusbar()
        self._connect_signals()
        self._restore_state()
        self._load_default_layouts()

    def _setup_ui(self):
        """Set up the main UI layout with workspace."""
        self.setWindowTitle("Nion nhdf Utility - Workspace Edition")
        self.setMinimumSize(1400, 900)

        # Create workspace widget as central widget
        self._workspace = WorkspaceWidget()
        self.setCentralWidget(self._workspace)

        # Left dock - File Browser
        self._file_browser_dock = QDockWidget("File Browser", self)
        self._file_browser_dock.setObjectName("FileBrowserDock")
        self._file_browser = FileBrowserPanel()
        self._file_browser_dock.setWidget(self._file_browser)
        self._file_browser_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._file_browser_dock.setMinimumWidth(250)
        self.addDockWidget(Qt.LeftDockWidgetArea, self._file_browser_dock)

        # Right dock - Metadata Panel with Export button
        self._metadata_dock = QDockWidget("Metadata", self)
        self._metadata_dock.setObjectName("MetadataDock")

        # Create container widget with metadata panel and export button
        metadata_container = QWidget()
        metadata_layout = QVBoxLayout(metadata_container)
        metadata_layout.setContentsMargins(0, 0, 0, 0)
        metadata_layout.setSpacing(0)

        self._metadata_panel = MetadataPanel()
        metadata_layout.addWidget(self._metadata_panel, 1)

        # Export button at bottom of metadata panel
        self._export_btn = QPushButton("Export...")
        self._export_btn.setEnabled(False)
        self._export_btn.setMinimumHeight(36)
        self._export_btn.clicked.connect(self._on_export)
        self._export_btn.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                font-weight: bold;
                margin: 8px;
            }
        """)
        metadata_layout.addWidget(self._export_btn)

        self._metadata_dock.setWidget(metadata_container)
        self._metadata_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._metadata_dock.setMinimumWidth(300)
        self.addDockWidget(Qt.RightDockWidgetArea, self._metadata_dock)

    def _setup_menus(self):
        """Set up the menu bar with workspace actions."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._on_open_file)
        file_menu.addAction(open_action)

        open_folder_action = QAction("Open &Folder...", self)
        open_folder_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        open_folder_action.triggered.connect(self._on_open_folder)
        file_menu.addAction(open_folder_action)

        file_menu.addSeparator()

        open_in_new_panel_action = QAction("Open in &New Panel...", self)
        open_in_new_panel_action.setShortcut(QKeySequence("Ctrl+N"))
        open_in_new_panel_action.triggered.connect(self._on_open_in_new_panel)
        file_menu.addAction(open_in_new_panel_action)

        file_menu.addSeparator()

        close_panel_action = QAction("&Close Panel", self)
        close_panel_action.setShortcut(QKeySequence.Close)
        close_panel_action.triggered.connect(self._on_close_panel)
        file_menu.addAction(close_panel_action)

        close_all_action = QAction("Close &All Panels", self)
        close_all_action.triggered.connect(self._on_close_all_panels)
        file_menu.addAction(close_all_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        view_menu.addAction(self._file_browser_dock.toggleViewAction())
        view_menu.addAction(self._metadata_dock.toggleViewAction())

        view_menu.addSeparator()

        # Workspace submenu
        workspace_menu = view_menu.addMenu("&Workspace")

        split_h_action = QAction("Split &Horizontally", self)
        split_h_action.setShortcut(QKeySequence("Ctrl+H"))
        split_h_action.triggered.connect(lambda: self._split_panel("horizontal"))
        workspace_menu.addAction(split_h_action)

        split_v_action = QAction("Split &Vertically", self)
        split_v_action.setShortcut(QKeySequence("Ctrl+V"))
        split_v_action.triggered.connect(lambda: self._split_panel("vertical"))
        workspace_menu.addAction(split_v_action)

        workspace_menu.addSeparator()

        # Layout presets submenu
        layouts_menu = workspace_menu.addMenu("&Layout Presets")

        single_action = QAction("&Single Panel", self)
        single_action.triggered.connect(lambda: self._apply_layout_preset("single"))
        layouts_menu.addAction(single_action)

        two_h_action = QAction("2 Panels &Horizontal", self)
        two_h_action.triggered.connect(lambda: self._apply_layout_preset("2h"))
        layouts_menu.addAction(two_h_action)

        two_v_action = QAction("2 Panels &Vertical", self)
        two_v_action.triggered.connect(lambda: self._apply_layout_preset("2v"))
        layouts_menu.addAction(two_v_action)

        four_grid_action = QAction("&4 Panel Grid", self)
        four_grid_action.triggered.connect(lambda: self._apply_layout_preset("2x2"))
        layouts_menu.addAction(four_grid_action)

        layouts_menu.addSeparator()

        save_layout_action = QAction("&Save Current Layout...", self)
        save_layout_action.triggered.connect(self._on_save_layout)
        layouts_menu.addAction(save_layout_action)

        load_layout_action = QAction("&Load Layout...", self)
        load_layout_action.triggered.connect(self._on_load_layout)
        layouts_menu.addAction(load_layout_action)

        workspace_menu.addSeparator()

        reset_layout_action = QAction("&Reset Layout", self)
        reset_layout_action.triggered.connect(self._reset_layout)
        workspace_menu.addAction(reset_layout_action)

        view_menu.addSeparator()

        reset_all_action = QAction("Reset &All Views", self)
        reset_all_action.triggered.connect(self._reset_all_views)
        view_menu.addAction(reset_all_action)

        # Export menu
        export_menu = menubar.addMenu("&Export")

        export_action = QAction("&Export Current Panel...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._on_export)
        export_action.setEnabled(False)
        self._export_action = export_action
        export_menu.addAction(export_action)

        export_all_action = QAction("Export &All Panels...", self)
        export_all_action.triggered.connect(self._on_export_all)
        export_all_action.setEnabled(False)
        self._export_all_action = export_all_action
        export_menu.addAction(export_all_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _setup_statusbar(self):
        """Set up the status bar."""
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("Ready")

    def _connect_signals(self):
        """Connect signals between components."""
        # File browser signals
        self._file_browser.file_selected.connect(self._on_file_selected)
        self._file_browser.file_double_clicked.connect(self._load_file_in_current_panel)

        # Workspace signals
        self._workspace.panel_added.connect(self._on_panel_added)
        self._workspace.panel_removed.connect(self._on_panel_removed)
        self._workspace.panel_selected.connect(self._on_panel_selected)
        self._workspace.layout_changed.connect(self._on_layout_changed)
        self._workspace.file_dropped_on_panel.connect(self._on_file_dropped_on_panel)

    def _restore_state(self):
        """Restore window state from settings."""
        geometry = self._settings.value("workspace/geometry")
        if geometry:
            self.restoreGeometry(geometry)

        state = self._settings.value("workspace/windowState")
        if state:
            self.restoreState(state)

        # Restore last folder
        last_folder = self._settings.value("workspace/lastFolder")
        if last_folder and pathlib.Path(last_folder).exists():
            self._file_browser.set_root_path(pathlib.Path(last_folder))

        # Restore workspace layout
        layout_data = self._settings.value("workspace/layout")
        if layout_data:
            try:
                self._workspace.load_layout(json.loads(layout_data))
            except Exception as e:
                print(f"Failed to restore workspace layout: {e}")

    def _save_state(self):
        """Save window state to settings."""
        self._settings.setValue("workspace/geometry", self.saveGeometry())
        self._settings.setValue("workspace/windowState", self.saveState())

        if self._file_browser.current_path:
            self._settings.setValue("workspace/lastFolder", str(self._file_browser.current_path))

        # Save workspace layout
        layout_data = self._workspace.save_layout()
        self._settings.setValue("workspace/layout", json.dumps(layout_data))

    def closeEvent(self, event):
        """Handle window close event."""
        self._save_state()
        super().closeEvent(event)

    def _load_default_layouts(self):
        """Load default layout presets."""
        self._workspace_layouts = [
            {
                "name": "Single Panel",
                "id": "single",
                "layout": {
                    "type": "panel",
                    "title": "Empty Panel"
                }
            },
            {
                "name": "2 Panels Horizontal",
                "id": "2h",
                "layout": {
                    "type": "splitter",
                    "orientation": "vertical",
                    "sizes": [50, 50],
                    "children": [
                        {"type": "panel", "title": "Panel 1"},
                        {"type": "panel", "title": "Panel 2"}
                    ]
                }
            },
            {
                "name": "2 Panels Vertical",
                "id": "2v",
                "layout": {
                    "type": "splitter",
                    "orientation": "horizontal",
                    "sizes": [50, 50],
                    "children": [
                        {"type": "panel", "title": "Panel 1"},
                        {"type": "panel", "title": "Panel 2"}
                    ]
                }
            },
            {
                "name": "4 Panel Grid",
                "id": "2x2",
                "layout": {
                    "type": "splitter",
                    "orientation": "vertical",
                    "sizes": [50, 50],
                    "children": [
                        {
                            "type": "splitter",
                            "orientation": "horizontal",
                            "sizes": [50, 50],
                            "children": [
                                {"type": "panel", "title": "Panel 1"},
                                {"type": "panel", "title": "Panel 2"}
                            ]
                        },
                        {
                            "type": "splitter",
                            "orientation": "horizontal",
                            "sizes": [50, 50],
                            "children": [
                                {"type": "panel", "title": "Panel 3"},
                                {"type": "panel", "title": "Panel 4"}
                            ]
                        }
                    ]
                }
            }
        ]

    # --- Workspace operations ---

    def _split_panel(self, direction: str):
        """Split the current panel."""
        if self._workspace.selected_panel:
            self._workspace._handle_panel_split(self._workspace.selected_panel, direction)

    def _apply_layout_preset(self, preset_id: str):
        """Apply a layout preset."""
        for layout in self._workspace_layouts:
            if layout["id"] == preset_id:
                self._workspace.from_dict(layout["layout"])
                self._workspace.layout_changed.emit()
                break

    def _on_save_layout(self):
        """Save current workspace layout."""
        name, ok = QInputDialog.getText(
            self,
            "Save Layout",
            "Layout name:"
        )
        if ok and name:
            layout_data = self._workspace.save_layout()
            # Save to settings or file
            saved_layouts = self._settings.value("workspace/saved_layouts", [])
            if not isinstance(saved_layouts, list):
                saved_layouts = []
            saved_layouts.append({
                "name": name,
                "layout": layout_data
            })
            self._settings.setValue("workspace/saved_layouts", saved_layouts)
            QMessageBox.information(self, "Layout Saved", f"Layout '{name}' saved successfully.")

    def _on_load_layout(self):
        """Load a saved workspace layout."""
        saved_layouts = self._settings.value("workspace/saved_layouts", [])
        if not saved_layouts:
            QMessageBox.information(self, "No Saved Layouts", "No saved layouts found.")
            return

        # TODO: Show a dialog to select from saved layouts
        # For now, just load the first one
        if saved_layouts:
            self._workspace.load_layout(saved_layouts[0]["layout"])

    def _reset_layout(self):
        """Reset workspace to single panel."""
        self._apply_layout_preset("single")

    def _reset_all_views(self):
        """Reset all dock widgets and workspace."""
        self._file_browser_dock.setVisible(True)
        self._metadata_dock.setVisible(True)

        self.removeDockWidget(self._file_browser_dock)
        self.removeDockWidget(self._metadata_dock)

        self.addDockWidget(Qt.LeftDockWidgetArea, self._file_browser_dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self._metadata_dock)

        self._reset_layout()

    # --- Panel event handlers ---

    def _on_panel_added(self, panel: WorkspacePanel):
        """Handle panel addition."""
        if isinstance(panel, WorkspaceDisplayPanel):
            panel.data_loaded.connect(lambda data: self._on_data_loaded_in_panel(panel, data))

    def _on_panel_removed(self, panel: WorkspacePanel):
        """Handle panel removal."""
        self._update_export_actions()

    def _on_panel_selected(self, panel: WorkspacePanel):
        """Handle panel selection."""
        # Update metadata panel if it's a display panel with data
        if isinstance(panel, WorkspaceDisplayPanel) and panel.current_data:
            self._metadata_panel.set_data(panel.current_data)
            self._statusbar.showMessage(panel.current_data.get_summary())
        else:
            self._metadata_panel.clear()

        self._update_export_actions()

    def _on_layout_changed(self):
        """Handle workspace layout change."""
        self._statusbar.showMessage(f"Workspace: {len(self._workspace.panels)} panels", 2000)

    def _on_data_loaded_in_panel(self, panel: WorkspaceDisplayPanel, data: NHDFData):
        """Handle data loaded in a specific panel."""
        if panel == self._workspace.selected_panel:
            self._metadata_panel.set_data(data)
            self._statusbar.showMessage(data.get_summary())

        self._update_export_actions()

    def _on_file_dropped_on_panel(self, panel: WorkspacePanel, file_path: str):
        """Handle file dropped on a panel."""
        # Load the file into the panel
        self._load_file_in_panel(panel, pathlib.Path(file_path))

    # --- File operations ---

    def _on_open_file(self):
        """Open a file dialog to select an nhdf file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open nhdf File",
            str(self._file_browser.current_path or pathlib.Path.home()),
            "nhdf Files (*.nhdf);;All Files (*)"
        )
        if file_path:
            self._load_file_in_current_panel(pathlib.Path(file_path))

    def _on_open_in_new_panel(self):
        """Open a file in a new panel."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open nhdf File in New Panel",
            str(self._file_browser.current_path or pathlib.Path.home()),
            "nhdf Files (*.nhdf);;All Files (*)"
        )
        if file_path:
            # Split current panel vertically and load file in new panel
            self._split_panel("vertical")
            self._load_file_in_current_panel(pathlib.Path(file_path))

    def _on_open_folder(self):
        """Open a folder in the file browser."""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Open Folder",
            str(self._file_browser.current_path or pathlib.Path.home())
        )
        if folder_path:
            self._file_browser.set_root_path(pathlib.Path(folder_path))

    def _on_close_panel(self):
        """Close the current panel."""
        if self._workspace.selected_panel and len(self._workspace.panels) > 1:
            self._workspace._handle_panel_close(self._workspace.selected_panel)

    def _on_close_all_panels(self):
        """Close all panels except one."""
        self._reset_layout()

    def _on_file_selected(self, path: pathlib.Path):
        """Handle file selection in browser (single click)."""
        # Show preview info in status bar
        try:
            from src.core.nhdf_reader import get_file_info
            info = get_file_info(path)
            if "error" not in info:
                self._statusbar.showMessage(
                    f"{path.name} | Shape: {info['shape']} | Frames: {info['num_frames']}"
                )
        except Exception:
            pass

    def _load_file_in_current_panel(self, path: pathlib.Path):
        """Load a file in the currently selected panel."""
        if self._workspace.selected_panel:
            self._load_file_in_panel(self._workspace.selected_panel, path)

    def _load_file_in_panel(self, panel: WorkspacePanel, path: pathlib.Path):
        """Load a file in a specific panel."""
        # Convert to WorkspaceDisplayPanel if needed
        if not isinstance(panel, WorkspaceDisplayPanel):
            # Replace with display panel
            new_panel = WorkspaceDisplayPanel(panel.panel_id)
            new_panel.close_requested.connect(self._workspace._handle_panel_close)
            new_panel.split_requested.connect(self._workspace._handle_panel_split)
            new_panel.file_dropped.connect(self._workspace._handle_file_dropped)
            new_panel.data_loaded.connect(lambda data: self._on_data_loaded_in_panel(new_panel, data))

            # Replace in workspace
            parent = panel.parent()
            from PySide6.QtWidgets import QSplitter
            if isinstance(parent, QSplitter):
                index = parent.indexOf(panel)
                panel.setParent(None)
                parent.insertWidget(index, new_panel)
            elif hasattr(self._workspace, 'layout'):
                self._workspace.layout.removeWidget(panel)
                self._workspace.layout.addWidget(new_panel)

            # Update references
            idx = self._workspace.panels.index(panel)
            self._workspace.panels[idx] = new_panel
            panel.deleteLater()
            panel = new_panel
            self._workspace._select_panel(new_panel)

        # Load file
        try:
            self._statusbar.showMessage(f"Loading {path.name}...")
            QApplication.processEvents()

            # Check if already loaded
            str_path = str(path)
            if str_path not in self._loaded_files:
                data = read_nhdf(path)
                self._loaded_files[str_path] = data
            else:
                data = self._loaded_files[str_path]

            panel.set_data(data, str(path))

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Loading File",
                f"Failed to load {path.name}:\n{str(e)}"
            )
            self._statusbar.showMessage("Error loading file")

    def _update_export_actions(self):
        """Update export action states."""
        has_data = False
        if isinstance(self._workspace.selected_panel, WorkspaceDisplayPanel):
            has_data = self._workspace.selected_panel.current_data is not None

        self._export_action.setEnabled(has_data)
        self._export_btn.setEnabled(has_data)

        # Check if any panel has data
        any_has_data = any(
            isinstance(p, WorkspaceDisplayPanel) and p.current_data
            for p in self._workspace.panels
        )
        self._export_all_action.setEnabled(any_has_data)

    # --- Export operations ---

    def _on_export(self):
        """Export current panel data."""
        if not isinstance(self._workspace.selected_panel, WorkspaceDisplayPanel):
            return

        panel = self._workspace.selected_panel
        if not panel.current_data:
            return

        # Get current display settings
        current_colormap = panel.get_current_colormap()
        display_range = panel.get_display_range()

        dialog = ExportDialog(
            panel.current_data,
            parent=self,
            current_colormap=current_colormap,
            display_range=display_range
        )
        dialog.exec()

    def _on_export_all(self):
        """Export all panel data."""
        # TODO: Implement batch export for all panels
        QMessageBox.information(
            self,
            "Export All",
            "Batch export for all panels will be implemented soon."
        )

    def _on_about(self):
        """Show about dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("About Atomic Engineering nhdf Utility")
        dialog.setFixedSize(500, 400)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Logo
        logo_label = QLabel()
        logo_path = pathlib.Path(__file__).parent.parent.parent / "assets" / "AE Full Icon.png"
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            scaled_pixmap = pixmap.scaledToWidth(400, Qt.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
            logo_label.setAlignment(Qt.AlignCenter)
        else:
            logo_label.setText("<h2>Atomic Engineering</h2>")
            logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label)

        # Title and description
        title_label = QLabel("<h3>nhdf Utility GUI - Workspace Edition</h3>")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        desc_label = QLabel(
            "<p>A viewer for Nion electron microscopy nhdf files</p>"
            "<p>with Nion Swift-inspired free-tiling workspace.</p>"
            "<br>"
            "<p>Features:</p>"
            "<p>• Free-tiling window layout<br>"
            "• Multiple files open simultaneously<br>"
            "• Flexible panel splitting<br>"
            "• Layout presets and saving</p>"
        )
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # Links
        links_label = QLabel(
            "<p><a href='https://github.com/SebDeng/Nion-EM-nhdf-Utility-GUI'>GitHub Repository</a></p>"
        )
        links_label.setAlignment(Qt.AlignCenter)
        links_label.setOpenExternalLinks(True)
        layout.addWidget(links_label)

        layout.addStretch()

        dialog.exec()

    # --- Public API ---

    def load_file(self, path: pathlib.Path):
        """Public method to load a file."""
        self._load_file_in_current_panel(path)