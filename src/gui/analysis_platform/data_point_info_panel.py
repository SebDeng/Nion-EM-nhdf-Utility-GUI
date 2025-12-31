"""
Data Point Info Panel.

Shows detailed information about a selected data point.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QPushButton, QGridLayout, QApplication
)
from PySide6.QtCore import Qt

from typing import Optional

from .dataset_manager import DatasetManager, Dataset, DataPoint


class DataPointInfoPanel(QWidget):
    """Panel showing details of a selected data point."""

    def __init__(self, dataset_manager: DatasetManager, parent=None):
        super().__init__(parent)
        self._manager = dataset_manager
        self._current_dataset: Optional[Dataset] = None
        self._current_point: Optional[DataPoint] = None

        self._setup_ui()

    def _setup_ui(self):
        """Setup the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header_layout = QHBoxLayout()
        self._title_label = QLabel("Selected Point")
        self._title_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(self._title_label)

        header_layout.addStretch()

        self._copy_btn = QPushButton("Copy")
        self._copy_btn.setToolTip("Copy point info to clipboard")
        self._copy_btn.clicked.connect(self._copy_to_clipboard)
        self._copy_btn.setEnabled(False)
        header_layout.addWidget(self._copy_btn)

        layout.addLayout(header_layout)

        # Info grid
        self._info_group = QGroupBox()
        info_layout = QGridLayout(self._info_group)
        info_layout.setColumnStretch(1, 1)

        # Labels for each field
        self._labels = {}
        fields = [
            ('dataset', 'Dataset:'),
            ('pairing_id', 'Pairing ID:'),
            ('light_intensity', 'Light Intensity:'),
            ('delta_area', 'ΔA:'),
            ('before_area', 'A₀ (before):'),
            ('after_area', 'A₁ (after):'),
            ('sqrt_A0_over_r', '√A₀/r:'),
            ('distance', 'r (distance):'),
            ('before_centroid', 'Centroid (before):'),
            ('after_centroid', 'Centroid (after):'),
            ('before_perp_width', 'Perp Width (before):'),
            ('after_perp_width', 'Perp Width (after):'),
        ]

        for row, (field_id, field_label) in enumerate(fields):
            label = QLabel(field_label)
            label.setStyleSheet("color: #666;")
            info_layout.addWidget(label, row, 0, Qt.AlignRight)

            value_label = QLabel("-")
            value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            info_layout.addWidget(value_label, row, 1)

            self._labels[field_id] = value_label

        layout.addWidget(self._info_group)
        layout.addStretch()

    def set_point(self, dataset_id: str, pairing_id: str):
        """Set the displayed point."""
        result = self._manager.get_point_by_id(pairing_id)

        if not result:
            self.clear()
            return

        dataset, point = result
        self._current_dataset = dataset
        self._current_point = point

        # Update labels
        self._labels['dataset'].setText(dataset.name)
        self._labels['pairing_id'].setText(point.pairing_id)
        self._labels['light_intensity'].setText(f"{dataset.light_intensity_mA:.1f} mA")
        self._labels['delta_area'].setText(f"{point.delta_area_nm2:.4f} nm²")
        self._labels['before_area'].setText(f"{point.before_area_nm2:.4f} nm²")
        self._labels['after_area'].setText(f"{point.after_area_nm2:.4f} nm²")
        self._labels['sqrt_A0_over_r'].setText(f"{point.sqrt_A0_over_r:.6f}")
        self._labels['distance'].setText(f"{point.distance_to_center_nm:.2f} nm")
        self._labels['before_centroid'].setText(f"({point.before_centroid_x:.1f}, {point.before_centroid_y:.1f})")
        self._labels['after_centroid'].setText(f"({point.after_centroid_x:.1f}, {point.after_centroid_y:.1f})")
        self._labels['before_perp_width'].setText(f"{point.before_perp_width_nm:.4f} nm")
        self._labels['after_perp_width'].setText(f"{point.after_perp_width_nm:.4f} nm")

        self._title_label.setText(f"Selected: {point.pairing_id}")
        self._copy_btn.setEnabled(True)

    def clear(self):
        """Clear the displayed point."""
        self._current_dataset = None
        self._current_point = None

        for label in self._labels.values():
            label.setText("-")

        self._title_label.setText("Selected Point")
        self._copy_btn.setEnabled(False)

    def _copy_to_clipboard(self):
        """Copy point info to clipboard."""
        if not self._current_point or not self._current_dataset:
            return

        point = self._current_point
        dataset = self._current_dataset

        text = (
            f"Dataset: {dataset.name}\n"
            f"Light Intensity: {dataset.light_intensity_mA:.1f} mA\n"
            f"Pairing ID: {point.pairing_id}\n"
            f"ΔA: {point.delta_area_nm2:.4f} nm²\n"
            f"A₀: {point.before_area_nm2:.4f} nm²\n"
            f"A₁: {point.after_area_nm2:.4f} nm²\n"
            f"√A₀/r: {point.sqrt_A0_over_r:.6f}\n"
            f"r: {point.distance_to_center_nm:.2f} nm\n"
            f"Centroid (before): ({point.before_centroid_x:.1f}, {point.before_centroid_y:.1f})\n"
            f"Centroid (after): ({point.after_centroid_x:.1f}, {point.after_centroid_y:.1f})\n"
            f"Perp Width (before): {point.before_perp_width_nm:.4f} nm\n"
            f"Perp Width (after): {point.after_perp_width_nm:.4f} nm\n"
        )

        clipboard = QApplication.clipboard()
        clipboard.setText(text)
