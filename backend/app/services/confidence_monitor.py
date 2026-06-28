from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

try:
    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import vision as mp_vision
    from mediapipe.tasks.python.core import base_options as mp_base_options
    from mediapipe.tasks.python.vision.core import image as mp_image_module
    from mediapipe.tasks.python.vision.core import vision_task_running_mode as mp_running_mode
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - runtime dependency check
    cv2 = None
    mp = None
    mp_vision = None
    mp_base_options = None
    mp_image_module = None
    mp_running_mode = None
    Image = None
    ImageDraw = None
    ImageFont = None

from app.services.mediapipe_assets import ensure_holistic_model
from app.services.visual_behavior_analysis import summarize_visual_samples

LandmarkList = list[Any]


@dataclass
class DisplayScores:
    eye: float = 0.0
    gesture: float = 0.0
    posture: float = 0.0
    confidence: float = 0.0
    arousal: float = 0.0
    stability: float = 0.0
    emotion: str = "未知"
    delivery: str = "未知"
    feedback: str = ""


@dataclass(frozen=True)
class CameraCaptureProfile:
    width: int
    height: int
    fps: int
    detect_every_frames: int
    jpeg_quality: int


def camera_capture_profile(*, low_performance: bool) -> CameraCaptureProfile:
    if low_performance:
        return CameraCaptureProfile(width=320, height=180, fps=8, detect_every_frames=6, jpeg_quality=56)
    return CameraCaptureProfile(width=640, height=360, fps=18, detect_every_frames=1, jpeg_quality=72)


def preview_write_interval(*, low_performance: bool) -> float:
    return 1.0 if low_performance else 0.5


