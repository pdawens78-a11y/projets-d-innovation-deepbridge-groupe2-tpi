"""
segmentation/diameter_measurement.py
======================================
Mesure du diamètre de la carotide par la méthode de la largeur à mi-hauteur
(FWHM) appliquée au profil d'intensité CT le long de sections perpendiculaires
à la ligne centrale.
"""
import logging, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger("diameter_measurement")
