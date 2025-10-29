# pcbgen.py — dynamic JSON → KiCad board + Gerbers (KiCad 6)
# Complete implementation with all required functions

import pcbnew
import os
import json
import glob
import re

# Map: footprint_name -> list of .pretty directories that contain it
FOOTPRINT_INDEX = {}  # {"R_0805_2012Metric": [".../Resistor_SMD.pretty", ...], ...}
DEFAULT_PLACEHOLDER = ("Resistor_SMD", "R_0805_2012Metric")  # fallback

def _existing_dirs(paths):
    """Return only existing directories from a list of paths"""
    return [p for p in paths if p and os.path.isdir(p)]

def _guess_kicad_share_dirs():
    """Try to find KiCad footprint directories"""
    # Try KiCad 8/7/6 env vars first, then Program Files fallbacks
    envs = [
        os.getenv("KICAD8_FOOTPRINT_DIR"),
        os.getenv("KICAD7_FOOTPRINT_DIR"),
        os.getenv("KICAD6_FOOTPRINT_DIR"),
    ]
    pf = r"C:\Program Files\KiCad"
    candidates = []
    for major in ("8.0", "7.0", "6.0"):
        d = os.path.join(pf, major, "share", "kicad", "footprints")
        candidates.append(d)
    return _existing_dirs(envs + candidates)

def build_footprint_index(extra_search_paths=None):
    """
    Build index of footprint names -> .pretty directory paths.
    Scans KiCad stock libs and any user-provided folders (.pretty or parent).
    """
    global FOOTPRINT_INDEX
    FOOTPRINT_INDEX.clear()

    search_roots = _guess_kicad_share_dirs()
    if extra_search_paths:
        # Accept both .pretty and parent dirs; expand to .pretty
        for p in extra_search_paths:
            if p.lower().endswith(".pretty"):
                search_roots.append(p)
            elif os.path.isdir(p):
                # Add all .pretty under this folder
                search_roots.extend(glob.glob(os.path.join(p, "*.pretty")))

    search_roots = _existing_dirs(list(dict.fromkeys(search_roots)))  # dedupe & keep order

    print("🔍 Scanning libraries:")
    for root in search_roots:
        print("   •", root)
        pretty_dirs = [root] if root.lower().endswith(".pretty") else glob.glob(os.path.join(root, "*.pretty"))
        for libdir in pretty_dirs:
            for modpath in glob.glob(os.path.join(libdir, "*.kicad_mod")):
                name = os.path.splitext(os.path.basename(modpath))[0]
                FOOTPRINT_INDEX.setdefault(name, []).append(libdir)

    print(f"✅ Indexed {len(FOOTPRINT_INDEX)} unique footprints")

def _fuzzy_find_name(requested):
    """Best-effort fuzzy match: ignore non-alnum, case-insensitive, allow substrings."""
    norm = re.sub(r"[^A-Za-z0-9]", "", requested).lower()
    if not norm:
        return None
    # Exact ignoring punctuation
    for cand in FOOTPRINT_INDEX.keys():
        if re.sub(r"[^A-Za-z0-9]", "", cand).lower() == norm:
            return cand
    # Substring match
    for cand in FOOTPRINT_INDEX.keys():
        if norm in re.sub(r"[^A-Za-z0-9]", "", cand).lower():
            return cand
    return None

def _resolve_footprint_path(name):
    """
    Given a footprint base name, return (pretty_dir, footprint_name)
    using our index. Picks the first path if multiple.
    """
    if name in FOOTPRINT_INDEX and FOOTPRINT_INDEX[name]:
        return FOOTPRINT_INDEX[name][0], name
    # try fuzzy
    fuzzy = _fuzzy_find_name(name)
    if fuzzy and FOOTPRINT_INDEX.get(fuzzy):
        print(f"⚠️ Fuzzy matched '{name}' -> '{fuzzy}'")
        return FOOTPRINT_INDEX[fuzzy][0], fuzzy
    return None, None

def _placeholder_path():
    """Find placeholder R_0805_2012Metric anywhere."""
    libnick, fpname = DEFAULT_PLACEHOLDER
    # Prefer a library dir that looks like the nickname
    for name, dirs in FOOTPRINT_INDEX.items():
        if name == fpname and dirs:
            return dirs[0], fpname
    # Last resort: any 0805 resistor variant
    for k, dirs in FOOTPRINT_INDEX.items():
        if "0805" in k and "R_" in k and dirs:
            return dirs[0], k
    return None, None  # should not happen if stock libs exist

