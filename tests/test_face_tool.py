import os
import sys
import shutil
import unittest
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
        self.db_file = os.path.join(TEST_TEMP_DIR, "test_faces.json")
        self.pipeline = FacePipeline(db_path=self.db_file)

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

    def test_04_enroll_and_identify(self):
        img_path = os.path.join(TEST_TEMP_DIR, "sample_user.jpg")
        img = Image.new("RGB", (200, 200), color=(180, 120, 80))
        img.save(img_path)

        # Enroll
        enrolled = self.pipeline.enroll("Alice", img_path)
        self.assertEqual(enrolled["name"], "Alice")
        self.assertIn("Alice", self.pipeline.db)

        # Identify
        res = self.pipeline.identify_image(img_path)
        self.assertIn("faces", res)

if __name__ == "__main__":
    unittest.main()
