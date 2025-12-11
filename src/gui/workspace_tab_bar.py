"""
Workspace Tab Bar widget for switching between workspaces.

Provides an Excel-like tab interface at the bottom of the workspace area
for easy navigation between multiple workspaces.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QMenu, QInputDialog,
    QMessageBox, QSizePolicy, QScrollArea, QFrame
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QAction, QMouseEvent

from typing import Optional, List, Dict


class WorkspaceTab(QPushButton):
    """Individual workspace tab button."""

    # Signals
    close_requested = Signal(str)  # workspace uuid
    rename_requested = Signal(str)  # workspace uuid
    clone_requested = Signal(str)  # workspace uuid

    def __init__(self, workspace_uuid: str, name: str, parent=None):
        super().__init__(name, parent)
        self._uuid = workspace_uuid
        self._is_current = False
        self._is_dark_mode = True

        self.setCheckable(True)
        self.setMinimumWidth(80)
        self.setMaximumWidth(200)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        # Enable context menu
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._update_style()

    @property
    def workspace_uuid(self) -> str:
        return self._uuid

    @property
    def is_current(self) -> bool:
        return self._is_current

    @is_current.setter
    def is_current(self, value: bool):
        self._is_current = value
        self.setChecked(value)
        self._update_style()

    def set_name(self, name: str):
        """Update the tab name."""
        self.setText(name)

    def set_theme(self, is_dark: bool):
        """Set the theme for this tab."""
        self._is_dark_mode = is_dark
        self._update_style()

    def _update_style(self):
        """Update tab appearance based on state and theme."""
        if self._is_current:
            # Current tab always uses accent color
            self.setStyleSheet("""
                QPushButton {
                    background-color: #2a82da;
                    color: white;
                    border: 1px solid #2070c0;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    padding: 6px 12px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #3a92ea;
                }
            """)
        elif self._is_dark_mode:
            # Dark mode inactive tab
            self.setStyleSheet("""
                QPushButton {
                    background-color: #404040;
                    color: #c0c0c0;
                    border: 1px solid #505050;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    padding: 6px 12px;
                }
                QPushButton:hover {
                    background-color: #505050;
                    color: white;
                }
                QPushButton:checked {
                    background-color: #2a82da;
                    color: white;
                }
            """)
        else:
            # Light mode inactive tab
            self.setStyleSheet("""
                QPushButton {
                    background-color: #d0d0d0;
                    color: #404040;
                    border: 1px solid #b4b4b4;
                    border-bottom: none;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    padding: 6px 12px;
                }
                QPushButton:hover {
                    background-color: #c0c0c0;
                    color: black;
                }
                QPushButton:checked {
                    background-color: #2a82da;
                    color: white;
                }
            """)

    def _show_context_menu(self, pos):
        """Show context menu for this tab."""
        menu = QMenu(self)

        rename_action = QAction("Rename...", self)
        rename_action.triggered.connect(lambda: self.rename_requested.emit(self._uuid))
        menu.addAction(rename_action)

        clone_action = QAction("Clone", self)
        clone_action.triggered.connect(lambda: self.clone_requested.emit(self._uuid))
        menu.addAction(clone_action)

        menu.addSeparator()

        close_action = QAction("Close", self)
        close_action.triggered.connect(lambda: self.close_requested.emit(self._uuid))
        menu.addAction(close_action)

        menu.exec_(self.mapToGlobal(pos))

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Handle double-click to rename."""
        if event.button() == Qt.LeftButton:
            self.rename_requested.emit(self._uuid)
        else:
            super().mouseDoubleClickEvent(event)


