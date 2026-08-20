"""
tests/test_all_layers.py
========================
Tests unitaires pour les 4 couches du pipeline DeepBridge.
Lancez avec : py -m pytest tests/ -v
"""
import sys, shutil, tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Imports couche par couche ────────────────────────────────
from ingestion.organize_dicom_files import (
    md5_suffix, safe_dest, validate, FileRecord, PipelineMetrics, iter_files
)
from ingestion.validate_dataset import validate_series
from ingestion.dicom_csv_matcher import extract_dicom_index

from preprocessing.hu_converter import to_hounsfield, window, convert_series
from preprocessing.resampler import get_spacing_from_dicom
from preprocessing.normalizer import zscore, clahe_slice, normalize

from annotation.nascet_calculator import compute_nascet, evaluate as nascet_evaluate
from annotation.dataset_builder import build_dataset

from training.evaluator import dice_coefficient, confusion_counts, auc_roc, evaluate as eval_metrics


# ────────────────────────────────────────────────────────────
# Fixtures communes
# ────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d)


@pytest.fixture
def mock_ds_valid():
    ds = MagicMock()
    ds.PatientID         = "PAT_001"
    ds.SeriesInstanceUID = "1.2.840.UID.001"
    ds.Modality          = "CT"
    return ds


@pytest.fixture
def volume_3d():
    return np.random.uniform(-200, 400, (32, 64, 64)).astype(np.float32)


@pytest.fixture
def mask_binary():
    m = np.zeros((32, 64, 64), dtype=np.uint8)
    m[10:20, 20:44, 20:44] = 1
    return m


# ════════════════════════════════════════════════════════════
# COUCHE 1 — Ingestion
# ════════════════════════════════════════════════════════════

class TestOrganizeDicomFiles:
    def test_md5_suffix_length(self, tmp_dir):
        p = tmp_dir / "f.dcm"; p.write_bytes(b"x")
        assert len(md5_suffix(p, 8)) == 8

    def test_md5_suffix_deterministic(self, tmp_dir):
        p = tmp_dir / "f.dcm"; p.write_bytes(b"x")
        assert md5_suffix(p) == md5_suffix(p)

    def test_safe_dest_no_collision(self, tmp_dir):
        src = tmp_dir / "a.dcm"; src.write_bytes(b"A" * 100)
        result = safe_dest(tmp_dir / "out", "a.dcm", src)
        assert result == tmp_dir / "out" / "a.dcm"

    def test_safe_dest_collision_adds_suffix(self, tmp_dir):
        src = tmp_dir / "a.dcm"; src.write_bytes(b"A" * 200)
        out = tmp_dir / "out"; out.mkdir()
        existing = out / "a.dcm"; existing.write_bytes(b"B" * 100)
        result = safe_dest(out, "a.dcm", src)
        assert result != existing
        assert "a_" in result.stem

    def test_validate_valid_dataset(self, mock_ds_valid):
        with patch("ingestion.organize_dicom_files.config") as c:
            c.REQUIRED_TAGS = ("PatientID", "SeriesInstanceUID", "Modality")
            ok, reason = validate(mock_ds_valid)
        assert ok and reason == ""

    def test_validate_missing_tag(self):
        ds = MagicMock(); ds.PatientID = ""
        ds.SeriesInstanceUID = "uid"; ds.Modality = "CT"
        with patch("ingestion.organize_dicom_files.config") as c:
            c.REQUIRED_TAGS = ("PatientID", "SeriesInstanceUID", "Modality")
            ok, reason = validate(ds)
        assert not ok and "PatientID" in reason

    def test_iter_files_recursive(self, tmp_dir):
        sub = tmp_dir / "sub"; sub.mkdir()
        (sub / "a.dcm").write_bytes(b""); (tmp_dir / "b.dcm").write_bytes(b"")
        (tmp_dir / ".hidden").write_bytes(b"")
        files = iter_files(tmp_dir)
        assert len(files) == 2

    def test_pipeline_metrics_summary(self):
        m = PipelineMetrics(total_scanned=100, moved=90, errors=10)
        s = m.summary()
        assert s["total_scanned"] == 100
        assert s["moved"] == 90
        assert "elapsed_seconds" in s


class TestValidateDataset:
    def test_empty_series_rejected(self, tmp_dir):
        series_dir = tmp_dir / "PAT_001" / "SERIES_001"
        series_dir.mkdir(parents=True)
        report = validate_series(series_dir)
        assert report.status == "rejected"
        assert "Aucun fichier" in report.reason

    def test_too_few_slices_rejected(self, tmp_dir):
        series_dir = tmp_dir / "PAT_001" / "SERIES_001"
        series_dir.mkdir(parents=True)
        for i in range(3):
            (series_dir / f"s{i:03d}.dcm").write_bytes(b"fake")
        with patch("ingestion.validate_dataset.pydicom.dcmread") as mock_read, \
             patch("ingestion.validate_dataset.config") as c:
            c.MIN_SLICES = 50
            c.MAX_PIXEL_SPACING = 1.5
            report = validate_series(series_dir)
        assert report.status == "rejected"


# ════════════════════════════════════════════════════════════
# COUCHE 2 — Prétraitement
# ════════════════════════════════════════════════════════════

