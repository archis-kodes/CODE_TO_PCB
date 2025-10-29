"""
Automatic component placement and optimization
Uses simulated annealing and force-directed algorithms
"""

import random
import math
from copy import deepcopy

class ComponentOptimizer:
    """Optimize component placement to minimize trace length and improve layout"""
    
    def __init__(self, components, connections, board_size):
        """
        Args:
            components: List of component dicts with positions
            connections: List of connection dicts
            board_size: (width, height) in mm
        """
        self.components = components
        self.connections = connections
        self.board_width, self.board_height = board_size
        
        # Build connection graph
        self.conn_graph = self.build_connection_graph()
        
    def build_connection_graph(self):
        """Build adjacency graph of component connections"""
        graph = {}
        
        for comp in self.components:
            graph[comp['name']] = []
        
        for conn in self.connections:
            from_comp = conn['from'].split(':')[0]
            to_comp = conn['to'].split(':')[0]
            
            if from_comp in graph:
                graph[from_comp].append(to_comp)
            if to_comp in graph:
                graph[to_comp].append(from_comp)
        
        return graph
    
    def calculate_total_wirelength(self, components=None):
        """Calculate total Manhattan distance of all connections"""
        if components is None:
            components = self.components
        
        comp_positions = {c['name']: (c['position']['x'], c['position']['y']) 
                         for c in components}
        
        total = 0
        for conn in self.connections:
            from_comp = conn['from'].split(':')[0]
            to_comp = conn['to'].split(':')[0]
            
            if from_comp in comp_positions and to_comp in comp_positions:
                x1, y1 = comp_positions[from_comp]
                x2, y2 = comp_positions[to_comp]
                total += abs(x2 - x1) + abs(y2 - y1)
        
        return total
    
    def check_overlap(self, components):
        """Check if any components overlap (simplified check)"""
        margin = 5  # mm minimum spacing
        
        for i, c1 in enumerate(components):
            for c2 in components[i+1:]:
                dx = abs(c1['position']['x'] - c2['position']['x'])
                dy = abs(c1['position']['y'] - c2['position']['y'])
                
                if dx < margin and dy < margin:
                    return True
        
        return False
    
    def optimize_simulated_annealing(self, iterations=1000, temp_start=100, temp_end=0.1):
        """
        Optimize placement using simulated annealing
        
        Returns:
            Optimized component list
        """
        print(f"🎯 Optimizing placement with simulated annealing ({iterations} iterations)...")
        
        current = deepcopy(self.components)
        current_cost = self.calculate_total_wirelength(current)
        best = deepcopy(current)
        best_cost = current_cost
        
        temp = temp_start
        cooling_rate = (temp_start / temp_end) ** (1.0 / iterations)
        
        for i in range(iterations):
            # Generate neighbor solution
            neighbor = deepcopy(current)
            
            # Random move: pick a component and perturb its position
            comp_idx = random.randint(0, len(neighbor) - 1)
            move_dist = 5 * (temp / temp_start)  # Smaller moves as temp decreases
            
            neighbor[comp_idx]['position']['x'] += random.uniform(-move_dist, move_dist)
            neighbor[comp_idx]['position']['y'] += random.uniform(-move_dist, move_dist)
            
            # Keep within bounds
            neighbor[comp_idx]['position']['x'] = max(5, min(self.board_width - 5, 
                                                              neighbor[comp_idx]['position']['x']))
            neighbor[comp_idx]['position']['y'] = max(5, min(self.board_height - 5,
                                                              neighbor[comp_idx]['position']['y']))
            
            # Check if valid (no overlaps)
            if self.check_overlap(neighbor):
                continue
            
            neighbor_cost = self.calculate_total_wirelength(neighbor)
            delta = neighbor_cost - current_cost
            
            # Accept or reject
            if delta < 0 or random.random() < math.exp(-delta / temp):
                current = neighbor
                current_cost = neighbor_cost
                
                if current_cost < best_cost:
                    best = deepcopy(current)
                    best_cost = current_cost
            
            # Cool down
            temp *= cooling_rate
            
            if i % 100 == 0:
                print(f"   Iteration {i}: cost={current_cost:.1f}mm, best={best_cost:.1f}mm, temp={temp:.2f}")
        
        improvement = ((self.calculate_total_wirelength() - best_cost) / 
                      self.calculate_total_wirelength() * 100)
        
        print(f"✅ Optimization complete: {improvement:.1f}% wirelength reduction")
        return best
    
    def optimize_force_directed(self, iterations=100, damping=0.9):
        """
        Force-directed placement - components connected by traces attract,
        unconnected components repel
        """
        print(f"🎯 Optimizing with force-directed algorithm ({iterations} iterations)...")
        
        components = deepcopy(self.components)
        
        for iteration in range(iterations):
            forces = {c['name']: {'x': 0, 'y': 0} for c in components}
            
            # Attractive forces (connections)
            for conn in self.connections:
                from_comp = conn['from'].split(':')[0]
                to_comp = conn['to'].split(':')[0]
                
                comp1 = next((c for c in components if c['name'] == from_comp), None)
                comp2 = next((c for c in components if c['name'] == to_comp), None)
                
                if comp1 and comp2:
                    dx = comp2['position']['x'] - comp1['position']['x']
                    dy = comp2['position']['y'] - comp1['position']['y']
                    dist = math.sqrt(dx**2 + dy**2)
                    
                    if dist > 0:
                        # Spring force: F = k * distance
                        k_spring = 0.1
                        force = k_spring * dist
                        
                        fx = force * dx / dist
                        fy = force * dy / dist
                        
                        forces[from_comp]['x'] += fx
                        forces[from_comp]['y'] += fy
                        forces[to_comp]['x'] -= fx
                        forces[to_comp]['y'] -= fy
            
            # Repulsive forces (avoid overlaps)
            for i, c1 in enumerate(components):
                for c2 in components[i+1:]:
                    dx = c2['position']['x'] - c1['position']['x']
                    dy = c2['position']['y'] - c1['position']['y']
                    dist = math.sqrt(dx**2 + dy**2)
                    
                    if dist < 15:  # Repel if too close
                        k_repel = 50
                        force = k_repel / (dist**2 + 0.1)
                        
                        fx = force * dx / (dist + 0.1)
                        fy = force * dy / (dist + 0.1)
                        
                        forces[c1['name']]['x'] -= fx
                        forces[c1['name']]['y'] -= fy
                        forces[c2['name']]['x'] += fx
                        forces[c2['name']]['y'] += fy
            
            # Apply forces
            for comp in components:
                comp['position']['x'] += forces[comp['name']]['x'] * damping
                comp['position']['y'] += forces[comp['name']]['y'] * damping
                
                # Keep within bounds
                comp['position']['x'] = max(5, min(self.board_width - 5, comp['position']['x']))
                comp['position']['y'] = max(5, min(self.board_height - 5, comp['position']['y']))
            
            if iteration % 20 == 0:
                cost = self.calculate_total_wirelength(components)
                print(f"   Iteration {iteration}: wirelength={cost:.1f}mm")
        
        final_cost = self.calculate_total_wirelength(components)
        initial_cost = self.calculate_total_wirelength()
        improvement = ((initial_cost - final_cost) / initial_cost * 100)
        
        print(f"✅ Force-directed complete: {improvement:.1f}% wirelength reduction")
        return components
    
    def optimize_orientation(self, components):
        """
        Optimize component orientations to reduce trace crossings
        Tests 0°, 90°, 180°, 270° for each component
        """
        print("🔄 Optimizing component orientations...")
        
        best_components = deepcopy(components)
        best_cost = self.calculate_total_wirelength(best_components)
        
        for comp in components:
            # Try different rotations
            original_rotation = comp.get('rotation', 0)
            best_rotation = original_rotation
            
            for rotation in [0, 90, 180, 270]:
                comp['rotation'] = rotation
                cost = self.calculate_total_wirelength(components)
                
                if cost < best_cost:
                    best_cost = cost
                    best_rotation = rotation
            
            comp['rotation'] = best_rotation
        
        print(f"✅ Orientation optimization complete")
        return components
    
    def auto_space_components(self, grid_spacing=10):
        """
        Arrange components in a grid pattern with proper spacing
        Good starting point before optimization
        """
        print(f"📐 Auto-spacing components (grid={grid_spacing}mm)...")
        
        components = deepcopy(self.components)
        
        # Calculate grid dimensions
        num_components = len(components)
        cols = math.ceil(math.sqrt(num_components))
        rows = math.ceil(num_components / cols)
        
        # Place on grid
        for i, comp in enumerate(components):
            row = i // cols
            col = i % cols
            
            comp['position']['x'] = 10 + col * grid_spacing
            comp['position']['y'] = 10 + row * grid_spacing
        
        print(f"✅ Components arranged in {rows}x{cols} grid")
        return components


