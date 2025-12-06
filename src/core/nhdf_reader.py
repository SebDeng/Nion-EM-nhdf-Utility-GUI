"""
nhdf file reader module.
Handles loading Nion nhdf (HDF5-based) files and extracting data/metadata.
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


# Global reader instance
_reader = NHDFReader()


def read_nhdf(path: pathlib.Path, use_cache: bool = True) -> NHDFData:
    """Convenience function to read an nhdf file."""
    return _reader.read(path, use_cache)


def get_file_info(path: pathlib.Path) -> Dict[str, Any]:
    """Convenience function to get file info."""
    return _reader.get_file_info(path)


def clear_cache(path: Optional[pathlib.Path] = None):
    """Convenience function to clear cache."""
    _reader.clear_cache(path)
