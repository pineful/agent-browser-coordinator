"""Cooperative ownership of a shared UI resource."""
from .coordinator import Coordinator, Conflict, VERSION
__version__ = VERSION
__all__ = ["Coordinator", "Conflict", "VERSION", "__version__"]
