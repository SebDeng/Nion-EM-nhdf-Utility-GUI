"""
Node graph widget for visualizing processing tree structure.
Approach 1+5: Details panel + Edge labels
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QFrame, QSplitter, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QFontMetrics
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


def compute_param_diff(parent_params: Dict, child_params: Dict) -> Dict:
    """
    Compute the difference between parent and child parameters.
    Returns a dict with only the changed parameters.
    """
    diff = {}

    # Default values for each parameter
    defaults = {
        'brightness': 0,
        'contrast': 1.0,
        'gamma': 1.0,
        'gaussian_enabled': False,
        'gaussian_sigma': 0,
        'median_enabled': False,
        'median_size': 3,
        'unsharp_enabled': False,
        'unsharp_amount': 0.5,
        'unsharp_radius': 1.0,
        'bandpass_enabled': False,
        'bandpass_large': 40,
        'bandpass_small': 3,
    }

    # All possible parameter keys
    all_keys = set(defaults.keys()) | set(parent_params.keys()) | set(child_params.keys())

    for key in all_keys:
        default = defaults.get(key, None)
        parent_val = parent_params.get(key, default)
        child_val = child_params.get(key, default)

        # Check if value changed
        if parent_val != child_val:
            diff[key] = {
                'from': parent_val,
                'to': child_val
            }

    return diff


def get_edge_label(parent_params: Dict, child_params: Dict) -> str:
    """Generate a short label for the edge showing what changed."""
    diff = compute_param_diff(parent_params, child_params)
    if not diff:
        return ""

    parts = []

    # Basic adjustments
    if 'brightness' in diff:
        val = diff['brightness']['to']
        if val != 0:
            parts.append(f"B{val:+d}")

    if 'contrast' in diff:
        val = diff['contrast']['to']
        if val != 1.0:
            parts.append(f"C{val:.1f}")

    if 'gamma' in diff:
        val = diff['gamma']['to']
        if val != 1.0:
            parts.append(f"γ{val:.1f}")

    # Filters (abbreviated)
    if diff.get('gaussian_enabled', {}).get('to', False):
        parts.append("Gauss")
    if diff.get('median_enabled', {}).get('to', False):
        parts.append("Med")
    if diff.get('unsharp_enabled', {}).get('to', False):
        parts.append("Sharp")
    if diff.get('bandpass_enabled', {}).get('to', False):
        parts.append("BP")

    return ", ".join(parts) if parts else ""


def format_diff_for_details(parent_params: Dict, child_params: Dict, parent_name: str) -> str:
    """Format the diff as detailed text for the details panel."""
    diff = compute_param_diff(parent_params, child_params)

    lines = [f"Changes from {parent_name}:", "─" * 25]

    if not diff:
        lines.append("No changes")
        return "\n".join(lines)

    # Basic adjustments
    if 'brightness' in diff:
        from_val = diff['brightness']['from']
        to_val = diff['brightness']['to']
        lines.append(f"Brightness: {from_val} → {to_val}")

    if 'contrast' in diff:
        from_val = diff['contrast']['from']
        to_val = diff['contrast']['to']
        lines.append(f"Contrast: {from_val:.2f} → {to_val:.2f}")

    if 'gamma' in diff:
        from_val = diff['gamma']['from']
        to_val = diff['gamma']['to']
        lines.append(f"Gamma: {from_val:.2f} → {to_val:.2f}")

    # Filters
    if diff.get('gaussian_enabled', {}).get('to', False):
        sigma = child_params.get('gaussian_sigma', 0)
        lines.append(f"+ Gaussian Blur (σ={sigma}px)")
    elif diff.get('gaussian_enabled', {}).get('from', False):
        lines.append("- Gaussian Blur (disabled)")

    if diff.get('median_enabled', {}).get('to', False):
        size = child_params.get('median_size', 3)
        lines.append(f"+ Median Filter ({size}px)")
    elif diff.get('median_enabled', {}).get('from', False):
        lines.append("- Median Filter (disabled)")

    if diff.get('unsharp_enabled', {}).get('to', False):
        amt = child_params.get('unsharp_amount', 0.5)
        rad = child_params.get('unsharp_radius', 1.0)
        lines.append(f"+ Unsharp Mask (amt={amt:.1f}, r={rad})")
    elif diff.get('unsharp_enabled', {}).get('from', False):
        lines.append("- Unsharp Mask (disabled)")

    if diff.get('bandpass_enabled', {}).get('to', False):
        large = child_params.get('bandpass_large', 40)
        small = child_params.get('bandpass_small', 3)
        lines.append(f"+ Bandpass Filter ({small}-{large}px)")
    elif diff.get('bandpass_enabled', {}).get('from', False):
        lines.append("- Bandpass Filter (disabled)")

    return "\n".join(lines)


@dataclass
class NodeData:
    """Data for a single node in the graph."""
    id: str
    name: str
    parent_id: Optional[str]
    params: Dict
    x: float = 0
    y: float = 0
    width: float = 120
    height: float = 50


class NodeGraphCanvas(QWidget):
    """Canvas widget that draws the node graph."""

    node_clicked = Signal(str)  # Emits node_id
    node_double_clicked = Signal(str)  # Emits node_id

    def __init__(self, parent=None):
        super().__init__(parent)

        self.nodes: Dict[str, NodeData] = {}
        self.selected_node: Optional[str] = None
        self.hovered_node: Optional[str] = None

        # Layout settings
        self.node_width = 120
        self.node_height = 50
        self.h_spacing = 40  # Horizontal spacing between nodes
        self.v_spacing = 80  # Vertical spacing between levels (increased for edge labels)
        self.padding = 20

        # Add root node
        self._add_root_node()

        self.setMouseTracking(True)
        self.setMinimumHeight(200)

    def _add_root_node(self):
        """Add the root 'Original' node."""
        self.nodes['root'] = NodeData(
            id='root',
            name='Original',
            parent_id=None,
            params={},
            x=0, y=0,
            width=self.node_width,
            height=self.node_height
        )
        self._layout_nodes()

    def add_node(self, node_id: str, name: str, parent_id: Optional[str], params: Dict):
        """Add a node to the graph."""
        self.nodes[node_id] = NodeData(
            id=node_id,
            name=name,
            parent_id=parent_id if parent_id else 'root',
            params=params,
            width=self.node_width,
            height=self.node_height
        )
        self._layout_nodes()
        self.update()

    def remove_node(self, node_id: str):
        """Remove a node and its children from the graph."""
        if node_id in self.nodes and node_id != 'root':
            # Find and remove children recursively
            children_to_remove = [nid for nid, node in self.nodes.items()
                                  if node.parent_id == node_id]
            for child_id in children_to_remove:
                self.remove_node(child_id)

            del self.nodes[node_id]
            self._layout_nodes()
            self.update()

    def clear_nodes(self):
        """Clear all nodes except root."""
        self.nodes = {'root': self.nodes.get('root', NodeData(
            id='root', name='Original', parent_id=None, params={},
            width=self.node_width, height=self.node_height
        ))}
        self.selected_node = None
        self._layout_nodes()
        self.update()

    def select_node(self, node_id: str):
        """Select a node."""
        if node_id in self.nodes:
            self.selected_node = node_id
            self.update()

    def _layout_nodes(self):
        """Layout nodes in a tree structure."""
        if not self.nodes:
            return

        # Build tree structure
        children: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for node_id, node in self.nodes.items():
            if node.parent_id and node.parent_id in children:
                children[node.parent_id].append(node_id)

        # Calculate positions using BFS
        levels: Dict[str, int] = {}
        positions_at_level: Dict[int, List[str]] = {}

        # Start from root
        queue = [('root', 0)]
        while queue:
            node_id, level = queue.pop(0)
            if node_id not in self.nodes:
                continue

            levels[node_id] = level
            if level not in positions_at_level:
                positions_at_level[level] = []
            positions_at_level[level].append(node_id)

            for child_id in children.get(node_id, []):
                queue.append((child_id, level + 1))

        # Position nodes
        max_width = 0
        for level, node_ids in positions_at_level.items():
            total_width = len(node_ids) * (self.node_width + self.h_spacing) - self.h_spacing
            max_width = max(max_width, total_width)

        for level, node_ids in positions_at_level.items():
            num_nodes = len(node_ids)
            total_width = num_nodes * (self.node_width + self.h_spacing) - self.h_spacing
            start_x = (max_width - total_width) / 2 + self.padding

            for i, node_id in enumerate(node_ids):
                if node_id in self.nodes:
                    self.nodes[node_id].x = start_x + i * (self.node_width + self.h_spacing)
                    self.nodes[node_id].y = self.padding + level * (self.node_height + self.v_spacing)

        # Update widget size
        max_y = max((n.y + n.height for n in self.nodes.values()), default=100)
        self.setMinimumSize(int(max_width + 2 * self.padding), int(max_y + self.padding))

    def paintEvent(self, event):
        """Draw the node graph."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get colors from palette for theme support
        palette = self.palette()
        bg_color = palette.window().color()
        text_color = palette.windowText().color()
        highlight_color = palette.highlight().color()

        # Fill background
        painter.fillRect(self.rect(), bg_color)

        # Draw connections first (behind nodes)
        self._draw_connections(painter, text_color)

        # Draw nodes
        for node_id, node in self.nodes.items():
            self._draw_node(painter, node, text_color, highlight_color)

        painter.end()

    def _draw_connections(self, painter: QPainter, line_color: QColor):
        """Draw connections between nodes with edge labels."""
        pen = QPen(line_color)
        pen.setWidth(2)
        painter.setPen(pen)

        for node_id, node in self.nodes.items():
            if node.parent_id and node.parent_id in self.nodes:
                parent = self.nodes[node.parent_id]

                # Draw bezier curve from parent bottom to child top
                start = QPointF(parent.x + parent.width / 2, parent.y + parent.height)
                end = QPointF(node.x + node.width / 2, node.y)

                # Control points for smooth curve
                ctrl1 = QPointF(start.x(), start.y() + self.v_spacing / 2)
                ctrl2 = QPointF(end.x(), end.y() - self.v_spacing / 2)

                path = QPainterPath()
                path.moveTo(start)
                path.cubicTo(ctrl1, ctrl2, end)

                painter.drawPath(path)

                # Draw arrow head
                self._draw_arrow(painter, ctrl2, end)

                # Draw edge label showing changes
                edge_label = get_edge_label(parent.params, node.params)
                if edge_label:
                    # Position label at midpoint of edge
                    mid_x = (start.x() + end.x()) / 2
                    mid_y = (start.y() + end.y()) / 2

                    # Draw label background
                    label_font = QFont()
                    label_font.setPointSize(8)
                    painter.setFont(label_font)

                    fm = QFontMetrics(label_font)
                    label_width = fm.horizontalAdvance(edge_label) + 8
                    label_height = fm.height() + 4

                    # Get background color from palette
                    bg_color = self.palette().window().color()
                    label_rect = QRectF(
                        mid_x - label_width / 2,
                        mid_y - label_height / 2,
                        label_width,
                        label_height
                    )

                    # Draw background with slight transparency
                    painter.setPen(Qt.NoPen)
                    bg_with_alpha = QColor(bg_color)
                    bg_with_alpha.setAlpha(230)
                    painter.setBrush(QBrush(bg_with_alpha))
                    painter.drawRoundedRect(label_rect, 4, 4)

                    # Draw border
                    border_pen = QPen(QColor(100, 150, 200))
                    border_pen.setWidth(1)
                    painter.setPen(border_pen)
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRoundedRect(label_rect, 4, 4)

                    # Draw label text
                    painter.setPen(QPen(QColor(100, 180, 255)))  # Light blue text
                    painter.drawText(label_rect, Qt.AlignCenter, edge_label)

                    # Reset pen for next connection
                    pen = QPen(line_color)
                    pen.setWidth(2)
                    painter.setPen(pen)

    def _draw_arrow(self, painter: QPainter, from_point: QPointF, to_point: QPointF):
        """Draw an arrow head at the end of a line."""
        import math

        arrow_size = 8
        angle = math.atan2(to_point.y() - from_point.y(), to_point.x() - from_point.x())

        p1 = QPointF(
            to_point.x() - arrow_size * math.cos(angle - math.pi / 6),
            to_point.y() - arrow_size * math.sin(angle - math.pi / 6)
        )
        p2 = QPointF(
            to_point.x() - arrow_size * math.cos(angle + math.pi / 6),
            to_point.y() - arrow_size * math.sin(angle + math.pi / 6)
        )

        path = QPainterPath()
        path.moveTo(to_point)
        path.lineTo(p1)
        path.lineTo(p2)
        path.closeSubpath()

        painter.fillPath(path, painter.pen().color())

    def _draw_node(self, painter: QPainter, node: NodeData, text_color: QColor, highlight_color: QColor):
        """Draw a single node."""
        rect = QRectF(node.x, node.y, node.width, node.height)

        # Determine colors based on state
        is_selected = node.id == self.selected_node
        is_hovered = node.id == self.hovered_node
        is_root = node.id == 'root'

        # Node colors
        if is_root:
            fill_color = QColor(70, 130, 180)  # Steel blue for root
        elif is_selected:
            fill_color = highlight_color
        elif is_hovered:
            fill_color = QColor(100, 100, 100)
        else:
            fill_color = QColor(80, 80, 80)

        # Draw node rectangle with rounded corners
        painter.setPen(QPen(text_color, 2 if is_selected else 1))
        painter.setBrush(QBrush(fill_color))
        painter.drawRoundedRect(rect, 8, 8)

        # Draw node name
        font = QFont()
        font.setPointSize(10)
        if is_root:
            font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(Qt.white if fill_color.lightness() < 128 else Qt.black))

        # Truncate name if too long
        fm = QFontMetrics(font)
        name = node.name
        if fm.horizontalAdvance(name) > node.width - 10:
            while fm.horizontalAdvance(name + "...") > node.width - 10 and len(name) > 0:
                name = name[:-1]
            name += "..."

        painter.drawText(rect, Qt.AlignCenter, name)

        # Draw parameter indicators (small dots for each applied param)
        if node.params:
            indicator_y = node.y + node.height - 8
            indicator_x = node.x + 5
            dot_size = 4

            colors = [
                QColor(255, 100, 100),  # Brightness
                QColor(100, 255, 100),  # Contrast
                QColor(100, 100, 255),  # Gamma
                QColor(255, 255, 100),  # Filter
            ]

            param_keys = ['brightness', 'contrast', 'gamma']
            for i, key in enumerate(param_keys):
                if key in node.params and node.params[key] != (0 if key == 'brightness' else 1.0):
                    painter.setBrush(QBrush(colors[i]))
                    painter.setPen(Qt.NoPen)
                    painter.drawEllipse(QPointF(indicator_x + i * (dot_size + 3), indicator_y), dot_size / 2, dot_size / 2)

    def mousePressEvent(self, event):
        """Handle mouse press."""
        if event.button() == Qt.LeftButton:
            node_id = self._node_at(event.pos())
            if node_id:
                self.selected_node = node_id
                self.node_clicked.emit(node_id)
                self.update()

    def mouseDoubleClickEvent(self, event):
        """Handle mouse double-click."""
        if event.button() == Qt.LeftButton:
            node_id = self._node_at(event.pos())
            if node_id:
                self.node_double_clicked.emit(node_id)

    def mouseMoveEvent(self, event):
        """Handle mouse move for hover effects."""
        node_id = self._node_at(event.pos())
        if node_id != self.hovered_node:
            self.hovered_node = node_id
            self.update()

            # Update tooltip
            if node_id and node_id in self.nodes:
                node = self.nodes[node_id]
                tooltip = f"{node.name}"
                if node.params:
                    if node.params.get('brightness', 0) != 0:
                        tooltip += f"\nBrightness: {node.params['brightness']}"
                    if node.params.get('contrast', 1.0) != 1.0:
                        tooltip += f"\nContrast: {node.params['contrast']:.2f}"
                    if node.params.get('gamma', 1.0) != 1.0:
                        tooltip += f"\nGamma: {node.params['gamma']:.2f}"
                self.setToolTip(tooltip)
            else:
                self.setToolTip("")

    def _node_at(self, pos) -> Optional[str]:
        """Get the node at the given position."""
        for node_id, node in self.nodes.items():
            rect = QRectF(node.x, node.y, node.width, node.height)
            if rect.contains(pos.x(), pos.y()):
                return node_id
        return None


