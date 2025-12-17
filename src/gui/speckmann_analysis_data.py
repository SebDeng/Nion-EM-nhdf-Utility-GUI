"""
Data structures and algorithms for Speckmann thermal diffusion analysis.

Compares void evolution between first and final frames of ndata1 sequences
to categorize voids as grew, new, unchanged, or disappeared.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
from enum import Enum
import numpy as np
import re
import csv
from io import StringIO


class VoidType(Enum):
    """Classification of void evolution."""
    GREW = "grew"               # Matched, area increased
    NEW = "new"                 # Not present in first frame (A₀ = 0)
    UNCHANGED = "unchanged"     # Matched, minimal area change
    DISAPPEARED = "disappeared" # Present in frame 0, not in frame N


@dataclass
class VoidSnapshot:
    """Void state at a specific frame."""
    void_id: str
    frame_index: int
    centroid: Tuple[float, float]       # (x, y) in pixels
    centroid_nm: Tuple[float, float]    # (x, y) in nm
    area_px: float
    area_nm2: float
    vertices: List[Tuple[float, float]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'void_id': self.void_id,
            'frame_index': self.frame_index,
            'centroid': list(self.centroid),
            'centroid_nm': list(self.centroid_nm),
            'area_px': self.area_px,
            'area_nm2': self.area_nm2,
            'vertices': [list(v) for v in self.vertices]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VoidSnapshot':
        return cls(
            void_id=data['void_id'],
            frame_index=data['frame_index'],
            centroid=tuple(data['centroid']),
            centroid_nm=tuple(data['centroid_nm']),
            area_px=data['area_px'],
            area_nm2=data['area_nm2'],
            vertices=[tuple(v) for v in data['vertices']]
        )


@dataclass
class VoidPairing:
    """Tracks a void across frames."""
    pairing_id: str
    initial: Optional[VoidSnapshot]     # None if newly nucleated
    final: Optional[VoidSnapshot]       # None if disappeared
    void_type: VoidType
    delta_A_nm2: float                  # final - initial (or just final if new)
    distance_to_source_nm: float
    sqrt_A0_over_r: Optional[float]     # None if new (A₀=0)
    near_contamination: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'pairing_id': self.pairing_id,
            'initial': self.initial.to_dict() if self.initial else None,
            'final': self.final.to_dict() if self.final else None,
            'void_type': self.void_type.value,
            'delta_A_nm2': self.delta_A_nm2,
            'distance_to_source_nm': self.distance_to_source_nm,
            'sqrt_A0_over_r': self.sqrt_A0_over_r,
            'near_contamination': self.near_contamination,
            'notes': self.notes
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VoidPairing':
        return cls(
            pairing_id=data['pairing_id'],
            initial=VoidSnapshot.from_dict(data['initial']) if data['initial'] else None,
            final=VoidSnapshot.from_dict(data['final']) if data['final'] else None,
            void_type=VoidType(data['void_type']),
            delta_A_nm2=data['delta_A_nm2'],
            distance_to_source_nm=data['distance_to_source_nm'],
            sqrt_A0_over_r=data.get('sqrt_A0_over_r'),
            near_contamination=data.get('near_contamination', False),
            notes=data.get('notes', '')
        )


@dataclass
class ExperimentAnalysis:
    """Complete analysis of one ndata1 file."""
    # Experiment-level info
    experiment_id: str
    filename: str
    filepath: str
    temperature_C: Optional[int]
    subscan_center_x_nm: float
    subscan_center_y_nm: float
    subscan_fov_nm: float
    total_frames: int
    analyzed_frame: int
    frame_time_s: float
    electron_dose_e_per_nm2: Optional[float]

    # Void data
    initial_voids: List[VoidSnapshot] = field(default_factory=list)
    final_voids: List[VoidSnapshot] = field(default_factory=list)
    pairings: List[VoidPairing] = field(default_factory=list)

    # Derived statistics (computed after matching)
    n_grew: int = 0
    n_new: int = 0
    n_unchanged: int = 0
    n_disappeared: int = 0
    total_delta_A_grew: float = 0.0
    total_new_area: float = 0.0

    def compute_statistics(self):
        """Compute derived statistics from pairings."""
        self.n_grew = 0
        self.n_new = 0
        self.n_unchanged = 0
        self.n_disappeared = 0
        self.total_delta_A_grew = 0.0
        self.total_new_area = 0.0

        for p in self.pairings:
            if p.void_type == VoidType.GREW:
                self.n_grew += 1
                self.total_delta_A_grew += p.delta_A_nm2
            elif p.void_type == VoidType.NEW:
                self.n_new += 1
                self.total_new_area += p.delta_A_nm2
            elif p.void_type == VoidType.UNCHANGED:
                self.n_unchanged += 1
            elif p.void_type == VoidType.DISAPPEARED:
                self.n_disappeared += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            'experiment_id': self.experiment_id,
            'filename': self.filename,
            'filepath': self.filepath,
            'temperature_C': self.temperature_C,
            'subscan_center_x_nm': self.subscan_center_x_nm,
            'subscan_center_y_nm': self.subscan_center_y_nm,
            'subscan_fov_nm': self.subscan_fov_nm,
            'total_frames': self.total_frames,
            'analyzed_frame': self.analyzed_frame,
            'frame_time_s': self.frame_time_s,
            'electron_dose_e_per_nm2': self.electron_dose_e_per_nm2,
            'initial_voids': [v.to_dict() for v in self.initial_voids],
            'final_voids': [v.to_dict() for v in self.final_voids],
            'pairings': [p.to_dict() for p in self.pairings],
            'n_grew': self.n_grew,
            'n_new': self.n_new,
            'n_unchanged': self.n_unchanged,
            'n_disappeared': self.n_disappeared,
            'total_delta_A_grew': self.total_delta_A_grew,
            'total_new_area': self.total_new_area
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExperimentAnalysis':
        exp = cls(
            experiment_id=data['experiment_id'],
            filename=data['filename'],
            filepath=data['filepath'],
            temperature_C=data.get('temperature_C'),
            subscan_center_x_nm=data['subscan_center_x_nm'],
            subscan_center_y_nm=data['subscan_center_y_nm'],
            subscan_fov_nm=data['subscan_fov_nm'],
            total_frames=data['total_frames'],
            analyzed_frame=data['analyzed_frame'],
            frame_time_s=data['frame_time_s'],
            electron_dose_e_per_nm2=data.get('electron_dose_e_per_nm2')
        )
        exp.initial_voids = [VoidSnapshot.from_dict(v) for v in data.get('initial_voids', [])]
        exp.final_voids = [VoidSnapshot.from_dict(v) for v in data.get('final_voids', [])]
        exp.pairings = [VoidPairing.from_dict(p) for p in data.get('pairings', [])]
        exp.n_grew = data.get('n_grew', 0)
        exp.n_new = data.get('n_new', 0)
        exp.n_unchanged = data.get('n_unchanged', 0)
        exp.n_disappeared = data.get('n_disappeared', 0)
        exp.total_delta_A_grew = data.get('total_delta_A_grew', 0.0)
        exp.total_new_area = data.get('total_new_area', 0.0)
        return exp


@dataclass
class SpeckmannSession:
    """Session containing multiple experiment analyses."""
    experiments: List[ExperimentAnalysis] = field(default_factory=list)

    # Analysis parameters
    match_tolerance_nm: float = 3.0
    growth_threshold_nm2: float = 0.5
    min_void_area_nm2: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            'experiments': [e.to_dict() for e in self.experiments],
            'match_tolerance_nm': self.match_tolerance_nm,
            'growth_threshold_nm2': self.growth_threshold_nm2,
            'min_void_area_nm2': self.min_void_area_nm2
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SpeckmannSession':
        session = cls(
            match_tolerance_nm=data.get('match_tolerance_nm', 3.0),
            growth_threshold_nm2=data.get('growth_threshold_nm2', 0.5),
            min_void_area_nm2=data.get('min_void_area_nm2', 0.5)
        )
        session.experiments = [ExperimentAnalysis.from_dict(e) for e in data.get('experiments', [])]
        return session


# ============================================================================
# Utility Functions
# ============================================================================

def extract_temperature_from_path(filepath: str) -> Optional[int]:
    """
    Extract temperature from folder name pattern: 60kV_xxxC

    Examples:
        /data/60kV_150C/scan.ndata1 → 150
        /data/60kV_300C/scan.ndata1 → 300
    """
    match = re.search(r'60kV_(\d+)C', filepath)
    if match:
        return int(match.group(1))
    return None


def get_subscan_center(data) -> Tuple[float, float]:
    """
    Get subscan center from ndata1 metadata, or default to image center.

    Args:
        data: NHDFData object

    Returns:
        (center_x_nm, center_y_nm) tuple
    """
    scan_info = getattr(data, 'scan_info', None)
    if scan_info:
        center_x = scan_info.get('center_x_nm')
        center_y = scan_info.get('center_y_nm')
        if center_x is not None and center_y is not None:
            return (float(center_x), float(center_y))

    # Default: image center in nm
    frame_shape = getattr(data, 'frame_shape', None)
    if frame_shape:
        h, w = frame_shape
        calibrations = getattr(data, 'dimensional_calibrations', None)
        scale = 1.0
        if calibrations and len(calibrations) > 0:
            cal = calibrations[-1]  # Use last (typically X) calibration
            scale = getattr(cal, 'scale', 1.0)
        return (w * scale / 2, h * scale / 2)

    return (0.0, 0.0)


def calculate_proper_centroid(vertices: List[Tuple[float, float]]) -> Tuple[float, float]:
    """
    Calculate true centroid (center of mass) of polygon using shoelace formula.

    Args:
        vertices: List of (x, y) coordinates

    Returns:
        (cx, cy) centroid coordinates
    """
    n = len(vertices)
    if n < 3:
        if n == 0:
            return (0.0, 0.0)
        return (sum(v[0] for v in vertices) / n, sum(v[1] for v in vertices) / n)

    signed_area = 0.0
    cx = cy = 0.0

    for i in range(n):
        j = (i + 1) % n
        cross = vertices[i][0] * vertices[j][1] - vertices[j][0] * vertices[i][1]
        signed_area += cross
        cx += (vertices[i][0] + vertices[j][0]) * cross
        cy += (vertices[i][1] + vertices[j][1]) * cross

    signed_area *= 0.5
    if abs(signed_area) < 1e-10:
        return (sum(v[0] for v in vertices) / n, sum(v[1] for v in vertices) / n)

    cx /= (6.0 * signed_area)
    cy /= (6.0 * signed_area)
    return (cx, cy)


def calculate_polygon_area(vertices: List[Tuple[float, float]]) -> float:
    """
    Calculate polygon area using shoelace formula.

    Args:
        vertices: List of (x, y) coordinates

    Returns:
        Absolute area value
    """
    n = len(vertices)
    if n < 3:
        return 0.0

    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += vertices[i][0] * vertices[j][1]
        area -= vertices[j][0] * vertices[i][1]

    return abs(area) / 2.0


def euclidean_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Calculate Euclidean distance between two points."""
    return np.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)