class TestHuConverter:
    def test_to_hounsfield_identity(self):
        arr = np.array([[100, 200], [300, 400]], dtype=np.float32)
        result = to_hounsfield(arr, slope=1.0, intercept=0.0)
        np.testing.assert_array_almost_equal(result, arr)

    def test_to_hounsfield_with_slope(self):
        arr = np.array([[1, 2]], dtype=np.float32)
        result = to_hounsfield(arr, slope=2.0, intercept=10.0)
        np.testing.assert_array_almost_equal(result, np.array([[12, 14]]))

    def test_to_hounsfield_replaces_minus2000(self):
        arr = np.array([[-2000, 100]], dtype=np.float32)
        result = to_hounsfield(arr, slope=1.0, intercept=0.0)
        assert result[0, 0] == 0.0

    def test_window_clips_and_normalizes(self):
        arr = np.array([-500, -100, 0, 200, 400, 800], dtype=np.float32)
        result = window(arr, hu_min=-100, hu_max=400)
        assert result.min() >= 0.0
        assert result.max() <= 1.0

    def test_window_shape_preserved(self, volume_3d):
        result = window(volume_3d)
        assert result.shape == volume_3d.shape


class TestNormalizer:
    def test_zscore_mean_near_zero(self, volume_3d):
        result = zscore(volume_3d)
        assert abs(result.mean()) < 0.01

    def test_zscore_std_near_one(self, volume_3d):
        result = zscore(volume_3d)
        assert abs(result.std() - 1.0) < 0.05

    def test_clahe_output_range(self):
        slc = np.random.uniform(0, 1, (64, 64)).astype(np.float32)
        result = clahe_slice(slc)
        assert result.min() >= 0.0
        assert result.max() <= 1.0

    def test_normalize_shape_preserved(self, volume_3d):
        result = normalize(volume_3d, use_clahe=True)
        assert result.shape == volume_3d.shape

    def test_normalize_no_clahe(self, volume_3d):
        result = normalize(volume_3d, use_clahe=False)
        assert result.shape == volume_3d.shape


# ════════════════════════════════════════════════════════════
# COUCHE 3 — Annotation
# ════════════════════════════════════════════════════════════

class TestNascetCalculator:
    def test_compute_nascet_zero_stenosis(self):
        assert compute_nascet(5.0, 5.0) == 0.0

    def test_compute_nascet_fifty_percent(self):
        assert abs(compute_nascet(2.5, 5.0) - 50.0) < 0.01

    def test_compute_nascet_seventy_percent(self):
        assert abs(compute_nascet(1.5, 5.0) - 70.0) < 0.01

    def test_compute_nascet_invalid_distal(self):
        with pytest.raises(ValueError):
            compute_nascet(1.0, 0.0)

    def test_compute_nascet_invalid_stenosis(self):
        with pytest.raises(ValueError):
            compute_nascet(-1.0, 5.0)

    def test_compute_nascet_stenosis_larger_than_distal_returns_zero(self):
        result = compute_nascet(6.0, 5.0)
        assert result == 0.0

    def test_evaluate_significant_stenosis(self, mask_binary):
        # Réduire le masque à la sténose (coupe 15) pour simuler une forte sténose
        mask_stenosis = mask_binary.copy()
        mask_stenosis[15, :, :] = 0   # coupe sténosée = presque vide
        with patch("annotation.nascet_calculator.config") as c:
            c.NASCT_THRESHOLD = 0.7
            result = nascet_evaluate("PAT_001", "UID_001", mask_binary,
                                     (1.0, 1.0, 1.0), 15, 12)
        assert result.patient_id == "PAT_001"
        assert 0 <= result.nascet_percent <= 100


# ════════════════════════════════════════════════════════════
# COUCHE 4 — Entraînement
# ════════════════════════════════════════════════════════════

class TestEvaluator:
    def test_dice_perfect(self, mask_binary):
        assert dice_coefficient(mask_binary, mask_binary) > 0.999

    def test_dice_zero(self, mask_binary):
        inverse = 1 - mask_binary
        assert dice_coefficient(mask_binary, inverse) < 0.01

    def test_dice_range(self, mask_binary):
        noisy = mask_binary.copy()
        noisy[5:8, 10:15, 10:15] = 1 - noisy[5:8, 10:15, 10:15]
        d = dice_coefficient(mask_binary, noisy)
        assert 0.0 <= d <= 1.0

    def test_confusion_counts_perfect(self, mask_binary):
        tp, fp, fn, tn = confusion_counts(mask_binary, mask_binary)
        assert fp == 0 and fn == 0

    def test_auc_random_near_half(self):
        y_true   = np.random.randint(0, 2, 1000)
        y_scores = np.random.rand(1000)
        auc = auc_roc(y_true, y_scores)
        assert 0.3 <= auc <= 0.7   # proche de 0.5 pour un prédicteur aléatoire

    def test_auc_perfect(self):
        y_true   = np.array([0, 0, 1, 1])
        y_scores = np.array([0.1, 0.2, 0.8, 0.9])
        auc = auc_roc(y_true, y_scores)
        assert auc > 0.9

    def test_evaluate_metrics_fields(self, mask_binary):
        scores = mask_binary.astype(np.float32) * 0.9 + 0.05
        metrics = eval_metrics(mask_binary, mask_binary, scores)
        assert hasattr(metrics, "dice")
        assert hasattr(metrics, "recall")
        assert hasattr(metrics, "auc")
        assert 0 <= metrics.dice <= 1
