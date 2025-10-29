"""
Main runner script for PCB generation with all advanced features
Run this script to generate a PCB from design.json
"""

import json
import os
import sys

# Import all the modules
try:
    from pcbgen import (
        generate_pcb, 
        build_footprint_index, 
        load_footprint,
        find_pad_by_name,
        create_drills,
        apply_board_settings
    )
    from advanced_routing import GridRouter, MultiLayerRouter, create_routed_connection_advanced
    from drc_checker import DRCChecker, run_drc
    from net_manager import NetManager, create_net_aware_routing
    from component_optimizer import ComponentOptimizer, optimize_component_layout
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure all module files are in the same directory:")
    print("  - pcbgen.py")
    print("  - advanced_routing.py")
    print("  - drc_checker.py")
    print("  - net_manager.py")
    print("  - component_optimizer.py")
    sys.exit(1)

import pcbnew


def generate_pcb_enhanced(pcb_json, project_name="dynamic_pcb", optimize=True, run_drc_check=True, use_advanced_routing=False):
    """
    Enhanced PCB generation with all advanced features
    
    Args:
        pcb_json: JSON design specification
        project_name: Output project name
        optimize: Whether to optimize component placement
        run_drc_check: Whether to run design rule checks
        use_advanced_routing: Use A* routing instead of simple L-shaped
    """
    
    print("\n" + "="*70)
    print("🚀 ADVANCED PCB GENERATOR - STARTING")
    print("="*70)
    
    # ========================================================================
    # STEP 1: COMPONENT OPTIMIZATION (if enabled)
    # ========================================================================
    if optimize:
        print("\n" + "="*70)
        print("STEP 1: COMPONENT PLACEMENT OPTIMIZATION")
        print("="*70)
        pcb_json = optimize_component_layout(pcb_json, method='both')
    else:
        print("\n⏭️  Skipping optimization (disabled)")
    
    # ========================================================================
    # STEP 2: BUILD FOOTPRINT INDEX
    # ========================================================================
    print("\n" + "="*70)
    print("STEP 2: FOOTPRINT LIBRARY INDEXING")
    print("="*70)
    
    extra_paths = []
    libs = pcb_json.get("libraries")
    if isinstance(libs, dict):
        extra_paths = libs.get("footprint_paths", []) or []
    build_footprint_index(extra_paths)
    
    # ========================================================================
    # STEP 3: CREATE BOARD AND APPLY SETTINGS
    # ========================================================================
    print("\n" + "="*70)
    print("STEP 3: BOARD INITIALIZATION")
    print("="*70)
    
    board = pcbnew.BOARD()
    apply_board_settings(board, pcb_json)
    
    # ========================================================================
    # STEP 4: CALCULATE BOARD SIZE
    # ========================================================================
    components = pcb_json.get("components", [])
    if components:
        min_x = min(comp["position"]["x"] for comp in components) - 10
        max_x = max(comp["position"]["x"] for comp in components) + 10
        min_y = min(comp["position"]["y"] for comp in components) - 10
        max_y = max(comp["position"]["y"] for comp in components) + 10
        
        width_mm = max(max_x - min_x, 30)
        height_mm = max(max_y - min_y, 20)
        
        x_offset = 5 - min_x
        y_offset = 5 - min_y
    else:
        width_mm = float(pcb_json["board"]["size"]["width"])
        height_mm = float(pcb_json["board"]["size"]["height"])
        x_offset = y_offset = 0
    
    print(f"📏 Board dimensions: {width_mm:.1f}mm × {height_mm:.1f}mm")
    print(f"📍 Component offset: ({x_offset:.1f}, {y_offset:.1f})mm")
    
    # ========================================================================
    # STEP 5: CREATE BOARD OUTLINE
    # ========================================================================
    print("\n" + "="*70)
    print("STEP 4: BOARD OUTLINE")
    print("="*70)
    
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
        seg.SetWidth(pcbnew.FromMM(0.15))
        board.Add(seg)
    
    print(f"✅ Board outline created: 4 edges")
    
    # ========================================================================
    # STEP 6: PLACE COMPONENTS
    # ========================================================================
    print("\n" + "="*70)
    print("STEP 5: COMPONENT PLACEMENT")
    print("="*70)
    
    footprints_map = {}
    for comp in components:
        try:
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
    
    print(f"✅ Placed {len(footprints_map)}/{len(components)} components")
    
    # ========================================================================
    # STEP 7: INITIALIZE ROUTER (if using advanced routing)
    # ========================================================================
    router = None
    if use_advanced_routing:
        print("\n" + "="*70)
        print("STEP 6: ADVANCED ROUTING INITIALIZATION")
        print("="*70)
        
        router = GridRouter(width_mm, height_mm, grid_resolution=0.1)
        
        # Add component footprints as obstacles
        for comp_name, fp in footprints_map.items():
            bbox = fp.GetBoundingBox()
            pos = fp.GetPosition()
            router.add_obstacle(
                pos.x / 1e6,  # Convert to mm
                pos.y / 1e6,
                bbox.GetWidth() / 1e6,
                bbox.GetHeight() / 1e6,
                clearance_mm=0.5
            )
        
        print(f"✅ Router initialized with {len(footprints_map)} obstacles")
    
    # ========================================================================
    # STEP 8: CREATE CONNECTIONS
    # ========================================================================
    print("\n" + "="*70)
    print("STEP 7: ELECTRICAL CONNECTIONS & ROUTING")
    print("="*70)
    
    if use_advanced_routing and router:
        # Use advanced A* routing
        print("🔀 Using A* pathfinding algorithm...")
        track_width = float(pcb_json.get("board", {}).get("track_width", 0.25))
        
        for i, connection in enumerate(pcb_json.get("connections", [])):
            try:
                from_comp, from_pin = connection["from"].split(":")
                to_comp, to_pin = connection["to"].split(":")
                
                from_footprint = footprints_map.get(from_comp)
                to_footprint = footprints_map.get(to_comp)
                
                if not from_footprint or not to_footprint:
                    print(f"⚠️  Skipping {connection['from']} → {connection['to']}: component not found")
                    continue
                
                from_pad = find_pad_by_name(from_footprint, from_pin)
                to_pad = find_pad_by_name(to_footprint, to_pin)
                
                if not from_pad or not to_pad:
                    print(f"⚠️  Skipping {connection['from']} → {connection['to']}: pad not found")
                    continue
                
                # Use A* routing
                layer_id = i % 2  # Alternate layers
                create_routed_connection_advanced(
                    board, 
                    from_pad.GetPosition(), 
                    to_pad.GetPosition(),
                    router,
                    track_width,
                    layer_id
                )
                
                print(f"✅ Routed: {connection['from']} → {connection['to']}")
                
            except Exception as e:
                print(f"❌ Routing failed for {connection.get('from', '?')} → {connection.get('to', '?')}: {e}")
    
    else:
        # Use net-aware routing with simple L-shaped traces
        print("🔀 Using net-aware routing with L-shaped traces...")
        try:
            net_mgr = create_net_aware_routing(board, pcb_json, footprints_map)
            print(f"✅ Created {len(pcb_json.get('connections', []))} connections")
        except Exception as e:
            print(f"❌ Net-aware routing failed: {e}")
            print("   Falling back to basic connection creation...")
            
            # Fallback: simple track creation
            from pcbgen import create_connections
            create_connections(board, pcb_json, footprints_map)
    
    # ========================================================================
    # STEP 9: CREATE DRILLS/MOUNTING HOLES
    # ========================================================================
    print("\n" + "="*70)
    print("STEP 8: MOUNTING HOLES")
    print("="*70)
    
    create_drills(board, pcb_json)
    
    # ========================================================================
    # STEP 10: SAVE PCB FILE
    # ========================================================================
    print("\n" + "="*70)
    print("STEP 9: SAVING PCB FILE")
    print("="*70)
    
    out_dir = os.path.abspath(project_name)
    os.makedirs(out_dir, exist_ok=True)
    board_file = os.path.join(out_dir, f"{project_name}.kicad_pcb")
    
    try:
        pcbnew.SaveBoard(board_file, board)
        print(f"✅ PCB saved: {board_file}")
    except Exception as e:
        print(f"❌ Failed to save PCB: {e}")
        return None, None
    
    # ========================================================================
    # STEP 11: RUN DRC CHECKS (if enabled)
    # ========================================================================
    if run_drc_check:
        print("\n" + "="*70)
        print("STEP 10: DESIGN RULE CHECK (DRC)")
        print("="*70)
        
        try:
            design_rules = {
                'min_track_width': float(pcb_json.get("board", {}).get("track_width", 0.15)),
                'min_clearance': float(pcb_json.get("board", {}).get("clearance", 0.2)),
                'min_drill': float(pcb_json.get("board", {}).get("min_drill", 0.3)),
            }
            
            drc_report = run_drc(board, design_rules)
            
            # Save DRC report
            drc_file = os.path.join(out_dir, "drc_report.json")
            with open(drc_file, 'w') as f:
                json.dump(drc_report, f, indent=2, default=str)
            
            print(f"📄 DRC report saved: {drc_file}")
            
        except Exception as e:
            print(f"⚠️  DRC check failed: {e}")
    else:
        print("\n⏭️  Skipping DRC check (disabled)")
    
    # ========================================================================
    # STEP 12: GENERATE GERBERS
    # ========================================================================
    print("\n" + "="*70)
    print("STEP 11: GERBER FILE GENERATION")
    print("="*70)
    
    gerber_dir = os.path.join(out_dir, "gerbers")
    os.makedirs(gerber_dir, exist_ok=True)
    
    try:
        pc = pcbnew.PLOT_CONTROLLER(board)
        po = pc.GetPlotOptions()
        po.SetOutputDirectory(gerber_dir)
        po.SetUseGerberProtelExtensions(True)
        po.SetExcludeEdgeLayer(True)
        po.SetScale(1.0)
        po.SetUseAuxOrigin(False)
        po.SetMirror(False)
        po.SetNegative(False)
        
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
        print(f"✅ Gerber files generated: {gerber_dir}")
        print(f"   - {len(layers)} layers exported")
        
    except Exception as e:
        print(f"❌ Gerber generation failed: {e}")
        gerber_dir = None
    
    # ========================================================================
    # FINAL SUMMARY
    # ========================================================================
    print("\n" + "="*70)
    print("🎉 PCB GENERATION COMPLETE!")
    print("="*70)
    print(f"📦 Project: {project_name}")
    print(f"📁 Output directory: {out_dir}")
    print(f"📐 Board size: {width_mm:.1f}mm × {height_mm:.1f}mm")
    print(f"🔌 Components: {len(footprints_map)}")
    print(f"🔗 Connections: {len(pcb_json.get('connections', []))}")
    if gerber_dir:
        print(f"📄 Gerbers: {gerber_dir}")
    print("="*70 + "\n")
    
    return board_file, gerber_dir


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Advanced PCB Generator - Create PCBs from JSON',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pcb_generator.py design.json my_board
  python run_pcb_generator.py design.json my_board --optimize --drc
  python run_pcb_generator.py design.json my_board --advanced-routing
  python run_pcb_generator.py design.json my_board --no-optimize --no-drc
        """
    )
    
    parser.add_argument('json_file', help='Input JSON design file (e.g., design.json)')
    parser.add_argument('project_name', nargs='?', default='generated_pcb',
                       help='Output project name (default: generated_pcb)')
    parser.add_argument('--optimize', action='store_true', default=True,
                       help='Enable component placement optimization (default: enabled)')
    parser.add_argument('--no-optimize', action='store_true',
                       help='Disable component placement optimization')
    parser.add_argument('--drc', action='store_true', default=True,
                       help='Run design rule checks (default: enabled)')
    parser.add_argument('--no-drc', action='store_true',
                       help='Skip DRC checks')
    parser.add_argument('--advanced-routing', action='store_true',
                       help='Use A* pathfinding for routing (experimental)')
    
    args = parser.parse_args()
    
    # Check if JSON file exists
    if not os.path.exists(args.json_file):
        print(f"❌ Error: File not found: {args.json_file}")
        sys.exit(1)
    
    # Load JSON design
    print(f"📖 Loading design from: {args.json_file}")
    try:
        with open(args.json_file, "r", encoding="utf-8") as f:
            pcb_json = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        sys.exit(1)
    
    # Determine settings
    optimize = args.optimize and not args.no_optimize
    run_drc_check = args.drc and not args.no_drc
    
    # Generate PCB
    try:
        board_file, gerber_dir = generate_pcb_enhanced(
            pcb_json,
            project_name=args.project_name,
            optimize=optimize,
            run_drc_check=run_drc_check,
            use_advanced_routing=args.advanced_routing
        )
        
        if board_file:
            print(f"\n✅ SUCCESS! Open your PCB in KiCad:")
            print(f"   {board_file}")
            return gerber_dir
        else:
            print(f"\n❌ PCB generation failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
