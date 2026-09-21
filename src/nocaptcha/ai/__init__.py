"""Init IA."""
from .detector import LocalDetector, Detection
from .ocr import LocalOcr
from .instructions import parse_instruction
from .animated import sample_animated_frames, vote_frames
from .slider import find_slider_gap, find_slider_gap_best, human_track
from .rotate_click import estimate_rotation_angle, click_targets
from .math_solver import solve_math_text
from .pow import solve_altcha, solve_pow_generic
from . import onnx_zoo
from . import dddd

__all__ = ["LocalDetector", "Detection", "LocalOcr", "parse_instruction",
           "sample_animated_frames", "vote_frames", "find_slider_gap", "human_track",
           "estimate_rotation_angle", "click_targets", "solve_math_text",
           "solve_altcha", "solve_pow_generic", "onnx_zoo", "dddd"]
