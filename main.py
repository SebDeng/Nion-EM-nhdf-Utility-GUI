#!/usr/bin/env python3
"""
Nion nhdf Utility GUI

A modern graphical user interface for viewing and managing
Nion electron microscopy nhdf files.

Usage:
    python main.py [file.nhdf]           # Workspace mode with free-tiling (default)
    python main.py --simple [file.nhdf]  # Simple single-panel mode
"""

import sys
import pathlib
import argparse
import os

# ============================================================================
# PERFORMANCE OPTIMIZATIONS - Configure before importing Qt/pyqtgraph
# ============================================================================
# Optimized for Apple Silicon (M1 Max with 64GB unified memory)
# - OpenGL works via Metal translation layer on macOS
# - Unified memory means GPU can access all 64GB without transfer overhead
# ============================================================================

os.environ.setdefault('PYQTGRAPH_QT_LIB', 'PySide6')

# Configure pyqtgraph BEFORE importing it
import pyqtgraph as pg

# Enable performance optimizations for pyqtgraph
# NOTE: OpenGL can cause visual glitches on some systems - disabled for stability
# NOTE: imageAxisOrder must stay default ('col-major') or polygons misalign
pg.setConfigOptions(
    useOpenGL=False,          # Disabled - caused polygon misalignment on macOS
    enableExperimental=True,  # Enable experimental features for performance
    antialias=False,          # Disable antialiasing for speed
    useNumba=True,            # Use Numba JIT compilation if available
    # imageAxisOrder stays default 'col-major' - changing it breaks polygon alignment
)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QPalette, QColor, QIcon

from src.gui.main_window import MainWindow
from src.gui.workspace_main_window import WorkspaceMainWindow

# Get the directory where this script is located
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def apply_dark_theme(app: QApplication):
    """Apply a dark theme similar to Nion Swift."""
    app.setStyle("Fusion")

    palette = QPalette()

    # Base colors
    dark_gray = QColor(53, 53, 53)
    gray = QColor(80, 80, 80)
    light_gray = QColor(120, 120, 120)
    very_light_gray = QColor(200, 200, 200)
    white = QColor(255, 255, 255)
    blue = QColor(42, 130, 218)

    # Set palette colors
    palette.setColor(QPalette.Window, dark_gray)
    palette.setColor(QPalette.WindowText, white)
    palette.setColor(QPalette.Base, QColor(35, 35, 35))
    palette.setColor(QPalette.AlternateBase, dark_gray)
    palette.setColor(QPalette.ToolTipBase, dark_gray)
    palette.setColor(QPalette.ToolTipText, white)
    palette.setColor(QPalette.Text, white)
    palette.setColor(QPalette.Button, dark_gray)
    palette.setColor(QPalette.ButtonText, white)
    palette.setColor(QPalette.BrightText, Qt.red)
    palette.setColor(QPalette.Link, blue)
    palette.setColor(QPalette.Highlight, blue)
    palette.setColor(QPalette.HighlightedText, white)

    # Disabled colors
    palette.setColor(QPalette.Disabled, QPalette.WindowText, light_gray)
    palette.setColor(QPalette.Disabled, QPalette.Text, light_gray)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, light_gray)

    app.setPalette(palette)

    # Additional stylesheet for fine-tuning
    app.setStyleSheet("""
        QToolTip {
            color: #ffffff;
            background-color: #353535;
            border: 1px solid #505050;
            padding: 4px;
        }

        QMenuBar {
            background-color: #353535;
            padding: 2px;
        }

        QMenuBar::item {
            background-color: transparent;
            padding: 4px 8px;
        }

        QMenuBar::item:selected {
            background-color: #505050;
        }

        QMenu {
            background-color: #353535;
            border: 1px solid #505050;
        }

        QMenu::item:selected {
            background-color: #2a82da;
        }

        QDockWidget {
            titlebar-close-icon: url(close.png);
            titlebar-normal-icon: url(float.png);
        }

        QDockWidget::title {
            background-color: #404040;
            padding: 6px;
            text-align: left;
        }

        QStatusBar {
            background-color: #353535;
            border-top: 1px solid #505050;
        }

        QTreeView {
            background-color: #2b2b2b;
            alternate-background-color: #323232;
            border: 1px solid #505050;
        }

        QTreeView::item:hover {
            background-color: #404040;
        }

        QTreeView::item:selected {
            background-color: #2a82da;
        }

        QHeaderView::section {
            background-color: #404040;
            padding: 4px;
            border: 1px solid #505050;
        }

        QSlider::groove:horizontal {
            border: 1px solid #505050;
            height: 6px;
            background: #2b2b2b;
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
            background-color: #2b2b2b;
            border: 1px solid #505050;
            padding: 2px;
        }

        QComboBox {
            background-color: #2b2b2b;
            border: 1px solid #505050;
            padding: 4px;
        }

        QComboBox::drop-down {
            border: none;
            width: 20px;
        }

        QLineEdit {
            background-color: #2b2b2b;
            border: 1px solid #505050;
            padding: 4px;
        }

        QPushButton {
            background-color: #404040;
            border: 1px solid #505050;
            padding: 6px 12px;
            border-radius: 3px;
        }

        QPushButton:hover {
            background-color: #505050;
        }

        QPushButton:pressed {
            background-color: #2a82da;
        }

        QPushButton:checked {
            background-color: #2a82da;
        }

        QCheckBox::indicator {
            width: 16px;
            height: 16px;
        }

        QGroupBox {
            border: 1px solid #505050;
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 8px;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 4px;
        }
    """)


