"""
Dataset Import Dialog.

Dialog for importing CSV files with metadata (light intensity, name, color).
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QDoubleSpinBox, QFileDialog, QGroupBox,
    QComboBox, QMessageBox, QFormLayout
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter, QBrush, QPen

import os
import csv

from .dataset_manager import DEFAULT_COLORS, DEFAULT_SYMBOLS


class DatasetImportDialog(QDialog):
    """Dialog for importing a CSV dataset with metadata."""

    def __init__(self, parent=None, default_color_index: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Import Dataset")
        self.setMinimumWidth(500)
        self.setModal(True)

        self._csv_path = ""
        self._default_color_index = default_color_index

        self._setup_ui()

    def _setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)

        # File Selection Group
        file_group = QGroupBox("CSV File")
        file_layout = QHBoxLayout(file_group)

        self._file_path_edit = QLineEdit()
        self._file_path_edit.setPlaceholderText("Select a CSV file...")
        self._file_path_edit.setReadOnly(True)
        file_layout.addWidget(self._file_path_edit)

        self._browse_btn = QPushButton("Browse...")
        self._browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(self._browse_btn)

        layout.addWidget(file_group)

        # Dataset Info Group
        info_group = QGroupBox("Dataset Information")
        info_layout = QFormLayout(info_group)

        # Name
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g., 54mA, Light-Off, ...")
        info_layout.addRow("Name:", self._name_edit)

        # Light Intensity
        self._intensity_spin = QDoubleSpinBox()
        self._intensity_spin.setRange(0, 1000)
        self._intensity_spin.setValue(0)
        self._intensity_spin.setSuffix(" mA")
        self._intensity_spin.setDecimals(1)
        self._intensity_spin.setToolTip("Enter the light intensity for this dataset")
        info_layout.addRow("Light Intensity:", self._intensity_spin)

        # Color
        self._color_combo = QComboBox()
        for i, color in enumerate(DEFAULT_COLORS):
            self._color_combo.addItem(self._color_icon(color), color, color)
        self._color_combo.setCurrentIndex(self._default_color_index % len(DEFAULT_COLORS))
        info_layout.addRow("Color:", self._color_combo)

        # Symbol
        self._symbol_combo = QComboBox()
        symbol_names = ['Circle', 'Square', 'Triangle', 'Diamond', 'Pentagon', 'Hexagon', 'Star', 'Plus']
        for i, (symbol, name) in enumerate(zip(DEFAULT_SYMBOLS, symbol_names)):
            self._symbol_combo.addItem(name, symbol)
        self._symbol_combo.setCurrentIndex(self._default_color_index % len(DEFAULT_SYMBOLS))
        info_layout.addRow("Symbol:", self._symbol_combo)

        layout.addWidget(info_group)

        # Session Link Group (for linking back to original data)
        session_group = QGroupBox("Source Session (Optional)")
        session_layout = QHBoxLayout(session_group)

        self._session_path = ""
        self._session_path_edit = QLineEdit()
        self._session_path_edit.setPlaceholderText("Link to workspace session file (.json)...")
        self._session_path_edit.setReadOnly(True)
        session_layout.addWidget(self._session_path_edit)

        self._session_browse_btn = QPushButton("Browse...")
        self._session_browse_btn.clicked.connect(self._browse_session)
        session_layout.addWidget(self._session_browse_btn)

        layout.addWidget(session_group)

        # Preview Group
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)

        self._preview_label = QLabel("No file selected")
        self._preview_label.setStyleSheet("color: #888; font-size: 11px;")
        self._preview_label.setWordWrap(True)
        preview_layout.addWidget(self._preview_label)

        layout.addWidget(preview_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self._cancel_btn)

        self._import_btn = QPushButton("Import")
        self._import_btn.setEnabled(False)
        self._import_btn.clicked.connect(self._do_import)
        self._import_btn.setDefault(True)
        button_layout.addWidget(self._import_btn)

        layout.addLayout(button_layout)

    def _color_icon(self, color_str: str) -> QIcon:
        """Create a colored square icon for combo box."""
        size = 16
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        color = QColor(color_str)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.darker(120), 1))

        # Draw filled circle
        margin = 2
        painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)

        painter.end()
        return QIcon(pixmap)

    def _browse_file(self):
        """Browse for CSV file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV File",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )

        if path:
            self._csv_path = path
            self._file_path_edit.setText(path)

            # Auto-fill name from filename
            basename = os.path.basename(path)
            name_without_ext = os.path.splitext(basename)[0]
            if not self._name_edit.text():
                self._name_edit.setText(name_without_ext)

            # Preview the file
            self._preview_file(path)

            self._import_btn.setEnabled(True)

    def _browse_session(self):
        """Browse for session file."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Session File",
            "",
            "Session Files (*.json);;All Files (*)"
        )

        if path:
            self._session_path = path
            self._session_path_edit.setText(path)

    def _preview_file(self, path: str):
        """Preview CSV file contents."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                # Read and skip comment lines
                lines = []
                for line in f:
                    stripped = line.strip()
                    if stripped and not stripped.startswith('#'):
                        lines.append(stripped)

                if not lines:
                    self._preview_label.setText("File is empty or contains only comments.")
                    return

                # Parse header
                reader = csv.DictReader(lines)
                columns = reader.fieldnames or []

                # Count rows
                row_count = sum(1 for _ in reader)

                # Show preview
                preview_text = (
                    f"<b>Rows:</b> {row_count}<br>"
                    f"<b>Columns:</b> {len(columns)}<br>"
                    f"<b>Fields:</b> {', '.join(columns[:5])}"
                )
                if len(columns) > 5:
                    preview_text += f" ... (+{len(columns) - 5} more)"

                self._preview_label.setText(preview_text)

        except Exception as e:
            self._preview_label.setText(f"<span style='color: red;'>Error reading file: {e}</span>")

    def _do_import(self):
        """Validate and accept the import."""
        if not self._csv_path:
            QMessageBox.warning(self, "No File", "Please select a CSV file.")
            return

        if not self._name_edit.text().strip():
            QMessageBox.warning(self, "No Name", "Please enter a name for the dataset.")
            return

        self.accept()

    def get_import_params(self) -> dict:
        """Get the import parameters."""
        return {
            'csv_path': self._csv_path,
            'name': self._name_edit.text().strip(),
            'light_intensity_mA': self._intensity_spin.value(),
            'color': self._color_combo.currentData(),
            'symbol': self._symbol_combo.currentData(),
            'session_path': self._session_path,
        }
