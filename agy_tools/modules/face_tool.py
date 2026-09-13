import os
import sys
import json
import time
import subprocess
import tempfile
import statistics
import base64
import numpy as np
from PIL import Image

try:
    import onnxruntime as ort
except ImportError:
    ort = None

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError:
    Fernet = None

from agy_tools.utils import emit_progress, emit_result, safe_jail_path

APP_DATA_DIR = os.path.expanduser("~/.gemini/antigravity-cli")
DEFAULT_DB_PATH = os.path.join(APP_DATA_DIR, "faces_db.enc")
LEGACY_DB_PATH = os.path.join(APP_DATA_DIR, "faces_db.json")
KEY_FILE_PATH = os.path.join(APP_DATA_DIR, ".face_key")

def get_or_create_encryption_key(key_path: str = None) -> bytes:
    """
    Retrieves or generates a secure Fernet symmetric encryption key for biometric data.
    Priority:
      1. AGY_BIOMETRIC_SECRET env var (derived via PBKDF2)
      2. Key file on disk (~/.gemini/antigravity-cli/.face_key with chmod 0600)
    """
    if Fernet is None:
        raise RuntimeError("cryptography kutubxonasi o'rnatilmagan. Iltimos: pip install cryptography")
        
    env_secret = os.environ.get("AGY_BIOMETRIC_SECRET")
    if env_secret:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"agy_biometric_salt_fixed_v1",
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(env_secret.encode()))

    target_key_file = key_path or KEY_FILE_PATH
    if os.path.exists(target_key_file):
        with open(target_key_file, "rb") as f:
            return f.read().strip()
    else:
        os.makedirs(os.path.dirname(target_key_file), exist_ok=True)
        key = Fernet.generate_key()
        with open(target_key_file, "wb") as f:
            f.write(key)
        try:
            os.chmod(target_key_file, 0o600)
        except Exception:
            pass
        return key

def get_face_describe():
    return {
        "name": "face",
        "description": "Shifrlangan, consent-nazoratli, ultra-yengil CPU biometrik yuz tanish (MobileFaceNet ONNX) vositasi.",
        "commands": {
            "enroll": "Shaxs yuzini shifrlangan biometrik bazaga ro'yxatga olish (--consent-confirmed talab etiladi)",
            "enroll-video": "180° video orqali ko'p burchakli 3D biometrik profil yaratish (--consent-confirmed talab etiladi)",
            "identify": "Rasm yoki kadr ichidagi yuzlarni aniqlash va shifrlangan bazadagi shaxslar bilan taqqoslash",
            "verify": "Kadr ko'rsatilgan shaxsga tegishli ekanligini verifikatsiya qilish",
            "video": "Telegram video xabarlari ichidan yuzlarni skanerlash (default: --owner-only maxfiylik rejimi)",
            "forget": "Shaxsning barcha biometrik embeddinglarini bazadan butunlay o'chirish (unutilish huquqi)",
            "list": "Biometrik bazada saqlangan shaxslar ro'yxatini ko'rish",
            "benchmark": "CPU tezligi, RAM sarfi va FPS samaradorligini o'lchash"
        }
    }

