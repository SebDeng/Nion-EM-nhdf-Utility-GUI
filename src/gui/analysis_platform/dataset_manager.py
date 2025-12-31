"""
Dataset Manager for Analysis Platform.

Manages imported CSV datasets, data persistence, and provides
data access for plotting and analysis.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime
import uuid
import json
import csv
import math
import os

from PySide6.QtCore import QObject, Signal


@dataclass
class DataPoint:
    """Single hole pairing data point with all variables."""
    pairing_id: str
    dataset_id: str  # Which dataset it came from

    # Basic variables
    delta_area_nm2: float = 0.0           # ΔA
    before_area_nm2: float = 0.0          # A₀
    after_area_nm2: float = 0.0           # A₁
    sqrt_A0_over_r: float = 0.0           # √A₀/r
    distance_to_center_nm: float = 0.0    # r

    # Extended variables
    before_centroid_x: float = 0.0
    before_centroid_y: float = 0.0
    after_centroid_x: float = 0.0
    after_centroid_y: float = 0.0
    before_perp_width_nm: float = 0.0
    after_perp_width_nm: float = 0.0

    # Metadata
    polygon_id_before: int = 0
    polygon_id_after: int = 0

    # Derived variables (computed on access)
    @property
    def sqrt_before_area(self) -> float:
        """√A₀"""
        return math.sqrt(max(0, self.before_area_nm2))

    @property
    def avg_perp_width_nm(self) -> float:
        """Average perpendicular width."""
        return (self.before_perp_width_nm + self.after_perp_width_nm) / 2.0

    def get_value(self, variable_name: str) -> float:
        """Get value by variable name for plotting."""
        mapping = {
            'delta_area_nm2': self.delta_area_nm2,
            'before_area_nm2': self.before_area_nm2,
            'after_area_nm2': self.after_area_nm2,
            'sqrt_A0_over_r': self.sqrt_A0_over_r,
            'distance_to_center_nm': self.distance_to_center_nm,
            'sqrt_before_area': self.sqrt_before_area,
            'before_centroid_x': self.before_centroid_x,
            'before_centroid_y': self.before_centroid_y,
            'after_centroid_x': self.after_centroid_x,
            'after_centroid_y': self.after_centroid_y,
            'before_perp_width_nm': self.before_perp_width_nm,
            'after_perp_width_nm': self.after_perp_width_nm,
            'avg_perp_width_nm': self.avg_perp_width_nm,
        }
        return mapping.get(variable_name, 0.0)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'pairing_id': self.pairing_id,
            'dataset_id': self.dataset_id,
            'delta_area_nm2': self.delta_area_nm2,
            'before_area_nm2': self.before_area_nm2,
            'after_area_nm2': self.after_area_nm2,
            'sqrt_A0_over_r': self.sqrt_A0_over_r,
            'distance_to_center_nm': self.distance_to_center_nm,
            'before_centroid_x': self.before_centroid_x,
            'before_centroid_y': self.before_centroid_y,
            'after_centroid_x': self.after_centroid_x,
            'after_centroid_y': self.after_centroid_y,
            'before_perp_width_nm': self.before_perp_width_nm,
            'after_perp_width_nm': self.after_perp_width_nm,
            'polygon_id_before': self.polygon_id_before,
            'polygon_id_after': self.polygon_id_after,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DataPoint':
        """Deserialize from dictionary."""
        return cls(
            pairing_id=data.get('pairing_id', ''),
            dataset_id=data.get('dataset_id', ''),
            delta_area_nm2=data.get('delta_area_nm2', 0.0),
            before_area_nm2=data.get('before_area_nm2', 0.0),
            after_area_nm2=data.get('after_area_nm2', 0.0),
            sqrt_A0_over_r=data.get('sqrt_A0_over_r', 0.0),
            distance_to_center_nm=data.get('distance_to_center_nm', 0.0),
            before_centroid_x=data.get('before_centroid_x', 0.0),
            before_centroid_y=data.get('before_centroid_y', 0.0),
            after_centroid_x=data.get('after_centroid_x', 0.0),
            after_centroid_y=data.get('after_centroid_y', 0.0),
            before_perp_width_nm=data.get('before_perp_width_nm', 0.0),
            after_perp_width_nm=data.get('after_perp_width_nm', 0.0),
            polygon_id_before=data.get('polygon_id_before', 0),
            polygon_id_after=data.get('polygon_id_after', 0),
        )


@dataclass
class Dataset:
    """A collection of data points from one CSV."""
    dataset_id: str
    name: str                              # User-friendly name
    light_intensity_mA: float = 0.0        # e.g., 54, 56, 58
    csv_path: str = ""                     # Original file path
    imported_at: str = ""                  # ISO timestamp
    color: str = "#4CAF50"                 # Display color in plots
    symbol: str = "o"                      # Plot symbol: o, s, t, d (circle, square, triangle, diamond)
    visible: bool = True                   # Show in plot
    session_path: str = ""                 # Path to source workspace session (.json file)
    data_points: List[DataPoint] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Number of data points."""
        return len(self.data_points)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'dataset_id': self.dataset_id,
            'name': self.name,
            'light_intensity_mA': self.light_intensity_mA,
            'csv_path': self.csv_path,
            'imported_at': self.imported_at,
            'color': self.color,
            'symbol': self.symbol,
            'visible': self.visible,
            'session_path': self.session_path,
            'data_points': [dp.to_dict() for dp in self.data_points],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Dataset':
        """Deserialize from dictionary."""
        dataset = cls(
            dataset_id=data.get('dataset_id', ''),
            name=data.get('name', ''),
            light_intensity_mA=data.get('light_intensity_mA', 0.0),
            csv_path=data.get('csv_path', ''),
            imported_at=data.get('imported_at', ''),
            color=data.get('color', '#4CAF50'),
            symbol=data.get('symbol', 'o'),
            visible=data.get('visible', True),
            session_path=data.get('session_path', ''),
        )
        dataset.data_points = [
            DataPoint.from_dict(dp) for dp in data.get('data_points', [])
        ]
        return dataset


