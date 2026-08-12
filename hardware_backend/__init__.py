import logging

try:
    import dwfpy
    from dwfpy import Device
    _dwf_error = None
except ImportError as exc:
    dwfpy = None
    Device = None
    _dwf_error = exc

try:
    import saleae
    from saleae import Saleae
    _saleae_error = None
except ImportError as exc:
    saleae = None
    Saleae = None
    _saleae_error = exc

from .backend import HardwareBackend
from .dwf import DwfHardwareInterface
from .saleae import SaleaeHardwareInterface

__all__ = [
    "HardwareBackend",
    "DwfHardwareInterface",
    "SaleaeHardwareInterface",
    "dwfpy",
    "Device",
    "saleae",
    "Saleae",
    "_dwf_error",
    "_saleae_error",
    "logging",
]