class ConfidenceMonitor:
    def __init__(
        self,
        *,
        camera_index: int = 0,
        feedback_interval: float = 0.5,
        no_person_duration: float = 1.0,
        show_landmarks: bool = False,
        session_log_path: str | None = None,
        preview_frame_path: str | None = None,
        low_performance: bool = False,
        show_window: bool = False,
        ) -> None:
        self.camera_index = camera_index
        self.low_performance = low_performance
        self.capture_profile = camera_capture_profile(low_performance=low_performance)
        self.feedback_interval = max(feedback_interval, 1.0) if low_performance else max(feedback_interval, 0.5)
        self.no_person_duration = no_person_duration
        self.show_landmarks = show_landmarks
        self.show_window = show_window
        self.session_log_path = Path(session_log_path) if session_log_path else None
        self.preview_frame_path = Path(preview_frame_path) if preview_frame_path else None

        self.prev_hand_signature: np.ndarray | None = None
        self.prev_pose_signature: np.ndarray | None = None
        self.prev_face_signature: np.ndarray | None = None
        self.last_hand_movement = 0.0
        self.last_pose_movement = 0.0
        self.last_face_movement = 0.0
        self.gesture_ema = 0.6
        self.motion_ema = 0.0
        self.last_update_time = 0.0
        self.no_person_start_time: float | None = None
        self.person_detected = False
        self.lower_bounds = self._refresh_lower_bounds()
        self.display_scores = DisplayScores()
        self.recent_samples: list[dict[str, Any]] = []
        self._font_cache: dict[int, Any] = {}
        self._base_font = self._load_font()
        self._session_start = time.time()
        self._last_preview_write_time = 0.0

    def _append_sample(
        self,
        *,
        has_person: bool,
        has_face: bool,
        has_pose: bool,
        has_hand: bool,
        raised_hand: bool,
        gesture_event: str = "",
    ) -> None:
        sample = {
            "ts": time.time(),
            "elapsed_sec": round(time.time() - self._session_start, 3),
            "has_person": has_person,
            "has_face": has_face,
            "has_pose": has_pose,
            "has_hand": has_hand,
            "raised_hand": raised_hand,
            "gesture_event": gesture_event,
            "eye": round(self.display_scores.eye, 4),
            "gesture": round(self.display_scores.gesture, 4),
            "posture": round(self.display_scores.posture, 4),
            "confidence": round(self.display_scores.confidence, 4),
            "arousal": round(self.display_scores.arousal, 4),
            "stability": round(self.display_scores.stability, 4),
            "emotion": self.display_scores.emotion,
            "delivery": self.display_scores.delivery,
            "feedback": self.display_scores.feedback,
        }
        self.recent_samples.append(sample)
        self.recent_samples = self.recent_samples[-60:]
        sample["visual_summary"] = summarize_visual_samples(self.recent_samples).as_payload()
        if self.session_log_path is None:
            return
        try:
            self.session_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.session_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _write_preview_frame(self, frame, now: float) -> None:
        if self.preview_frame_path is None or cv2 is None:
            return
        if now - self._last_preview_write_time < preview_write_interval(low_performance=self.low_performance):
            return
        try:
            self.preview_frame_path.parent.mkdir(parents=True, exist_ok=True)
            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.capture_profile.jpeg_quality])
            if not ok:
                return
            tmp_path = self.preview_frame_path.with_suffix(".tmp")
            tmp_path.write_bytes(encoded.tobytes())
            tmp_path.replace(self.preview_frame_path)
            self._last_preview_write_time = now
        except Exception:
            pass

    @staticmethod
    def _dependency_error() -> RuntimeError:
        return RuntimeError("自信度识别依赖缺失。请安装: pip install -r backend/requirements-confidence.txt")

    @staticmethod
    def _refresh_lower_bounds() -> dict[str, float]:
        return {
            "eye": random.uniform(0.10, 0.15),
            "gesture": random.uniform(0.10, 0.15),
            "posture": random.uniform(0.10, 0.15),
        }

    @staticmethod
    def _load_font():
        if ImageFont is None:
            return None
        font_paths = [
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/msyh.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            "simhei.ttf",
        ]
        for path in font_paths:
            try:
                return ImageFont.truetype(path, 20)
            except Exception:
                continue
        return ImageFont.load_default()

    def _font_for_size(self, size: int):
        if self._base_font is None or ImageFont is None:
            return None
        if size in self._font_cache:
            return self._font_cache[size]
        try:
            path = getattr(self._base_font, "path", None)
            font = ImageFont.truetype(path, size) if path else self._base_font
        except Exception:
            font = self._base_font
        self._font_cache[size] = font
        return font

    def _draw_text(self, frame, text: str, position: tuple[int, int], color: tuple[int, int, int], size: int) -> Any:
        if Image is None or ImageDraw is None:
            cv2.putText(frame, text, position, cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1)
            return frame

        img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        draw.text(
            position,
            text,
            fill=(color[2], color[1], color[0]),
            font=self._font_for_size(size),
        )
        return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    @staticmethod
    def _eye_stability(face_landmarks: LandmarkList | None) -> float:
        if not face_landmarks or len(face_landmarks) < 264:
            return 0.0
        nose = face_landmarks[1]
        left_eye = face_landmarks[33]
        right_eye = face_landmarks[263]
        eye_center_x = (left_eye.x + right_eye.x) / 2
        yaw = nose.x - eye_center_x
        stability = max(0.0, 1.0 - abs(yaw) * 15.0)
        return min(1.0, stability)

    @staticmethod
    def _signature(landmarks: LandmarkList | None, ids: tuple[int, ...]) -> np.ndarray | None:
        if not landmarks or len(landmarks) <= max(ids):
            return None
        pts = np.array([[landmarks[i].x, landmarks[i].y, landmarks[i].z] for i in ids], dtype=np.float32)
        origin = pts[0]
        scale = np.linalg.norm(pts[-1] - origin) + 1e-6
        return ((pts - origin) / scale).reshape(-1)

    @staticmethod
    def _hand_signature(hand_landmarks: LandmarkList) -> np.ndarray:
        sample_ids = (0, 5, 9, 13, 17, 8, 12, 16, 20)
        signature = ConfidenceMonitor._signature(hand_landmarks, sample_ids)
        if signature is None:
            raise ValueError("insufficient_hand_landmarks")
        return signature

    def _movement_from_signature(self, current: np.ndarray | None, previous_attr: str) -> float:
        if current is None:
            setattr(self, previous_attr, None)
            return 0.0
        previous = getattr(self, previous_attr)
        setattr(self, previous_attr, current)
        if previous is None:
            return 0.0
        return float(np.mean(np.abs(current - previous)))

    def _gesture_smoothness(self, hand_landmarks: LandmarkList | None, pose_landmarks: LandmarkList | None) -> float:
        if hand_landmarks is None:
            self.prev_hand_signature = None
            self.last_hand_movement = 0.0
            self.gesture_ema = max(0.0, self.gesture_ema * 0.94)
            return 0.0
        try:
            curr_signature = self._hand_signature(hand_landmarks)
        except ValueError:
            self.prev_hand_signature = None
            self.last_hand_movement = 0.0
            self.gesture_ema = max(0.0, self.gesture_ema * 0.92)
            return self.gesture_ema

        movement = self._movement_from_signature(curr_signature, "prev_hand_signature")
        self.last_hand_movement = movement

        shoulder_factor = 1.0
        if pose_landmarks and len(pose_landmarks) > 12:
            ls = pose_landmarks[11]
            rs = pose_landmarks[12]
            shoulder_width = np.sqrt((ls.x - rs.x) ** 2 + (ls.y - rs.y) ** 2)
            shoulder_factor = float(np.clip(0.28 / max(0.12, shoulder_width), 0.85, 1.35))

        dead_zone = 0.013 * shoulder_factor
        jitter_scale = 8.5 / shoulder_factor
        movement_over = max(0.0, movement - dead_zone)
        raw = max(0.0, min(1.0, 1.0 - movement_over * jitter_scale))
        self.gesture_ema = 0.68 * self.gesture_ema + 0.32 * raw
        return self.gesture_ema

    @staticmethod
    def _posture_stability(pose_landmarks: LandmarkList | None) -> float:
        if not pose_landmarks or len(pose_landmarks) <= 12:
            return 0.0
        left_shoulder = pose_landmarks[11]
        right_shoulder = pose_landmarks[12]
        dx = right_shoulder.x - left_shoulder.x
        dy = right_shoulder.y - left_shoulder.y
        angle_deg = abs(np.arctan2(dy, dx) * 180.0 / np.pi)
        return max(0.0, 1.0 - angle_deg / 20.0)

    @staticmethod
    def _mouth_open(face_landmarks: LandmarkList | None) -> float:
        if not face_landmarks or len(face_landmarks) <= 14:
            return 0.0
        upper_lip = face_landmarks[13]
        lower_lip = face_landmarks[14]
        left_face = face_landmarks[234] if len(face_landmarks) > 454 else face_landmarks[0]
        right_face = face_landmarks[454] if len(face_landmarks) > 454 else face_landmarks[1]
        face_width = abs(right_face.x - left_face.x) + 1e-6
        return float(np.clip(abs(lower_lip.y - upper_lip.y) / face_width * 3.2, 0.0, 1.0))

    def _update_body_motion(
        self,
        *,
        face_landmarks: LandmarkList | None,
        pose_landmarks: LandmarkList | None,
    ) -> float:
        face_sig = self._signature(face_landmarks, (1, 33, 263, 13, 14))
        pose_sig = self._signature(pose_landmarks, (0, 11, 12, 15, 16)) if pose_landmarks else None
        self.last_face_movement = self._movement_from_signature(face_sig, "prev_face_signature")
        self.last_pose_movement = self._movement_from_signature(pose_sig, "prev_pose_signature")
        combined = self.last_hand_movement * 0.55 + self.last_pose_movement * 0.3 + self.last_face_movement * 0.15
        self.motion_ema = 0.7 * self.motion_ema + 0.3 * combined
        return self.motion_ema

    def _arousal_score(
        self,
        *,
        face_landmarks: LandmarkList | None,
        gesture_smoothness: float,
        gesture_event: str,
    ) -> float:
        mouth = self._mouth_open(face_landmarks)
        motion = min(1.0, self.motion_ema * 9.0)
        hand_burst = min(1.0, self.last_hand_movement * 20.0)
        event_boost = 0.15 if gesture_event in {"pointing", "chop", "fast_wave"} else 0.0
        stillness = max(0.0, 1.0 - gesture_smoothness)
        return float(np.clip(mouth * 0.34 + motion * 0.28 + hand_burst * 0.2 + stillness * 0.08 + event_boost, 0.0, 1.0))

    @staticmethod
    def _emotion_label(arousal: float, confidence: float, stability: float, gesture_event: str) -> str:
        if arousal >= 0.74 or gesture_event in {"pointing", "chop", "fast_wave"}:
            return "激动"
        if confidence < 0.35 and stability < 0.45:
            return "紧张"
        if arousal <= 0.35 and stability >= 0.55:
            return "平静"
        return "专注"

    @staticmethod
    def _feedback(
        eye: float,
        gesture: float,
        posture: float,
        confidence: float,
        arousal: float,
        stability: float,
    ) -> str:
        if confidence < 0.2:
            return "未检测到人体，请进入画面中央"
        if eye < 0.4:
            return "眼神飘忽，请注视镜头"
        if gesture < 0.4:
            return "手势过快或僵硬，请放慢动作"
        if posture < 0.5:
            return "身体倾斜，请坐直并保持双肩水平"
        if arousal > 0.78:
            return "情绪偏激烈，请放慢语速并用证据收束"
        if stability > 0.75 and confidence > 0.72:
            return "表达稳定自信，继续保持"
        return "状态良好，可加强停顿和关键词手势"

    @staticmethod
    def _detect_raise_hand(pose_landmarks: LandmarkList | None, hand_landmarks: LandmarkList | None) -> bool:
        if not pose_landmarks or not hand_landmarks or len(pose_landmarks) <= 11:
            return False
        wrist = hand_landmarks[0]
        shoulder = pose_landmarks[11]
        return wrist.y < shoulder.y

    @staticmethod
    def _finger_open_count(hand_landmarks: LandmarkList) -> int:
        if len(hand_landmarks) <= 20:
            return 0
        wrist = hand_landmarks[0]
        tips = (4, 8, 12, 16, 20)
        bases = (2, 5, 9, 13, 17)
        count = 0
        for tip_idx, base_idx in zip(tips, bases, strict=False):
            tip = hand_landmarks[tip_idx]
            base = hand_landmarks[base_idx]
            tip_dist = np.hypot(tip.x - wrist.x, tip.y - wrist.y)
            base_dist = np.hypot(base.x - wrist.x, base.y - wrist.y)
            if tip_dist > base_dist * 1.15:
                count += 1
        return count

    def _gesture_event(self, pose_landmarks: LandmarkList | None, hand_landmarks: LandmarkList | None) -> str:
        if not hand_landmarks or len(hand_landmarks) <= 20:
            return ""
        wrist = hand_landmarks[0]
        index_tip = hand_landmarks[8]
        pinky_tip = hand_landmarks[20]
        middle_tip = hand_landmarks[12]
        ring_tip = hand_landmarks[16]
        palm_span = abs(index_tip.x - pinky_tip.x)
        vertical_spread = abs(index_tip.y - wrist.y) + abs(pinky_tip.y - wrist.y)

        if pose_landmarks and len(pose_landmarks) > 12:
            left_shoulder = pose_landmarks[11]
            right_shoulder = pose_landmarks[12]
            shoulder_y = (left_shoulder.y + right_shoulder.y) / 2
            if wrist.y < shoulder_y:
                return "raised_hand"
            if wrist.y > shoulder_y and palm_span > 0.12 and vertical_spread < 0.35:
                return "shrug"

        if self.last_hand_movement > 0.055:
            return "fast_wave"

        open_count = self._finger_open_count(hand_landmarks)
        if open_count >= 4 and palm_span > 0.08:
            return "open_palm"

        index_extension = abs(index_tip.x - wrist.x) + abs(index_tip.y - wrist.y)
        other_extension = abs(middle_tip.x - wrist.x) + abs(middle_tip.y - wrist.y)
        if index_extension > 0.22 and index_extension > other_extension * 1.25:
            return "pointing"

        tips_x = [index_tip.x, middle_tip.x, ring_tip.x, pinky_tip.x]
        tips_y = [index_tip.y, middle_tip.y, ring_tip.y, pinky_tip.y]
        if max(tips_x) - min(tips_x) < 0.035 and max(tips_y) - min(tips_y) > 0.12:
            return "chop"
        return ""

    def _draw_selected_landmarks(
        self,
        frame,
        *,
        face_landmarks: LandmarkList | None,
        pose_landmarks: LandmarkList | None,
        left_hand_landmarks: LandmarkList | None,
        right_hand_landmarks: LandmarkList | None,
    ) -> None:
        h, w = frame.shape[:2]
        if face_landmarks and len(face_landmarks) > 1:
            nose = face_landmarks[1]
            cx, cy = int(nose.x * w), int(nose.y * h)
            cv2.circle(frame, (cx, cy), 5, (0, 255, 0), -1)
            cv2.putText(frame, "Nose", (cx + 5, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        if pose_landmarks and len(pose_landmarks) > 12:
            left_shoulder = pose_landmarks[11]
            right_shoulder = pose_landmarks[12]
            lx, ly = int(left_shoulder.x * w), int(left_shoulder.y * h)
            rx, ry = int(right_shoulder.x * w), int(right_shoulder.y * h)
            cv2.circle(frame, (lx, ly), 5, (0, 255, 0), -1)
            cv2.circle(frame, (rx, ry), 5, (0, 255, 0), -1)
            cv2.line(frame, (lx, ly), (rx, ry), (0, 255, 0), 1)
        hand = left_hand_landmarks if left_hand_landmarks else right_hand_landmarks
        if hand:
            wrist = hand[0]
            wx, wy = int(wrist.x * w), int(wrist.y * h)
            cv2.circle(frame, (wx, wy), 5, (0, 255, 0), -1)
            cv2.putText(frame, "Wrist", (wx + 5, wy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    @staticmethod
    def _draw_face_box(frame, face_landmarks: LandmarkList | None) -> None:
        if not face_landmarks:
            return
        h, w = frame.shape[:2]
        xs = [p.x for p in face_landmarks]
        ys = [p.y for p in face_landmarks]
        if not xs or not ys:
            return
        x1 = max(0, int(min(xs) * w) - 12)
        y1 = max(0, int(min(ys) * h) - 12)
        x2 = min(w - 1, int(max(xs) * w) + 12)
        y2 = min(h - 1, int(max(ys) * h) + 12)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 80), 2)
        cv2.putText(frame, "Face: detected", (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 80), 1)

    @staticmethod
    def _open_camera(camera_index: int, *, low_performance: bool = False):
        if cv2 is None:
            raise ConfidenceMonitor._dependency_error()
        profile = camera_capture_profile(low_performance=low_performance)
        backend_candidates = [
            getattr(cv2, "CAP_DSHOW", 700),
            getattr(cv2, "CAP_MSMF", 1400),
            getattr(cv2, "CAP_ANY", 0),
        ]
        errors: list[str] = []
        for backend in dict.fromkeys(backend_candidates):
            capture = cv2.VideoCapture(camera_index, backend)
            if not capture.isOpened():
                capture.release()
                errors.append(f"backend={backend}: not opened")
                continue
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, profile.width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, profile.height)
            capture.set(cv2.CAP_PROP_FPS, profile.fps)
            warmed = False
            for _ in range(8):
                ok, frame = capture.read()
                if ok and frame is not None:
                    warmed = True
                    break
                time.sleep(0.05)
            if warmed:
                return capture
            capture.release()
            errors.append(f"backend={backend}: opened but no frames")
        detail = "；".join(errors) or "no backend available"
        raise RuntimeError(f"无法打开摄像头 index={camera_index}，请检查权限或是否被其他程序占用（{detail}）")

    def _create_holistic_landmarker(self):
        if mp_vision is None or mp_base_options is None:
            raise self._dependency_error()
        model_path = ensure_holistic_model()
        options = mp_vision.HolisticLandmarkerOptions(
            base_options=mp_base_options.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp_running_mode.VisionTaskRunningMode.VIDEO,
            min_face_detection_confidence=0.45,
            min_pose_detection_confidence=0.45,
        )
        return mp_vision.HolisticLandmarker.create_from_options(options)

    def _update_scores(
        self,
        *,
        face_landmarks: LandmarkList | None,
        pose_landmarks: LandmarkList | None,
        hand_landmarks: LandmarkList | None,
        gesture_event: str,
        gesture_smoothness: float | None = None,
    ) -> None:
        eye = max(self._eye_stability(face_landmarks), self.lower_bounds["eye"])
        gesture_raw = (
            self._gesture_smoothness(hand_landmarks, pose_landmarks)
            if gesture_smoothness is None
            else gesture_smoothness
        )
        gesture = max(gesture_raw, self.lower_bounds["gesture"])
        posture = max(self._posture_stability(pose_landmarks), self.lower_bounds["posture"])
        motion = self._update_body_motion(face_landmarks=face_landmarks, pose_landmarks=pose_landmarks)
        arousal = self._arousal_score(face_landmarks=face_landmarks, gesture_smoothness=gesture, gesture_event=gesture_event)
        motion_stability = max(0.0, min(1.0, 1.0 - motion * 8.0))
        stability = max(0.0, min(1.0, eye * 0.28 + gesture * 0.28 + posture * 0.24 + motion_stability * 0.2))
        confidence = max(0.0, min(1.0, eye * 0.48 + posture * 0.22 + gesture * 0.16 + stability * 0.14))
        emotion = self._emotion_label(arousal, confidence, stability, gesture_event)
        delivery = summarize_visual_samples(
            [
                {
                    "has_face": bool(face_landmarks),
                    "has_pose": bool(pose_landmarks),
                    "has_hand": bool(hand_landmarks),
                    "confidence": confidence,
                    "eye": eye,
                    "gesture": gesture,
                    "posture": posture,
                    "arousal": arousal,
                    "stability": stability,
                    "gesture_event": gesture_event,
                    "emotion": emotion,
                }
            ]
        ).delivery
        feedback = self._feedback(eye, gesture, posture, confidence, arousal, stability)
        self.display_scores = DisplayScores(
            eye=eye,
            gesture=gesture,
            posture=posture,
            confidence=confidence,
            arousal=arousal,
            stability=stability,
            emotion=emotion,
            delivery=delivery,
            feedback=feedback,
        )

    def run(self) -> None:
        if cv2 is None or mp_image_module is None:
            raise self._dependency_error()

        holistic = self._create_holistic_landmarker()
        cap = None
        last_error: Exception | None = None
        for idx in dict.fromkeys([self.camera_index, 0, 1, 2]):
            try:
                cap = self._open_camera(idx, low_performance=self.low_performance)
                self.camera_index = idx
                break
            except RuntimeError as exc:
                last_error = exc
        if cap is None:
            raise RuntimeError("无法打开摄像头，请关闭浏览器预览、会议软件等占用源后重试") from last_error

        window_name = "AI辩手训练系统 - 自信度分析"
        if self.show_window:
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        self.last_update_time = time.time()
        timestamp_ms = 0
        frame_count = 0
        print("自信度识别已启动：网页预览模式。" if not self.show_window else "自信度识别已启动：按 q 退出。")

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    raise RuntimeError("摄像头读取中断，请检查摄像头连接或占用状态")
                frame = cv2.flip(frame, 1)
                frame_count += 1
                if frame_count % self.capture_profile.detect_every_frames != 0:
                    self._write_preview_frame(frame, time.time())
                    if self.show_window:
                        cv2.imshow(window_name, frame)
                        key = cv2.waitKey(1) & 0xFF
                        if key == ord("q"):
                            break
                        if key == ord("s"):
                            self.show_landmarks = not self.show_landmarks
                    continue

                rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                mp_image = mp_image_module.Image(image_format=mp_image_module.ImageFormat.SRGB, data=rgb)
                timestamp_ms += max(1, int(1000 / max(1, self.capture_profile.fps))) * self.capture_profile.detect_every_frames
                results = holistic.detect_for_video(mp_image, timestamp_ms)

                face_landmarks = results.face_landmarks or []
                pose_landmarks = results.pose_landmarks or []
                left_hand = results.left_hand_landmarks or []
                right_hand = results.right_hand_landmarks or []

                has_face = len(face_landmarks) > 0
                has_pose = len(pose_landmarks) > 0
                has_hand = len(left_hand) > 0 or len(right_hand) > 0
                has_person = has_face or has_pose or has_hand

                now = time.time()
                hand_landmarks = left_hand if left_hand else right_hand
                should_refresh_scores = now - self.last_update_time >= self.feedback_interval

                if not has_person:
                    if self.no_person_start_time is None:
                        self.no_person_start_time = now
                    elif now - self.no_person_start_time >= self.no_person_duration:
                        self.person_detected = False
                        self.prev_hand_signature = None
                        self.prev_pose_signature = None
                        self.prev_face_signature = None
                        self.gesture_ema = 0.6
                        self.motion_ema = 0.0
                        self.lower_bounds = self._refresh_lower_bounds()
                        self.display_scores = DisplayScores(feedback="未检测到人体，请进入画面中央")
                    if should_refresh_scores:
                        self.last_update_time = now
                else:
                    self.no_person_start_time = None
                    if not self.person_detected:
                        self.lower_bounds = self._refresh_lower_bounds()
                    self.person_detected = True

                    gesture = self._gesture_smoothness(hand_landmarks, pose_landmarks)
                    gesture_event = self._gesture_event(pose_landmarks, hand_landmarks) if has_person else ""
                    if should_refresh_scores:
                        self._update_scores(
                            face_landmarks=face_landmarks,
                            pose_landmarks=pose_landmarks,
                            hand_landmarks=hand_landmarks,
                            gesture_event=gesture_event,
                            gesture_smoothness=gesture,
                        )
                        self.last_update_time = now
                    else:
                        self._update_body_motion(face_landmarks=face_landmarks, pose_landmarks=pose_landmarks)

                raised_hand = bool(has_person and self._detect_raise_hand(pose_landmarks, hand_landmarks))
                gesture_event = self._gesture_event(pose_landmarks, hand_landmarks) if has_person else ""
                if should_refresh_scores:
                    self._append_sample(
                        has_person=has_person,
                        has_face=has_face,
                        has_pose=has_pose,
                        has_hand=has_hand,
                        raised_hand=raised_hand,
                        gesture_event=gesture_event,
                    )

                if has_face:
                    self._draw_face_box(frame, face_landmarks)

                if self.show_landmarks and has_person:
                    self._draw_selected_landmarks(
                        frame,
                        face_landmarks=face_landmarks,
                        pose_landmarks=pose_landmarks,
                        left_hand_landmarks=left_hand,
                        right_hand_landmarks=right_hand,
                    )

                self._write_preview_frame(frame, now)
                if self.show_window:
                    cv2.imshow(window_name, frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        break
                    if key == ord("s"):
                        self.show_landmarks = not self.show_landmarks
        finally:
            cap.release()
            if self.show_window:
                cv2.destroyAllWindows()
            holistic.close()  # type: ignore[union-attr]


def run_confidence_monitor(
    show_landmarks: bool = False,
    camera_index: int = 0,
    session_log_path: str | None = None,
    preview_frame_path: str | None = None,
    low_performance: bool = False,
    show_window: bool = False,
) -> None:
    monitor = ConfidenceMonitor(
        show_landmarks=show_landmarks,
        camera_index=camera_index,
        session_log_path=session_log_path,
        preview_frame_path=preview_frame_path,
        low_performance=low_performance,
        show_window=show_window,
    )
    monitor.run()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI 辩手自信度摄像头识别")
    parser.add_argument("--show-landmarks", action="store_true", help="默认显示关键点")
    parser.add_argument("--show-window", action="store_true", help="显示本地 OpenCV 窗口（默认仅网页预览）")
    parser.add_argument("--camera-index", type=int, default=0, help="摄像头索引")
    parser.add_argument("--session-log-path", type=str, default="", help="会话参数 JSONL 日志路径")
    parser.add_argument("--preview-frame-path", type=str, default="", help="Web 预览帧 JPG 输出路径")
    parser.add_argument("--low-performance", action="store_true", help="低性能模式（低分辨率/低帧率）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_confidence_monitor(
        show_landmarks=args.show_landmarks,
        show_window=args.show_window,
        camera_index=args.camera_index,
        session_log_path=args.session_log_path or None,
        preview_frame_path=args.preview_frame_path or None,
        low_performance=args.low_performance,
    )


if __name__ == "__main__":
    main()
