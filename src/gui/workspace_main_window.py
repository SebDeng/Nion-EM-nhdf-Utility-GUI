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
from PySide6.QtCore import Qt, Signal, QSettings, QTimer
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
from src.gui.workspace_manager import WorkspaceManager, SessionManager, WorkspaceState
from src.gui.unified_control_panel import UnifiedControlPanel
from src.gui.view_mode_toolbar import ViewModeToolBar
from src.gui.mode_manager import ModeManager
from src.gui.preview_mode import AnalysisToolBar
from src.gui.preview_mode.analysis_panel import AnalysisResultsPanel
from src.gui.measurement_toolbar import MeasurementToolBar
from src.gui.dose_calculator import DoseCalculatorDialog
from src.gui.material_calculator import MaterialCalculatorDialog
from src.gui.workspace_tab_bar import WorkspaceTabBar


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

        # Initialize workspace and session managers
        self._workspace_manager = WorkspaceManager(self)
        self._session_manager = SessionManager(self._workspace_manager, self)

        self._setup_ui()
        self._setup_menus()
        self._setup_statusbar()
        self._connect_signals()
        self._restore_state()
        self._load_default_layouts()

        # Initialize first workspace
        self._init_default_workspace()

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
        self._measurement_toolbar.create_polygon.connect(self._on_create_polygon)
        self._measurement_toolbar.create_pipette.connect(self._on_create_pipette)
        self._measurement_toolbar.create_memo.connect(self._on_create_memo)
        self._measurement_toolbar.open_dose_calculator.connect(self._on_show_dose_calculator)
        self._measurement_toolbar.clear_all.connect(self._on_clear_measurements)
        self._measurement_toolbar.clear_last.connect(self._on_clear_last_measurement)
        self._measurement_toolbar.delete_selected.connect(self._on_delete_selected_measurement)
        self._measurement_toolbar.toggle_labels.connect(self._on_toggle_measurement_labels)
        self._measurement_toolbar.toggle_handles.connect(self._on_toggle_measurement_handles)
        self._measurement_toolbar.font_size_changed.connect(self._on_measurement_font_size_changed)
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
        self._analysis_toolbar.show_frame_statistics.connect(self._on_show_frame_statistics)
        central_layout.addWidget(self._analysis_toolbar)

        # Create mode manager with tabbed workspace/processing
        # Use WorkspaceDisplayPanel as the panel factory so empty panels can have memos
        self._mode_manager = ModeManager(self, panel_factory=lambda: WorkspaceDisplayPanel())
        self._mode_manager.mode_changed.connect(self._on_mode_changed)
        self._mode_manager.processing_requested.connect(self._on_processing_requested)
        central_layout.addWidget(self._mode_manager.get_widget(), 1)  # Give tabs the stretch factor

        # Keep reference to workspace for compatibility
        self._workspace = self._mode_manager.get_preview_widget()

        # Add workspace tab bar at the bottom (Excel-like tabs for switching workspaces)
        self._workspace_tab_bar = WorkspaceTabBar()
        self._workspace_tab_bar.setFixedHeight(36)
        central_layout.addWidget(self._workspace_tab_bar)

        self.setCentralWidget(central_widget)

        # Left dock - File Browser
        self._file_browser_dock = QDockWidget("File Browser", self)
        self._file_browser_dock.setObjectName("FileBrowserDock")
        self._file_browser = FileBrowserPanel()
        self._file_browser_dock.setWidget(self._file_browser)
        self._file_browser_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._file_browser_dock.setMinimumWidth(250)
        self.addDockWidget(Qt.LeftDockWidgetArea, self._file_browser_dock)

        # Hole Pairing Panel dock (below file browser)
        from src.gui.hole_pairing_panel import HolePairingPanel

        self._hole_pairing_dock = QDockWidget("Hole Pairing", self)
        self._hole_pairing_dock.setObjectName("HolePairingDock")
        self._hole_pairing_panel = HolePairingPanel()
        self._hole_pairing_dock.setWidget(self._hole_pairing_panel)
        self._hole_pairing_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._hole_pairing_dock.setMinimumWidth(280)
        self.addDockWidget(Qt.LeftDockWidgetArea, self._hole_pairing_dock)

        # Stack below file browser (vertical split)
        self.splitDockWidget(self._file_browser_dock, self._hole_pairing_dock, Qt.Vertical)
        self._hole_pairing_dock.setVisible(False)  # Start hidden

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

        # Session menu items
        new_session_action = QAction("New &Session", self)
        new_session_action.triggered.connect(self._on_new_session)
        file_menu.addAction(new_session_action)

        open_session_action = QAction("Open S&ession...", self)
        open_session_action.triggered.connect(self._on_open_session)
        file_menu.addAction(open_session_action)

        save_session_action = QAction("&Save Session", self)
        save_session_action.setShortcut(QKeySequence("Ctrl+S"))
        save_session_action.triggered.connect(self._on_save_session)
        file_menu.addAction(save_session_action)

        save_session_as_action = QAction("Save Session &As...", self)
        save_session_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_session_as_action.triggered.connect(self._on_save_session_as)
        file_menu.addAction(save_session_as_action)

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
        view_menu.addAction(self._hole_pairing_dock.toggleViewAction())

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

        # Workspaces submenu (for multi-workspace management)
        self._workspaces_menu = view_menu.addMenu("W&orkspaces")
        self._setup_workspaces_menu()

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

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        dose_calc_action = QAction("&Electron Dose Calculator...", self)
        dose_calc_action.setShortcut(QKeySequence("Ctrl+D"))
        dose_calc_action.triggered.connect(self._on_show_dose_calculator)
        tools_menu.addAction(dose_calc_action)

        material_calc_action = QAction("&Material Atom Calculator...", self)
        material_calc_action.setShortcut(QKeySequence("Ctrl+M"))
        material_calc_action.triggered.connect(self._on_show_material_calculator)
        tools_menu.addAction(material_calc_action)

        tools_menu.addSeparator()

        hole_pairing_action = QAction("&Hole Pairing Analysis...", self)
        hole_pairing_action.setShortcut(QKeySequence("Ctrl+Shift+H"))
        hole_pairing_action.triggered.connect(self._on_show_hole_pairing)
        tools_menu.addAction(hole_pairing_action)

        speckmann_action = QAction("&Speckmann Analysis...", self)
        speckmann_action.setShortcut(QKeySequence("Ctrl+Shift+K"))
        speckmann_action.triggered.connect(self._on_show_speckmann_analysis)
        tools_menu.addAction(speckmann_action)

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

        # Workspace tab bar signals
        self._workspace_tab_bar.tab_selected.connect(self._on_tab_bar_tab_selected)
        self._workspace_tab_bar.new_workspace_requested.connect(self._on_new_workspace)
        self._workspace_tab_bar.close_workspace_requested.connect(self._on_tab_bar_close_workspace)
        self._workspace_tab_bar.rename_workspace_requested.connect(self._on_tab_bar_rename_workspace)
        self._workspace_tab_bar.clone_workspace_requested.connect(self._on_tab_bar_clone_workspace)
        self._workspace_tab_bar.tabs_reordered.connect(self._on_tabs_reordered)

        # Workspace manager signals - update tab bar when workspaces change
        self._workspace_manager.workspaces_changed.connect(self._sync_tab_bar_with_workspaces)

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

        # Update workspace tab bar theme
        if hasattr(self, '_workspace_tab_bar'):
            self._workspace_tab_bar.set_theme(is_dark)

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
        if panel.current_data and panel.current_file_path:
            # Switch to processing mode and load the file
            self._mode_manager.switch_to_processing(panel.current_file_path, panel.current_data)
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

    def _on_show_frame_statistics(self):
        """Handle show frame statistics button click."""
        # Show analysis dock and switch to frame statistics tab
        self._analysis_dock.setVisible(True)
        self._analysis_panel.show_frame_statistics_tab()

        # Connect widget signals for ROI control
        frame_stats_widget = self._analysis_panel.get_frame_statistics_widget()
        # Disconnect first to avoid duplicate connections
        try:
            frame_stats_widget.roi_mode_requested.disconnect(self._on_frame_stats_roi_requested)
            frame_stats_widget.roi_clear_requested.disconnect(self._on_frame_stats_roi_clear)
            frame_stats_widget.export_requested.disconnect(self._on_frame_stats_export)
        except (TypeError, RuntimeError):
            pass  # Not connected yet
        frame_stats_widget.roi_mode_requested.connect(self._on_frame_stats_roi_requested)
        frame_stats_widget.roi_clear_requested.connect(self._on_frame_stats_roi_clear)
        frame_stats_widget.export_requested.connect(self._on_frame_stats_export)

        # Update statistics for current panel
        if self._workspace and self._workspace.selected_panel:
            panel = self._workspace.selected_panel
            if isinstance(panel, WorkspaceDisplayPanel):
                self._update_frame_statistics_for_panel(panel)

    def _on_frame_stats_roi_requested(self):
        """Handle ROI creation request from frame statistics widget."""
        if self._workspace and self._workspace.selected_panel:
            panel = self._workspace.selected_panel
            if isinstance(panel, WorkspaceDisplayPanel):
                if hasattr(panel, 'display_panel') and panel.display_panel:
                    display = panel.display_panel
                    display.create_frame_statistics_roi()
                    # Connect ROI update signal
                    try:
                        display.frame_stats_roi_changed.disconnect(self._on_frame_stats_roi_changed)
                    except (TypeError, RuntimeError):
                        pass
                    display.frame_stats_roi_changed.connect(self._on_frame_stats_roi_changed)

    def _on_frame_stats_roi_clear(self):
        """Handle ROI clear request from frame statistics widget."""
        if self._workspace and self._workspace.selected_panel:
            panel = self._workspace.selected_panel
            if isinstance(panel, WorkspaceDisplayPanel):
                if hasattr(panel, 'display_panel') and panel.display_panel:
                    panel.display_panel.clear_frame_statistics_roi()
                    # Update statistics without ROI
                    self._update_frame_statistics_for_panel(panel)

    def _on_frame_stats_roi_changed(self, roi_data):
        """Handle ROI change - recompute statistics."""
        if self._workspace and self._workspace.selected_panel:
            panel = self._workspace.selected_panel
            if isinstance(panel, WorkspaceDisplayPanel):
                self._update_frame_statistics_for_panel(panel)

    def _on_frame_stats_export(self):
        """Handle frame statistics export request."""
        from src.gui.frame_statistics_export_dialog import FrameStatisticsExportDialog

        frame_stats_widget = self._analysis_panel.get_frame_statistics_widget()
        stats_data = frame_stats_widget.get_current_data()

        if stats_data is None:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Data", "No frame statistics data to export.")
            return

        # Add file name if available
        if self._workspace and self._workspace.selected_panel:
            panel = self._workspace.selected_panel
            if isinstance(panel, WorkspaceDisplayPanel) and panel.current_file_path:
                import os
                stats_data['file_name'] = os.path.basename(panel.current_file_path)

        dialog = FrameStatisticsExportDialog(stats_data, self)
        dialog.exec()

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
                    self._connect_measurement_signals(display)

    def _on_create_polygon(self):
        """Handle create polygon button click for area measurement."""
        if self._workspace and self._workspace.selected_panel:
            panel = self._workspace.selected_panel
            if isinstance(panel, WorkspaceDisplayPanel):
                if hasattr(panel, 'display_panel') and panel.display_panel:
                    display = panel.display_panel
                    display.create_polygon_area()
                    # Connect measurement signals to update toolbar
                    self._connect_measurement_signals(display)

    def _on_create_pipette(self):
        """Handle create pipette button click for auto-detecting polygon regions."""
        if self._workspace and self._workspace.selected_panel:
            panel = self._workspace.selected_panel
            if isinstance(panel, WorkspaceDisplayPanel):
                if hasattr(panel, 'display_panel') and panel.display_panel:
                    display = panel.display_panel
                    display.activate_pipette_mode()
                    # Connect measurement signals to update toolbar
                    self._connect_measurement_signals(display)

    def _on_create_memo(self):
        """Handle create memo button click."""
        if self._workspace and self._workspace.selected_panel:
            panel = self._workspace.selected_panel
            if isinstance(panel, WorkspaceDisplayPanel):
                if hasattr(panel, 'display_panel') and panel.display_panel:
                    display = panel.display_panel
                    if not display.create_memo():
                        # Max memos reached
                        from PySide6.QtWidgets import QMessageBox
                        QMessageBox.information(
                            self, "Memo Limit",
                            "Maximum of 2 memos per panel reached.\n"
                            "Close an existing memo to add a new one."
                        )

    def _connect_measurement_signals(self, display):
        """Connect measurement signals from display panel if not already connected."""
        if hasattr(display, '_measurement_overlay') and display._measurement_overlay:
            overlay_id = id(display._measurement_overlay)
            if overlay_id not in self._measurement_connected_panels:
                display._measurement_overlay.measurement_created.connect(self._on_measurement_updated)
                display._measurement_overlay.polygon_area_created.connect(self._on_polygon_area_updated)
                display._measurement_overlay.total_polygon_area_changed.connect(self._on_total_polygon_area_updated)
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

    def _on_delete_selected_measurement(self):
        """Handle delete selected measurement button click."""
        # Try to delete selected measurement from any panel
        if self._workspace:
            for panel in self._workspace.panels:
                if isinstance(panel, WorkspaceDisplayPanel):
                    if hasattr(panel, 'display_panel') and panel.display_panel:
                        dp = panel.display_panel
                        if hasattr(dp, '_measurement_overlay') and dp._measurement_overlay:
                            overlay = dp._measurement_overlay
                            if overlay.has_selection():
                                if overlay.delete_selected():
                                    # Update measurement count
                                    count = overlay.get_total_measurement_count()
                                    self._measurement_toolbar.set_measurement_count(count)
                                    return  # Deleted something, stop looking

    def _on_measurement_updated(self, measurement_data):
        """Handle measurement data updates from display panels."""
        from src.gui.measurement_overlay import MeasurementData
        if isinstance(measurement_data, MeasurementData):
            self._measurement_toolbar.update_distance(
                measurement_data.distance_px,
                measurement_data.distance_nm
            )

    def _on_polygon_area_updated(self, polygon_data):
        """Handle polygon area data updates from display panels."""
        from src.gui.measurement_overlay import PolygonAreaData
        if isinstance(polygon_data, PolygonAreaData):
            self._measurement_toolbar.update_area(
                polygon_data.area_px,
                polygon_data.area_nm2
            )

    def _on_total_polygon_area_updated(self, area_px: float, area_nm2):
        """Handle total polygon area updates from display panels."""
        self._measurement_toolbar.update_total_polygon_area(area_px, area_nm2)

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

    def _on_toggle_measurement_handles(self, visible: bool):
        """Handle toggle handles checkbox from measurement toolbar.

        PERFORMANCE: Hiding polygon handles dramatically improves pan/zoom speed
        when many polygons are present.
        """
        if self._workspace:
            for panel in self._workspace.panels:
                if isinstance(panel, WorkspaceDisplayPanel):
                    if hasattr(panel, 'display_panel') and panel.display_panel:
                        dp = panel.display_panel
                        if hasattr(dp, '_measurement_overlay') and dp._measurement_overlay:
                            overlay = dp._measurement_overlay
                            if visible:
                                overlay.show_all_polygon_handles()
                            else:
                                overlay.hide_all_polygon_handles()

    def _on_measurement_font_size_changed(self, size: int):
        """Handle font size change from measurement toolbar."""
        # Update font size for all display panels
        if self._workspace:
            for panel in self._workspace.panels:
                if isinstance(panel, WorkspaceDisplayPanel):
                    if hasattr(panel, 'display_panel') and panel.display_panel:
                        dp = panel.display_panel
                        if hasattr(dp, '_measurement_overlay') and dp._measurement_overlay:
                            dp._measurement_overlay.set_label_font_size(size)

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
            # Update total polygon area for the selected panel
            self._update_total_polygon_area_for_panel(panel)
        else:
            self._current_display_panel = None
            self._metadata_panel.clear()
            # Clear analysis widgets when no display panel is selected
            if hasattr(self, '_analysis_panel'):
                self._analysis_panel._histogram_widget.clear_histogram()
                self._analysis_panel._line_profile_widget.clear_plot()
            # Clear total polygon area display
            self._measurement_toolbar.update_total_polygon_area(0, None)

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

    def _update_total_polygon_area_for_panel(self, panel: WorkspaceDisplayPanel):
        """Update the total polygon area display for the given panel."""
        if not isinstance(panel, WorkspaceDisplayPanel):
            self._measurement_toolbar.update_total_polygon_area(0, None)
            return

        # Get the display panel and measurement overlay
        display_panel = panel.display_panel if hasattr(panel, 'display_panel') else None
        if display_panel and hasattr(display_panel, '_measurement_overlay') and display_panel._measurement_overlay:
            area_px, area_nm2 = display_panel._measurement_overlay.get_total_polygon_area()
            self._measurement_toolbar.update_total_polygon_area(area_px, area_nm2)
        else:
            self._measurement_toolbar.update_total_polygon_area(0, None)

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

    def _update_frame_statistics_for_panel(self, panel: WorkspaceDisplayPanel):
        """Update the frame statistics display for the given panel."""
        import numpy as np

        if not hasattr(self, '_analysis_panel'):
            return

        if not isinstance(panel, WorkspaceDisplayPanel) or not panel.current_data:
            self._analysis_panel._frame_statistics_widget.clear_statistics()
            return

        data = panel.current_data
        num_frames = data.num_frames

        if num_frames < 2:
            # Single frame - show message in widget
            self._analysis_panel._frame_statistics_widget.clear_statistics()
            return

        # Get ROI bounds if available
        roi_bounds = None
        display_panel = panel.display_panel if hasattr(panel, 'display_panel') else None
        if display_panel:
            roi_bounds = display_panel.get_frame_statistics_roi_bounds()

        # Compute statistics for all frames
        stats_data = self._compute_frame_statistics(data, roi_bounds)

        # Add metadata
        if panel.current_file_path:
            import os
            stats_data['file_name'] = os.path.basename(panel.current_file_path)

        # Update widget
        self._analysis_panel.update_frame_statistics(stats_data)

    def _compute_frame_statistics(self, data, roi_bounds=None):
        """
        Compute statistics for all frames in the data.

        Args:
            data: NHDFData object
            roi_bounds: Optional tuple (x, y, w, h) for ROI

        Returns:
            Dictionary with frame statistics
        """
        import numpy as np

        num_frames = data.num_frames

        means = np.zeros(num_frames)
        sums = np.zeros(num_frames)
        stds = np.zeros(num_frames)
        mins = np.zeros(num_frames)
        maxs = np.zeros(num_frames)

        for i in range(num_frames):
            frame = data.get_frame(i)

            # Apply ROI if present
            if roi_bounds is not None:
                x, y, w, h = roi_bounds
                x, y, w, h = int(x), int(y), int(w), int(h)
                # Clip to frame bounds
                x = max(0, x)
                y = max(0, y)
                if x + w > frame.shape[1]:
                    w = frame.shape[1] - x
                if y + h > frame.shape[0]:
                    h = frame.shape[0] - y
                if w > 0 and h > 0:
                    frame = frame[y:y+h, x:x+w]

            # Compute statistics (handle NaN values)
            means[i] = np.nanmean(frame)
            sums[i] = np.nansum(frame)
            stds[i] = np.nanstd(frame)
            mins[i] = np.nanmin(frame)
            maxs[i] = np.nanmax(frame)

        return {
            'frame_numbers': np.arange(num_frames),
            'mean': means,
            'sum': sums,
            'std': stds,
            'min': mins,
            'max': maxs,
            'roi_bounds': roi_bounds,
            'total_frames': num_frames
        }

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
            # Use QTimer.singleShot to defer sync until after Qt event loop processes
            # This ensures the display panel has fully updated its state
            QTimer.singleShot(0, lambda: self._unified_controls.set_current_panel(panel, force_sync=True))

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
            "Open EM File",
            str(self._file_browser.current_path or pathlib.Path.home()),
            "EM Files (*.nhdf *.ndata1 *.dm3 *.dm4);;nhdf Files (*.nhdf);;ndata1 Files (*.ndata1);;DM Files (*.dm3 *.dm4);;All Files (*)"
        )
        if file_path:
            self._load_file_in_current_panel(pathlib.Path(file_path))

    def _on_open_in_new_panel(self):
        """Open a file in a new panel."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open EM File in New Panel",
            str(self._file_browser.current_path or pathlib.Path.home()),
            "EM Files (*.nhdf *.ndata1 *.dm3 *.dm4);;nhdf Files (*.nhdf);;ndata1 Files (*.ndata1);;DM Files (*.dm3 *.dm4);;All Files (*)"
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

    def _on_show_dose_calculator(self):
        """Show the electron dose calculator dialog."""
        # Get current data and frame index from selected panel
        current_data = None
        frame_index = 0
        if isinstance(self._workspace.selected_panel, WorkspaceDisplayPanel):
            current_data = self._workspace.selected_panel.current_data
            frame_index = self._workspace.selected_panel.display_panel.current_frame

        dialog = DoseCalculatorDialog(current_data, frame_index=frame_index, parent=self)
        dialog.add_to_panel.connect(self._on_add_dose_to_panel)
        dialog.exec()

    def _on_add_dose_to_panel(self, dose_data: dict, use_angstrom: bool):
        """Add dose calculation result as a floating label on the panel."""
        if not isinstance(self._workspace.selected_panel, WorkspaceDisplayPanel):
            QMessageBox.warning(
                self,
                "No Panel Selected",
                "Please select a display panel first."
            )
            return

        panel = self._workspace.selected_panel
        if not panel.display_panel.can_add_dose_label():
            QMessageBox.warning(
                self,
                "Limit Reached",
                "Maximum of 2 dose labels per panel. Remove one to add another."
            )
            return

        panel.display_panel.add_dose_label(dose_data, use_angstrom)

    def _on_show_material_calculator(self):
        """Show the material atom calculator dialog."""
        # Get frame area from selected panel if available
        frame_area_nm2 = None
        if isinstance(self._workspace.selected_panel, WorkspaceDisplayPanel):
            current_data = self._workspace.selected_panel.current_data
            if current_data:
                # Try to get frame area from dose calculation
                dose_result = current_data.calculate_electron_dose()
                if dose_result:
                    frame_area_nm2 = dose_result.get('frame_area_nm2')

        dialog = MaterialCalculatorDialog(frame_area_nm2, parent=self)
        dialog.add_to_panel.connect(self._on_add_material_to_panel)
        dialog.exec()

    def _on_add_material_to_panel(self, material_data: dict):
        """Add material calculation result as a floating label on the panel."""
        if not isinstance(self._workspace.selected_panel, WorkspaceDisplayPanel):
            QMessageBox.warning(
                self,
                "No Panel Selected",
                "Please select a display panel first."
            )
            return

        panel = self._workspace.selected_panel
        if not panel.display_panel.can_add_material_label():
            QMessageBox.warning(
                self,
                "Limit Reached",
                "Maximum of 2 material labels per panel. Remove one to add another."
            )
            return

        panel.display_panel.add_material_label(material_data)

    def _on_show_hole_pairing(self):
        """Show the hole pairing panel for vacancy diffusion analysis."""
        self._hole_pairing_dock.setVisible(True)
        self._hole_pairing_panel.set_workspace(self._workspace)
        self._hole_pairing_panel.set_main_window(self)
        self._hole_pairing_panel._refresh_panel_list()

    def _on_show_speckmann_analysis(self):
        """Show the Speckmann thermal diffusion analysis dialog."""
        from .speckmann_analysis_dialog import SpeckmannAnalysisDialog
        dialog = SpeckmannAnalysisDialog(workspace=self._workspace, parent=self)
        dialog.exec()

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

    # --- Workspace Management Methods ---

    def _init_default_workspace(self):
        """Initialize the first default workspace."""
        if self._workspace_manager.workspace_count == 0:
            workspace = self._workspace_manager.new_workspace("Workspace 1")
            self._workspace_manager.set_current_workspace(workspace.uuid)
            # Initialize tab bar with the first workspace
            self._sync_tab_bar_with_workspaces()

    def _setup_workspaces_menu(self):
        """Set up the Workspaces submenu with workspace list and actions."""
        self._workspaces_menu.clear()

        # New workspace action
        new_ws_action = QAction("&New Workspace", self)
        new_ws_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        new_ws_action.triggered.connect(self._on_new_workspace)
        self._workspaces_menu.addAction(new_ws_action)

        # Clone workspace action
        clone_ws_action = QAction("&Clone Current Workspace", self)
        clone_ws_action.triggered.connect(self._on_clone_workspace)
        self._workspaces_menu.addAction(clone_ws_action)

        # Rename workspace action
        rename_ws_action = QAction("&Rename Current Workspace...", self)
        rename_ws_action.triggered.connect(self._on_rename_workspace)
        self._workspaces_menu.addAction(rename_ws_action)

        # Delete workspace action
        delete_ws_action = QAction("&Delete Current Workspace", self)
        delete_ws_action.triggered.connect(self._on_delete_workspace)
        self._workspaces_menu.addAction(delete_ws_action)

        self._workspaces_menu.addSeparator()

        # Navigation actions
        next_ws_action = QAction("Next &Workspace", self)
        next_ws_action.setShortcut(QKeySequence("Ctrl+Tab"))
        next_ws_action.triggered.connect(self._on_next_workspace)
        self._workspaces_menu.addAction(next_ws_action)

        prev_ws_action = QAction("&Previous Workspace", self)
        prev_ws_action.setShortcut(QKeySequence("Ctrl+Shift+Tab"))
        prev_ws_action.triggered.connect(self._on_previous_workspace)
        self._workspaces_menu.addAction(prev_ws_action)

        self._workspaces_menu.addSeparator()

        # Add workspace list
        self._update_workspace_list_menu()

    def _update_workspace_list_menu(self):
        """Update the workspace list in the menu."""
        # Find the separator after the navigation items
        actions = self._workspaces_menu.actions()

        # Remove existing workspace entries (after the second separator)
        separator_count = 0
        for action in actions[:]:
            if action.isSeparator():
                separator_count += 1
            elif separator_count >= 2:
                self._workspaces_menu.removeAction(action)

        # Add current workspaces
        current_uuid = self._workspace_manager.current_workspace_uuid
        for i, workspace in enumerate(self._workspace_manager.workspaces):
            action = QAction(workspace.name, self)
            action.setCheckable(True)
            action.setChecked(workspace.uuid == current_uuid)

            # Add shortcut for first 9 workspaces
            if i < 9:
                action.setShortcut(QKeySequence(f"Alt+{i + 1}"))

            # Connect with workspace UUID
            uuid = workspace.uuid  # Capture in closure
            action.triggered.connect(lambda checked, uid=uuid: self._switch_to_workspace(uid))

            self._workspaces_menu.addAction(action)

    def _on_new_workspace(self):
        """Create a new workspace."""
        # Save current workspace state first
        self._save_current_workspace_state()

        # Create new workspace
        workspace = self._workspace_manager.new_workspace()
        self._switch_to_workspace(workspace.uuid)

        self._statusbar.showMessage(f"Created new workspace: {workspace.name}")

    def _on_clone_workspace(self):
        """Clone the current workspace."""
        current = self._workspace_manager.current_workspace
        if not current:
            return

        # Save current state first
        self._save_current_workspace_state()

        # Clone
        clone = self._workspace_manager.clone_workspace(current.uuid)
        if clone:
            self._switch_to_workspace(clone.uuid)
            self._statusbar.showMessage(f"Cloned workspace: {clone.name}")

    def _on_rename_workspace(self):
        """Rename the current workspace."""
        current = self._workspace_manager.current_workspace
        if not current:
            return

        name, ok = QInputDialog.getText(
            self, "Rename Workspace",
            "Enter new workspace name:",
            text=current.name
        )

        if ok and name.strip():
            self._workspace_manager.rename_workspace(current.uuid, name.strip())
            self._update_workspace_list_menu()
            self._update_window_title()
            self._statusbar.showMessage(f"Renamed workspace to: {name.strip()}")

    def _on_delete_workspace(self):
        """Delete the current workspace."""
        current = self._workspace_manager.current_workspace
        if not current:
            return

        if self._workspace_manager.workspace_count <= 1:
            QMessageBox.warning(
                self, "Cannot Delete",
                "Cannot delete the last workspace."
            )
            return

        reply = QMessageBox.question(
            self, "Delete Workspace",
            f"Are you sure you want to delete workspace '{current.name}'?\n"
            "All panels in this workspace will be closed.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # Get next workspace to switch to
            next_uuid = self._workspace_manager.get_next_workspace_uuid()
            if next_uuid == current.uuid:
                next_uuid = self._workspace_manager.get_previous_workspace_uuid()

            # Delete current workspace
            self._workspace_manager.delete_workspace(current.uuid)

            # Switch to next workspace
            if next_uuid:
                self._switch_to_workspace(next_uuid)

            self._statusbar.showMessage("Workspace deleted")

    def _on_next_workspace(self):
        """Switch to the next workspace."""
        next_uuid = self._workspace_manager.get_next_workspace_uuid()
        if next_uuid:
            self._save_current_workspace_state()
            self._switch_to_workspace(next_uuid)

    def _on_previous_workspace(self):
        """Switch to the previous workspace."""
        prev_uuid = self._workspace_manager.get_previous_workspace_uuid()
        if prev_uuid:
            self._save_current_workspace_state()
            self._switch_to_workspace(prev_uuid)

    # --- Workspace Tab Bar Methods ---

    def _sync_tab_bar_with_workspaces(self):
        """Synchronize the tab bar with the workspace manager state."""
        workspaces = [
            {'uuid': ws.uuid, 'name': ws.name}
            for ws in self._workspace_manager.workspaces
        ]
        current_uuid = self._workspace_manager.current_workspace_uuid
        self._workspace_tab_bar.update_tabs(workspaces, current_uuid)

    def _on_tab_bar_tab_selected(self, workspace_uuid: str):
        """Handle tab selection from the tab bar."""
        if workspace_uuid != self._workspace_manager.current_workspace_uuid:
            self._save_current_workspace_state()
            self._switch_to_workspace(workspace_uuid)

    def _on_tab_bar_close_workspace(self, workspace_uuid: str):
        """Handle workspace close request from tab bar."""
        workspace = self._workspace_manager.get_workspace(workspace_uuid)
        if not workspace:
            return

        if self._workspace_manager.workspace_count <= 1:
            QMessageBox.warning(
                self, "Cannot Close",
                "Cannot close the last workspace."
            )
            return

        reply = QMessageBox.question(
            self, "Close Workspace",
            f"Are you sure you want to close workspace '{workspace.name}'?\n"
            "All panels in this workspace will be closed.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            # If closing current workspace, switch first
            if workspace_uuid == self._workspace_manager.current_workspace_uuid:
                next_uuid = self._workspace_manager.get_next_workspace_uuid()
                if next_uuid == workspace_uuid:
                    next_uuid = self._workspace_manager.get_previous_workspace_uuid()

                # Delete workspace
                self._workspace_manager.delete_workspace(workspace_uuid)

                # Switch to next workspace
                if next_uuid and next_uuid != workspace_uuid:
                    self._switch_to_workspace(next_uuid)
            else:
                # Just delete the non-current workspace
                self._workspace_manager.delete_workspace(workspace_uuid)

            self._statusbar.showMessage("Workspace closed")

    def _on_tab_bar_rename_workspace(self, workspace_uuid: str, new_name: str):
        """Handle workspace rename request from tab bar."""
        if self._workspace_manager.rename_workspace(workspace_uuid, new_name):
            self._update_workspace_list_menu()
            self._sync_tab_bar_with_workspaces()
            self._update_window_title()
            self._statusbar.showMessage(f"Renamed workspace to: {new_name}")

    def _on_tab_bar_clone_workspace(self, workspace_uuid: str):
        """Handle workspace clone request from tab bar."""
        # Save current state first if cloning current workspace
        if workspace_uuid == self._workspace_manager.current_workspace_uuid:
            self._save_current_workspace_state()

        clone = self._workspace_manager.clone_workspace(workspace_uuid)
        if clone:
            self._switch_to_workspace(clone.uuid)
            self._statusbar.showMessage(f"Cloned workspace: {clone.name}")

    def _on_tabs_reordered(self, new_order: list):
        """Handle tab reorder from drag-and-drop."""
        self._workspace_manager.reorder_workspaces(new_order)
        self._statusbar.showMessage("Workspace tabs reordered")

    def _save_current_workspace_state(self):
        """Save the current workspace's state before switching."""
        if not self._workspace_manager.current_workspace:
            return

        # Get current layout from workspace widget
        layout = self._workspace.to_dict()

        # Get panel states
        panel_states = {}
        for panel in self._workspace.panels:
            if isinstance(panel, WorkspaceDisplayPanel):
                panel_states[panel.panel_id] = panel.to_dict()

        # Get measurements from current panel
        measurements = []
        if self._current_display_panel and hasattr(self._current_display_panel, '_measurement_overlay'):
            overlay = self._current_display_panel._measurement_overlay
            if overlay:
                # Serialize line measurements
                for line_roi in overlay.active_line_rois:
                    pos = line_roi.getLocalHandlePositions()
                    if len(pos) >= 2:
                        measurements.append({
                            'type': 'line',
                            'start': [pos[0][1].x(), pos[0][1].y()],
                            'end': [pos[1][1].x(), pos[1][1].y()]
                        })
                # Serialize polygon measurements
                for poly_roi in overlay.active_polygon_rois:
                    vertices = []
                    for info, pt in poly_roi.getLocalHandlePositions():
                        vertices.append([pt.x(), pt.y()])
                    if vertices:
                        measurements.append({
                            'type': 'polygon',
                            'vertices': vertices
                        })

        # Get hole pairing session data
        hole_pairing_session = None
        if hasattr(self, '_hole_pairing_panel') and self._hole_pairing_panel:
            hole_pairing_session = self._hole_pairing_panel.to_dict()

        # Update workspace state
        self._workspace_manager.update_current_workspace_state(
            layout=layout,
            panel_states=panel_states,
            measurements=measurements,
            hole_pairing_session=hole_pairing_session
        )

    def _switch_to_workspace(self, workspace_uuid: str):
        """Switch to a different workspace."""
        workspace = self._workspace_manager.get_workspace(workspace_uuid)
        if not workspace:
            return

        # Set as current
        self._workspace_manager.set_current_workspace(workspace_uuid)

        # Restore workspace layout
        self._workspace.from_dict(workspace.layout)

        # Restore panel states (file loading, display settings)
        for panel in self._workspace.panels:
            if isinstance(panel, WorkspaceDisplayPanel):
                state = workspace.panel_states.get(panel.panel_id, {})
                file_path = state.get('file_path')

                if file_path:
                    # Check if file is already loaded in cache
                    if file_path in self._loaded_files:
                        data = self._loaded_files[file_path]
                    else:
                        # Load file
                        try:
                            data = read_em_file(file_path)
                            self._loaded_files[file_path] = data
                        except Exception as e:
                            print(f"Error loading file {file_path}: {e}")
                            continue

                    panel.set_data(data, file_path, skip_overlay_warning=True)
                    panel.restore_state(state)
                    # Note: measurements are now restored per-panel in restore_state()

        # Restore hole pairing session
        if hasattr(self, '_hole_pairing_panel') and self._hole_pairing_panel:
            if workspace.hole_pairing_session:
                self._hole_pairing_panel.from_dict(workspace.hole_pairing_session)
                self._hole_pairing_panel.set_workspace(self._workspace)
            else:
                # Clear if no session data
                self._hole_pairing_panel._session = None
                from src.gui.hole_pairing_data import PairingSession
                self._hole_pairing_panel._session = PairingSession()
                self._hole_pairing_panel._refresh_panel_list()

        # Update menu and tab bar
        self._update_workspace_list_menu()
        self._sync_tab_bar_with_workspaces()
        self._update_window_title()

        # Update status
        self._statusbar.showMessage(f"Switched to workspace: {workspace.name}")

    def _update_window_title(self):
        """Update the window title to show current workspace."""
        base_title = "Nion nhdf Utility - Workspace Edition"
        current = self._workspace_manager.current_workspace
        if current:
            session_name = self._session_manager.session_name
            modified = "*" if self._session_manager.is_modified else ""
            self.setWindowTitle(f"{base_title} - [{current.name}] - {session_name}{modified}")
        else:
            self.setWindowTitle(base_title)

    # --- Session Management Methods ---

    def _on_new_session(self):
        """Create a new session."""
        if self._session_manager.is_modified:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "Current session has unsaved changes. Do you want to save before creating a new session?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )

            if reply == QMessageBox.Save:
                if not self._on_save_session():
                    return  # Save was cancelled
            elif reply == QMessageBox.Cancel:
                return

        # Clear and create new session
        self._session_manager.new_session()

        # Reset workspace widget
        self._workspace.from_dict({'type': 'panel'})

        # Update UI
        self._update_workspace_list_menu()
        self._update_window_title()
        self._statusbar.showMessage("New session created")

    def _on_open_session(self):
        """Open an existing session."""
        if self._session_manager.is_modified:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "Current session has unsaved changes. Do you want to save before opening another session?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )

            if reply == QMessageBox.Save:
                if not self._on_save_session():
                    return
            elif reply == QMessageBox.Cancel:
                return

        # Show file dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Session",
            str(pathlib.Path.home()),
            "Session Files (*.json);;All Files (*)"
        )

        if file_path:
            if self._session_manager.load_session(file_path):
                # Restore current workspace
                current = self._workspace_manager.current_workspace
                if current:
                    self._switch_to_workspace(current.uuid)

                self._update_workspace_list_menu()
                self._update_window_title()
                self._statusbar.showMessage(f"Session loaded: {file_path}")
            else:
                QMessageBox.warning(
                    self, "Error",
                    f"Failed to load session from {file_path}"
                )

    def _on_save_session(self) -> bool:
        """Save the current session."""
        # Save current workspace state first
        self._save_current_workspace_state()

        if self._session_manager.current_session_path:
            if self._session_manager.save_session():
                self._update_window_title()
                self._statusbar.showMessage("Session saved")
                return True
            else:
                QMessageBox.warning(
                    self, "Error",
                    "Failed to save session"
                )
                return False
        else:
            return self._on_save_session_as()

    def _on_save_session_as(self) -> bool:
        """Save the current session to a new file."""
        # Save current workspace state first
        self._save_current_workspace_state()

        # Ask for session name
        name, ok = QInputDialog.getText(
            self, "Session Name",
            "Enter a name for this session:",
            text=self._session_manager.session_name
        )

        if not ok:
            return False

        self._session_manager.session_name = name.strip() if name.strip() else "Untitled Session"

        # Show file dialog
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Session As",
            str(pathlib.Path.home() / f"{self._session_manager.session_name}.json"),
            "Session Files (*.json);;All Files (*)"
        )

        if file_path:
            if self._session_manager.save_session(file_path):
                self._update_window_title()
                self._statusbar.showMessage(f"Session saved: {file_path}")
                return True
            else:
                QMessageBox.warning(
                    self, "Error",
                    f"Failed to save session to {file_path}"
                )
                return False

        return False

    # --- Public API ---

    def load_file(self, path: pathlib.Path):
        """Public method to load a file."""
        self._load_file_in_current_panel(path)