@dataclass
class AnalysisProject:
    """Persisted project with all datasets."""
    project_id: str
    name: str
    created: str                           # ISO timestamp
    modified: str                          # ISO timestamp
    datasets: List[Dataset] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'version': 1,
            'project_id': self.project_id,
            'name': self.name,
            'created': self.created,
            'modified': self.modified,
            'datasets': [ds.to_dict() for ds in self.datasets],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AnalysisProject':
        """Deserialize from dictionary."""
        project = cls(
            project_id=data.get('project_id', ''),
            name=data.get('name', ''),
            created=data.get('created', ''),
            modified=data.get('modified', ''),
        )
        project.datasets = [
            Dataset.from_dict(ds) for ds in data.get('datasets', [])
        ]
        return project


# Available variables for plotting
PLOT_VARIABLES = [
    ('delta_area_nm2', 'ΔA (nm²)', 'Area change'),
    ('before_area_nm2', 'A₀ (nm²)', 'Before area'),
    ('after_area_nm2', 'A₁ (nm²)', 'After area'),
    ('sqrt_A0_over_r', '√A₀/r', 'sqrt(before_area) / distance'),
    ('distance_to_center_nm', 'r (nm)', 'Distance to center'),
    ('sqrt_before_area', '√A₀ (nm)', 'sqrt(before_area)'),
    ('before_centroid_x', 'Centroid X (before)', 'X position before'),
    ('before_centroid_y', 'Centroid Y (before)', 'Y position before'),
    ('after_centroid_x', 'Centroid X (after)', 'X position after'),
    ('after_centroid_y', 'Centroid Y (after)', 'Y position after'),
    ('before_perp_width_nm', 'Perp Width (before)', 'Perpendicular width before'),
    ('after_perp_width_nm', 'Perp Width (after)', 'Perpendicular width after'),
    ('avg_perp_width_nm', 'Avg Perp Width (nm)', 'Average perpendicular width'),
]

# Default colors for datasets
DEFAULT_COLORS = [
    '#4CAF50',  # Green
    '#FF9800',  # Orange
    '#9C27B0',  # Purple
    '#2196F3',  # Blue
    '#F44336',  # Red
    '#00BCD4',  # Cyan
    '#FFEB3B',  # Yellow
    '#795548',  # Brown
]

# Default symbols for datasets
DEFAULT_SYMBOLS = ['o', 's', 't', 'd', 'p', 'h', 'star', '+']


