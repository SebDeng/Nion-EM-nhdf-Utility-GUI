"""
Node graph widget for visualizing processing tree structure.
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QFontMetrics
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


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
        self.v_spacing = 60  # Vertical spacing between levels
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
        """Draw connections between nodes."""
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


class NodeGraphWidget(QWidget):
    """Widget containing the node graph with scroll support."""

    node_selected = Signal(str)  # Emits node_id on single click
    node_activated = Signal(str)  # Emits node_id on double click

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Header
        header = QLabel("Processing Graph")
        header.setStyleSheet("font-weight: bold;")
        layout.addWidget(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Canvas
        self.canvas = NodeGraphCanvas()
        self.canvas.node_clicked.connect(self.node_selected.emit)
        self.canvas.node_double_clicked.connect(self.node_activated.emit)

        scroll.setWidget(self.canvas)
        layout.addWidget(scroll)

    def add_node(self, node_id: str, name: str, parent_id: Optional[str], params: Dict):
        """Add a node to the graph."""
        self.canvas.add_node(node_id, name, parent_id, params)

    def remove_node(self, node_id: str):
        """Remove a node from the graph."""
        self.canvas.remove_node(node_id)

    def clear_nodes(self):
        """Clear all nodes except root."""
        self.canvas.clear_nodes()

    def select_node(self, node_id: str):
        """Select a node."""
        self.canvas.select_node(node_id)

    def get_selected_node(self) -> Optional[str]:
        """Get the currently selected node."""
        return self.canvas.selected_node
