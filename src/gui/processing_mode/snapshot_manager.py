"""
Manager for handling processing snapshots and their history.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from PySide6.QtCore import QObject, Signal
import numpy as np
import uuid


@dataclass
class ProcessingSnapshot:
    """
    Represents a snapshot of processed image with its parameters.
    """
    id: str
    timestamp: datetime
    processed_data: np.ndarray
    processing_params: Dict[str, Any]
    frame_index: int
    parent_id: Optional[str] = None  # For tracking processing tree
    notes: str = ""

    def get_summary(self) -> str:
        """Get a summary of the processing applied."""
        params = []
        if 'brightness' in self.processing_params and self.processing_params['brightness'] != 0:
            params.append(f"Brightness: {self.processing_params['brightness']}")
        if 'contrast' in self.processing_params and self.processing_params['contrast'] != 1.0:
            params.append(f"Contrast: {self.processing_params['contrast']:.2f}")
        if 'gamma' in self.processing_params and self.processing_params['gamma'] != 1.0:
            params.append(f"Gamma: {self.processing_params['gamma']:.2f}")
        if 'gaussian_sigma' in self.processing_params:
            params.append(f"Gaussian σ={self.processing_params['gaussian_sigma']:.1f}")
        if 'median_size' in self.processing_params:
            params.append(f"Median size={self.processing_params['median_size']}")
        if 'unsharp_amount' in self.processing_params:
            params.append(f"Unsharp mask")

        return " | ".join(params) if params else "No processing"


@dataclass
class ProcessingHistory:
    """
    Tracks the complete processing history for a file.
    """
    file_path: str
    original_shape: tuple
    original_dtype: np.dtype
    snapshots: List[ProcessingSnapshot] = field(default_factory=list)
    current_snapshot_id: Optional[str] = None

    def add_snapshot(self, snapshot: ProcessingSnapshot):
        """Add a snapshot to the history."""
        self.snapshots.append(snapshot)
        self.current_snapshot_id = snapshot.id

    def get_snapshot(self, snapshot_id: str) -> Optional[ProcessingSnapshot]:
        """Get a specific snapshot by ID."""
        for snapshot in self.snapshots:
            if snapshot.id == snapshot_id:
                return snapshot
        return None

    def get_processing_tree(self) -> Dict[str, List[str]]:
        """Get the processing tree structure."""
        tree = {}
        for snapshot in self.snapshots:
            if snapshot.parent_id:
                if snapshot.parent_id not in tree:
                    tree[snapshot.parent_id] = []
                tree[snapshot.parent_id].append(snapshot.id)
        return tree


class SnapshotManager(QObject):
    """
    Manages snapshots and processing history.
    """

    # Signals
    snapshot_created = Signal(object)  # ProcessingSnapshot
    snapshot_deleted = Signal(str)  # snapshot_id
    snapshot_selected = Signal(str)  # snapshot_id

    def __init__(self):
        super().__init__()

        self.snapshots: Dict[str, ProcessingSnapshot] = {}
        self.history: Optional[ProcessingHistory] = None
        self.current_file: Optional[str] = None
        self._next_snapshot_number = 1

    def reset(self):
        """Reset the snapshot manager for a new file."""
        self.snapshots.clear()
        self.history = None
        self._next_snapshot_number = 1

    def create_snapshot(
        self,
        processed_data: np.ndarray,
        processing_params: Dict[str, Any],
        frame_index: int = 0,
        parent_id: Optional[str] = None,
        notes: str = ""
    ) -> ProcessingSnapshot:
        """Create a new snapshot."""
        # Generate ID
        snapshot_id = f"S{self._next_snapshot_number:03d}"
        self._next_snapshot_number += 1

        # Create snapshot
        snapshot = ProcessingSnapshot(
            id=snapshot_id,
            timestamp=datetime.now(),
            processed_data=processed_data.copy(),  # Make a copy
            processing_params=processing_params.copy(),
            frame_index=frame_index,
            parent_id=parent_id,
            notes=notes
        )

        # Store snapshot
        self.snapshots[snapshot_id] = snapshot

        # Add to history if available
        if self.history:
            self.history.add_snapshot(snapshot)

        # Emit signal
        self.snapshot_created.emit(snapshot)

        return snapshot

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        if snapshot_id in self.snapshots:
            del self.snapshots[snapshot_id]

            # Remove from history
            if self.history:
                self.history.snapshots = [
                    s for s in self.history.snapshots if s.id != snapshot_id
                ]

            # Emit signal
            self.snapshot_deleted.emit(snapshot_id)
            return True

        return False

    def get_snapshot(self, snapshot_id: str) -> Optional[ProcessingSnapshot]:
        """Get a specific snapshot."""
        return self.snapshots.get(snapshot_id)

    def get_all_snapshots(self) -> List[ProcessingSnapshot]:
        """Get all snapshots."""
        return list(self.snapshots.values())

    def get_snapshot_count(self) -> int:
        """Get the number of snapshots."""
        return len(self.snapshots)

    def export_snapshot(self, snapshot_id: str, file_path: str, format: str = 'tiff'):
        """Export a snapshot to file."""
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            return False

        # Import here to avoid circular dependency
        from src.core.exporter import ExportSettings, Exporter

        # Create temporary NHDFData-like object for exporter
        class TempData:
            def __init__(self, data):
                self.data = data
                self.shape = data.shape
                self.dtype = data.dtype

        temp_data = TempData(snapshot.processed_data)

        # Set up export settings
        settings = ExportSettings(
            output_dir=str(file_path.parent) if hasattr(file_path, 'parent') else '.',
            file_name=str(file_path.name) if hasattr(file_path, 'name') else file_path,
            image_format=format
        )

        # Export
        try:
            exporter = Exporter(temp_data)
            exporter.export(settings)
            return True
        except Exception as e:
            print(f"Failed to export snapshot: {e}")
            return False

    def compare_snapshots(self, snapshot_ids: List[str]) -> Optional[np.ndarray]:
        """
        Create a comparison image of multiple snapshots.
        Returns a composite image for display.
        """
        if len(snapshot_ids) < 2:
            return None

        snapshots = [self.get_snapshot(sid) for sid in snapshot_ids]
        snapshots = [s for s in snapshots if s is not None]

        if len(snapshots) < 2:
            return None

        # Get the images
        images = [s.processed_data for s in snapshots]

        # Ensure all images have the same shape
        target_shape = images[0].shape
        for i in range(1, len(images)):
            if images[i].shape != target_shape:
                # Resize if needed (simple approach)
                # In production, might want more sophisticated resizing
                continue

        # Create comparison grid (2x2 for up to 4 images, etc.)
        import math
        n = len(images)
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)

        # Create composite image
        h, w = target_shape
        composite = np.zeros((rows * h, cols * w), dtype=images[0].dtype)

        for i, img in enumerate(images):
            row = i // cols
            col = i % cols
            composite[row*h:(row+1)*h, col*w:(col+1)*w] = img

        return composite

    def get_processing_chain(self, snapshot_id: str) -> List[Dict[str, Any]]:
        """
        Get the complete processing chain leading to a snapshot.
        Returns list of processing steps in order.
        """
        chain = []
        current_id = snapshot_id

        while current_id:
            snapshot = self.get_snapshot(current_id)
            if not snapshot:
                break

            # Add to beginning of chain (reverse order)
            chain.insert(0, {
                'id': snapshot.id,
                'timestamp': snapshot.timestamp.isoformat(),
                'params': snapshot.processing_params,
                'notes': snapshot.notes
            })

            current_id = snapshot.parent_id

        return chain

    def create_processing_report(self, snapshot_id: str) -> str:
        """
        Create a text report of the processing applied to reach a snapshot.
        """
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            return "Snapshot not found"

        chain = self.get_processing_chain(snapshot_id)

        report = f"Processing Report for {snapshot_id}\n"
        report += f"{'='*50}\n"
        report += f"Created: {snapshot.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"Frame Index: {snapshot.frame_index}\n\n"

        report += "Processing Steps:\n"
        report += f"{'-'*30}\n"

        for i, step in enumerate(chain, 1):
            report += f"\nStep {i}: {step['id']}\n"
            report += f"Time: {step['timestamp']}\n"

            if step['params']:
                report += "Parameters:\n"
                for key, value in step['params'].items():
                    if isinstance(value, float):
                        report += f"  - {key}: {value:.2f}\n"
                    else:
                        report += f"  - {key}: {value}\n"

            if step['notes']:
                report += f"Notes: {step['notes']}\n"

        return report