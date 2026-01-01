"""
Data structures for hole pairing in vacancy diffusion analysis.

Used to track pairings between "sink" holes in before/after STEM images,
and the fate of small holes (disappeared or absorbed into sinks).
"""

from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any
from enum import Enum
import uuid
from datetime import datetime


class HoleFate(Enum):
    """Fate of a small hole in vacancy diffusion analysis."""
    UNKNOWN = "unknown"
    DISAPPEARED = "disappeared"  # Consumed by vacancy flux
    ABSORBED = "absorbed"        # Absorbed into a nearby sink (Ostwald ripening)
    SURVIVED = "survived"        # Still exists in "after" image


@dataclass
class HoleReference:
    """Reference to a polygon hole in a specific panel."""
    panel_id: str                           # panel_id from WorkspaceDisplayPanel
    polygon_id: int                         # _polygon_id from polygon ROI
    centroid: Tuple[float, float]           # (x, y) in pixels - proper centroid
    area_nm2: float                         # Area in nm²
    area_px: float = 0.0                    # Area in pixels
    vertices: List[Tuple[float, float]] = field(default_factory=list)  # For visualization

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'panel_id': self.panel_id,
            'polygon_id': self.polygon_id,
            'centroid': list(self.centroid),
            'area_nm2': self.area_nm2,
            'area_px': self.area_px,
            'vertices': [list(v) for v in self.vertices]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HoleReference':
        """Deserialize from dictionary."""
        return cls(
            panel_id=data['panel_id'],
            polygon_id=data['polygon_id'],
            centroid=tuple(data['centroid']),
            area_nm2=data.get('area_nm2', 0.0),
            area_px=data.get('area_px', 0.0),
            vertices=[tuple(v) for v in data.get('vertices', [])]
        )


@dataclass
class SinkPairing:
    """Pairing between a sink in 'before' and 'after' images."""
    pairing_id: str = field(default_factory=lambda: f"P{str(uuid.uuid4())[:6]}")
    before_hole: Optional[HoleReference] = None
    after_hole: Optional[HoleReference] = None
    distance_to_center_nm: float = 0.0      # Distance from image center (vacancy source)
    distance_to_center_px: float = 0.0      # Distance in pixels
    area_change_nm2: float = 0.0            # Area difference (after - before)
    sqrt_A0_over_r: float = 0.0             # Key metric: sqrt(before_area) / distance
    confirmed: bool = False
    created: str = field(default_factory=lambda: datetime.now().isoformat())

    def calculate_metrics(self, calibration_scale: float = 1.0):
        """Calculate derived metrics after pairing is set."""
        if self.before_hole and self.after_hole:
            self.area_change_nm2 = self.after_hole.area_nm2 - self.before_hole.area_nm2
        elif self.before_hole:
            self.area_change_nm2 = -self.before_hole.area_nm2  # Hole disappeared

        # Calculate sqrt(A0)/r metric
        if self.before_hole and self.distance_to_center_nm > 0:
            import math
            sqrt_A0 = math.sqrt(self.before_hole.area_nm2)
            self.sqrt_A0_over_r = sqrt_A0 / self.distance_to_center_nm

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'pairing_id': self.pairing_id,
            'before_hole': self.before_hole.to_dict() if self.before_hole else None,
            'after_hole': self.after_hole.to_dict() if self.after_hole else None,
            'distance_to_center_nm': self.distance_to_center_nm,
            'distance_to_center_px': self.distance_to_center_px,
            'area_change_nm2': self.area_change_nm2,
            'sqrt_A0_over_r': self.sqrt_A0_over_r,
            'confirmed': self.confirmed,
            'created': self.created
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SinkPairing':
        """Deserialize from dictionary."""
        return cls(
            pairing_id=data.get('pairing_id', f"P{str(uuid.uuid4())[:6]}"),
            before_hole=HoleReference.from_dict(data['before_hole']) if data.get('before_hole') else None,
            after_hole=HoleReference.from_dict(data['after_hole']) if data.get('after_hole') else None,
            distance_to_center_nm=data.get('distance_to_center_nm', 0.0),
            distance_to_center_px=data.get('distance_to_center_px', 0.0),
            area_change_nm2=data.get('area_change_nm2', 0.0),
            sqrt_A0_over_r=data.get('sqrt_A0_over_r', 0.0),
            confirmed=data.get('confirmed', False),
            created=data.get('created', datetime.now().isoformat())
        )


