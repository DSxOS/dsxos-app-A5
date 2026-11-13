import os
import sys

# Make the app modules (flat layout) importable from tests/.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
