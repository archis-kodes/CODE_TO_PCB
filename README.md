🚀RUN THE PROJECT
```
python app.py
```
🎯 KEY FEATURES:
1. Advanced Auto-routing

- A* pathfinding with obstacle avoidance
- Grid-based routing with configurable resolution
- Path simplification (Douglas-Peucker)
- Multi-layer support with via planning

2. Automatic DRC

- Track width validation
- Clearance checking between all copper items
- Drill size verification
- Annular ring checks
- Board outline validation
- Unconnected net detection

3. Sophisticated Net Management

- Automatic net classification (power, ground, signal, clock, high-speed)
- Priority-based routing order
- Differential pair detection and handling
- Bus grouping
- Per-class routing rules (width, clearance, impedance)

4. Component Optimization

- Simulated annealing for global optimization
- Force-directed placement for physical constraints
- Automatic orientation optimization
- Grid-based auto-spacing
- Wirelength minimization
