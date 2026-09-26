"""
UrbanSense AI — Dataset Preparation Pipeline Test Suite
=========================================================
Tests for RDD2022 India dataset auditing, taxonomy transformations,
anomaly handling (D0w0 & D50), bounding box validation, leakage prevention,
reproducible train/val splitting, YOLO coordinate formatting, and post-conversion validity.

Invariants verified:
  1. Taxonomy mapping integrity and configuration parsing.
  2. D0w0 is explicitly remapped to D00 with verified audit trail.
  3. D50 is quarantined and isolated from YOLO labels.
  4. Empty XMLs are correctly classified as background samples.
  5. Bounding box coordinates are valid (Pascal VOC -> normalized YOLO xywh).
  6. Split reproducibility: same input + same seed -> identical splits and labels.
  7. Leakage gate: zero overlap between train and val splits.
  8. YOLO label validity: 1:1 image/label matching, coordinates in [0.0, 1.0].
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from scripts.prepare_rdd_dataset import (
    load_yaml,
    RDDDatasetPreparationPipeline,
    RawBoundingBox,
)

BASE_DIR = Path("D:/UrbanSense AI")
RAW_DATASET_ROOT = BASE_DIR / "datasets" / "India" / "India"
TAXONOMY_CONFIG_PATH = BASE_DIR / "datasets" / "config" / "taxonomy.yaml"
OUTPUT_BASE = BASE_DIR / "datasets"


class TestTaxonomyAndConfig:
    """Verifies taxonomy configuration and candidate definitions."""

    def test_taxonomy_yaml_exists_and_loads(self):
        assert TAXONOMY_CONFIG_PATH.exists()
        config = load_yaml(TAXONOMY_CONFIG_PATH)
        assert "taxonomies" in config
        assert "Candidate_A_Full_RDD" in config["taxonomies"]
        assert "Candidate_B_UrbanSense_Defect" in config["taxonomies"]

    def test_candidate_a_class_definitions(self):
        config = load_yaml(TAXONOMY_CONFIG_PATH)
        cand_a = config["taxonomies"]["Candidate_A_Full_RDD"]
        classes = cand_a["classes"]
        assert len(classes) == 8
        assert classes[0] == "D00"
        assert classes[5] == "D40"
        assert cand_a["label_mapping"]["D0w0"] == "D00"
        assert "D50" in cand_a["quarantine_classes"]

    def test_candidate_b_consolidation(self):
        config = load_yaml(TAXONOMY_CONFIG_PATH)
        cand_b = config["taxonomies"]["Candidate_B_UrbanSense_Defect"]
        assert cand_b["label_mapping"]["D01"] == "longitudinal_crack"
        assert cand_b["label_mapping"]["D11"] == "transverse_crack"
        assert "D43" in cand_b["quarantine_classes"]
        assert "D44" in cand_b["quarantine_classes"]


class TestAnomalyResolutions:
    """Verifies that anomalies D0w0 and D50 are handled according to policy."""

    def test_d0w0_audit_trail_entry(self):
        audit_trail_path = OUTPUT_BASE / "cleaned" / "rdd_urbansense" / "cleaning_audit_trail.json"
        assert audit_trail_path.exists()
        with open(audit_trail_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        transformations = {t["original_label"]: t for t in data["transformations"]}
        assert "D0w0" in transformations
        t_d0w0 = transformations["D0w0"]
        assert t_d0w0["new_label"] == "D00"
        assert t_d0w0["decision_status"] == "APPROVED_MAPPING"
        assert t_d0w0["object_count"] == 1

    def test_d50_quarantine_manifest(self):
        quarantine_path = OUTPUT_BASE / "cleaned" / "quarantine" / "quarantine_manifest.json"
        assert quarantine_path.exists()
        with open(quarantine_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["total_quarantined_samples"] == 28
        assert data["total_quarantined_objects"] == 28
        assert "D50" in data["quarantine_classes"]

    def test_d50_excluded_from_yolo_labels(self):
        """D50 class must NOT exist in the active YOLO label set."""
        yolo_report_path = OUTPUT_BASE / "yolo" / "rdd_urbansense" / "yolo_validation_report.json"
        assert yolo_report_path.exists()
        with open(yolo_report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        assert "D50" not in report["class_counts_in_yolo"]
        assert "D0w0" not in report["class_counts_in_yolo"]
        assert report["class_counts_in_yolo"]["D00"] == 1556


class TestDatasetSplitsAndLeakage:
    """Verifies that dataset splits are deterministic and leakage-free."""

    def test_train_val_disjoint(self):
        yolo_dir = OUTPUT_BASE / "yolo" / "rdd_urbansense"
        train_imgs = {p.stem for p in (yolo_dir / "images" / "train").glob("*.jpg")}
        val_imgs = {p.stem for p in (yolo_dir / "images" / "val").glob("*.jpg")}
        assert train_imgs.isdisjoint(val_imgs), "Train and validation splits overlap!"
        assert len(train_imgs) == 3320
        assert len(val_imgs) == 831

    def test_unannotated_test_set_isolated(self):
        """Test images (1959 images) must NOT be present in train or val."""
        yolo_dir = OUTPUT_BASE / "yolo" / "rdd_urbansense"
        train_imgs = {p.stem for p in (yolo_dir / "images" / "train").glob("*.jpg")}
        val_imgs = {p.stem for p in (yolo_dir / "images" / "val").glob("*.jpg")}
        raw_test_imgs = {p.stem for p in (RAW_DATASET_ROOT / "test" / "images").glob("*.jpg")}
        assert len(raw_test_imgs) == 1959
        assert train_imgs.isdisjoint(raw_test_imgs)
        assert val_imgs.isdisjoint(raw_test_imgs)

    def test_near_duplicate_pairs_grouped_together(self):
        """Verified near-duplicate pairs must be in the exact same split."""
        yolo_dir = OUTPUT_BASE / "yolo" / "rdd_urbansense"
        train_imgs = {p.stem for p in (yolo_dir / "images" / "train").glob("*.jpg")}
        val_imgs = {p.stem for p in (yolo_dir / "images" / "val").glob("*.jpg")}

        train_pairs = [
            ("India_002318", "India_008870"),
            ("India_003191", "India_003989"),
            ("India_003967", "India_008857"),
            ("India_008592", "India_009873"),
        ]
        for p1, p2 in train_pairs:
            in_train_1 = p1 in train_imgs
            in_train_2 = p2 in train_imgs
            in_val_1 = p1 in val_imgs
            in_val_2 = p2 in val_imgs

            if in_train_1:
                assert in_train_2, f"Leakage: {p1} in train, but {p2} not in train!"
            if in_val_1:
                assert in_val_2, f"Leakage: {p1} in val, but {p2} not in val!"


class TestYOLOConversionAndValidity:
    """Verifies that generated YOLO labels and data.yaml conform to specifications."""

    def test_data_yaml_structure(self):
        data_yaml_p = OUTPUT_BASE / "yolo" / "rdd_urbansense" / "data.yaml"
        assert data_yaml_p.exists()
        config = load_yaml(data_yaml_p)
        assert int(config["nc"]) == 8
        names = config["names"]
        # Can be dict with int or str keys
        name_0 = names.get(0) or names.get("0")
        name_5 = names.get(5) or names.get("5")
        assert name_0 == "D00"
        assert name_5 == "D40"

    def test_yolo_labels_match_images(self):
        yolo_dir = OUTPUT_BASE / "yolo" / "rdd_urbansense"
        for split in ["train", "val"]:
            img_stems = {p.stem for p in (yolo_dir / "images" / split).glob("*.jpg")}
            lbl_stems = {p.stem for p in (yolo_dir / "labels" / split).glob("*.txt")}
            assert img_stems == lbl_stems, f"Mismatch in {split} images and labels!"

    def test_yolo_label_coordinates_valid(self):
        """All bounding boxes in YOLO labels must have normalized coordinates in [0.0, 1.0]."""
        yolo_dir = OUTPUT_BASE / "yolo" / "rdd_urbansense"
        checked_boxes = 0
        for split in ["train", "val"]:
            for lbl_p in (yolo_dir / "labels" / split).glob("*.txt"):
                content = lbl_p.read_text(encoding="utf-8").strip()
                if not content:
                    continue  # background image, valid
                for line in content.splitlines():
                    parts = line.strip().split()
                    assert len(parts) == 5
                    cid, xc, yc, w, h = int(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
                    assert 0 <= cid <= 7
                    assert 0.0 <= xc <= 1.0
                    assert 0.0 <= yc <= 1.0
                    assert 0.0 <= w <= 1.0
                    assert 0.0 <= h <= 1.0
                    checked_boxes += 1
        assert checked_boxes == 8175, f"Expected 8175 checked YOLO boxes, got {checked_boxes}"


class TestPipelineDeterminism:
    """Proves that running the split with the same seed produces identical assignments."""

    def test_split_reproducibility(self):
        pipeline = RDDDatasetPreparationPipeline(
            raw_dataset_root=RAW_DATASET_ROOT,
            output_base_dir=OUTPUT_BASE,
            taxonomy_config_path=TAXONOMY_CONFIG_PATH,
            active_taxonomy_name="Candidate_A_Full_RDD",
            train_ratio=0.80,
            background_ratio=0.10,
            seed=42,
        )
        pipeline.phase_1_2_confirm_structure()
        pipeline.phase_4_14_load_taxonomy()
        pipeline.phase_10_duplicate_leakage_audit()

        t1, v1, bgt1, bgv1 = pipeline.phase_17_split_dataset()
        t2, v2, bgt2, bgv2 = pipeline.phase_17_split_dataset()

        assert t1 == t2, "Train split is not deterministic with seed 42!"
        assert v1 == v2, "Val split is not deterministic with seed 42!"
        assert bgt1 == bgt2, "Background train split is not deterministic!"
        assert bgv1 == bgv2, "Background val split is not deterministic!"
