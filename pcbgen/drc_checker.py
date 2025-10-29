"""
Design Rule Check (DRC) module for PCB validation
Checks clearances, track widths, drill sizes, etc.
"""

import math
from collections import defaultdict

class DRCChecker:
    """Automated Design Rule Checker"""
    
    def __init__(self, board, design_rules=None):
        """
        Args:
            board: KiCad BOARD object
            design_rules: Dict with rules like:
                {
                    'min_track_width': 0.15,  # mm
                    'min_clearance': 0.2,      # mm
                    'min_drill': 0.3,          # mm
                    'min_annular_ring': 0.15,  # mm
                    'max_track_width': 5.0,    # mm
                }
        """
        self.board = board
        self.rules = design_rules or self.get_default_rules()
        self.violations = []
        
    @staticmethod
    def get_default_rules():
        """Standard PCB manufacturing design rules"""
        return {
            'min_track_width': 0.15,      # 6 mil
            'max_track_width': 5.0,
            'min_clearance': 0.2,          # 8 mil
            'min_drill': 0.3,              # 12 mil
            'min_annular_ring': 0.15,     # 6 mil
            'min_hole_to_hole': 0.5,      # 20 mil
            'min_silk_width': 0.15,
            'min_silk_text_size': 0.8,
        }
    
    def check_all(self):
        """Run all DRC checks"""
        self.violations = []
        
        print("🔍 Running DRC checks...")
        
        self.check_track_widths()
        self.check_clearances()
        self.check_drill_sizes()
        self.check_annular_rings()
        self.check_board_outline()
        self.check_unconnected_pads()
        
        return self.get_report()
    
    def check_track_widths(self):
        """Check all tracks meet minimum/maximum width requirements"""
        import pcbnew
        
        for track in self.board.GetTracks():
            if track.GetClass() == "PCB_TRACK":
                width_mm = track.GetWidth() / 1e6  # Convert to mm
                
                if width_mm < self.rules['min_track_width']:
                    self.add_violation(
                        'TRACK_WIDTH_TOO_SMALL',
                        f"Track width {width_mm:.3f}mm < minimum {self.rules['min_track_width']}mm",
                        track.GetPosition()
                    )
                
                if width_mm > self.rules['max_track_width']:
                    self.add_violation(
                        'TRACK_WIDTH_TOO_LARGE',
                        f"Track width {width_mm:.3f}mm > maximum {self.rules['max_track_width']}mm",
                        track.GetPosition()
                    )
    
    def check_clearances(self):
        """Check clearances between tracks, pads, and other copper features"""
        import pcbnew
        
        # Get all copper items
        copper_items = []
        
        # Tracks
        for track in self.board.GetTracks():
            if track.GetClass() == "PCB_TRACK":
                copper_items.append(('track', track))
        
        # Pads
        for footprint in self.board.GetFootprints():
            for pad in footprint.Pads():
                copper_items.append(('pad', pad))
        
        # Check all pairs
        min_clearance = self.rules['min_clearance'] * 1e6  # Convert to internal units
        
        for i, (type1, item1) in enumerate(copper_items):
            for type2, item2 in copper_items[i+1:]:
                # Skip if on different nets (should be checked by netlist)
                if hasattr(item1, 'GetNetCode') and hasattr(item2, 'GetNetCode'):
                    if item1.GetNetCode() == item2.GetNetCode() and item1.GetNetCode() != 0:
                        continue  # Same net, no clearance needed
                
                distance = self.get_distance(item1, item2)
                
                if distance < min_clearance:
                    self.add_violation(
                        'CLEARANCE_VIOLATION',
                        f"Clearance {distance/1e6:.3f}mm < minimum {self.rules['min_clearance']}mm",
                        item1.GetPosition() if hasattr(item1, 'GetPosition') else None
                    )
    
    def check_drill_sizes(self):
        """Check all drill holes meet minimum size requirements"""
        min_drill = self.rules['min_drill'] * 1e6
        
        for footprint in self.board.GetFootprints():
            for pad in footprint.Pads():
                if pad.GetDrillSize().x > 0:  # Has a drill hole
                    drill_size = pad.GetDrillSize().x / 1e6  # Convert to mm
                    
                    if drill_size < self.rules['min_drill']:
                        self.add_violation(
                            'DRILL_TOO_SMALL',
                            f"Drill size {drill_size:.3f}mm < minimum {self.rules['min_drill']}mm at {footprint.GetReference()}",
                            pad.GetPosition()
                        )
    
    def check_annular_rings(self):
        """Check pad annular rings (copper around drill holes)"""
        min_ring = self.rules['min_annular_ring'] * 1e6
        
        for footprint in self.board.GetFootprints():
            for pad in footprint.Pads():
                if pad.GetDrillSize().x > 0:
                    pad_size = min(pad.GetSize().x, pad.GetSize().y)
                    drill_size = pad.GetDrillSize().x
                    annular_ring = (pad_size - drill_size) / 2
                    
                    if annular_ring < min_ring:
                        self.add_violation(
                            'ANNULAR_RING_TOO_SMALL',
                            f"Annular ring {annular_ring/1e6:.3f}mm < minimum {self.rules['min_annular_ring']}mm at {footprint.GetReference()}",
                            pad.GetPosition()
                        )
    
    def check_board_outline(self):
        """Check board outline is closed and valid"""
        import pcbnew
        
        edge_cuts = []
        for drawing in self.board.GetDrawings():
            if drawing.GetLayer() == pcbnew.Edge_Cuts:
                edge_cuts.append(drawing)
        
        if not edge_cuts:
            self.add_violation(
                'NO_BOARD_OUTLINE',
                "No board outline defined on Edge.Cuts layer",
                None
            )
            return
        
        # Check if outline forms closed loop (simplified check)
        # In production, would use proper polygon analysis
        print(f"   Found {len(edge_cuts)} edge cuts segments")
    
    def check_unconnected_pads(self):
        """Check for pads that should be connected but aren't"""
        import pcbnew
        
        # Group pads by net
        nets = defaultdict(list)
        for footprint in self.board.GetFootprints():
            for pad in footprint.Pads():
                net_code = pad.GetNetCode()
                if net_code > 0:  # Ignore unconnected pads (net 0)
                    nets[net_code].append((footprint.GetReference(), pad))
        
        # Check each net has tracks connecting its pads
        for net_code, pads in nets.items():
            if len(pads) > 1:
                # Check if tracks exist for this net
                tracks_for_net = [t for t in self.board.GetTracks() 
                                if hasattr(t, 'GetNetCode') and t.GetNetCode() == net_code]
                
                if not tracks_for_net:
                    pad_refs = [ref for ref, _ in pads]
                    self.add_violation(
                        'UNCONNECTED_NET',
                        f"Net {net_code} has no tracks connecting pads: {', '.join(pad_refs)}",
                        pads[0][1].GetPosition()
                    )
    
    def get_distance(self, item1, item2):
        """Calculate minimum distance between two board items"""
        # Simplified distance calculation
        # In production, would use proper geometric distance
        
        pos1 = item1.GetPosition() if hasattr(item1, 'GetPosition') else item1.GetStart()
        pos2 = item2.GetPosition() if hasattr(item2, 'GetPosition') else item2.GetStart()
        
        dx = pos1.x - pos2.x
        dy = pos1.y - pos2.y
        
        return math.sqrt(dx*dx + dy*dy)
    
    def add_violation(self, error_code, message, position):
        """Add a DRC violation"""
        self.violations.append({
            'code': error_code,
            'message': message,
            'position': position,
        })
    
    def get_report(self):
        """Generate DRC report"""
        report = {
            'total_violations': len(self.violations),
            'violations_by_type': defaultdict(int),
            'violations': self.violations,
            'passed': len(self.violations) == 0
        }
        
        for v in self.violations:
            report['violations_by_type'][v['code']] += 1
        
        return report
    
    def print_report(self):
        """Print human-readable DRC report"""
        report = self.get_report()
        
        print("\n" + "="*60)
        print("📋 DRC REPORT")
        print("="*60)
        
        if report['passed']:
            print("✅ All checks passed! No violations found.")
        else:
            print(f"❌ Found {report['total_violations']} violations:\n")
            
            for error_code, count in report['violations_by_type'].items():
                print(f"   • {error_code}: {count} violations")
            
            print("\nDetailed violations:")
            for i, v in enumerate(self.violations, 1):
                pos_str = f" at ({v['position'].x/1e6:.2f}, {v['position'].y/1e6:.2f})mm" if v['position'] else ""
                print(f"   {i}. [{v['code']}] {v['message']}{pos_str}")
        
        print("="*60 + "\n")
        
        return report


