"""
EM file reader module.
Handles loading Nion nhdf (HDF5-based) files and Gatan DM3/DM4 files.
"""

import h5py
import json
import numpy as np
import pathlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Dict, List, Tuple

from nion.data import Calibration
from nion.data import DataAndMetadata
from nion.utils import Converter

# Try to import ncempy for DM3/DM4 support
try:
    import ncempy.io.dm as dm
    HAS_NCEMPY = True
except ImportError:
    HAS_NCEMPY = False

# PIL for standard image formats (PNG, JPG, etc.)
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Supported image extensions
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp')


@dataclass
class CalibrationInfo:
    """Calibration information for a dimension or intensity."""
    offset: float = 0.0
    scale: float = 1.0
    units: str = ""

    @classmethod
    def from_rpc_dict(cls, d: dict) -> "CalibrationInfo":
        return cls(
            offset=d.get("offset", 0.0),
            scale=d.get("scale", 1.0),
            units=d.get("units", "")
        )

    def __str__(self) -> str:
        if self.units:
            return f"{self.scale} {self.units}/pixel (offset: {self.offset})"
        return f"scale={self.scale}, offset={self.offset}"


@dataclass
class DataDescriptor:
    """Describes the meaning of data dimensions."""
    is_sequence: bool = False
    collection_dimension_count: int = 0
    datum_dimension_count: int = 0

    @property
    def sequence_dimension_count(self) -> int:
        return 1 if self.is_sequence else 0

    def describe(self) -> str:
        parts = []
        if self.is_sequence:
            parts.append("Sequence")
        if self.collection_dimension_count > 0:
            parts.append(f"{self.collection_dimension_count}D Collection")
        if self.datum_dimension_count > 0:
            parts.append(f"{self.datum_dimension_count}D Data")
        return " + ".join(parts) if parts else "Unknown"


