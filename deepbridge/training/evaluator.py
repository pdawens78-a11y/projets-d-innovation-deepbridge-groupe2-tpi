"""
training/evaluator.py
======================
Couche 4 — Évaluation du modèle : Dice, AUC, Recall, Precision, F1.
"""
import logging, sys
import numpy as np
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger("evaluator")


@dataclass
class EvalMetrics:
    dice: float
    recall: float        # sensibilité
    precision: float
    f1: float
    auc: float           # AUC-ROC si scores de probabilité disponibles
    tp: int
    fp: int
    fn: int
    tn: int

    def report(self) -> str:
        return (
            f"Dice: {self.dice:.4f} | "
            f"Recall: {self.recall:.4f} | "
            f"Precision: {self.precision:.4f} | "
            f"F1: {self.f1:.4f} | "
            f"AUC: {self.auc:.4f}"
        )


def dice_coefficient(y_true: np.ndarray, y_pred: np.ndarray, smooth: float = 1e-6) -> float:
    """
    Coefficient de Dice (F1 volumétrique).
    Travaille sur des masques binaires aplatis.

    Args:
        y_true: masque de référence (0/1)
        y_pred: masque prédit (0/1)
        smooth: terme de lissage pour éviter la division par zéro

    Returns:
        score Dice ∈ [0, 1]
    """
    y_true_f = y_true.flatten().astype(np.float32)
    y_pred_f = y_pred.flatten().astype(np.float32)
    intersection = (y_true_f * y_pred_f).sum()
    return float((2.0 * intersection + smooth) / (y_true_f.sum() + y_pred_f.sum() + smooth))


def confusion_counts(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[int, int, int, int]:
    """Retourne (TP, FP, FN, TN) depuis deux masques binaires."""
    yt = y_true.flatten().astype(bool)
    yp = y_pred.flatten().astype(bool)
    tp = int((yt & yp).sum())
    fp = int((~yt & yp).sum())
    fn = int((yt & ~yp).sum())
    tn = int((~yt & ~yp).sum())
    return tp, fp, fn, tn


def auc_roc(y_true: np.ndarray, y_scores: np.ndarray, n_thresholds: int = 100) -> float:
    """
    Calcule l'AUC-ROC par méthode des trapèzes sur n_thresholds seuils.

    Args:
        y_true:    masque binaire de référence aplati
        y_scores:  probabilités prédites aplatties ∈ [0, 1]

    Returns:
        AUC ∈ [0, 1]
    """
    yt = y_true.flatten().astype(int)
    ys = y_scores.flatten()

    thresholds = np.linspace(0, 1, n_thresholds)
    tprs, fprs = [], []

    for t in thresholds:
        pred = (ys >= t).astype(int)
        tp   = int(((yt == 1) & (pred == 1)).sum())
        fp   = int(((yt == 0) & (pred == 1)).sum())
        fn   = int(((yt == 1) & (pred == 0)).sum())
        tn   = int(((yt == 0) & (pred == 0)).sum())
        tpr  = tp / (tp + fn + 1e-8)
        fpr  = fp / (fp + tn + 1e-8)
        tprs.append(tpr)
        fprs.append(fpr)

    # Tri par FPR croissant pour intégration trapèze
    sorted_pairs = sorted(zip(fprs, tprs))
    fprs_s = [p[0] for p in sorted_pairs]
    tprs_s = [p[1] for p in sorted_pairs]

    return float(np.trapz(tprs_s, fprs_s))


def evaluate(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_scores: np.ndarray | None = None,
) -> EvalMetrics:
    """
    Évalue la segmentation complète.

    Args:
        y_true:   masque de référence binaire
        y_pred:   masque prédit binaire
        y_scores: probabilités prédites (pour l'AUC, optionnel)

    Returns:
        EvalMetrics
    """
    dice   = dice_coefficient(y_true, y_pred)
    tp, fp, fn, tn = confusion_counts(y_true, y_pred)

    recall    = tp / (tp + fn + 1e-8)
    precision = tp / (tp + fp + 1e-8)
    f1        = 2 * precision * recall / (precision + recall + 1e-8)

    auc = auc_roc(y_true, y_scores) if y_scores is not None else float("nan")

    metrics = EvalMetrics(
        dice=round(dice, 4),
        recall=round(recall, 4),
        precision=round(precision, 4),
        f1=round(f1, 4),
        auc=round(auc, 4) if not np.isnan(auc) else float("nan"),
        tp=tp, fp=fp, fn=fn, tn=tn,
    )

    logger.info(metrics.report())
    return metrics