@dataclass
class SmallHoleFate:
    """Tracks the fate of a small hole (area <= sink_threshold)."""
    fate_id: str = field(default_factory=lambda: f"F{str(uuid.uuid4())[:6]}")
    hole: Optional[HoleReference] = None
    fate: HoleFate = HoleFate.UNKNOWN
    absorbed_by_pairing_id: Optional[str] = None  # If fate is ABSORBED, which sink
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'fate_id': self.fate_id,
            'hole': self.hole.to_dict() if self.hole else None,
            'fate': self.fate.value,
            'absorbed_by_pairing_id': self.absorbed_by_pairing_id,
            'notes': self.notes
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SmallHoleFate':
        """Deserialize from dictionary."""
        return cls(
            fate_id=data.get('fate_id', f"F{str(uuid.uuid4())[:6]}"),
            hole=HoleReference.from_dict(data['hole']) if data.get('hole') else None,
            fate=HoleFate(data.get('fate', 'unknown')),
            absorbed_by_pairing_id=data.get('absorbed_by_pairing_id'),
            notes=data.get('notes', '')
        )


@dataclass
class PairingSession:
    """Complete pairing session with configuration and data."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Panel references
    before_panel_id: Optional[str] = None
    after_panel_id: Optional[str] = None
    before_panel_title: str = ""  # For display
    after_panel_title: str = ""   # For display

    # Configuration
    sink_threshold_nm2: float = 4.0         # Default 4 nm² - holes larger are "sinks"
    match_tolerance_nm: float = 3.0         # Default 3 nm proximity for matching

    # Image center (vacancy source point) - always image center
    image_center_px: Optional[Tuple[float, float]] = None
    image_size_px: Optional[Tuple[int, int]] = None  # (width, height)
    calibration_scale: float = 1.0          # nm per pixel

    # Pairing data
    sink_pairings: List[SinkPairing] = field(default_factory=list)
    small_hole_fates: List[SmallHoleFate] = field(default_factory=list)

    # Timestamps
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    modified: str = field(default_factory=lambda: datetime.now().isoformat())

    def touch(self):
        """Update modified timestamp."""
        self.modified = datetime.now().isoformat()

    def get_confirmed_pairings(self) -> List[SinkPairing]:
        """Get only confirmed pairings."""
        return [p for p in self.sink_pairings if p.confirmed]

    def get_unconfirmed_pairings(self) -> List[SinkPairing]:
        """Get unconfirmed (suggested) pairings."""
        return [p for p in self.sink_pairings if not p.confirmed]

    def get_pairing_by_id(self, pairing_id: str) -> Optional[SinkPairing]:
        """Find a pairing by its ID."""
        for p in self.sink_pairings:
            if p.pairing_id == pairing_id:
                return p
        return None

    def add_pairing(self, pairing: SinkPairing):
        """Add a new pairing."""
        self.sink_pairings.append(pairing)
        self.touch()

    def remove_pairing(self, pairing_id: str):
        """Remove a pairing by ID."""
        self.sink_pairings = [p for p in self.sink_pairings if p.pairing_id != pairing_id]
        self.touch()

    def confirm_pairing(self, pairing_id: str):
        """Mark a pairing as confirmed."""
        pairing = self.get_pairing_by_id(pairing_id)
        if pairing:
            pairing.confirmed = True
            self.touch()

    def get_small_hole_fate(self, polygon_id: int, panel_id: str) -> Optional[SmallHoleFate]:
        """Find a small hole fate by polygon ID and panel."""
        for f in self.small_hole_fates:
            if f.hole and f.hole.polygon_id == polygon_id and f.hole.panel_id == panel_id:
                return f
        return None

    def set_small_hole_fate(self, hole: HoleReference, fate: HoleFate,
                            absorbed_by: Optional[str] = None):
        """Set or update the fate of a small hole."""
        existing = self.get_small_hole_fate(hole.polygon_id, hole.panel_id)
        if existing:
            existing.fate = fate
            existing.absorbed_by_pairing_id = absorbed_by
        else:
            self.small_hole_fates.append(SmallHoleFate(
                hole=hole,
                fate=fate,
                absorbed_by_pairing_id=absorbed_by
            ))
        self.touch()

    def clear(self):
        """Clear all pairings and fates."""
        self.sink_pairings.clear()
        self.small_hole_fates.clear()
        self.touch()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            'session_id': self.session_id,
            'before_panel_id': self.before_panel_id,
            'after_panel_id': self.after_panel_id,
            'before_panel_title': self.before_panel_title,
            'after_panel_title': self.after_panel_title,
            'sink_threshold_nm2': self.sink_threshold_nm2,
            'match_tolerance_nm': self.match_tolerance_nm,
            'image_center_px': list(self.image_center_px) if self.image_center_px else None,
            'image_size_px': list(self.image_size_px) if self.image_size_px else None,
            'calibration_scale': self.calibration_scale,
            'sink_pairings': [p.to_dict() for p in self.sink_pairings],
            'small_hole_fates': [f.to_dict() for f in self.small_hole_fates],
            'created': self.created,
            'modified': self.modified
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PairingSession':
        """Deserialize from dictionary."""
        session = cls(
            session_id=data.get('session_id', str(uuid.uuid4())[:8]),
            before_panel_id=data.get('before_panel_id'),
            after_panel_id=data.get('after_panel_id'),
            before_panel_title=data.get('before_panel_title', ''),
            after_panel_title=data.get('after_panel_title', ''),
            sink_threshold_nm2=data.get('sink_threshold_nm2', 4.0),
            match_tolerance_nm=data.get('match_tolerance_nm', 3.0),
            calibration_scale=data.get('calibration_scale', 1.0),
            created=data.get('created', datetime.now().isoformat()),
            modified=data.get('modified', datetime.now().isoformat())
        )

        # Restore image center/size
        if data.get('image_center_px'):
            session.image_center_px = tuple(data['image_center_px'])
        if data.get('image_size_px'):
            session.image_size_px = tuple(data['image_size_px'])

        # Restore pairings
        for p_data in data.get('sink_pairings', []):
            session.sink_pairings.append(SinkPairing.from_dict(p_data))

        # Restore small hole fates
        for f_data in data.get('small_hole_fates', []):
            session.small_hole_fates.append(SmallHoleFate.from_dict(f_data))

        return session


def calculate_proper_centroid(vertices: List[Tuple[float, float]]) -> Tuple[float, float]:
    """
    Calculate true centroid (center of mass) of polygon using the shoelace formula.

    This is more accurate than simple average of vertices, especially for
    non-convex polygons.

    Args:
        vertices: List of (x, y) vertex coordinates

    Returns:
        (cx, cy) centroid coordinates
    """
    n = len(vertices)
    if n == 0:
        return (0.0, 0.0)
    if n < 3:
        # For degenerate cases, use simple average
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

    # Handle degenerate polygon (zero area)
    if abs(signed_area) < 1e-10:
        return (sum(v[0] for v in vertices) / n, sum(v[1] for v in vertices) / n)

    cx /= (6.0 * signed_area)
    cy /= (6.0 * signed_area)

    return (cx, cy)


def calculate_polygon_area(vertices: List[Tuple[float, float]]) -> float:
    """
    Calculate polygon area using the shoelace formula.

    Args:
        vertices: List of (x, y) vertex coordinates

    Returns:
        Area in square units (pixels or nm depending on input)
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


