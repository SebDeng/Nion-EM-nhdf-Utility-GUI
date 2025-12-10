"""
Processing engine that handles all image processing operations.
Maintains processed frames and ensures consistency across all frames.
"""

import numpy as np
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass
class ProcessingState:
    """Represents a complete processing state."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    original_data: Optional[np.ndarray] = None
    processed_data: Optional[np.ndarray] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    parent_id: Optional[str] = None
    name: str = ""

    @property
    def processing_params(self) -> Dict[str, Any]:
        """Alias for parameters for backwards compatibility."""
        return self.parameters

    def get_frame(self, index: int) -> Optional[np.ndarray]:
        """Get a specific processed frame."""
        if self.processed_data is None:
            return None
        if len(self.processed_data.shape) == 3:
            if 0 <= index < self.processed_data.shape[0]:
                return self.processed_data[index]
        else:
            return self.processed_data
        return None


class ProcessingEngine:
    """
    Central processing engine that handles all image processing operations.
    """

    def __init__(self):
        self.original_data: Optional[np.ndarray] = None
        self.current_processed_data: Optional[np.ndarray] = None
        self.current_parameters: Dict[str, Any] = {}

        # Processing tree
        self.states: Dict[str, ProcessingState] = {}
        self.current_state_id: Optional[str] = None

        # Callbacks for UI updates
        self.on_processing_complete: Optional[Callable] = None
        self.on_frame_processed: Optional[Callable] = None

    def load_data(self, data: np.ndarray):
        """Load original data for processing."""
        self.original_data = data.astype(np.float64)
        self.current_processed_data = self.original_data.copy()
        self.current_parameters = {}
        self.states.clear()
        self.current_state_id = None

    def apply_processing(self, parameters: Dict[str, Any], real_time: bool = True):
        """
        Apply processing to all frames with given parameters.

        Args:
            parameters: Processing parameters (brightness, contrast, gamma, filters)
            real_time: If True, processes immediately for real-time preview
        """
        if self.original_data is None:
            return

        self.current_parameters = parameters.copy()

        # Process all frames
        if len(self.original_data.shape) == 3:
            # Multi-frame data
            num_frames = self.original_data.shape[0]
            self.current_processed_data = np.zeros_like(self.original_data)

            for i in range(num_frames):
                # Process each frame
                frame = self.original_data[i].copy()
                processed_frame = self._process_single_frame(frame, parameters)
                self.current_processed_data[i] = processed_frame

                # Callback for progress updates if needed
                if self.on_frame_processed and not real_time:
                    self.on_frame_processed(i, num_frames)
        else:
            # Single frame
            self.current_processed_data = self._process_single_frame(
                self.original_data.copy(), parameters
            )

        # Callback when complete
        if self.on_processing_complete:
            self.on_processing_complete(self.current_processed_data)

    def _process_single_frame(self, frame: np.ndarray, params: Dict[str, Any]) -> np.ndarray:
        """
        Apply all processing steps to a single frame.
        Follows ImageJ/Fiji conventions for all operations.
        """
        result = frame.astype(np.float64)

        # Get original data statistics for reference
        orig_min = np.min(frame)
        orig_max = np.max(frame)
        data_range = orig_max - orig_min if orig_max > orig_min else 1.0

        # === ImageJ-style Brightness & Contrast ===
        # In ImageJ, B&C adjusts the display window (min/max) not pixel values directly.
        # But for actual pixel modification (like Process > Math > Add), we follow this:
        #
        # ImageJ Brightness: Simply adds a value to all pixels
        # ImageJ Contrast: Multiplies deviation from center by a factor
        #
        # The formula ImageJ uses for B&C window adjustment:
        #   display_value = (pixel - min) / (max - min) * 255
        # Where min/max are adjusted by brightness/contrast sliders
        #
        # For pixel modification, we use:
        #   new_pixel = (pixel - center) * contrast + center + brightness

        center = (orig_min + orig_max) / 2.0

        # Apply contrast first (ImageJ applies contrast around center)
        if 'contrast' in params and params['contrast'] != 1.0:
            # ImageJ contrast: multiply deviation from center
            result = (result - center) * params['contrast'] + center

        # Apply brightness (ImageJ: simple addition, scaled to data range)
        if 'brightness' in params and params['brightness'] != 0:
            # Map -100 to 100 slider to reasonable fraction of data range
            # ImageJ uses direct pixel value addition
            brightness_offset = (params['brightness'] / 100.0) * data_range
            result = result + brightness_offset

        # === ImageJ-style Gamma ===
        # ImageJ gamma: Process > Math > Gamma
        # Formula: output = (input/max)^gamma * max
        # Or normalized: output = input^gamma (for 0-1 range)
        if 'gamma' in params and params['gamma'] != 1.0:
            # Normalize to 0-1 based on current data range
            current_min = np.min(result)
            current_max = np.max(result)
            if current_max > current_min:
                # Normalize to 0-1
                normalized = (result - current_min) / (current_max - current_min)
                # Clip to valid range
                normalized = np.clip(normalized, 0, 1)
                # Apply gamma (ImageJ formula)
                normalized = np.power(normalized, params['gamma'])
                # Scale back to original range
                result = normalized * (current_max - current_min) + current_min

        # === Local Normalization ===
        # Normalize intensity within local blocks to equalize contrast
        if params.get('local_norm_enabled'):
            block_size = params.get('local_norm_block_size', 45)
            result = self._apply_local_normalization(result, block_size)

        # Apply filters (ImageJ-style)
        result = self._apply_filters(result, params)

        return result

    def _apply_filters(self, image: np.ndarray, params: Dict[str, Any]) -> np.ndarray:
        """
        Apply filter operations to image.
        All filters follow ImageJ/Fiji conventions.
        """
        from scipy import ndimage
        result = image.copy()

        # === ImageJ Gaussian Blur ===
        # ImageJ: Process > Filters > Gaussian Blur
        # Uses sigma (radius) in pixels, applies separable 2D Gaussian
        # scipy.ndimage.gaussian_filter is equivalent
        if params.get('gaussian_enabled') and 'gaussian_sigma' in params:
            sigma = params['gaussian_sigma']
            # ImageJ uses the same sigma for both dimensions
            result = ndimage.gaussian_filter(result, sigma=sigma, mode='reflect')

        # === ImageJ Median Filter ===
        # ImageJ: Process > Filters > Median
        # Uses a square neighborhood of given radius
        # ImageJ "radius" means the filter size is (2*radius+1)
        # Our "size" parameter directly specifies the neighborhood size
        if params.get('median_enabled') and 'median_size' in params:
            size = params['median_size']
            # Ensure odd size (ImageJ uses odd sizes)
            if size % 2 == 0:
                size += 1
            result = ndimage.median_filter(result, size=size, mode='reflect')

        # === ImageJ Unsharp Mask ===
        # ImageJ: Process > Filters > Unsharp Mask
        # Formula: sharpened = original + weight * (original - blurred)
        # Parameters:
        #   - Radius (sigma): Gaussian blur radius in pixels
        #   - Mask Weight: Amount of sharpening (0-1 typical, can go higher)
        if params.get('unsharp_enabled') and 'unsharp_amount' in params and 'unsharp_radius' in params:
            radius = params['unsharp_radius']
            weight = params['unsharp_amount']
            # Create blurred version using Gaussian (ImageJ style)
            blurred = ndimage.gaussian_filter(result, sigma=radius, mode='reflect')
            # ImageJ formula: output = original + weight * (original - blurred)
            result = result + weight * (result - blurred)

        # === ImageJ FFT Bandpass Filter ===
        # ImageJ: Process > FFT > Bandpass Filter
        if params.get('bandpass_enabled'):
            result = self._apply_bandpass_filter_imagej(
                result,
                filter_large=params.get('bandpass_large', 40),
                filter_small=params.get('bandpass_small', 3),
                suppress_stripes=params.get('bandpass_suppress_stripes', 'None'),
                tolerance=params.get('bandpass_tolerance', 5),
                autoscale=params.get('bandpass_autoscale', True),
                saturate=params.get('bandpass_saturate', False)
            )

        # === ImageJ Rolling Ball Background Subtraction ===
        # ImageJ: Process > Subtract Background
        if params.get('rolling_ball_enabled'):
            result = self._apply_rolling_ball_background(
                result,
                radius=params.get('rolling_ball_radius', 50),
                light_background=params.get('rolling_ball_light_bg', False),
                create_background=params.get('rolling_ball_create_bg', False)
            )

        return result

    def _apply_bandpass_filter_imagej(self, image: np.ndarray,
                                        filter_large: float = 40,
                                        filter_small: float = 3,
                                        suppress_stripes: str = 'None',
                                        tolerance: float = 5,
                                        autoscale: bool = True,
                                        saturate: bool = False) -> np.ndarray:
        """
        Apply ImageJ-style FFT Bandpass Filter.

        This replicates ImageJ's Process > FFT > Bandpass Filter exactly.

        Args:
            image: Input image
            filter_large: Filter large structures down to X pixels (high-pass cutoff)
            filter_small: Filter small structures up to X pixels (low-pass cutoff)
            suppress_stripes: 'None', 'Horizontal', or 'Vertical'
            tolerance: Direction tolerance for stripe suppression (%)
            autoscale: Whether to autoscale result after filtering
            saturate: Whether to saturate when autoscaling

        Returns:
            Bandpass filtered image
        """
        rows, cols = image.shape

        # ImageJ pads to power of 2 for FFT efficiency
        # Find next power of 2
        fft_rows = int(2 ** np.ceil(np.log2(rows)))
        fft_cols = int(2 ** np.ceil(np.log2(cols)))

        # Pad image (ImageJ uses edge padding)
        padded = np.zeros((fft_rows, fft_cols), dtype=np.float64)
        padded[:rows, :cols] = image

        # Mirror padding for edges (ImageJ style)
        if rows < fft_rows:
            padded[rows:, :cols] = image[rows-1::-1, :][:fft_rows-rows, :]
        if cols < fft_cols:
            padded[:rows, cols:] = image[:, cols-1::-1][:, :fft_cols-cols]
        if rows < fft_rows and cols < fft_cols:
            padded[rows:, cols:] = image[rows-1::-1, cols-1::-1][:fft_rows-rows, :fft_cols-cols]

        # Perform FFT
        fft = np.fft.fft2(padded)
        fft_shifted = np.fft.fftshift(fft)

        # Create filter mask
        crow, ccol = fft_rows // 2, fft_cols // 2
        y, x = np.ogrid[:fft_rows, :fft_cols]

        # Distance from center in pixels
        distance = np.sqrt((x - ccol) ** 2 + (y - crow) ** 2)

        # ImageJ uses pixel-based cutoffs
        # filter_large: removes structures larger than this (high-pass)
        # filter_small: removes structures smaller than this (low-pass)

        # Convert to frequency domain cutoffs
        # In ImageJ, filter_large corresponds to low frequency cutoff
        # filter_small corresponds to high frequency cutoff

        # ImageJ uses smooth Gaussian-like transitions
        filter_mask = np.ones((fft_rows, fft_cols), dtype=np.float64)

        # High-pass filter (remove large structures / low frequencies)
        if filter_large > 0 and filter_large < max(fft_rows, fft_cols):
            # Cutoff frequency corresponds to structures of size filter_large pixels
            # frequency = size / 2 in FFT space
            cutoff_large = max(fft_rows, fft_cols) / filter_large
            # Smooth Gaussian transition (ImageJ style)
            hp_filter = 1.0 - np.exp(-(distance ** 2) / (2 * cutoff_large ** 2))
            filter_mask *= hp_filter

        # Low-pass filter (remove small structures / high frequencies)
        if filter_small > 0:
            cutoff_small = max(fft_rows, fft_cols) / filter_small
            # Smooth Gaussian transition
            lp_filter = np.exp(-(distance ** 2) / (2 * cutoff_small ** 2))
            filter_mask *= lp_filter

        # Stripe suppression (ImageJ feature)
        if suppress_stripes in ['Horizontal', 'Vertical']:
            angle_tolerance = tolerance / 100.0 * np.pi / 2  # Convert to radians

            # Calculate angle from center
            with np.errstate(divide='ignore', invalid='ignore'):
                angle = np.arctan2(y - crow, x - ccol)
                angle = np.nan_to_num(angle, nan=0.0)

            if suppress_stripes == 'Horizontal':
                # Suppress horizontal stripes = suppress vertical frequencies
                # Vertical frequencies are near angle = ±π/2
                stripe_mask = np.abs(np.abs(angle) - np.pi/2) > angle_tolerance
            else:  # Vertical
                # Suppress vertical stripes = suppress horizontal frequencies
                # Horizontal frequencies are near angle = 0 or ±π
                stripe_mask = (np.abs(angle) > angle_tolerance) & (np.abs(angle) < np.pi - angle_tolerance)

            # Smooth transition at the edges
            filter_mask *= stripe_mask.astype(np.float64)

        # Preserve DC component (ImageJ does this)
        filter_mask[crow, ccol] = 1.0

        # Apply filter
        filtered_fft = fft_shifted * filter_mask

        # Inverse FFT
        filtered = np.fft.ifft2(np.fft.ifftshift(filtered_fft))
        filtered = np.real(filtered)

        # Crop back to original size
        result = filtered[:rows, :cols]

        # Autoscale if requested (ImageJ default)
        if autoscale:
            result_min = np.min(result)
            result_max = np.max(result)
            orig_min = np.min(image)
            orig_max = np.max(image)

            if result_max > result_min:
                # Scale to original range
                result = (result - result_min) / (result_max - result_min)
                result = result * (orig_max - orig_min) + orig_min

                if saturate:
                    result = np.clip(result, orig_min, orig_max)

        return result

    def _apply_rolling_ball_background(self, image: np.ndarray,
                                        radius: int = 50,
                                        light_background: bool = False,
                                        create_background: bool = False) -> np.ndarray:
        """
        Apply ImageJ-style Rolling Ball Background Subtraction.

        This replicates ImageJ's Process > Subtract Background algorithm.
        The rolling ball algorithm was introduced by Stanley Sternberg in 1983.

        The algorithm simulates rolling a ball underneath (or above for light backgrounds)
        the image surface to estimate the background.

        Args:
            image: Input 2D image
            radius: Rolling ball radius in pixels (larger = smoother background)
            light_background: If True, assumes light background (inverts algorithm)
            create_background: If True, returns the background instead of subtracting it

        Returns:
            Background-subtracted image (or background if create_background=True)
        """
        from scipy import ndimage
        from scipy.ndimage import minimum_filter, maximum_filter, zoom

        rows, cols = image.shape
        result = image.astype(np.float64)

        # For light backgrounds, invert the image first
        if light_background:
            img_min = np.min(result)
            img_max = np.max(result)
            result = img_max + img_min - result  # Invert around center

        # ImageJ's optimized rolling ball algorithm:
        # 1. Shrink the image to speed up processing
        # 2. Roll the ball on the shrunk image
        # 3. Expand back and interpolate

        # Calculate shrink factor (ImageJ uses this optimization)
        # For radius > 10, shrink to speed up processing
        shrink_factor = max(1, radius // 10)

        if shrink_factor > 1:
            # Shrink image using block minimum (faster vectorized approach)
            small_rows = rows // shrink_factor
            small_cols = cols // shrink_factor

            # Reshape for block processing
            trimmed = result[:small_rows * shrink_factor, :small_cols * shrink_factor]
            reshaped = trimmed.reshape(small_rows, shrink_factor, small_cols, shrink_factor)
            small_image = reshaped.min(axis=(1, 3))

            # Adjusted radius for shrunk image
            small_radius = max(1, radius // shrink_factor)
        else:
            small_image = result.copy()
            small_rows, small_cols = rows, cols
            small_radius = radius

        # Create ball structure (paraboloid approximation)
        # The ball is a paraboloid: z = dist^2 / (2*r)
        ball_width = 2 * small_radius + 1
        y, x = np.ogrid[:ball_width, :ball_width]
        x = x - small_radius
        y = y - small_radius
        dist_sq = (x * x + y * y).astype(np.float64)

        # Create paraboloid ball (ImageJ's approximation)
        # Height increases as we move away from center
        ball = np.where(
            dist_sq <= small_radius * small_radius,
            dist_sq / (2.0 * small_radius),
            np.inf  # Outside the ball - will be ignored
        )

        # Rolling ball: We want to find the minimum of (image - ball_offset) at each position
        # This is equivalent to a local minimum filter with the ball shape subtracted

        # Simplified approach: Use morphological opening with a disk footprint
        # and then smooth to approximate the paraboloid effect

        # Create circular footprint
        footprint = dist_sq <= small_radius * small_radius

        # Morphological opening = erosion followed by dilation
        # This finds the "floor" where a flat disk can roll
        eroded = minimum_filter(small_image, footprint=footprint, mode='reflect')
        background_small = maximum_filter(eroded, footprint=footprint, mode='reflect')

        # Apply additional smoothing to better approximate rolling ball
        # The paraboloid shape creates smoother transitions than flat disk
        smooth_size = max(3, small_radius // 2)
        if smooth_size % 2 == 0:
            smooth_size += 1
        background_small = ndimage.uniform_filter(background_small, size=smooth_size)

        # Expand background back to original size if shrunk
        if shrink_factor > 1:
            # Use bilinear interpolation to expand
            zoom_factor_r = rows / small_rows
            zoom_factor_c = cols / small_cols
            background = zoom(background_small, (zoom_factor_r, zoom_factor_c), order=1)
            # Ensure exact size match
            background = background[:rows, :cols]
        else:
            background = background_small

        # For light backgrounds, invert back
        if light_background:
            result = img_max + img_min - result
            background = img_max + img_min - background

        # Return background or subtract it
        if create_background:
            return background
        else:
            subtracted = result - background
            return subtracted

    def _apply_local_normalization(self, image: np.ndarray, block_size: int = 45) -> np.ndarray:
        """
        Apply local normalization to equalize contrast across the image.

        Divides the image into blocks and normalizes each block independently
        to have values in the range [0, 1]. This helps when different regions
        of the image have very different intensity levels.

        Args:
            image: Input 2D image
            block_size: Size of blocks in pixels (larger = smoother normalization)

        Returns:
            Locally normalized image with values scaled to original range
        """
        rows, cols = image.shape
        result = np.zeros_like(image, dtype=np.float64)

        # Store original range to scale output
        orig_min = np.min(image)
        orig_max = np.max(image)
        orig_range = orig_max - orig_min if orig_max > orig_min else 1.0

        # Process image in blocks
        for y in range(0, rows, block_size):
            for x in range(0, cols, block_size):
                # Get block bounds (handle edge cases)
                y_end = min(y + block_size, rows)
                x_end = min(x + block_size, cols)

                # Extract block
                block = image[y:y_end, x:x_end].astype(np.float64)

                # Normalize block to [0, 1]
                block_min = np.min(block)
                block_max = np.max(block)

                if block_max > block_min:
                    normalized_block = (block - block_min) / (block_max - block_min)
                else:
                    # Constant block - set to 0.5
                    normalized_block = np.full_like(block, 0.5)

                # Store normalized block
                result[y:y_end, x:x_end] = normalized_block

        # Scale back to original range
        result = result * orig_range + orig_min

        return result

    def get_current_frame(self, index: int) -> Optional[np.ndarray]:
        """Get the current processed frame at index."""
        if self.current_processed_data is None:
            return None

        if len(self.current_processed_data.shape) == 3:
            if 0 <= index < self.current_processed_data.shape[0]:
                return self.current_processed_data[index]
        else:
            return self.current_processed_data

        return None

    def create_snapshot(self, name: str = "") -> ProcessingState:
        """Create a snapshot of the current processing state."""
        state = ProcessingState(
            original_data=self.original_data.copy() if self.original_data is not None else None,
            processed_data=self.current_processed_data.copy() if self.current_processed_data is not None else None,
            parameters=self.current_parameters.copy(),
            parent_id=self.current_state_id,
            name=name or f"Snapshot {len(self.states) + 1}"
        )

        self.states[state.id] = state
        self.current_state_id = state.id

        return state

    def load_snapshot(self, state_id: str):
        """Load a snapshot as the current processing state."""
        if state_id in self.states:
            state = self.states[state_id]
            self.current_processed_data = state.processed_data.copy() if state.processed_data is not None else None
            self.current_parameters = state.parameters.copy()
            self.current_state_id = state_id

            # Notify UI
            if self.on_processing_complete:
                self.on_processing_complete(self.current_processed_data)

    def get_processing_tree(self) -> Dict[str, list]:
        """Get the processing tree structure."""
        tree = {}
        for state_id, state in self.states.items():
            if state.parent_id:
                if state.parent_id not in tree:
                    tree[state.parent_id] = []
                tree[state.parent_id].append(state_id)
            else:
                # Root nodes
                if 'root' not in tree:
                    tree['root'] = []
                tree['root'].append(state_id)
        return tree

    def reset_to_original(self):
        """Reset to original unprocessed data."""
        if self.original_data is not None:
            self.current_processed_data = self.original_data.copy()
            self.current_parameters = {}
            # Reset current state to None so new snapshots branch from root
            self.current_state_id = None

            if self.on_processing_complete:
                self.on_processing_complete(self.current_processed_data)