class DatasetManager(QObject):
    """Manages datasets and provides data access for the analysis platform."""

    # Signals
    datasets_changed = Signal()           # Emitted when datasets are added/removed/modified
    project_changed = Signal()            # Emitted when project metadata changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[AnalysisProject] = None
        self._project_path: Optional[str] = None

    @property
    def project(self) -> Optional[AnalysisProject]:
        """Get current project."""
        return self._project

    @property
    def datasets(self) -> List[Dataset]:
        """Get all datasets."""
        if self._project:
            return self._project.datasets
        return []

    @property
    def project_path(self) -> Optional[str]:
        """Get current project file path."""
        return self._project_path

    def new_project(self, name: str = "Untitled Project") -> AnalysisProject:
        """Create a new empty project."""
        now = datetime.now().isoformat()
        self._project = AnalysisProject(
            project_id=str(uuid.uuid4()),
            name=name,
            created=now,
            modified=now,
        )
        self._project_path = None
        self.project_changed.emit()
        return self._project

    def save_project(self, path: str) -> bool:
        """Save project to file."""
        if not self._project:
            return False

        try:
            self._project.modified = datetime.now().isoformat()
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._project.to_dict(), f, indent=2)
            self._project_path = path
            return True
        except Exception as e:
            print(f"Error saving project: {e}")
            return False

    def load_project(self, path: str) -> bool:
        """Load project from file."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._project = AnalysisProject.from_dict(data)
            self._project_path = path
            self.project_changed.emit()
            self.datasets_changed.emit()
            return True
        except Exception as e:
            print(f"Error loading project: {e}")
            return False

    def import_csv(self, csv_path: str, name: str, light_intensity_mA: float,
                   color: str = None, symbol: str = None,
                   session_path: str = "") -> Optional[Dataset]:
        """Import a CSV file as a new dataset."""
        if not self._project:
            self.new_project()

        # Assign default color and symbol
        idx = len(self._project.datasets)
        if color is None:
            color = DEFAULT_COLORS[idx % len(DEFAULT_COLORS)]
        if symbol is None:
            symbol = DEFAULT_SYMBOLS[idx % len(DEFAULT_SYMBOLS)]

        dataset_id = str(uuid.uuid4())
        data_points = self._parse_csv(csv_path, dataset_id)

        if not data_points:
            return None

        dataset = Dataset(
            dataset_id=dataset_id,
            name=name,
            light_intensity_mA=light_intensity_mA,
            csv_path=csv_path,
            imported_at=datetime.now().isoformat(),
            color=color,
            symbol=symbol,
            session_path=session_path,
            data_points=data_points,
        )

        self._project.datasets.append(dataset)
        self._project.modified = datetime.now().isoformat()
        self.datasets_changed.emit()

        return dataset

    def update_dataset(self, dataset_id: str, csv_path: str) -> bool:
        """Update a dataset by re-importing its CSV."""
        if not self._project:
            return False

        dataset = self.get_dataset(dataset_id)
        if not dataset:
            return False

        data_points = self._parse_csv(csv_path, dataset_id)
        if not data_points:
            return False

        dataset.data_points = data_points
        dataset.csv_path = csv_path
        dataset.imported_at = datetime.now().isoformat()
        self._project.modified = datetime.now().isoformat()
        self.datasets_changed.emit()

        return True

    def remove_dataset(self, dataset_id: str) -> bool:
        """Remove a dataset."""
        if not self._project:
            return False

        for i, ds in enumerate(self._project.datasets):
            if ds.dataset_id == dataset_id:
                del self._project.datasets[i]
                self._project.modified = datetime.now().isoformat()
                self.datasets_changed.emit()
                return True

        return False

    def get_dataset(self, dataset_id: str) -> Optional[Dataset]:
        """Get a dataset by ID."""
        if not self._project:
            return None

        for ds in self._project.datasets:
            if ds.dataset_id == dataset_id:
                return ds
        return None

    def get_all_points(self, visible_only: bool = True) -> List[DataPoint]:
        """Get all data points across all datasets."""
        points = []
        for ds in self.datasets:
            if visible_only and not ds.visible:
                continue
            points.extend(ds.data_points)
        return points

    def get_point_by_id(self, pairing_id: str) -> Optional[Tuple[Dataset, DataPoint]]:
        """Find a data point by pairing ID, returns (dataset, point)."""
        for ds in self.datasets:
            for point in ds.data_points:
                if point.pairing_id == pairing_id:
                    return (ds, point)
        return None

    def _parse_csv(self, csv_path: str, dataset_id: str) -> List[DataPoint]:
        """Parse CSV file into DataPoint objects."""
        data_points = []

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                # Skip comment lines (starting with #)
                lines = []
                for line in f:
                    stripped = line.strip()
                    if stripped and not stripped.startswith('#'):
                        lines.append(stripped)

                if not lines:
                    return []

                # Parse CSV
                reader = csv.DictReader(lines)

                for row in reader:
                    try:
                        point = DataPoint(
                            pairing_id=row.get('pairing_id', str(uuid.uuid4())[:8]),
                            dataset_id=dataset_id,
                            delta_area_nm2=float(row.get('delta_area_nm2', 0) or 0),
                            before_area_nm2=float(row.get('before_area_nm2', 0) or 0),
                            after_area_nm2=float(row.get('after_area_nm2', 0) or 0),
                            sqrt_A0_over_r=float(row.get('sqrt_A0_over_r', 0) or 0),
                            distance_to_center_nm=float(row.get('distance_to_center_nm', 0) or 0),
                            before_centroid_x=float(row.get('before_centroid_x', 0) or 0),
                            before_centroid_y=float(row.get('before_centroid_y', 0) or 0),
                            after_centroid_x=float(row.get('after_centroid_x', 0) or 0),
                            after_centroid_y=float(row.get('after_centroid_y', 0) or 0),
                            before_perp_width_nm=float(row.get('before_perp_width_nm', 0) or 0),
                            after_perp_width_nm=float(row.get('after_perp_width_nm', 0) or 0),
                            polygon_id_before=int(row.get('before_polygon_id', 0) or 0),
                            polygon_id_after=int(row.get('after_polygon_id', 0) or 0),
                        )
                        data_points.append(point)
                    except (ValueError, KeyError) as e:
                        print(f"Warning: Skipping row due to error: {e}")
                        continue

        except Exception as e:
            print(f"Error parsing CSV: {e}")
            return []

        return data_points

    def set_dataset_visibility(self, dataset_id: str, visible: bool):
        """Set dataset visibility."""
        dataset = self.get_dataset(dataset_id)
        if dataset:
            dataset.visible = visible
            self.datasets_changed.emit()

    def set_dataset_color(self, dataset_id: str, color: str):
        """Set dataset color."""
        dataset = self.get_dataset(dataset_id)
        if dataset:
            dataset.color = color
            self.datasets_changed.emit()

    def set_dataset_symbol(self, dataset_id: str, symbol: str):
        """Set dataset plot symbol."""
        dataset = self.get_dataset(dataset_id)
        if dataset:
            dataset.symbol = symbol
            self.datasets_changed.emit()

    def get_datasets_by_intensity(self) -> Dict[float, List[Dataset]]:
        """Group datasets by light intensity."""
        groups = {}
        for ds in self.datasets:
            intensity = ds.light_intensity_mA
            if intensity not in groups:
                groups[intensity] = []
            groups[intensity].append(ds)
        return groups

    def merge_datasets_by_intensity(self) -> List[Dataset]:
        """
        Create merged datasets for each unique light intensity.
        Returns list of new merged datasets.
        Does not modify existing datasets - adds new merged ones.
        """
        if not self._project:
            return []

        groups = self.get_datasets_by_intensity()
        merged_datasets = []

        for intensity, datasets in groups.items():
            # Skip if only one dataset with this intensity
            if len(datasets) <= 1:
                continue

            # Create merged dataset
            merged_id = str(uuid.uuid4())
            merged_name = f"Merged {intensity:.0f}mA"

            # Combine all data points
            all_points = []
            source_names = []
            for ds in datasets:
                for point in ds.data_points:
                    # Create copy with new dataset_id but preserve original pairing_id
                    new_point = DataPoint(
                        pairing_id=point.pairing_id,
                        dataset_id=merged_id,
                        delta_area_nm2=point.delta_area_nm2,
                        before_area_nm2=point.before_area_nm2,
                        after_area_nm2=point.after_area_nm2,
                        sqrt_A0_over_r=point.sqrt_A0_over_r,
                        distance_to_center_nm=point.distance_to_center_nm,
                        before_centroid_x=point.before_centroid_x,
                        before_centroid_y=point.before_centroid_y,
                        after_centroid_x=point.after_centroid_x,
                        after_centroid_y=point.after_centroid_y,
                        before_perp_width_nm=point.before_perp_width_nm,
                        after_perp_width_nm=point.after_perp_width_nm,
                        polygon_id_before=point.polygon_id_before,
                        polygon_id_after=point.polygon_id_after,
                    )
                    all_points.append(new_point)
                source_names.append(ds.name)

            # Pick a distinct color and symbol for merged dataset
            idx = len(self._project.datasets)
            merged_color = DEFAULT_COLORS[(idx + 4) % len(DEFAULT_COLORS)]  # Offset to get different color
            merged_symbol = 'star'  # Star symbol for merged datasets

            merged_dataset = Dataset(
                dataset_id=merged_id,
                name=merged_name,
                light_intensity_mA=intensity,
                csv_path=f"Merged from: {', '.join(source_names)}",
                imported_at=datetime.now().isoformat(),
                color=merged_color,
                symbol=merged_symbol,
                data_points=all_points,
            )

            merged_datasets.append(merged_dataset)
            self._project.datasets.append(merged_dataset)

        if merged_datasets:
            self._project.modified = datetime.now().isoformat()
            self.datasets_changed.emit()

        return merged_datasets