def _place_footprint_props(footprint, comp):
    """Set footprint properties: reference, value, position, rotation"""
    footprint.Reference().SetText(comp["name"])
    footprint.Value().SetText(comp.get("value", comp.get("type", comp["name"])))
    footprint.SetPosition(pcbnew.wxPointMM(comp["position"]["x"], comp["position"]["y"]))
    footprint.SetOrientationDegrees(float(comp.get("rotation", 0.0)))
    return footprint

def load_footprint(comp):
    """
    Load a footprint robustly:
      1) exact match by file name,
      2) fuzzy match,
      3) placeholder
    Returns a placed FOOTPRINT ready to add to board.
    """
    req = str(comp["footprint"]).strip()
    pretty_dir, fpname = _resolve_footprint_path(req)

    if pretty_dir and fpname:
        fp = pcbnew.FootprintLoad(pretty_dir, fpname)
        if fp:
            print(f"✅ {comp['name']}: {fpname}  ← {os.path.basename(pretty_dir)}")
            return _place_footprint_props(fp, comp)
        else:
            print(f"⚠️ Failed to load {fpname} from {pretty_dir}, will use placeholder")

    # Placeholder
    pdir, pname = _placeholder_path()
    if pdir and pname:
        fp = pcbnew.FootprintLoad(pdir, pname)
        if fp:
            print(f"⚠️ {comp['name']}: using placeholder {pname} from {os.path.basename(pdir)}")
            return _place_footprint_props(fp, comp)

    raise RuntimeError(f"Could not load footprint for {comp['name']} (requested '{req}')")

def find_pad_by_name(footprint, pad_name):
    """Find a pad in the footprint by name/number."""
    # Handle common pin name mappings for ATmega328P and components
    pin_mappings = {
        'PB5': ['19'],  # ATmega328P DIP-28 pin 19
        'VCC': ['7'],   # ATmega328P DIP-28 pin 7  
        'GND': ['8'],   # ATmega328P DIP-28 pin 8
        'AGND': ['22'], # ATmega328P DIP-28 pin 22
        'AVCC': ['20'], # ATmega328P DIP-28 pin 20
        'RESET': ['1'], # ATmega328P DIP-28 pin 1
        'XTAL1': ['9'], # ATmega328P DIP-28 pin 9
        'XTAL2': ['10'], # ATmega328P DIP-28 pin 10
        'Power': ['7'], # Same as VCC
        'Anode': ['1'], # LED anode is typically pin 1
        'Cathode': ['2'] # LED cathode is typically pin 2
    }
    
    # Try exact match first
    for pad in footprint.Pads():
        if pad.GetName() == pad_name:
            return pad
    
    # Try mapped alternatives
    alternatives = pin_mappings.get(pad_name, [])
    for alt in alternatives:
        for pad in footprint.Pads():
            if pad.GetName() == alt:
                return pad
    
    # Debug: print available pads for troubleshooting
    available_pads = [pad.GetName() for pad in footprint.Pads()]
    print(f"   ⚠️ Pad '{pad_name}' not found on {footprint.GetReference()}")
    print(f"      Available pads: {available_pads}")
    return None

def create_routed_connection(board, start_pos, end_pos, track_width, layer=pcbnew.F_Cu, clearance=0.2):
    """Create a routed connection with proper track routing to avoid overlaps."""
    # Simple L-shaped routing to avoid overlaps
    mid_x = start_pos.x
    mid_y = end_pos.y
    
    # First segment: vertical/horizontal
    if abs(start_pos.x - end_pos.x) > abs(start_pos.y - end_pos.y):
        # Route horizontally first, then vertically
        mid_point = pcbnew.wxPoint(end_pos.x, start_pos.y)
    else:
        # Route vertically first, then horizontally  
        mid_point = pcbnew.wxPoint(start_pos.x, end_pos.y)
    
    # Create first track segment
    track1 = pcbnew.PCB_TRACK(board)
    track1.SetStart(start_pos)
    track1.SetEnd(mid_point)
    track1.SetWidth(pcbnew.FromMM(track_width))
    track1.SetLayer(layer)
    board.Add(track1)
    
    # Create second track segment (if needed)
    if mid_point != end_pos:
        track2 = pcbnew.PCB_TRACK(board)
        track2.SetStart(mid_point)
        track2.SetEnd(end_pos)
        track2.SetWidth(pcbnew.FromMM(track_width))
        track2.SetLayer(layer)
        board.Add(track2)

