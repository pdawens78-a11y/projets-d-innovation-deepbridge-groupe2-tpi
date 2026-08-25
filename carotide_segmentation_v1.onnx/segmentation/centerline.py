"""
segmentation/centerline.py
===========================
Extraction de la ligne centrale (centerline) de la carotide par recherche du
plus court chemin géodésique (Dijkstra) à travers le masque vasculaire segmenté.
"""
import logging, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger("centerline")
