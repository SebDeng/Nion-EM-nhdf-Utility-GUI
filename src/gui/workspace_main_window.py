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
from typing import Optional, Dict, List, Set
import warnings

from src.core.nhdf_reader import NHDFData, read_em_file, is_supported_file
from src.gui.file_browser import FileBrowserPanel
from src.gui.metadata_panel import MetadataPanel
from src.gui.export_dialog import ExportDialog
from src.gui.workspace import WorkspaceWidget, WorkspacePanel
from src.gui.workspace_display_panel import WorkspaceDisplayPanel
from src.gui.unified_control_panel import UnifiedControlPanel
from src.gui.view_mode_toolbar import ViewModeToolBar
from src.gui.mode_manager import ModeManager
from src.gui.preview_mode import AnalysisToolBar
from src.gui.preview_mode.analysis_panel import AnalysisResultsPanel
from src.gui.measurement_toolbar import MeasurementToolBar


class WorkspaceMainWindow(QMainWindow):
    """Main application window with free-tiling workspace support."""

    # Signals
    file_loaded = Signal(object)  # Emits NHDFData when file is loaded

    def __init__(self):
        super().__init__()

        self._loaded_files: Dict[str, NHDFData] = {}  # path -> data mapping
        self._settings = QSettings("NionUtility", "nhdfGUI")
        self._workspace_layouts: List[Dict] = []  # Saved layouts
        self._is_dark_mode = True  # Track current theme
        self._current_display_panel = None  # Track active display panel for reference
        self._measurement_connected_panels: Set[int] = set()  # Track panels with measurement signal connected

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

        # Create central widget with layout
        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # Top toolbar row - contains view mode toolbar (left) and measurement toolbar (right)
        top_toolbar_widget = QWidget()
        top_toolbar_layout = QHBoxLayout(top_toolbar_widget)
        top_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        top_toolbar_layout.setSpacing(0)

        # Add view mode toolbar at the top left
        self._view_toolbar = ViewModeToolBar()
        self._view_toolbar.layout_selected.connect(self._on_view_mode_selected)
        self._view_toolbar.theme_changed.connect(self._on_theme_changed)
        top_toolbar_layout.addWidget(self._view_toolbar)

        # Add measurement toolbar at the top right
        self._measurement_toolbar = MeasurementToolBar()
        self._measurement_toolbar.create_measurement.connect(self._on_create_measurement)
        self._measurement_toolbar.clear_all.connect(self._on_clear_measurements)
        self._measurement_toolbar.clear_last.connect(self._on_clear_last_measurement)
        self._measurement_toolbar.toggle_labels.connect(self._on_toggle_measurement_labels)
        top_toolbar_layout.addWidget(self._measurement_toolbar, 1)  # Give stretch factor to fill space

        central_layout.addWidget(top_toolbar_widget)

        # Add unified control panel below the view toolbar
        self._unified_controls = UnifiedControlPanel()
        central_layout.addWidget(self._unified_controls)

        # Add analysis toolbar below unified controls (only visible in preview mode)
        self._analysis_toolbar = AnalysisToolBar()
        self._analysis_toolbar.create_line_profile.connect(self._on_create_line_profile)
        self._analysis_toolbar.clear_requested.connect(self._on_clear_analysis)
        self._analysis_toolbar.width_changed.connect(self._on_line_width_changed)
        self._analysis_toolbar.unit_changed.connect(self._on_unit_changed)
        self._analysis_toolbar.export_requested.connect(self._on_export_plot)
        self._analysis_toolbar.show_histogram.connect(self._on_show_histogram)
        central_layout.addWidget(self._analysis_toolbar)

        # Create mode manager with tabbed workspace/processing
        self._mode_manager = ModeManager(self)
        self._mode_manager.mode_changed.connect(self._on_mode_changed)
        self._mode_manager.processing_requested.connect(self._on_processing_requested)
        central_layout.addWidget(self._mode_manager.get_widget(), 1)  # Give tabs the stretch factor

        # Keep reference to workspace for compatibility
        self._workspace = self._mode_manager.get_preview_widget()

        self.setCentralWidget(central_widget)

        # Left dock - File Browser
        self._file_browser_dock = QDockWidget("File Browser", self)
        self._file_browser_dock.setObjectName("FileBrowserDock")
        self._file_browser = FileBrowserPanel()
        self._file_browser_dock.setWidget(self._file_browser)
        self._file_browser_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._file_browser_dock.setMinimumWidth(250)
        self.addDockWidget(Qt.LeftDockWidgetArea, self._file_browser_dock)

        # Right dock - Metadata Panel (without Export button - moved to File menu)
        self._metadata_dock = QDockWidget("Metadata", self)
        self._metadata_dock.setObjectName("MetadataDock")

        self._metadata_panel = MetadataPanel()
        self._metadata_dock.setWidget(self._metadata_panel)
        self._metadata_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._metadata_dock.setMinimumWidth(300)
        self.addDockWidget(Qt.RightDockWidgetArea, self._metadata_dock)

        # Bottom dock - Analysis Results Panel (only visible in preview mode)
        self._analysis_dock = QDockWidget("Analysis Results", self)
        self._analysis_dock.setObjectName("AnalysisDock")

        self._analysis_panel = AnalysisResultsPanel()
        self._analysis_dock.setWidget(self._analysis_panel)
        self._analysis_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.RightDockWidgetArea)
        self._analysis_dock.setMinimumHeight(200)
        self.addDockWidget(Qt.BottomDockWidgetArea, self._analysis_dock)
        self._analysis_dock.setVisible(False)  # Start hidden

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

        # Export action (moved from metadata panel for better accessibility)
        self._export_action = QAction("&Export...", self)
        self._export_action.setShortcut(QKeySequence("Ctrl+E"))
        self._export_action.setEnabled(False)
        self._export_action.triggered.connect(self._on_export)
        file_menu.addAction(self._export_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        view_menu.addAction(self._file_browser_dock.toggleViewAction())
        view_menu.addAction(self._metadata_dock.toggleViewAction())
        view_menu.addAction(self._analysis_dock.toggleViewAction())

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

        # Process menu
        process_menu = menubar.addMenu("&Process")

        send_to_processing_action = QAction("&Send to Processing Mode", self)
        send_to_processing_action.setShortcut(QKeySequence("Ctrl+P"))
        send_to_processing_action.triggered.connect(self._send_to_processing_mode)
        send_to_processing_action.setEnabled(False)
        self._send_to_processing_action = send_to_processing_action
        process_menu.addAction(send_to_processing_action)

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

        # Connect panel selection to unified controls
        self._workspace.panel_selected.connect(self._update_unified_controls)

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
                    "orientation": "vertical",  # Vertical splitter = side by side panels
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
                    "orientation": "horizontal",  # Horizontal splitter = stacked panels
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
            },
            {
                "name": "3 Panels Horizontal",
                "id": "3h",
                "layout": {
                    "type": "splitter",
                    "orientation": "vertical",  # Vertical splitter = side by side panels
                    "sizes": [33, 34, 33],
                    "children": [
                        {"type": "panel", "title": "Panel 1"},
                        {"type": "panel", "title": "Panel 2"},
                        {"type": "panel", "title": "Panel 3"}
                    ]
                }
            },
            {
                "name": "3 Panels Vertical",
                "id": "3v",
                "layout": {
                    "type": "splitter",
                    "orientation": "horizontal",  # Horizontal splitter = stacked panels
                    "sizes": [33, 34, 33],
                    "children": [
                        {"type": "panel", "title": "Panel 1"},
                        {"type": "panel", "title": "Panel 2"},
                        {"type": "panel", "title": "Panel 3"}
                    ]
                }
            },
            {
                "name": "9 Panel Grid",
                "id": "3x3",
                "layout": {
                    "type": "splitter",
                    "orientation": "vertical",
                    "sizes": [33, 34, 33],
                    "children": [
                        {
                            "type": "splitter",
                            "orientation": "horizontal",
                            "sizes": [33, 34, 33],
                            "children": [
                                {"type": "panel", "title": "Panel 1"},
                                {"type": "panel", "title": "Panel 2"},
                                {"type": "panel", "title": "Panel 3"}
                            ]
                        },
                        {
                            "type": "splitter",
                            "orientation": "horizontal",
                            "sizes": [33, 34, 33],
                            "children": [
                                {"type": "panel", "title": "Panel 4"},
                                {"type": "panel", "title": "Panel 5"},
                                {"type": "panel", "title": "Panel 6"}
                            ]
                        },
                        {
                            "type": "splitter",
                            "orientation": "horizontal",
                            "sizes": [33, 34, 33],
                            "children": [
                                {"type": "panel", "title": "Panel 7"},
                                {"type": "panel", "title": "Panel 8"},
                                {"type": "panel", "title": "Panel 9"}
                            ]
                        }
                    ]
                }
            },
            {
                "name": "6 Panel Grid (2x3)",
                "id": "2x3",
                "layout": {
                    "type": "splitter",
                    "orientation": "vertical",
                    "sizes": [50, 50],
                    "children": [
                        {
                            "type": "splitter",
                            "orientation": "horizontal",
                            "sizes": [33, 34, 33],
                            "children": [
                                {"type": "panel", "title": "Panel 1"},
                                {"type": "panel", "title": "Panel 2"},
                                {"type": "panel", "title": "Panel 3"}
                            ]
                        },
                        {
                            "type": "splitter",
                            "orientation": "horizontal",
                            "sizes": [33, 34, 33],
                            "children": [
                                {"type": "panel", "title": "Panel 4"},
                                {"type": "panel", "title": "Panel 5"},
                                {"type": "panel", "title": "Panel 6"}
                            ]
                        }
                    ]
                }
            },
            {
                "name": "6 Panel Grid (3x2)",
                "id": "3x2",
                "layout": {
                    "type": "splitter",
                    "orientation": "vertical",
                    "sizes": [33, 34, 33],
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
                        },
                        {
                            "type": "splitter",
                            "orientation": "horizontal",
                            "sizes": [50, 50],
                            "children": [
                                {"type": "panel", "title": "Panel 5"},
                                {"type": "panel", "title": "Panel 6"}
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

    def _on_view_mode_selected(self, layout_id: str):
        """Handle view mode selection from toolbar."""
        # Map toolbar layout IDs to preset IDs
        layout_map = {
            "single": "single",
            "h2": "2h",
            "v2": "2v",
            "grid4": "2x2",
            "h3": "3h",
            "v3": "3v",
            "grid9": "3x3",
            "grid6": "2x3",
            "grid6_v": "3x2",
        }

        # Check if it's a predefined layout
        if layout_id in layout_map:
            preset_id = layout_map[layout_id]
            self._apply_layout_preset(preset_id)
        else:
            # Handle custom layouts (L-shape, T-shape, etc.)
            self._apply_custom_layout(layout_id)

    def _apply_custom_layout(self, layout_id: str):
        """Apply a custom layout pattern."""
        # For now, just create a basic layout
        # TODO: Implement custom layout patterns
        if layout_id == "l_shape":
            # Create L-shaped layout
            self._apply_layout_preset("2x2")  # Fallback to 2x2 for now
        elif layout_id == "t_shape":
            # Create T-shaped layout
            self._apply_layout_preset("2x2")  # Fallback to 2x2 for now
        elif layout_id == "h_shape":
            # Create H-shaped layout
            self._apply_layout_preset("2x2")  # Fallback to 2x2 for now

    def _on_theme_changed(self, is_dark: bool):
        """Handle theme change from toolbar."""
        from PySide6.QtGui import QPalette, QColor
        app = QApplication.instance()

        self._is_dark_mode = is_dark

        # Update the view mode toolbar's theme (no-op if it's the source of the change)
        if hasattr(self, '_view_toolbar'):
            self._view_toolbar.set_theme(is_dark)

        # Update analysis toolbar theme
        if hasattr(self, '_analysis_toolbar'):
            self._analysis_toolbar.set_theme(is_dark)

        # Update measurement toolbar theme
        if hasattr(self, '_measurement_toolbar'):
            self._measurement_toolbar.set_theme(is_dark)

        # Update analysis panel theme
        if hasattr(self, '_analysis_panel'):
            self._analysis_panel.set_theme(is_dark)

        if is_dark:
            # Apply dark theme
            from main import apply_dark_theme
            apply_dark_theme(app)
            # Update pyqtgraph graphics widgets for dark mode
            self._update_pyqtgraph_theme(is_dark=True)
        else:
            # Apply light theme
            palette = QPalette()

            # Light theme colors
            white = QColor(255, 255, 255)
            light_gray = QColor(240, 240, 240)
            gray = QColor(180, 180, 180)
            dark_gray = QColor(100, 100, 100)
            black = QColor(0, 0, 0)
            blue = QColor(42, 130, 218)

            # Set palette colors for light theme
            palette.setColor(QPalette.Window, light_gray)
            palette.setColor(QPalette.WindowText, black)
            palette.setColor(QPalette.Base, white)
            palette.setColor(QPalette.AlternateBase, light_gray)
            palette.setColor(QPalette.ToolTipBase, light_gray)
            palette.setColor(QPalette.ToolTipText, black)
            palette.setColor(QPalette.Text, black)
            palette.setColor(QPalette.Button, light_gray)
            palette.setColor(QPalette.ButtonText, black)
            palette.setColor(QPalette.BrightText, Qt.red)
            palette.setColor(QPalette.Link, blue)
            palette.setColor(QPalette.Highlight, blue)
            palette.setColor(QPalette.HighlightedText, white)

            # Disabled colors
            palette.setColor(QPalette.Disabled, QPalette.WindowText, gray)
            palette.setColor(QPalette.Disabled, QPalette.Text, gray)
            palette.setColor(QPalette.Disabled, QPalette.ButtonText, gray)

            app.setPalette(palette)

            # Light theme stylesheet
            app.setStyleSheet("""
                QWidget {
                    background-color: #f0f0f0;
                    color: #000000;
                }
                QFrame {
                    background-color: #f0f0f0;
                    color: #000000;
                }
                QToolTip {
                    color: #000000;
                    background-color: #f0f0f0;
                    border: 1px solid #b4b4b4;
                    padding: 4px;
                }
                QMenuBar {
                    background-color: #f0f0f0;
                    padding: 2px;
                }
                QMenuBar::item:selected {
                    background-color: #d0d0d0;
                }
                QMenu {
                    background-color: #f0f0f0;
                    border: 1px solid #b4b4b4;
                }
                QMenu::item:selected {
                    background-color: #2a82da;
                    color: white;
                }
                QTreeView {
                    background-color: white;
                    alternate-background-color: #f5f5f5;
                    border: 1px solid #b4b4b4;
                }
                QTreeView::item:hover {
                    background-color: #e0e0e0;
                }
                QTreeView::item:selected {
                    background-color: #2a82da;
                    color: white;
                }
                QDockWidget {
                    background-color: #f0f0f0;
                    color: #000000;
                }
                QDockWidget::title {
                    background-color: #e0e0e0;
                    padding: 6px;
                    color: #000000;
                }
                QStatusBar {
                    background-color: #f0f0f0;
                    border-top: 1px solid #b4b4b4;
                    color: #000000;
                }
                QHeaderView::section {
                    background-color: #e0e0e0;
                    padding: 4px;
                    border: 1px solid #b4b4b4;
                    color: #000000;
                }
                QSlider::groove:horizontal {
                    border: 1px solid #b4b4b4;
                    height: 6px;
                    background: #ffffff;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background: #2a82da;
                    border: 1px solid #2a82da;
                    width: 14px;
                    margin: -4px 0;
                    border-radius: 7px;
                }
                QSlider::handle:horizontal:hover {
                    background: #3a92ea;
                }
                QSpinBox, QDoubleSpinBox {
                    background-color: white;
                    border: 1px solid #b4b4b4;
                    padding: 2px;
                    color: #000000;
                }
                QComboBox {
                    background-color: white;
                    border: 1px solid #b4b4b4;
                    padding: 4px;
                    color: #000000;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                }
                QLineEdit {
                    background-color: white;
                    border: 1px solid #b4b4b4;
                    padding: 4px;
                    color: #000000;
                }
                QPushButton {
                    background-color: #e0e0e0;
                    border: 1px solid #b4b4b4;
                    padding: 6px 12px;
                    border-radius: 3px;
                    color: #000000;
                }
                QPushButton:hover {
                    background-color: #d0d0d0;
                }
                QPushButton:pressed {
                    background-color: #2a82da;
                    color: white;
                }
                QPushButton:checked {
                    background-color: #2a82da;
                    color: white;
                }
                QCheckBox {
                    color: #000000;
                }
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                }
                QGroupBox {
                    border: 1px solid #b4b4b4;
                    border-radius: 4px;
                    margin-top: 8px;
                    padding-top: 8px;
                    color: #000000;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    padding: 0 4px;
                    color: #000000;
                }
                QLabel {
                    color: #000000;
                }
                QSplitter {
                    background-color: #f0f0f0;
                }
                QSplitter::handle {
                    background-color: #d0d0d0;
                }
                QGraphicsView {
                    background-color: white;
                    border: 1px solid #b4b4b4;
                }
                /* Workspace panels */
                WorkspacePanel {
                    background-color: white;
                }
            """)

            # Also update pyqtgraph graphics widgets for light mode
            self._update_pyqtgraph_theme(is_dark=False)

    def _update_pyqtgraph_theme(self, is_dark: bool):
        """Update pyqtgraph widgets for the current theme."""
        import pyqtgraph as pg

        # Set global pyqtgraph options
        if is_dark:
            pg.setConfigOption('background', '#1e1e1e')
            pg.setConfigOption('foreground', '#d4d4d4')
        else:
            pg.setConfigOption('background', 'w')
            pg.setConfigOption('foreground', 'k')

        # Update all workspace panels through the workspace widget
        self._workspace.set_theme(is_dark)

    def _on_mode_changed(self, mode: str):
        """Handle mode change between Preview and Processing."""
        if mode == "preview":
            # Show analysis tools for preview mode
            self._analysis_toolbar.setVisible(True)
            self._analysis_dock.setVisible(False)  # Start hidden, user can show if needed
        elif mode == "processing":
            # Hide analysis tools in processing mode
            self._analysis_toolbar.setVisible(False)
            self._analysis_dock.setVisible(False)

    def _on_processing_requested(self, file_path: str, data):
        """Handle request to load file in processing mode."""
        # Load the file into processing mode
        processing_widget = self._mode_manager.get_processing_widget()
        if processing_widget and hasattr(processing_widget, 'load_file'):
            processing_widget.load_file(file_path, data)

    def _send_to_processing_mode(self):
        """Send current panel's file to Processing Mode."""
        if not isinstance(self._workspace.selected_panel, WorkspaceDisplayPanel):
            return

        panel = self._workspace.selected_panel
        if panel.current_data and panel.current_file:
            # Switch to processing mode and load the file
            self._mode_manager.switch_to_processing(panel.current_file, panel.current_data)
            self._statusbar.showMessage("Sent to Processing Mode")

    def _on_create_line_profile(self):
        """Handle create line profile button click."""
        # Show analysis dock and switch to line profile tab
        self._analysis_dock.setVisible(True)
        self._analysis_panel.show_line_profile_tab()

        # Get the selected panel and create a line profile on it
        if self._workspace and self._workspace.selected_panel:
            panel = self._workspace.selected_panel
            if isinstance(panel, WorkspaceDisplayPanel):
                if hasattr(panel, 'display_panel') and panel.display_panel:
                    panel.display_panel.create_line_profile()

    def _on_show_histogram(self):
        """Handle show histogram button click."""
        # Show analysis dock and switch to histogram tab
        self._analysis_dock.setVisible(True)
        self._analysis_panel.show_histogram_tab()

        # Update histogram for current panel
        if self._workspace and self._workspace.selected_panel:
            panel = self._workspace.selected_panel
            if isinstance(panel, WorkspaceDisplayPanel):
                self._update_histogram_for_panel(panel)

    def _on_create_measurement(self):
        """Handle create measurement button click."""
        # Get the selected panel and create a measurement on it
        if self._workspace and self._workspace.selected_panel:
            panel = self._workspace.selected_panel
            if isinstance(panel, WorkspaceDisplayPanel):
                if hasattr(panel, 'display_panel') and panel.display_panel:
                    display = panel.display_panel
                    display.create_measurement()
                    # Connect measurement signal to update toolbar (only if not already connected)
                    if hasattr(display, '_measurement_overlay') and display._measurement_overlay:
                        overlay_id = id(display._measurement_overlay)
                        if overlay_id not in self._measurement_connected_panels:
                            display._measurement_overlay.measurement_created.connect(self._on_measurement_updated)
                            self._measurement_connected_panels.add(overlay_id)

    def _on_clear_measurements(self):
        """Handle clear all measurements button click."""
        if self._workspace:
            for panel in self._workspace.panels:
                if isinstance(panel, WorkspaceDisplayPanel):
                    if hasattr(panel, 'display_panel') and panel.display_panel:
                        panel.display_panel.clear_measurements()
        self._measurement_toolbar.clear_distance()

    def _on_clear_last_measurement(self):
        """Handle clear last measurement button click."""
        if self._workspace and self._workspace.selected_panel:
            panel = self._workspace.selected_panel
            if isinstance(panel, WorkspaceDisplayPanel):
                if hasattr(panel, 'display_panel') and panel.display_panel:
                    panel.display_panel.clear_last_measurement()

    def _on_measurement_updated(self, measurement_data):
        """Handle measurement data updates from display panels."""
        from src.gui.measurement_overlay import MeasurementData
        if isinstance(measurement_data, MeasurementData):
            self._measurement_toolbar.update_distance(
                measurement_data.distance_px,
                measurement_data.distance_nm
            )

    def _on_toggle_measurement_labels(self, visible: bool):
        """Handle toggle labels checkbox from measurement toolbar."""
        # Toggle labels for all display panels
        if self._workspace:
            for panel in self._workspace.panels:
                if isinstance(panel, WorkspaceDisplayPanel):
                    if hasattr(panel, 'display_panel') and panel.display_panel:
                        dp = panel.display_panel
                        if hasattr(dp, '_measurement_overlay') and dp._measurement_overlay:
                            dp._measurement_overlay.set_labels_visible(visible)

    def _on_clear_analysis(self):
        """Handle clear analysis request."""
        # Clear analysis panel
        self._analysis_panel.clear_all()

        # Clear overlays in all display panels
        if self._workspace:
            for panel in self._workspace.panels:
                if isinstance(panel, WorkspaceDisplayPanel):
                    if hasattr(panel, 'display_panel') and panel.display_panel:
                        panel.display_panel.clear_analysis_overlays()

    def _on_line_width_changed(self, width):
        """Handle line profile width change from toolbar."""
        # Update width for all display panels with line profiles
        if self._workspace:
            for panel in self._workspace.panels:
                if isinstance(panel, WorkspaceDisplayPanel):
                    if hasattr(panel, 'display_panel') and panel.display_panel:
                        display = panel.display_panel
                        if hasattr(display, '_line_profile_overlay') and display._line_profile_overlay:
                            display._line_profile_overlay.set_line_width(width)

    def _on_unit_changed(self, unit):
        """Handle unit change from toolbar."""
        # Update unit in the line profile widget
        if self._analysis_panel and hasattr(self._analysis_panel, '_line_profile_widget'):
            self._analysis_panel._line_profile_widget.set_unit(unit)

    def _on_export_plot(self):
        """Handle export plot request from toolbar."""
        # Export the line profile plot
        if self._analysis_panel and hasattr(self._analysis_panel, '_line_profile_widget'):
            self._analysis_panel._line_profile_widget.export_plot()

    def _on_line_profile_created(self, profile_data):
        """Handle line profile creation from display panels."""
        from src.gui.line_profile_overlay import LineProfileData

        if isinstance(profile_data, LineProfileData) and self._analysis_panel:
            # Add to analysis panel - include both 'distances' array and 'distance' total
            data_dict = {
                'start': profile_data.start_point,
                'end': profile_data.end_point,
                'values': profile_data.values,
                'distances': profile_data.distances,  # Array of distances for plotting
                'distance': profile_data.distances[-1] if len(profile_data.distances) > 0 else 0,  # Total distance
                'unit': profile_data.unit,
                'width': profile_data.width if hasattr(profile_data, 'width') else 1,
                'calibration': profile_data.calibration if hasattr(profile_data, 'calibration') else None
            }
            self._analysis_panel.add_line_profile(profile_data.profile_id, data_dict)

            # Connect reference marker signals if not already connected
            if hasattr(self._analysis_panel, '_line_profile_widget'):
                line_widget = self._analysis_panel._line_profile_widget

                # Store connections as attributes to track them
                if hasattr(self, '_ref_marker_connection'):
                    try:
                        line_widget.reference_marker_added.disconnect(self._ref_marker_connection)
                    except (RuntimeError, TypeError):
                        pass

                if hasattr(self, '_ref_clear_connection'):
                    try:
                        line_widget.reference_markers_cleared.disconnect(self._ref_clear_connection)
                    except (RuntimeError, TypeError):
                        pass

                # Connect to the display that created this profile
                if self._current_display_panel:
                    self._ref_marker_connection = self._on_reference_marker_added
                    self._ref_clear_connection = self._on_reference_markers_cleared
                    line_widget.reference_marker_added.connect(self._ref_marker_connection)
                    line_widget.reference_markers_cleared.connect(self._ref_clear_connection)

    def _on_reference_marker_added(self, index: int, image_x: float, image_y: float):
        """Handle reference marker addition from the line profile widget."""
        # Add reference marker on the current display
        if self._current_display_panel and hasattr(self._current_display_panel, '_line_profile_overlay'):
            self._current_display_panel._line_profile_overlay.add_reference_marker(image_x, image_y, index)

    def _on_reference_markers_cleared(self):
        """Handle clearing of all reference markers."""
        # Clear all reference markers on the current display
        if self._current_display_panel and hasattr(self._current_display_panel, '_line_profile_overlay'):
            self._current_display_panel._line_profile_overlay.clear_reference_markers()

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

            # Connect frame_changed to update histogram when frame changes
            panel.frame_changed.connect(lambda frame: self._on_frame_changed_in_panel(panel, frame))

            # Apply current theme to new panel
            if hasattr(panel, 'set_theme'):
                panel.set_theme(self._is_dark_mode)

            if hasattr(panel, 'display_panel') and panel.display_panel:
                display = panel.display_panel
                if hasattr(display, '_graphics_widget'):
                    bg_color = 'k' if self._is_dark_mode else 'w'
                    display._graphics_widget.setBackground(bg_color)

                # Connect line profile signals to analysis panel
                if hasattr(display, '_line_profile_overlay') and display._line_profile_overlay:
                    display._line_profile_overlay.profile_created.connect(self._on_line_profile_created)

    def _on_panel_removed(self, panel: WorkspacePanel):
        """Handle panel removal."""
        self._update_export_actions()

    def _on_panel_selected(self, panel: WorkspacePanel):
        """Handle panel selection."""
        # Track the current display panel
        if isinstance(panel, WorkspaceDisplayPanel):
            self._current_display_panel = panel.display_panel if hasattr(panel, 'display_panel') else panel
            # Update metadata panel if it has data
            if panel.current_data:
                self._metadata_panel.set_data(panel.current_data)
                self._statusbar.showMessage(panel.current_data.get_summary())
                # Update histogram for the selected panel
                self._update_histogram_for_panel(panel)
                # Update line profile for the selected panel
                self._update_line_profile_for_panel(panel)
        else:
            self._current_display_panel = None
            self._metadata_panel.clear()
            # Clear analysis widgets when no display panel is selected
            if hasattr(self, '_analysis_panel'):
                self._analysis_panel._histogram_widget.clear_histogram()
                self._analysis_panel._line_profile_widget.clear_plot()

        self._update_export_actions()

    def _update_unified_controls(self, panel: WorkspacePanel):
        """Update unified control panel for the selected panel."""
        if isinstance(panel, WorkspaceDisplayPanel):
            self._unified_controls.set_current_panel(panel)
        else:
            self._unified_controls.set_current_panel(None)

    def _on_frame_changed_in_panel(self, panel: WorkspaceDisplayPanel, frame: int):
        """Handle frame change in a panel - update histogram if this is the selected panel."""
        if panel == self._workspace.selected_panel:
            self._update_histogram_for_panel(panel)

    def _update_histogram_for_panel(self, panel: WorkspaceDisplayPanel):
        """Update the histogram display for the given panel."""
        if not hasattr(self, '_analysis_panel'):
            return

        if not isinstance(panel, WorkspaceDisplayPanel) or not panel.current_data:
            self._analysis_panel._histogram_widget.clear_histogram()
            return

        # Get current frame data
        data = panel.current_data
        display_panel = panel.display_panel if hasattr(panel, 'display_panel') else None

        if display_panel:
            current_frame = display_panel.current_frame
            frame_data = data.get_frame(current_frame)

            # Get display range from the panel
            display_range = panel.get_display_range()

            # Update the histogram
            self._analysis_panel.update_histogram(frame_data, display_range)

    def _update_line_profile_for_panel(self, panel: WorkspaceDisplayPanel):
        """Update the line profile display for the given panel."""
        if not hasattr(self, '_analysis_panel'):
            return

        if not isinstance(panel, WorkspaceDisplayPanel) or not panel.current_data:
            self._analysis_panel._line_profile_widget.clear_plot()
            return

        # Get the display panel and its line profile overlay
        display_panel = panel.display_panel if hasattr(panel, 'display_panel') else None

        if display_panel and hasattr(display_panel, '_line_profile_overlay'):
            overlay = display_panel._line_profile_overlay
            if overlay and overlay.has_active_profile():
                # Refresh the profile to re-emit the data
                overlay.refresh_profile()
            else:
                # No active line profile on this panel, clear the widget
                self._analysis_panel._line_profile_widget.clear_plot()

    def _on_layout_changed(self):
        """Handle workspace layout change."""
        self._statusbar.showMessage(f"Workspace: {len(self._workspace.panels)} panels", 2000)

    def _on_data_loaded_in_panel(self, panel: WorkspaceDisplayPanel, data: NHDFData):
        """Handle data loaded in a specific panel."""
        if panel == self._workspace.selected_panel:
            self._metadata_panel.set_data(data)
            self._statusbar.showMessage(data.get_summary())
            # Update histogram when data is loaded
            self._update_histogram_for_panel(panel)
            # Re-sync unified controls to update subscan checkbox state
            self._update_unified_controls(panel)

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
            "EM Files (*.nhdf *.dm3 *.dm4);;nhdf Files (*.nhdf);;DM Files (*.dm3 *.dm4);;All Files (*)"
        )
        if file_path:
            self._load_file_in_current_panel(pathlib.Path(file_path))

    def _on_open_in_new_panel(self):
        """Open a file in a new panel."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open nhdf File in New Panel",
            str(self._file_browser.current_path or pathlib.Path.home()),
            "EM Files (*.nhdf *.dm3 *.dm4);;nhdf Files (*.nhdf);;DM Files (*.dm3 *.dm4);;All Files (*)"
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
        # Safety check - ensure panel is still valid
        try:
            # Test if panel is still valid by accessing a property
            panel_id = panel.panel_id
        except RuntimeError:
            # Panel was deleted, find the selected panel instead
            if self._workspace.selected_panel:
                panel = self._workspace.selected_panel
            else:
                return  # No valid panel to load into

        # Convert to WorkspaceDisplayPanel if needed
        if not isinstance(panel, WorkspaceDisplayPanel):
            # Create new display panel
            new_panel = WorkspaceDisplayPanel(panel.panel_id)
            new_panel.close_requested.connect(self._workspace._handle_panel_close)
            new_panel.split_requested.connect(self._workspace._handle_panel_split)
            new_panel.file_dropped.connect(self._workspace._handle_file_dropped)
            new_panel.data_loaded.connect(lambda data: self._on_data_loaded_in_panel(new_panel, data))

            # Apply current theme to the new panel
            new_panel.set_theme(self._is_dark_mode)

            # Get parent and index before modifying
            try:
                parent = panel.parent()
            except RuntimeError:
                # Panel is already deleted, abort
                return

            # Update references BEFORE removing from parent
            if panel in self._workspace.panels:
                idx = self._workspace.panels.index(panel)
                self._workspace.panels[idx] = new_panel

                # If this was the selected panel, update selection reference
                if self._workspace.selected_panel == panel:
                    self._workspace.selected_panel = new_panel

                # Now replace in the UI
                from PySide6.QtWidgets import QSplitter
                if isinstance(parent, QSplitter):
                    index = parent.indexOf(panel)
                    panel.setParent(None)
                    parent.insertWidget(index, new_panel)
                elif hasattr(self._workspace, 'layout'):
                    self._workspace.layout.removeWidget(panel)
                    self._workspace.layout.addWidget(new_panel)

                # Delete old panel after all references are updated
                panel.deleteLater()

                # Use the new panel for loading
                panel = new_panel
            else:
                # Panel not in list, something went wrong
                return

        # Load file
        try:
            self._statusbar.showMessage(f"Loading {path.name}...")
            QApplication.processEvents()

            # Check if already loaded
            str_path = str(path)
            if str_path not in self._loaded_files:
                data = read_em_file(path)
                self._loaded_files[str_path] = data
            else:
                data = self._loaded_files[str_path]

            panel.set_data(data, str(path))

            # Connect line profile signal if not already connected
            if isinstance(panel, WorkspaceDisplayPanel):
                if hasattr(panel, 'display_panel') and panel.display_panel:
                    display = panel.display_panel
                    if hasattr(display, '_line_profile_overlay') and display._line_profile_overlay:
                        # Disconnect any existing connections first to avoid duplicates
                        try:
                            display._line_profile_overlay.profile_created.disconnect()
                        except:
                            pass
                        # Connect the signal
                        display._line_profile_overlay.profile_created.connect(self._on_line_profile_created)

            # Select the panel (this will trigger updates)
            self._workspace._select_panel(panel)

            # Force update of unified controls
            self._update_unified_controls(panel)
            # Also update metadata panel
            self._metadata_panel.set_data(data)
            self._statusbar.showMessage(data.get_summary())

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

        # Enable "Send to Processing" if current panel has data
        if hasattr(self, '_send_to_processing_action'):
            self._send_to_processing_action.setEnabled(has_data)

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