# Nion EM nhdf Utility GUI

A modern graphical user interface for visualizing and managing Nion electron microscopy data files in nhdf (HDF5-based) format.

## Features

- **Data Visualization**: View 2D images, line profiles, and multi-dimensional data
- **Multi-file Preview**: Open and compare multiple nhdf files simultaneously
- **Metadata Browser**: Explore comprehensive metadata including calibrations, timestamps, and instrument parameters
- **Export Options**: Export data to various formats (TIFF, PNG, CSV, HDF5)
- **Modern UI**: Clean, dark-themed interface built with PySide6 (Qt), inspired by Nion Swift

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

```bash
conda activate nhdf-gui
python main.py
```

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
├── main.py                  # Application entry point
├── src/
│   ├── core/
│   │   └── nhdf_reader.py   # nhdf file loading and parsing
│   ├── gui/
│   │   ├── main_window.py   # Main application window
│   │   ├── file_browser.py  # File browser panel
│   │   ├── display_panel.py # Image display with frame controls
│   │   └── metadata_panel.py # Metadata browser
│   └── utils/               # Utility modules
├── TestFiles/               # Sample nhdf files for testing (gitignored)
├── requirements.txt         # Python dependencies
├── DEVELOPMENT_PLAN.md      # Development roadmap
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