def check_point_in_polygon(point: Tuple[float, float],
                           polygon: List[Tuple[float, float]]) -> bool:
    """
    Check if a point is inside a polygon using ray casting algorithm.
    Avoids shapely dependency.

    Args:
        point: (x, y) coordinates
        polygon: List of (x, y) vertices

    Returns:
        True if point is inside polygon
    """
    x, y = point
    n = len(polygon)
    inside = False

    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]

        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i

    return inside


def find_nearest_void(target: VoidSnapshot,
                      void_list: List[VoidSnapshot]) -> Optional[VoidSnapshot]:
    """Find the nearest void to target from a list."""
    if not void_list:
        return None

    min_dist = float('inf')
    nearest = None

    for v in void_list:
        dist = euclidean_distance(target.centroid_nm, v.centroid_nm)
        if dist < min_dist:
            min_dist = dist
            nearest = v

    return nearest


class MatchingDebugInfo:
    """Debug information from matching process."""
    def __init__(self):
        self.initial_centroids_nm = []
        self.final_centroids_nm = []
        self.distance_matrix = []  # List of (initial_id, final_id, distance_nm)
        self.matched_pairs = []    # List of (initial_id, final_id, distance_nm)
        self.min_distance = float('inf')
        self.max_distance = 0.0
        self.tolerance_used = 0.0