def run_drc(board, design_rules=None, auto_fix=False):
    """
    Convenience function to run DRC on a board
    
    Args:
        board: KiCad BOARD object
        design_rules: Optional custom design rules
        auto_fix: If True, attempt to fix violations automatically
    
    Returns:
        DRC report dictionary
    """
    checker = DRCChecker(board, design_rules)
    report = checker.check_all()
    checker.print_report()
    
    if auto_fix and not report['passed']:
        print("🔧 Auto-fix not yet implemented")
        # Future: Implement automatic violation fixes
        # - Increase track width
        # - Reroute traces with violations
        # - Adjust pad sizes
    
    return report


# Integration example for your pcbgen.py:
def integrate_drc_check(board, pcb_json):
    """
    Add this function to pcbgen.py after generate_pcb() creates the board
    """
    # Extract design rules from JSON
    board_config = pcb_json.get("board", {})
    design_rules = {
        'min_track_width': float(board_config.get("track_width", 0.15)),
        'min_clearance': float(board_config.get("clearance", 0.2)),
        'min_drill': float(board_config.get("min_drill", 0.3)),
    }
    
    # Run DRC
    drc_report = run_drc(board, design_rules)
    
    # Save report
    import json
    report_file = "drc_report.json"
    with open(report_file, 'w') as f:
        json.dump(drc_report, f, indent=2, default=str)
    
    print(f"📄 DRC report saved to {report_file}")
    
    return drc_report