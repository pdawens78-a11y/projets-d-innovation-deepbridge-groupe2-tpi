"""
tests/test_pipeline.py
======================
Tests unitaires du pipeline DeepBridge.
Lancez avec : py -m pytest tests/ -v
"""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Imports des modules à tester
# ---------------------------------------------------------------------------
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from organize_dicom_files import (
    md5_suffix,
    safe_destination,
    validate_dicom,
    FileRecord,
    PipelineMetrics,
    iter_files,
    write_report,
)
from analyse_results import (
    count_direct_subdirs,
    count_dcm_recursive,
    scans_per_patient,
    dcm_per_series,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir():
    """Dossier temporaire supprimé après chaque test."""
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d)


@pytest.fixture
def mock_dataset_valid():
    """Dataset DICOM valide simulé."""
    ds = MagicMock()
    ds.PatientID         = "PAT_001"
    ds.SeriesInstanceUID = "1.2.840.UID.001"
    ds.Modality          = "CT"
    # Simule hasattr() correctement
    ds.__contains__ = lambda self, item: True
    return ds


@pytest.fixture
def mock_dataset_missing_tag():
    """Dataset DICOM avec PatientID manquant."""
    ds = MagicMock()
    ds.PatientID         = ""       # vide
    ds.SeriesInstanceUID = "1.2.840.UID.002"
    ds.Modality          = "CT"
    return ds


# ---------------------------------------------------------------------------
# Tests — utilitaires
# ---------------------------------------------------------------------------

class TestMd5Suffix:
    def test_returns_string(self, tmp_dir):
        p = tmp_dir / "test.dcm"
        p.write_bytes(b"dummy")
        result = md5_suffix(p)
        assert isinstance(result, str)

    def test_length_respected(self, tmp_dir):
        p = tmp_dir / "test.dcm"
        p.write_bytes(b"dummy")
        assert len(md5_suffix(p, length=6)) == 6
        assert len(md5_suffix(p, length=12)) == 12

    def test_deterministic(self, tmp_dir):
        p = tmp_dir / "test.dcm"
        p.write_bytes(b"dummy")
        assert md5_suffix(p) == md5_suffix(p)


class TestSafeDestination:
    def test_no_collision(self, tmp_dir):
        source = tmp_dir / "source.dcm"
        source.write_bytes(b"A" * 100)
        dest = safe_destination(tmp_dir / "out", "source.dcm", source)
        assert dest == tmp_dir / "out" / "source.dcm"

    def test_same_size_returns_original_dest(self, tmp_dir):
        """Doublon exact → même destination (source sera supprimée)."""
        source = tmp_dir / "source.dcm"
        source.write_bytes(b"A" * 100)
        dest_dir = tmp_dir / "out"
        dest_dir.mkdir()
        existing = dest_dir / "source.dcm"
        existing.write_bytes(b"B" * 100)  # même taille, contenu différent… mais taille identique = doublon
        result = safe_destination(dest_dir, "source.dcm", source)
        assert result == existing

    def test_real_collision_gets_suffix(self, tmp_dir):
        """Collision réelle (même nom, tailles différentes) → suffixe hash ajouté."""
        source = tmp_dir / "source.dcm"
        source.write_bytes(b"A" * 200)
        dest_dir = tmp_dir / "out"
        dest_dir.mkdir()
        existing = dest_dir / "source.dcm"
        existing.write_bytes(b"B" * 100)  # taille différente → vraie collision
        result = safe_destination(dest_dir, "source.dcm", source)
        assert result != existing
        assert result.stem.startswith("source_")


# ---------------------------------------------------------------------------
# Tests — validation DICOM
# ---------------------------------------------------------------------------

class TestValidateDicom:
    def test_valid_dataset(self, mock_dataset_valid):
        with patch("organize_dicom_files.config") as mock_config:
            mock_config.REQUIRED_TAGS = ("PatientID", "SeriesInstanceUID", "Modality")
            is_valid, reason = validate_dicom(mock_dataset_valid)
        assert is_valid is True
        assert reason == ""

    def test_missing_patient_id(self, mock_dataset_missing_tag):
        with patch("organize_dicom_files.config") as mock_config:
            mock_config.REQUIRED_TAGS = ("PatientID", "SeriesInstanceUID", "Modality")
            is_valid, reason = validate_dicom(mock_dataset_missing_tag)
        assert is_valid is False
        assert "PatientID" in reason


