"""
Advanced net management for PCB design
Handles net classes, priority routing, differential pairs, and bus routing
"""

from collections import defaultdict
from enum import Enum

class NetClass(Enum):
    """Net classification for routing priorities"""
    POWER = "power"
    GROUND = "ground"
    SIGNAL = "signal"
    CLOCK = "clock"
    HIGH_SPEED = "high_speed"
    DIFFERENTIAL = "differential"
    ANALOG = "analog"

class NetManager:
    """Manage all nets (electrical connections) in the PCB"""
    
    def __init__(self, board):
        self.board = board
        self.nets = {}  # {net_name: Net object}
        self.net_classes = defaultdict(list)  # {NetClass: [net_names]}
        self.differential_pairs = []  # [(net_p, net_n)]
        self.bus_groups = []  # [[net1, net2, ...]]
        
    def create_net(self, net_name, net_class=NetClass.SIGNAL, properties=None):
        """Create a new net with classification and properties"""
        net = Net(net_name, net_class, properties or {})
        self.nets[net_name] = net
        self.net_classes[net_class].append(net_name)
        return net
    
    def add_differential_pair(self, net_p, net_n, impedance=100, tolerance=0.1):
        """
        Define a differential pair (e.g., USB D+/D-, LVDS)
        
        Args:
            net_p: Positive net name
            net_n: Negative net name
            impedance: Target differential impedance in ohms
            tolerance: Maximum length mismatch in mm
        """
        self.differential_pairs.append({
            'positive': net_p,
            'negative': net_n,
            'impedance': impedance,
            'max_length_mismatch': tolerance,
            'coupled': True
        })
        
        # Mark nets as high-speed differential
        if net_p in self.nets:
            self.nets[net_p].net_class = NetClass.DIFFERENTIAL
        if net_n in self.nets:
            self.nets[net_n].net_class = NetClass.DIFFERENTIAL
    
    def add_bus(self, net_names, bus_name=None):
        """Group related nets into a bus (e.g., data bus, address bus)"""
        self.bus_groups.append({
            'name': bus_name or f"Bus_{len(self.bus_groups)}",
            'nets': net_names,
            'route_together': True
        })
    
    def assign_net_to_connection(self, connection, pcb_json):
        """
        Intelligently assign net names based on connection type
        Auto-detects power, ground, clocks, etc.
        """
        from_comp, from_pin = connection["from"].split(":")
        to_comp, to_pin = connection["to"].split(":")
        
        # Auto-detect net class
        net_class = NetClass.SIGNAL
        net_name = connection.get("net", f"{from_comp}_{from_pin}_to_{to_comp}_{to_pin}")
        
        # Power net detection
        if any(keyword in net_name.upper() for keyword in ['VCC', 'VDD', 'POWER', '+5V', '+3V3', '+12V']):
            net_class = NetClass.POWER
        
        # Ground net detection
        elif any(keyword in net_name.upper() for keyword in ['GND', 'GROUND', 'VSS']):
            net_class = NetClass.GROUND
        
        # Clock detection
        elif any(keyword in net_name.upper() for keyword in ['CLK', 'CLOCK', 'OSC']):
            net_class = NetClass.CLOCK
        
        # High-speed detection
        elif any(keyword in net_name.upper() for keyword in ['USB', 'HDMI', 'PCIE', 'SATA', 'ETH']):
            net_class = NetClass.HIGH_SPEED
        
        # Create or get existing net
        if net_name not in self.nets:
            properties = self.get_net_properties(net_class)
            self.create_net(net_name, net_class, properties)
        
        return net_name, net_class
    
    def get_net_properties(self, net_class):
        """Get routing properties based on net class"""
        properties = {
            NetClass.POWER: {
                'track_width': 0.5,      # Wider for power
                'clearance': 0.3,
                'priority': 1,           # Route first
                'via_size': 0.8,
            },
            NetClass.GROUND: {
                'track_width': 0.5,
                'clearance': 0.3,
                'priority': 1,
                'via_size': 0.8,
                'pour_copper': True,     # Use copper pour/plane
            },
            NetClass.SIGNAL: {
                'track_width': 0.25,
                'clearance': 0.2,
                'priority': 5,
                'via_size': 0.6,
            },
            NetClass.CLOCK: {
                'track_width': 0.25,
                'clearance': 0.3,        # More clearance for EMI
                'priority': 2,           # Route early
                'via_size': 0.6,
                'length_matching': True,
            },
            NetClass.HIGH_SPEED: {
                'track_width': 0.2,
                'clearance': 0.3,
                'priority': 2,
                'via_size': 0.5,
                'impedance_control': True,
                'length_matching': True,
            },
            NetClass.DIFFERENTIAL: {
                'track_width': 0.15,
                'clearance': 0.3,
                'priority': 2,
                'via_size': 0.5,
                'coupled_spacing': 0.15, # Spacing between pair
                'impedance_control': True,
            },
            NetClass.ANALOG: {
                'track_width': 0.25,
                'clearance': 0.4,        # Keep away from digital
                'priority': 3,
                'via_size': 0.6,
                'separate_ground': True,
            }
        }
        return properties.get(net_class, properties[NetClass.SIGNAL])
    
    def get_routing_order(self):
        """Return nets sorted by routing priority"""
        sorted_nets = []
        
        # Sort by priority (lower number = higher priority)
        for net_name, net in self.nets.items():
            priority = net.properties.get('priority', 5)
            sorted_nets.append((priority, net_name, net))
        
        sorted_nets.sort(key=lambda x: x[0])
        return [(name, net) for _, name, net in sorted_nets]
    
    def apply_to_kicad_board(self, board):
        """Apply net classes and properties to KiCad board"""
        import pcbnew
        
        # Get netclass manager
        design_settings = board.GetDesignSettings()
        
        for net_name, net in self.nets.items():
            # Find or create KiCad net
            netinfo = board.FindNet(net_name)
            if not netinfo:
                netinfo = pcbnew.NETINFO_ITEM(board, net_name)
                board.Add(netinfo)
            
            # Apply net class settings
            # Note: KiCad 6.0 API for netclasses varies, this is simplified
            props = net.properties
            
            print(f"   Net: {net_name} [{net.net_class.value}] - " +
                  f"width={props.get('track_width')}mm, " +
                  f"clearance={props.get('clearance')}mm")


