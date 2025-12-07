"""
Re-export WorkspaceWidget from workspace.py for cleaner imports.
This helps prevent circular imports.
"""

from src.gui.workspace import WorkspaceWidget

__all__ = ['WorkspaceWidget']