@dataclass
class NHDFData:
    """Container for data loaded from an nhdf file."""
    # File info
    file_path: pathlib.Path

    # Data array (may be multi-dimensional)
    data: np.ndarray

    # Data description
    data_descriptor: DataDescriptor

    # Calibrations
    intensity_calibration: CalibrationInfo
    dimensional_calibrations: List[CalibrationInfo]

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[datetime] = None
    timezone: Optional[str] = None
    timezone_offset: Optional[str] = None

    # Raw properties (for full metadata access)
    raw_properties: Dict[str, Any] = field(default_factory=dict)

    @property
    def shape(self) -> Tuple[int, ...]:
        return self.data.shape

    @property
    def dtype(self) -> np.dtype:
        return self.data.dtype

    @property
    def ndim(self) -> int:
        return self.data.ndim

    @property
    def num_frames(self) -> int:
        """Number of frames if this is a sequence, otherwise 1."""
        if self.data_descriptor.is_sequence and self.ndim > 0:
            return self.shape[0]
        return 1

    @property
    def frame_shape(self) -> Tuple[int, ...]:
        """Shape of a single frame."""
        if self.data_descriptor.is_sequence and self.ndim > 1:
            return self.shape[1:]
        return self.shape

    def get_frame(self, index: int = 0) -> np.ndarray:
        """Get a single frame from the data."""
        if self.data_descriptor.is_sequence and self.ndim > 1:
            index = max(0, min(index, self.num_frames - 1))
            return self.data[index]
        return self.data

    @property
    def is_2d_image(self) -> bool:
        """Check if frame data is a 2D image."""
        return len(self.frame_shape) == 2

    @property
    def is_1d_data(self) -> bool:
        """Check if frame data is 1D (line profile, spectrum)."""
        return len(self.frame_shape) == 1

    def get_display_name(self) -> str:
        """Get a display name for this data."""
        return self.file_path.stem

    def get_summary(self) -> str:
        """Get a summary string of the data."""
        parts = [
            f"Shape: {self.shape}",
            f"Type: {self.dtype}",
            f"Structure: {self.data_descriptor.describe()}",
        ]
        if self.num_frames > 1:
            parts.append(f"Frames: {self.num_frames}")
        return " | ".join(parts)

    # --- Scan-related properties ---

    @property
    def scan_info(self) -> Dict[str, Any]:
        """Get scan-related metadata."""
        return self.metadata.get("scan", {})

    @property
    def is_subscan(self) -> bool:
        """
        Check if this data is from a subscan (partial scan of a larger context).

        A subscan occurs when scan_size != scan_context_size.
        """
        scan = self.scan_info
        scan_size = scan.get("scan_size", [])
        context_size = scan.get("scan_context_size", [])

        if not scan_size or not context_size:
            return False

        # Normalize to lists for comparison
        if isinstance(scan_size, (list, tuple)) and isinstance(context_size, (list, tuple)):
            # Convert to int for comparison (scan_size might be floats)
            scan_size = [int(s) for s in scan_size]
            context_size = [int(c) for c in context_size]
            return scan_size != context_size

        return False

    @property
    def context_fov_nm(self) -> Optional[float]:
        """Get the FOV of the full scan context in nm (from metadata)."""
        return self.scan_info.get("fov_nm")

    @property
    def actual_fov(self) -> Optional[Tuple[float, float, str]]:
        """
        Calculate actual FOV from calibrations.

        Returns:
            Tuple of (fov_y, fov_x, units) or None if not applicable.
        """
        if not self.is_2d_image:
            return None

        # Get spatial calibrations (skip sequence dimension if present)
        spatial_cals = self.dimensional_calibrations
        if self.data_descriptor.is_sequence and len(spatial_cals) > 2:
            spatial_cals = spatial_cals[1:]  # Skip sequence dimension

        if len(spatial_cals) < 2:
            return None

        y_cal, x_cal = spatial_cals[0], spatial_cals[1]
        ny, nx = self.frame_shape

        fov_y = ny * abs(y_cal.scale)
        fov_x = nx * abs(x_cal.scale)
        units = y_cal.units or x_cal.units or ""

        return (fov_y, fov_x, units)

    @property
    def scan_center_nm(self) -> Optional[Tuple[float, float]]:
        """Get the scan center position in nm (for subscans)."""
        scan = self.scan_info
        x = scan.get("center_x_nm")
        y = scan.get("center_y_nm")
        if x is not None and y is not None:
            return (x, y)
        return None

    @property
    def scan_rotation_deg(self) -> Optional[float]:
        """Get the scan rotation in degrees."""
        return self.scan_info.get("rotation_deg")

    @property
    def hardware_source(self) -> Dict[str, Any]:
        """Get hardware source information."""
        return self.metadata.get("hardware_source", {})

    @property
    def channel_name(self) -> Optional[str]:
        """Get the detector channel name (e.g., 'MADF', 'HAADF')."""
        return self.hardware_source.get("channel_name")

    @property
    def pixel_time_us(self) -> Optional[float]:
        """Get the pixel dwell time in microseconds."""
        return self.hardware_source.get("pixel_time_us")

    @property
    def exposure_time(self) -> Optional[float]:
        """Get the total exposure time in seconds."""
        return self.hardware_source.get("exposure")

    @property
    def pixel_size_nm(self) -> Optional[float]:
        """Get the pixel size in nm (assumes square pixels)."""
        if not self.is_2d_image:
            return None

        # Get spatial calibrations (skip sequence dimension if present)
        spatial_cals = self.dimensional_calibrations
        if self.data_descriptor.is_sequence and len(spatial_cals) > 2:
            spatial_cals = spatial_cals[1:]

        if len(spatial_cals) < 2:
            return None

        # Use the first spatial calibration (y dimension)
        cal = spatial_cals[0]
        if cal.units in ('nm', 'nanometer', 'nanometers'):
            return abs(cal.scale)
        elif cal.units in ('um', 'µm', 'micrometer', 'micrometers'):
            return abs(cal.scale) * 1000  # Convert to nm
        elif cal.units in ('m', 'meter', 'meters'):
            return abs(cal.scale) * 1e9  # Convert to nm

        # If no units, assume nm
        return abs(cal.scale)

    def calculate_electron_dose(self, probe_current_pA: float = 15.0) -> Optional[Dict[str, float]]:
        """
        Calculate electron dose, flux, and electron counts.

        Args:
            probe_current_pA: Probe current in picoamperes (default: 15 pA)

        Returns:
            Dictionary with dose calculations or None if data is insufficient.
            Keys: 'dose_e_per_nm2', 'dose_e_per_A2', 'flux_e_per_nm2_s', 'flux_e_per_A2_s',
                  'pixel_size_nm', 'pixel_time_us', 'electrons_per_pixel',
                  'electrons_per_frame', 'total_electrons_series', 'num_pixels',
                  'num_frames', 'frame_area_nm2', 'frame_area_A2'
        """
        pixel_size_nm = self.pixel_size_nm
        pixel_time_us = self.pixel_time_us

        if pixel_size_nm is None or pixel_time_us is None:
            return None

        # Constants
        e_charge = 1.602e-19  # Coulombs (electron charge)

        # Convert units
        probe_current_A = probe_current_pA * 1e-12  # pA to A
        pixel_time_s = pixel_time_us * 1e-6  # µs to s
        pixel_size_A = pixel_size_nm * 10  # nm to Å

        # Calculate pixel area
        pixel_area_nm2 = pixel_size_nm ** 2
        pixel_area_A2 = pixel_size_A ** 2

        # Calculate electrons per pixel
        # electrons = (current [A] × time [s]) / e [C]
        electrons_per_pixel = (probe_current_A * pixel_time_s) / e_charge

        # Calculate dose (electrons per area)
        dose_e_per_nm2 = electrons_per_pixel / pixel_area_nm2
        dose_e_per_A2 = electrons_per_pixel / pixel_area_A2

        # Calculate flux (dose rate)
        # For a single frame, flux = dose / pixel_time
        flux_e_per_nm2_s = dose_e_per_nm2 / pixel_time_s
        flux_e_per_A2_s = dose_e_per_A2 / pixel_time_s

        # Calculate frame-level electron counts
        frame_shape = self.frame_shape
        num_pixels = frame_shape[0] * frame_shape[1] if len(frame_shape) >= 2 else 1
        num_frames = self.num_frames

        # Total electrons per frame = electrons/pixel × number of pixels
        electrons_per_frame = electrons_per_pixel * num_pixels

        # Total electrons in the entire series = electrons/frame × number of frames
        total_electrons_series = electrons_per_frame * num_frames

        # Frame area (for reference)
        frame_area_nm2 = pixel_area_nm2 * num_pixels
        frame_area_A2 = pixel_area_A2 * num_pixels

        return {
            'dose_e_per_nm2': dose_e_per_nm2,
            'dose_e_per_A2': dose_e_per_A2,
            'flux_e_per_nm2_s': flux_e_per_nm2_s,
            'flux_e_per_A2_s': flux_e_per_A2_s,
            'pixel_size_nm': pixel_size_nm,
            'pixel_time_us': pixel_time_us,
            'electrons_per_pixel': electrons_per_pixel,
            'probe_current_pA': probe_current_pA,
            # New electron count fields
            'electrons_per_frame': electrons_per_frame,
            'total_electrons_series': total_electrons_series,
            'num_pixels': num_pixels,
            'num_frames': num_frames,
            'frame_area_nm2': frame_area_nm2,
            'frame_area_A2': frame_area_A2
        }


