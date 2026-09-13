import os
import sys
import shutil
import unittest
import json
import numpy as np
from PIL import Image, ImageDraw

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from agy_tools.modules.face_tool import FacePipeline

TEST_TEMP_DIR = os.path.join(parent_dir, "tests_temp_face")
TEST_DATA_DIR = os.path.join(parent_dir, "tests", "test_data_faces")

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

    def test_08_image_variations_robustness(self):
        pA_full = os.path.join(TEST_DATA_DIR, "personA_full.jpg")
        if not os.path.exists(pA_full):
            self.skipTest("Real face test data not available")

        orig_path = os.path.join(TEST_TEMP_DIR, "orig.jpg")
        Image.open(pA_full).convert("RGB").save(orig_path, quality=95)

        self.pipeline.enroll("Fayzillo", orig_path, consent_confirmed=True)

        resaved_path = os.path.join(TEST_TEMP_DIR, "resaved_pil.jpg")
        Image.open(orig_path).save(resaved_path, quality=95)
        res_pil = self.pipeline.identify_image(resaved_path)
        self.assertGreaterEqual(res_pil["faces_found"], 1)
        self.assertEqual(res_pil["faces"][0]["identity"], "Fayzillo")
        self.assertTrue(res_pil["faces"][0]["is_verified"])
        self.assertGreaterEqual(res_pil["faces"][0]["similarity"], 0.95)

    def test_09_real_human_photos_disk_io(self):
        pA_full = os.path.join(TEST_DATA_DIR, "personA_full.jpg")
        pB = os.path.join(TEST_DATA_DIR, "personB.jpg")
        if not os.path.exists(pA_full) or not os.path.exists(pB):
            self.skipTest("Real face test data not available")

        # 1. Enroll PersonA from disk
        enrolled = self.pipeline.enroll("PersonA", pA_full, consent_confirmed=True)
        self.assertEqual(enrolled["name"], "PersonA")

        # 2. Test PersonA with real JPEG q70 saved to disk
        pA_q70 = os.path.join(TEST_TEMP_DIR, "personA_q70.jpg")
        Image.open(pA_full).convert("RGB").save(pA_q70, quality=70)
        res_q70 = self.pipeline.identify_image(pA_q70)
        self.assertGreaterEqual(res_q70["faces_found"], 1)
        self.assertEqual(res_q70["faces"][0]["identity"], "PersonA")
        self.assertTrue(res_q70["faces"][0]["is_verified"])
        self.assertGreaterEqual(res_q70["faces"][0]["similarity"], 0.95)

        # 3. Test PersonA with real JPEG q85 saved to disk
        pA_q85 = os.path.join(TEST_TEMP_DIR, "personA_q85.jpg")
        Image.open(pA_full).convert("RGB").save(pA_q85, quality=85)
        res_q85 = self.pipeline.identify_image(pA_q85)
        self.assertGreaterEqual(res_q85["faces_found"], 1)
        self.assertEqual(res_q85["faces"][0]["identity"], "PersonA")
        self.assertTrue(res_q85["faces"][0]["is_verified"])
        self.assertGreaterEqual(res_q85["faces"][0]["similarity"], 0.95)

        # 4. Test PersonA with real resize -20% saved to disk
        pA_res20 = os.path.join(TEST_TEMP_DIR, "personA_res20.jpg")
        imgA = Image.open(pA_full).convert("RGB")
        w, h = imgA.size
        imgA.resize((int(w * 0.8), int(h * 0.8)), Image.Resampling.BILINEAR).save(pA_res20, quality=85)
        res_res20 = self.pipeline.identify_image(pA_res20)
        self.assertGreaterEqual(res_res20["faces_found"], 1)
        self.assertEqual(res_res20["faces"][0]["identity"], "PersonA")
        self.assertTrue(res_res20["faces"][0]["is_verified"])
        self.assertGreaterEqual(res_res20["faces"][0]["similarity"], 0.95)

        # 5. Test PersonB (Different person) -> Must NOT match PersonA
        res_pB = self.pipeline.identify_image(pB)
        self.assertGreaterEqual(res_pB["faces_found"], 1)
        for face in res_pB["faces"]:
            # Different person similarity against PersonA must be below 0.35 (well separated)
            if face["identity"] == "PersonA":
                self.assertFalse(face["is_verified"])

if __name__ == "__main__":
    unittest.main()