class WorkspaceTabBar(QWidget):
    """
    Tab bar widget for workspace navigation.

    Displays tabs for each workspace with:
    - Click to switch workspaces
    - Double-click to rename
    - Right-click context menu
    - + button to add new workspace
    - Scroll support for many tabs
    """

    # Signals
    tab_selected = Signal(str)  # workspace uuid
    new_workspace_requested = Signal()
    close_workspace_requested = Signal(str)  # workspace uuid
    rename_workspace_requested = Signal(str, str)  # workspace uuid, new name
    clone_workspace_requested = Signal(str)  # workspace uuid

    def __init__(self, parent=None):
        super().__init__(parent)

        self._tabs: Dict[str, WorkspaceTab] = {}  # uuid -> tab
        self._current_uuid: Optional[str] = None
        self._is_dark_mode = True

        self._setup_ui()

    def _setup_ui(self):
        """Set up the tab bar UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(2)

        # Scroll area for tabs (in case of many workspaces)
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setFrameShape(QFrame.NoFrame)
        self._scroll_area.setFixedHeight(32)
        self._scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
        """)

        # Container for tabs
        self._tab_container = QWidget()
        self._tab_layout = QHBoxLayout(self._tab_container)
        self._tab_layout.setContentsMargins(0, 0, 0, 0)
        self._tab_layout.setSpacing(2)
        self._tab_layout.setAlignment(Qt.AlignLeft)

        self._scroll_area.setWidget(self._tab_container)
        layout.addWidget(self._scroll_area, 1)

        # Workspace list dropdown button (for quick navigation with many workspaces)
        self._list_button = QPushButton("≡")
        self._list_button.setFixedSize(32, 28)
        self._list_button.setToolTip("Show All Workspaces")
        self._list_button.clicked.connect(self._show_workspace_list)
        layout.addWidget(self._list_button)

        # Add workspace button - use Unicode "＋" (fullwidth plus) for better rendering
        self._add_button = QPushButton("＋")
        self._add_button.setFixedSize(32, 28)
        self._add_button.setToolTip("New Workspace (Ctrl+Shift+N)")
        self._add_button.clicked.connect(self.new_workspace_requested.emit)
        self._add_button.setStyleSheet("""
            QPushButton {
                background-color: #404040;
                color: #c0c0c0;
                border: 1px solid #505050;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #505050;
                color: white;
            }
            QPushButton:pressed {
                background-color: #2a82da;
            }
        """)
        layout.addWidget(self._add_button)

        # Set overall style
        self._update_theme_style()

    def _update_theme_style(self):
        """Update styles based on current theme."""
        if self._is_dark_mode:
            self.setStyleSheet("""
                WorkspaceTabBar {
                    background-color: #2b2b2b;
                    border-top: 1px solid #505050;
                }
            """)
            button_style = """
                QPushButton {
                    background-color: #404040;
                    color: #c0c0c0;
                    border: 1px solid #505050;
                    border-radius: 4px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #505050;
                    color: white;
                }
                QPushButton:pressed {
                    background-color: #2a82da;
                }
            """
            self._add_button.setStyleSheet(button_style)
            self._list_button.setStyleSheet(button_style)
        else:
            self.setStyleSheet("""
                WorkspaceTabBar {
                    background-color: #e0e0e0;
                    border-top: 1px solid #b4b4b4;
                }
            """)
            button_style = """
                QPushButton {
                    background-color: #d0d0d0;
                    color: #404040;
                    border: 1px solid #b4b4b4;
                    border-radius: 4px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #c0c0c0;
                    color: black;
                }
                QPushButton:pressed {
                    background-color: #2a82da;
                    color: white;
                }
            """
            self._add_button.setStyleSheet(button_style)
            self._list_button.setStyleSheet(button_style)

    def set_theme(self, is_dark: bool):
        """Set the theme for the tab bar."""
        self._is_dark_mode = is_dark
        self._update_theme_style()

        # Update all tabs
        for tab in self._tabs.values():
            tab.set_theme(is_dark)

    def add_tab(self, workspace_uuid: str, name: str):
        """Add a new workspace tab."""
        if workspace_uuid in self._tabs:
            return

        tab = WorkspaceTab(workspace_uuid, name)
        tab.set_theme(self._is_dark_mode)  # Apply current theme
        tab.clicked.connect(lambda: self._on_tab_clicked(workspace_uuid))
        tab.close_requested.connect(self._on_close_requested)
        tab.rename_requested.connect(self._on_rename_requested)
        tab.clone_requested.connect(self.clone_workspace_requested.emit)

        self._tabs[workspace_uuid] = tab
        self._tab_layout.addWidget(tab)

    def remove_tab(self, workspace_uuid: str):
        """Remove a workspace tab."""
        if workspace_uuid not in self._tabs:
            return

        tab = self._tabs.pop(workspace_uuid)
        self._tab_layout.removeWidget(tab)
        tab.deleteLater()

        if self._current_uuid == workspace_uuid:
            self._current_uuid = None

    def rename_tab(self, workspace_uuid: str, new_name: str):
        """Rename a workspace tab."""
        if workspace_uuid in self._tabs:
            self._tabs[workspace_uuid].set_name(new_name)

    def set_current_tab(self, workspace_uuid: str):
        """Set the current/active tab."""
        # Deselect previous tab
        if self._current_uuid and self._current_uuid in self._tabs:
            self._tabs[self._current_uuid].is_current = False

        # Select new tab
        self._current_uuid = workspace_uuid
        if workspace_uuid in self._tabs:
            self._tabs[workspace_uuid].is_current = True

            # Ensure tab is visible in scroll area
            tab = self._tabs[workspace_uuid]
            self._scroll_area.ensureWidgetVisible(tab)

    def clear_tabs(self):
        """Remove all tabs."""
        for uuid in list(self._tabs.keys()):
            self.remove_tab(uuid)
        self._current_uuid = None

    def update_tabs(self, workspaces: List[Dict], current_uuid: Optional[str] = None):
        """
        Update all tabs to match the workspace list.

        Args:
            workspaces: List of dicts with 'uuid' and 'name' keys
            current_uuid: UUID of the current workspace
        """
        # Get current UUIDs
        existing_uuids = set(self._tabs.keys())
        new_uuids = set(ws['uuid'] for ws in workspaces)

        # Remove tabs that no longer exist
        for uuid in existing_uuids - new_uuids:
            self.remove_tab(uuid)

        # Add new tabs
        for ws in workspaces:
            if ws['uuid'] not in existing_uuids:
                self.add_tab(ws['uuid'], ws['name'])
            else:
                # Update name if changed
                self.rename_tab(ws['uuid'], ws['name'])

        # Reorder tabs to match workspace order
        for i, ws in enumerate(workspaces):
            tab = self._tabs.get(ws['uuid'])
            if tab:
                # Remove and re-add at correct position
                self._tab_layout.removeWidget(tab)
                self._tab_layout.insertWidget(i, tab)

        # Set current tab
        if current_uuid:
            self.set_current_tab(current_uuid)

    def _on_tab_clicked(self, workspace_uuid: str):
        """Handle tab click."""
        if workspace_uuid != self._current_uuid:
            self.tab_selected.emit(workspace_uuid)

    def _on_close_requested(self, workspace_uuid: str):
        """Handle tab close request."""
        # Don't allow closing the last tab
        if len(self._tabs) <= 1:
            QMessageBox.warning(
                self, "Cannot Close",
                "Cannot close the last workspace."
            )
            return

        self.close_workspace_requested.emit(workspace_uuid)

    def _on_rename_requested(self, workspace_uuid: str):
        """Handle tab rename request."""
        if workspace_uuid not in self._tabs:
            return

        current_name = self._tabs[workspace_uuid].text()
        name, ok = QInputDialog.getText(
            self, "Rename Workspace",
            "Enter new workspace name:",
            text=current_name
        )

        if ok and name.strip():
            self.rename_workspace_requested.emit(workspace_uuid, name.strip())

    def _show_workspace_list(self):
        """Show a popup menu with all workspaces for quick navigation."""
        menu = QMenu(self)

        # Style the menu based on theme
        if self._is_dark_mode:
            menu.setStyleSheet("""
                QMenu {
                    background-color: #3c3c3c;
                    color: #e0e0e0;
                    border: 1px solid #505050;
                    padding: 4px;
                }
                QMenu::item {
                    padding: 6px 24px 6px 12px;
                    border-radius: 3px;
                }
                QMenu::item:selected {
                    background-color: #2a82da;
                    color: white;
                }
                QMenu::item:checked {
                    font-weight: bold;
                }
                QMenu::separator {
                    height: 1px;
                    background-color: #505050;
                    margin: 4px 8px;
                }
            """)
        else:
            menu.setStyleSheet("""
                QMenu {
                    background-color: #f5f5f5;
                    color: #303030;
                    border: 1px solid #b0b0b0;
                    padding: 4px;
                }
                QMenu::item {
                    padding: 6px 24px 6px 12px;
                    border-radius: 3px;
                }
                QMenu::item:selected {
                    background-color: #2a82da;
                    color: white;
                }
                QMenu::item:checked {
                    font-weight: bold;
                }
                QMenu::separator {
                    height: 1px;
                    background-color: #c0c0c0;
                    margin: 4px 8px;
                }
            """)

        # Add header
        header = QAction(f"Workspaces ({len(self._tabs)})", self)
        header.setEnabled(False)
        menu.addAction(header)
        menu.addSeparator()

        # Add all workspaces sorted by tab order
        for uuid, tab in self._tabs.items():
            action = QAction(tab.text(), self)
            action.setCheckable(True)
            action.setChecked(uuid == self._current_uuid)

            # Capture uuid in closure
            workspace_uuid = uuid
            action.triggered.connect(lambda checked, uid=workspace_uuid: self._on_menu_workspace_selected(uid))
            menu.addAction(action)

        # Show menu below the button
        menu.exec_(self._list_button.mapToGlobal(self._list_button.rect().bottomLeft()))

    def _on_menu_workspace_selected(self, workspace_uuid: str):
        """Handle workspace selection from dropdown menu."""
        if workspace_uuid != self._current_uuid:
            self.tab_selected.emit(workspace_uuid)
