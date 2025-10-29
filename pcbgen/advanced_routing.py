"""
Advanced auto-routing algorithms for PCB trace generation
Implements A* pathfinding with obstacle avoidance
"""

import heapq
import math
from collections import defaultdict

class GridRouter:
    """Grid-based A* router with obstacle avoidance"""
    
    def __init__(self, board_width, board_height, grid_resolution=0.1):
        """
        Args:
            board_width: Board width in mm
            board_height: Board height in mm
            grid_resolution: Grid cell size in mm (smaller = more accurate but slower)
        """
        self.width = board_width
        self.height = board_height
        self.resolution = grid_resolution
        self.grid_w = int(board_width / grid_resolution)
        self.grid_h = int(board_height / grid_resolution)
        
        # Track obstacles and existing traces
        self.obstacles = set()  # (grid_x, grid_y) tuples
        self.clearance_zones = set()  # Areas around obstacles
        
    def mm_to_grid(self, x_mm, y_mm):
        """Convert mm coordinates to grid coordinates"""
        return (int(x_mm / self.resolution), int(y_mm / self.resolution))
    
    def grid_to_mm(self, grid_x, grid_y):
        """Convert grid coordinates to mm"""
        return (grid_x * self.resolution, grid_y * self.resolution)
    
    def add_obstacle(self, x_mm, y_mm, width_mm, height_mm, clearance_mm=0.5):
        """Add a rectangular obstacle (e.g., component footprint)"""
        gx, gy = self.mm_to_grid(x_mm, y_mm)
        gw = int(width_mm / self.resolution)
        gh = int(height_mm / self.resolution)
        gc = int(clearance_mm / self.resolution)
        
        # Mark obstacle cells
        for x in range(gx - gc, gx + gw + gc):
            for y in range(gy - gc, gy + gh + gc):
                if 0 <= x < self.grid_w and 0 <= y < self.grid_h:
                    if gc == 0 or x < gx or x >= gx + gw or y < gy or y >= gy + gh:
                        self.clearance_zones.add((x, y))
                    else:
                        self.obstacles.add((x, y))
    
    def heuristic(self, a, b):
        """Manhattan distance heuristic"""
        return abs(a[0] - b[0]) + abs(a[1] - b[1])
    
    def get_neighbors(self, pos):
        """Get valid neighbor cells (8-directional)"""
        x, y = pos
        neighbors = []
        
        # 8 directions: N, S, E, W, NE, NW, SE, SW
        for dx, dy in [(0,1), (0,-1), (1,0), (-1,0), (1,1), (1,-1), (-1,1), (-1,-1)]:
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.grid_w and 0 <= ny < self.grid_h:
                if (nx, ny) not in self.obstacles:
                    # Add cost penalty for clearance zones
                    cost = 1.414 if dx != 0 and dy != 0 else 1.0  # Diagonal cost
                    if (nx, ny) in self.clearance_zones:
                        cost *= 2.0  # Prefer avoiding clearance zones
                    neighbors.append(((nx, ny), cost))
        
        return neighbors
    
    def a_star_route(self, start_mm, end_mm):
        """
        A* pathfinding from start to end
        Returns list of waypoints in mm coordinates, or None if no path found
        """
        start = self.mm_to_grid(*start_mm)
        goal = self.mm_to_grid(*end_mm)
        
        # Check if start/end are valid
        if start in self.obstacles or goal in self.obstacles:
            return None
        
        # Priority queue: (f_score, counter, position)
        counter = 0
        frontier = [(0, counter, start)]
        came_from = {}
        g_score = {start: 0}
        f_score = {start: self.heuristic(start, goal)}
        
        while frontier:
            _, _, current = heapq.heappop(frontier)
            
            if current == goal:
                # Reconstruct path
                path = []
                while current in came_from:
                    path.append(self.grid_to_mm(*current))
                    current = came_from[current]
                path.append(self.grid_to_mm(*start))
                path.reverse()
                
                # Simplify path (remove redundant waypoints)
                return self.simplify_path(path)
            
            for neighbor, move_cost in self.get_neighbors(current):
                tentative_g = g_score[current] + move_cost
                
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f = tentative_g + self.heuristic(neighbor, goal)
                    f_score[neighbor] = f
                    counter += 1
                    heapq.heappush(frontier, (f, counter, neighbor))
        
        return None  # No path found
    
    def simplify_path(self, path, tolerance=0.5):
        """
        Simplify path using Douglas-Peucker algorithm
        Removes unnecessary waypoints while keeping path shape
        """
        if len(path) < 3:
            return path
        
        def perpendicular_distance(point, line_start, line_end):
            """Distance from point to line segment"""
            x0, y0 = point
            x1, y1 = line_start
            x2, y2 = line_end
            
            dx = x2 - x1
            dy = y2 - y1
            
            if dx == 0 and dy == 0:
                return math.sqrt((x0 - x1)**2 + (y0 - y1)**2)
            
            t = max(0, min(1, ((x0 - x1) * dx + (y0 - y1) * dy) / (dx**2 + dy**2)))
            proj_x = x1 + t * dx
            proj_y = y1 + t * dy
            
            return math.sqrt((x0 - proj_x)**2 + (y0 - proj_y)**2)
        
        def simplify_recursive(points, start_idx, end_idx):
            if end_idx <= start_idx + 1:
                return [points[start_idx], points[end_idx]]
            
            # Find point with maximum distance
            max_dist = 0
            max_idx = start_idx
            
            for i in range(start_idx + 1, end_idx):
                dist = perpendicular_distance(points[i], points[start_idx], points[end_idx])
                if dist > max_dist:
                    max_dist = dist
                    max_idx = i
            
            # If max distance is greater than tolerance, recursively simplify
            if max_dist > tolerance:
                left = simplify_recursive(points, start_idx, max_idx)
                right = simplify_recursive(points, max_idx, end_idx)
                return left[:-1] + right
            else:
                return [points[start_idx], points[end_idx]]
        
        simplified = simplify_recursive(path, 0, len(path) - 1)
        return simplified
    
    def mark_trace(self, path, track_width_mm=0.25):
        """Mark a routed trace as an obstacle for future routes"""
        if not path or len(path) < 2:
            return
        
        track_radius = int((track_width_mm / 2) / self.resolution)
        
        for i in range(len(path) - 1):
            x1, y1 = self.mm_to_grid(*path[i])
            x2, y2 = self.mm_to_grid(*path[i + 1])
            
            # Bresenham's line algorithm to mark all cells along trace
            dx = abs(x2 - x1)
            dy = abs(y2 - y1)
            sx = 1 if x1 < x2 else -1
            sy = 1 if y1 < y2 else -1
            err = dx - dy
            
            x, y = x1, y1
            while True:
                # Mark cells around trace
                for ox in range(-track_radius, track_radius + 1):
                    for oy in range(-track_radius, track_radius + 1):
                        gx, gy = x + ox, y + oy
                        if 0 <= gx < self.grid_w and 0 <= gy < self.grid_h:
                            self.clearance_zones.add((gx, gy))
                
                if x == x2 and y == y2:
                    break
                
                e2 = 2 * err
                if e2 > -dy:
                    err -= dy
                    x += sx
                if e2 < dx:
                    err += dx
                    y += sy