class NHDFReader:
    """Reader for Nion nhdf files."""

    def __init__(self):
        self._cache: Dict[str, NHDFData] = {}

    def read(self, path: pathlib.Path, use_cache: bool = True) -> NHDFData:
        """
        Read an nhdf file and return the data and metadata.

        Args:
            path: Path to the nhdf file
            use_cache: Whether to use cached data if available

        Returns:
            NHDFData object containing the data and metadata
        """
        path = pathlib.Path(path)
        cache_key = str(path.resolve())

        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if not path.suffix.lower() == '.nhdf':
            raise ValueError(f"Not an nhdf file: {path}")

        with h5py.File(str(path), "r") as f:
            # Read the data group
            if "data" not in f:
                raise ValueError(f"No 'data' group found in {path}")

            dg = f["data"]

            # Get the first key (may have multiple in future)
            keys = list(sorted(dg.keys()))
            if not keys:
                raise ValueError(f"No datasets found in {path}")

            key0 = keys[0]
            ds = dg[key0]

            # Read the properties attribute
            if "properties" not in ds.attrs:
                raise ValueError(f"No 'properties' attribute found in dataset")

            json_properties = json.loads(ds.attrs["properties"])

            # Read the data (load into memory)
            data = np.array(ds)

            # Create data descriptor
            data_descriptor = DataDescriptor(
                is_sequence=json_properties.get("is_sequence", False),
                collection_dimension_count=json_properties.get("collection_dimension_count", 0),
                datum_dimension_count=json_properties.get("datum_dimension_count", 0)
            )

            # Create calibrations
            intensity_cal_dict = json_properties.get("intensity_calibration", {})
            intensity_calibration = CalibrationInfo.from_rpc_dict(intensity_cal_dict)

            dim_cals = json_properties.get("dimensional_calibrations", [])
            dimensional_calibrations = [
                CalibrationInfo.from_rpc_dict(d) for d in dim_cals
            ]

            # Parse timestamp
            timestamp = None
            created_str = json_properties.get("created", "")
            if created_str:
                try:
                    timestamp = Converter.DatetimeToStringConverter().convert_back(created_str)
                except Exception:
                    pass

            # Create result object
            result = NHDFData(
                file_path=path,
                data=data,
                data_descriptor=data_descriptor,
                intensity_calibration=intensity_calibration,
                dimensional_calibrations=dimensional_calibrations,
                metadata=json_properties.get("metadata", {}),
                timestamp=timestamp,
                timezone=json_properties.get("timezone"),
                timezone_offset=json_properties.get("timezone_offset"),
                raw_properties=json_properties
            )

            if use_cache:
                self._cache[cache_key] = result

            return result

    def clear_cache(self, path: Optional[pathlib.Path] = None):
        """Clear the cache, optionally for a specific file."""
        if path is None:
            self._cache.clear()
        else:
            cache_key = str(pathlib.Path(path).resolve())
            self._cache.pop(cache_key, None)

    def get_file_info(self, path: pathlib.Path) -> Dict[str, Any]:
        """
        Get basic info about an nhdf file without loading all data.
        Useful for file browser preview.
        """
        path = pathlib.Path(path)

        with h5py.File(str(path), "r") as f:
            if "data" not in f:
                return {"error": "No data group"}

            dg = f["data"]
            keys = list(sorted(dg.keys()))
            if not keys:
                return {"error": "No datasets"}

            ds = dg[keys[0]]
            json_properties = json.loads(ds.attrs.get("properties", "{}"))

            return {
                "shape": ds.shape,
                "dtype": str(ds.dtype),
                "is_sequence": json_properties.get("is_sequence", False),
                "num_frames": ds.shape[0] if json_properties.get("is_sequence", False) else 1,
                "created": json_properties.get("created", ""),
            }


