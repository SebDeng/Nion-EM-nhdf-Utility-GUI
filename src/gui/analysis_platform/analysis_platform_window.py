"""
Analysis Platform Main Window.

Standalone window for interactive hole pairing data analysis.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QSplitter,
    QGroupBox, QCheckBox, QFileDialog, QMessageBox,
    QMenuBar, QMenu, QToolBar, QStatusBar, QDoubleSpinBox,
    QFormLayout, QFrame
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QColor, QIcon, QPixmap, QPainter, QBrush, QPen

import os
from typing import Optional

from .dataset_manager import DatasetManager, Dataset, AnalysisProject
from .dataset_import_dialog import DatasetImportDialog
from .interactive_plot_widget import InteractivePlotWidget
from .data_point_info_panel import DataPointInfoPanel


def create_color_icon(color_str: str, symbol: str = 'o', size: int = 16) -> QIcon:
    """Create a colored icon with the dataset symbol."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    color = QColor(color_str)
    painter.setBrush(QBrush(color))
    painter.setPen(QPen(color.darker(120), 1))

    center = size // 2
    radius = size // 2 - 2

    if symbol == 'o':  # circle
        painter.drawEllipse(center - radius, center - radius, radius * 2, radius * 2)
    elif symbol == 's':  # square
        painter.drawRect(center - radius, center - radius, radius * 2, radius * 2)
    elif symbol == 't':  # triangle
        from PySide6.QtGui import QPolygon
        from PySide6.QtCore import QPoint
        points = [
            QPoint(center, center - radius),
            QPoint(center - radius, center + radius),
            QPoint(center + radius, center + radius)
        ]
        painter.drawPolygon(QPolygon(points))
    elif symbol == 'd':  # diamond
        from PySide6.QtGui import QPolygon
        from PySide6.QtCore import QPoint
        points = [
            QPoint(center, center - radius),
            QPoint(center + radius, center),
            QPoint(center, center + radius),
            QPoint(center - radius, center)
        ]
        painter.drawPolygon(QPolygon(points))
    else:  # default circle
        painter.drawEllipse(center - radius, center - radius, radius * 2, radius * 2)

    painter.end()
    return QIcon(pixmap)


class DatasetListItem(QListWidgetItem):
    """List item for a dataset with visibility checkbox."""

    def __init__(self, dataset: Dataset, parent=None):
        super().__init__(parent)
        self.dataset = dataset
        self._update_display()

    def _update_display(self):
        """Update the display text and icon."""
        visibility = "●" if self.dataset.visible else "○"
        self.setText(f"{visibility} {self.dataset.name} (n={self.dataset.count})")

        # Set colored icon with symbol shape
        icon = create_color_icon(self.dataset.color, self.dataset.symbol, 16)
        self.setIcon(icon)

        # Also set text color for better visibility
        color = QColor(self.dataset.color)
        self.setForeground(color)