class MultiLayerRouter:
    """Route traces across multiple PCB layers with via support"""
    
    def __init__(self, board_width, board_height, num_layers=2):
        self.layers = [GridRouter(board_width, board_height) for _ in range(num_layers)]
        self.num_layers = num_layers
        
    def route_with_vias(self, start_mm, end_mm, preferred_layer=0):
        """
        Route with automatic layer switching via vias
        Returns: (layer_paths, via_positions)
            layer_paths: dict of {layer_id: [waypoints]}
            via_positions: list of (x, y, from_layer, to_layer)
        """
        # Try single layer first
        path = self.layers[preferred_layer].a_star_route(start_mm, end_mm)
        if path:
            return {preferred_layer: path}, []
        
        # Try other layers
        for layer_id in range(self.num_layers):
            if layer_id == preferred_layer:
                continue
            path = self.layers[layer_id].a_star_route(start_mm, end_mm)
            if path:
                return {layer_id: path}, []
        
        # Multi-layer routing (simplified version)
        # In production, this would use 3D A* with via costs
        print("⚠️ Multi-layer routing with vias not yet implemented")
        return None, None


def create_routed_connection_advanced(board, start_pos, end_pos, router, track_width, layer_id=0):
    """
    Replace the simple L-shaped routing with advanced A* routing
    
    Args:
        board: KiCad board object
        start_pos: wxPoint start position
        end_pos: wxPoint end position  
        router: GridRouter or MultiLayerRouter instance
        track_width: Track width in mm
        layer_id: PCB layer (0=F_Cu, 1=B_Cu)
    """
    import pcbnew
    
    # Convert wxPoint to mm
    start_mm = (start_pos.x / 1e6, start_pos.y / 1e6)  # KiCad uses internal units
    end_mm = (end_pos.x / 1e6, end_pos.y / 1e6)
    
    # Get routed path
    path = router.layers[layer_id].a_star_route(start_mm, end_mm) if hasattr(router, 'layers') else router.a_star_route(start_mm, end_mm)
    
    if not path:
        print(f"⚠️ No route found from {start_mm} to {end_mm}, falling back to direct connection")
        # Fallback to direct line
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(start_pos)
        track.SetEnd(end_pos)
        track.SetWidth(pcbnew.FromMM(track_width))
        track.SetLayer(pcbnew.F_Cu if layer_id == 0 else pcbnew.B_Cu)
        board.Add(track)
        return
    
    # Create track segments along path
    layer = pcbnew.F_Cu if layer_id == 0 else pcbnew.B_Cu
    
    for i in range(len(path) - 1):
        x1, y1 = path[i]
        x2, y2 = path[i + 1]
        
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.wxPointMM(x1, y1))
        track.SetEnd(pcbnew.wxPointMM(x2, y2))
        track.SetWidth(pcbnew.FromMM(track_width))
        track.SetLayer(layer)
        board.Add(track)
    
    # Mark this trace as obstacle for future routes
    router.mark_trace(path, track_width) if not hasattr(router, 'layers') else router.layers[layer_id].mark_trace(path, track_width)
    
    print(f"✅ Routed with {len(path)} waypoints on layer {layer_id}")