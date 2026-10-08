"""Stable adapter between validated pipeline artifacts and the web dashboard."""

from .adapter import build_dashboard_data, write_dashboard_data

__all__ = ["build_dashboard_data", "write_dashboard_data"]