class AnalysisPlatformWindow(QMainWindow):
    """Main window for the analysis platform."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hole Pairing Analysis Platform")
        self.setMinimumSize(1200, 800)

        # Data manager
        self._manager = DatasetManager(self)

        # Setup UI
        self._setup_menubar()
        self._setup_toolbar()
        self._setup_ui()
        self._setup_statusbar()

        self._connect_signals()

        # Start with empty project
        self._manager.new_project()

    def _setup_menubar(self):
        """Setup the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        self._new_action = QAction("New Project", self)
        self._new_action.setShortcut("Ctrl+N")
        self._new_action.triggered.connect(self._new_project)
        file_menu.addAction(self._new_action)

        self._open_action = QAction("Open Project...", self)
        self._open_action.setShortcut("Ctrl+O")
        self._open_action.triggered.connect(self._open_project)
        file_menu.addAction(self._open_action)

        self._save_action = QAction("Save Project", self)
        self._save_action.setShortcut("Ctrl+S")
        self._save_action.triggered.connect(self._save_project)
        file_menu.addAction(self._save_action)

        self._save_as_action = QAction("Save Project As...", self)
        self._save_as_action.setShortcut("Ctrl+Shift+S")
        self._save_as_action.triggered.connect(self._save_project_as)
        file_menu.addAction(self._save_as_action)

        file_menu.addSeparator()

        self._import_action = QAction("Import CSV...", self)
        self._import_action.setShortcut("Ctrl+I")
        self._import_action.triggered.connect(self._import_csv)
        file_menu.addAction(self._import_action)

        file_menu.addSeparator()

        self._close_action = QAction("Close", self)
        self._close_action.setShortcut("Ctrl+W")
        self._close_action.triggered.connect(self.close)
        file_menu.addAction(self._close_action)

        # Export menu
        export_menu = menubar.addMenu("Export")

        self._export_plot_action = QAction("Export Plot as PNG...", self)
        self._export_plot_action.triggered.connect(self._export_plot)
        export_menu.addAction(self._export_plot_action)

        self._export_stats_action = QAction("Export Statistics as CSV...", self)
        self._export_stats_action.triggered.connect(self._export_statistics)
        export_menu.addAction(self._export_stats_action)

        # Help menu
        help_menu = menubar.addMenu("Help")

        self._about_action = QAction("About", self)
        self._about_action.triggered.connect(self._show_about)
        help_menu.addAction(self._about_action)

    def _setup_toolbar(self):
        """Setup the toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        toolbar.addAction(self._import_action)
        toolbar.addSeparator()
        toolbar.addAction(self._save_action)

    def _setup_ui(self):
        """Setup the main UI."""
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)

        # Main splitter
        splitter = QSplitter(Qt.Horizontal)

        # === Left Panel: Datasets and Filters ===
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Datasets Group
        datasets_group = QGroupBox("Datasets")
        datasets_layout = QVBoxLayout(datasets_group)

        self._dataset_list = QListWidget()
        self._dataset_list.setAlternatingRowColors(True)
        self._dataset_list.itemDoubleClicked.connect(self._on_dataset_double_clicked)
        self._dataset_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._dataset_list.customContextMenuRequested.connect(self._show_dataset_context_menu)
        datasets_layout.addWidget(self._dataset_list)

        # Dataset buttons
        dataset_btn_layout = QHBoxLayout()

        self._import_btn = QPushButton("+ Import CSV")
        self._import_btn.clicked.connect(self._import_csv)
        dataset_btn_layout.addWidget(self._import_btn)

        self._refresh_btn = QPushButton("↻")
        self._refresh_btn.setToolTip("Refresh selected dataset from CSV")
        self._refresh_btn.setMaximumWidth(30)
        self._refresh_btn.clicked.connect(self._refresh_selected_dataset)
        dataset_btn_layout.addWidget(self._refresh_btn)

        self._remove_btn = QPushButton("−")
        self._remove_btn.setToolTip("Remove selected dataset")
        self._remove_btn.setMaximumWidth(30)
        self._remove_btn.clicked.connect(self._remove_selected_dataset)
        dataset_btn_layout.addWidget(self._remove_btn)

        datasets_layout.addLayout(dataset_btn_layout)

        # Merge button
        self._merge_btn = QPushButton("Merge by Current")
        self._merge_btn.setToolTip("Merge datasets with same light intensity into one for fitting")
        self._merge_btn.clicked.connect(self._merge_datasets)
        datasets_layout.addWidget(self._merge_btn)

        left_layout.addWidget(datasets_group)

        # Filters Group
        filters_group = QGroupBox("Filters")
        filters_layout = QFormLayout(filters_group)

        # ΔA filter
        delta_a_layout = QHBoxLayout()
        self._delta_a_min = QDoubleSpinBox()
        self._delta_a_min.setRange(-1000, 1000)
        self._delta_a_min.setValue(-1000)
        self._delta_a_min.setPrefix("min: ")
        delta_a_layout.addWidget(self._delta_a_min)

        self._delta_a_max = QDoubleSpinBox()
        self._delta_a_max.setRange(-1000, 1000)
        self._delta_a_max.setValue(1000)
        self._delta_a_max.setPrefix("max: ")
        delta_a_layout.addWidget(self._delta_a_max)

        filters_layout.addRow("ΔA (nm²):", delta_a_layout)

        # Distance filter
        dist_layout = QHBoxLayout()
        self._dist_min = QDoubleSpinBox()
        self._dist_min.setRange(0, 10000)
        self._dist_min.setValue(0)
        self._dist_min.setPrefix("min: ")
        dist_layout.addWidget(self._dist_min)

        self._dist_max = QDoubleSpinBox()
        self._dist_max.setRange(0, 10000)
        self._dist_max.setValue(10000)
        self._dist_max.setPrefix("max: ")
        dist_layout.addWidget(self._dist_max)

        filters_layout.addRow("r (nm):", dist_layout)

        left_layout.addWidget(filters_group)

        # Selected Point Info
        self._info_panel = DataPointInfoPanel(self._manager)
        left_layout.addWidget(self._info_panel)

        left_layout.addStretch()

        splitter.addWidget(left_panel)

        # === Center Panel: Plot ===
        self._plot_widget = InteractivePlotWidget(self._manager)
        splitter.addWidget(self._plot_widget)

        # Set splitter sizes (30% left, 70% center)
        splitter.setSizes([300, 700])

        main_layout.addWidget(splitter)

    def _setup_statusbar(self):
        """Setup the status bar."""
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("Ready")

    def _connect_signals(self):
        """Connect signals."""
        self._manager.datasets_changed.connect(self._update_dataset_list)
        self._manager.project_changed.connect(self._update_window_title)
        self._plot_widget.point_clicked.connect(self._on_point_clicked)
        self._plot_widget.point_hovered.connect(self._on_point_hovered)
        self._info_panel.show_in_session.connect(self._on_show_in_session)

    def _update_window_title(self):
        """Update window title with project name."""
        project = self._manager.project
        if project:
            title = f"Hole Pairing Analysis Platform - {project.name}"
            if self._manager.project_path:
                title += f" ({os.path.basename(self._manager.project_path)})"
            self.setWindowTitle(title)
        else:
            self.setWindowTitle("Hole Pairing Analysis Platform")

    def _update_dataset_list(self):
        """Update the dataset list widget."""
        self._dataset_list.clear()

        for dataset in self._manager.datasets:
            item = DatasetListItem(dataset)
            self._dataset_list.addItem(item)

        # Update status
        total_points = sum(ds.count for ds in self._manager.datasets)
        self._statusbar.showMessage(
            f"{len(self._manager.datasets)} datasets, {total_points} total points"
        )

    def _new_project(self):
        """Create a new project."""
        if self._manager.datasets:
            reply = QMessageBox.question(
                self, "New Project",
                "Create a new project? Unsaved changes will be lost.",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        self._manager.new_project()
        self._update_dataset_list()

    def _open_project(self):
        """Open an existing project."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Project",
            "", "Analysis Project (*.hpa);;All Files (*)"
        )

        if path:
            if self._manager.load_project(path):
                self._statusbar.showMessage(f"Loaded: {path}")
            else:
                QMessageBox.warning(self, "Error", "Failed to load project.")

    def _save_project(self):
        """Save the current project."""
        if self._manager.project_path:
            if self._manager.save_project(self._manager.project_path):
                self._statusbar.showMessage("Project saved.")
            else:
                QMessageBox.warning(self, "Error", "Failed to save project.")
        else:
            self._save_project_as()

    def _save_project_as(self):
        """Save project with a new name."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Project",
            "analysis_project.hpa",
            "Analysis Project (*.hpa);;All Files (*)"
        )

        if path:
            if not path.endswith('.hpa'):
                path += '.hpa'

            if self._manager.save_project(path):
                self._statusbar.showMessage(f"Saved: {path}")
                self._update_window_title()
            else:
                QMessageBox.warning(self, "Error", "Failed to save project.")

    def _import_csv(self):
        """Import a CSV file."""
        dialog = DatasetImportDialog(self, len(self._manager.datasets))

        if dialog.exec() == DatasetImportDialog.Accepted:
            params = dialog.get_import_params()

            dataset = self._manager.import_csv(
                csv_path=params['csv_path'],
                name=params['name'],
                light_intensity_mA=params['light_intensity_mA'],
                color=params['color'],
                symbol=params['symbol'],
                session_path=params.get('session_path', '')
            )

            if dataset:
                self._statusbar.showMessage(
                    f"Imported: {dataset.name} ({dataset.count} points)"
                )
            else:
                QMessageBox.warning(self, "Import Error", "Failed to import CSV file.")

    def _refresh_selected_dataset(self):
        """Refresh selected dataset from its CSV."""
        item = self._dataset_list.currentItem()
        if not isinstance(item, DatasetListItem):
            return

        dataset = item.dataset

        # Ask for new CSV file
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Updated CSV",
            dataset.csv_path,
            "CSV Files (*.csv);;All Files (*)"
        )

        if path:
            if self._manager.update_dataset(dataset.dataset_id, path):
                self._statusbar.showMessage(f"Updated: {dataset.name}")
            else:
                QMessageBox.warning(self, "Error", "Failed to update dataset.")

    def _remove_selected_dataset(self):
        """Remove selected dataset."""
        item = self._dataset_list.currentItem()
        if not isinstance(item, DatasetListItem):
            return

        dataset = item.dataset

        reply = QMessageBox.question(
            self, "Remove Dataset",
            f"Remove dataset '{dataset.name}'?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self._manager.remove_dataset(dataset.dataset_id)

    def _merge_datasets(self):
        """Merge datasets with the same light intensity."""
        # Check if there are datasets to merge
        groups = self._manager.get_datasets_by_intensity()
        mergeable = {k: v for k, v in groups.items() if len(v) > 1}

        if not mergeable:
            QMessageBox.information(
                self, "No Datasets to Merge",
                "There are no datasets with the same light intensity to merge.\n"
                "You need at least 2 datasets with the same current value."
            )
            return

        # Show confirmation
        msg = "This will create merged datasets for the following currents:\n\n"
        for intensity, datasets in mergeable.items():
            names = [ds.name for ds in datasets]
            msg += f"• {intensity:.0f} mA: {', '.join(names)}\n"
        msg += "\nThe original datasets will be kept. Continue?"

        reply = QMessageBox.question(
            self, "Merge Datasets",
            msg,
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            merged = self._manager.merge_datasets_by_intensity()
            if merged:
                self._statusbar.showMessage(
                    f"Created {len(merged)} merged dataset(s)"
                )
            else:
                QMessageBox.warning(self, "Error", "Failed to merge datasets.")

    def _on_dataset_double_clicked(self, item):
        """Handle double-click on dataset to toggle visibility."""
        if isinstance(item, DatasetListItem):
            dataset = item.dataset
            self._manager.set_dataset_visibility(
                dataset.dataset_id,
                not dataset.visible
            )

    def _show_dataset_context_menu(self, pos):
        """Show context menu for dataset."""
        item = self._dataset_list.itemAt(pos)
        if not isinstance(item, DatasetListItem):
            return

        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)

        toggle_action = menu.addAction(
            "Hide" if item.dataset.visible else "Show"
        )
        toggle_action.triggered.connect(
            lambda: self._manager.set_dataset_visibility(
                item.dataset.dataset_id,
                not item.dataset.visible
            )
        )

        menu.addSeparator()

        refresh_action = menu.addAction("Refresh from CSV...")
        refresh_action.triggered.connect(self._refresh_selected_dataset)

        remove_action = menu.addAction("Remove")
        remove_action.triggered.connect(self._remove_selected_dataset)

        menu.exec_(self._dataset_list.mapToGlobal(pos))

    def _on_point_clicked(self, dataset_id: str, pairing_id: str):
        """Handle point click."""
        self._info_panel.set_point(dataset_id, pairing_id)

    def _on_point_hovered(self, dataset_id: str, pairing_id: str):
        """Handle point hover."""
        if dataset_id and pairing_id:
            result = self._manager.get_point_by_id(pairing_id)
            if result:
                dataset, point = result
                self._statusbar.showMessage(
                    f"{dataset.name} | {pairing_id} | ΔA={point.delta_area_nm2:.4f} nm²"
                )
        else:
            # Restore default status
            total_points = sum(ds.count for ds in self._manager.datasets)
            self._statusbar.showMessage(
                f"{len(self._manager.datasets)} datasets, {total_points} total points"
            )

    def _on_show_in_session(self, session_path: str, pairing_id: str):
        """Handle request to show point in original session."""
        import os

        if not os.path.exists(session_path):
            QMessageBox.warning(
                self, "Session Not Found",
                f"The session file could not be found:\n{session_path}\n\n"
                "The file may have been moved or deleted."
            )
            return

        # Open the hole viewer dialog
        from .hole_viewer_dialog import HoleViewerDialog
        dialog = HoleViewerDialog(session_path, pairing_id, parent=self)
        dialog.exec()

    def _export_plot(self):
        """Export plot as PNG."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Plot",
            "analysis_plot.png",
            "PNG Images (*.png);;All Files (*)"
        )

        if path:
            if not path.endswith('.png'):
                path += '.png'

            try:
                self._plot_widget.export_plot_image(path)
                self._statusbar.showMessage(f"Exported: {path}")
            except Exception as e:
                QMessageBox.warning(self, "Export Error", f"Failed to export: {e}")

    def _export_statistics(self):
        """Export statistics as CSV."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Statistics",
            "analysis_statistics.csv",
            "CSV Files (*.csv);;All Files (*)"
        )

        if path:
            if not path.endswith('.csv'):
                path += '.csv'

            try:
                import csv

                stats = self._plot_widget.get_statistics()

                with open(path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        'Dataset', 'Light Intensity (mA)', 'n',
                        'X Variable', 'Y Variable',
                        'Slope', 'Intercept', 'R²', 'p-value', 'Std Error'
                    ])

                    for stat in stats:
                        writer.writerow([
                            stat['dataset_name'],
                            stat['light_intensity_mA'],
                            stat['n'],
                            stat['x_variable'],
                            stat['y_variable'],
                            f"{stat['slope']:.6f}",
                            f"{stat['intercept']:.6f}",
                            f"{stat['r_squared']:.6f}",
                            f"{stat['p_value']:.6e}",
                            f"{stat['std_err']:.6f}",
                        ])

                self._statusbar.showMessage(f"Exported: {path}")

            except Exception as e:
                QMessageBox.warning(self, "Export Error", f"Failed to export: {e}")

    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About Analysis Platform",
            "Hole Pairing Analysis Platform\n\n"
            "An interactive data exploration tool for\n"
            "vacancy diffusion analysis.\n\n"
            "Features:\n"
            "- Import multiple CSV datasets\n"
            "- Interactive scatter plots\n"
            "- Flexible axis selection\n"
            "- Linear regression statistics\n"
            "- Export to PNG and CSV"
        )
