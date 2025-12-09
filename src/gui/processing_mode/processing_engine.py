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
        """Apply all processing steps to a single frame."""
        result = frame.astype(np.float64)

        # Get original data statistics
        orig_min = np.min(frame)
        orig_max = np.max(frame)
        orig_mean = np.mean(frame)
        data_range = orig_max - orig_min if orig_max > orig_min else 1.0

        # Apply brightness - more aggressive scaling
        if 'brightness' in params and params['brightness'] != 0:
            # Scale brightness more aggressively: -100 to 100 maps to -range to +range
            brightness_scale = data_range * (params['brightness'] / 100.0)
            result = result + brightness_scale

        # Apply contrast - center around mean
        if 'contrast' in params and params['contrast'] != 1.0:
            # Use original mean as center point
            result = orig_mean + (result - orig_mean) * params['contrast']

        # Apply gamma
        if 'gamma' in params and params['gamma'] != 1.0:
            # Normalize to 0-1 range
            current_min = np.min(result)
            current_max = np.max(result)
            if current_max > current_min:
                normalized = (result - current_min) / (current_max - current_min)
                # Apply gamma
                normalized = np.power(np.clip(normalized, 0, 1), params['gamma'])
                # Rescale back to original range
                result = normalized * data_range + orig_min

        # Apply filters
        result = self._apply_filters(result, params)

        return result

    def _apply_filters(self, image: np.ndarray, params: Dict[str, Any]) -> np.ndarray:
        """Apply filter operations to image."""
        from scipy import ndimage
        result = image.copy()

        # Gaussian blur
        if params.get('gaussian_enabled') and 'gaussian_sigma' in params:
            result = ndimage.gaussian_filter(result, sigma=params['gaussian_sigma'])

        # Median filter
        if params.get('median_enabled') and 'median_size' in params:
            result = ndimage.median_filter(result, size=params['median_size'])

        # Unsharp mask
        if params.get('unsharp_enabled') and 'unsharp_amount' in params and 'unsharp_radius' in params:
            # Create blurred version
            blurred = ndimage.gaussian_filter(result, sigma=params['unsharp_radius'])
            # Apply unsharp mask
            result = result + params['unsharp_amount'] * (result - blurred)

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

            if self.on_processing_complete:
                self.on_processing_complete(self.current_processed_data)