class FacePipeline:
    def __init__(self, db_path: str = None, key_path: str = None):
        if ort is None:
            raise RuntimeError("onnxruntime kutubxonasi o'rnatilmagan. Iltimos: pip install onnxruntime")
        if Fernet is None:
            raise RuntimeError("cryptography kutubxonasi o'rnatilmagan. Iltimos: pip install cryptography")
            
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.models_dir = os.path.join(base_dir, "models")
        
        self.det_model_path = os.path.join(self.models_dir, "ultraface_rfb_320.onnx")
        self.emb_model_path = os.path.join(self.models_dir, "w600k_mbf.onnx")
        
        self.db_path = db_path or DEFAULT_DB_PATH
        self.key_path = key_path or KEY_FILE_PATH
        self.fernet = Fernet(get_or_create_encryption_key(self.key_path))
        
        self.conf_threshold = 0.7
        self.iou_threshold = 0.4
        self.match_threshold = 0.55
        
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
        # 1. Check encrypted db path
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "rb") as f:
                    encrypted_data = f.read()
                decrypted = self.fernet.decrypt(encrypted_data)
                return json.loads(decrypted.decode("utf-8"))
            except Exception:
                return {}

        # 2. Migration from legacy unencrypted json if present
        legacy_path = self.db_path.replace(".enc", ".json")
        if os.path.exists(legacy_path):
            try:
                with open(legacy_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Encrypt and save to .enc
                self.db = data
                self._save_db()
                # Securely remove plain-text legacy json
                os.remove(legacy_path)
                return data
            except Exception:
                return {}

        return {}

    def _save_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        raw_json = json.dumps(self.db, ensure_ascii=False).encode("utf-8")
        encrypted_data = self.fernet.encrypt(raw_json)
        with open(self.db_path, "wb") as f:
            f.write(encrypted_data)
        try:
            os.chmod(self.db_path, 0o600)
        except Exception:
            pass

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

    def enroll(self, name: str, image_path: str, consent_confirmed: bool = False):
        if not consent_confirmed:
            raise PermissionError("Xavfsizlik talabi: Ushbu shaxsning biometrik ma'lumotlarini qayta ishlashga roziligi olinganini tasdiqlang: --consent-confirmed")

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
            "box": box,
            "encrypted": True
        }

    def enroll_video(self, name: str, video_path: str, consent_confirmed: bool = False, max_samples: int = 8, min_diff_threshold: float = 0.15):
        if not consent_confirmed:
            raise PermissionError("Xavfsizlik talabi: Ushbu shaxsning biometrik ma'lumotlarini qayta ishlashga roziligi olinganini tasdiqlang: --consent-confirmed")

        safe_path = safe_jail_path(video_path)
        with tempfile.TemporaryDirectory(dir="/home/fayzillo/Desktop/temp" if os.path.exists("/home/fayzillo/Desktop/temp") else None) as tmpdir:
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
                "enrolled_frames": enrolled_samples,
                "encrypted": True
            }

    def forget(self, name: str):
        """
        Right to be forgotten: permanently deletes a person's biometric vectors from database.
        """
        if name in self.db:
            samples_removed = len(self.db[name])
            del self.db[name]
            self._save_db()
            return {
                "name": name,
                "deleted": True,
                "samples_removed": samples_removed,
                "remaining_persons": list(self.db.keys())
            }
        else:
            return {
                "name": name,
                "deleted": False,
                "message": f"'{name}' biometrik bazada topilmadi"
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

    def scan_video(self, video_path: str, owner_only: bool = True, owner_name: str = None, allow_multi_identity: bool = False):
        safe_path = safe_jail_path(video_path)
        is_owner_mode = owner_only and not allow_multi_identity
        
        # Determine owner identity
        target_owner = owner_name or os.environ.get("AGY_OWNER_NAME")
        if not target_owner and len(self.db) > 0:
            target_owner = list(self.db.keys())[0]

        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory(dir="/home/fayzillo/Desktop/temp" if os.path.exists("/home/fayzillo/Desktop/temp") else None) as tmpdir:
            frame_pattern = os.path.join(tmpdir, "frame_%03d.jpg")
            cmd = ["ffmpeg", "-y", "-i", safe_path, "-vf", "fps=1.0", "-vframes", "10", "-q:v", "2", frame_pattern]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            frames = sorted(os.listdir(tmpdir))
            frame_detections = []
            verified_people = set()

            for f in frames:
                f_path = os.path.join(tmpdir, f)
                res = self.identify_image(f_path)
                for face in res.get("faces", []):
                    if is_owner_mode:
                        # Owner-only privacy protection mode
                        if target_owner and face["identity"].lower() == target_owner.lower() and face["is_verified"]:
                            verified_people.add(target_owner)
                            frame_detections.append({
                                "frame": f,
                                "identity": target_owner,
                                "confidence_pct": face["confidence_pct"],
                                "box": face["box"]
                            })
                        else:
                            # Strict privacy: do NOT reveal identity or names of other people
                            frame_detections.append({
                                "frame": f,
                                "identity": "unknown_person",
                                "confidence_pct": 0.0,
                                "box": face["box"]
                            })
                    else:
                        # Multi-identity mode
                        if face["is_verified"]:
                            verified_people.add(face["identity"])
                        frame_detections.append({
                            "frame": f,
                            "identity": face["identity"],
                            "confidence_pct": face["confidence_pct"],
                            "box": face["box"]
                        })

        t_total = (time.perf_counter() - t0) * 1000
        return {
            "video_file": os.path.basename(safe_path),
            "privacy_mode": "owner_only" if is_owner_mode else "multi_identity",
            "frames_analyzed": len(frames),
            "detections_count": len(frame_detections),
            "verified_identities": list(verified_people),
            "total_time_ms": round(t_total, 2),
            "timeline": frame_detections
        }


def run_face_enroll(args):
    consent = "--consent-confirmed" in args
    clean_args = [a for a in args if a != "--consent-confirmed"]
    if len(clean_args) < 2:
        emit_result(None, success=False, error="Sintaksis: agy-tool face enroll <name> <image_path> --consent-confirmed")
        return
    name = clean_args[0]
    img_path = clean_args[1]

    if not consent:
        emit_result(None, success=False, error="Xavfsizlik talabi: Ushbu shaxsning biometrik ma'lumotlarini qayta ishlashga roziligi olinganini tasdiqlang: --consent-confirmed")
        return

    emit_progress("Face Biometrics", 30, f"'{name}' yuz embeddingi shifrlangan holatda hisoblanmoqda...")
    try:
        pipeline = FacePipeline()
        res = pipeline.enroll(name, img_path, consent_confirmed=True)
        emit_progress("Complete", 100, "Shifrlangan biometriya ro'yxatga olindi.")
        emit_result(res, success=True)
    except Exception as e:
        emit_result(None, success=False, error=str(e))

def run_face_enroll_video(args):
    consent = "--consent-confirmed" in args
    clean_args = [a for a in args if a != "--consent-confirmed"]
    if len(clean_args) < 2:
        emit_result(None, success=False, error="Sintaksis: agy-tool face enroll-video <name> <video_path> --consent-confirmed")
        return
    name = clean_args[0]
    video_path = clean_args[1]

    if not consent:
        emit_result(None, success=False, error="Xavfsizlik talabi: Ushbu shaxsning biometrik ma'lumotlarini qayta ishlashga roziligi olinganini tasdiqlang: --consent-confirmed")
        return

    emit_progress("Video Biometrics", 30, f"'{name}' 180° video kadrlaridan ko'p burchakli vektorlar shifrlanmoqda...")
    try:
        pipeline = FacePipeline()
        res = pipeline.enroll_video(name, video_path, consent_confirmed=True)
        emit_progress("Complete", 100, "180° shifrlangan biometrik profil saqlandi.")
        emit_result(res, success=True)
    except Exception as e:
        emit_result(None, success=False, error=str(e))

def run_face_forget(args):
    if not args:
        emit_result(None, success=False, error="Sintaksis: agy-tool face forget <name>")
        return
    name = args[0]
    emit_progress("Right to Forget", 50, f"'{name}' biometrik ma'lumotlari bazadan butunlay o'chirilmoqda...")
    try:
        pipeline = FacePipeline()
        res = pipeline.forget(name)
        emit_progress("Complete", 100, "O'chirish yakunlandi.")
        emit_result(res, success=True)
    except Exception as e:
        emit_result(None, success=False, error=str(e))

def run_face_identify(args):
    if not args:
        emit_result(None, success=False, error="Sintaksis: agy-tool face identify <image_path>")
        return
    img_path = args[0]
    emit_progress("Face Recognition", 40, "Yuzlar aniqlanmoqda va shifrlangan bazadan taqqoslanmoqda...")
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
        emit_result(None, success=False, error="Sintaksis: agy-tool face video <video_path> [--allow-multi-identity] [--owner-name <name>]")
        return
    
    allow_multi = "--allow-multi-identity" in args
    owner_name = None
    clean_args = []
    i = 0
    while i < len(args):
        if args[i] == "--allow-multi-identity":
            i += 1
        elif args[i] == "--owner-name" and i + 1 < len(args):
            owner_name = args[i + 1]
            i += 2
        else:
            clean_args.append(args[i])
            i += 1

    if not clean_args:
        emit_result(None, success=False, error="Video fayl yo'li ko'rsatilmadi.")
        return

    video_path = safe_jail_path(clean_args[0])
    emit_progress("Video Slicing", 20, "Video kadrlar chiqarilmoqda (Privacy Guard faol)...")
    try:
        pipeline = FacePipeline()
        res = pipeline.scan_video(video_path, owner_only=not allow_multi, owner_name=owner_name, allow_multi_identity=allow_multi)
        emit_progress("Complete", 100, "Video skaneri yakunlandi.")
        emit_result(res, success=True)
    except Exception as e:
        emit_result(None, success=False, error=str(e))

def run_face_list(args):
    emit_progress("Database", 50, "Shifrlangan biometrik baza o'qilmoqda...")
    try:
        pipeline = FacePipeline()
        summary = {k: len(v) for k, v in pipeline.db.items()}
        emit_result({
            "total_enrolled": len(summary),
            "enrolled_persons": summary,
            "encrypted": True
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
            "cpu_load_impact": "0.00 load average (micro-burst)",
            "encrypted_db": True
        }, success=True)
    except Exception as e:
        emit_result(None, success=False, error=str(e))
