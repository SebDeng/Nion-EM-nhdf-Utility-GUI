"""
Metadata panel for displaying nhdf file metadata in a tree view.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QLabel, QLineEdit, QHBoxLayout
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QBrush

from typing import Any, Dict, Optional
from datetime import datetime

from src.core.nhdf_reader import NHDFData


class MetadataPanel(QWidget):
    """Panel for displaying metadata from nhdf files."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: Optional[NHDFData] = None
        self._setup_ui()

    def _setup_ui(self):
        """Set up the metadata panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Search/filter box
        search_layout = QHBoxLayout()
        search_layout.setSpacing(4)

        search_layout.addWidget(QLabel("Filter:"))
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search metadata...")
        self._search_edit.textChanged.connect(self._on_filter_changed)
        search_layout.addWidget(self._search_edit)

        layout.addLayout(search_layout)

        # Tree widget for metadata
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Property", "Value"])
        self._tree.setAlternatingRowColors(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setUniformRowHeights(True)

        # Configure header
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setStretchLastSection(True)

        layout.addWidget(self._tree, 1)

        # Info label at bottom
        self._info_label = QLabel("No file loaded")
        self._info_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self._info_label)

    def set_data(self, data: NHDFData):
        """Set the data and populate metadata tree."""
        self._data = data
        self._populate_tree()
        self._info_label.setText(f"File: {data.file_path.name}")

    def _populate_tree(self):
        """Populate the tree with metadata from current data."""
        self._tree.clear()

        if self._data is None:
            return

        # File Info section
        file_item = QTreeWidgetItem(["File Info"])
        file_item.setFont(0, self._bold_font())
        self._tree.addTopLevelItem(file_item)

        self._add_child(file_item, "Name", self._data.file_path.name)
        self._add_child(file_item, "Path", str(self._data.file_path.parent))
        file_item.setExpanded(True)

        # Data Info section
        data_item = QTreeWidgetItem(["Data Info"])
        data_item.setFont(0, self._bold_font())
        self._tree.addTopLevelItem(data_item)

        self._add_child(data_item, "Shape", str(self._data.shape))
        self._add_child(data_item, "Data Type", str(self._data.dtype))
        self._add_child(data_item, "Dimensions", str(self._data.ndim))
        self._add_child(data_item, "Structure", self._data.data_descriptor.describe())

        if self._data.num_frames > 1:
            self._add_child(data_item, "Number of Frames", str(self._data.num_frames))
            self._add_child(data_item, "Frame Shape", str(self._data.frame_shape))

        data_item.setExpanded(True)

        # Scan Info section (important for understanding the data)
        scan_item = QTreeWidgetItem(["Scan Info"])
        scan_item.setFont(0, self._bold_font())
        self._tree.addTopLevelItem(scan_item)

        # Subscan indicator (highlighted if true)
        is_subscan = self._data.is_subscan
        subscan_child = self._add_child(scan_item, "Is Subscan", "YES" if is_subscan else "No")
        if is_subscan:
            subscan_child.setForeground(1, QBrush(QColor("#ff9800")))  # Orange highlight
            subscan_child.setFont(1, self._bold_font())

        # Actual FOV (calculated from calibrations)
        fov = self._data.actual_fov
        if fov:
            fov_y, fov_x, units = fov
            if fov_y == fov_x:
                self._add_child(scan_item, "Actual FOV", f"{fov_x:.4g} {units}")
            else:
                self._add_child(scan_item, "Actual FOV", f"{fov_x:.4g} x {fov_y:.4g} {units}")

        # Context FOV (from metadata - full scan area)
        context_fov = self._data.context_fov_nm
        if context_fov is not None:
            label = "Context FOV (metadata)" if is_subscan else "FOV (metadata)"
            self._add_child(scan_item, label, f"{context_fov:.4g} nm")

        # Scan center (important for subscans)
        center = self._data.scan_center_nm
        if center:
            self._add_child(scan_item, "Scan Center", f"({center[0]:.4g}, {center[1]:.4g}) nm")

        # Rotation
        rotation = self._data.scan_rotation_deg
        if rotation is not None:
            self._add_child(scan_item, "Rotation", f"{rotation:.2f} deg")

        # Context vs actual size
        scan_info = self._data.scan_info
        if scan_info:
            scan_size = scan_info.get("scan_size")
            context_size = scan_info.get("scan_context_size")
            if scan_size:
                self._add_child(scan_item, "Scan Size", str(scan_size))
            if context_size and is_subscan:
                self._add_child(scan_item, "Context Size", str(context_size))

        scan_item.setExpanded(True)

        # Hardware Info section
        hw_item = QTreeWidgetItem(["Hardware Info"])
        hw_item.setFont(0, self._bold_font())
        self._tree.addTopLevelItem(hw_item)

        channel = self._data.channel_name
        if channel:
            self._add_child(hw_item, "Channel", channel)

        hw_source = self._data.hardware_source
        if hw_source.get("hardware_source_name"):
            self._add_child(hw_item, "Source", hw_source.get("hardware_source_name"))

        pixel_time = self._data.pixel_time_us
        if pixel_time is not None:
            self._add_child(hw_item, "Pixel Time", f"{pixel_time:.4g} us")

        exposure = self._data.exposure_time
        if exposure is not None:
            self._add_child(hw_item, "Exposure", f"{exposure:.4g} s")

        hw_item.setExpanded(True)

        # Timestamp section
        if self._data.timestamp:
            time_item = QTreeWidgetItem(["Timestamp"])
            time_item.setFont(0, self._bold_font())
            self._tree.addTopLevelItem(time_item)

            self._add_child(time_item, "Created", self._data.timestamp.isoformat())
            if self._data.timezone:
                self._add_child(time_item, "Timezone", self._data.timezone)
            if self._data.timezone_offset:
                self._add_child(time_item, "Timezone Offset", self._data.timezone_offset)

            time_item.setExpanded(True)

        # Calibrations section
        cal_item = QTreeWidgetItem(["Calibrations"])
        cal_item.setFont(0, self._bold_font())
        self._tree.addTopLevelItem(cal_item)

        # Intensity calibration
        int_cal = self._data.intensity_calibration
        int_item = QTreeWidgetItem(["Intensity"])
        cal_item.addChild(int_item)
        self._add_child(int_item, "Scale", f"{int_cal.scale}")
        self._add_child(int_item, "Offset", f"{int_cal.offset}")
        self._add_child(int_item, "Units", int_cal.units or "(none)")

        # Dimensional calibrations
        for i, dim_cal in enumerate(self._data.dimensional_calibrations):
            dim_item = QTreeWidgetItem([f"Dimension {i}"])
            cal_item.addChild(dim_item)
            self._add_child(dim_item, "Scale", f"{dim_cal.scale}")
            self._add_child(dim_item, "Offset", f"{dim_cal.offset}")
            self._add_child(dim_item, "Units", dim_cal.units or "(none)")

        cal_item.setExpanded(True)

        # Metadata section (nested)
        if self._data.metadata:
            meta_item = QTreeWidgetItem(["Metadata"])
            meta_item.setFont(0, self._bold_font())
            self._tree.addTopLevelItem(meta_item)
            self._add_dict_items(meta_item, self._data.metadata)
            meta_item.setExpanded(True)

        # Raw Properties (collapsible, for debugging)
        if self._data.raw_properties:
            raw_item = QTreeWidgetItem(["Raw Properties"])
            raw_item.setFont(0, self._bold_font())
            raw_item.setForeground(0, Qt.gray)
            self._tree.addTopLevelItem(raw_item)
            self._add_dict_items(raw_item, self._data.raw_properties)
            raw_item.setExpanded(False)  # Collapsed by default

    def _add_child(self, parent: QTreeWidgetItem, key: str, value: str):
        """Add a child item with key-value pair."""
        item = QTreeWidgetItem([key, value])
        parent.addChild(item)
        return item

    def _add_dict_items(self, parent: QTreeWidgetItem, data: Dict[str, Any], max_depth: int = 10):
        """Recursively add dictionary items to tree."""
        if max_depth <= 0:
            self._add_child(parent, "...", "(max depth reached)")
            return

        for key, value in data.items():
            if isinstance(value, dict):
                dict_item = QTreeWidgetItem([str(key)])
                parent.addChild(dict_item)
                self._add_dict_items(dict_item, value, max_depth - 1)
            elif isinstance(value, list):
                list_item = QTreeWidgetItem([str(key), f"[{len(value)} items]"])
                parent.addChild(list_item)
                for i, item in enumerate(value[:100]):  # Limit to first 100
                    if isinstance(item, dict):
                        item_node = QTreeWidgetItem([f"[{i}]"])
                        list_item.addChild(item_node)
                        self._add_dict_items(item_node, item, max_depth - 1)
                    else:
                        self._add_child(list_item, f"[{i}]", self._format_value(item))
                if len(value) > 100:
                    self._add_child(list_item, "...", f"(+{len(value) - 100} more)")
            else:
                self._add_child(parent, str(key), self._format_value(value))

    def _format_value(self, value: Any) -> str:
        """Format a value for display."""
        if value is None:
            return "(none)"
        if isinstance(value, float):
            if abs(value) < 0.001 or abs(value) > 10000:
                return f"{value:.4e}"
            return f"{value:.6g}"
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (list, tuple)) and len(value) > 10:
            return f"[{len(value)} items]"
        return str(value)

    def _bold_font(self) -> QFont:
        """Get a bold font for section headers."""
        font = QFont()
        font.setBold(True)
        return font

    def _on_filter_changed(self, text: str):
        """Handle filter text change."""
        text = text.lower().strip()

        def set_visibility(item: QTreeWidgetItem, show: bool):
            """Recursively set item visibility."""
            item.setHidden(not show)

        def matches(item: QTreeWidgetItem) -> bool:
            """Check if item or children match filter."""
            if not text:
                return True

            # Check this item's text
            for col in range(item.columnCount()):
                if text in item.text(col).lower():
                    return True

            # Check children
            for i in range(item.childCount()):
                if matches(item.child(i)):
                    return True

            return False

        def filter_item(item: QTreeWidgetItem):
            """Apply filter to item and children."""
            item_matches = matches(item)
            set_visibility(item, item_matches)

            # If item matches, show all children
            if item_matches and text:
                for i in range(item.childCount()):
                    set_visibility(item.child(i), True)
                    item.setExpanded(True)

            # Process children
            for i in range(item.childCount()):
                child = item.child(i)
                filter_item(child)

        # Apply filter to all top-level items
        for i in range(self._tree.topLevelItemCount()):
            filter_item(self._tree.topLevelItem(i))

    def clear(self):
        """Clear the metadata display."""
        self._data = None
        self._tree.clear()
        self._search_edit.clear()
        self._info_label.setText("No file loaded")

    def expand_all(self):
        """Expand all tree items."""
        self._tree.expandAll()

    def collapse_all(self):
        """Collapse all tree items."""
        self._tree.collapseAll()
