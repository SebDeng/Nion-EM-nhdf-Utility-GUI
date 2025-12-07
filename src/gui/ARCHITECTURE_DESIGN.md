# Two-Tab System Architecture Design

## Overview
Clean separation of Preview and Processing modes to avoid circular imports and initialization issues.

## Key Design Principles
1. **No Circular Imports**: Modules only import downward in the hierarchy
2. **Lazy Initialization**: Components created only when needed
3. **Signal-Based Communication**: Use Qt signals instead of direct references
4. **Independent Modes**: Preview and Processing modes are self-contained

## Component Hierarchy

```
WorkspaceMainWindow
    ├── ModeManager (NEW - central coordinator)
    │   ├── Preview Mode
    │   │   ├── WorkspaceWidget (existing multi-panel viewer)
    │   │   ├── AnalysisToolbar
    │   │   └── AnalysisResults Panel
    │   └── Processing Mode
    │       ├── ProcessingWidget (NEW - 3-panel layout)
    │       ├── ProcessingToolbar
    │       └── Snapshot Manager
    └── Shared Components
        ├── FileBrowserDock
        ├── MetadataDock
        └── File Menu (with Export)
```

## Implementation Strategy

### Phase 1: Mode Manager Foundation
- Create `mode_manager.py` as central coordinator
- Handles tab switching without circular imports
- Lazy initialization of modes

### Phase 2: Preview Mode Enhancements
- Keep existing WorkspaceWidget
- Add analysis toolbar below main toolbar
- Add dockable analysis results panel
- Move export to File menu

### Phase 3: Processing Mode
- Create new ProcessingWidget with fixed 3-panel layout
- Original panel (immutable)
- Live Preview panel
- Snapshots panel
- Add processing toolbar

## Signal Flow
```
User Action → ModeManager → Signal → Target Mode → Update UI
```

## File Structure
```
src/gui/
├── mode_manager.py         # NEW: Central coordinator
├── preview_mode/           # NEW: Directory for preview components
│   ├── __init__.py
│   ├── analysis_toolbar.py
│   └── analysis_panel.py
├── processing_mode/        # NEW: Directory for processing components
│   ├── __init__.py
│   ├── processing_widget.py
│   ├── processing_toolbar.py
│   └── snapshot_manager.py
└── workspace_main_window.py  # Modified: Uses ModeManager
```

## Key Differences from Previous Attempt
1. **ModeManager**: Central coordinator prevents circular imports
2. **Directory Structure**: Separate directories for each mode
3. **Lazy Loading**: Modes initialized only when first accessed
4. **No Cross-References**: Modes communicate only through ModeManager signals
5. **Simpler Initialization**: No deferred initialization or timers needed