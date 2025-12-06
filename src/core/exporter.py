"""
Export module for nhdf data.
Supports exporting images (TIFF, PNG, JPG) and metadata (JSON, TXT, CSV).
"""

import json
import pathlib
import numpy as np
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
import tifffile

from src.core.nhdf_reader import NHDFData


def _find_nice_value(target: float) -> float:
    """Find a 'nice' round value close to target for scale bars."""
    if target <= 0:
        return 1.0

    # Find the order of magnitude
    exponent = np.floor(np.log10(target))
    base = 10 ** exponent

    # Nice values: 1, 2, 5, 10
    nice_factors = [1, 2, 5, 10]
    nice_values = [f * base for f in nice_factors]

    # Find closest nice value
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
        # Convert to larger unit if possible
        if units == "nm":
            return f"{value/1000:.4g} \u00b5m"
        elif units == "\u00b5m" or units == "um":
            return f"{value/1000:.4g} mm"
        else:
            return f"{value:.4g} {units}"
    elif value < 0.01:
        return f"{value:.2e} {units}"
    else:
        return f"{value:.4g} {units}"


@dataclass
class ExportSettings:
    """Settings for export operation."""
    # Output location
    output_dir: pathlib.Path
    folder_name: str

    # Image settings
    export_images: bool = True
    image_format: str = "tiff"  # tiff, png, jpg
    bit_depth: int = 16  # 8, 16, 32 (32 only for tiff)
    export_all_frames: bool = False
    apply_colormap: bool = False
    colormap_name: str = "viridis"
    include_scale_bar: bool = False

    # Video settings
    export_video: bool = False
    video_fps: int = 10
    video_quality: int = 8  # 1-10 scale, higher = better quality

    # Intensity scaling
    use_display_range: bool = True
    display_min: float = 0.0
    display_max: float = 1.0

    # Metadata settings
    export_json: bool = True
    export_txt: bool = False
    export_csv: bool = False


