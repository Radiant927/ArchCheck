"""BIM ingestion facade — parse + model-QA in one pass.

Re-exports the extraction layer (bim/extractor) and the quality-validation layer
(bim/qa_validator). Kept as `bim.parser` so existing callers (`from bim.parser
import parse_ifc, build_review_data`) keep working unchanged.
"""
import ifcopenshell

from bim.extractor import parse_model, build_review_data, available
from bim.qa_validator import validate_model


def parse_ifc(path, max_floors=None, max_rooms_per_floor=None):
    """Open an IFC, extract its structure, and attach a model-usability QA report.

    Returns the same structure dict as before plus a ``qa`` key:
    ``{score, fatal, checks, stats}`` (see bim/qa_validator.validate_model).
    """
    m = ifcopenshell.open(str(path))
    struct = parse_model(m, path, max_floors, max_rooms_per_floor)
    struct["qa"] = validate_model(m, struct)
    return struct


__all__ = ["parse_ifc", "parse_model", "build_review_data", "validate_model", "available"]
