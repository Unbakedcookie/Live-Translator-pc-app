"""PyInstaller entry point for the built app (the package's own __main__ needs `-m`)."""

import sys

from livetranslator.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