# ---------------------------------------------------------------------------
# Tests — métriques
# ---------------------------------------------------------------------------

class TestPipelineMetrics:
    def test_initial_values(self):
        m = PipelineMetrics()
        assert m.total_scanned == 0
        assert m.moved == 0
        assert m.errors == 0

    def test_summary_keys(self):
        m = PipelineMetrics(total_scanned=10, moved=8, errors=2)
        s = m.summary()
        assert "total_scanned" in s
        assert "moved" in s
        assert "errors" in s
        assert "elapsed_seconds" in s
        assert "throughput_files_per_s" in s

    def test_elapsed_positive(self):
        m = PipelineMetrics()
        assert m.elapsed() >= 0


# ---------------------------------------------------------------------------
# Tests — scan de fichiers
# ---------------------------------------------------------------------------

class TestIterFiles:
    def test_finds_dcm_files(self, tmp_dir):
        (tmp_dir / "a.dcm").write_bytes(b"")
        (tmp_dir / "b.dcm").write_bytes(b"")
        files = iter_files(tmp_dir)
        assert len(files) == 2

    def test_ignores_hidden_files(self, tmp_dir):
        (tmp_dir / ".hidden.dcm").write_bytes(b"")
        (tmp_dir / "visible.dcm").write_bytes(b"")
        files = iter_files(tmp_dir)
        assert len(files) == 1

    def test_recursive(self, tmp_dir):
        sub = tmp_dir / "sub"
        sub.mkdir()
        (sub / "c.dcm").write_bytes(b"")
        (tmp_dir / "a.dcm").write_bytes(b"")
        files = iter_files(tmp_dir)
        assert len(files) == 2

    def test_empty_folder(self, tmp_dir):
        assert iter_files(tmp_dir) == []


# ---------------------------------------------------------------------------
# Tests — rapport CSV
# ---------------------------------------------------------------------------

class TestWriteReport:
    def test_creates_csv(self, tmp_dir):
        records = [
            FileRecord(
                timestamp="2024-01-01T00:00:00Z",
                source_path="/src/a.dcm",
                destination_path="/out/PAT/UID/a.dcm",
                patient_id="PAT_001",
                series_uid="1.2.840",
                modality="CT",
                status="moved",
                reason="",
                file_size_bytes=1024,
            )
        ]
        with patch("organize_dicom_files.config") as mock_config:
            mock_config.REPORT_FILENAME = "pipeline_report.csv"
            mock_config.REPORT_FIELDS = [
                "timestamp", "source_path", "destination_path",
                "patient_id", "series_uid", "modality",
                "status", "reason", "file_size_bytes",
            ]
            path = write_report(records, tmp_dir)

        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "PAT_001" in content
        assert "moved" in content


# ---------------------------------------------------------------------------
# Tests — analyse_results
# ---------------------------------------------------------------------------

class TestAnalyseResults:
    def test_count_direct_subdirs(self, tmp_dir):
        (tmp_dir / "PAT_001").mkdir()
        (tmp_dir / "PAT_002").mkdir()
        (tmp_dir / "_quarantine").mkdir()  # doit être ignoré
        assert count_direct_subdirs(tmp_dir) == 2

    def test_count_dcm_recursive(self, tmp_dir):
        sub = tmp_dir / "PAT_001" / "SERIES_001"
        sub.mkdir(parents=True)
        (sub / "slice_001.dcm").write_bytes(b"")
        (sub / "slice_002.dcm").write_bytes(b"")
        (sub / ".hidden.dcm").write_bytes(b"")  # ignoré
        assert count_dcm_recursive(tmp_dir) == 2

    def test_scans_per_patient(self, tmp_dir):
        pat = tmp_dir / "PAT_001"
        (pat / "SERIES_001").mkdir(parents=True)
        (pat / "SERIES_002").mkdir(parents=True)
        result = scans_per_patient(tmp_dir)
        assert result["PAT_001"] == 2

    def test_dcm_per_series(self, tmp_dir):
        series = tmp_dir / "PAT_001" / "SERIES_001"
        series.mkdir(parents=True)
        (series / "a.dcm").write_bytes(b"")
        (series / "b.dcm").write_bytes(b"")
        result = dcm_per_series(tmp_dir)
        assert result["SERIES_001"] == 2

    def test_nonexistent_path(self):
        assert count_direct_subdirs(Path("/does/not/exist")) == 0
        assert count_dcm_recursive(Path("/does/not/exist")) == 0