class Net:
    """Represents a single electrical net"""
    
    def __init__(self, name, net_class=NetClass.SIGNAL, properties=None):
        self.name = name
        self.net_class = net_class
        self.properties = properties or {}
        self.connections = []  # [(from_pad, to_pad)]
        self.total_length = 0.0  # mm
        
    def add_connection(self, from_pad, to_pad):
        """Add a connection to this net"""
        self.connections.append((from_pad, to_pad))
    
    def calculate_length(self):
        """Calculate total routed length"""
        # Would sum up all track segments on this net
        pass


class LengthMatcher:
    """Match trace lengths for timing-critical signals"""
    
    def __init__(self, target_length_mm, tolerance_mm=0.5):
        self.target_length = target_length_mm
        self.tolerance = tolerance_mm
        
    def add_meander(self, path, additional_length_needed):
        """
        Add serpentine/meander pattern to increase trace length
        
        Args:
            path: List of waypoints [(x, y), ...]
            additional_length_needed: How much more length to add (mm)
        
        Returns:
            Modified path with meanders
        """
        if additional_length_needed <= 0:
            return path
        
        # Find longest straight segment to add meander
        max_segment_idx = 0
        max_segment_length = 0
        
        for i in range(len(path) - 1):
            dx = path[i+1][0] - path[i][0]
            dy = path[i+1][1] - path[i][1]
            length = (dx**2 + dy**2)**0.5
            if length > max_segment_length:
                max_segment_length = length
                max_segment_idx = i
        
        # Insert meander pattern
        start = path[max_segment_idx]
        end = path[max_segment_idx + 1]
        
        meander_path = self.generate_meander(start, end, additional_length_needed)
        
        # Replace straight segment with meander
        new_path = path[:max_segment_idx] + meander_path + path[max_segment_idx+2:]
        return new_path
    
    def generate_meander(self, start, end, target_length, amplitude=1.0):
        """
        Generate serpentine meander pattern
        
        Args:
            start: Starting point (x, y)
            end: Ending point (x, y)
            target_length: Desired total length
            amplitude: Meander wave amplitude in mm
        """
        import math
        
        # Direction vector
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        direct_length = math.sqrt(dx**2 + dy**2)
        
        if target_length <= direct_length:
            return [start, end]
        
        # Calculate number of meander cycles needed
        extra_length = target_length - direct_length
        
        # Perpendicular direction for meander
        perp_x = -dy / direct_length if direct_length > 0 else 0
        perp_y = dx / direct_length if direct_length > 0 else 0
        
        # Generate meander points
        num_cycles = int(extra_length / (4 * amplitude)) + 1
        points = [start]
        
        for i in range(1, num_cycles * 2):
            t = i / (num_cycles * 2)
            
            # Base position along line
            base_x = start[0] + dx * t
            base_y = start[1] + dy * t
            
            # Offset perpendicular
            offset = amplitude * (1 if i % 2 == 1 else -1)
            points.append((
                base_x + perp_x * offset,
                base_y + perp_y * offset
            ))
        
        points.append(end)
        return points


