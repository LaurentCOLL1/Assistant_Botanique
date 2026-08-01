"""Exports des onglets de la version 3."""
from .adaptive_tab import AdaptiveCareTab
from .maintenance_tab import MaintenanceTab
from .photo_tab import PhotoTimelineTab
from .productivity_tabs import CareCalendarTab, GlobalSearchTab, TodayDashboardTab
from .review_tab import CatalogueReviewTab

__all__ = [
    "AdaptiveCareTab",
    "CareCalendarTab",
    "CatalogueReviewTab",
    "GlobalSearchTab",
    "MaintenanceTab",
    "PhotoTimelineTab",
    "TodayDashboardTab",
]
