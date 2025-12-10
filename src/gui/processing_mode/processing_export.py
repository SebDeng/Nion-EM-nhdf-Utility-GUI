"""
Export functionality for Processing Mode.
Allows exporting processed data from snapshots.
"""

import json
import pathlib
import numpy as np
import uuid
import h5py
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
import tifffile

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QGroupBox, QRadioButton, QButtonGroup, QFileDialog,
    QProgressBar, QMessageBox, QSpinBox, QListWidget, QListWidgetItem,
    QScrollArea, QFrame, QWidget
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QPixmap, QImage

from .processing_engine import ProcessingState


def _find_nice_value(target: float) -> float:
    """Find a 'nice' round value close to target for scale bars."""
    if target <= 0:
        return 1.0

    exponent = np.floor(np.log10(target))
    base = 10 ** exponent

    nice_factors = [1, 2, 5, 10]
    nice_values = [f * base for f in nice_factors]

    best = nice_values[0]
    best_diff = abs(target - best)
    for v in nice_values[1:]:
        diff = abs(target - v)
        if diff < best_diff:
            best = v
            best_diff = diff

    return best


def _format_scale_value(value: float, units: str) -> str:
    """Format scale value with appropriate unit conversion."""
    if value >= 1000:
        if units == "nm":
            return f"{value/1000:.4g} µm"
        elif units == "µm" or units == "um":
            return f"{value/1000:.4g} mm"
        else:
            return f"{value:.4g} {units}"
    elif value < 0.01:
        return f"{value:.2e} {units}"
    else:
        return f"{value:.4g} {units}"


@dataclass
class ProcessingExportSettings:
    """Settings for processing export operation."""
    # Output location
    output_dir: pathlib.Path
    folder_name: str

    # Snapshots to export
    snapshot_ids: List[str] = field(default_factory=list)

    # Image settings
    export_images: bool = True
    image_format: str = "tiff"  # tiff, png, jpg, nhdf
    bit_depth: int = 16  # 8, 16, 32 (32 only for tiff)
    export_all_frames: bool = False
    apply_colormap: bool = False
    colormap_name: str = "viridis"
    include_scale_bar: bool = False

    # NHDF-specific settings
    export_nhdf: bool = False  # Export as NHDF (scientific format with calibrations)
    preserve_calibrations: bool = True  # Preserve original calibrations in NHDF

    # Video settings
    export_video: bool = False
    video_fps: int = 10
    video_quality: int = 8

    # Intensity scaling
    use_full_range: bool = True  # Use full data range
    display_min: float = 0.0
    display_max: float = 1.0

    # Metadata settings
    export_json: bool = True
    export_txt: bool = False
    export_processing_params: bool = True  # Export processing parameters

    # Scale info (from original data)
    scale_per_pixel: float = 1.0
    scale_units: str = "px"
    image_width: int = 0
    image_height: int = 0

    # Full calibration info for NHDF export (list of dicts with offset, scale, units)
    dimensional_calibrations: Optional[List[Dict]] = None
    intensity_calibration: Optional[Dict] = None
    original_metadata: Optional[Dict] = None  # Original file metadata to preserve


