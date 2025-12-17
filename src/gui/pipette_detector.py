"""
Pipette detector for automatic polygon detection.
Uses flood-fill algorithm to detect dark regions in images.
Optimized for performance with vectorized numpy operations.
"""

import numpy as np
from scipy.ndimage import label, binary_erosion
from scipy.spatial import ConvexHull
from typing import Optional, Tuple, List
from dataclasses import dataclass


@dataclass
class DetectionResult:
    """Result of pipette region detection."""
    vertices: List[Tuple[float, float]]  # Polygon vertices
    mask: np.ndarray  # Binary mask of detected region
    area_px: float  # Area in pixels
    centroid: Tuple[float, float]  # Center of region
    clicked_value: float  # Intensity at click point
    threshold: float  # Threshold used for detection


class PipetteDetector:
    """
    Detects dark regions in images using flood-fill algorithm.
    Click on a dark region to automatically detect its boundary.
    Optimized for speed using vectorized operations.
    """

    def __init__(self):
        self.min_area_px = 10  # Minimum region area in pixels
        self.preview_vertices = 20  # Fast preview vertex count
        self.min_vertices = 10  # Minimum polygon vertices for final
        self.max_vertices = 100  # Maximum polygon vertices (hard limit)
        self.vertices_per_perimeter_px = 8  # Target: 1 vertex per N pixels of perimeter
        self.default_tolerance = 0.10  # Default threshold tolerance (10%)

    def detect_region(
        self,
        image_data: np.ndarray,
        click_x: float,
        click_y: float,
        threshold_tolerance: float = None,
        max_image_size: int = 1024
    ) -> Optional[DetectionResult]:
        """
        Detect connected dark region at click point using flood fill.

        Args:
            image_data: 2D numpy array (grayscale image)
            click_x, click_y: Clicked pixel coordinates
            threshold_tolerance: Tolerance as fraction of data range (0.0-1.0)
                                Higher = include more pixels (larger region)
            max_image_size: Maximum dimension for processing (larger images downsampled)

        Returns:
            DetectionResult with vertices, mask, area, etc.
            None if no valid region detected
        """
        if threshold_tolerance is None:
            threshold_tolerance = self.default_tolerance

        # Handle RGB images by converting to grayscale
        if len(image_data.shape) == 3:
            # Use luminance formula (fast)
            image_data = np.mean(image_data, axis=2)

        height, width = image_data.shape

        # Downsample large images for speed
        scale_factor = 1.0
        if max(height, width) > max_image_size:
            scale_factor = max_image_size / max(height, width)
            new_h = int(height * scale_factor)
            new_w = int(width * scale_factor)
            # Fast downsampling using slicing
            step_h = max(1, height // new_h)
            step_w = max(1, width // new_w)
            image_data = image_data[::step_h, ::step_w]
            height, width = image_data.shape
            click_x = click_x * scale_factor
            click_y = click_y * scale_factor

        # Ensure coordinates are within bounds
        click_x = int(np.clip(click_x, 0, width - 1))
        click_y = int(np.clip(click_y, 0, height - 1))

        # Get clicked pixel intensity
        clicked_value = float(image_data[click_y, click_x])

        # Calculate threshold
        data_min = float(image_data.min())
        data_max = float(image_data.max())
        data_range = data_max - data_min

        if data_range == 0:
            return None  # Uniform image, no detection possible

        # Threshold: include pixels darker than clicked + tolerance
        threshold = clicked_value + (data_range * threshold_tolerance)

        # Create binary mask (dark pixels below threshold)
        binary_mask = image_data < threshold

        # Label connected components
        labeled, num_features = label(binary_mask)

        if num_features == 0:
            return None  # No dark regions found

        # Get label at click point
        clicked_label = labeled[click_y, click_x]

        if clicked_label == 0:
            return None  # Clicked on background (above threshold)

        # Extract only the clicked region
        region_mask = (labeled == clicked_label)

        # Calculate area (scale back to original size)
        area_px = float(np.sum(region_mask))
        if scale_factor != 1.0:
            area_px = area_px / (scale_factor * scale_factor)

        if area_px < self.min_area_px:
            return None  # Region too small

        # Calculate centroid
        y_coords, x_coords = np.where(region_mask)
        centroid = (float(np.mean(x_coords)), float(np.mean(y_coords)))

        # Extract boundary contour
        boundary_vertices = self._extract_boundary(region_mask)

        if boundary_vertices is None or len(boundary_vertices) < 3:
            return None  # Could not extract valid boundary

        # Fast simplification for preview (adaptive applied on finalize)
        simplified = self._simplify_contour(boundary_vertices, self.preview_vertices)

        # Scale vertices back to original image coordinates
        if scale_factor != 1.0:
            inv_scale = 1.0 / scale_factor
            simplified = [(x * inv_scale, y * inv_scale) for x, y in simplified]
            centroid = (centroid[0] * inv_scale, centroid[1] * inv_scale)

        return DetectionResult(
            vertices=simplified,
            mask=region_mask,
            area_px=area_px,
            centroid=centroid,
            clicked_value=clicked_value,
            threshold=threshold
        )

    def detect_with_threshold(
        self,
        image_data: np.ndarray,
        click_x: float,
        click_y: float,
        absolute_threshold: float,
        max_image_size: int = 1024
    ) -> Optional[DetectionResult]:
        """
        Detect region using an absolute threshold value.

        Args:
            image_data: 2D numpy array
            click_x, click_y: Clicked pixel coordinates
            absolute_threshold: Absolute intensity threshold
            max_image_size: Maximum dimension for processing

        Returns:
            DetectionResult or None
        """
        # Handle RGB images
        if len(image_data.shape) == 3:
            image_data = np.mean(image_data, axis=2)

        height, width = image_data.shape

        # Downsample large images for speed
        scale_factor = 1.0
        if max(height, width) > max_image_size:
            scale_factor = max_image_size / max(height, width)
            step_h = max(1, int(1.0 / scale_factor))
            step_w = max(1, int(1.0 / scale_factor))
            image_data = image_data[::step_h, ::step_w]
            height, width = image_data.shape
            click_x = click_x * scale_factor
            click_y = click_y * scale_factor

        click_x = int(np.clip(click_x, 0, width - 1))
        click_y = int(np.clip(click_y, 0, height - 1))

        clicked_value = float(image_data[click_y, click_x])

        # Create binary mask with absolute threshold
        binary_mask = image_data < absolute_threshold

        # Label connected components
        labeled, num_features = label(binary_mask)

        if num_features == 0:
            return None

        clicked_label = labeled[click_y, click_x]

        if clicked_label == 0:
            return None

        region_mask = (labeled == clicked_label)
        area_px = float(np.sum(region_mask))
        if scale_factor != 1.0:
            area_px = area_px / (scale_factor * scale_factor)

        if area_px < self.min_area_px:
            return None

        y_coords, x_coords = np.where(region_mask)
        centroid = (float(np.mean(x_coords)), float(np.mean(y_coords)))

        boundary_vertices = self._extract_boundary(region_mask)

        if boundary_vertices is None or len(boundary_vertices) < 3:
            return None

        # Fast simplification for preview (adaptive applied on finalize)
        simplified = self._simplify_contour(boundary_vertices, self.preview_vertices)

        # Scale vertices back to original image coordinates
        if scale_factor != 1.0:
            inv_scale = 1.0 / scale_factor
            simplified = [(x * inv_scale, y * inv_scale) for x, y in simplified]
            centroid = (centroid[0] * inv_scale, centroid[1] * inv_scale)

        return DetectionResult(
            vertices=simplified,
            mask=region_mask,
            area_px=area_px,
            centroid=centroid,
            clicked_value=clicked_value,
            threshold=absolute_threshold
        )

    def _extract_boundary(self, region_mask: np.ndarray) -> Optional[List[Tuple[float, float]]]:
        """
        Extract boundary pixels from binary mask using contour tracing.

        Args:
            region_mask: Boolean 2D array

        Returns:
            Ordered list of (x, y) boundary coordinates
        """
        # Try to use skimage's marching squares (best quality)
        try:
            from skimage.measure import find_contours
            contours = find_contours(region_mask.astype(float), 0.5)
            if contours:
                # Get the longest contour (main boundary)
                longest = max(contours, key=len)
                # Convert from (row, col) to (x, y)
                return [(float(pt[1]), float(pt[0])) for pt in longest]
        except ImportError:
            pass

        # Fallback: use boundary tracing algorithm
        return self._trace_boundary(region_mask)

    def _trace_boundary(self, region_mask: np.ndarray) -> Optional[List[Tuple[float, float]]]:
        """
        Trace boundary using Moore-Neighbor algorithm.
        Properly handles concave shapes.

        Args:
            region_mask: Boolean 2D array

        Returns:
            Ordered list of (x, y) boundary coordinates
        """
        # Get boundary by XOR with eroded mask
        eroded = binary_erosion(region_mask)
        boundary_mask = region_mask & ~eroded

        # Find starting point (topmost, then leftmost boundary pixel)
        y_coords, x_coords = np.where(boundary_mask)
        if len(x_coords) < 3:
            return None

        # Start from the topmost-leftmost boundary pixel
        start_idx = np.lexsort((x_coords, y_coords))[0]
        start_x, start_y = int(x_coords[start_idx]), int(y_coords[start_idx])

        # Moore neighborhood directions (8-connected, clockwise from left)
        # Directions: 0=left, 1=up-left, 2=up, 3=up-right, 4=right, 5=down-right, 6=down, 7=down-left
        dx = [-1, -1, 0, 1, 1, 1, 0, -1]
        dy = [0, -1, -1, -1, 0, 1, 1, 1]

        height, width = boundary_mask.shape
        contour = [(float(start_x), float(start_y))]

        curr_x, curr_y = start_x, start_y
        # Start searching from direction 0 (left)
        direction = 0

        max_iterations = len(x_coords) * 4  # Safety limit
        iterations = 0

        while iterations < max_iterations:
            iterations += 1

            # Search for next boundary pixel in clockwise order
            found = False
            # Start from (direction + 5) % 8 to search counter-clockwise from where we came
            search_start = (direction + 5) % 8

            for i in range(8):
                search_dir = (search_start + i) % 8
                nx = curr_x + dx[search_dir]
                ny = curr_y + dy[search_dir]

                # Check bounds
                if 0 <= nx < width and 0 <= ny < height:
                    if boundary_mask[ny, nx]:
                        # Found next boundary pixel
                        if nx == start_x and ny == start_y and len(contour) > 2:
                            # Back to start - complete
                            return contour

                        contour.append((float(nx), float(ny)))
                        curr_x, curr_y = nx, ny
                        direction = search_dir
                        found = True
                        break

            if not found:
                # No neighbor found, return what we have
                break

            # Prevent infinite loops on small contours
            if len(contour) > len(x_coords) * 2:
                break

        return contour if len(contour) >= 3 else None

    def finalize_polygon(
        self,
        result: DetectionResult,
        original_shape: Tuple[int, int] = None
    ) -> List[Tuple[float, float]]:
        """
        Finalize polygon with adaptive vertex count.

        Call this after user confirms the detection to get high-quality vertices.
        Re-extracts boundary from mask and applies adaptive RDP simplification.

        Args:
            result: DetectionResult from detect_region or detect_with_threshold
            original_shape: (height, width) of original image for coordinate scaling

        Returns:
            List of (x, y) vertices with adaptive count based on shape complexity
        """
        if result is None:
            return []

        # Re-extract boundary from mask for full resolution
        boundary_vertices = self._extract_boundary(result.mask)

        if boundary_vertices is None or len(boundary_vertices) < 3:
            # Fall back to existing vertices
            return list(result.vertices)

        # Apply adaptive simplification with RDP
        simplified = self._simplify_contour_adaptive(boundary_vertices)

        # Scale vertices back to original image coordinates if mask was downsampled
        if original_shape is not None:
            mask_h, mask_w = result.mask.shape
            orig_h, orig_w = original_shape
            if mask_h != orig_h or mask_w != orig_w:
                scale_x = orig_w / mask_w
                scale_y = orig_h / mask_h
                simplified = [(x * scale_x, y * scale_y) for x, y in simplified]

        return simplified

    def _calculate_perimeter(self, vertices: List[Tuple[float, float]]) -> float:
        """Calculate the perimeter length of a polygon."""
        if len(vertices) < 2:
            return 0.0

        perimeter = 0.0
        n = len(vertices)
        for i in range(n):
            x1, y1 = vertices[i]
            x2, y2 = vertices[(i + 1) % n]
            perimeter += np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        return perimeter

    def _simplify_contour_adaptive(
        self,
        vertices: List[Tuple[float, float]]
    ) -> List[Tuple[float, float]]:
        """
        Simplify contour with adaptive vertex count based on shape complexity.

        Uses perimeter length to determine appropriate vertex count, then applies
        Ramer-Douglas-Peucker algorithm for high-quality simplification.

        Args:
            vertices: List of (x, y) coordinates

        Returns:
            Simplified list of vertices
        """
        n = len(vertices)

        if n <= self.min_vertices:
            return vertices

        # Calculate perimeter to determine appropriate vertex count
        perimeter = self._calculate_perimeter(vertices)

        # Adaptive target: 1 vertex per N pixels of perimeter
        target_vertices = int(perimeter / self.vertices_per_perimeter_px)

        # Clamp to min/max bounds
        target_vertices = max(self.min_vertices, min(self.max_vertices, target_vertices))

        if n <= target_vertices:
            return vertices

        # Use Ramer-Douglas-Peucker for high-quality simplification
        return self._rdp_simplify(vertices, target_vertices)

    def _rdp_simplify(
        self,
        vertices: List[Tuple[float, float]],
        target_vertices: int
    ) -> List[Tuple[float, float]]:
        """
        Simplify polygon using Ramer-Douglas-Peucker algorithm.

        Binary searches for the epsilon value that produces approximately
        the target number of vertices.

        Args:
            vertices: List of (x, y) coordinates
            target_vertices: Target number of vertices

        Returns:
            Simplified list of vertices
        """
        n = len(vertices)

        if n <= target_vertices:
            return vertices

        # Calculate bounding box for epsilon scaling
        xs = [v[0] for v in vertices]
        ys = [v[1] for v in vertices]
        bbox_diag = np.sqrt((max(xs) - min(xs))**2 + (max(ys) - min(ys))**2)

        # Binary search for epsilon that gives target vertex count
        eps_low = 0.0
        eps_high = bbox_diag * 0.5
        best_result = vertices
        best_diff = n

        for _ in range(15):  # Max 15 iterations for convergence
            eps_mid = (eps_low + eps_high) / 2
            result = self._rdp_recursive(vertices, eps_mid)
            result_count = len(result)

            diff = abs(result_count - target_vertices)
            if diff < best_diff:
                best_diff = diff
                best_result = result

            if result_count == target_vertices:
                return result
            elif result_count > target_vertices:
                eps_low = eps_mid
            else:
                eps_high = eps_mid

            # Early exit if close enough
            if diff <= 2:
                break

        return best_result

    def _rdp_recursive(
        self,
        vertices: List[Tuple[float, float]],
        epsilon: float
    ) -> List[Tuple[float, float]]:
        """
        Ramer-Douglas-Peucker recursive implementation.

        Args:
            vertices: List of (x, y) coordinates
            epsilon: Distance threshold

        Returns:
            Simplified list of vertices
        """
        if len(vertices) < 3:
            return vertices

        # Find the point with maximum distance from line
        start = np.array(vertices[0])
        end = np.array(vertices[-1])

        # Handle case where start == end (closed polygon segment)
        line_vec = end - start
        line_len = np.linalg.norm(line_vec)

        max_dist = 0.0
        max_idx = 0

        for i in range(1, len(vertices) - 1):
            point = np.array(vertices[i])

            if line_len < 1e-10:
                # Start and end are same point, use distance to start
                dist = np.linalg.norm(point - start)
            else:
                # Distance from point to line segment
                t = max(0, min(1, np.dot(point - start, line_vec) / (line_len ** 2)))
                projection = start + t * line_vec
                dist = np.linalg.norm(point - projection)

            if dist > max_dist:
                max_dist = dist
                max_idx = i

        # If max distance > epsilon, recursively simplify
        if max_dist > epsilon:
            left = self._rdp_recursive(vertices[:max_idx + 1], epsilon)
            right = self._rdp_recursive(vertices[max_idx:], epsilon)
            return left[:-1] + right
        else:
            return [vertices[0], vertices[-1]]

    def _simplify_contour(
        self,
        vertices: List[Tuple[float, float]],
        max_vertices: int
    ) -> List[Tuple[float, float]]:
        """
        Legacy method: Simplify contour using fast uniform sampling.
        Kept for backwards compatibility.

        Args:
            vertices: List of (x, y) coordinates
            max_vertices: Maximum number of vertices to keep

        Returns:
            Simplified list of vertices
        """
        n = len(vertices)

        if n <= max_vertices:
            return vertices

        # Fast uniform sampling - O(n) complexity
        indices = np.linspace(0, n - 1, max_vertices, dtype=int)
        return [vertices[i] for i in indices]


def get_threshold_range(image_data: np.ndarray) -> Tuple[float, float]:
    """
    Get the intensity range of an image for threshold slider.

    Args:
        image_data: 2D or 3D numpy array

    Returns:
        (min_value, max_value) tuple
    """
    if len(image_data.shape) == 3:
        image_data = np.mean(image_data, axis=2)

    return float(image_data.min()), float(image_data.max())
