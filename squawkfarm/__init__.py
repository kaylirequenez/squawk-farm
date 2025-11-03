"""
Squawk Farm app package.

This package contains:
- Kivy app/bootstrap code (app.py)
- Screens (screens/)
- Logic/services (services/)
- Data models (models/)
"""

from .app import build_app  # so you can do: from squawkfarm import build_app

__all__ = ["build_app"]