class ProcessingExporter:
    """Export processed data from snapshots."""

    def __init__(self, snapshots: Dict[str, ProcessingState],
                 original_file_path: Optional[pathlib.Path] = None):
        self._snapshots = snapshots
        self._original_file_path = original_file_path

    def export(self, settings: ProcessingExportSettings,
               progress_callback=None) -> pathlib.Path:
        """
        Export snapshots according to settings.

        Args:
            settings: Export settings
            progress_callback: Optional callback(current, total, message)

        Returns:
            Path to the created export folder
        """
        # Create output folder
        output_folder = settings.output_dir / settings.folder_name
        output_folder.mkdir(parents=True, exist_ok=True)

        # Get snapshots to export
        snapshots_to_export = []
        for sid in settings.snapshot_ids:
            if sid in self._snapshots:
                snapshots_to_export.append(self._snapshots[sid])

        if not snapshots_to_export:
            raise ValueError("No snapshots selected for export")

        # Calculate total steps
        total_steps = 0
        for snapshot in snapshots_to_export:
            if settings.export_images:
                if settings.export_all_frames and snapshot.processed_data is not None:
                    if len(snapshot.processed_data.shape) == 3:
                        total_steps += snapshot.processed_data.shape[0]
                    else:
                        total_steps += 1
                else:
                    total_steps += 1
            if settings.export_video:
                total_steps += 1
            if settings.export_nhdf:
                total_steps += 1
            if settings.export_json or settings.export_txt:
                total_steps += 1

        current_step = 0

        # Get original file stem for naming
        original_stem = ""
        if self._original_file_path:
            original_stem = self._original_file_path.stem

        # Export each snapshot
        for snapshot in snapshots_to_export:
            # Create subfolder for each snapshot
            snapshot_folder = output_folder / self._sanitize_name(snapshot.name)
            snapshot_folder.mkdir(parents=True, exist_ok=True)

            # Build base name: OriginalFileName_SnapshotName
            snapshot_name = self._sanitize_name(snapshot.name)
            if original_stem:
                base_name = f"{original_stem}_{snapshot_name}"
            else:
                base_name = snapshot_name

            # Export images
            if settings.export_images and snapshot.processed_data is not None:
                if settings.export_all_frames and len(snapshot.processed_data.shape) == 3:
                    num_frames = snapshot.processed_data.shape[0]
                    for i in range(num_frames):
                        frame_name = f"{base_name}_{i+1:04d}"
                        self._export_frame(
                            snapshot.processed_data[i],
                            snapshot_folder,
                            frame_name,
                            settings
                        )
                        current_step += 1
                        if progress_callback:
                            progress_callback(
                                current_step, total_steps,
                                f"Exporting {snapshot.name} frame {i+1}/{num_frames}"
                            )
                else:
                    # Export single frame
                    frame_data = snapshot.get_frame(0)
                    if frame_data is not None:
                        self._export_frame(frame_data, snapshot_folder, base_name, settings)
                    current_step += 1
                    if progress_callback:
                        progress_callback(current_step, total_steps, f"Exporting {snapshot.name}")

            # Export video
            if settings.export_video and snapshot.processed_data is not None:
                if len(snapshot.processed_data.shape) == 3:
                    if progress_callback:
                        progress_callback(current_step, total_steps, f"Exporting {snapshot.name} video...")
                    self._export_video(snapshot.processed_data, snapshot_folder, base_name, settings)
                current_step += 1
                if progress_callback:
                    progress_callback(current_step, total_steps, f"{snapshot.name} video complete")

            # Export NHDF (scientific format with calibrations)
            if settings.export_nhdf and snapshot.processed_data is not None:
                if progress_callback:
                    progress_callback(current_step, total_steps, f"Exporting {snapshot.name} as NHDF...")
                self._export_nhdf(snapshot, snapshot_folder, base_name, settings)
                current_step += 1
                if progress_callback:
                    progress_callback(current_step, total_steps, f"{snapshot.name} NHDF complete")

            # Export metadata
            if settings.export_json or settings.export_txt:
                self._export_metadata(snapshot, snapshot_folder, base_name, settings)
                current_step += 1
                if progress_callback:
                    progress_callback(current_step, total_steps, f"Exported {snapshot.name} metadata")

        return output_folder

    def _sanitize_name(self, name: str) -> str:
        """Sanitize name for use as filename."""
        # Replace spaces and special chars
        safe = name.replace(" ", "_").replace("/", "-").replace("\\", "-")
        # Remove other problematic chars
        safe = "".join(c for c in safe if c.isalnum() or c in "_-")
        return safe or "unnamed"

    def _normalize_data(self, data: np.ndarray, settings: ProcessingExportSettings) -> np.ndarray:
        """Normalize data to 0-1 range."""
        if settings.use_full_range:
            vmin, vmax = np.nanmin(data), np.nanmax(data)
        else:
            vmin, vmax = settings.display_min, settings.display_max

        if vmax == vmin:
            return np.zeros_like(data, dtype=np.float64)

        normalized = (data.astype(np.float64) - vmin) / (vmax - vmin)
        return np.clip(normalized, 0, 1)

    def _apply_colormap(self, data: np.ndarray, colormap_name: str) -> np.ndarray:
        """Apply colormap to normalized data, returns RGB array."""
        from matplotlib import colormaps as mpl_colormaps

        cmap = mpl_colormaps.get_cmap(colormap_name)
        colored = cmap(data)
        return (colored[:, :, :3] * 255).astype(np.uint8)

    def _draw_scale_bar(self, img: Image.Image, settings: ProcessingExportSettings) -> Image.Image:
        """Draw scale bar onto a PIL Image."""
        if settings.scale_per_pixel <= 0 or settings.image_width <= 0:
            return img

        scale_per_pixel = settings.scale_per_pixel
        units = settings.scale_units
        image_width = img.width
        image_height = img.height

        # Calculate bar dimensions
        target_pixels = image_width * 0.2
        target_value = target_pixels * scale_per_pixel
        nice_value = _find_nice_value(target_value)
        bar_length_pixels = int(nice_value / scale_per_pixel)
        bar_text = _format_scale_value(nice_value, units)

        # Bar positioning
        margin_x = int(image_width * 0.03)
        margin_y = int(image_height * 0.05)
        bar_thickness = max(int(image_height * 0.015), 4)

        bar_x_end = image_width - margin_x
        bar_x_start = bar_x_end - bar_length_pixels
        bar_y = image_height - margin_y - bar_thickness

        # Convert to RGB if needed
        if img.mode == 'L':
            img = img.convert('RGB')
        elif img.mode == 'I;16':
            arr = np.array(img)
            arr_8bit = (arr / 256).astype(np.uint8)
            img = Image.fromarray(arr_8bit).convert('RGB')

        draw = ImageDraw.Draw(img)

        # Draw black background
        outline_padding = max(bar_thickness // 2, 2)
        draw.rectangle(
            [bar_x_start - outline_padding, bar_y - outline_padding,
             bar_x_end + outline_padding, bar_y + bar_thickness + outline_padding],
            fill=(0, 0, 0)
        )

        # Draw white bar
        draw.rectangle(
            [bar_x_start, bar_y, bar_x_end, bar_y + bar_thickness],
            fill=(255, 255, 255)
        )

        # Draw text
        font_size = max(int(image_height * 0.035), 12)
        try:
            font = ImageFont.truetype("Arial", font_size)
        except (IOError, OSError):
            try:
                font = ImageFont.truetype("DejaVuSans", font_size)
            except (IOError, OSError):
                font = ImageFont.load_default()

        text_bbox = draw.textbbox((0, 0), bar_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        text_x = bar_x_start + (bar_length_pixels - text_width) // 2
        text_y = bar_y - text_height - outline_padding - 2

        # Text shadow
        for dx, dy in [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]:
            draw.text((text_x + dx, text_y + dy), bar_text, font=font, fill=(0, 0, 0))

        draw.text((text_x, text_y), bar_text, font=font, fill=(255, 255, 255))

        return img

    def _export_frame(self, data: np.ndarray, output_folder: pathlib.Path,
                      base_name: str, settings: ProcessingExportSettings):
        """Export a single frame as image."""
        ext_map = {"tiff": ".tiff", "png": ".png", "jpg": ".jpg"}
        ext = ext_map.get(settings.image_format, ".tiff")
        output_path = output_folder / f"{base_name}{ext}"

        if settings.image_format == "tiff":
            self._export_tiff(data, output_path, settings)
        elif settings.image_format == "png":
            self._export_png(data, output_path, settings)
        elif settings.image_format == "jpg":
            self._export_jpg(data, output_path, settings)

    def _export_tiff(self, data: np.ndarray, output_path: pathlib.Path,
                     settings: ProcessingExportSettings):
        """Export as TIFF."""
        if settings.apply_colormap:
            normalized = self._normalize_data(data, settings)
            rgb_data = self._apply_colormap(normalized, settings.colormap_name)

            if settings.include_scale_bar:
                img = Image.fromarray(rgb_data, mode='RGB')
                img = self._draw_scale_bar(img, settings)
                img.save(str(output_path), 'TIFF')
            else:
                tifffile.imwrite(str(output_path), rgb_data)
        else:
            if settings.include_scale_bar:
                normalized = self._normalize_data(data, settings)
                data_8 = (normalized * 255).astype(np.uint8)
                img = Image.fromarray(data_8, mode='L')
                img = self._draw_scale_bar(img, settings)
                img.save(str(output_path), 'TIFF')
            elif settings.bit_depth == 32:
                tifffile.imwrite(str(output_path), data.astype(np.float32))
            elif settings.bit_depth == 16:
                normalized = self._normalize_data(data, settings)
                data_16 = (normalized * 65535).astype(np.uint16)
                tifffile.imwrite(str(output_path), data_16)
            else:
                normalized = self._normalize_data(data, settings)
                data_8 = (normalized * 255).astype(np.uint8)
                tifffile.imwrite(str(output_path), data_8)

    def _export_png(self, data: np.ndarray, output_path: pathlib.Path,
                    settings: ProcessingExportSettings):
        """Export as PNG."""
        if settings.apply_colormap:
            normalized = self._normalize_data(data, settings)
            rgb_data = self._apply_colormap(normalized, settings.colormap_name)
            img = Image.fromarray(rgb_data, mode='RGB')
            if settings.include_scale_bar:
                img = self._draw_scale_bar(img, settings)
            img.save(str(output_path), 'PNG')
        else:
            normalized = self._normalize_data(data, settings)
            if settings.include_scale_bar:
                data_8 = (normalized * 255).astype(np.uint8)
                img = Image.fromarray(data_8, mode='L')
                img = self._draw_scale_bar(img, settings)
                img.save(str(output_path), 'PNG')
            elif settings.bit_depth == 16:
                data_16 = (normalized * 65535).astype(np.uint16)
                img = Image.fromarray(data_16, mode='I;16')
                img.save(str(output_path), 'PNG')
            else:
                data_8 = (normalized * 255).astype(np.uint8)
                img = Image.fromarray(data_8, mode='L')
                img.save(str(output_path), 'PNG')

    def _export_jpg(self, data: np.ndarray, output_path: pathlib.Path,
                    settings: ProcessingExportSettings):
        """Export as JPG."""
        normalized = self._normalize_data(data, settings)

        if settings.apply_colormap:
            rgb_data = self._apply_colormap(normalized, settings.colormap_name)
            img = Image.fromarray(rgb_data, mode='RGB')
        else:
            data_8 = (normalized * 255).astype(np.uint8)
            img = Image.fromarray(data_8, mode='L')

        if settings.include_scale_bar:
            img = self._draw_scale_bar(img, settings)

        if img.mode == 'L':
            img = img.convert('RGB')

        img.save(str(output_path), 'JPEG', quality=95)

    def _export_video(self, data: np.ndarray, output_folder: pathlib.Path,
                      base_name: str, settings: ProcessingExportSettings):
        """Export as MP4 video."""
        import imageio

        output_path = output_folder / f"{base_name}.mp4"

        quality_map = {
            1: 500000, 2: 1000000, 3: 2000000, 4: 3000000, 5: 5000000,
            6: 8000000, 7: 12000000, 8: 16000000, 9: 24000000, 10: 32000000,
        }
        bitrate = quality_map.get(settings.video_quality, 16000000)

        writer = imageio.get_writer(
            str(output_path),
            fps=settings.video_fps,
            codec='libx264',
            bitrate=bitrate,
            pixelformat='yuv420p',
            macro_block_size=1
        )

        try:
            num_frames = data.shape[0]
            for i in range(num_frames):
                frame_data = data[i]
                normalized = self._normalize_data(frame_data, settings)

                if settings.apply_colormap:
                    rgb_frame = self._apply_colormap(normalized, settings.colormap_name)
                else:
                    gray_8bit = (normalized * 255).astype(np.uint8)
                    rgb_frame = np.stack([gray_8bit, gray_8bit, gray_8bit], axis=-1)

                if settings.include_scale_bar:
                    img = Image.fromarray(rgb_frame, mode='RGB')
                    img = self._draw_scale_bar(img, settings)
                    rgb_frame = np.array(img)

                writer.append_data(rgb_frame)
        finally:
            writer.close()

    def _export_nhdf(self, snapshot: ProcessingState, output_folder: pathlib.Path,
                     base_name: str, settings: ProcessingExportSettings):
        """Export as NHDF (Nion HDF5 format) with calibrations preserved."""
        output_path = output_folder / f"{base_name}.nhdf"
        data = snapshot.processed_data

        # Determine data properties
        is_sequence = len(data.shape) == 3
        data_shape = list(data.shape)

        # Build dimensional calibrations
        dim_calibrations = []
        if settings.dimensional_calibrations and settings.preserve_calibrations:
            dim_calibrations = settings.dimensional_calibrations
        else:
            # Create default calibrations from scale info
            if is_sequence:
                # Sequence dimension
                dim_calibrations.append({
                    "offset": 0.0,
                    "scale": 1.0,
                    "units": ""
                })
            # Spatial dimensions
            for _ in range(2):
                dim_calibrations.append({
                    "offset": 0.0,
                    "scale": settings.scale_per_pixel if settings.scale_per_pixel > 0 else 1.0,
                    "units": settings.scale_units if settings.scale_units != "px" else ""
                })

        # Build intensity calibration
        intensity_cal = {"offset": 0.0, "scale": 1.0, "units": ""}
        if settings.intensity_calibration and settings.preserve_calibrations:
            intensity_cal = settings.intensity_calibration

        # Build properties dict (Nion format)
        properties = {
            "type": "data-item",
            "uuid": str(uuid.uuid4()),
            "created": datetime.now().isoformat(),
            "data_shape": data_shape,
            "data_dtype": str(data.dtype),
            "is_sequence": is_sequence,
            "collection_dimension_count": 0,
            "datum_dimension_count": 2,
            "intensity_calibration": intensity_cal,
            "dimensional_calibrations": dim_calibrations,
            "data_modified": datetime.now().isoformat(),
            "title": snapshot.name,
            "description": f"Processed from {self._original_file_path.name if self._original_file_path else 'unknown'}"
        }

        # Add processing parameters to metadata
        if snapshot.parameters:
            properties["processing_parameters"] = self._format_params_for_export(snapshot.parameters)

        # Preserve original metadata if available
        if settings.original_metadata and settings.preserve_calibrations:
            # Merge with processing info
            properties["original_metadata"] = settings.original_metadata

        # Write NHDF file
        with h5py.File(str(output_path), 'w') as f:
            # Create data group structure
            data_group = f.create_group("data")

            # Create dataset
            ds = data_group.create_dataset(
                "0",
                data=data.astype(np.float32),
                compression="gzip",
                compression_opts=4
            )

            # Store properties as JSON attribute
            ds.attrs['properties'] = json.dumps(properties)

            # Create index group (for Nion Swift compatibility)
            index_group = f.create_group("index")
            index_info = {
                "type": "display_item",
                "uuid": str(uuid.uuid4()),
                "created": datetime.now().isoformat()
            }
            index_group.attrs['1'] = json.dumps(index_info)

    def _export_metadata(self, snapshot: ProcessingState, output_folder: pathlib.Path,
                         base_name: str, settings: ProcessingExportSettings):
        """Export metadata for a snapshot."""
        metadata = {
            "snapshot_info": {
                "id": snapshot.id,
                "name": snapshot.name,
                "timestamp": snapshot.timestamp.isoformat(),
                "parent_id": snapshot.parent_id
            },
            "data_info": {
                "shape": list(snapshot.processed_data.shape) if snapshot.processed_data is not None else None,
                "dtype": str(snapshot.processed_data.dtype) if snapshot.processed_data is not None else None,
            },
            "export_info": {
                "exported_at": datetime.now().isoformat(),
                "original_file": str(self._original_file_path) if self._original_file_path else None
            }
        }

        if settings.export_processing_params:
            metadata["processing_parameters"] = self._format_params_for_export(snapshot.parameters)

        if settings.export_json:
            json_path = output_folder / f"{base_name}_metadata.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, default=str)

        if settings.export_txt:
            txt_path = output_folder / f"{base_name}_info.txt"
            self._write_txt_metadata(metadata, txt_path, snapshot)

    def _format_params_for_export(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Format processing parameters for human-readable export."""
        formatted = {}

        # Basic adjustments
        if params.get('brightness', 0) != 0:
            formatted['brightness'] = params['brightness']
        if params.get('contrast', 1.0) != 1.0:
            formatted['contrast'] = params['contrast']
        if params.get('gamma', 1.0) != 1.0:
            formatted['gamma'] = params['gamma']

        # Filters
        if params.get('gaussian_enabled'):
            formatted['gaussian_blur'] = {
                'enabled': True,
                'sigma': params.get('gaussian_sigma', 1.0)
            }
        if params.get('median_enabled'):
            formatted['median_filter'] = {
                'enabled': True,
                'size': params.get('median_size', 3)
            }
        if params.get('unsharp_enabled'):
            formatted['unsharp_mask'] = {
                'enabled': True,
                'amount': params.get('unsharp_amount', 0.5),
                'radius': params.get('unsharp_radius', 1.0)
            }
        if params.get('bandpass_enabled'):
            formatted['bandpass_filter'] = {
                'enabled': True,
                'large': params.get('bandpass_large', 40),
                'small': params.get('bandpass_small', 3),
                'suppress_stripes': params.get('bandpass_suppress_stripes', 'None'),
                'autoscale': params.get('bandpass_autoscale', True)
            }

        return formatted

    def _write_txt_metadata(self, metadata: dict, path: pathlib.Path,
                            snapshot: ProcessingState):
        """Write human-readable metadata."""
        lines = []
        lines.append("=" * 60)
        lines.append(f"Processing Snapshot: {snapshot.name}")
        lines.append("=" * 60)
        lines.append("")

        lines.append("SNAPSHOT INFORMATION")
        lines.append("-" * 40)
        lines.append(f"ID: {snapshot.id}")
        lines.append(f"Name: {snapshot.name}")
        lines.append(f"Created: {snapshot.timestamp.isoformat()}")
        if snapshot.parent_id:
            lines.append(f"Parent: {snapshot.parent_id}")
        lines.append("")

        if snapshot.processed_data is not None:
            lines.append("DATA INFORMATION")
            lines.append("-" * 40)
            lines.append(f"Shape: {snapshot.processed_data.shape}")
            lines.append(f"Data Type: {snapshot.processed_data.dtype}")
            lines.append("")

        if snapshot.parameters:
            lines.append("PROCESSING PARAMETERS")
            lines.append("-" * 40)
            params = snapshot.parameters

            # Basic adjustments
            if params.get('brightness', 0) != 0:
                lines.append(f"Brightness: {params['brightness']}")
            if params.get('contrast', 1.0) != 1.0:
                lines.append(f"Contrast: {params['contrast']:.2f}")
            if params.get('gamma', 1.0) != 1.0:
                lines.append(f"Gamma: {params['gamma']:.2f}")

            # Filters
            if params.get('gaussian_enabled'):
                lines.append(f"Gaussian Blur: sigma={params.get('gaussian_sigma', 1.0)}")
            if params.get('median_enabled'):
                lines.append(f"Median Filter: size={params.get('median_size', 3)}")
            if params.get('unsharp_enabled'):
                lines.append(f"Unsharp Mask: amount={params.get('unsharp_amount', 0.5)}, radius={params.get('unsharp_radius', 1.0)}")
            if params.get('bandpass_enabled'):
                lines.append(f"Bandpass: large={params.get('bandpass_large', 40)}, small={params.get('bandpass_small', 3)}")
            lines.append("")

        lines.append("=" * 60)
        lines.append(f"Exported: {datetime.now().isoformat()}")
        lines.append("=" * 60)

        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))


class ProcessingExportWorker(QThread):
    """Worker thread for export operation."""
    progress = Signal(int, int, str)
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, exporter: ProcessingExporter, settings: ProcessingExportSettings):
        super().__init__()
        self._exporter = exporter
        self._settings = settings

    def run(self):
        try:
            result_path = self._exporter.export(
                self._settings,
                progress_callback=lambda c, t, m: self.progress.emit(c, t, m)
            )
            self.finished.emit(result_path)
        except Exception as e:
            self.error.emit(str(e))


class SnapshotListItem(QFrame):
    """Widget for displaying a snapshot in the export dialog list."""

    def __init__(self, snapshot: ProcessingState, parent=None):
        super().__init__(parent)
        self.snapshot = snapshot
        self._setup_ui()

    def _setup_ui(self):
        self.setFrameStyle(QFrame.Box)
        self.setFixedHeight(60)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Checkbox
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        layout.addWidget(self.checkbox)

        # Thumbnail placeholder
        thumb_label = QLabel()
        thumb_label.setFixedSize(50, 50)
        thumb_label.setStyleSheet("background-color: #333; border: 1px solid #555;")

        # Create thumbnail from snapshot data
        if self.snapshot.processed_data is not None:
            frame = self.snapshot.get_frame(0)
            if frame is not None:
                # Normalize and create thumbnail
                vmin, vmax = np.nanmin(frame), np.nanmax(frame)
                if vmax > vmin:
                    normalized = (frame - vmin) / (vmax - vmin)
                else:
                    normalized = np.zeros_like(frame)
                img_8bit = (normalized * 255).astype(np.uint8)

                # Resize to thumbnail
                h, w = img_8bit.shape
                qimg = QImage(img_8bit.data, w, h, w, QImage.Format_Grayscale8)
                pixmap = QPixmap.fromImage(qimg)
                thumb_label.setPixmap(pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        layout.addWidget(thumb_label)

        # Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name_label = QLabel(f"<b>{self.snapshot.name}</b>")
        info_layout.addWidget(name_label)

        # Show brief parameter summary
        params_text = self._get_params_summary()
        params_label = QLabel(params_text)
        params_label.setStyleSheet("color: #888; font-size: 10px;")
        info_layout.addWidget(params_label)

        layout.addLayout(info_layout, 1)

    def _get_params_summary(self) -> str:
        """Get a brief summary of processing parameters."""
        params = self.snapshot.parameters
        if not params:
            return "No processing"

        parts = []
        if params.get('brightness', 0) != 0:
            parts.append(f"B:{params['brightness']:+.0f}")
        if params.get('contrast', 1.0) != 1.0:
            parts.append(f"C:{params['contrast']:.1f}")
        if params.get('gamma', 1.0) != 1.0:
            parts.append(f"G:{params['gamma']:.2f}")
        if params.get('gaussian_enabled'):
            parts.append("Gauss")
        if params.get('median_enabled'):
            parts.append("Med")
        if params.get('unsharp_enabled'):
            parts.append("USM")
        if params.get('bandpass_enabled'):
            parts.append("BP")

        return ", ".join(parts) if parts else "No changes"

    def is_selected(self) -> bool:
        return self.checkbox.isChecked()


class ProcessingExportDialog(QDialog):
    """Dialog for exporting processed data from snapshots."""

    def __init__(self, snapshots: Dict[str, ProcessingState],
                 original_file_path: Optional[pathlib.Path] = None,
                 scale_info: Optional[Tuple[float, str, int, int]] = None,
                 calibration_info: Optional[Dict] = None,
                 parent=None):
        super().__init__(parent)
        self._snapshots = snapshots
        self._original_file_path = original_file_path
        self._scale_info = scale_info  # (scale_per_pixel, units, width, height)
        self._calibration_info = calibration_info  # {'dimensional': [...], 'intensity': {...}, 'metadata': {...}}
        self._worker: Optional[ProcessingExportWorker] = None
        self._snapshot_items: List[SnapshotListItem] = []

        self._setup_ui()
        self._connect_signals()
        self._update_ui_state()

    def _setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Export Processed Data")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Snapshot selection
        snapshot_group = QGroupBox("Select Snapshots to Export")
        snapshot_layout = QVBoxLayout(snapshot_group)

        # Select all/none buttons
        btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        btn_layout.addWidget(select_all_btn)

        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(self._select_none)
        btn_layout.addWidget(select_none_btn)
        btn_layout.addStretch()
        snapshot_layout.addLayout(btn_layout)

        # Snapshot list in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(200)

        list_widget = QWidget()
        self._list_layout = QVBoxLayout(list_widget)
        self._list_layout.setSpacing(4)
        self._list_layout.setContentsMargins(0, 0, 0, 0)

        # Add snapshot items
        for snapshot_id, snapshot in self._snapshots.items():
            item = SnapshotListItem(snapshot)
            self._list_layout.addWidget(item)
            self._snapshot_items.append(item)

        self._list_layout.addStretch()
        scroll.setWidget(list_widget)
        snapshot_layout.addWidget(scroll)

        layout.addWidget(snapshot_group)

        # Output location
        location_group = QGroupBox("Output Location")
        location_layout = QGridLayout(location_group)

        location_layout.addWidget(QLabel("Directory:"), 0, 0)
        self._dir_edit = QLineEdit()
        if self._original_file_path:
            self._dir_edit.setText(str(self._original_file_path.parent))
        location_layout.addWidget(self._dir_edit, 0, 1)
        self._browse_btn = QPushButton("Browse...")
        self._browse_btn.setFixedWidth(80)
        location_layout.addWidget(self._browse_btn, 0, 2)

        location_layout.addWidget(QLabel("Folder Name:"), 1, 0)
        self._folder_edit = QLineEdit()
        if self._original_file_path:
            self._folder_edit.setText(f"{self._original_file_path.stem}_processed")
        else:
            self._folder_edit.setText("processed_export")
        location_layout.addWidget(self._folder_edit, 1, 1, 1, 2)

        layout.addWidget(location_group)

        # Image options
        image_group = QGroupBox("Image Export")
        image_layout = QGridLayout(image_group)

        self._export_images_check = QCheckBox("Export image(s)")
        self._export_images_check.setChecked(True)
        image_layout.addWidget(self._export_images_check, 0, 0, 1, 3)

        # Format
        self._format_label = QLabel("Format:")
        image_layout.addWidget(self._format_label, 1, 0)
        format_layout = QHBoxLayout()
        self._format_group = QButtonGroup(self)
        self._tiff_radio = QRadioButton("TIFF")
        self._png_radio = QRadioButton("PNG")
        self._jpg_radio = QRadioButton("JPG")
        self._tiff_radio.setChecked(True)
        self._format_group.addButton(self._tiff_radio, 0)
        self._format_group.addButton(self._png_radio, 1)
        self._format_group.addButton(self._jpg_radio, 2)
        format_layout.addWidget(self._tiff_radio)
        format_layout.addWidget(self._png_radio)
        format_layout.addWidget(self._jpg_radio)
        format_layout.addStretch()
        image_layout.addLayout(format_layout, 1, 1, 1, 2)

        # Bit depth
        self._bit_depth_label = QLabel("Bit Depth:")
        image_layout.addWidget(self._bit_depth_label, 2, 0)
        self._bit_depth_combo = QComboBox()
        self._bit_depth_combo.addItems(["8-bit", "16-bit", "32-bit (TIFF only)"])
        self._bit_depth_combo.setCurrentIndex(1)
        image_layout.addWidget(self._bit_depth_combo, 2, 1, 1, 2)

        # Frame selection
        self._frames_label = QLabel("Frames:")
        image_layout.addWidget(self._frames_label, 3, 0)
        frame_layout = QHBoxLayout()
        self._frame_group = QButtonGroup(self)
        self._current_frame_radio = QRadioButton("First frame only")
        self._all_frames_radio = QRadioButton("All frames")
        self._current_frame_radio.setChecked(True)
        self._frame_group.addButton(self._current_frame_radio, 0)
        self._frame_group.addButton(self._all_frames_radio, 1)
        frame_layout.addWidget(self._current_frame_radio)
        frame_layout.addWidget(self._all_frames_radio)
        frame_layout.addStretch()
        image_layout.addLayout(frame_layout, 3, 1, 1, 2)

        # Colormap
        self._colormap_check = QCheckBox("Apply colormap")
        self._colormap_check.setChecked(False)
        image_layout.addWidget(self._colormap_check, 4, 0, 1, 2)

        self._colormap_combo = QComboBox()
        self._colormap_combo.addItems([
            'viridis', 'plasma', 'inferno', 'magma', 'cividis',
            'Greys', 'gray', 'hot', 'cool', 'jet', 'turbo'
        ])
        self._colormap_combo.setEnabled(False)
        image_layout.addWidget(self._colormap_combo, 4, 2)

        # Scale bar
        self._scale_bar_check = QCheckBox("Include scale bar")
        self._scale_bar_check.setChecked(False)
        self._scale_bar_check.setEnabled(self._scale_info is not None)
        image_layout.addWidget(self._scale_bar_check, 5, 0, 1, 3)

        layout.addWidget(image_group)

        # Video export
        video_group = QGroupBox("Video Export")
        video_layout = QGridLayout(video_group)

        self._video_check = QCheckBox("Export as MP4 video (multi-frame snapshots)")
        self._video_check.setChecked(False)
        video_layout.addWidget(self._video_check, 0, 0, 1, 3)

        video_layout.addWidget(QLabel("Frame Rate:"), 1, 0)
        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(1, 60)
        self._fps_spin.setValue(10)
        self._fps_spin.setSuffix(" fps")
        self._fps_spin.setEnabled(False)
        video_layout.addWidget(self._fps_spin, 1, 1)

        video_layout.addWidget(QLabel("Quality:"), 2, 0)
        self._quality_spin = QSpinBox()
        self._quality_spin.setRange(1, 10)
        self._quality_spin.setValue(8)
        self._quality_spin.setEnabled(False)
        video_layout.addWidget(self._quality_spin, 2, 1)

        layout.addWidget(video_group)

        # Scientific format export (NHDF)
        scientific_group = QGroupBox("Scientific Format Export")
        scientific_layout = QVBoxLayout(scientific_group)

        self._nhdf_check = QCheckBox("Export as NHDF (Nion HDF5 format)")
        self._nhdf_check.setChecked(False)
        self._nhdf_check.setToolTip("Exports processed data in NHDF format with calibrations preserved.\nCan be loaded back into this viewer or Nion Swift.")
        scientific_layout.addWidget(self._nhdf_check)

        self._preserve_calibrations_check = QCheckBox("Preserve original calibrations")
        self._preserve_calibrations_check.setChecked(True)
        self._preserve_calibrations_check.setEnabled(False)
        self._preserve_calibrations_check.setToolTip("Keep the original scale and unit calibrations from the source file.")
        scientific_layout.addWidget(self._preserve_calibrations_check)

        layout.addWidget(scientific_group)

        # Metadata options
        meta_group = QGroupBox("Metadata Export")
        meta_layout = QVBoxLayout(meta_group)

        self._json_check = QCheckBox("JSON (full metadata)")
        self._json_check.setChecked(True)
        meta_layout.addWidget(self._json_check)

        self._txt_check = QCheckBox("TXT (human-readable summary)")
        self._txt_check.setChecked(False)
        meta_layout.addWidget(self._txt_check)

        self._params_check = QCheckBox("Include processing parameters")
        self._params_check.setChecked(True)
        meta_layout.addWidget(self._params_check)

        layout.addWidget(meta_group)

        # Progress
        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._progress_label = QLabel("")
        self._progress_label.setVisible(False)
        self._progress_label.setStyleSheet("color: #888;")
        layout.addWidget(self._progress_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(80)
        button_layout.addWidget(self._cancel_btn)

        self._export_btn = QPushButton("Export")
        self._export_btn.setFixedWidth(80)
        self._export_btn.setDefault(True)
        button_layout.addWidget(self._export_btn)

        layout.addLayout(button_layout)

    def _connect_signals(self):
        """Connect UI signals."""
        self._browse_btn.clicked.connect(self._on_browse)
        self._cancel_btn.clicked.connect(self.reject)
        self._export_btn.clicked.connect(self._on_export)

        self._colormap_check.toggled.connect(self._colormap_combo.setEnabled)
        self._format_group.buttonClicked.connect(self._update_ui_state)
        self._export_images_check.toggled.connect(self._on_export_images_toggled)
        self._video_check.toggled.connect(self._on_video_check_toggled)
        self._nhdf_check.toggled.connect(self._preserve_calibrations_check.setEnabled)

    def _update_ui_state(self):
        """Update UI based on selections."""
        format_id = self._format_group.checkedId()

        if format_id == 2:  # JPG
            self._bit_depth_combo.setCurrentIndex(0)
            self._bit_depth_combo.setEnabled(False)
        elif format_id == 1:  # PNG
            if self._bit_depth_combo.currentIndex() == 2:
                self._bit_depth_combo.setCurrentIndex(1)
            self._bit_depth_combo.setEnabled(True)
        else:  # TIFF
            self._bit_depth_combo.setEnabled(True)

    def _on_export_images_toggled(self, checked: bool):
        """Handle export images toggle."""
        self._format_label.setEnabled(checked)
        self._tiff_radio.setEnabled(checked)
        self._png_radio.setEnabled(checked)
        self._jpg_radio.setEnabled(checked)
        self._bit_depth_label.setEnabled(checked)
        self._bit_depth_combo.setEnabled(checked)
        self._frames_label.setEnabled(checked)
        self._current_frame_radio.setEnabled(checked)
        self._all_frames_radio.setEnabled(checked)

    def _on_video_check_toggled(self, checked: bool):
        """Handle video checkbox toggle."""
        self._fps_spin.setEnabled(checked)
        self._quality_spin.setEnabled(checked)

    def _select_all(self):
        """Select all snapshots."""
        for item in self._snapshot_items:
            item.checkbox.setChecked(True)

    def _select_none(self):
        """Deselect all snapshots."""
        for item in self._snapshot_items:
            item.checkbox.setChecked(False)

    def _on_browse(self):
        """Browse for output directory."""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", self._dir_edit.text()
        )
        if dir_path:
            self._dir_edit.setText(dir_path)

    def _get_settings(self) -> ProcessingExportSettings:
        """Build settings from current UI state."""
        # Get selected snapshots
        selected_ids = []
        for item in self._snapshot_items:
            if item.is_selected():
                selected_ids.append(item.snapshot.id)

        # Get format
        format_id = self._format_group.checkedId()
        format_map = {0: "tiff", 1: "png", 2: "jpg"}
        image_format = format_map.get(format_id, "tiff")

        # Get bit depth
        bit_depth_map = {0: 8, 1: 16, 2: 32}
        bit_depth = bit_depth_map.get(self._bit_depth_combo.currentIndex(), 16)

        # Scale info
        scale_per_pixel = 1.0
        scale_units = "px"
        image_width = 0
        image_height = 0
        if self._scale_info:
            scale_per_pixel, scale_units, image_width, image_height = self._scale_info

        return ProcessingExportSettings(
            output_dir=pathlib.Path(self._dir_edit.text()),
            folder_name=self._folder_edit.text() or "processed_export",
            snapshot_ids=selected_ids,
            export_images=self._export_images_check.isChecked(),
            image_format=image_format,
            bit_depth=bit_depth,
            export_all_frames=self._all_frames_radio.isChecked(),
            apply_colormap=self._colormap_check.isChecked(),
            colormap_name=self._colormap_combo.currentText(),
            include_scale_bar=self._scale_bar_check.isChecked(),
            export_nhdf=self._nhdf_check.isChecked(),
            preserve_calibrations=self._preserve_calibrations_check.isChecked(),
            export_video=self._video_check.isChecked(),
            video_fps=self._fps_spin.value(),
            video_quality=self._quality_spin.value(),
            export_json=self._json_check.isChecked(),
            export_txt=self._txt_check.isChecked(),
            export_processing_params=self._params_check.isChecked(),
            scale_per_pixel=scale_per_pixel,
            scale_units=scale_units,
            image_width=image_width,
            image_height=image_height,
            dimensional_calibrations=self._calibration_info.get('dimensional') if hasattr(self, '_calibration_info') and self._calibration_info else None,
            intensity_calibration=self._calibration_info.get('intensity') if hasattr(self, '_calibration_info') and self._calibration_info else None,
            original_metadata=self._calibration_info.get('metadata') if hasattr(self, '_calibration_info') and self._calibration_info else None
        )

    def _on_export(self):
        """Start export."""
        # Validate
        output_dir = pathlib.Path(self._dir_edit.text())
        if not output_dir.exists():
            QMessageBox.warning(self, "Invalid Directory", "Output directory does not exist.")
            return

        # Check selected snapshots
        selected = [item for item in self._snapshot_items if item.is_selected()]
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select at least one snapshot to export.")
            return

        folder_name = self._folder_edit.text().strip()
        if not folder_name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a folder name.")
            return

        # Check if exists
        output_folder = output_dir / folder_name
        if output_folder.exists():
            result = QMessageBox.question(
                self, "Folder Exists",
                f"The folder '{folder_name}' already exists. Continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if result != QMessageBox.Yes:
                return

        # Start export
        self._set_ui_enabled(False)
        self._progress_bar.setVisible(True)
        self._progress_label.setVisible(True)
        self._progress_bar.setValue(0)
        self._progress_label.setText("Starting export...")

        settings = self._get_settings()
        exporter = ProcessingExporter(self._snapshots, self._original_file_path)

        self._worker = ProcessingExportWorker(exporter, settings)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _set_ui_enabled(self, enabled: bool):
        """Enable/disable UI."""
        for item in self._snapshot_items:
            item.checkbox.setEnabled(enabled)
        self._dir_edit.setEnabled(enabled)
        self._browse_btn.setEnabled(enabled)
        self._folder_edit.setEnabled(enabled)
        self._export_images_check.setEnabled(enabled)
        self._tiff_radio.setEnabled(enabled)
        self._png_radio.setEnabled(enabled)
        self._jpg_radio.setEnabled(enabled)
        self._bit_depth_combo.setEnabled(enabled)
        self._current_frame_radio.setEnabled(enabled)
        self._all_frames_radio.setEnabled(enabled)
        self._colormap_check.setEnabled(enabled)
        self._colormap_combo.setEnabled(enabled and self._colormap_check.isChecked())
        self._scale_bar_check.setEnabled(enabled and self._scale_info is not None)
        self._video_check.setEnabled(enabled)
        self._fps_spin.setEnabled(enabled and self._video_check.isChecked())
        self._quality_spin.setEnabled(enabled and self._video_check.isChecked())
        self._nhdf_check.setEnabled(enabled)
        self._preserve_calibrations_check.setEnabled(enabled and self._nhdf_check.isChecked())
        self._json_check.setEnabled(enabled)
        self._txt_check.setEnabled(enabled)
        self._params_check.setEnabled(enabled)
        self._export_btn.setEnabled(enabled)

    def _on_progress(self, current: int, total: int, message: str):
        """Handle progress update."""
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._progress_label.setText(message)

    def _on_finished(self, result_path):
        """Handle export completion."""
        self._worker = None
        self._set_ui_enabled(True)
        self._progress_bar.setVisible(False)
        self._progress_label.setVisible(False)

        QMessageBox.information(
            self, "Export Complete",
            f"Data exported successfully to:\n{result_path}"
        )
        self.accept()

    def _on_error(self, error_msg: str):
        """Handle export error."""
        self._worker = None
        self._set_ui_enabled(True)
        self._progress_bar.setVisible(False)
        self._progress_label.setVisible(False)

        QMessageBox.critical(self, "Export Failed", f"Export failed:\n{error_msg}")

    def reject(self):
        """Handle cancel."""
        if self._worker and self._worker.isRunning():
            pass  # Could implement cancellation
        super().reject()
