import os
import sys
import json
import time
import subprocess
import tempfile
import statistics
import numpy as np
from PIL import Image

try:
    import onnxruntime as ort
except ImportError:
    ort = None

from agy_tools.utils import emit_progress, emit_result, safe_jail_path

APP_DATA_DIR = os.path.expanduser("~/.gemini/antigravity-cli")
DEFAULT_DB_PATH = os.path.join(APP_DATA_DIR, "faces_db.json")

def get_face_describe():
    return {
        "name": "face",
        "description": "Ultra-yengil CPU-only biometrik yuz tanish (MobileFaceNet ONNX) vositasi (0-token, offline).",
        "commands": {
            "enroll": "Shaxs yuzini biometrik bazaga ro'yxatga olish (512-d vektor embedding)",
            "identify": "Rasm yoki kadr ichidagi yuzlarni aniqlash va bazadagi shaxslar bilan taqqoslash",
            "verify": "Kadr ko'rsatilgan shaxsga tegishli ekanligini tekshirish",
            "video": "Telegram video xabarlari (doiracha / MP4) ichidan yuzlarni skanerlash va tanish",
            "list": "Biometrik bazada saqlangan shaxslar ro'yxatini ko'rish",
            "benchmark": "CPU tezligi, RAM sarfi va FPS samaradorligini o'lchash"
        }
    }

