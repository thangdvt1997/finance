"""pattern-render: ve anh kich ban (PNG) tu nen + annotation JSON. Doc lap, khong phu thuoc engine/DB."""
from .render import render_signal, render_png_bytes
from .schema import validate_annotations, SchemaError

__all__ = ["render_signal", "render_png_bytes", "validate_annotations", "SchemaError"]
