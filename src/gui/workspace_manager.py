"""
Workspace and Session Manager for managing multiple workspaces and saving/loading sessions.

This module provides:
- WorkspaceManager: Manages multiple workspaces within a session
- SessionManager: Handles saving/loading entire sessions to/from files
"""

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox

import json
import uuid
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field


@dataclass
class WorkspaceState:
    """
    Represents a complete workspace state including layout and panel contents.
    This is used for in-memory storage when switching between workspaces.
    """
    uuid: str
    name: str
    created: str  # ISO format timestamp
    modified: str  # ISO format timestamp
    layout: Dict[str, Any]  # Hierarchical layout structure
    panel_states: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # panel_id -> state
    measurements: List[Dict[str, Any]] = field(default_factory=list)  # Measurement data
    hole_pairing_session: Optional[Dict[str, Any]] = None  # Hole pairing data for vacancy analysis

    @classmethod
    def create_new(cls, name: str = "Workspace") -> 'WorkspaceState':
        """Create a new empty workspace state."""
        now = datetime.now().isoformat()
        return cls(
            uuid=str(uuid.uuid4()),
            name=name,
            created=now,
            modified=now,
            layout={'type': 'panel', 'panel_id': str(uuid.uuid4())},
            panel_states={},
            measurements=[]
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkspaceState':
        """Create from dictionary."""
        return cls(
            uuid=data.get('uuid', str(uuid.uuid4())),
            name=data.get('name', 'Workspace'),
            created=data.get('created', datetime.now().isoformat()),
            modified=data.get('modified', datetime.now().isoformat()),
            layout=data.get('layout', {'type': 'panel'}),
            panel_states=data.get('panel_states', {}),
            measurements=data.get('measurements', []),
            hole_pairing_session=data.get('hole_pairing_session')
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'uuid': self.uuid,
            'name': self.name,
            'created': self.created,
            'modified': self.modified,
            'layout': self.layout,
            'panel_states': self.panel_states,
            'measurements': self.measurements,
            'hole_pairing_session': self.hole_pairing_session
        }

    def touch(self):
        """Update the modified timestamp."""
        self.modified = datetime.now().isoformat()


class WorkspaceManager(QObject):
    """
    Manages multiple workspaces within a session.

    Handles:
    - Creating, deleting, renaming workspaces
    - Switching between workspaces (keeping state in memory)
    - Tracking current workspace
    """

    # Signals
    workspace_created = Signal(str)  # workspace uuid
    workspace_deleted = Signal(str)  # workspace uuid
    workspace_renamed = Signal(str, str)  # workspace uuid, new name
    workspace_switched = Signal(str, str)  # old uuid, new uuid
    workspaces_changed = Signal()  # General signal for any workspace list change

    def __init__(self, parent=None):
        super().__init__(parent)

        self._workspaces: Dict[str, WorkspaceState] = {}  # uuid -> WorkspaceState
        self._current_workspace_uuid: Optional[str] = None
        self._workspace_order: List[str] = []  # UUIDs in creation order

    @property
    def current_workspace(self) -> Optional[WorkspaceState]:
        """Get the current workspace state."""
        if self._current_workspace_uuid:
            return self._workspaces.get(self._current_workspace_uuid)
        return None

    @property
    def current_workspace_uuid(self) -> Optional[str]:
        """Get the current workspace UUID."""
        return self._current_workspace_uuid

    @property
    def workspaces(self) -> List[WorkspaceState]:
        """Get all workspaces in order."""
        return [self._workspaces[uid] for uid in self._workspace_order if uid in self._workspaces]

    @property
    def workspace_count(self) -> int:
        """Get the number of workspaces."""
        return len(self._workspaces)

    def new_workspace(self, name: Optional[str] = None) -> WorkspaceState:
        """
        Create a new workspace.

        Args:
            name: Name for the workspace (default: "Workspace N")

        Returns:
            The newly created WorkspaceState
        """
        if name is None:
            name = f"Workspace {len(self._workspaces) + 1}"

        workspace = WorkspaceState.create_new(name)
        self._workspaces[workspace.uuid] = workspace
        self._workspace_order.append(workspace.uuid)

        self.workspace_created.emit(workspace.uuid)
        self.workspaces_changed.emit()

        return workspace

    def delete_workspace(self, workspace_uuid: str) -> bool:
        """
        Delete a workspace.

        Args:
            workspace_uuid: UUID of workspace to delete

        Returns:
            True if deleted, False if not found or is the only workspace
        """
        if workspace_uuid not in self._workspaces:
            return False

        # Don't delete the last workspace
        if len(self._workspaces) <= 1:
            return False

        # If deleting current workspace, switch to another first
        if workspace_uuid == self._current_workspace_uuid:
            # Find next workspace to switch to
            current_index = self._workspace_order.index(workspace_uuid)
            if current_index > 0:
                new_uuid = self._workspace_order[current_index - 1]
            else:
                new_uuid = self._workspace_order[current_index + 1]
            # Note: actual switch will be handled by caller
            self._current_workspace_uuid = new_uuid

        # Remove workspace
        del self._workspaces[workspace_uuid]
        self._workspace_order.remove(workspace_uuid)

        self.workspace_deleted.emit(workspace_uuid)
        self.workspaces_changed.emit()

        return True

    def rename_workspace(self, workspace_uuid: str, new_name: str) -> bool:
        """
        Rename a workspace.

        Args:
            workspace_uuid: UUID of workspace to rename
            new_name: New name for the workspace

        Returns:
            True if renamed, False if not found
        """
        if workspace_uuid not in self._workspaces:
            return False

        workspace = self._workspaces[workspace_uuid]
        workspace.name = new_name
        workspace.touch()

        self.workspace_renamed.emit(workspace_uuid, new_name)
        self.workspaces_changed.emit()

        return True

    def clone_workspace(self, workspace_uuid: str, new_name: Optional[str] = None) -> Optional[WorkspaceState]:
        """
        Clone a workspace.

        Args:
            workspace_uuid: UUID of workspace to clone
            new_name: Name for the clone (default: "Copy of <original>")

        Returns:
            The cloned WorkspaceState, or None if source not found
        """
        if workspace_uuid not in self._workspaces:
            return None

        source = self._workspaces[workspace_uuid]

        if new_name is None:
            new_name = f"Copy of {source.name}"

        # Create new workspace with copied data
        now = datetime.now().isoformat()
        clone = WorkspaceState(
            uuid=str(uuid.uuid4()),
            name=new_name,
            created=now,
            modified=now,
            layout=json.loads(json.dumps(source.layout)),  # Deep copy
            panel_states=json.loads(json.dumps(source.panel_states)),
            measurements=json.loads(json.dumps(source.measurements))
        )

        self._workspaces[clone.uuid] = clone
        # Insert after source in order
        source_index = self._workspace_order.index(workspace_uuid)
        self._workspace_order.insert(source_index + 1, clone.uuid)

        self.workspace_created.emit(clone.uuid)
        self.workspaces_changed.emit()

        return clone

    def reorder_workspaces(self, new_order: List[str]) -> bool:
        """
        Reorder workspaces to match the given order.

        Args:
            new_order: List of workspace UUIDs in the desired order

        Returns:
            True if reordered, False if order is invalid
        """
        # Validate that new_order contains exactly the same UUIDs
        if set(new_order) != set(self._workspace_order):
            return False

        self._workspace_order = new_order.copy()
        self.workspaces_changed.emit()

        return True

    def get_workspace(self, workspace_uuid: str) -> Optional[WorkspaceState]:
        """Get a workspace by UUID."""
        return self._workspaces.get(workspace_uuid)

    def set_current_workspace(self, workspace_uuid: str) -> bool:
        """
        Set the current workspace (for internal use during switching).

        Args:
            workspace_uuid: UUID of workspace to set as current

        Returns:
            True if set, False if not found
        """
        if workspace_uuid not in self._workspaces:
            return False

        old_uuid = self._current_workspace_uuid
        self._current_workspace_uuid = workspace_uuid

        if old_uuid != workspace_uuid:
            self.workspace_switched.emit(old_uuid or "", workspace_uuid)

        return True

    def update_current_workspace_state(self, layout: Dict[str, Any],
                                        panel_states: Dict[str, Dict[str, Any]],
                                        measurements: List[Dict[str, Any]],
                                        hole_pairing_session: Optional[Dict[str, Any]] = None):
        """
        Update the current workspace's state (called before switching).

        Args:
            layout: Current layout structure
            panel_states: Current panel states
            measurements: Current measurements
            hole_pairing_session: Hole pairing analysis data (optional)
        """
        if self._current_workspace_uuid and self._current_workspace_uuid in self._workspaces:
            workspace = self._workspaces[self._current_workspace_uuid]
            workspace.layout = layout
            workspace.panel_states = panel_states
            workspace.measurements = measurements
            workspace.hole_pairing_session = hole_pairing_session
            workspace.touch()

    def get_next_workspace_uuid(self) -> Optional[str]:
        """Get the UUID of the next workspace in order."""
        if not self._current_workspace_uuid or len(self._workspace_order) < 2:
            return None

        current_index = self._workspace_order.index(self._current_workspace_uuid)
        next_index = (current_index + 1) % len(self._workspace_order)
        return self._workspace_order[next_index]

    def get_previous_workspace_uuid(self) -> Optional[str]:
        """Get the UUID of the previous workspace in order."""
        if not self._current_workspace_uuid or len(self._workspace_order) < 2:
            return None

        current_index = self._workspace_order.index(self._current_workspace_uuid)
        prev_index = (current_index - 1) % len(self._workspace_order)
        return self._workspace_order[prev_index]

    def clear(self):
        """Clear all workspaces."""
        self._workspaces.clear()
        self._workspace_order.clear()
        self._current_workspace_uuid = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize all workspaces to dictionary."""
        return {
            'workspaces': [ws.to_dict() for ws in self.workspaces],
            'current_workspace_uuid': self._current_workspace_uuid,
            'workspace_order': self._workspace_order
        }

    def from_dict(self, data: Dict[str, Any]):
        """Load workspaces from dictionary."""
        self.clear()

        for ws_data in data.get('workspaces', []):
            workspace = WorkspaceState.from_dict(ws_data)
            self._workspaces[workspace.uuid] = workspace

        self._workspace_order = data.get('workspace_order', list(self._workspaces.keys()))
        self._current_workspace_uuid = data.get('current_workspace_uuid')

        # Ensure current workspace is valid
        if self._current_workspace_uuid not in self._workspaces:
            self._current_workspace_uuid = self._workspace_order[0] if self._workspace_order else None

        self.workspaces_changed.emit()


class SessionManager(QObject):
    """
    Manages saving and loading entire sessions to/from files.

    A session includes:
    - All workspaces and their layouts
    - Panel states (file paths, colormap, display range, etc.)
    - Measurements (lines, polygons)
    - Current workspace selection
    """

    SESSION_VERSION = 1
    SESSION_EXTENSION = ".json"

    # Signals
    session_loaded = Signal(str)  # file path
    session_saved = Signal(str)  # file path
    session_cleared = Signal()

    def __init__(self, workspace_manager: WorkspaceManager, parent=None):
        super().__init__(parent)

        self._workspace_manager = workspace_manager
        self._current_session_path: Optional[str] = None
        self._is_modified: bool = False
        self._session_name: str = "Untitled Session"

    @property
    def current_session_path(self) -> Optional[str]:
        """Get the current session file path."""
        return self._current_session_path

    @property
    def session_name(self) -> str:
        """Get the session name."""
        return self._session_name

    @session_name.setter
    def session_name(self, name: str):
        """Set the session name."""
        self._session_name = name

    @property
    def is_modified(self) -> bool:
        """Check if session has unsaved changes."""
        return self._is_modified

    def mark_modified(self):
        """Mark the session as having unsaved changes."""
        self._is_modified = True

    def new_session(self, name: str = "Untitled Session"):
        """
        Start a new session, clearing all existing data.

        Args:
            name: Name for the new session
        """
        self._workspace_manager.clear()
        self._current_session_path = None
        self._session_name = name
        self._is_modified = False

        # Create initial workspace
        self._workspace_manager.new_workspace("Workspace 1")
        if self._workspace_manager.workspaces:
            self._workspace_manager.set_current_workspace(
                self._workspace_manager.workspaces[0].uuid
            )

        self.session_cleared.emit()

    def save_session(self, file_path: Optional[str] = None) -> bool:
        """
        Save the current session to a file.

        Args:
            file_path: Path to save to (uses current path if None)

        Returns:
            True if saved successfully, False otherwise
        """
        if file_path is None:
            file_path = self._current_session_path

        if file_path is None:
            return False

        # Ensure correct extension
        if not file_path.endswith(self.SESSION_EXTENSION):
            file_path += self.SESSION_EXTENSION

        try:
            session_data = self._create_session_data()

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)

            self._current_session_path = file_path
            self._is_modified = False
            self.session_saved.emit(file_path)

            return True

        except Exception as e:
            print(f"Error saving session: {e}")
            return False

    def load_session(self, file_path: str) -> bool:
        """
        Load a session from a file.

        Args:
            file_path: Path to load from

        Returns:
            True if loaded successfully, False otherwise
        """
        if not os.path.exists(file_path):
            return False

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)

            # Validate version
            version = session_data.get('version', 0)
            if version > self.SESSION_VERSION:
                print(f"Session file version {version} is newer than supported {self.SESSION_VERSION}")
                return False

            # Load data
            self._load_session_data(session_data)

            self._current_session_path = file_path
            self._session_name = session_data.get('name', os.path.basename(file_path))
            self._is_modified = False

            self.session_loaded.emit(file_path)

            return True

        except Exception as e:
            print(f"Error loading session: {e}")
            return False

    def _create_session_data(self) -> Dict[str, Any]:
        """Create session data dictionary for saving."""
        return {
            'version': self.SESSION_VERSION,
            'app_version': '1.0.0',  # TODO: Get from app
            'name': self._session_name,
            'created': datetime.now().isoformat(),
            'modified': datetime.now().isoformat(),
            **self._workspace_manager.to_dict()
        }

    def _load_session_data(self, data: Dict[str, Any]):
        """Load session data from dictionary."""
        self._workspace_manager.from_dict(data)

    def get_session_info(self) -> Dict[str, Any]:
        """Get information about the current session."""
        return {
            'name': self._session_name,
            'path': self._current_session_path,
            'is_modified': self._is_modified,
            'workspace_count': self._workspace_manager.workspace_count,
            'current_workspace': self._workspace_manager.current_workspace.name if self._workspace_manager.current_workspace else None
        }