def match_voids(initial_voids: List[VoidSnapshot],
                final_voids: List[VoidSnapshot],
                source_center_nm: Tuple[float, float],
                tolerance_nm: float = 3.0,
                growth_threshold_nm2: float = 0.5,
                return_debug: bool = False
                ) -> List[VoidPairing]:
    """
    Match voids between frames and categorize.

    Uses greedy nearest-neighbor matching (similar to hole_pairing_panel.py).

    Args:
        initial_voids: Voids from first frame
        final_voids: Voids from final frame
        source_center_nm: (x, y) of vacancy source in nm
        tolerance_nm: Maximum distance for matching
        growth_threshold_nm2: Minimum ΔA to classify as "grew"
        return_debug: If True, returns (pairings, debug_info)

    Returns:
        List of VoidPairing objects (or tuple with debug info)
    """

    n_initial = len(initial_voids)
    n_final = len(final_voids)

    pairings = []
    pairing_counter = 1

    # Debug info
    debug = MatchingDebugInfo()
    debug.tolerance_used = tolerance_nm
    debug.initial_centroids_nm = [(iv.void_id, iv.centroid_nm) for iv in initial_voids]
    debug.final_centroids_nm = [(fv.void_id, fv.centroid_nm) for fv in final_voids]

    if n_initial == 0 and n_final == 0:
        if return_debug:
            return pairings, debug
        return pairings

    # Handle edge cases
    if n_initial == 0:
        # All final voids are new
        for fv in final_voids:
            dist_to_source = euclidean_distance(fv.centroid_nm, source_center_nm)
            near_contam = False
            pairings.append(VoidPairing(
                pairing_id=f"P{pairing_counter:03d}",
                initial=None,
                final=fv,
                void_type=VoidType.NEW,
                delta_A_nm2=fv.area_nm2,
                distance_to_source_nm=dist_to_source,
                sqrt_A0_over_r=None,
                near_contamination=near_contam
            ))
            pairing_counter += 1
        if return_debug:
            return pairings, debug
        return pairings

    if n_final == 0:
        # All initial voids disappeared
        for iv in initial_voids:
            dist_to_source = euclidean_distance(iv.centroid_nm, source_center_nm)
            near_contam = False
            pairings.append(VoidPairing(
                pairing_id=f"P{pairing_counter:03d}",
                initial=iv,
                final=None,
                void_type=VoidType.DISAPPEARED,
                delta_A_nm2=-iv.area_nm2,
                distance_to_source_nm=dist_to_source,
                sqrt_A0_over_r=None,
                near_contamination=near_contam
            ))
            pairing_counter += 1
        if return_debug:
            return pairings, debug
        return pairings

    # Build distance matrix for debug info
    for iv in initial_voids:
        for fv in final_voids:
            dist = euclidean_distance(fv.centroid_nm, iv.centroid_nm)
            debug.distance_matrix.append((iv.void_id, fv.void_id, dist))
            if dist < debug.min_distance:
                debug.min_distance = dist
            if dist > debug.max_distance:
                debug.max_distance = dist

    # Greedy nearest-neighbor matching (like hole_pairing_panel.py)
    # This is simpler and works well for small numbers of voids
    used_final_ids = set()
    matched_initial = set()
    matched_final = set()

    for i, iv in enumerate(initial_voids):
        best_match = None
        best_distance = float('inf')

        for j, fv in enumerate(final_voids):
            if j in used_final_ids:
                continue

            # Calculate distance between centroids in nm
            dist = euclidean_distance(iv.centroid_nm, fv.centroid_nm)

            if dist < tolerance_nm and dist < best_distance:
                best_match = (j, fv)
                best_distance = dist

        if best_match is not None:
            j, fv = best_match
            delta_A = fv.area_nm2 - iv.area_nm2

            # Use average centroid for distance calculation
            avg_centroid_nm = (
                (iv.centroid_nm[0] + fv.centroid_nm[0]) / 2,
                (iv.centroid_nm[1] + fv.centroid_nm[1]) / 2
            )
            dist_to_source = euclidean_distance(avg_centroid_nm, source_center_nm)

            # Determine void type based on area change
            if delta_A > growth_threshold_nm2:
                void_type = VoidType.GREW
            elif delta_A < -growth_threshold_nm2:
                # Void shrunk - still track
                void_type = VoidType.GREW
            else:
                void_type = VoidType.UNCHANGED

            # Calculate sqrt(A0)/r for Ostwald ripening analysis
            if iv.area_nm2 > 0 and dist_to_source > 0:
                sqrt_A0_over_r = np.sqrt(iv.area_nm2) / dist_to_source
            else:
                sqrt_A0_over_r = None

            near_contam = False

            pairings.append(VoidPairing(
                pairing_id=f"P{pairing_counter:03d}",
                initial=iv,
                final=fv,
                void_type=void_type,
                delta_A_nm2=delta_A,
                distance_to_source_nm=dist_to_source,
                sqrt_A0_over_r=sqrt_A0_over_r,
                near_contamination=near_contam,
                notes=f"Match dist: {best_distance:.2f} nm"
            ))
            pairing_counter += 1
            used_final_ids.add(j)
            matched_initial.add(i)
            matched_final.add(j)
            debug.matched_pairs.append((iv.void_id, fv.void_id, best_distance))

    # Unmatched final voids → new
    for j, fv in enumerate(final_voids):
        if j not in matched_final:
            dist_to_source = euclidean_distance(fv.centroid_nm, source_center_nm)
            near_contam = False

            # Find nearest initial void for note
            nearest_dist = float('inf')
            nearest_id = None
            for iv in initial_voids:
                d = euclidean_distance(fv.centroid_nm, iv.centroid_nm)
                if d < nearest_dist:
                    nearest_dist = d
                    nearest_id = iv.void_id

            notes = f"Nearest initial: {nearest_id} @ {nearest_dist:.2f}nm" if nearest_id else ""

            pairings.append(VoidPairing(
                pairing_id=f"P{pairing_counter:03d}",
                initial=None,
                final=fv,
                void_type=VoidType.NEW,
                delta_A_nm2=fv.area_nm2,
                distance_to_source_nm=dist_to_source,
                sqrt_A0_over_r=None,
                near_contamination=near_contam,
                notes=notes
            ))
            pairing_counter += 1

    # Unmatched initial voids → disappeared
    for i, iv in enumerate(initial_voids):
        if i not in matched_initial:
            dist_to_source = euclidean_distance(iv.centroid_nm, source_center_nm)
            near_contam = False

            # Find nearest final void to suggest what absorbed it
            nearest_dist = float('inf')
            nearest = None
            for fv in final_voids:
                d = euclidean_distance(iv.centroid_nm, fv.centroid_nm)
                if d < nearest_dist:
                    nearest_dist = d
                    nearest = fv

            notes = f"Nearest final: {nearest.void_id} @ {nearest_dist:.2f}nm" if nearest else ""

            pairings.append(VoidPairing(
                pairing_id=f"P{pairing_counter:03d}",
                initial=iv,
                final=None,
                void_type=VoidType.DISAPPEARED,
                delta_A_nm2=-iv.area_nm2,
                distance_to_source_nm=dist_to_source,
                sqrt_A0_over_r=None,
                near_contamination=near_contam,
                notes=notes
            ))
            pairing_counter += 1

    if return_debug:
        return pairings, debug
    return pairings


