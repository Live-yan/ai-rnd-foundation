"""Compatibility entrypoint. HTTP controllers live in modules/workbench."""
from .modules.workbench.controller import create_router

__all__ = ["create_router"]
