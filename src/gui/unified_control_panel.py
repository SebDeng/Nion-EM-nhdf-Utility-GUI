"""
Unified control panel for workspace display.
Shows controls for the currently selected workspace panel.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QComboBox,
    QCheckBox, QDoubleSpinBox, QFrame, QPushButton
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

from typing import Optional
import numpy as np

from src.gui.display_panel import FrameControls


class UnifiedControlPanel(QFrame):
    """
    A unified control panel that sits at the top of the workspace
    and controls the currently selected display panel.
    """

    # Signals
    colormap_changed = Signal(str)
    auto_scale_changed = Signal(bool)
    scale_changed = Signal(float, float)
    scalebar_toggled = Signal(bool)
    frame_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_panel = None
        self._is_updating = False  # Prevent recursive updates

        self._setup_ui()
        self._set_enabled_state(False)

    def _setup_ui(self):
        """Set up the unified control panel UI."""
        self.setFrameShape(QFrame.StyledPanel)
        self.setMaximumHeight(100)  # Slightly taller to accommodate frame controls

        # Main layout - vertical with two rows
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(8)

        # Top row - display controls
        top_row = QFrame()
        top_row.setFrameShape(QFrame.NoFrame)
        layout = QHBoxLayout(top_row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        # Panel indicator section
        panel_section = QFrame()
        panel_layout = QHBoxLayout(panel_section)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(8)

        # Current panel indicator
        self._panel_label = QLabel("No Panel Selected")
        self._panel_label.setStyleSheet("""
            QLabel {
                color: #2a82da;
                font-weight: bold;
                font-size: 12px;
                background-color: rgba(42, 130, 218, 0.1);
                border: 1px solid #2a82da;
                border-radius: 3px;
                padding: 4px 8px;
            }
        """)
        panel_layout.addWidget(self._panel_label)

        layout.addWidget(panel_section)

        # Separator
        separator1 = QFrame()
        separator1.setFrameShape(QFrame.VLine)
        separator1.setStyleSheet("color: #505050;")
        layout.addWidget(separator1)

        # Display controls section
        controls_section = QFrame()
        controls_layout = QHBoxLayout(controls_section)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(12)

        # Colormap selector
        controls_layout.addWidget(QLabel("Colormap:"))
        self._colormap_combo = QComboBox()
        self._colormap_combo.addItems([
            'viridis', 'plasma', 'inferno', 'magma', 'cividis',
            'Greys', 'gray', 'hot', 'cool', 'jet', 'turbo',
            'Blues', 'Reds', 'Greens', 'copper'
        ])
        self._colormap_combo.currentTextChanged.connect(self._on_colormap_changed)
        self._colormap_combo.setFixedWidth(100)
        controls_layout.addWidget(self._colormap_combo)

        # Auto scale checkbox
        self._auto_scale_check = QCheckBox("Auto Scale")
        self._auto_scale_check.setChecked(True)
        self._auto_scale_check.toggled.connect(self._on_auto_scale_changed)
        controls_layout.addWidget(self._auto_scale_check)

        # Manual scale controls
        controls_layout.addWidget(QLabel("Min:"))
        self._min_spin = QDoubleSpinBox()
        self._min_spin.setRange(-1e10, 1e10)
        self._min_spin.setDecimals(2)
        self._min_spin.setEnabled(False)
        self._min_spin.valueChanged.connect(self._on_min_changed)
        self._min_spin.setFixedWidth(100)
        controls_layout.addWidget(self._min_spin)

        controls_layout.addWidget(QLabel("Max:"))
        self._max_spin = QDoubleSpinBox()
        self._max_spin.setRange(-1e10, 1e10)
        self._max_spin.setDecimals(2)
        self._max_spin.setEnabled(False)
        self._max_spin.valueChanged.connect(self._on_max_changed)
        self._max_spin.setFixedWidth(100)
        controls_layout.addWidget(self._max_spin)

        # Scale bar checkbox
        self._scalebar_check = QCheckBox("Scale Bar")
        self._scalebar_check.setChecked(True)
        self._scalebar_check.toggled.connect(self._on_scalebar_toggled)
        controls_layout.addWidget(self._scalebar_check)

        # Subscan area checkbox (only enabled for context scans)
        self._subscan_area_check = QCheckBox("Subscan Area")
        self._subscan_area_check.setChecked(False)
        self._subscan_area_check.setToolTip("Show typical subscan area (only available for context scans)")
        self._subscan_area_check.toggled.connect(self._on_subscan_area_toggled)
        self._subscan_area_check.setEnabled(False)  # Disabled by default
        controls_layout.addWidget(self._subscan_area_check)

        layout.addWidget(controls_section)

        # Info section
        layout.addStretch()

        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self._info_label)

        # Add top row to main layout
        main_layout.addWidget(top_row)

        # Bottom row - frame controls (shown/hidden as needed)
        self._frame_section = QFrame()
        self._frame_section.setFrameShape(QFrame.NoFrame)
        frame_layout = QHBoxLayout(self._frame_section)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(8)

        # Embedded frame controls
        self._frame_controls = FrameControls()
        self._frame_controls.frame_changed.connect(self._on_frame_changed)
        frame_layout.addWidget(self._frame_controls)

        self._frame_section.hide()  # Hidden by default
        main_layout.addWidget(self._frame_section)

    def set_current_panel(self, panel, force_sync: bool = False):
        """Set the current panel to control.

        Args:
            panel: The panel to control
            force_sync: If True, force a re-sync even if same panel (useful after data load)
        """
        is_same_panel = (self._current_panel == panel)

        if is_same_panel and not force_sync:
            return

        # Disconnect from old panel if exists (only if different panel)
        if self._current_panel and not is_same_panel:
            self._disconnect_from_panel(self._current_panel)

        self._current_panel = panel

        if panel and hasattr(panel, 'display_panel') and panel.display_panel:
            # Only connect signals if this is a new panel
            if not is_same_panel:
                self._connect_to_panel(panel)
            self._sync_from_panel(panel)
            self._set_enabled_state(True)

            # Update panel label
            if hasattr(panel, 'title_label'):
                title = panel.title_label.text()
            elif hasattr(panel, '_title_label'):
                title = panel._title_label.text()
            else:
                title = "Display Panel"
            self._panel_label.setText(f"Panel: {title}")
        else:
            self._set_enabled_state(False)
            self._panel_label.setText("No Panel Selected")
            self._info_label.setText("")

    def _connect_to_panel(self, panel):
        """Connect signals to the panel's display."""
        if not panel or not hasattr(panel, 'display_panel'):
            return

        display = panel.display_panel

        # Connect our signals to the display panel
        self.colormap_changed.connect(display._on_colormap_changed)
        self.auto_scale_changed.connect(display._on_auto_scale_changed)
        self.scalebar_toggled.connect(display._on_scalebar_toggled)

        # Connect frame controls if the panel has multi-frame data
        if hasattr(display, '_frame_controls'):
            self.frame_changed.connect(display._frame_controls.set_current_frame)

    def _disconnect_from_panel(self, panel):
        """Disconnect signals from the panel's display."""
        if not panel or not hasattr(panel, 'display_panel'):
            return

        display = panel.display_panel

        # Disconnect our signals
        try:
            self.colormap_changed.disconnect(display._on_colormap_changed)
            self.auto_scale_changed.disconnect(display._on_auto_scale_changed)
            self.scalebar_toggled.disconnect(display._on_scalebar_toggled)

            if hasattr(display, '_frame_controls'):
                self.frame_changed.disconnect(display._frame_controls.set_current_frame)
        except:
            pass  # Ignore disconnection errors

    def _sync_from_panel(self, panel):
        """Sync our controls with the current panel's state."""
        if not panel or not hasattr(panel, 'display_panel'):
            return

        display = panel.display_panel
        if not display:
            return

        self._is_updating = True

        # Sync colormap
        if hasattr(display, '_colormap_combo'):
            current_map = display._colormap_combo.currentText()
            index = self._colormap_combo.findText(current_map)
            if index >= 0:
                self._colormap_combo.setCurrentIndex(index)

        # Sync auto scale
        if hasattr(display, '_auto_scale_check'):
            self._auto_scale_check.setChecked(display._auto_scale_check.isChecked())
            self._min_spin.setEnabled(not display._auto_scale_check.isChecked())
            self._max_spin.setEnabled(not display._auto_scale_check.isChecked())

        # Sync scale values
        if hasattr(display, '_min_spin') and hasattr(display, '_max_spin'):
            self._min_spin.setValue(display._min_spin.value())
            self._max_spin.setValue(display._max_spin.value())

        # Sync scalebar
        if hasattr(display, '_scalebar_check'):
            self._scalebar_check.setChecked(display._scalebar_check.isChecked())

        # Sync subscan area overlay
        if hasattr(display, 'is_subscan_overlay_available'):
            is_available = display.is_subscan_overlay_available()
            self._subscan_area_check.setEnabled(is_available)
            if not is_available:
                self._subscan_area_check.setChecked(False)
                self._subscan_area_check.setToolTip("Only available for context scans (not subscans)")
            else:
                self._subscan_area_check.setToolTip("Show typical subscan area on this context scan")
                # Sync visibility state
                if hasattr(display, '_subscan_overlay'):
                    self._subscan_area_check.setChecked(display._subscan_overlay._visible)

        # Sync frame controls
        if hasattr(display, '_data') and display._data:
            if display._data.num_frames > 1:
                self._frame_section.show()
                self._frame_controls.set_num_frames(display._data.num_frames)
                # Get current frame from display
                current_frame = display._current_frame if hasattr(display, '_current_frame') else 0
                self._frame_controls.set_current_frame(current_frame)
                # Also sync the play button state if playing
                if hasattr(display, '_frame_controls') and hasattr(display._frame_controls, '_is_playing'):
                    if display._frame_controls._is_playing:
                        self._frame_controls._play_btn.setChecked(True)
            else:
                self._frame_section.hide()
        else:
            self._frame_section.hide()

        # Update info label
        if hasattr(display, '_info_label'):
            self._info_label.setText(display._info_label.text())

        self._is_updating = False

    def _set_enabled_state(self, enabled: bool):
        """Enable or disable all controls."""
        self._colormap_combo.setEnabled(enabled)
        self._auto_scale_check.setEnabled(enabled)
        self._scalebar_check.setEnabled(enabled)

        # Min/max only enabled when not auto-scaling
        if enabled and not self._auto_scale_check.isChecked():
            self._min_spin.setEnabled(True)
            self._max_spin.setEnabled(True)
        else:
            self._min_spin.setEnabled(False)
            self._max_spin.setEnabled(False)

    def _on_colormap_changed(self, colormap: str):
        """Handle colormap change."""
        if not self._is_updating:
            self.colormap_changed.emit(colormap)

    def _on_auto_scale_changed(self, checked: bool):
        """Handle auto scale change."""
        if not self._is_updating:
            self._min_spin.setEnabled(not checked)
            self._max_spin.setEnabled(not checked)
            self.auto_scale_changed.emit(checked)

            # Update the panel's controls
            if self._current_panel and hasattr(self._current_panel, 'display_panel'):
                display = self._current_panel.display_panel
                if hasattr(display, '_auto_scale_check'):
                    display._auto_scale_check.setChecked(checked)

    def _on_min_changed(self, value: float):
        """Handle min value change."""
        if not self._is_updating and self._current_panel:
            if hasattr(self._current_panel, 'display_panel'):
                display = self._current_panel.display_panel
                if hasattr(display, '_min_spin'):
                    display._min_spin.setValue(value)
                    display._on_scale_changed()

    def _on_max_changed(self, value: float):
        """Handle max value change."""
        if not self._is_updating and self._current_panel:
            if hasattr(self._current_panel, 'display_panel'):
                display = self._current_panel.display_panel
                if hasattr(display, '_max_spin'):
                    display._max_spin.setValue(value)
                    display._on_scale_changed()

    def _on_scalebar_toggled(self, checked: bool):
        """Handle scalebar toggle."""
        if not self._is_updating:
            self.scalebar_toggled.emit(checked)

    def _on_subscan_area_toggled(self, checked: bool):
        """Handle subscan area overlay toggle."""
        if not self._is_updating and self._current_panel:
            if hasattr(self._current_panel, 'display_panel'):
                display = self._current_panel.display_panel
                if hasattr(display, 'set_subscan_overlay_visible'):
                    display.set_subscan_overlay_visible(checked)

    def _on_frame_changed(self, frame: int):
        """Handle frame change."""
        if not self._is_updating:
            # Update the panel directly
            if self._current_panel and hasattr(self._current_panel, 'display_panel'):
                display = self._current_panel.display_panel
                if hasattr(display, '_on_frame_changed'):
                    display._on_frame_changed(frame)