class Exporter:
    """Export nhdf data to various formats."""

    def __init__(self, data: NHDFData):
        self._data = data

    def export(self, settings: ExportSettings, progress_callback=None) -> pathlib.Path:
        """
        Export data according to settings.

        Args:
            settings: Export settings
            progress_callback: Optional callback(current, total, message) for progress

        Returns:
            Path to the created export folder
        """
        # Create output folder
        output_folder = settings.output_dir / settings.folder_name
        output_folder.mkdir(parents=True, exist_ok=True)

        base_name = self._data.file_path.stem

        # Calculate total steps for progress
        total_steps = 0
        if settings.export_images:
            if settings.export_all_frames:
                total_steps += self._data.num_frames
            else:
                total_steps += 1
        if settings.export_video and self._data.num_frames > 1:
            total_steps += 1  # Video export is one step (progress handled internally)
        if settings.export_json:
            total_steps += 1
        if settings.export_txt:
            total_steps += 1
        if settings.export_csv:
            total_steps += 1

        current_step = 0

        # Export images
        if settings.export_images:
            if settings.export_all_frames and self._data.num_frames > 1:
                for i in range(self._data.num_frames):
                    frame_name = f"{base_name}_{i+1:04d}"
                    self._export_frame(i, output_folder, frame_name, settings)
                    current_step += 1
                    if progress_callback:
                        progress_callback(current_step, total_steps, f"Exporting frame {i+1}/{self._data.num_frames}")
            else:
                # Export current/first frame
                self._export_frame(0, output_folder, base_name, settings)
                current_step += 1
                if progress_callback:
                    progress_callback(current_step, total_steps, "Exporting image")

        # Export video
        if settings.export_video and self._data.num_frames > 1:
            if progress_callback:
                progress_callback(current_step, total_steps, "Exporting video...")
            self._export_video(output_folder, base_name, settings, progress_callback)
            current_step += 1
            if progress_callback:
                progress_callback(current_step, total_steps, "Video export complete")

        # Export metadata
        if settings.export_json:
            self._export_json(output_folder, base_name)
            current_step += 1
            if progress_callback:
                progress_callback(current_step, total_steps, "Exporting JSON metadata")

        if settings.export_txt:
            self._export_txt(output_folder, base_name)
            current_step += 1
            if progress_callback:
                progress_callback(current_step, total_steps, "Exporting TXT summary")

        if settings.export_csv:
            self._export_csv(output_folder, base_name)
            current_step += 1
            if progress_callback:
                progress_callback(current_step, total_steps, "Exporting CSV metadata")

        return output_folder

    def _export_frame(self, frame_index: int, output_folder: pathlib.Path,
                      base_name: str, settings: ExportSettings):
        """Export a single frame as image."""
        frame_data = self._data.get_frame(frame_index)

        # Get file extension
        ext_map = {"tiff": ".tiff", "png": ".png", "jpg": ".jpg"}
        ext = ext_map.get(settings.image_format, ".tiff")
        output_path = output_folder / f"{base_name}{ext}"

        if settings.image_format == "tiff":
            self._export_tiff(frame_data, output_path, settings)
        elif settings.image_format == "png":
            self._export_png(frame_data, output_path, settings)
        elif settings.image_format == "jpg":
            self._export_jpg(frame_data, output_path, settings)

    def _normalize_data(self, data: np.ndarray, settings: ExportSettings) -> np.ndarray:
        """Normalize data to 0-1 range based on settings."""
        if settings.use_display_range:
            vmin, vmax = settings.display_min, settings.display_max
        else:
            vmin, vmax = np.nanmin(data), np.nanmax(data)

        if vmax == vmin:
            return np.zeros_like(data, dtype=np.float64)

        normalized = (data.astype(np.float64) - vmin) / (vmax - vmin)
        return np.clip(normalized, 0, 1)

    def _apply_colormap(self, data: np.ndarray, colormap_name: str) -> np.ndarray:
        """Apply colormap to normalized data, returns RGB array."""
        from matplotlib import colormaps as mpl_colormaps

        cmap = mpl_colormaps.get_cmap(colormap_name)
        colored = cmap(data)  # Returns RGBA float array
        return (colored[:, :, :3] * 255).astype(np.uint8)  # RGB 8-bit

    def _get_scale_info(self) -> Optional[Tuple[float, str, int, int]]:
        """Get scale information for the current data.

        Returns:
            Tuple of (scale_per_pixel, units, width, height) or None if not available.
        """
        if not self._data.is_2d_image:
            return None

        fov_info = self._data.actual_fov
        if fov_info is None:
            return None

        fov_y, fov_x, units = fov_info
        ny, nx = self._data.frame_shape

        scale_per_pixel = fov_x / nx if nx > 0 else 1.0
        return (scale_per_pixel, units, nx, ny)

    def _draw_scale_bar(self, img: Image.Image) -> Image.Image:
        """Draw scale bar onto a PIL Image.

        Args:
            img: PIL Image (RGB or L mode)

        Returns:
            Image with scale bar burned in.
        """
        scale_info = self._get_scale_info()
        if scale_info is None:
            return img

        scale_per_pixel, units, image_width, image_height = scale_info

        if scale_per_pixel == 0 or image_width == 0:
            return img

        # Calculate bar dimensions
        # Target bar length: ~20% of image width
        target_pixels = image_width * 0.2
        target_value = target_pixels * scale_per_pixel
        nice_value = _find_nice_value(target_value)
        bar_length_pixels = int(nice_value / scale_per_pixel)
        bar_text = _format_scale_value(nice_value, units)

        # Bar positioning (bottom-right corner)
        margin_x = int(image_width * 0.03)  # 3% margin from right
        margin_y = int(image_height * 0.05)  # 5% margin from bottom
        bar_thickness = max(int(image_height * 0.015), 4)  # 1.5% of height, min 4 pixels

        bar_x_end = image_width - margin_x
        bar_x_start = bar_x_end - bar_length_pixels
        bar_y = image_height - margin_y - bar_thickness

        # Convert to RGB if grayscale for colored scale bar
        if img.mode == 'L':
            img = img.convert('RGB')
        elif img.mode == 'I;16':
            # 16-bit grayscale - convert to 8-bit RGB
            arr = np.array(img)
            arr_8bit = (arr / 256).astype(np.uint8)
            img = Image.fromarray(arr_8bit).convert('RGB')

        draw = ImageDraw.Draw(img)

        # Draw black background/outline
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

        # Draw text label
        font_size = max(int(image_height * 0.035), 12)  # 3.5% of height, min 12
        try:
            # Try to load a good font
            font = ImageFont.truetype("Arial", font_size)
        except (IOError, OSError):
            try:
                font = ImageFont.truetype("DejaVuSans", font_size)
            except (IOError, OSError):
                # Fall back to default font
                font = ImageFont.load_default()

        # Get text bounding box
        text_bbox = draw.textbbox((0, 0), bar_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        # Center text above the bar
        text_x = bar_x_start + (bar_length_pixels - text_width) // 2
        text_y = bar_y - text_height - outline_padding - 2

        # Draw text shadow (black outline)
        for dx, dy in [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]:
            draw.text((text_x + dx, text_y + dy), bar_text, font=font, fill=(0, 0, 0))

        # Draw text (white)
        draw.text((text_x, text_y), bar_text, font=font, fill=(255, 255, 255))

        return img

    def _export_tiff(self, data: np.ndarray, output_path: pathlib.Path,
                     settings: ExportSettings):
        """Export as TIFF with specified bit depth."""
        if settings.apply_colormap:
            # Colormap output is always 8-bit RGB
            normalized = self._normalize_data(data, settings)
            rgb_data = self._apply_colormap(normalized, settings.colormap_name)

            if settings.include_scale_bar:
                img = Image.fromarray(rgb_data, mode='RGB')
                img = self._draw_scale_bar(img)
                img.save(str(output_path), 'TIFF')
            else:
                tifffile.imwrite(str(output_path), rgb_data)
        else:
            # Grayscale with specified bit depth
            if settings.include_scale_bar:
                # Scale bar requires conversion to RGB
                normalized = self._normalize_data(data, settings)
                data_8 = (normalized * 255).astype(np.uint8)
                img = Image.fromarray(data_8, mode='L')
                img = self._draw_scale_bar(img)  # This converts to RGB
                img.save(str(output_path), 'TIFF')
            elif settings.bit_depth == 32:
                # 32-bit float
                tifffile.imwrite(str(output_path), data.astype(np.float32))
            elif settings.bit_depth == 16:
                # 16-bit unsigned
                normalized = self._normalize_data(data, settings)
                data_16 = (normalized * 65535).astype(np.uint16)
                tifffile.imwrite(str(output_path), data_16)
            else:
                # 8-bit unsigned
                normalized = self._normalize_data(data, settings)
                data_8 = (normalized * 255).astype(np.uint8)
                tifffile.imwrite(str(output_path), data_8)

    def _export_png(self, data: np.ndarray, output_path: pathlib.Path,
                    settings: ExportSettings):
        """Export as PNG (8-bit or 16-bit)."""
        if settings.apply_colormap:
            normalized = self._normalize_data(data, settings)
            rgb_data = self._apply_colormap(normalized, settings.colormap_name)
            img = Image.fromarray(rgb_data, mode='RGB')
            if settings.include_scale_bar:
                img = self._draw_scale_bar(img)
            img.save(str(output_path), 'PNG')
        else:
            normalized = self._normalize_data(data, settings)
            if settings.include_scale_bar:
                # Scale bar requires conversion to RGB
                data_8 = (normalized * 255).astype(np.uint8)
                img = Image.fromarray(data_8, mode='L')
                img = self._draw_scale_bar(img)  # This converts to RGB
                img.save(str(output_path), 'PNG')
            elif settings.bit_depth == 16:
                # 16-bit grayscale PNG
                data_16 = (normalized * 65535).astype(np.uint16)
                img = Image.fromarray(data_16, mode='I;16')
                img.save(str(output_path), 'PNG')
            else:
                # 8-bit grayscale
                data_8 = (normalized * 255).astype(np.uint8)
                img = Image.fromarray(data_8, mode='L')
                img.save(str(output_path), 'PNG')

    def _export_jpg(self, data: np.ndarray, output_path: pathlib.Path,
                    settings: ExportSettings):
        """Export as JPG (always 8-bit)."""
        normalized = self._normalize_data(data, settings)

        if settings.apply_colormap:
            rgb_data = self._apply_colormap(normalized, settings.colormap_name)
            img = Image.fromarray(rgb_data, mode='RGB')
        else:
            data_8 = (normalized * 255).astype(np.uint8)
            img = Image.fromarray(data_8, mode='L')

        if settings.include_scale_bar:
            img = self._draw_scale_bar(img)

        # JPG requires RGB mode (convert if grayscale with no scale bar)
        if img.mode == 'L':
            img = img.convert('RGB')

        img.save(str(output_path), 'JPEG', quality=95)

    def _export_video(self, output_folder: pathlib.Path, base_name: str,
                      settings: ExportSettings, progress_callback=None):
        """Export all frames as MP4 video."""
        import imageio

        output_path = output_folder / f"{base_name}.mp4"

        # Calculate quality setting for imageio
        # video_quality is 1-10, we need to map to appropriate bitrate/quality
        # Higher quality = higher bitrate
        quality_map = {
            1: 500000,    # 500 kbps
            2: 1000000,   # 1 Mbps
            3: 2000000,   # 2 Mbps
            4: 3000000,   # 3 Mbps
            5: 5000000,   # 5 Mbps
            6: 8000000,   # 8 Mbps
            7: 12000000,  # 12 Mbps
            8: 16000000,  # 16 Mbps
            9: 24000000,  # 24 Mbps
            10: 32000000, # 32 Mbps
        }
        bitrate = quality_map.get(settings.video_quality, 16000000)

        # Create video writer
        writer = imageio.get_writer(
            str(output_path),
            fps=settings.video_fps,
            codec='libx264',
            bitrate=bitrate,
            pixelformat='yuv420p',  # For maximum compatibility
            macro_block_size=1  # Allows any frame size
        )

        try:
            for i in range(self._data.num_frames):
                frame_data = self._data.get_frame(i)

                # Normalize data
                normalized = self._normalize_data(frame_data, settings)

                # Apply colormap or convert to RGB
                if settings.apply_colormap:
                    rgb_frame = self._apply_colormap(normalized, settings.colormap_name)
                else:
                    # Grayscale to RGB
                    gray_8bit = (normalized * 255).astype(np.uint8)
                    rgb_frame = np.stack([gray_8bit, gray_8bit, gray_8bit], axis=-1)

                # Apply scale bar if enabled
                if settings.include_scale_bar:
                    img = Image.fromarray(rgb_frame, mode='RGB')
                    img = self._draw_scale_bar(img)
                    rgb_frame = np.array(img)

                # Write frame to video
                writer.append_data(rgb_frame)

        finally:
            writer.close()

    def _export_json(self, output_folder: pathlib.Path, base_name: str):
        """Export full metadata as JSON."""
        output_path = output_folder / f"{base_name}_metadata.json"

        metadata = self._build_metadata_dict()

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, default=str)

    def _export_txt(self, output_folder: pathlib.Path, base_name: str):
        """Export human-readable metadata summary as TXT."""
        output_path = output_folder / f"{base_name}_info.txt"

        lines = []
        lines.append("=" * 60)
        lines.append(f"nhdf File Information")
        lines.append("=" * 60)
        lines.append("")

        # File info
        lines.append("FILE INFORMATION")
        lines.append("-" * 40)
        lines.append(f"Name: {self._data.file_path.name}")
        lines.append(f"Path: {self._data.file_path.parent}")
        lines.append("")

        # Data info
        lines.append("DATA INFORMATION")
        lines.append("-" * 40)
        lines.append(f"Shape: {self._data.shape}")
        lines.append(f"Data Type: {self._data.dtype}")
        lines.append(f"Dimensions: {self._data.ndim}")
        lines.append(f"Structure: {self._data.data_descriptor.describe()}")
        if self._data.num_frames > 1:
            lines.append(f"Number of Frames: {self._data.num_frames}")
            lines.append(f"Frame Shape: {self._data.frame_shape}")
        lines.append("")

        # Scan info
        lines.append("SCAN INFORMATION")
        lines.append("-" * 40)
        lines.append(f"Is Subscan: {'Yes' if self._data.is_subscan else 'No'}")
        fov = self._data.actual_fov
        if fov:
            fov_y, fov_x, units = fov
            if fov_y == fov_x:
                lines.append(f"Actual FOV: {fov_x:.4g} {units}")
            else:
                lines.append(f"Actual FOV: {fov_x:.4g} x {fov_y:.4g} {units}")
        context_fov = self._data.context_fov_nm
        if context_fov is not None:
            lines.append(f"Context FOV: {context_fov:.4g} nm")
        center = self._data.scan_center_nm
        if center:
            lines.append(f"Scan Center: ({center[0]:.4g}, {center[1]:.4g}) nm")
        rotation = self._data.scan_rotation_deg
        if rotation is not None:
            lines.append(f"Rotation: {rotation:.2f} deg")
        lines.append("")

        # Hardware info
        lines.append("HARDWARE INFORMATION")
        lines.append("-" * 40)
        channel = self._data.channel_name
        if channel:
            lines.append(f"Channel: {channel}")
        hw_source = self._data.hardware_source
        if hw_source.get("hardware_source_name"):
            lines.append(f"Source: {hw_source.get('hardware_source_name')}")
        pixel_time = self._data.pixel_time_us
        if pixel_time is not None:
            lines.append(f"Pixel Time: {pixel_time:.4g} us")
        exposure = self._data.exposure_time
        if exposure is not None:
            lines.append(f"Exposure: {exposure:.4g} s")
        lines.append("")

        # Timestamp
        if self._data.timestamp:
            lines.append("TIMESTAMP")
            lines.append("-" * 40)
            lines.append(f"Created: {self._data.timestamp.isoformat()}")
            if self._data.timezone:
                lines.append(f"Timezone: {self._data.timezone}")
            lines.append("")

        # Calibrations
        lines.append("CALIBRATIONS")
        lines.append("-" * 40)
        int_cal = self._data.intensity_calibration
        lines.append(f"Intensity: scale={int_cal.scale}, offset={int_cal.offset}, units={int_cal.units or '(none)'}")
        for i, dim_cal in enumerate(self._data.dimensional_calibrations):
            lines.append(f"Dimension {i}: scale={dim_cal.scale}, offset={dim_cal.offset}, units={dim_cal.units or '(none)'}")
        lines.append("")

        lines.append("=" * 60)
        lines.append(f"Exported: {datetime.now().isoformat()}")
        lines.append("=" * 60)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

    def _export_csv(self, output_folder: pathlib.Path, base_name: str):
        """Export metadata as CSV (key-value pairs)."""
        output_path = output_folder / f"{base_name}_metadata.csv"

        rows = []
        rows.append(["Property", "Value"])

        # File info
        rows.append(["File Name", self._data.file_path.name])
        rows.append(["File Path", str(self._data.file_path.parent)])

        # Data info
        rows.append(["Shape", str(self._data.shape)])
        rows.append(["Data Type", str(self._data.dtype)])
        rows.append(["Dimensions", str(self._data.ndim)])
        rows.append(["Structure", self._data.data_descriptor.describe()])
        rows.append(["Number of Frames", str(self._data.num_frames)])
        rows.append(["Frame Shape", str(self._data.frame_shape)])

        # Scan info
        rows.append(["Is Subscan", "Yes" if self._data.is_subscan else "No"])
        fov = self._data.actual_fov
        if fov:
            fov_y, fov_x, units = fov
            rows.append(["Actual FOV", f"{fov_x:.4g} x {fov_y:.4g} {units}"])
        context_fov = self._data.context_fov_nm
        if context_fov is not None:
            rows.append(["Context FOV (nm)", str(context_fov)])
        center = self._data.scan_center_nm
        if center:
            rows.append(["Scan Center X (nm)", str(center[0])])
            rows.append(["Scan Center Y (nm)", str(center[1])])
        rotation = self._data.scan_rotation_deg
        if rotation is not None:
            rows.append(["Rotation (deg)", str(rotation)])

        # Hardware info
        channel = self._data.channel_name
        if channel:
            rows.append(["Channel", channel])
        hw_source = self._data.hardware_source
        if hw_source.get("hardware_source_name"):
            rows.append(["Hardware Source", hw_source.get("hardware_source_name")])
        pixel_time = self._data.pixel_time_us
        if pixel_time is not None:
            rows.append(["Pixel Time (us)", str(pixel_time)])
        exposure = self._data.exposure_time
        if exposure is not None:
            rows.append(["Exposure (s)", str(exposure)])

        # Timestamp
        if self._data.timestamp:
            rows.append(["Created", self._data.timestamp.isoformat()])
            if self._data.timezone:
                rows.append(["Timezone", self._data.timezone])

        # Calibrations
        int_cal = self._data.intensity_calibration
        rows.append(["Intensity Scale", str(int_cal.scale)])
        rows.append(["Intensity Offset", str(int_cal.offset)])
        rows.append(["Intensity Units", int_cal.units or ""])

        for i, dim_cal in enumerate(self._data.dimensional_calibrations):
            rows.append([f"Dimension {i} Scale", str(dim_cal.scale)])
            rows.append([f"Dimension {i} Offset", str(dim_cal.offset)])
            rows.append([f"Dimension {i} Units", dim_cal.units or ""])

        # Write CSV
        import csv
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(rows)

    def _build_metadata_dict(self) -> Dict[str, Any]:
        """Build a comprehensive metadata dictionary for JSON export."""
        return {
            "file_info": {
                "name": self._data.file_path.name,
                "path": str(self._data.file_path.parent),
                "full_path": str(self._data.file_path)
            },
            "data_info": {
                "shape": list(self._data.shape),
                "dtype": str(self._data.dtype),
                "ndim": self._data.ndim,
                "structure": self._data.data_descriptor.describe(),
                "is_sequence": self._data.data_descriptor.is_sequence,
                "collection_dimension_count": self._data.data_descriptor.collection_dimension_count,
                "datum_dimension_count": self._data.data_descriptor.datum_dimension_count,
                "num_frames": self._data.num_frames,
                "frame_shape": list(self._data.frame_shape)
            },
            "scan_info": {
                "is_subscan": self._data.is_subscan,
                "actual_fov": self._data.actual_fov,
                "context_fov_nm": self._data.context_fov_nm,
                "scan_center_nm": self._data.scan_center_nm,
                "scan_rotation_deg": self._data.scan_rotation_deg,
                "raw_scan_info": self._data.scan_info
            },
            "hardware_info": {
                "channel_name": self._data.channel_name,
                "hardware_source": self._data.hardware_source,
                "pixel_time_us": self._data.pixel_time_us,
                "exposure_time": self._data.exposure_time
            },
            "timestamp": {
                "created": self._data.timestamp.isoformat() if self._data.timestamp else None,
                "timezone": self._data.timezone,
                "timezone_offset": self._data.timezone_offset
            },
            "calibrations": {
                "intensity": {
                    "scale": self._data.intensity_calibration.scale,
                    "offset": self._data.intensity_calibration.offset,
                    "units": self._data.intensity_calibration.units
                },
                "dimensions": [
                    {
                        "index": i,
                        "scale": cal.scale,
                        "offset": cal.offset,
                        "units": cal.units
                    }
                    for i, cal in enumerate(self._data.dimensional_calibrations)
                ]
            },
            "metadata": self._data.metadata,
            "raw_properties": self._data.raw_properties,
            "export_info": {
                "exported_at": datetime.now().isoformat(),
                "exporter_version": "1.0"
            }
        }