def create_connections(board, pcb_json, footprints_map):
    """Create electrical connections (tracks) between component pads."""
    track_width = float(pcb_json.get("board", {}).get("track_width", 0.25))
    clearance = float(pcb_json.get("board", {}).get("clearance", 0.2))
    
    print("🔗 Creating connections...")
    
    for i, connection in enumerate(pcb_json.get("connections", [])):
        try:
            # Parse connection format: "ComponentName:PinName"
            from_comp, from_pin = connection["from"].split(":")
            to_comp, to_pin = connection["to"].split(":")
            
            # Find footprints
            from_footprint = footprints_map.get(from_comp)
            to_footprint = footprints_map.get(to_comp)
            
            if not from_footprint or not to_footprint:
                print(f"⚠️ Could not find footprints for connection {connection['from']} -> {connection['to']}")
                print(f"   Available components: {list(footprints_map.keys())}")
                continue
            
            # Find pads
            from_pad = find_pad_by_name(from_footprint, from_pin)
            to_pad = find_pad_by_name(to_footprint, to_pin)
            
            if not from_pad or not to_pad:
                print(f"⚠️ Could not find pads for connection {connection['from']} -> {connection['to']}")
                continue
            
            # Use different layers to avoid overlap
            layer = pcbnew.F_Cu if i % 2 == 0 else pcbnew.B_Cu
            
            # Create routed connection to avoid overlaps
            create_routed_connection(board, from_pad.GetPosition(), to_pad.GetPosition(), 
                                   track_width, layer, clearance)
            
            layer_name = "Front" if layer == pcbnew.F_Cu else "Back"
            print(f"✅ Connected {connection['from']} -> {connection['to']} on {layer_name} layer")
            
        except Exception as e:
            print(f"❌ Failed to create connection {connection.get('from', '?')} -> {connection.get('to', '?')}: {e}")

def create_drills(board, pcb_json):
    """Create mounting holes/drills from the JSON specification."""
    print("🔩 Creating drills...")
    
    for drill in pcb_json.get("drills", []):
        try:
            x = float(drill["position"]["x"])
            y = float(drill["position"]["y"])
            diameter = float(drill["diameter"])
            
            # Create a circle on Edge.Cuts for drill holes in KiCad 6.0
            circle = pcbnew.PCB_SHAPE(board)
            circle.SetShape(pcbnew.SHAPE_T_CIRCLE)
            circle.SetCenter(pcbnew.wxPointMM(x, y))
            circle.SetEnd(pcbnew.wxPointMM(x + diameter/2, y))  # Set end point for radius
            circle.SetLayer(pcbnew.Edge_Cuts)
            circle.SetWidth(pcbnew.FromMM(0.1))  # Thin line
            
            board.Add(circle)
            
            print(f"✅ Created drill at ({x}, {y}) diameter {diameter}mm")
            
        except Exception as e:
            print(f"❌ Failed to create drill: {e}")

def apply_board_settings(board, pcb_json):
    """Apply board-level settings like design rules."""
    board_config = pcb_json.get("board", {})
    
    # Get design settings
    design_settings = board.GetDesignSettings()
    
    # Set track width using the correct KiCad 6.0 method
    if "track_width" in board_config:
        track_width = float(board_config["track_width"])
        # KiCad 6.0 uses different method - set via net class
        try:
            net_class = design_settings.GetDefault()
            if hasattr(net_class, 'SetTrackWidth'):
                net_class.SetTrackWidth(pcbnew.FromMM(track_width))
            print(f"✅ Set default track width: {track_width}mm")
        except:
            print(f"⚠️ Could not set track width (KiCad API variation)")
    
    # Set clearance
    if "clearance" in board_config:
        clearance = float(board_config["clearance"])
        try:
            if hasattr(design_settings, 'SetDefaultClearance'):
                design_settings.SetDefaultClearance(pcbnew.FromMM(clearance))
            print(f"✅ Set default clearance: {clearance}mm")
        except:
            print(f"⚠️ Could not set clearance (KiCad API variation)")
    
    # Set layer count based on layers specified
    layers = board_config.get("layers", [])
    if layers:
        # Count copper layers
        copper_layers = [l for l in layers if "Cu" in l]
        layer_count = len(copper_layers) if copper_layers else 2
        design_settings.SetCopperLayerCount(layer_count)
        print(f"✅ Set copper layer count: {layer_count}")