class SnapshotDetailsPanel(QFrame):
    """Panel showing detailed diff information for the selected snapshot."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.StyledPanel)
        self.setMinimumHeight(80)
        self.setMaximumHeight(150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Header
        self.header_label = QLabel("Snapshot Details")
        self.header_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        layout.addWidget(self.header_label)

        # Details text
        self.details_label = QLabel("Select a snapshot to see details")
        self.details_label.setWordWrap(True)
        self.details_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.details_label.setStyleSheet("font-size: 10px; color: #888;")
        layout.addWidget(self.details_label, 1)

    def update_details(self, node_name: str, parent_name: str, params: Dict, parent_params: Dict):
        """Update the details panel with node information."""
        self.header_label.setText(f"📌 {node_name}")

        if not parent_params and not params:
            self.details_label.setText("Original image (no processing applied)")
            self.details_label.setStyleSheet("font-size: 10px; color: #888;")
            return

        diff_text = format_diff_for_details(parent_params, params, parent_name)
        self.details_label.setText(diff_text)
        self.details_label.setStyleSheet("font-size: 10px; color: #ccc;")

    def clear_details(self):
        """Clear the details panel."""
        self.header_label.setText("Snapshot Details")
        self.details_label.setText("Select a snapshot to see details")
        self.details_label.setStyleSheet("font-size: 10px; color: #888;")


class NodeGraphWidget(QWidget):
    """Widget containing the node graph with scroll support and details panel."""

    node_selected = Signal(str)  # Emits node_id on single click
    node_activated = Signal(str)  # Emits node_id on double click

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Header
        header = QLabel("Processing Graph")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        # Splitter for graph and details
        splitter = QSplitter(Qt.Vertical)

        # Scroll area for graph
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Canvas
        self.canvas = NodeGraphCanvas()
        self.canvas.node_clicked.connect(self._on_node_clicked)
        self.canvas.node_double_clicked.connect(self.node_activated.emit)

        scroll.setWidget(self.canvas)
        splitter.addWidget(scroll)

        # Details panel
        self.details_panel = SnapshotDetailsPanel()
        splitter.addWidget(self.details_panel)

        # Set initial sizes (graph takes more space)
        splitter.setSizes([200, 100])

        layout.addWidget(splitter)

    def _on_node_clicked(self, node_id: str):
        """Handle node click - update details panel."""
        self.node_selected.emit(node_id)

        if node_id and node_id in self.canvas.nodes:
            node = self.canvas.nodes[node_id]

            if node_id == 'root':
                self.details_panel.update_details("Original", "", {}, {})
            else:
                parent_params = {}
                parent_name = "Original"
                if node.parent_id and node.parent_id in self.canvas.nodes:
                    parent_name = self.canvas.nodes[node.parent_id].name
                    parent_params = self.canvas.nodes[node.parent_id].params

                self.details_panel.update_details(
                    node.name,
                    parent_name,
                    node.params,
                    parent_params
                )
        else:
            self.details_panel.clear_details()

    def add_node(self, node_id: str, name: str, parent_id: Optional[str], params: Dict):
        """Add a node to the graph."""
        self.canvas.add_node(node_id, name, parent_id, params)

    def remove_node(self, node_id: str):
        """Remove a node from the graph."""
        self.canvas.remove_node(node_id)

    def clear_nodes(self):
        """Clear all nodes except root."""
        self.canvas.clear_nodes()
        self.details_panel.clear_details()

    def select_node(self, node_id: str):
        """Select a node."""
        self.canvas.select_node(node_id)
        # Also update details panel
        self._on_node_clicked(node_id)

    def get_selected_node(self) -> Optional[str]:
        """Get the currently selected node."""
        return self.canvas.selected_node
