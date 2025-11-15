"""
analytics2map
==============

Tools for converting Google Analytics visitor telemetry into SVG visitor maps.
"""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("analytics2map")
except PackageNotFoundError:  # pragma: no cover - occurs in local dev before install
    __version__ = "0.0.0"

__all__ = ["__version__"]

