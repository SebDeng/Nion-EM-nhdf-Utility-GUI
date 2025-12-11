"""
2D Material Atom Calculator.

Calculates the number of atoms in a given area for various 2D materials
like MoS2, WS2, graphene, etc.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QDoubleSpinBox, QComboBox, QPushButton,
    QGroupBox, QFrame, QRadioButton, QButtonGroup
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from typing import Optional, Dict, Any
import math


# 2D Materials database
# a: lattice constant in nm
# formula: atoms per unit cell
MATERIALS_2D = {
    'MoS2': {
        'a': 0.316,  # nm
        'formula': {'Mo': 1, 'S': 2},
        'description': 'Molybdenum disulfide'
    },
    'WS2': {
        'a': 0.315,
        'formula': {'W': 1, 'S': 2},
        'description': 'Tungsten disulfide'
    },
    'WSe2': {
        'a': 0.328,
        'formula': {'W': 1, 'Se': 2},
        'description': 'Tungsten diselenide'
    },
    'MoSe2': {
        'a': 0.329,
        'formula': {'Mo': 1, 'Se': 2},
        'description': 'Molybdenum diselenide'
    },
    'Graphene': {
        'a': 0.246,
        'formula': {'C': 2},  # 2 carbon atoms per hexagonal unit cell
        'description': 'Monolayer graphene'
    },
    'hBN': {
        'a': 0.250,
        'formula': {'B': 1, 'N': 1},
        'description': 'Hexagonal boron nitride'
    },
}


def calculate_hexagonal_unit_cell_area(a: float) -> float:
    """
    Calculate the area of a hexagonal unit cell.

    Args:
        a: Lattice constant in nm

    Returns:
        Area in nm²
    """
    # Area = (√3/2) × a²
    return (math.sqrt(3) / 2) * (a ** 2)


def calculate_atoms_in_area(material: str, area_nm2: float) -> Dict[str, Any]:
    """
    Calculate the number of atoms in a given area for a 2D material.

    Args:
        material: Material name (key in MATERIALS_2D)
        area_nm2: Area in nm²

    Returns:
        Dictionary with calculation results
    """
    if material not in MATERIALS_2D:
        return None

    mat_data = MATERIALS_2D[material]
    a = mat_data['a']
    formula = mat_data['formula']

    # Calculate unit cell area
    unit_cell_area = calculate_hexagonal_unit_cell_area(a)

    # Number of unit cells in the area
    num_unit_cells = area_nm2 / unit_cell_area

    # Calculate atoms for each element
    atoms = {}
    total_atoms = 0
    for element, count_per_cell in formula.items():
        atom_count = num_unit_cells * count_per_cell
        atoms[element] = atom_count
        total_atoms += atom_count

    return {
        'material': material,
        'area_nm2': area_nm2,
        'area_A2': area_nm2 * 100,  # Convert to Ų
        'lattice_constant_nm': a,
        'unit_cell_area_nm2': unit_cell_area,
        'num_unit_cells': num_unit_cells,
        'atoms': atoms,
        'total_atoms': total_atoms,
        'description': mat_data['description']
    }


class MaterialCalculatorDialog(QDialog):
    """
    Dialog for calculating atom counts in 2D materials.
    """

    # Signal emitted when user wants to add result to panel
    add_to_panel = Signal(dict)  # Emits calculation result

    def __init__(self, frame_area_nm2: Optional[float] = None, parent=None):
        super().__init__(parent)
        self._frame_area_nm2 = frame_area_nm2
        self._last_result: Optional[Dict[str, Any]] = None

        self.setWindowTitle("2D Material Atom Calculator")
        self.setMinimumWidth(420)

        self._setup_ui()
        self._on_calculate()

    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title
        title = QLabel("2D Material Atom Calculator")
        title.setFont(QFont("sans-serif", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Material Selection Group
        material_group = QGroupBox("Material")
        material_layout = QHBoxLayout(material_group)

        material_layout.addWidget(QLabel("Select Material:"))
        self._material_combo = QComboBox()
        for mat_name, mat_data in MATERIALS_2D.items():
            self._material_combo.addItem(f"{mat_name} - {mat_data['description']}", mat_name)
        self._material_combo.currentIndexChanged.connect(self._on_calculate)
        material_layout.addWidget(self._material_combo, 1)

        layout.addWidget(material_group)

        # Area Input Group
        area_group = QGroupBox("Area")
        area_layout = QGridLayout(area_group)

        # Unit selection
        self._unit_group = QButtonGroup(self)
        self._nm2_radio = QRadioButton("nm²")
        self._A2_radio = QRadioButton("Ų")
        self._nm2_radio.setChecked(True)
        self._unit_group.addButton(self._nm2_radio)
        self._unit_group.addButton(self._A2_radio)
        self._nm2_radio.toggled.connect(self._on_unit_changed)

        area_layout.addWidget(QLabel("Units:"), 0, 0)
        unit_layout = QHBoxLayout()
        unit_layout.addWidget(self._nm2_radio)
        unit_layout.addWidget(self._A2_radio)
        unit_layout.addStretch()
        area_layout.addLayout(unit_layout, 0, 1)

        # Area input
        area_layout.addWidget(QLabel("Area:"), 1, 0)
        self._area_spin = QDoubleSpinBox()
        self._area_spin.setRange(0.001, 1e12)
        self._area_spin.setDecimals(3)
        self._area_spin.setValue(100.0)  # Default 100 nm²
        self._area_spin.setSuffix(" nm²")
        self._area_spin.valueChanged.connect(self._on_calculate)
        area_layout.addWidget(self._area_spin, 1, 1)

        # Use frame area button
        self._use_frame_btn = QPushButton("Use Frame Area")
        self._use_frame_btn.setToolTip("Use the area from the current image frame")
        self._use_frame_btn.clicked.connect(self._on_use_frame_area)
        self._use_frame_btn.setEnabled(self._frame_area_nm2 is not None)
        area_layout.addWidget(self._use_frame_btn, 2, 1)

        if self._frame_area_nm2 is not None:
            frame_info = QLabel(f"Frame area: {self._frame_area_nm2:.2e} nm²")
            frame_info.setStyleSheet("color: #888; font-size: 11px;")
            area_layout.addWidget(frame_info, 3, 1)

        layout.addWidget(area_group)

        # Crystal Info Group
        crystal_group = QGroupBox("Crystal Structure Info")
        crystal_layout = QGridLayout(crystal_group)

        crystal_layout.addWidget(QLabel("Lattice Constant (a):"), 0, 0)
        self._lattice_label = QLabel("--")
        self._lattice_label.setStyleSheet("font-family: monospace;")
        crystal_layout.addWidget(self._lattice_label, 0, 1)

        crystal_layout.addWidget(QLabel("Unit Cell Area:"), 1, 0)
        self._unit_cell_label = QLabel("--")
        self._unit_cell_label.setStyleSheet("font-family: monospace;")
        crystal_layout.addWidget(self._unit_cell_label, 1, 1)

        crystal_layout.addWidget(QLabel("Number of Unit Cells:"), 2, 0)
        self._num_cells_label = QLabel("--")
        self._num_cells_label.setStyleSheet("font-family: monospace; font-weight: bold;")
        crystal_layout.addWidget(self._num_cells_label, 2, 1)

        layout.addWidget(crystal_group)

        # Results Group
        results_group = QGroupBox("Atom Counts")
        self._results_layout = QGridLayout(results_group)
        self._results_layout.setColumnStretch(1, 1)

        # Will be populated dynamically
        self._atom_labels = {}

        layout.addWidget(results_group)

        # Formula info
        formula_frame = QFrame()
        formula_frame.setFrameStyle(QFrame.StyledPanel)
        formula_layout = QVBoxLayout(formula_frame)
        formula_layout.setContentsMargins(8, 8, 8, 8)

        formula_title = QLabel("Formula:")
        formula_title.setStyleSheet("font-weight: bold;")
        formula_layout.addWidget(formula_title)

        formula_text = QLabel(
            "• Unit cell area = (√3/2) × a²\n"
            "• Unit cells = Area / Unit cell area\n"
            "• Atoms = Unit cells × Atoms per cell"
        )
        formula_text.setStyleSheet("font-size: 11px; color: #888;")
        formula_layout.addWidget(formula_text)

        layout.addWidget(formula_frame)

        # Buttons
        button_layout = QHBoxLayout()

        self._add_to_panel_btn = QPushButton("Add to Panel")
        self._add_to_panel_btn.setToolTip("Add atom count as floating label on the image panel")
        self._add_to_panel_btn.clicked.connect(self._on_add_to_panel)
        button_layout.addWidget(self._add_to_panel_btn)

        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _on_unit_changed(self):
        """Handle unit radio button change."""
        if self._nm2_radio.isChecked():
            # Convert current value from Ų to nm²
            current_A2 = self._area_spin.value()
            self._area_spin.blockSignals(True)
            self._area_spin.setSuffix(" nm²")
            self._area_spin.setValue(current_A2 / 100)
            self._area_spin.blockSignals(False)
        else:
            # Convert current value from nm² to Ų
            current_nm2 = self._area_spin.value()
            self._area_spin.blockSignals(True)
            self._area_spin.setSuffix(" Ų")
            self._area_spin.setValue(current_nm2 * 100)
            self._area_spin.blockSignals(False)

        self._on_calculate()

    def _on_use_frame_area(self):
        """Use the frame area from the current image."""
        if self._frame_area_nm2 is not None:
            if self._nm2_radio.isChecked():
                self._area_spin.setValue(self._frame_area_nm2)
            else:
                self._area_spin.setValue(self._frame_area_nm2 * 100)

    def _on_calculate(self):
        """Calculate atom counts."""
        material = self._material_combo.currentData()

        # Get area in nm²
        if self._nm2_radio.isChecked():
            area_nm2 = self._area_spin.value()
        else:
            area_nm2 = self._area_spin.value() / 100  # Convert Ų to nm²

        result = calculate_atoms_in_area(material, area_nm2)
        if result is None:
            return

        self._last_result = result
        self._update_display(result)

    def _update_display(self, result: Dict[str, Any]):
        """Update the display with calculation results."""
        # Update crystal info
        a = result['lattice_constant_nm']
        self._lattice_label.setText(f"{a:.3f} nm ({a*10:.2f} Å)")

        uc_area = result['unit_cell_area_nm2']
        self._unit_cell_label.setText(f"{uc_area:.4f} nm² ({uc_area*100:.2f} Ų)")

        num_cells = result['num_unit_cells']
        self._num_cells_label.setText(f"{num_cells:.3e}")

        # Clear existing atom labels
        for label in self._atom_labels.values():
            label.setParent(None)
            label.deleteLater()
        self._atom_labels.clear()

        # Add atom count labels
        row = 0
        atoms = result['atoms']

        # Define colors for different elements
        colors = {
            'S': '#ffaa4a',   # Orange for sulfur
            'Se': '#ff6a9e',  # Pink for selenium
            'Mo': '#4a9eff',  # Blue for molybdenum
            'W': '#9e4aff',   # Purple for tungsten
            'C': '#4aff9e',   # Green for carbon
            'B': '#ff4a4a',   # Red for boron
            'N': '#4affff',   # Cyan for nitrogen
        }

        for element, count in atoms.items():
            # Element label
            elem_label = QLabel(f"{element} atoms:")
            self._results_layout.addWidget(elem_label, row, 0)

            # Count label
            color = colors.get(element, '#ffffff')
            count_label = QLabel(f"{count:.3e}")
            count_label.setStyleSheet(f"font-family: monospace; font-weight: bold; color: {color};")
            self._results_layout.addWidget(count_label, row, 1)

            self._atom_labels[f"{element}_elem"] = elem_label
            self._atom_labels[f"{element}_count"] = count_label
            row += 1

        # Total atoms
        total_elem = QLabel("Total atoms:")
        total_elem.setStyleSheet("font-weight: bold;")
        self._results_layout.addWidget(total_elem, row, 0)

        total_count = QLabel(f"{result['total_atoms']:.3e}")
        total_count.setStyleSheet("font-family: monospace; font-weight: bold; font-size: 12px;")
        self._results_layout.addWidget(total_count, row, 1)

        self._atom_labels['total_elem'] = total_elem
        self._atom_labels['total_count'] = total_count

    def _on_add_to_panel(self):
        """Handle add to panel button click."""
        if self._last_result:
            self.add_to_panel.emit(self._last_result)

    def set_frame_area(self, area_nm2: float):
        """Set the frame area from external source."""
        self._frame_area_nm2 = area_nm2
        self._use_frame_btn.setEnabled(True)

    def get_last_result(self) -> Optional[Dict[str, Any]]:
        """Get the last calculation result."""
        return self._last_result
