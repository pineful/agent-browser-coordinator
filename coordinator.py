#!/usr/bin/env python3
"""Source-checkout compatibility entry point; installed users use the CLI."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from agent_browser_coordinator import coordinator as implementation
if __name__ == "__main__":
    from agent_browser_coordinator.cli import main
    main()
else:
    sys.modules[__name__] = implementation