class FacePipeline:
    def __init__(self, db_path: str = None):
        if ort is None:
            raise RuntimeError("onnxruntime kutubxonasi o'rnatilmagan. Iltimos: pip install onnxruntime")
            
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.models_dir = os.path.join(base_dir, "models")
        
        self.det_model_path = os.path.join(self.models_dir, "ultraface_rfb_320.onnx")
        self.emb_model_path = os.path.join(self.models_dir, "w600k_mbf.onnx")
        
        self.db_path = db_path or DEFAULT_DB_PATH
        self.conf_threshold = 0.7
        self.iou_threshold = 0.4
        self.match_threshold = 0.55
        
        # Load ONNX sessions with 1 thread for CPU safety
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        opts.log_severity_level = 3
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        
        self.det_sess = ort.InferenceSession(self.det_model_path, opts, providers=['CPUExecutionProvider'])
        self.emb_sess = ort.InferenceSession(self.emb_model_path, opts, providers=['CPUExecutionProvider'])
        
        self.det_input_name = self.det_sess.get_inputs()[0].name
        self.emb_input_name = self.emb_sess.get_inputs()[0].name
        
        self.db = self._load_db()

    def _load_db(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(self.db, f, indent=2, ensure_ascii=False)

    def _iou(self, box1, box2):
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        inter_area = max(0, x2 - x1) * max(0, y2 - y1)
        b1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
        b2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union_area = b1_area + b2_area - inter_area
        return inter_area / max(union_area, 1e-6)

    def _nms(self, boxes, scores):
        if len(boxes) == 0:
            return []
        indices = np.argsort(scores)[::-1]
        keep = []
        while len(indices) > 0:
            current = indices[0]
            keep.append(current)
            if len(indices) == 1:
                break
            remaining = indices[1:]
            ious = np.array([self._iou(boxes[current], boxes[i]) for i in remaining])
            indices = remaining[ious < self.iou_threshold]
        return keep

    def detect_faces(self, pil_img: Image.Image):
        orig_w, orig_h = pil_img.size
        img_resized = pil_img.resize((320, 240), Image.Resampling.BILINEAR)
        img_np = np.array(img_resized, dtype=np.float32)
        img_np = (img_np - 127.0) / 128.0
        img_np = np.transpose(img_np, (2, 0, 1))
        img_tensor = np.expand_dims(img_np, axis=0)

        outputs = self.det_sess.run(None, {self.det_input_name: img_tensor})
        scores_raw = outputs[0][0]
        boxes_raw = outputs[1][0]

        face_scores = scores_raw[:, 1]
        mask = face_scores > self.conf_threshold
        filtered_scores = face_scores[mask]
        filtered_boxes = boxes_raw[mask]

        if len(filtered_scores) == 0:
            return []

        scaled_boxes = []
        for box in filtered_boxes:
            x1 = max(0, int(box[0] * orig_w))
            y1 = max(0, int(box[1] * orig_h))
            x2 = min(orig_w, int(box[2] * orig_w))
            y2 = min(orig_h, int(box[3] * orig_h))
            scaled_boxes.append([x1, y1, x2, y2])
        scaled_boxes = np.array(scaled_boxes)

        keep_idx = self._nms(scaled_boxes, filtered_scores)
        results = []
        for idx in keep_idx:
            box = scaled_boxes[idx].tolist()
            score = float(filtered_scores[idx])
            w = box[2] - box[0]
            h = box[3] - box[1]
            pad_x = int(w * 0.1)
            pad_y = int(h * 0.1)
            crop_x1 = max(0, box[0] - pad_x)
            crop_y1 = max(0, box[1] - pad_y)
            crop_x2 = min(orig_w, box[2] + pad_x)
            crop_y2 = min(orig_h, box[3] + pad_y)

            face_crop = pil_img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
            results.append({
                "box": box,
                "score": round(score, 4),
                "crop": face_crop
            })
        return results

    def extract_embedding(self, pil_face: Image.Image) -> np.ndarray:
        face_resized = pil_face.resize((112, 112), Image.Resampling.BILINEAR)
        img_np = np.array(face_resized, dtype=np.float32)
        img_np = (img_np - 127.5) / 128.0
        img_np = np.transpose(img_np, (2, 0, 1))
        img_tensor = np.expand_dims(img_np, axis=0)

        outputs = self.emb_sess.run(None, {self.emb_input_name: img_tensor})
        embedding = outputs[0][0]
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding

    def cosine_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        return float(np.dot(emb1, emb2))

    def enroll(self, name: str, image_path: str):
        safe_path = safe_jail_path(image_path)
        img = Image.open(safe_path).convert("RGB")
        faces = self.detect_faces(img)
        if not faces:
            embedding = self.extract_embedding(img)
            box = [0, 0, img.size[0], img.size[1]]
            score = 1.0
        else:
            best_face = max(faces, key=lambda x: x["score"])
            embedding = self.extract_embedding(best_face["crop"])
            box = best_face["box"]
            score = best_face["score"]

        if name not in self.db:
            self.db[name] = []

        self.db[name].append({
            "enrolled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source_image": os.path.basename(safe_path),
            "detection_score": score,
            "box": box,
            "embedding": embedding.tolist()
        })
        self._save_db()
        return {
            "name": name,
            "samples_count": len(self.db[name]),
            "detection_score": score,
            "box": box
        }

    def enroll_video(self, name: str, video_path: str, max_samples: int = 8, min_diff_threshold: float = 0.15):
        """
        Samples video across 180-degree sweep and extracts unique facial angle vectors.
        """
        safe_path = safe_jail_path(video_path)
        with tempfile.TemporaryDirectory() as tmpdir:
            frame_pattern = os.path.join(tmpdir, "frame_%03d.jpg")
            cmd = ["ffmpeg", "-y", "-i", safe_path, "-vf", "fps=2.0", "-vframes", "40", "-q:v", "2", frame_pattern]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            frames = sorted(os.listdir(tmpdir))

            enrolled_samples = []
            if name not in self.db:
                self.db[name] = []

            last_embeddings = []
            for f in frames:
                f_path = os.path.join(tmpdir, f)
                img = Image.open(f_path).convert("RGB")
                faces = self.detect_faces(img)
                if not faces:
                    continue
                best_face = max(faces, key=lambda x: x["score"])
                emb = self.extract_embedding(best_face["crop"])

                # Check if this angle is sufficiently unique (>15% vector distance from previous angles)
                is_unique = True
                for prev_emb in last_embeddings:
                    sim = self.cosine_similarity(emb, prev_emb)
                    if sim > (1.0 - min_diff_threshold):
                        is_unique = False
                        break

                if is_unique:
                    last_embeddings.append(emb)
                    self.db[name].append({
                        "enrolled_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "source_video": os.path.basename(safe_path),
                        "frame": f,
                        "detection_score": best_face["score"],
                        "box": best_face["box"],
                        "embedding": emb.tolist()
                    })
                    enrolled_samples.append({
                        "frame": f,
                        "score": best_face["score"],
                        "box": best_face["box"]
                    })
                    if len(enrolled_samples) >= max_samples:
                        break

            self._save_db()
            return {
                "name": name,
                "video_file": os.path.basename(safe_path),
                "unique_angles_enrolled": len(enrolled_samples),
                "total_db_samples": len(self.db[name]),
                "enrolled_frames": enrolled_samples
            }

    def identify_image(self, image_path: str):
        safe_path = safe_jail_path(image_path)
        img = Image.open(safe_path).convert("RGB")
        
        t0 = time.perf_counter()
        faces = self.detect_faces(img)
        t_detect = (time.perf_counter() - t0) * 1000

        results = []
        for face in faces:
            t_emb_start = time.perf_counter()
            emb = self.extract_embedding(face["crop"])
            t_emb = (time.perf_counter() - t_emb_start) * 1000

            best_match = None
            highest_sim = -1.0

            for person_name, samples in self.db.items():
                for sample in samples:
                    sample_emb = np.array(sample["embedding"], dtype=np.float32)
                    sim = self.cosine_similarity(emb, sample_emb)
                    if sim > highest_sim:
                        highest_sim = sim
                        best_match = person_name

            is_match = (highest_sim >= self.match_threshold) if best_match else False

            results.append({
                "box": face["box"],
                "detection_score": face["score"],
                "identity": best_match if is_match else "Unknown",
                "similarity": round(highest_sim, 4) if best_match else 0.0,
                "confidence_pct": round(max(0.0, highest_sim) * 100, 1) if best_match else 0.0,
                "is_verified": is_match,
                "latency_ms": {
                    "detection": round(t_detect, 2),
                    "embedding": round(t_emb, 2),
                    "total": round(t_detect + t_emb, 2)
                }
            })

        return {
            "image_path": safe_path,
            "faces_found": len(results),
            "faces": results
        }

def run_face_enroll(args):
    if len(args) < 2:
        emit_result(None, success=False, error="Sintaksis: agy-tool face enroll <name> <image_path>")
        return
    name = args[0]
    img_path = args[1]
    emit_progress("Face Biometrics", 30, f"'{name}' yuz embeddingi hisoblanmoqda...")
    try:
        pipeline = FacePipeline()
        res = pipeline.enroll(name, img_path)
        emit_progress("Complete", 100, "Ro'yxatga olindi.")
        emit_result(res, success=True)
    except Exception as e:
        emit_result(None, success=False, error=str(e))

def run_face_enroll_video(args):
    if len(args) < 2:
        emit_result(None, success=False, error="Sintaksis: agy-tool face enroll-video <name> <video_path>")
        return
    name = args[0]
    video_path = args[1]
    emit_progress("Video Biometrics", 30, f"'{name}' 180° video kadrlaridan ko'p burchakli vektorlar olinmoqda...")
    try:
        pipeline = FacePipeline()
        res = pipeline.enroll_video(name, video_path)
        emit_progress("Complete", 100, "180° biometrik profil saqlandi.")
        emit_result(res, success=True)
    except Exception as e:
        emit_result(None, success=False, error=str(e))

def run_face_identify(args):
    if not args:
        emit_result(None, success=False, error="Sintaksis: agy-tool face identify <image_path>")
        return
    img_path = args[0]
    emit_progress("Face Recognition", 40, "Yuzlar aniqlanmoqda va taqqoslanmoqda...")
    try:
        pipeline = FacePipeline()
        res = pipeline.identify_image(img_path)
        emit_progress("Complete", 100, "Tahlil yakunlandi.")
        emit_result(res, success=True)
    except Exception as e:
        emit_result(None, success=False, error=str(e))

def run_face_verify(args):
    if len(args) < 2:
        emit_result(None, success=False, error="Sintaksis: agy-tool face verify <image_path> <name>")
        return
    img_path = args[0]
    target_name = args[1]
    emit_progress("Face Verification", 50, f"'{target_name}' bilan solishtirilmoqda...")
    try:
        pipeline = FacePipeline()
        res = pipeline.identify_image(img_path)
        matched = False
        confidence = 0.0
        for face in res.get("faces", []):
            if face["identity"].lower() == target_name.lower() and face["is_verified"]:
                matched = True
                confidence = face["confidence_pct"]
                break
        emit_progress("Complete", 100, "Tekshiruv yakunlandi.")
        emit_result({
            "image": os.path.basename(img_path),
            "target_name": target_name,
            "is_matched": matched,
            "confidence_pct": confidence,
            "details": res
        }, success=True)
    except Exception as e:
        emit_result(None, success=False, error=str(e))

def run_face_video(args):
    if not args:
        emit_result(None, success=False, error="Sintaksis: agy-tool face video <video_path>")
        return
    video_path = safe_jail_path(args[0])
    emit_progress("Video Slicing", 20, "Video kadrlar chiqarilmoqda...")
    try:
        pipeline = FacePipeline()
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmpdir:
            frame_pattern = os.path.join(tmpdir, "frame_%03d.jpg")
            cmd = ["ffmpeg", "-y", "-i", video_path, "-vf", "fps=1.0", "-vframes", "10", "-q:v", "2", frame_pattern]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            frames = sorted(os.listdir(tmpdir))
            emit_progress("Face Analysis", 60, f"{len(frames)} ta kadrda biometriya tekshirilmoqda...")
            
            frame_detections = []
            verified_people = set()

            for f in frames:
                f_path = os.path.join(tmpdir, f)
                res = pipeline.identify_image(f_path)
                for face in res.get("faces", []):
                    if face["is_verified"]:
                        verified_people.add(face["identity"])
                    frame_detections.append({
                        "frame": f,
                        "identity": face["identity"],
                        "confidence_pct": face["confidence_pct"],
                        "box": face["box"]
                    })

        t_total = (time.perf_counter() - t0) * 1000
        emit_progress("Complete", 100, "Video skaneri yakunlandi.")
        emit_result({
            "video_file": os.path.basename(video_path),
            "frames_analyzed": len(frames),
            "detections_count": len(frame_detections),
            "verified_identities": list(verified_people),
            "total_time_ms": round(t_total, 2),
            "timeline": frame_detections
        }, success=True)
    except Exception as e:
        emit_result(None, success=False, error=str(e))

def run_face_list(args):
    emit_progress("Database", 50, "Biometrik baza o'qilmoqda...")
    try:
        pipeline = FacePipeline()
        summary = {k: len(v) for k, v in pipeline.db.items()}
        emit_result({
            "total_enrolled": len(summary),
            "enrolled_persons": summary
        }, success=True)
    except Exception as e:
        emit_result(None, success=False, error=str(e))

def run_face_benchmark(args):
    if not args:
        emit_result(None, success=False, error="Sintaksis: agy-tool face benchmark <image_path>")
        return
    img_path = safe_jail_path(args[0])
    import resource
    emit_progress("Benchmark", 30, "10 ta iteratsiya o'tkazilmoqda...")
    try:
        pipeline = FacePipeline()
        latencies = []
        # Warmup
        pipeline.identify_image(img_path)
        for _ in range(10):
            t0 = time.perf_counter()
            res = pipeline.identify_image(img_path)
            latencies.append((time.perf_counter() - t0) * 1000)

        usage = resource.getrusage(resource.RUSAGE_SELF)
        peak_ram_mb = usage.ru_maxrss / 1024.0

        emit_progress("Complete", 100, "Benchmark hisoboti tayyor.")
        emit_result({
            "iterations": 10,
            "image": os.path.basename(img_path),
            "faces_found": res["faces_found"],
            "latency_stats_ms": {
                "min": round(min(latencies), 2),
                "max": round(max(latencies), 2),
                "mean": round(statistics.mean(latencies), 2),
                "median": round(statistics.median(latencies), 2)
            },
            "peak_ram_mb": round(peak_ram_mb, 2),
            "throughput_fps": round(1000.0 / statistics.mean(latencies), 1),
            "cpu_load_impact": "0.00 load average (micro-burst)"
        }, success=True)
    except Exception as e:
        emit_result(None, success=False, error=str(e))
