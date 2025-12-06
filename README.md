# Nion EM nhdf Utility GUI

A modern graphical user interface for visualizing and managing Nion electron microscopy data files in nhdf (HDF5-based) format.

## Features

- **Data Visualization**: View 2D images, line profiles, and multi-dimensional data
- **Free-Tiling Workspace**: NEW! Nion Swift-style panel management with flexible splitting
- **Multi-file Preview**: Open and compare multiple nhdf files simultaneously
- **Metadata Browser**: Explore comprehensive metadata including calibrations, timestamps, and instrument parameters
- **Export Options**: Export data to various formats (TIFF, PNG, JPG, MP4 video, CSV, JSON)
- **Modern UI**: Clean, dark-themed interface built with PySide6 (Qt), inspired by Nion Swift
- **Scale Bar**: Automatic scale bar overlay with calibrated units
- **Frame Navigation**: Playback controls for multi-frame sequences with video export

## Installation

### Prerequisites

- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or [Anaconda](https://www.anaconda.com/products/distribution)

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/SebDeng/Nion-EM-nhdf-Utility-GUI.git
   cd Nion-EM-nhdf-Utility-GUI
   ```

2. Create and activate the conda environment:
   ```bash
   conda create -n nhdf-gui python=3.11 -y
   conda activate nhdf-gui
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Standard Mode (Single Panel)
```bash
conda activate nhdf-gui
python main.py [file.nhdf]
```

### Workspace Mode (Free-Tiling Panels)
```bash
conda activate nhdf-gui
python main.py --workspace [file.nhdf]
```

### Workspace Features
When running in workspace mode (`--workspace`), you can:

- **Split Panels**:
  - Horizontal split: `Ctrl+H` or View → Workspace → Split Horizontally
  - Vertical split: `Ctrl+V` or View → Workspace → Split Vertically
- **Close Panels**: Click the ✕ button on any panel (minimum 1 panel required)
- **Layout Presets**: View → Workspace → Layout Presets
  - Single Panel
  - 2 Panels Horizontal/Vertical
  - 4 Panel Grid (2x2)
- **Save/Load Layouts**: Save your custom workspace arrangements
- **Multiple Files**: Open different nhdf files in separate panels for comparison
- **Drag to Resize**: Grab splitter handles between panels to adjust sizes

## Dependencies

### Core Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| Python | 3.11 | Runtime |
| PySide6 | 6.10.1 | GUI framework (Qt 6, LGPL) |
| numpy | 2.3.5 | Numerical computing |
| h5py | 3.15.1 | HDF5 file I/O |
| matplotlib | 3.10.7 | Data visualization |
| pyqtgraph | 0.14.0 | Fast interactive plotting |
| niondata | 15.9.1 | Nion data structures |
| scipy | 1.16.3 | Scientific computing |

### Full Dependency List

See `requirements.txt` for complete list with all transitive dependencies.

## nhdf File Format

nhdf files are HDF5-based containers for electron microscopy data from Nion instruments. Each file contains:

- **Data**: N-dimensional arrays (images, spectra, sequences)
- **Calibrations**: Spatial and intensity calibrations with units
- **Metadata**: Instrument settings, timestamps, and acquisition parameters

### Data Structure

```
file.nhdf
├── data/
│   └── <uuid>/          # Dataset with raw data
│       └── @properties  # JSON metadata attribute
```

## Development

### Project Structure

```
Nion-EM-nhdf-Utility-GUI/
├── main.py                         # Application entry point
├── src/
│   ├── core/
│   │   ├── nhdf_reader.py          # nhdf file loading and parsing
│   │   └── exporter.py             # Export functionality
│   ├── gui/
│   │   ├── main_window.py          # Standard single-panel window
│   │   ├── workspace_main_window.py # Workspace mode with tiling
│   │   ├── workspace.py            # Free-tiling workspace manager
│   │   ├── workspace_display_panel.py # Workspace display panels
│   │   ├── file_browser.py         # File browser panel
│   │   ├── display_panel.py        # Image display with frame controls
│   │   ├── metadata_panel.py       # Metadata browser
│   │   └── export_dialog.py        # Export configuration dialog
│   └── utils/                      # Utility modules
├── assets/                         # Application icons
├── TestFiles/                      # Sample nhdf files (gitignored)
├── requirements.txt                # Python dependencies
├── DEVELOPMENT_PLAN.md             # Development roadmap
└── README.md
```

### Running Tests

```bash
pytest tests/
```

## License

[MIT License](LICENSE)

## Acknowledgments

- nhdf reading code based on [Chris Meyer's gist](https://gist.github.com/cmeyer) from Nion Software
- Built for the electron microscopy community at Yale University
