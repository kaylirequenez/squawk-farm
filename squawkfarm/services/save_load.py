"""Saves and loads full garden compositions."""

from squawkfarm.models.project import Project
from squawkfarm.services.loop_engine import LoopEngine


def get_loop_engine(project: Project = Project()) -> LoopEngine:
    return LoopEngine(project.global_settings, project.loops)