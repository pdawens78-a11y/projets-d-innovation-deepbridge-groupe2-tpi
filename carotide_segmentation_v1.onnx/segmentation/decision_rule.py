"""
segmentation/decision_rule.py
===============================
Règle de décision finale à quatre verdicts possibles — "mesure",
"mesure_incertaine", "pas_de_stenose", "non_calculable" — combinant le taux de
sténose calculé, la présence de calcifications et la fiabilité géométrique de
la mesure pour produire un verdict traçable et explicable.
"""
import logging, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger("decision_rule")
