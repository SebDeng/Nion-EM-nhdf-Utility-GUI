"""
Hole Pairing Panel for vacancy diffusion analysis.

Allows pairing polygons between before/after STEM images to track
sink growth and small hole fates in vacancy diffusion experiments.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QGroupBox, QListWidget, QListWidgetItem,
    QDoubleSpinBox, QScrollArea, QMessageBox, QFileDialog,
    QAbstractItemView, QSplitter, QFrame, QInputDialog
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush, QFont

import pyqtgraph as pg

from typing import Optional, List, Dict, Tuple
import csv
import math
import os

from src.gui.hole_pairing_data import (
    HoleReference, SinkPairing, SmallHoleFate,
    PairingSession, HoleFate,
    calculate_proper_centroid, calculate_polygon_area,
    calculate_perpendicular_width
)
from src.gui.heatmap_visualization_dialog import HeatMapVisualizationDialog


class HolePairingPanel(QWidget):
    """
    Panel for pairing holes between before/after vacancy diffusion images.
    """

    # Signals
    pairing_confirmed = Signal(SinkPairing)
    pairing_rejected = Signal(str)  # pairing_id
    session_changed = Signal(PairingSession)
    highlight_polygon_requested = Signal(str, int)  # panel_id, polygon_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workspace = None  # Reference to WorkspaceWidget
        self._main_window = None  # Reference to main window for panel access
        self._session = PairingSession()
        self._is_dark_mode = True

        # Multi-session storage: key = "before_id::after_id" -> session
        self._sessions: Dict[str, PairingSession] = {}
        self._current_session_key: Optional[str] = None

        # Highlight markers for visual feedback
        self._highlight_markers: List[pg.ScatterPlotItem] = []
        self._highlight_labels: List[pg.TextItem] = []

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Create scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)

        # --- Panel Selection Group ---
        panel_group = QGroupBox("Panel Selection")
        panel_layout = QVBoxLayout(panel_group)
        panel_layout.setSpacing(4)

        # Before panel selector
        before_row = QHBoxLayout()
        before_label = QLabel("Before:")
        before_label.setFixedWidth(50)
        before_row.addWidget(before_label)
        self._before_combo = QComboBox()
        self._before_combo.setMinimumWidth(120)
        self._before_combo.setToolTip("Select the panel with the 'before' image")
        before_row.addWidget(self._before_combo, 1)
        panel_layout.addLayout(before_row)

        # After panel selector
        after_row = QHBoxLayout()
        after_label = QLabel("After:")
        after_label.setFixedWidth(50)
        after_row.addWidget(after_label)
        self._after_combo = QComboBox()
        self._after_combo.setMinimumWidth(120)
        self._after_combo.setToolTip("Select the panel with the 'after' image")
        after_row.addWidget(self._after_combo, 1)
        panel_layout.addLayout(after_row)

        # Refresh panels button
        self._refresh_btn = QPushButton("Refresh Panels")
        self._refresh_btn.setToolTip("Reload the list of available panels")
        panel_layout.addWidget(self._refresh_btn)

        content_layout.addWidget(panel_group)

        # --- Configuration Group ---
        config_group = QGroupBox("Configuration")
        config_layout = QVBoxLayout(config_group)
        config_layout.setSpacing(4)

        # Sink threshold
        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel("Sink threshold:"))
        self._threshold_spin = QDoubleSpinBox()
        self._threshold_spin.setRange(0.1, 100.0)
        self._threshold_spin.setValue(4.0)
        self._threshold_spin.setSingleStep(0.5)
        self._threshold_spin.setSuffix(" nm²")
        self._threshold_spin.setToolTip("Holes larger than this are 'sinks'")
        threshold_row.addWidget(self._threshold_spin)
        config_layout.addLayout(threshold_row)

        # Match tolerance
        tolerance_row = QHBoxLayout()
        tolerance_row.addWidget(QLabel("Match tolerance:"))
        self._tolerance_spin = QDoubleSpinBox()
        self._tolerance_spin.setRange(0.5, 50.0)
        self._tolerance_spin.setValue(3.0)
        self._tolerance_spin.setSingleStep(0.5)
        self._tolerance_spin.setSuffix(" nm")
        self._tolerance_spin.setToolTip("Max centroid distance for auto-matching")
        tolerance_row.addWidget(self._tolerance_spin)
        config_layout.addLayout(tolerance_row)

        content_layout.addWidget(config_group)

        # --- Auto-match Button ---
        self._auto_match_btn = QPushButton("Auto-Match Sinks")
        self._auto_match_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self._auto_match_btn.setToolTip("Automatically match sinks by centroid proximity")
        content_layout.addWidget(self._auto_match_btn)

        # --- Manual Pairing Group ---
        manual_group = QGroupBox("Manual Pairing")
        manual_layout = QVBoxLayout(manual_group)
        manual_layout.setSpacing(4)

        # Before hole selector
        before_hole_row = QHBoxLayout()
        before_hole_row.addWidget(QLabel("Before:"))
        self._before_hole_combo = QComboBox()
        self._before_hole_combo.setToolTip("Select a hole from the 'before' panel")
        before_hole_row.addWidget(self._before_hole_combo, 1)
        manual_layout.addLayout(before_hole_row)

        # After hole selector
        after_hole_row = QHBoxLayout()
        after_hole_row.addWidget(QLabel("After:"))
        self._after_hole_combo = QComboBox()
        self._after_hole_combo.setToolTip("Select a hole from the 'after' panel")
        after_hole_row.addWidget(self._after_hole_combo, 1)
        manual_layout.addLayout(after_hole_row)

        # Manual pair buttons
        manual_btn_row = QHBoxLayout()
        self._refresh_holes_btn = QPushButton("Refresh")
        self._refresh_holes_btn.setToolTip("Refresh hole lists from panels")
        manual_btn_row.addWidget(self._refresh_holes_btn)

        self._create_pair_btn = QPushButton("Create Pair")
        self._create_pair_btn.setToolTip("Create a manual pairing from selected holes")
        self._create_pair_btn.setStyleSheet("font-weight: bold;")
        manual_btn_row.addWidget(self._create_pair_btn)

        manual_layout.addLayout(manual_btn_row)
        content_layout.addWidget(manual_group)

        # --- Suggested Pairings Group ---
        suggestions_group = QGroupBox("Suggested Pairings")
        suggestions_layout = QVBoxLayout(suggestions_group)
        suggestions_layout.setSpacing(4)

        self._suggestions_list = QListWidget()
        self._suggestions_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._suggestions_list.setMaximumHeight(120)
        self._suggestions_list.setToolTip("Click to select, then Confirm or Reject")
        suggestions_layout.addWidget(self._suggestions_list)

        # Confirm/Reject buttons
        btn_row = QHBoxLayout()
        self._confirm_btn = QPushButton("Confirm")
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.setToolTip("Confirm the selected pairing")
        btn_row.addWidget(self._confirm_btn)

        self._reject_btn = QPushButton("Reject")
        self._reject_btn.setEnabled(False)
        self._reject_btn.setToolTip("Reject the selected pairing")
        btn_row.addWidget(self._reject_btn)

        self._confirm_all_btn = QPushButton("All")
        self._confirm_all_btn.setToolTip("Confirm all suggested pairings")
        btn_row.addWidget(self._confirm_all_btn)

        suggestions_layout.addLayout(btn_row)
        content_layout.addWidget(suggestions_group)

        # --- Confirmed Pairings Group ---
        confirmed_group = QGroupBox("Confirmed Pairings")
        confirmed_layout = QVBoxLayout(confirmed_group)
        confirmed_layout.setSpacing(4)

        self._confirmed_list = QListWidget()
        self._confirmed_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._confirmed_list.setMaximumHeight(100)
        confirmed_layout.addWidget(self._confirmed_list)

        # Unconfirm button
        self._unconfirm_btn = QPushButton("Unconfirm Selected")
        self._unconfirm_btn.setEnabled(False)
        self._unconfirm_btn.setToolTip("Move pairing back to suggestions")
        confirmed_layout.addWidget(self._unconfirm_btn)

        content_layout.addWidget(confirmed_group)

        # --- Unassigned Holes Group ---
        unassigned_group = QGroupBox("Unassigned Holes")
        unassigned_layout = QVBoxLayout(unassigned_group)
        unassigned_layout.setSpacing(4)

        # Before unassigned
        before_unassigned_row = QHBoxLayout()
        before_unassigned_row.addWidget(QLabel("Before:"))
        self._before_unassigned_label = QLabel("0 holes")
        self._before_unassigned_label.setStyleSheet("color: #FF6B6B; font-weight: bold;")
        before_unassigned_row.addWidget(self._before_unassigned_label)
        before_unassigned_row.addStretch()
        unassigned_layout.addLayout(before_unassigned_row)

        self._before_unassigned_list = QListWidget()
        self._before_unassigned_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._before_unassigned_list.setMaximumHeight(80)
        self._before_unassigned_list.setToolTip("Holes in 'before' panel not yet paired")
        unassigned_layout.addWidget(self._before_unassigned_list)

        # After unassigned
        after_unassigned_row = QHBoxLayout()
        after_unassigned_row.addWidget(QLabel("After:"))
        self._after_unassigned_label = QLabel("0 holes")
        self._after_unassigned_label.setStyleSheet("color: #FF6B6B; font-weight: bold;")
        after_unassigned_row.addWidget(self._after_unassigned_label)
        after_unassigned_row.addStretch()
        unassigned_layout.addLayout(after_unassigned_row)

        self._after_unassigned_list = QListWidget()
        self._after_unassigned_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._after_unassigned_list.setMaximumHeight(80)
        self._after_unassigned_list.setToolTip("Holes in 'after' panel not yet paired")
        unassigned_layout.addWidget(self._after_unassigned_list)

        # Refresh unassigned button
        self._refresh_unassigned_btn = QPushButton("Refresh Unassigned")
        self._refresh_unassigned_btn.setToolTip("Update the list of unassigned holes")
        unassigned_layout.addWidget(self._refresh_unassigned_btn)

        content_layout.addWidget(unassigned_group)

        # --- Small Holes Fate Group ---
        small_holes_group = QGroupBox("Small Holes (< threshold)")
        small_holes_layout = QVBoxLayout(small_holes_group)
        small_holes_layout.setSpacing(4)

        self._small_holes_list = QListWidget()
        self._small_holes_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._small_holes_list.setMaximumHeight(100)
        self._small_holes_list.setToolTip("Small holes from the 'before' image")
        small_holes_layout.addWidget(self._small_holes_list)

        fate_row = QHBoxLayout()
        self._mark_disappeared_btn = QPushButton("Disappeared")
        self._mark_disappeared_btn.setEnabled(False)
        self._mark_disappeared_btn.setToolTip("Mark hole as disappeared (consumed by vacancy flux)")
        fate_row.addWidget(self._mark_disappeared_btn)

        self._mark_survived_btn = QPushButton("Survived")
        self._mark_survived_btn.setEnabled(False)
        self._mark_survived_btn.setToolTip("Mark hole as survived (still exists in after)")
        fate_row.addWidget(self._mark_survived_btn)

        small_holes_layout.addLayout(fate_row)

        # Absorbed dropdown row
        absorbed_row = QHBoxLayout()
        absorbed_row.addWidget(QLabel("Absorbed by:"))
        self._absorbed_combo = QComboBox()
        self._absorbed_combo.setEnabled(False)
        self._absorbed_combo.setToolTip("Select which sink absorbed this hole")
        absorbed_row.addWidget(self._absorbed_combo, 1)
        self._mark_absorbed_btn = QPushButton("Set")
        self._mark_absorbed_btn.setEnabled(False)
        self._mark_absorbed_btn.setToolTip("Mark as absorbed by selected sink")
        absorbed_row.addWidget(self._mark_absorbed_btn)
        small_holes_layout.addLayout(absorbed_row)

        content_layout.addWidget(small_holes_group)

        # --- Visualization Button ---
        viz_row = QHBoxLayout()
        self._show_heatmap_btn = QPushButton("Show ΔA Heat Map")
        self._show_heatmap_btn.setStyleSheet("font-weight: bold;")
        self._show_heatmap_btn.setToolTip(
            "Open visualization dialog showing area change (ΔA) as a heat map.\n"
            "Blue = shrinking, Red = growing"
        )
        viz_row.addWidget(self._show_heatmap_btn)
        content_layout.addLayout(viz_row)

        # --- Import/Export Buttons ---
        export_row = QHBoxLayout()
        self._import_btn = QPushButton("Import CSV...")
        self._import_btn.setToolTip("Import pairing data from a previously exported CSV")
        export_row.addWidget(self._import_btn)

        self._export_btn = QPushButton("Export CSV...")
        self._export_btn.setToolTip("Export pairing data and small hole fates to CSV")
        export_row.addWidget(self._export_btn)

        content_layout.addLayout(export_row)

        # Clear button on its own row
        clear_row = QHBoxLayout()
        self._clear_btn = QPushButton("Clear All")
        self._clear_btn.setToolTip("Clear all pairings and start over")
        clear_row.addWidget(self._clear_btn)
        content_layout.addLayout(clear_row)

        # Statistics label
        self._stats_label = QLabel("No data loaded")
        self._stats_label.setWordWrap(True)
        self._stats_label.setStyleSheet("color: #888; font-size: 11px;")
        content_layout.addWidget(self._stats_label)

        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _connect_signals(self):
        """Connect internal signals."""
        self._refresh_btn.clicked.connect(self._refresh_panel_list)
        self._before_combo.currentIndexChanged.connect(self._on_panel_selection_changed)
        self._after_combo.currentIndexChanged.connect(self._on_panel_selection_changed)
        self._threshold_spin.valueChanged.connect(self._on_config_changed)
        self._tolerance_spin.valueChanged.connect(self._on_config_changed)

        self._auto_match_btn.clicked.connect(self._run_auto_match)

        # Manual pairing signals
        self._refresh_holes_btn.clicked.connect(self._refresh_hole_dropdowns)
        self._create_pair_btn.clicked.connect(self._create_manual_pair)
        self._before_hole_combo.currentIndexChanged.connect(self._on_manual_hole_selected)
        self._after_hole_combo.currentIndexChanged.connect(self._on_manual_hole_selected)

        self._suggestions_list.itemSelectionChanged.connect(self._on_suggestion_selected)
        self._confirm_btn.clicked.connect(self._confirm_selected)
        self._reject_btn.clicked.connect(self._reject_selected)
        self._confirm_all_btn.clicked.connect(self._confirm_all)

        self._confirmed_list.itemSelectionChanged.connect(self._on_confirmed_selected)
        self._unconfirm_btn.clicked.connect(self._unconfirm_selected)

        # Unassigned holes signals
        self._refresh_unassigned_btn.clicked.connect(self._update_unassigned_lists)
        self._before_unassigned_list.itemSelectionChanged.connect(self._on_before_unassigned_selected)
        self._after_unassigned_list.itemSelectionChanged.connect(self._on_after_unassigned_selected)

        self._small_holes_list.itemSelectionChanged.connect(self._on_small_hole_selected)
        self._mark_disappeared_btn.clicked.connect(lambda: self._mark_fate(HoleFate.DISAPPEARED))
        self._mark_survived_btn.clicked.connect(lambda: self._mark_fate(HoleFate.SURVIVED))
        self._mark_absorbed_btn.clicked.connect(self._mark_absorbed)

        self._import_btn.clicked.connect(self._import_csv)
        self._export_btn.clicked.connect(self._export_csv)
        self._clear_btn.clicked.connect(self._clear_all)
        self._show_heatmap_btn.clicked.connect(self._show_heatmap_dialog)

    def set_workspace(self, workspace):
        """Set reference to the workspace widget."""
        self._workspace = workspace
        self._refresh_panel_list()

        # Connect to workspace panel selection signal if available
        if hasattr(workspace, 'panel_selected'):
            try:
                workspace.panel_selected.connect(self._on_workspace_panel_selected)
            except Exception:
                pass  # Signal might already be connected or not exist

    def set_main_window(self, main_window):
        """Set reference to main window for accessing panels."""
        self._main_window = main_window
        self._refresh_panel_list()

    def _on_workspace_panel_selected(self, panel):
        """Handle workspace panel selection - auto-switch to matching session."""
        if not panel:
            return

        # Get panel_id from the panel object
        panel_id = getattr(panel, 'panel_id', None)
        if not panel_id:
            return

        # Find sessions where this panel is used
        matching_sessions = self._find_sessions_with_panel(panel_id)

        if not matching_sessions:
            return

        # If only one match, use it
        # If multiple matches (panel is used as both before and after), prefer "before"
        best_match = None
        for session_key, role in matching_sessions:
            if role == 'before':
                best_match = session_key
                break
            elif best_match is None:
                best_match = session_key

        if best_match and best_match != self._current_session_key:
            # Switch to the matching session
            session = self._sessions.get(best_match)
            if session:
                # Update dropdowns to match
                if session.before_panel_id:
                    idx = self._before_combo.findData(session.before_panel_id)
                    if idx >= 0:
                        self._before_combo.blockSignals(True)
                        self._before_combo.setCurrentIndex(idx)
                        self._before_combo.blockSignals(False)

                if session.after_panel_id:
                    idx = self._after_combo.findData(session.after_panel_id)
                    if idx >= 0:
                        self._after_combo.blockSignals(True)
                        self._after_combo.setCurrentIndex(idx)
                        self._after_combo.blockSignals(False)

                # Now trigger the session switch
                self._on_panel_selection_changed()

    def _find_sessions_with_panel(self, panel_id: str) -> List[Tuple[str, str]]:
        """Find all sessions that use the given panel.

        Returns list of (session_key, role) where role is 'before' or 'after'.
        """
        matches = []
        for session_key, session in self._sessions.items():
            if session.before_panel_id == panel_id:
                matches.append((session_key, 'before'))
            elif session.after_panel_id == panel_id:
                matches.append((session_key, 'after'))
        return matches

    def _refresh_panel_list(self):
        """Refresh the list of available panels."""
        if not self._workspace:
            return

        # Save current selections
        before_id = self._before_combo.currentData()
        after_id = self._after_combo.currentData()

        self._before_combo.clear()
        self._after_combo.clear()

        self._before_combo.addItem("(Select panel)", None)
        self._after_combo.addItem("(Select panel)", None)

        # Get panels from workspace
        for i, panel in enumerate(self._workspace.panels):
            # Build a more descriptive label
            panel_id = panel.panel_id

            # Try to get file name if loaded
            file_name = None
            if hasattr(panel, 'current_file_path') and panel.current_file_path:
                file_name = os.path.basename(panel.current_file_path)

            # Create label: "Panel 1: filename" or "Panel 1 (empty)"
            if file_name:
                label = f"Panel {i+1}: {file_name}"
            else:
                label = f"Panel {i+1} (empty)"

            self._before_combo.addItem(label, panel_id)
            self._after_combo.addItem(label, panel_id)

        # Restore selections if possible
        if before_id:
            idx = self._before_combo.findData(before_id)
            if idx >= 0:
                self._before_combo.setCurrentIndex(idx)

        if after_id:
            idx = self._after_combo.findData(after_id)
            if idx >= 0:
                self._after_combo.setCurrentIndex(idx)

    def _get_session_key(self, before_id: Optional[str], after_id: Optional[str]) -> Optional[str]:
        """Generate a unique key for a panel pair session."""
        if not before_id or not after_id:
            return None
        if before_id == after_id:
            return None
        return f"{before_id}::{after_id}"

    def _save_current_session(self):
        """Save the current session to the sessions dictionary."""
        if self._current_session_key and self._session:
            # Only save if there's actual data
            has_data = (len(self._session.sink_pairings) > 0 or
                       len(self._session.small_hole_fates) > 0)
            if has_data or self._current_session_key in self._sessions:
                self._sessions[self._current_session_key] = self._session

    def _load_or_create_session(self, session_key: Optional[str]) -> PairingSession:
        """Load existing session or create new one for the given key."""
        if session_key and session_key in self._sessions:
            return self._sessions[session_key]
        return PairingSession()

    def _on_panel_selection_changed(self):
        """Handle panel selection changes."""
        # Clear any existing highlights when panels change
        self._clear_highlights()

        before_id = self._before_combo.currentData()
        after_id = self._after_combo.currentData()

        # Generate new session key
        new_session_key = self._get_session_key(before_id, after_id)

        # If switching to a different panel pair, save current and load new
        if new_session_key != self._current_session_key:
            # Save current session
            self._save_current_session()

            # Load or create session for new panel pair
            self._session = self._load_or_create_session(new_session_key)
            self._current_session_key = new_session_key

            # Update session with panel info
            if new_session_key:
                self._session.before_panel_id = before_id
                self._session.after_panel_id = after_id
                self._session.before_panel_title = self._before_combo.currentText()
                self._session.after_panel_title = self._after_combo.currentText()

        # Refresh hole dropdowns for manual pairing
        self._refresh_hole_dropdowns()

        # Update absorbed dropdown with confirmed pairings
        self._update_absorbed_dropdown()
        self._update_stats()
        self._update_unassigned_lists()

        # Update lists from loaded session
        self._update_suggestions_list()
        self._update_confirmed_list()

        # Rebuild small holes list from session fates
        if self._session.small_hole_fates:
            holes = [f.hole for f in self._session.small_hole_fates if f.hole]
            self._update_small_holes_list(holes)

    def _on_config_changed(self):
        """Handle configuration changes."""
        self._session.sink_threshold_nm2 = self._threshold_spin.value()
        self._session.match_tolerance_nm = self._tolerance_spin.value()
        self._session.touch()

    def _refresh_hole_dropdowns(self):
        """Refresh the manual pairing hole dropdowns with current polygons."""
        before_id = self._session.before_panel_id
        after_id = self._session.after_panel_id

        # Clear and add placeholder
        self._before_hole_combo.clear()
        self._after_hole_combo.clear()
        self._before_hole_combo.addItem("(Select hole)", None)
        self._after_hole_combo.addItem("(Select hole)", None)

        if not before_id or not after_id:
            return

        # Get all holes from both panels
        before_holes = self._get_panel_polygons(before_id)
        after_holes = self._get_panel_polygons(after_id)

        # Get IDs of holes already used in pairings (both confirmed and suggested)
        used_before_ids = set()
        used_after_ids = set()
        for p in self._session.sink_pairings:
            if p.before_hole:
                used_before_ids.add(p.before_hole.polygon_id)
            if p.after_hole:
                used_after_ids.add(p.after_hole.polygon_id)

        # Populate before holes
        for hole in before_holes:
            used_marker = " [PAIRED]" if hole.polygon_id in used_before_ids else ""
            text = f"#{hole.polygon_id}: {hole.area_nm2:.2f} nm²{used_marker}"
            self._before_hole_combo.addItem(text, hole)

        # Populate after holes
        for hole in after_holes:
            used_marker = " [PAIRED]" if hole.polygon_id in used_after_ids else ""
            text = f"#{hole.polygon_id}: {hole.area_nm2:.2f} nm²{used_marker}"
            self._after_hole_combo.addItem(text, hole)

    def _on_manual_hole_selected(self):
        """Handle manual hole selection - highlight the selected hole."""
        # Clear previous highlights
        self._clear_highlights()

        # Highlight before hole if selected
        before_hole = self._before_hole_combo.currentData()
        after_hole = self._after_hole_combo.currentData()

        if before_hole:
            self._highlight_hole(before_hole, '#00FFFF', f"#{before_hole.polygon_id}\nBEFORE")
        if after_hole:
            self._highlight_hole(after_hole, '#FF00FF', f"#{after_hole.polygon_id}\nAFTER")

    def _create_manual_pair(self):
        """Create a manual pairing from selected holes."""
        before_hole = self._before_hole_combo.currentData()
        after_hole = self._after_hole_combo.currentData()

        if not before_hole:
            QMessageBox.warning(self, "Missing Selection",
                                "Please select a 'Before' hole.")
            return

        if not after_hole:
            QMessageBox.warning(self, "Missing Selection",
                                "Please select an 'After' hole.")
            return

        # Check if either hole is already paired
        for p in self._session.sink_pairings:
            if p.before_hole and p.before_hole.polygon_id == before_hole.polygon_id:
                QMessageBox.warning(self, "Already Paired",
                                    f"Before hole #{before_hole.polygon_id} is already in a pairing.")
                return
            if p.after_hole and p.after_hole.polygon_id == after_hole.polygon_id:
                QMessageBox.warning(self, "Already Paired",
                                    f"After hole #{after_hole.polygon_id} is already in a pairing.")
                return

        # Get image center for distance calculation
        center = self._get_image_center(self._session.before_panel_id)
        cal_scale = self._get_calibration_scale(self._session.before_panel_id)

        # Calculate distance to center
        dist_px = 0.0
        dist_nm = 0.0
        if center:
            dx = before_hole.centroid[0] - center[0]
            dy = before_hole.centroid[1] - center[1]
            dist_px = math.sqrt(dx * dx + dy * dy)
            dist_nm = dist_px * cal_scale

        # Create pairing
        pairing = SinkPairing(
            before_hole=before_hole,
            after_hole=after_hole,
            distance_to_center_px=dist_px,
            distance_to_center_nm=dist_nm,
            confirmed=True  # Manual pairings are auto-confirmed
        )
        pairing.calculate_metrics(cal_scale)

        self._session.add_pairing(pairing)

        # Update UI
        self._update_suggestions_list()
        self._update_confirmed_list()
        self._update_absorbed_dropdown()
        self._update_stats()
        self._update_unassigned_lists()
        self._refresh_hole_dropdowns()  # Refresh to show [PAIRED] markers

        # Clear highlights and show success
        self._clear_highlights()
        QMessageBox.information(self, "Pair Created",
                                f"Created pairing {pairing.pairing_id}:\n"
                                f"Before #{before_hole.polygon_id} → After #{after_hole.polygon_id}")

    def _get_panel_by_id(self, panel_id: str):
        """Get a panel by its ID."""
        if not self._workspace:
            return None
        return self._workspace.get_panel_by_id(panel_id)

    def _get_panel_polygons(self, panel_id: str) -> List[HoleReference]:
        """Get all polygons from a panel as HoleReference objects."""
        panel = self._get_panel_by_id(panel_id)
        if not panel:
            return []

        holes = []

        # Get display panel content
        display_panel = None
        if hasattr(panel, 'display_panel'):
            display_panel = panel.display_panel
        elif hasattr(panel, '_display_panel'):
            display_panel = panel._display_panel

        if not display_panel:
            return []

        # Get measurement overlay
        measurement_overlay = None
        if hasattr(display_panel, '_measurement_overlay'):
            measurement_overlay = display_panel._measurement_overlay
        elif hasattr(display_panel, 'measurement_overlay'):
            measurement_overlay = display_panel.measurement_overlay

        if not measurement_overlay:
            return []

        # Get calibration
        calibration = getattr(measurement_overlay, 'calibration', None)
        cal_scale = calibration.scale if calibration and hasattr(calibration, 'scale') else 1.0

        # Get polygons
        polygon_rois = getattr(measurement_overlay, 'active_polygon_rois', [])

        for roi in polygon_rois:
            # Get vertices using same approach as measurement_overlay
            vertices = []
            try:
                handles = roi.getLocalHandlePositions()
                roi_pos = roi.pos()
                for _, handle_pos in handles:
                    x = roi_pos.x() + handle_pos.x()
                    y = roi_pos.y() + handle_pos.y()
                    vertices.append((x, y))
            except Exception:
                continue

            if len(vertices) < 3:
                continue

            # Calculate properties
            # Check both _polygon_id and _measurement_id for compatibility
            polygon_id = getattr(roi, '_polygon_id', None)
            if polygon_id is None:
                polygon_id = getattr(roi, '_measurement_id', 0)
            centroid = calculate_proper_centroid(vertices)
            area_px = calculate_polygon_area(vertices)
            area_nm2 = area_px * (cal_scale ** 2)

            holes.append(HoleReference(
                panel_id=panel_id,
                polygon_id=polygon_id,
                centroid=centroid,
                area_nm2=area_nm2,
                area_px=area_px,
                vertices=vertices
            ))

        return holes

    def _get_image_center(self, panel_id: str) -> Optional[Tuple[float, float]]:
        """Get image center for a panel (vacancy source point)."""
        panel = self._get_panel_by_id(panel_id)
        if not panel:
            return None

        # Get display panel
        display_panel = None
        if hasattr(panel, 'display_panel'):
            display_panel = panel.display_panel
        elif hasattr(panel, '_display_panel'):
            display_panel = panel._display_panel

        if not display_panel:
            return None

        # Get current data shape
        nhdf_data = getattr(display_panel, '_data', None)
        if not nhdf_data:
            return None

        frame_shape = nhdf_data.frame_shape
        if len(frame_shape) >= 2:
            height, width = frame_shape[0], frame_shape[1]
            return (width / 2.0, height / 2.0)

        return None

    def _get_calibration_scale(self, panel_id: str) -> float:
        """Get calibration scale (nm per pixel) for a panel."""
        panel = self._get_panel_by_id(panel_id)
        if not panel:
            return 1.0

        display_panel = None
        if hasattr(panel, 'display_panel'):
            display_panel = panel.display_panel
        elif hasattr(panel, '_display_panel'):
            display_panel = panel._display_panel

        if not display_panel:
            return 1.0

        measurement_overlay = None
        if hasattr(display_panel, '_measurement_overlay'):
            measurement_overlay = display_panel._measurement_overlay

        if measurement_overlay:
            calibration = getattr(measurement_overlay, 'calibration', None)
            if calibration and hasattr(calibration, 'scale'):
                return calibration.scale

        return 1.0

    def _clear_highlights(self):
        """Clear all highlight markers from panels."""
        for marker in self._highlight_markers:
            try:
                if marker.scene():
                    marker.scene().removeItem(marker)
            except Exception:
                pass
        self._highlight_markers.clear()

        for label in self._highlight_labels:
            try:
                if label.scene():
                    label.scene().removeItem(label)
            except Exception:
                pass
        self._highlight_labels.clear()

    def _get_plot_item(self, panel_id: str):
        """Get the plot item for a panel."""
        panel = self._get_panel_by_id(panel_id)
        if not panel:
            return None

        display_panel = None
        if hasattr(panel, 'display_panel'):
            display_panel = panel.display_panel

        if not display_panel:
            return None

        if hasattr(display_panel, '_plot_item'):
            return display_panel._plot_item

        return None

    def _highlight_hole(self, hole: HoleReference, color: str, label_text: str):
        """Add a highlight marker at a hole's centroid."""
        plot_item = self._get_plot_item(hole.panel_id)
        if not plot_item:
            return

        cx, cy = hole.centroid

        # Create a large ring marker at centroid
        marker = pg.ScatterPlotItem(
            [cx], [cy],
            size=30,
            pen=pg.mkPen(color, width=3),
            brush=pg.mkBrush(None),
            symbol='o'
        )
        marker.setZValue(2000)
        plot_item.addItem(marker)
        self._highlight_markers.append(marker)

        # Add label with pairing ID
        label = pg.TextItem(
            text=label_text,
            color=color,
            anchor=(0.5, 2.0)  # Center horizontally, above the marker
        )
        label.setPos(cx, cy)
        label.setZValue(2001)
        font = label.textItem.font()
        font.setPointSize(12)
        font.setBold(True)
        label.textItem.setFont(font)
        plot_item.addItem(label)
        self._highlight_labels.append(label)

    def _highlight_pairing(self, pairing: SinkPairing):
        """Highlight both holes in a pairing."""
        self._clear_highlights()

        # Use different colors for before (cyan) and after (magenta)
        if pairing.before_hole:
            self._highlight_hole(pairing.before_hole, '#00FFFF', f"{pairing.pairing_id}\nBEFORE")
        if pairing.after_hole:
            self._highlight_hole(pairing.after_hole, '#FF00FF', f"{pairing.pairing_id}\nAFTER")

    def _highlight_small_hole(self, hole: HoleReference):
        """Highlight a single small hole."""
        self._clear_highlights()
        self._highlight_hole(hole, '#FFFF00', "SELECTED")

    def _run_auto_match(self):
        """Run auto-matching algorithm based on centroid proximity."""
        # Clear any existing highlights
        self._clear_highlights()

        before_id = self._session.before_panel_id
        after_id = self._session.after_panel_id

        if not before_id or not after_id:
            QMessageBox.warning(self, "Missing Panels",
                                "Please select both 'Before' and 'After' panels.")
            return

        if before_id == after_id:
            QMessageBox.warning(self, "Same Panel",
                                "Before and After panels must be different.")
            return

        threshold = self._threshold_spin.value()
        tolerance = self._tolerance_spin.value()

        # Get polygons from both panels
        before_holes = self._get_panel_polygons(before_id)
        after_holes = self._get_panel_polygons(after_id)

        if not before_holes:
            QMessageBox.warning(self, "No Polygons",
                                "No polygons found in the 'Before' panel.\n"
                                "Draw polygons around holes first.")
            return

        if not after_holes:
            QMessageBox.warning(self, "No Polygons",
                                "No polygons found in the 'After' panel.\n"
                                "Draw polygons around holes first.")
            return

        # Get image center and calibration
        center = self._get_image_center(before_id)
        if not center:
            QMessageBox.warning(self, "No Image",
                                "Could not determine image center.")
            return

        self._session.image_center_px = center
        cal_scale = self._get_calibration_scale(before_id)
        self._session.calibration_scale = cal_scale

        # Filter to sinks only (area > threshold)
        before_sinks = [h for h in before_holes if h.area_nm2 > threshold]
        after_sinks = [h for h in after_holes if h.area_nm2 > threshold]

        # Clear existing unconfirmed pairings (keep confirmed ones)
        self._session.sink_pairings = [p for p in self._session.sink_pairings if p.confirmed]

        # Track used after holes
        used_after_ids = set()

        # Also skip after holes already used in confirmed pairings
        for p in self._session.sink_pairings:
            if p.after_hole:
                used_after_ids.add(p.after_hole.polygon_id)

        # Match by centroid proximity
        for before_sink in before_sinks:
            # Skip if already in a confirmed pairing
            already_paired = False
            for p in self._session.sink_pairings:
                if p.before_hole and p.before_hole.polygon_id == before_sink.polygon_id:
                    already_paired = True
                    break
            if already_paired:
                continue

            best_match = None
            best_distance = float('inf')

            for after_sink in after_sinks:
                if after_sink.polygon_id in used_after_ids:
                    continue

                # Calculate centroid distance in pixels
                dx = after_sink.centroid[0] - before_sink.centroid[0]
                dy = after_sink.centroid[1] - before_sink.centroid[1]
                distance_px = math.sqrt(dx * dx + dy * dy)
                distance_nm = distance_px * cal_scale

                if distance_nm < tolerance and distance_nm < best_distance:
                    best_match = after_sink
                    best_distance = distance_nm

            if best_match:
                # Calculate distance to center
                cx, cy = center
                dist_to_center_px = math.sqrt(
                    (before_sink.centroid[0] - cx) ** 2 +
                    (before_sink.centroid[1] - cy) ** 2
                )
                dist_to_center_nm = dist_to_center_px * cal_scale

                pairing = SinkPairing(
                    before_hole=before_sink,
                    after_hole=best_match,
                    distance_to_center_px=dist_to_center_px,
                    distance_to_center_nm=dist_to_center_nm,
                    confirmed=False
                )
                pairing.calculate_metrics(cal_scale)

                self._session.add_pairing(pairing)
                used_after_ids.add(best_match.polygon_id)

        # Update small holes list
        small_holes = [h for h in before_holes if h.area_nm2 <= threshold]
        self._update_small_holes_list(small_holes)

        # Update UI
        self._update_suggestions_list()
        self._update_confirmed_list()
        self._update_absorbed_dropdown()
        self._update_stats()
        self._update_unassigned_lists()

        # Show summary
        n_suggestions = len(self._session.get_unconfirmed_pairings())
        n_confirmed = len(self._session.get_confirmed_pairings())
        n_small = len(small_holes)

        QMessageBox.information(
            self, "Auto-Match Complete",
            f"Found {n_suggestions} new suggested pairings.\n"
            f"({n_confirmed} already confirmed)\n"
            f"Small holes (<{threshold} nm²): {n_small}"
        )

    def _update_suggestions_list(self):
        """Update the suggestions list widget."""
        self._suggestions_list.clear()

        for pairing in self._session.get_unconfirmed_pairings():
            before_id = pairing.before_hole.polygon_id if pairing.before_hole else "?"
            after_id = pairing.after_hole.polygon_id if pairing.after_hole else "?"
            delta = pairing.area_change_nm2

            text = f"B#{before_id} → A#{after_id}  (ΔA={delta:+.2f} nm²)"

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, pairing.pairing_id)

            # Color code by area change
            if delta > 0:
                item.setForeground(QBrush(QColor(100, 200, 100)))  # Green for growth
            elif delta < 0:
                item.setForeground(QBrush(QColor(200, 100, 100)))  # Red for shrink

            self._suggestions_list.addItem(item)

    def _update_confirmed_list(self):
        """Update the confirmed pairings list widget."""
        self._confirmed_list.clear()

        for pairing in self._session.get_confirmed_pairings():
            before_id = pairing.before_hole.polygon_id if pairing.before_hole else "?"
            after_id = pairing.after_hole.polygon_id if pairing.after_hole else "?"
            delta = pairing.area_change_nm2
            sqrt_r = pairing.sqrt_A0_over_r

            text = f"✓ B#{before_id}→A#{after_id} ΔA={delta:+.1f} √A/r={sqrt_r:.3f}"

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, pairing.pairing_id)
            self._confirmed_list.addItem(item)

    def _update_small_holes_list(self, holes: List[HoleReference]):
        """Update the small holes list widget."""
        self._small_holes_list.clear()

        for hole in holes:
            # Check if already has a fate assigned
            fate_obj = self._session.get_small_hole_fate(hole.polygon_id, hole.panel_id)
            fate_str = ""
            if fate_obj and fate_obj.fate != HoleFate.UNKNOWN:
                if fate_obj.fate == HoleFate.DISAPPEARED:
                    fate_str = " [GONE]"
                elif fate_obj.fate == HoleFate.SURVIVED:
                    fate_str = " [OK]"
                elif fate_obj.fate == HoleFate.ABSORBED:
                    fate_str = f" [→{fate_obj.absorbed_by_pairing_id}]"

            text = f"#{hole.polygon_id}: {hole.area_nm2:.2f} nm²{fate_str}"

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, (hole.panel_id, hole.polygon_id))

            # Store hole reference for later use
            item.setData(Qt.UserRole + 1, hole)

            # Color by fate
            if fate_obj:
                if fate_obj.fate == HoleFate.DISAPPEARED:
                    item.setForeground(QBrush(QColor(200, 100, 100)))
                elif fate_obj.fate == HoleFate.SURVIVED:
                    item.setForeground(QBrush(QColor(100, 200, 100)))
                elif fate_obj.fate == HoleFate.ABSORBED:
                    item.setForeground(QBrush(QColor(100, 150, 200)))

            self._small_holes_list.addItem(item)

    def _update_absorbed_dropdown(self):
        """Update the absorbed-by dropdown with confirmed pairings."""
        self._absorbed_combo.clear()
        self._absorbed_combo.addItem("(Select sink)", None)

        for pairing in self._session.get_confirmed_pairings():
            before_id = pairing.before_hole.polygon_id if pairing.before_hole else "?"
            text = f"Sink #{before_id} ({pairing.pairing_id})"
            self._absorbed_combo.addItem(text, pairing.pairing_id)

    def _on_suggestion_selected(self):
        """Handle suggestion selection."""
        selected = self._suggestions_list.selectedItems()
        has_selection = len(selected) > 0
        self._confirm_btn.setEnabled(has_selection)
        self._reject_btn.setEnabled(has_selection)

        # Highlight the selected pairing on the images
        if has_selection:
            pairing_id = selected[0].data(Qt.UserRole)
            pairing = self._session.get_pairing_by_id(pairing_id)
            if pairing:
                self._highlight_pairing(pairing)
        else:
            self._clear_highlights()

    def _on_confirmed_selected(self):
        """Handle confirmed pairing selection."""
        selected = self._confirmed_list.selectedItems()
        self._unconfirm_btn.setEnabled(len(selected) > 0)

        # Highlight the selected pairing on the images
        if len(selected) > 0:
            pairing_id = selected[0].data(Qt.UserRole)
            pairing = self._session.get_pairing_by_id(pairing_id)
            if pairing:
                self._highlight_pairing(pairing)
        else:
            self._clear_highlights()

    def _on_small_hole_selected(self):
        """Handle small hole selection."""
        selected = self._small_holes_list.selectedItems()
        has_selection = len(selected) > 0
        has_confirmed = len(self._session.get_confirmed_pairings()) > 0

        self._mark_disappeared_btn.setEnabled(has_selection)
        self._mark_survived_btn.setEnabled(has_selection)
        self._absorbed_combo.setEnabled(has_selection and has_confirmed)
        self._mark_absorbed_btn.setEnabled(has_selection and has_confirmed)

        # Highlight the selected small hole on the image
        if has_selection:
            # The hole reference is stored in Qt.UserRole + 1
            hole = selected[0].data(Qt.UserRole + 1)
            if hole:
                self._highlight_small_hole(hole)
        else:
            self._clear_highlights()

    def _confirm_selected(self):
        """Confirm the selected pairing."""
        selected = self._suggestions_list.selectedItems()
        if not selected:
            return

        pairing_id = selected[0].data(Qt.UserRole)
        self._session.confirm_pairing(pairing_id)

        self._update_suggestions_list()
        self._update_confirmed_list()
        self._update_absorbed_dropdown()
        self._update_stats()
        self._update_unassigned_lists()

        self.pairing_confirmed.emit(self._session.get_pairing_by_id(pairing_id))

    def _reject_selected(self):
        """Reject the selected pairing."""
        selected = self._suggestions_list.selectedItems()
        if not selected:
            return

        pairing_id = selected[0].data(Qt.UserRole)
        self._session.remove_pairing(pairing_id)

        self._update_suggestions_list()
        self._update_stats()
        self._update_unassigned_lists()

        self.pairing_rejected.emit(pairing_id)

    def _confirm_all(self):
        """Confirm all suggested pairings."""
        for pairing in self._session.get_unconfirmed_pairings():
            pairing.confirmed = True

        self._session.touch()
        self._update_suggestions_list()
        self._update_confirmed_list()
        self._update_absorbed_dropdown()
        self._update_stats()
        self._update_unassigned_lists()

    def _unconfirm_selected(self):
        """Move selected pairing back to suggestions."""
        selected = self._confirmed_list.selectedItems()
        if not selected:
            return

        pairing_id = selected[0].data(Qt.UserRole)
        pairing = self._session.get_pairing_by_id(pairing_id)
        if pairing:
            pairing.confirmed = False
            self._session.touch()

        self._update_suggestions_list()
        self._update_confirmed_list()
        self._update_absorbed_dropdown()
        self._update_stats()
        self._update_unassigned_lists()

    def _mark_fate(self, fate: HoleFate):
        """Mark selected small hole with a fate."""
        selected = self._small_holes_list.selectedItems()
        if not selected:
            return

        hole = selected[0].data(Qt.UserRole + 1)
        if not hole:
            return

        self._session.set_small_hole_fate(hole, fate)

        # Refresh the list to show updated fate
        self._refresh_small_holes_display()
        self._update_stats()

    def _mark_absorbed(self):
        """Mark small hole as absorbed by selected sink."""
        selected = self._small_holes_list.selectedItems()
        if not selected:
            return

        hole = selected[0].data(Qt.UserRole + 1)
        if not hole:
            return

        pairing_id = self._absorbed_combo.currentData()
        if not pairing_id:
            QMessageBox.warning(self, "No Sink Selected",
                                "Please select a sink from the dropdown.")
            return

        self._session.set_small_hole_fate(hole, HoleFate.ABSORBED, pairing_id)

        self._refresh_small_holes_display()
        self._update_stats()

    def _refresh_small_holes_display(self):
        """Refresh small holes list preserving the holes."""
        # Get current small holes from list
        holes = []
        for i in range(self._small_holes_list.count()):
            item = self._small_holes_list.item(i)
            hole = item.data(Qt.UserRole + 1)
            if hole:
                holes.append(hole)

        self._update_small_holes_list(holes)

    def _update_stats(self):
        """Update statistics label."""
        n_confirmed = len(self._session.get_confirmed_pairings())
        n_suggestions = len(self._session.get_unconfirmed_pairings())
        n_small = self._small_holes_list.count()

        # Count fates
        n_disappeared = sum(1 for f in self._session.small_hole_fates
                           if f.fate == HoleFate.DISAPPEARED)
        n_absorbed = sum(1 for f in self._session.small_hole_fates
                        if f.fate == HoleFate.ABSORBED)
        n_survived = sum(1 for f in self._session.small_hole_fates
                        if f.fate == HoleFate.SURVIVED)

        # Count total sessions with data
        n_sessions = len([s for s in self._sessions.values()
                         if len(s.sink_pairings) > 0 or len(s.small_hole_fates) > 0])

        text = (f"Sessions: {n_sessions} stored\n"
                f"Sinks: {n_confirmed} confirmed, {n_suggestions} pending\n"
                f"Small holes: {n_small} total\n"
                f"  - Disappeared: {n_disappeared}\n"
                f"  - Absorbed: {n_absorbed}\n"
                f"  - Survived: {n_survived}")

        self._stats_label.setText(text)

    def _update_unassigned_lists(self):
        """Update the lists of unassigned holes."""
        before_id = self._session.before_panel_id
        after_id = self._session.after_panel_id

        self._before_unassigned_list.clear()
        self._after_unassigned_list.clear()

        if not before_id or not after_id:
            self._before_unassigned_label.setText("0 holes")
            self._after_unassigned_label.setText("0 holes")
            return

        # Get all holes from both panels
        before_holes = self._get_panel_polygons(before_id)
        after_holes = self._get_panel_polygons(after_id)

        # Get IDs of holes already in pairings
        paired_before_ids = set()
        paired_after_ids = set()
        for p in self._session.sink_pairings:
            if p.before_hole:
                paired_before_ids.add(p.before_hole.polygon_id)
            if p.after_hole:
                paired_after_ids.add(p.after_hole.polygon_id)

        # Also check small hole fates
        for f in self._session.small_hole_fates:
            if f.hole:
                paired_before_ids.add(f.hole.polygon_id)

        # Find unassigned before holes
        threshold = self._threshold_spin.value()
        unassigned_before = []
        for hole in before_holes:
            if hole.polygon_id not in paired_before_ids:
                # Only show sinks (> threshold) as unassigned
                if hole.area_nm2 > threshold:
                    unassigned_before.append(hole)

        # Find unassigned after holes
        unassigned_after = []
        for hole in after_holes:
            if hole.polygon_id not in paired_after_ids:
                if hole.area_nm2 > threshold:
                    unassigned_after.append(hole)

        # Update before list
        for hole in unassigned_before:
            text = f"#{hole.polygon_id}: {hole.area_nm2:.2f} nm²"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, hole)
            self._before_unassigned_list.addItem(item)

        # Update after list
        for hole in unassigned_after:
            text = f"#{hole.polygon_id}: {hole.area_nm2:.2f} nm²"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, hole)
            self._after_unassigned_list.addItem(item)

        # Update labels with counts
        n_before = len(unassigned_before)
        n_after = len(unassigned_after)

        if n_before == 0:
            self._before_unassigned_label.setText("0 holes ✓")
            self._before_unassigned_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            self._before_unassigned_label.setText(f"{n_before} holes")
            self._before_unassigned_label.setStyleSheet("color: #FF6B6B; font-weight: bold;")

        if n_after == 0:
            self._after_unassigned_label.setText("0 holes ✓")
            self._after_unassigned_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            self._after_unassigned_label.setText(f"{n_after} holes")
            self._after_unassigned_label.setStyleSheet("color: #FF6B6B; font-weight: bold;")

    def _on_before_unassigned_selected(self):
        """Handle selection in before unassigned list."""
        selected = self._before_unassigned_list.selectedItems()
        if selected:
            hole = selected[0].data(Qt.UserRole)
            if hole:
                self._clear_highlights()
                self._highlight_hole(hole, '#FF6B6B', f"#{hole.polygon_id}\nUNASSIGNED")

    def _on_after_unassigned_selected(self):
        """Handle selection in after unassigned list."""
        selected = self._after_unassigned_list.selectedItems()
        if selected:
            hole = selected[0].data(Qt.UserRole)
            if hole:
                self._clear_highlights()
                self._highlight_hole(hole, '#FF6B6B', f"#{hole.polygon_id}\nUNASSIGNED")

    def _import_csv(self):
        """Import pairing data from a previously exported CSV file."""
        # Get file path
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Pairing Data",
            "",
            "CSV Files (*.csv)"
        )

        if not path:
            return

        try:
            sink_pairings = []
            small_hole_fates = []
            current_section = None

            with open(path, 'r') as f:
                reader = csv.reader(f)
                header = None

                for row in reader:
                    if not row:
                        continue

                    line = ','.join(row).strip()

                    # Skip metadata lines
                    if line.startswith('# Electron Fluence'):
                        continue

                    # Detect section headers
                    if '# Sink Pairings' in line:
                        current_section = 'sinks'
                        header = None
                        continue
                    elif '# Small Hole' in line:
                        current_section = 'fates'
                        header = None
                        continue

                    # Skip empty or comment lines
                    if line.startswith('#'):
                        continue

                    # Parse header row
                    if header is None:
                        header = row
                        continue

                    # Parse data rows
                    if current_section == 'sinks' and row[0].startswith('P'):
                        try:
                            # Parse sink pairing
                            pairing_id = row[0]
                            before_polygon_id = int(row[1]) if row[1] else 0
                            after_polygon_id = int(row[2]) if row[2] else 0
                            before_area = float(row[3]) if row[3] else 0
                            after_area = float(row[4]) if row[4] else 0
                            delta_area = float(row[5]) if row[5] else 0
                            distance_to_center = float(row[6]) if row[6] else 0
                            sqrt_A0_over_r = float(row[7]) if row[7] else 0

                            # Find centroid columns (they're near the end)
                            # Format varies - look for centroid columns by header
                            before_cx, before_cy = 0.0, 0.0
                            after_cx, after_cy = 0.0, 0.0

                            if 'before_centroid_x' in header:
                                cx_idx = header.index('before_centroid_x')
                                cy_idx = header.index('before_centroid_y')
                                before_cx = float(row[cx_idx]) if len(row) > cx_idx else 0
                                before_cy = float(row[cy_idx]) if len(row) > cy_idx else 0

                            if 'after_centroid_x' in header:
                                cx_idx = header.index('after_centroid_x')
                                cy_idx = header.index('after_centroid_y')
                                after_cx = float(row[cx_idx]) if len(row) > cx_idx else 0
                                after_cy = float(row[cy_idx]) if len(row) > cy_idx else 0

                            # Create HoleReference objects (without vertices - just metadata)
                            before_hole = HoleReference(
                                panel_id=self._session.before_panel_id or "",
                                polygon_id=before_polygon_id,
                                centroid=(before_cx, before_cy),
                                area_nm2=before_area,
                                area_px=0,  # Not available from CSV
                                vertices=[]  # Not available from CSV
                            )

                            after_hole = HoleReference(
                                panel_id=self._session.after_panel_id or "",
                                polygon_id=after_polygon_id,
                                centroid=(after_cx, after_cy),
                                area_nm2=after_area,
                                area_px=0,
                                vertices=[]
                            )

                            # Create pairing
                            pairing = SinkPairing(
                                before_hole=before_hole,
                                after_hole=after_hole,
                                distance_to_center_px=0,
                                distance_to_center_nm=distance_to_center,
                                confirmed=True
                            )
                            pairing.pairing_id = pairing_id
                            pairing.area_change_nm2 = delta_area
                            pairing.sqrt_A0_over_r = sqrt_A0_over_r

                            sink_pairings.append(pairing)

                        except (ValueError, IndexError) as e:
                            print(f"Warning: Could not parse sink row: {row}, error: {e}")
                            continue

                    elif current_section == 'fates' and row[0].startswith('F'):
                        try:
                            # Parse small hole fate
                            fate_id = row[0]
                            polygon_id = int(row[1]) if row[1] else 0
                            area = float(row[2]) if row[2] else 0
                            fate_str = row[3] if len(row) > 3 else 'unknown'
                            absorbed_by = row[4] if len(row) > 4 and row[4] else None
                            cx = float(row[5]) if len(row) > 5 and row[5] else 0
                            cy = float(row[6]) if len(row) > 6 and row[6] else 0

                            # Map fate string to enum
                            fate_map = {
                                'disappeared': HoleFate.DISAPPEARED,
                                'absorbed': HoleFate.ABSORBED,
                                'survived': HoleFate.SURVIVED,
                                'unknown': HoleFate.UNKNOWN
                            }
                            fate_enum = fate_map.get(fate_str.lower(), HoleFate.UNKNOWN)

                            # Create hole reference
                            hole = HoleReference(
                                panel_id=self._session.before_panel_id or "",
                                polygon_id=polygon_id,
                                centroid=(cx, cy),
                                area_nm2=area,
                                area_px=0,
                                vertices=[]
                            )

                            # Create fate object
                            fate_obj = SmallHoleFate(
                                hole=hole,
                                fate=fate_enum,
                                absorbed_by_pairing_id=absorbed_by
                            )
                            fate_obj.fate_id = fate_id

                            small_hole_fates.append(fate_obj)

                        except (ValueError, IndexError) as e:
                            print(f"Warning: Could not parse fate row: {row}, error: {e}")
                            continue

            # Add imported data to current session
            for pairing in sink_pairings:
                self._session.sink_pairings.append(pairing)

            for fate in small_hole_fates:
                self._session.small_hole_fates.append(fate)

            self._session.touch()

            # Update UI
            self._update_suggestions_list()
            self._update_confirmed_list()
            self._update_absorbed_dropdown()
            self._update_stats()

            # Rebuild small holes list
            if small_hole_fates:
                holes = [f.hole for f in small_hole_fates if f.hole]
                self._update_small_holes_list(holes)

            QMessageBox.information(
                self, "Import Complete",
                f"Imported from: {os.path.basename(path)}\n\n"
                f"Sink pairings: {len(sink_pairings)}\n"
                f"Small hole fates: {len(small_hole_fates)}"
            )

        except Exception as e:
            QMessageBox.critical(self, "Import Error",
                                f"Failed to import CSV:\n{str(e)}")

    def _export_csv(self):
        """Export pairing data to CSV."""
        if not self._session.get_confirmed_pairings() and not self._session.small_hole_fates:
            QMessageBox.warning(self, "No Data",
                                "No confirmed pairings or small hole fates to export.")
            return

        # Prompt for electron fluence
        # PySide6 uses positional args: parent, title, label, value, minValue, maxValue, decimals
        fluence, ok = QInputDialog.getDouble(
            self,
            "Electron Fluence",
            "Enter electron fluence (e⁻/nm²):\n\n"
            "This value will be used to normalize ΔA.\n"
            "Enter 0 to skip normalization.",
            0.0,   # value
            0.0,   # minValue
            1e12,  # maxValue
            2      # decimals
        )

        if not ok:
            return

        # Get save path
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Pairing Data",
            "hole_pairings.csv",
            "CSV Files (*.csv)"
        )

        if not path:
            return

        # Get image center for perpendicular width calculation
        image_center = self._session.image_center_px
        calibration = self._session.calibration_scale

        try:
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)

                # Write metadata header
                writer.writerow([f"# Electron Fluence: {fluence} e-/nm2"])
                writer.writerow([])

                # Write sink pairings section
                writer.writerow(["# Sink Pairings"])

                # Build header row
                header = [
                    "pairing_id", "before_polygon_id", "after_polygon_id",
                    "before_area_nm2", "after_area_nm2", "delta_area_nm2",
                    "distance_to_center_nm", "sqrt_A0_over_r"
                ]
                if fluence > 0:
                    header.append("delta_area_normalized")
                header.extend([
                    "before_perp_width_nm", "after_perp_width_nm", "avg_perp_width_nm",
                    "half_avg_perp_over_r",
                    "before_centroid_x", "before_centroid_y",
                    "after_centroid_x", "after_centroid_y"
                ])
                writer.writerow(header)

                for p in self._session.get_confirmed_pairings():
                    before_id = p.before_hole.polygon_id if p.before_hole else ""
                    after_id = p.after_hole.polygon_id if p.after_hole else ""
                    before_area = p.before_hole.area_nm2 if p.before_hole else 0
                    after_area = p.after_hole.area_nm2 if p.after_hole else 0
                    before_cx = p.before_hole.centroid[0] if p.before_hole else 0
                    before_cy = p.before_hole.centroid[1] if p.before_hole else 0
                    after_cx = p.after_hole.centroid[0] if p.after_hole else 0
                    after_cy = p.after_hole.centroid[1] if p.after_hole else 0

                    # Calculate perpendicular widths
                    before_perp_width = 0.0
                    after_perp_width = 0.0
                    if image_center:
                        if p.before_hole and p.before_hole.vertices:
                            before_perp_width = calculate_perpendicular_width(
                                p.before_hole.vertices, p.before_hole.centroid, image_center
                            ) * calibration  # Convert to nm
                        if p.after_hole and p.after_hole.vertices:
                            after_perp_width = calculate_perpendicular_width(
                                p.after_hole.vertices, p.after_hole.centroid, image_center
                            ) * calibration  # Convert to nm

                    avg_perp_width = (before_perp_width + after_perp_width) / 2.0
                    half_avg_perp_over_r = (avg_perp_width / 2.0) / p.distance_to_center_nm if p.distance_to_center_nm > 0 else 0

                    # Calculate normalized delta area
                    delta_area_normalized = p.area_change_nm2 / fluence if fluence > 0 else 0

                    # Build row
                    row = [
                        p.pairing_id, before_id, after_id,
                        f"{before_area:.4f}", f"{after_area:.4f}", f"{p.area_change_nm2:.4f}",
                        f"{p.distance_to_center_nm:.4f}", f"{p.sqrt_A0_over_r:.6f}"
                    ]
                    if fluence > 0:
                        row.append(f"{delta_area_normalized:.6e}")
                    row.extend([
                        f"{before_perp_width:.4f}", f"{after_perp_width:.4f}", f"{avg_perp_width:.4f}",
                        f"{half_avg_perp_over_r:.6f}",
                        f"{before_cx:.2f}", f"{before_cy:.2f}",
                        f"{after_cx:.2f}", f"{after_cy:.2f}"
                    ])
                    writer.writerow(row)

                writer.writerow([])

                # Write small hole fates section
                writer.writerow(["# Small Hole Fates"])
                writer.writerow([
                    "fate_id", "polygon_id", "area_nm2", "fate",
                    "absorbed_by_pairing_id", "centroid_x", "centroid_y"
                ])

                for f in self._session.small_hole_fates:
                    if f.hole:
                        writer.writerow([
                            f.fate_id, f.hole.polygon_id, f"{f.hole.area_nm2:.4f}",
                            f.fate.value, f.absorbed_by_pairing_id or "",
                            f"{f.hole.centroid[0]:.2f}", f"{f.hole.centroid[1]:.2f}"
                        ])

            fluence_msg = f"\nFluence: {fluence} e⁻/nm²" if fluence > 0 else "\nFluence: not specified"
            QMessageBox.information(self, "Export Complete",
                                    f"Data exported to:\n{path}{fluence_msg}")

        except Exception as e:
            QMessageBox.critical(self, "Export Error",
                                 f"Failed to export: {str(e)}")

    def _clear_all(self):
        """Clear all pairings and start over."""
        reply = QMessageBox.question(
            self, "Clear All",
            "Are you sure you want to clear all pairings and fates\n"
            "for the current panel pair?\n\n"
            "This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self._session.clear()
            # Remove from sessions storage since it's now empty
            if self._current_session_key and self._current_session_key in self._sessions:
                del self._sessions[self._current_session_key]
            self._update_suggestions_list()
            self._update_confirmed_list()
            self._small_holes_list.clear()
            self._update_absorbed_dropdown()
            self._update_stats()
            self._update_unassigned_lists()

    def _show_heatmap_dialog(self):
        """Open the ΔA heat map visualization dialog."""
        # Check if we have confirmed pairings
        confirmed = self._session.get_confirmed_pairings()
        if not confirmed:
            QMessageBox.warning(
                self,
                "No Confirmed Pairings",
                "Please confirm at least one sink pairing before generating the heat map.\n\n"
                "The heat map visualizes area change (ΔA) for confirmed pairings."
            )
            return

        # Check if panels are selected
        if not self._session.before_panel_id or not self._session.after_panel_id:
            QMessageBox.warning(
                self,
                "No Panels Selected",
                "Please select both Before and After panels."
            )
            return

        # Open the dialog
        dialog = HeatMapVisualizationDialog(self._session, self._workspace, self)
        dialog.exec()

    def set_theme(self, is_dark: bool):
        """Update theme for the panel."""
        self._is_dark_mode = is_dark

    def get_session(self) -> PairingSession:
        """Get current pairing session for serialization."""
        return self._session

    def set_session(self, session: PairingSession):
        """Load a pairing session."""
        self._session = session
        self._update_ui_from_session()

    def _update_ui_from_session(self):
        """Update UI to reflect loaded session."""
        # Update config spinboxes
        self._threshold_spin.setValue(self._session.sink_threshold_nm2)
        self._tolerance_spin.setValue(self._session.match_tolerance_nm)

        # Try to select panels
        if self._session.before_panel_id:
            idx = self._before_combo.findData(self._session.before_panel_id)
            if idx >= 0:
                self._before_combo.setCurrentIndex(idx)

        if self._session.after_panel_id:
            idx = self._after_combo.findData(self._session.after_panel_id)
            if idx >= 0:
                self._after_combo.setCurrentIndex(idx)

        # Update lists
        self._update_suggestions_list()
        self._update_confirmed_list()
        self._update_absorbed_dropdown()

        # Rebuild small holes list from fates
        holes = [f.hole for f in self._session.small_hole_fates if f.hole]
        self._update_small_holes_list(holes)

        self._update_stats()

    def to_dict(self) -> dict:
        """Serialize panel state for session save."""
        # Save current session first
        self._save_current_session()

        # Serialize all sessions
        sessions_data = {}
        for key, session in self._sessions.items():
            sessions_data[key] = session.to_dict()

        return {
            'sessions': sessions_data,
            'current_session_key': self._current_session_key,
            # Also save current session directly for backwards compatibility
            'current_session': self._session.to_dict() if self._session else None
        }

    def from_dict(self, data: dict):
        """Restore panel state from session."""
        if not data:
            return

        # Check for multi-session format
        if 'sessions' in data:
            # New multi-session format
            sessions_data = data.get('sessions', {})
            self._sessions = {}
            for key, session_data in sessions_data.items():
                self._sessions[key] = PairingSession.from_dict(session_data)

            self._current_session_key = data.get('current_session_key')

            # Load current session
            if self._current_session_key and self._current_session_key in self._sessions:
                self._session = self._sessions[self._current_session_key]
            elif data.get('current_session'):
                self._session = PairingSession.from_dict(data['current_session'])
            else:
                self._session = PairingSession()
        else:
            # Old single-session format (backwards compatibility)
            self._session = PairingSession.from_dict(data)
            # Store in sessions dict if it has panel IDs
            if self._session.before_panel_id and self._session.after_panel_id:
                key = self._get_session_key(self._session.before_panel_id,
                                           self._session.after_panel_id)
                if key:
                    self._sessions[key] = self._session
                    self._current_session_key = key

        self._update_ui_from_session()
