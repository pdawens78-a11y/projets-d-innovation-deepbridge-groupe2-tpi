"""
segmentation/totalsegmentator_runner.py
=========================================
Segmentation du volume CT par TotalSegmentator (tâche "headneck_bones_vessels"),
en vue d'isoler les structures osseuses et vasculaires de la région cervicale
nécessaires au calcul du degré de sténose carotidienne.
"""
import logging, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger("totalsegmentator_runner")
