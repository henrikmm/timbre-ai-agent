"""Allow python -m timbre without importing the CLI into the core engine."""

from timbre.cli import main

raise SystemExit(main())