class DM3Reader:
    """Reader for Gatan DM3/DM4 files."""

    def __init__(self):
        self._cache: Dict[str, NHDFData] = {}

    def can_read(self) -> bool:
        """Check if DM3/DM4 reading is available."""
        return HAS_NCEMPY

    def read(self, path: pathlib.Path, use_cache: bool = True) -> NHDFData:
        """
        Read a DM3/DM4 file and return the data in NHDFData format.

        Args:
            path: Path to the DM3/DM4 file
            use_cache: Whether to use cached data if available

        Returns:
            NHDFData object containing the data and metadata
        """
        if not HAS_NCEMPY:
            raise ImportError(
                "ncempy is required to read DM3/DM4 files. "
                "Install with: pip install ncempy"
            )

        path = pathlib.Path(path)
        cache_key = str(path.resolve())

        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        suffix = path.suffix.lower()
        if suffix not in ('.dm3', '.dm4'):
            raise ValueError(f"Not a DM3/DM4 file: {path}")

        # Read the DM file
        dmfile = dm.fileDM(str(path))

        # Get the first dataset (most DM files have only one)
        if dmfile.numObjects < 1:
            raise ValueError(f"No datasets found in {path}")

        dataset = dmfile.getDataset(0)
        data = dataset['data']

        # Get calibrations from dataset
        pixel_size = dataset.get('pixelSize', [1.0] * data.ndim)
        pixel_unit = dataset.get('pixelUnit', [''] * data.ndim)
        pixel_origin = dataset.get('pixelOrigin', [0.0] * data.ndim)

        # Create calibrations (DM uses origin as center, we convert to offset)
        dimensional_calibrations = []
        for i in range(data.ndim):
            scale = pixel_size[i] if i < len(pixel_size) else 1.0
            units = pixel_unit[i] if i < len(pixel_unit) else ''
            origin = pixel_origin[i] if i < len(pixel_origin) else 0.0
            # DM origin is the coordinate of pixel 0, convert to offset
            offset = -origin * scale
            dimensional_calibrations.append(CalibrationInfo(
                offset=offset,
                scale=scale,
                units=units
            ))

        # Get intensity calibration from tags
        all_tags = dmfile.allTags
        intensity_scale = all_tags.get('.ImageList.1.ImageData.Calibrations.Brightness.Scale', 1.0)
        intensity_offset = all_tags.get('.ImageList.1.ImageData.Calibrations.Brightness.Origin', 0.0)
        intensity_units = all_tags.get('.ImageList.1.ImageData.Calibrations.Brightness.Units', '')

        intensity_calibration = CalibrationInfo(
            offset=float(intensity_offset) if intensity_offset else 0.0,
            scale=float(intensity_scale) if intensity_scale else 1.0,
            units=str(intensity_units) if intensity_units else ''
        )

        # Determine if this is a sequence (3D data)
        is_sequence = data.ndim == 3
        datum_dim_count = 2 if data.ndim >= 2 else data.ndim

        data_descriptor = DataDescriptor(
            is_sequence=is_sequence,
            collection_dimension_count=0,
            datum_dimension_count=datum_dim_count
        )

        # Extract metadata from tags
        metadata = self._extract_metadata(all_tags)

        # Parse timestamp
        timestamp = None
        timestamp_str = all_tags.get('.ImageList.1.ImageTags.Timestamp', '')
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except Exception:
                pass

        # Also try DataBar timestamp
        if timestamp is None:
            acq_date = all_tags.get('.DataBar.Acquisition Date', '')
            acq_time = all_tags.get('.DataBar.Acquisition Time', '')
            if acq_date and acq_time:
                try:
                    # Parse MM/DD/YY and HH:MM:SS format
                    dt_str = f"{acq_date} {acq_time.split()[0]}"  # Remove timezone suffix
                    timestamp = datetime.strptime(dt_str, "%m/%d/%y %H:%M:%S")
                except Exception:
                    pass

        timezone = all_tags.get('.ImageList.1.ImageTags.Timezone')
        timezone_offset = all_tags.get('.ImageList.1.ImageTags.TimezoneOffset')

        # Build raw properties dict (similar to nhdf format)
        raw_properties = {
            'type': 'dm-data-item',
            'data_shape': list(data.shape),
            'data_dtype': str(data.dtype),
            'is_sequence': is_sequence,
            'dimensional_calibrations': [
                {'offset': c.offset, 'scale': c.scale, 'units': c.units}
                for c in dimensional_calibrations
            ],
            'intensity_calibration': {
                'offset': intensity_calibration.offset,
                'scale': intensity_calibration.scale,
                'units': intensity_calibration.units
            },
            'metadata': metadata,
            'source_format': 'dm3' if suffix == '.dm3' else 'dm4'
        }

        # Create result object
        result = NHDFData(
            file_path=path,
            data=data,
            data_descriptor=data_descriptor,
            intensity_calibration=intensity_calibration,
            dimensional_calibrations=dimensional_calibrations,
            metadata=metadata,
            timestamp=timestamp,
            timezone=timezone,
            timezone_offset=timezone_offset,
            raw_properties=raw_properties
        )

        if use_cache:
            self._cache[cache_key] = result

        return result

    def _extract_metadata(self, tags: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata from DM tags into nhdf-compatible structure."""
        metadata = {}

        # Hardware source info
        hw_prefix = '.ImageList.1.ImageTags.hardware_source.'
        hardware_source = {}
        for key, val in tags.items():
            if key.startswith(hw_prefix):
                short_key = key[len(hw_prefix):]
                hardware_source[short_key] = val
        if hardware_source:
            metadata['hardware_source'] = hardware_source

        # Instrument info
        inst_prefix = '.ImageList.1.ImageTags.instrument.'
        instrument = {}
        for key, val in tags.items():
            if key.startswith(inst_prefix):
                short_key = key[len(inst_prefix):]
                # Handle nested keys like ImageScanned.EHT
                parts = short_key.split('.')
                current = instrument
                for part in parts[:-1]:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                current[parts[-1]] = val
        if instrument:
            metadata['instrument'] = instrument

        # Scan info
        scan_prefix = '.ImageList.1.ImageTags.scan.'
        scan = {}
        for key, val in tags.items():
            if key.startswith(scan_prefix):
                short_key = key[len(scan_prefix):]
                scan[short_key] = val
        if scan:
            metadata['scan'] = scan

        return metadata

    def clear_cache(self, path: Optional[pathlib.Path] = None):
        """Clear the cache, optionally for a specific file."""
        if path is None:
            self._cache.clear()
        else:
            cache_key = str(pathlib.Path(path).resolve())
            self._cache.pop(cache_key, None)

    def get_file_info(self, path: pathlib.Path) -> Dict[str, Any]:
        """Get basic info about a DM3/DM4 file without loading all data."""
        if not HAS_NCEMPY:
            return {"error": "ncempy not installed"}

        path = pathlib.Path(path)

        try:
            dmfile = dm.fileDM(str(path))
            if dmfile.numObjects < 1:
                return {"error": "No datasets"}

            dataset = dmfile.getDataset(0)
            data_shape = dataset['data'].shape
            data_dtype = str(dataset['data'].dtype)

            all_tags = dmfile.allTags
            timestamp = all_tags.get('.ImageList.1.ImageTags.Timestamp', '')

            return {
                "shape": data_shape,
                "dtype": data_dtype,
                "is_sequence": len(data_shape) == 3,
                "num_frames": data_shape[0] if len(data_shape) == 3 else 1,
                "created": timestamp,
            }
        except Exception as e:
            return {"error": str(e)}


# Global reader instances
_nhdf_reader = NHDFReader()
_dm3_reader = DM3Reader()


def read_nhdf(path: pathlib.Path, use_cache: bool = True) -> NHDFData:
    """Convenience function to read an nhdf file."""
    return _nhdf_reader.read(path, use_cache)


def read_dm3(path: pathlib.Path, use_cache: bool = True) -> NHDFData:
    """Convenience function to read a DM3/DM4 file."""
    return _dm3_reader.read(path, use_cache)


def read_image_file(path: pathlib.Path) -> NHDFData:
    """
    Read a standard image file (PNG, JPG, TIFF, BMP) and return as NHDFData.

    Args:
        path: Path to the image file

    Returns:
        NHDFData object with the image data
    """
    if not HAS_PIL:
        raise ImportError("PIL/Pillow is required to read image files. Install with: pip install Pillow")

    path = pathlib.Path(path)
    is_rgb = False

    # Open and convert image to numpy array
    with Image.open(path) as img:
        # Convert to RGB if necessary (handles RGBA, palette, etc.)
        if img.mode == 'RGBA':
            # Convert RGBA to RGB with white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode == 'L':
            # Already grayscale, keep as-is
            pass
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Convert to numpy array
        data = np.array(img)

    # Handle grayscale vs color
    if len(data.shape) == 2:
        # Grayscale image - already 2D
        is_rgb = False
    elif len(data.shape) == 3:
        if data.shape[2] == 3:
            # RGB - keep as RGB for proper color display
            is_rgb = True
        elif data.shape[2] == 1:
            # Single channel - squeeze
            data = data.squeeze()
            is_rgb = False

    # Flip vertically for correct display in pyqtgraph (Y=0 at bottom)
    if is_rgb:
        data = np.flip(data, axis=0)
    else:
        data = np.flip(data, axis=0)

    # Create data descriptor (2D image, or 3D for RGB)
    data_descriptor = DataDescriptor(
        is_sequence=False,
        collection_dimension_count=0,
        datum_dimension_count=2
    )

    # Default calibrations (pixels)
    dim_cals = [
        CalibrationInfo(offset=0.0, scale=1.0, units='px'),
        CalibrationInfo(offset=0.0, scale=1.0, units='px')
    ]
    if is_rgb:
        # Add calibration for color channel
        dim_cals.append(CalibrationInfo(offset=0.0, scale=1.0, units=''))
    int_cal = CalibrationInfo(offset=0.0, scale=1.0, units='')

    # Build metadata
    metadata = {
        'title': path.stem,
        'source_format': path.suffix.lower().lstrip('.'),
        'original_size': data.shape,
        'is_rgb': is_rgb
    }

    return NHDFData(
        file_path=path,
        data=data,
        data_descriptor=data_descriptor,
        intensity_calibration=int_cal,
        dimensional_calibrations=dim_cals,
        metadata=metadata,
        timestamp=datetime.now(),
        raw_properties={'title': path.stem, 'is_image_file': True, 'is_rgb': is_rgb}
    )


def read_em_file(path: pathlib.Path, use_cache: bool = True) -> NHDFData:
    """
    Read an EM file or image file and return data in NHDFData format.

    Automatically detects file type based on extension.
    Supports: .nhdf, .dm3, .dm4, .png, .jpg, .jpeg, .tif, .tiff, .bmp
    """
    path = pathlib.Path(path)
    suffix = path.suffix.lower()

    if suffix == '.nhdf':
        return _nhdf_reader.read(path, use_cache)
    elif suffix in ('.dm3', '.dm4'):
        return _dm3_reader.read(path, use_cache)
    elif suffix in IMAGE_EXTENSIONS:
        return read_image_file(path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}. Supported: .nhdf, .dm3, .dm4, .png, .jpg, .tif, .bmp")


def get_file_info(path: pathlib.Path) -> Dict[str, Any]:
    """Convenience function to get file info for any supported format."""
    path = pathlib.Path(path)
    suffix = path.suffix.lower()

    if suffix == '.nhdf':
        return _nhdf_reader.get_file_info(path)
    elif suffix in ('.dm3', '.dm4'):
        return _dm3_reader.get_file_info(path)
    else:
        return {"error": f"Unsupported format: {suffix}"}


def clear_cache(path: Optional[pathlib.Path] = None):
    """Convenience function to clear cache for all readers."""
    _nhdf_reader.clear_cache(path)
    _dm3_reader.clear_cache(path)


def is_supported_file(path: pathlib.Path) -> bool:
    """Check if a file is a supported format (EM or image)."""
    suffix = pathlib.Path(path).suffix.lower()
    return suffix in ('.nhdf', '.dm3', '.dm4') or suffix in IMAGE_EXTENSIONS


def get_supported_extensions() -> List[str]:
    """Get list of supported file extensions."""
    return ['.nhdf', '.dm3', '.dm4'] + list(IMAGE_EXTENSIONS)


def create_nhdf_data_from_array(
    data: np.ndarray,
    name: str = "Processed Data",
    dimensional_calibrations: Optional[List[Dict]] = None,
    intensity_calibration: Optional[Dict] = None,
    source_file: Optional[pathlib.Path] = None,
    metadata: Optional[Dict] = None
) -> NHDFData:
    """
    Create an NHDFData object from a numpy array.

    Useful for displaying processed data in the Preview mode without
    needing to save to a file first.

    Args:
        data: The numpy array data
        name: A name for the data item
        dimensional_calibrations: List of dicts with 'offset', 'scale', 'units' for each dimension
        intensity_calibration: Dict with 'offset', 'scale', 'units' for intensity
        source_file: Optional source file path (for display purposes)
        metadata: Optional additional metadata

    Returns:
        NHDFData object suitable for display in Preview mode
    """
    # Determine data descriptor
    is_sequence = len(data.shape) == 3
    datum_dim_count = 2
    collection_dim_count = 0

    data_descriptor = DataDescriptor(
        is_sequence=is_sequence,
        collection_dimension_count=collection_dim_count,
        datum_dimension_count=datum_dim_count
    )

    # Build dimensional calibrations
    dim_cals = []
    if dimensional_calibrations:
        for cal_dict in dimensional_calibrations:
            dim_cals.append(CalibrationInfo(
                offset=cal_dict.get('offset', 0.0),
                scale=cal_dict.get('scale', 1.0),
                units=cal_dict.get('units', '')
            ))
    else:
        # Default calibrations for each dimension
        for _ in range(len(data.shape)):
            dim_cals.append(CalibrationInfo())

    # Build intensity calibration
    if intensity_calibration:
        int_cal = CalibrationInfo(
            offset=intensity_calibration.get('offset', 0.0),
            scale=intensity_calibration.get('scale', 1.0),
            units=intensity_calibration.get('units', '')
        )
    else:
        int_cal = CalibrationInfo()

    # Create a virtual file path for display
    if source_file:
        virtual_path = pathlib.Path(str(source_file).replace('.nhdf', f'_{name}.nhdf'))
    else:
        virtual_path = pathlib.Path(f"/virtual/{name}.nhdf")

    return NHDFData(
        file_path=virtual_path,
        data=data,
        data_descriptor=data_descriptor,
        intensity_calibration=int_cal,
        dimensional_calibrations=dim_cals,
        metadata=metadata or {},
        timestamp=datetime.now(),
        raw_properties={'title': name, 'is_processed': True}
    )
