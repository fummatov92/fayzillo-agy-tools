import os
import sys
import shutil
import unittest
import json
import numpy as np
from PIL import Image

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from agy_tools.modules.face_tool import FacePipeline

TEST_TEMP_DIR = os.path.join(parent_dir, "tests_temp_face")

class TestFaceTool(unittest.TestCase):
    def setUp(self):
        os.makedirs(TEST_TEMP_DIR, exist_ok=True)
        self.db_file = os.path.join(TEST_TEMP_DIR, "test_faces.enc")
        self.key_file = os.path.join(TEST_TEMP_DIR, "test_face.key")
        self.pipeline = FacePipeline(db_path=self.db_file, key_path=self.key_file)

    def tearDown(self):
        if os.path.exists(TEST_TEMP_DIR):
            shutil.rmtree(TEST_TEMP_DIR, ignore_errors=True)

    def test_01_models_loaded(self):
        self.assertIsNotNone(self.pipeline.det_sess)
        self.assertIsNotNone(self.pipeline.emb_sess)

    def test_02_embedding_shape_and_l2_norm(self):
        dummy_face = Image.new("RGB", (112, 112), color=(150, 100, 50))
        emb = self.pipeline.extract_embedding(dummy_face)
        self.assertEqual(emb.shape, (512,))
        norm = np.linalg.norm(emb)
        self.assertAlmostEqual(norm, 1.0, places=4)

    def test_03_blank_image_detection(self):
        blank = Image.new("RGB", (320, 240), color=(0, 0, 0))
        faces = self.pipeline.detect_faces(blank)
        self.assertEqual(len(faces), 0)

    def test_04_enroll_requires_consent(self):
        img_path = os.path.join(TEST_TEMP_DIR, "sample_user.jpg")
        img = Image.new("RGB", (200, 200), color=(180, 120, 80))
        img.save(img_path)

        # Without consent flag, enroll must raise PermissionError
        with self.assertRaises(PermissionError):
            self.pipeline.enroll("Alice", img_path, consent_confirmed=False)

    def test_05_enroll_and_encrypted_db(self):
        img_path = os.path.join(TEST_TEMP_DIR, "sample_alice.jpg")
        img = Image.new("RGB", (200, 200), color=(180, 120, 80))
        img.save(img_path)

        # Enroll with explicit consent
        enrolled = self.pipeline.enroll("Alice", img_path, consent_confirmed=True)
        self.assertEqual(enrolled["name"], "Alice")
        self.assertIn("Alice", self.pipeline.db)
        self.assertTrue(os.path.exists(self.db_file))

        # Check that file content is NOT plain JSON text (Fernet encrypted)
        with open(self.db_file, "rb") as f:
            raw_bytes = f.read()
        self.assertNotIn(b'"Alice"', raw_bytes)
        self.assertNotIn(b'"embedding"', raw_bytes)

        # Re-open pipeline and verify decryption
        new_pipeline = FacePipeline(db_path=self.db_file, key_path=self.key_file)
        self.assertIn("Alice", new_pipeline.db)

    def test_06_right_to_be_forgotten(self):
        img_path = os.path.join(TEST_TEMP_DIR, "sample_bob.jpg")
        img = Image.new("RGB", (200, 200), color=(160, 110, 70))
        img.save(img_path)

        self.pipeline.enroll("Bob", img_path, consent_confirmed=True)
        self.assertIn("Bob", self.pipeline.db)

        # Forget Bob
        res = self.pipeline.forget("Bob")
        self.assertTrue(res["deleted"])
        self.assertNotIn("Bob", self.pipeline.db)

        # Reload pipeline from disk to ensure persistence of deletion
        reloaded = FacePipeline(db_path=self.db_file, key_path=self.key_file)
        self.assertNotIn("Bob", reloaded.db)

    def test_07_legacy_json_migration(self):
        # Create legacy JSON file
        legacy_json = os.path.join(TEST_TEMP_DIR, "test_faces.json")
        dummy_data = {"Charlie": [{"embedding": [0.1]*512, "score": 0.99, "box": [0,0,10,10]}]}
        with open(legacy_json, "w", encoding="utf-8") as f:
            json.dump(dummy_data, f)

        # Target db file is .enc
        target_enc = os.path.join(TEST_TEMP_DIR, "test_faces.enc")
        if os.path.exists(target_enc):
            os.remove(target_enc)

        migrating_pipeline = FacePipeline(db_path=target_enc, key_path=self.key_file)
        self.assertIn("Charlie", migrating_pipeline.db)
        # Verify plain-text file was removed and encrypted file was created
        self.assertFalse(os.path.exists(legacy_json))
        self.assertTrue(os.path.exists(target_enc))

if __name__ == "__main__":
    unittest.main()
