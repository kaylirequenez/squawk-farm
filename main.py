"""Entry point for the squawk-farm Kivy app.

This is a minimal placeholder that imports the app package and runs it.
"""

from imslib.core import run
from squawkfarm import build_app

if __name__ == "__main__":
    sm = build_app()
    run(sm)
