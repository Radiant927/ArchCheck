"""BIM ingestion — parse an IFC file into the structured building JSON that
core/engine.py's review engine consumes (same schema as demo_building_data.json).
"""
from pathlib import Path

try:
    import ifcopenshell
    IFC_AVAILABLE = True
except ImportError:
    ifcopenshell = None
    IFC_AVAILABLE = False


def available():
    """Whether the ifcopenshell library is installed."""
    return IFC_AVAILABLE


def parse_ifc(path):
    """Parse an IFC file (path or str) into a building data dict.

    Returns a dict shaped like:
    {
      "project_name": ...,
      "building_params": {...},
      "floors": [{"floor_id", "floor_name", "rooms": [...], "fire_zones": [...]}]
    }
    """
    raise NotImplementedError("IFC parsing is not implemented yet.")
