# Nion nhdf Utility GUI - Development Plan

## User Preferences

- **UI Framework**: PySide6 (Qt, LGPL license, same as Nion Swift)
- **Design Style**: Similar to Nion Swift's free-tiling windows
- **Target Users**: Nion electron microscopy users

---

## Phase 1: Basic GUI + File Loading + Metadata Browser

**Goal**: Load nhdf files, display images with frame navigation, browse metadata

### Components

#### 1.1 Main Window Structure
- [x] QMainWindow with menu bar, status bar
- [x] Central widget for image display
- [x] Dock widgets for file browser and metadata panel

#### 1.2 File Browser Panel (Left Dock)
- [ ] QTreeView for directory navigation
- [ ] Filter for .nhdf files
- [ ] Double-click or drag to open files
- [ ] Recent files list

#### 1.3 Image Display Panel (Center)
- [ ] Display 2D images using matplotlib or pyqtgraph
- [ ] Frame navigation for sequences:
  - [ ] Slider bar for frame selection
  - [ ] Frame counter (current/total)
  - [ ] Previous/Next buttons
  - [ ] Play/Pause auto-advance
  - [ ] Speed control
- [ ] Basic zoom/pan controls
- [ ] Color map selection
- [ ] Intensity scaling (min/max, auto)

#### 1.4 Metadata Panel (Right Dock)
- [ ] QTreeWidget showing hierarchical metadata
- [ ] Display calibrations (spatial, intensity)
- [ ] Display data properties (shape, dtype, timestamp)
- [ ] Display instrument metadata

#### 1.5 Data Loading Module
- [ ] nhdf file reader (based on Example_Reading_Code.py)
- [ ] Handle multi-frame sequences
- [ ] Extract metadata and calibrations
- [ ] Memory-efficient loading for large files

---

## Phase 2: Data Export

**Goal**: Export data to various formats

### Components

#### 2.1 Export Dialog
- [ ] Format selection (TIFF, PNG, CSV, HDF5, NumPy)
- [ ] Options per format (bit depth, compression, etc.)
- [ ] Export current frame or all frames
- [ ] Batch export from file browser

#### 2.2 Export Formats
- [ ] TIFF (single/multi-page, 8/16/32-bit)
- [ ] PNG (8/16-bit with colormap)
- [ ] CSV (for 1D/2D data)
- [ ] HDF5 (standard format)
- [ ] NumPy (.npy, .npz)
- [ ] Include metadata option (JSON sidecar)

#### 2.3 Export Metadata
- [ ] Export metadata as JSON
- [ ] Export calibrations
- [ ] Include in image EXIF/tags where possible

---

## Phase 3: Free-Tiling Workspace

**Goal**: Multiple panels with Nion Swift-style free-tiling

### Components

#### 3.1 Workspace Manager
- [ ] Splitter-based panel system
- [ ] Horizontal/vertical splitting
- [ ] Drag-to-resize panels
- [ ] Close/maximize individual panels

#### 3.2 Multi-File Preview
- [ ] Open multiple nhdf files simultaneously
- [ ] Each file in separate display panel
- [ ] Synchronized frame navigation (optional)
- [ ] Compare mode (side-by-side, overlay)

#### 3.3 Layout Management
- [ ] Save/load workspace layouts
- [ ] Preset layouts (single, 2x1, 2x2, etc.)
- [ ] Remember last layout on restart

---

## Phase 4: Advanced Features

**Goal**: Enhanced visualization and analysis

### Components

#### 4.1 Enhanced Visualization
- [ ] Line profile tool (draw line, show intensity profile)
- [ ] ROI selection and statistics
- [ ] Histogram panel with adjustable range
- [ ] Multiple color maps

#### 4.2 Data Processing
- [ ] Basic operations (crop, rotate, flip)
- [ ] Binning/downsampling
- [ ] Background subtraction
- [ ] FFT display

#### 4.3 Sequence Tools
- [ ] Sum/average frames
- [ ] Max/min projection
- [ ] Drift correction (basic)
- [ ] Export as video (MP4/GIF)

---

## Project Structure

```
Nion-EM-nhdf-Utility-GUI/
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── README.md              # User documentation
├── DEVELOPMENT_PLAN.md    # This file
│
├── src/
│   ├── __init__.py
│   │
│   ├── core/              # Data handling
│   │   ├── __init__.py
│   │   ├── nhdf_reader.py     # nhdf file loading
│   │   ├── data_model.py      # Data structures
│   │   └── exporter.py        # Export functionality
│   │
│   ├── gui/               # UI components
│   │   ├── __init__.py
│   │   ├── main_window.py     # Main application window
│   │   ├── file_browser.py    # File browser panel
│   │   ├── display_panel.py   # Image/data display
│   │   ├── metadata_panel.py  # Metadata browser
│   │   ├── frame_controls.py  # Frame navigation widget
│   │   └── workspace.py       # Free-tiling workspace (Phase 3)
│   │
│   └── utils/             # Utilities
│       ├── __init__.py
│       └── settings.py        # App settings/preferences
│
└── TestFiles/             # Test data (gitignored)
```

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| GUI Framework | PySide6 (Qt 6) |
| Plotting | pyqtgraph (fast) + matplotlib (publication) |
| Data I/O | h5py, niondata |
| Numerical | numpy, scipy |
| Image Export | Pillow, tifffile |

---

## Milestones

1. **M1**: Basic window with file browser and metadata panel
2. **M2**: Image display with frame navigation
3. **M3**: Export functionality
4. **M4**: Free-tiling multi-panel workspace
5. **M5**: Advanced visualization tools