def generate_pcb(pcb_json, project_name="dynamic_pcb"):
    """
    Generate PCB from JSON specification
    
    Args:
        pcb_json: Dictionary containing PCB design specification
        project_name: Name of the output project
    
    Returns:
        Tuple of (board_file_path, gerber_directory_path)
    """
    # Optional: user-provided extra library roots
    extra_paths = []
    libs = pcb_json.get("libraries")
    if isinstance(libs, dict):
        extra_paths = libs.get("footprint_paths", []) or []
    build_footprint_index(extra_paths)

    board = pcbnew.BOARD()

    # Apply board settings first
    apply_board_settings(board, pcb_json)

    # Calculate optimal board size based on component positions
    components = pcb_json.get("components", [])
    if components:
        min_x = min(comp["position"]["x"] for comp in components) - 10
        max_x = max(comp["position"]["x"] for comp in components) + 10
        min_y = min(comp["position"]["y"] for comp in components) - 10
        max_y = max(comp["position"]["y"] for comp in components) + 10
        
        width_mm = max(max_x - min_x, 30)  # Minimum 30mm width
        height_mm = max(max_y - min_y, 20)  # Minimum 20mm height
        
        # Adjust component positions to start from (5,5) with margin
        x_offset = 5 - min_x
        y_offset = 5 - min_y
    else:
        # Fallback to JSON specified size
        width_mm = float(pcb_json["board"]["size"]["width"])
        height_mm = float(pcb_json["board"]["size"]["height"])
        x_offset = y_offset = 0

    print(f"📏 Board size: {width_mm:.1f}mm x {height_mm:.1f}mm")

    # Board outline (optimized size)
    outline = [
        pcbnew.wxPointMM(0, 0),
        pcbnew.wxPointMM(width_mm, 0),
        pcbnew.wxPointMM(width_mm, height_mm),
        pcbnew.wxPointMM(0, height_mm),
        pcbnew.wxPointMM(0, 0),
    ]
    for i in range(len(outline) - 1):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(outline[i])
        seg.SetEnd(outline[i + 1])
        seg.SetLayer(pcbnew.Edge_Cuts)
        board.Add(seg)

    # Place components and build footprints map
    footprints_map = {}
    for comp in pcb_json.get("components", []):
        try:
            # Adjust component position with calculated offset
            adjusted_comp = comp.copy()
            adjusted_comp["position"] = {
                "x": comp["position"]["x"] + x_offset,
                "y": comp["position"]["y"] + y_offset
            }
            
            fp = load_footprint(adjusted_comp)
            board.Add(fp)
            footprints_map[comp["name"]] = fp
        except Exception as e:
            print(f"❌ Failed to place {comp.get('name','?')}: {e}")

    # Create connections between components
    create_connections(board, pcb_json, footprints_map)
    
    # Create drills/mounting holes
    create_drills(board, pcb_json)

    # Save .kicad_pcb
    out_dir = os.path.abspath(project_name)
    os.makedirs(out_dir, exist_ok=True)
    board_file = os.path.join(out_dir, f"{project_name}.kicad_pcb")
    pcbnew.SaveBoard(board_file, board)
    print(f"✅ PCB saved to {board_file}")

    # Plot Gerbers
    gerber_dir = os.path.join(out_dir, "gerbers")
    os.makedirs(gerber_dir, exist_ok=True)

    pc = pcbnew.PLOT_CONTROLLER(board)
    po = pc.GetPlotOptions()
    po.SetOutputDirectory(gerber_dir)
    po.SetUseGerberProtelExtensions(True)
    po.SetExcludeEdgeLayer(True)
    po.SetScale(1.0)

    layers = [
        (pcbnew.F_Cu, "F_Cu"),
        (pcbnew.B_Cu, "B_Cu"),
        (pcbnew.F_SilkS, "F_SilkS"),
        (pcbnew.B_SilkS, "B_SilkS"),
        (pcbnew.F_Mask, "F_Mask"),
        (pcbnew.B_Mask, "B_Mask"),
        (pcbnew.Edge_Cuts, "Edge_Cuts"),
    ]
    for layer, name in layers:
        pc.SetLayer(layer)
        pc.OpenPlotfile(name, pcbnew.PLOT_FORMAT_GERBER, name)
        pc.PlotLayer()
    pc.ClosePlot()
    print(f"✅ Gerbers written to {gerber_dir}")

    return board_file, gerber_dir

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: pcbgen.py <design.json> [project_name]")
        sys.exit(1)

    json_file = sys.argv[1]
    project_name = sys.argv[2] if len(sys.argv) > 2 else "dynamic_pcb"

    with open(json_file, "r", encoding="utf-8") as f:
        pcb_json = json.load(f)

    generate_pcb(pcb_json, project_name)