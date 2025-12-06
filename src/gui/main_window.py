"""
Main application window for nhdf Utility GUI.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QDockWidget, QMenuBar, QMenu, QStatusBar, QFileDialog,
    QMessageBox, QApplication, QDialog, QLabel
)
from PySide6.QtCore import Qt, Signal, QSettings
from PySide6.QtGui import QAction, QKeySequence, QPixmap

import pathlib
from typing import Optional

from src.core.nhdf_reader import NHDFData, read_nhdf
from src.gui.file_browser import FileBrowserPanel
from src.gui.display_panel import DisplayPanel
from src.gui.metadata_panel import MetadataPanel


class MainWindow(QMainWindow):
    """Main application window with Nion Swift-inspired layout."""

    # Signals
    file_loaded = Signal(object)  # Emits NHDFData when file is loaded

    def __init__(self):
        super().__init__()

        self._current_data: Optional[NHDFData] = None
        self._settings = QSettings("NionUtility", "nhdfGUI")

        self._setup_ui()
        self._setup_menus()
        self._setup_statusbar()
        self._connect_signals()
        self._restore_state()

    def _setup_ui(self):
        """Set up the main UI layout."""
        self.setWindowTitle("Nion nhdf Utility")
        self.setMinimumSize(1200, 800)

        # Central widget - Display Panel
        self._display_panel = DisplayPanel()
        self.setCentralWidget(self._display_panel)

        # Left dock - File Browser
        self._file_browser_dock = QDockWidget("File Browser", self)
        self._file_browser_dock.setObjectName("FileBrowserDock")
        self._file_browser = FileBrowserPanel()
        self._file_browser_dock.setWidget(self._file_browser)
        self._file_browser_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._file_browser_dock.setMinimumWidth(250)
        self.addDockWidget(Qt.LeftDockWidgetArea, self._file_browser_dock)

        # Right dock - Metadata Panel
        self._metadata_dock = QDockWidget("Metadata", self)
        self._metadata_dock.setObjectName("MetadataDock")
        self._metadata_panel = MetadataPanel()
        self._metadata_dock.setWidget(self._metadata_panel)
        self._metadata_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._metadata_dock.setMinimumWidth(300)
        self.addDockWidget(Qt.RightDockWidgetArea, self._metadata_dock)

    def _setup_menus(self):
        """Set up the menu bar."""
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

        close_action = QAction("&Close", self)
        close_action.setShortcut(QKeySequence.Close)
        close_action.triggered.connect(self._on_close_file)
        file_menu.addAction(close_action)

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

        reset_layout_action = QAction("Reset Layout", self)
        reset_layout_action.triggered.connect(self._reset_layout)
        view_menu.addAction(reset_layout_action)

        # Export menu (placeholder for Phase 2)
        export_menu = menubar.addMenu("&Export")

        export_image_action = QAction("Export &Image...", self)
        export_image_action.setShortcut(QKeySequence("Ctrl+E"))
        export_image_action.triggered.connect(self._on_export_image)
        export_image_action.setEnabled(False)
        self._export_image_action = export_image_action
        export_menu.addAction(export_image_action)

        export_data_action = QAction("Export &Data...", self)
        export_data_action.triggered.connect(self._on_export_data)
        export_data_action.setEnabled(False)
        self._export_data_action = export_data_action
        export_menu.addAction(export_data_action)

        export_metadata_action = QAction("Export &Metadata...", self)
        export_metadata_action.triggered.connect(self._on_export_metadata)
        export_metadata_action.setEnabled(False)
        self._export_metadata_action = export_metadata_action
        export_menu.addAction(export_metadata_action)

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
        self._file_browser.file_double_clicked.connect(self._load_file)

        # Display panel signals
        self._display_panel.frame_changed.connect(self._on_frame_changed)

        # Internal signals
        self.file_loaded.connect(self._on_file_loaded)

    def _restore_state(self):
        """Restore window state from settings."""
        geometry = self._settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        state = self._settings.value("windowState")
        if state:
            self.restoreState(state)

        # Restore last folder
        last_folder = self._settings.value("lastFolder")
        if last_folder and pathlib.Path(last_folder).exists():
            self._file_browser.set_root_path(pathlib.Path(last_folder))

    def _save_state(self):
        """Save window state to settings."""
        self._settings.setValue("geometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState())

        if self._file_browser.current_path:
            self._settings.setValue("lastFolder", str(self._file_browser.current_path))

    def closeEvent(self, event):
        """Handle window close event."""
        self._save_state()
        super().closeEvent(event)

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
            self._load_file(pathlib.Path(file_path))

    def _on_open_folder(self):
        """Open a folder in the file browser."""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Open Folder",
            str(self._file_browser.current_path or pathlib.Path.home())
        )
        if folder_path:
            self._file_browser.set_root_path(pathlib.Path(folder_path))

    def _on_close_file(self):
        """Close the current file."""
        self._current_data = None
        self._display_panel.clear()
        self._metadata_panel.clear()
        self._update_export_actions(False)
        self._statusbar.showMessage("Ready")

    def _on_file_selected(self, path: pathlib.Path):
        """Handle file selection in browser (single click)."""
        # Could show preview info in status bar
        try:
            from src.core.nhdf_reader import get_file_info
            info = get_file_info(path)
            if "error" not in info:
                self._statusbar.showMessage(
                    f"{path.name} | Shape: {info['shape']} | Frames: {info['num_frames']}"
                )
        except Exception:
            pass

    def _load_file(self, path: pathlib.Path):
        """Load an nhdf file."""
        try:
            self._statusbar.showMessage(f"Loading {path.name}...")
            QApplication.processEvents()

            data = read_nhdf(path)
            self._current_data = data
            self.file_loaded.emit(data)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Error Loading File",
                f"Failed to load {path.name}:\n{str(e)}"
            )
            self._statusbar.showMessage("Error loading file")

    def _on_file_loaded(self, data: NHDFData):
        """Handle successful file load."""
        # Update display panel
        self._display_panel.set_data(data)

        # Update metadata panel
        self._metadata_panel.set_data(data)

        # Update status bar
        self._statusbar.showMessage(data.get_summary())

        # Enable export actions
        self._update_export_actions(True)

    def _on_frame_changed(self, frame_index: int):
        """Handle frame change in display panel."""
        if self._current_data:
            self._statusbar.showMessage(
                f"{self._current_data.get_display_name()} | "
                f"Frame {frame_index + 1}/{self._current_data.num_frames} | "
                f"{self._current_data.frame_shape}"
            )

    def _update_export_actions(self, enabled: bool):
        """Enable/disable export actions."""
        self._export_image_action.setEnabled(enabled)
        self._export_data_action.setEnabled(enabled)
        self._export_metadata_action.setEnabled(enabled)

    # --- Export operations (Phase 2 placeholders) ---

    def _on_export_image(self):
        """Export current frame as image."""
        QMessageBox.information(self, "Export", "Export Image - Coming in Phase 2")

    def _on_export_data(self):
        """Export data in various formats."""
        QMessageBox.information(self, "Export", "Export Data - Coming in Phase 2")

    def _on_export_metadata(self):
        """Export metadata as JSON."""
        QMessageBox.information(self, "Export", "Export Metadata - Coming in Phase 2")

    # --- View operations ---

    def _reset_layout(self):
        """Reset dock widgets to default layout."""
        self._file_browser_dock.setVisible(True)
        self._metadata_dock.setVisible(True)

        self.removeDockWidget(self._file_browser_dock)
        self.removeDockWidget(self._metadata_dock)

        self.addDockWidget(Qt.LeftDockWidgetArea, self._file_browser_dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self._metadata_dock)

    def _on_about(self):
        """Show about dialog with logo."""
        dialog = QDialog(self)
        dialog.setWindowTitle("About Atomic Engineering nhdf Utility")
        dialog.setFixedSize(500, 350)

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
        title_label = QLabel("<h3>nhdf Utility GUI</h3>")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        desc_label = QLabel(
            "<p>A viewer for Nion electron microscopy nhdf files.</p>"
            "<p>Built with PySide6 (Qt) for the electron microscopy community.</p>"
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
        self._load_file(path)

    @property
    def current_data(self) -> Optional[NHDFData]:
        """Get the currently loaded data."""
        return self._current_data