def optimize_component_layout(pcb_json, method='simulated_annealing'):
    """
    Main function to optimize component placement
    Add this to pcbgen.py before placing components
    
    Args:
        pcb_json: PCB JSON specification
        method: 'simulated_annealing', 'force_directed', or 'both'
    
    Returns:
        Optimized pcb_json with updated component positions
    """
    components = pcb_json.get('components', [])
    connections = pcb_json.get('connections', [])
    board_size = (
        float(pcb_json['board']['size']['width']),
        float(pcb_json['board']['size']['height'])
    )
    
    if not components or not connections:
        print("⚠️ No components or connections to optimize")
        return pcb_json
    
    optimizer = ComponentOptimizer(components, connections, board_size)
    
    print(f"\n📊 Initial wirelength: {optimizer.calculate_total_wirelength():.1f}mm")
    
    # Choose optimization method
    if method == 'simulated_annealing':
        optimized = optimizer.optimize_simulated_annealing(iterations=1000)
    elif method == 'force_directed':
        optimized = optimizer.optimize_force_directed(iterations=100)
    elif method == 'both':
        # Start with force-directed, then fine-tune with SA
        temp = optimizer.optimize_force_directed(iterations=50)
        optimizer.components = temp
        optimized = optimizer.optimize_simulated_annealing(iterations=500)
    else:
        # Just auto-space
        optimized = optimizer.auto_space_components()
    
    # Optimize orientations
    optimized = optimizer.optimize_orientation(optimized)
    
    # Update JSON
    pcb_json['components'] = optimized
    
    print(f"📊 Final wirelength: {optimizer.calculate_total_wirelength(optimized):.1f}mm\n")
    
    return pcb_json