def create_net_aware_routing(board, pcb_json, footprints_map):
    """
    Enhanced connection creation with net management
    Replace create_connections() in pcbgen.py with this
    """
    import pcbnew
    
    # Initialize net manager
    net_mgr = NetManager(board)
    
    # Process connections and create nets
    print("🌐 Building net topology...")
    
    connection_by_net = defaultdict(list)
    
    for connection in pcb_json.get("connections", []):
        net_name, net_class = net_mgr.assign_net_to_connection(connection, pcb_json)
        connection['net'] = net_name
        connection_by_net[net_name].append(connection)
    
    # Detect differential pairs
    for net_name in list(net_mgr.nets.keys()):
        if net_name.endswith('_P') or net_name.endswith('+'):
            # Look for matching negative net
            neg_name = net_name.replace('_P', '_N').replace('+', '-')
            if neg_name in net_mgr.nets:
                net_mgr.add_differential_pair(net_name, neg_name)
                print(f"   🔗 Differential pair detected: {net_name} / {neg_name}")
    
    # Apply net classes to board
    net_mgr.apply_to_kicad_board(board)
    
    # Route in priority order
    print("\n🔌 Routing connections by priority...")
    
    for net_name, net in net_mgr.get_routing_order():
        connections = connection_by_net[net_name]
        props = net.properties
        
        print(f"\n   Routing net: {net_name} ({len(connections)} connections)")
        
        for conn in connections:
            try:
                from_comp, from_pin = conn["from"].split(":")
                to_comp, to_pin = conn["to"].split(":")
                
                from_footprint = footprints_map.get(from_comp)
                to_footprint = footprints_map.get(to_comp)
                
                if not from_footprint or not to_footprint:
                    continue
                
                from_pad = find_pad_by_name(from_footprint, from_pin)
                to_pad = find_pad_by_name(to_footprint, to_pin)
                
                if not from_pad or not to_pad:
                    continue
                
                # Use net-specific track width
                track_width = props.get('track_width', 0.25)
                
                # Create track with proper net assignment
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(from_pad.GetPosition())
                track.SetEnd(to_pad.GetPosition())
                track.SetWidth(pcbnew.FromMM(track_width))
                track.SetLayer(pcbnew.F_Cu)
                
                # Assign to net
                netinfo = board.FindNet(net_name)
                if netinfo:
                    track.SetNet(netinfo)
                
                board.Add(track)
                
                print(f"      ✓ {conn['from']} → {conn['to']} (width={track_width}mm)")
                
            except Exception as e:
                print(f"      ✗ Failed: {e}")
    
    return net_mgr


# Helper function (add to pcbgen.py)
def find_pad_by_name(footprint, pad_name):
    """Find pad - same as in original code"""
    pin_mappings = {
        'PB5': ['19'], 'VCC': ['7'], 'GND': ['8'],
        'Power': ['7'], 'Anode': ['1'], 'Cathode': ['2']
    }
    
    for pad in footprint.Pads():
        if pad.GetName() == pad_name:
            return pad
    
    alternatives = pin_mappings.get(pad_name, [])
    for alt in alternatives:
        for pad in footprint.Pads():
            if pad.GetName() == alt:
                return pad
    
    return None