# ============================================================================
# CSV Export/Import
# ============================================================================

def export_session_to_csv(session: SpeckmannSession, filepath: str):
    """
    Export session to CSV with experiment info and void pairings.

    Creates two sections:
    1. Experiment Info
    2. Void Pairings
    """
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)

        # Section 1: Experiment Info
        writer.writerow(['# Experiment Info'])
        writer.writerow([
            'filename', 'temperature_C',
            'subscan_center_x_nm', 'subscan_center_y_nm', 'subscan_fov_nm',
            'total_frames', 'analyzed_frame', 'frame_time_s',
            'electron_dose_e_per_nm2', 'n_grew', 'n_new', 'n_unchanged', 'n_disappeared'
        ])

        for exp in session.experiments:
            writer.writerow([
                exp.filename,
                exp.temperature_C if exp.temperature_C is not None else '',
                f"{exp.subscan_center_x_nm:.2f}",
                f"{exp.subscan_center_y_nm:.2f}",
                f"{exp.subscan_fov_nm:.2f}",
                exp.total_frames,
                exp.analyzed_frame,
                f"{exp.frame_time_s:.4f}",
                f"{exp.electron_dose_e_per_nm2:.2e}" if exp.electron_dose_e_per_nm2 else '',
                exp.n_grew,
                exp.n_new,
                exp.n_unchanged,
                exp.n_disappeared
            ])

        writer.writerow([])  # Empty row separator

        # Section 2: Void Pairings
        writer.writerow(['# Void Pairings'])
        writer.writerow([
            'filename', 'temperature_C', 'void_id', 'void_type',
            'initial_area_nm2', 'final_area_nm2', 'delta_A_nm2',
            'distance_to_source_nm', 'sqrt_A0_over_r', 'notes'
        ])

        for exp in session.experiments:
            for p in exp.pairings:
                # Get void ID from final if exists, else from initial
                void_id = p.final.void_id if p.final else p.initial.void_id

                writer.writerow([
                    exp.filename,
                    exp.temperature_C if exp.temperature_C is not None else '',
                    void_id,
                    p.void_type.value,
                    f"{p.initial.area_nm2:.3f}" if p.initial else '0',
                    f"{p.final.area_nm2:.3f}" if p.final else '0',
                    f"{p.delta_A_nm2:.3f}",
                    f"{p.distance_to_source_nm:.2f}",
                    f"{p.sqrt_A0_over_r:.4f}" if p.sqrt_A0_over_r else '',
                    p.notes
                ])


