"""Exports des onglets de la version 3."""
from .adaptive_tab import AdaptiveCareTab
from .advanced_ecosystem_tab import AdvancedEcosystemTab
from .collection_intelligence_tab import CollectionIntelligenceTab
from .maintenance_tab import MaintenanceTab
from .photo_tab import PhotoTimelineTab
from .productivity_tabs import CareCalendarTab, GlobalSearchTab, TodayDashboardTab
from .review_tab import CatalogueReviewTab

__all__ = [
    "AdaptiveCareTab",
    "AdvancedEcosystemTab",
    "CareCalendarTab",
    "CatalogueReviewTab",
    "CollectionIntelligenceTab",
    "GlobalSearchTab",
    "MaintenanceTab",
    "PhotoTimelineTab",
    "TodayDashboardTab",
]