def configure_thread_pool():
    """Configure the global thread pool for better parallel performance."""
    pool = QThreadPool.globalInstance()

    # Get the number of CPU cores
    import multiprocessing
    cpu_count = multiprocessing.cpu_count()

    # M1 Max has 10 cores (8 performance + 2 efficiency)
    # Set max thread count to 2x CPU cores for I/O bound operations
    # This allows better parallelism for file loading, image processing, etc.
    max_threads = max(cpu_count * 2, 16)  # At least 16 threads for M1
    pool.setMaxThreadCount(max_threads)

    # Set thread expiry time (ms) - keep threads alive longer to reduce overhead
    pool.setExpiryTimeout(120000)  # 2 minutes - longer for better reuse

    # Set stack size for threads (optional, useful for deep recursion)
    # pool.setStackSize(8 * 1024 * 1024)  # 8MB stack per thread

    print(f"Thread pool configured: {max_threads} threads (CPU cores: {cpu_count})")
    return pool


def main():
    """Main entry point."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Nion nhdf Utility GUI")
    parser.add_argument("file", nargs="?", help="nhdf file to open")
    parser.add_argument("--simple", action="store_true",
                        help="Use simple single-panel mode instead of workspace")
    args = parser.parse_args()

    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create application
    app = QApplication([])  # Empty list to avoid re-parsing args

    # Configure thread pool for parallel operations
    configure_thread_pool()
    app.setApplicationName("Nion nhdf Utility")
    app.setOrganizationName("NionUtility")
    app.setOrganizationDomain("github.com/SebDeng")

    # Apply dark theme
    apply_dark_theme(app)

    # Set application icon (use pre-rounded PNG for proper appearance)
    icon_path = os.path.join(_SCRIPT_DIR, "assets", "AppIcon_rounded.png")
    if not os.path.exists(icon_path):
        icon_path = os.path.join(_SCRIPT_DIR, "assets", "AE APP ICON.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Create main window based on mode
    if args.simple:
        window = MainWindow()
    else:
        window = WorkspaceMainWindow()  # Default to workspace mode

    window.show()

    # Load file if provided
    if args.file:
        file_path = pathlib.Path(args.file)
        if file_path.exists() and file_path.suffix.lower() == '.nhdf':
            window.load_file(file_path)

    # Run event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
