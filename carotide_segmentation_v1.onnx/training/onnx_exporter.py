# Non utilisé en production depuis le passage à TotalSegmentator — conservé pour référence et couvert par les tests unitaires.
"""
training/onnx_exporter.py
==========================
Couche 4 — Export du modèle PyTorch → ONNX pour déploiement C#/.NET.
"""
import logging, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger("onnx_exporter")


def export(
    model,                          # torch.nn.Module entraîné
    output_path: Path = config.MODEL_OUTPUT,
    input_shape: tuple = (1, 1, 96, 96, 96),   # (batch, channels, Z, H, W)
    opset: int = config.ONNX_OPSET,
    dynamic_axes: dict | None = None,
) -> Path:
    """
    Exporte un modèle PyTorch en ONNX.

    Args:
        model:        modèle PyTorch en mode eval()
        output_path:  chemin de sortie .onnx
        input_shape:  forme du tenseur d'entrée
        opset:        version ONNX opset (17 recommandé pour C#)
        dynamic_axes: axes dynamiques (batch size, dimensions spatiales)

    Returns:
        chemin du fichier ONNX créé
    """
    try:
        import torch
    except ImportError:
        raise RuntimeError("PyTorch requis pour l'export ONNX. pip install torch")

    try:
        import onnx
    except ImportError:
        raise RuntimeError("ONNX requis pour l'export. pip install onnx")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    model.eval()
    dummy_input = torch.zeros(input_shape, dtype=torch.float32)

    if dynamic_axes is None:
        dynamic_axes = {
            "input":  {0: "batch_size"},
            "output": {0: "batch_size"},
        }

    logger.info("Export ONNX — opset %d → %s", opset, output_path)

    torch.onnx.export(
        model,
        dummy_input,
        str(output_path),
        opset_version=opset,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes=dynamic_axes,
        export_params=True,
        do_constant_folding=True,
    )

    # Vérification de l'intégrité du modèle exporté
    onnx_model = onnx.load(str(output_path))
    onnx.checker.check_model(onnx_model)

    size_mb = output_path.stat().st_size / 1_048_576
    logger.info("Modèle ONNX validé — %.1f Mo — %s", size_mb, output_path.name)

    return output_path


def verify_inference(model_path: Path, input_shape: tuple = (1, 1, 96, 96, 96)) -> np.ndarray:
    """
    Vérifie que l'inférence ONNX fonctionne via onnxruntime.
    Utile pour valider avant le déploiement C#.

    Args:
        model_path:  chemin vers le fichier .onnx
        input_shape: forme du tenseur de test

    Returns:
        tableau numpy des prédictions
    """
    try:
        import onnxruntime as ort
    except ImportError:
        raise RuntimeError("onnxruntime requis. pip install onnxruntime")

    session = ort.InferenceSession(str(model_path))
    dummy   = np.random.randn(*input_shape).astype(np.float32)
    result  = session.run(None, {"input": dummy})

    logger.info("Inférence ONNX OK — sortie shape : %s", result[0].shape)
    return result[0]


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Vérification inférence ONNX")
    p.add_argument("model_path", type=Path, help="Chemin vers le fichier .onnx")
    a = p.parse_args()
    verify_inference(a.model_path)