def calculate_perpendicular_width(vertices: List[Tuple[float, float]],
                                   centroid: Tuple[float, float],
                                   image_center: Tuple[float, float]) -> float:
    """
    Calculate the perpendicular width of a polygon relative to the vacancy flux direction.

    The vacancy flux comes from image_center toward the polygon centroid.
    This function finds the maximum width of the polygon perpendicular to this flux direction,
    which represents the "capture cross-section" for vacancies.

    Args:
        vertices: List of (x, y) vertex coordinates
        centroid: (cx, cy) polygon centroid
        image_center: (x, y) image center (vacancy source)

    Returns:
        Width in the same units as input (pixels or nm)
    """
    import math

    n = len(vertices)
    if n < 3:
        return 0.0

    # Direction vector from image center to centroid (flux direction)
    dx = centroid[0] - image_center[0]
    dy = centroid[1] - image_center[1]

    # Normalize
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1e-10:
        return 0.0

    dx /= length
    dy /= length

    # Perpendicular direction (rotate 90 degrees)
    perp_x = -dy
    perp_y = dx

    # Project all vertices onto the perpendicular axis
    # The projection is the dot product with the perpendicular direction
    projections = []
    for vx, vy in vertices:
        # Vector from centroid to vertex
        rel_x = vx - centroid[0]
        rel_y = vy - centroid[1]
        # Project onto perpendicular direction
        proj = rel_x * perp_x + rel_y * perp_y
        projections.append(proj)

    # Width is the range of projections
    width = max(projections) - min(projections)
    return width


def calculate_perimeter(vertices: List[Tuple[float, float]]) -> float:
    """
    Calculate the perimeter (total edge length) of a polygon.

    Args:
        vertices: List of (x, y) vertex coordinates

    Returns:
        Perimeter in the same units as input (pixels or nm)
    """
    import math

    n = len(vertices)
    if n < 2:
        return 0.0

    perimeter = 0.0
    for i in range(n):
        j = (i + 1) % n  # Next vertex (wraps around to close polygon)
        dx = vertices[j][0] - vertices[i][0]
        dy = vertices[j][1] - vertices[i][1]
        perimeter += math.sqrt(dx * dx + dy * dy)

    return perimeter