def import_session_from_csv(filepath: str) -> SpeckmannSession:
    """
    Import session from CSV file.

    Note: This imports summary data only, not full polygon vertices.
    """
    session = SpeckmannSession()

    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Find section headers
    exp_header_idx = None
    void_header_idx = None

    for i, row in enumerate(rows):
        if row and row[0] == '# Experiment Info':
            exp_header_idx = i + 1
        elif row and row[0] == '# Void Pairings':
            void_header_idx = i + 1

    if exp_header_idx is None or void_header_idx is None:
        raise ValueError("Invalid CSV format: missing section headers")

    # Parse experiments
    experiments_by_id = {}

    for i in range(exp_header_idx + 1, void_header_idx - 1):
        row = rows[i]
        if not row or row[0].startswith('#'):
            continue

        exp_id = row[0]
        exp = ExperimentAnalysis(
            experiment_id=exp_id,
            filename=row[1],
            filepath='',  # Not stored in CSV
            temperature_C=int(row[2]) if row[2] else None,
            subscan_center_x_nm=float(row[3]),
            subscan_center_y_nm=float(row[4]),
            subscan_fov_nm=float(row[5]),
            total_frames=int(row[6]),
            analyzed_frame=int(row[7]),
            frame_time_s=float(row[8]),
            electron_dose_e_per_nm2=float(row[9]) if row[9] else None
        )
        exp.n_grew = int(row[10]) if len(row) > 10 else 0
        exp.n_new = int(row[11]) if len(row) > 11 else 0
        exp.n_unchanged = int(row[12]) if len(row) > 12 else 0
        exp.n_disappeared = int(row[13]) if len(row) > 13 else 0

        experiments_by_id[exp_id] = exp
        session.experiments.append(exp)

    # Parse void pairings (simplified - no full vertex data)
    for i in range(void_header_idx + 1, len(rows)):
        row = rows[i]
        if not row or len(row) < 12 or row[0].startswith('#'):
            continue

        exp_id = row[0]
        if exp_id not in experiments_by_id:
            continue

        exp = experiments_by_id[exp_id]

        # Create simplified pairing (without full VoidSnapshot)
        void_type = VoidType(row[2])

        # Create VoidSnapshots with available data
        initial = None
        if row[3] and float(row[3]) > 0:
            initial = VoidSnapshot(
                void_id=row[1],
                frame_index=0,
                centroid=(0, 0),  # Not available
                centroid_nm=(float(row[6]) if row[6] else 0, float(row[7]) if row[7] else 0),
                area_px=0,  # Not available
                area_nm2=float(row[3]),
                vertices=[]  # Not available
            )

        final = None
        if row[4] and float(row[4]) > 0:
            final = VoidSnapshot(
                void_id=row[1],
                frame_index=exp.analyzed_frame,
                centroid=(0, 0),
                centroid_nm=(float(row[8]) if row[8] else 0, float(row[9]) if row[9] else 0),
                area_px=0,
                area_nm2=float(row[4]),
                vertices=[]
            )

        pairing = VoidPairing(
            pairing_id=f"P{len(exp.pairings)+1:03d}",
            initial=initial,
            final=final,
            void_type=void_type,
            delta_A_nm2=float(row[5]),
            distance_to_source_nm=float(row[10]),
            sqrt_A0_over_r=float(row[11]) if row[11] else None,
            near_contamination=row[12].lower() == 'true' if len(row) > 12 else False,
            notes=row[13] if len(row) > 13 else ''
        )

        exp.pairings.append(pairing)

    return session
