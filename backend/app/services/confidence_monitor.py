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
except Exception:  # pragma: no cover - 依赖缺失时仅用于运行期提示
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

LandmarkList = list[Any]


@dataclass
class DisplayScores:
    eye: float = 0.0
    gesture: float = 0.0
    posture: float = 0.0
    confidence: float = 0.0
    feedback: str = ""


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
        self.feedback_interval = max(feedback_interval, 0.8) if low_performance else feedback_interval
        self.no_person_duration = no_person_duration
        self.show_landmarks = show_landmarks
        self.show_window = show_window
        self.session_log_path = Path(session_log_path) if session_log_path else None
        self.preview_frame_path = Path(preview_frame_path) if preview_frame_path else None

        self.prev_hand_signature: np.ndarray | None = None
        self.gesture_ema = 0.6
        self.last_update_time = 0.0
        self.no_person_start_time: float | None = None
        self.person_detected = False
        self.lower_bounds = self._refresh_lower_bounds()
        self.display_scores = DisplayScores()
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
        if self.session_log_path is None:
            return
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
            "feedback": self.display_scores.feedback,
        }
        try:
            self.session_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.session_log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        except Exception:
            # 日志写入失败不应影响主训练循环。
            pass

    def _write_preview_frame(self, frame, now: float) -> None:
        if self.preview_frame_path is None:
            return
        if now - self._last_preview_write_time < 0.12:
            return
        try:
            self.preview_frame_path.parent.mkdir(parents=True, exist_ok=True)
            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
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
        return RuntimeError(
            "自信度训练依赖缺失。请安装: pip install -r backend/requirements-confidence.txt"
        )

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
            # truetype 字体对象通常有 path，默认字体没有。
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
    def _hand_signature(hand_landmarks: LandmarkList) -> np.ndarray:
        # 选取掌心与指尖关键点，减少单点抖动造成的误判。
        sample_ids = (0, 5, 9, 13, 17, 8, 12, 16, 20)
        if len(hand_landmarks) <= max(sample_ids):
            raise ValueError("insufficient_hand_landmarks")
        pts = np.array(
            [[hand_landmarks[i].x, hand_landmarks[i].y, hand_landmarks[i].z] for i in sample_ids],
            dtype=np.float32,
        )
        wrist = pts[0]
        palm_scale = np.linalg.norm(pts[2] - wrist) + 1e-6
        pts = (pts - wrist) / palm_scale
        return pts.reshape(-1)

    def _gesture_smoothness(self, hand_landmarks: LandmarkList | None, pose_landmarks: LandmarkList | None) -> float:
        if hand_landmarks is None:
            self.prev_hand_signature = None
            self.gesture_ema = max(0.0, self.gesture_ema * 0.94)
            return 0.0
        try:
            curr_signature = self._hand_signature(hand_landmarks)
        except ValueError:
            # 个别帧关键点数量不足（手被遮挡/检测不完整）时，平滑降级，不中断训练进程。
            self.prev_hand_signature = None
            self.gesture_ema = max(0.0, self.gesture_ema * 0.92)
            return self.gesture_ema
        if self.prev_hand_signature is None:
            self.prev_hand_signature = curr_signature
            self.gesture_ema = 0.8
            return self.gesture_ema
        movement = float(np.mean(np.abs(curr_signature - self.prev_hand_signature)))
        self.prev_hand_signature = curr_signature

        # 肩宽越小（离镜头更远）时，适当放宽手势移动阈值。
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
    def _feedback(eye: float, gesture: float, posture: float, confidence: float) -> str:
        if confidence < 0.2:
            return "未检测到人体，请进入画面中央"
        if eye < 0.4:
            return "眼神飘忽，请注视镜头"
        if gesture < 0.4:
            return "手势过快或僵硬，请放慢动作"
        if posture < 0.5:
            return "身体倾斜，请坐直并保持双肩水平"
        if confidence > 0.8:
            return "表现非常自信！继续保持"
        if confidence > 0.6:
            return "状态良好，可再加强眼神接触"
        return "保持当前状态，注意放松肩膀"

    @staticmethod
    def _detect_raise_hand(pose_landmarks: LandmarkList | None, hand_landmarks: LandmarkList | None) -> bool:
        if not pose_landmarks or not hand_landmarks or len(pose_landmarks) <= 11:
            return False
        wrist = hand_landmarks[0]
        shoulder = pose_landmarks[11]
        return wrist.y < shoulder.y

    @staticmethod
    def _gesture_event(pose_landmarks: LandmarkList | None, hand_landmarks: LandmarkList | None) -> str:
        if not hand_landmarks or len(hand_landmarks) <= 20:
            return ""
        wrist = hand_landmarks[0]
        index_tip = hand_landmarks[8]
        pinky_tip = hand_landmarks[20]
        middle_tip = hand_landmarks[12]
        palm_span = abs(index_tip.x - pinky_tip.x)
        vertical_spread = abs(index_tip.y - wrist.y) + abs(pinky_tip.y - wrist.y)
        if pose_landmarks and len(pose_landmarks) > 12:
            left_shoulder = pose_landmarks[11]
            right_shoulder = pose_landmarks[12]
            shoulder_y = (left_shoulder.y + right_shoulder.y) / 2
            if wrist.y > shoulder_y and palm_span > 0.12 and vertical_spread < 0.35:
                return "shrug"
        index_extension = abs(index_tip.x - wrist.x) + abs(index_tip.y - wrist.y)
        other_extension = abs(middle_tip.x - wrist.x) + abs(middle_tip.y - wrist.y)
        if index_extension > 0.22 and index_extension > other_extension * 1.25:
            return "pointing"
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
            cv2.putText(frame, "L_Shoulder", (lx + 5, ly), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.putText(frame, "R_Shoulder", (rx + 5, ry), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
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
        backends = [getattr(cv2, "CAP_DSHOW", 700), getattr(cv2, "CAP_MSMF", 1400), 0]
        for backend in backends:
            capture = cv2.VideoCapture(camera_index, backend) if backend else cv2.VideoCapture(camera_index)
            if capture.isOpened():
                if low_performance:
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    capture.set(cv2.CAP_PROP_FPS, 15)
                else:
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                return capture
        raise RuntimeError(f"无法打开摄像头 index={camera_index}，请检查权限或是否被其他程序占用")

    def _create_holistic_landmarker(self):
        if mp_vision is None or mp_base_options is None:
            raise self._dependency_error()
        model_path = ensure_holistic_model()
        options = mp_vision.HolisticLandmarkerOptions(
            base_options=mp_base_options.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp_running_mode.VisionTaskRunningMode.VIDEO,
            min_face_detection_confidence=0.5,
            min_pose_detection_confidence=0.5,
        )
        return mp_vision.HolisticLandmarker.create_from_options(options)

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
            raise RuntimeError(
                "无法打开摄像头，请关闭占用摄像头的程序（如浏览器预览/会议软件）后重试"
            ) from last_error

        window_name = "AI辩手训练系统 - 自信度分析"
        if self.show_window:
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        self.last_update_time = time.time()
        timestamp_ms = 0
        if self.show_window:
            print("自信度训练启动：按 q 退出，按 s 切换关键点显示。")
        else:
            print("自信度训练启动：网页预览模式（不弹本地窗口）。")

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frame = cv2.flip(frame, 1)
                rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                mp_image = mp_image_module.Image(image_format=mp_image_module.ImageFormat.SRGB, data=rgb)
                timestamp_ms += 33
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
                        self.gesture_ema = 0.6
                        self.lower_bounds = self._refresh_lower_bounds()
                        self.display_scores = DisplayScores(feedback="未检测到人体，请进入画面中央")
                    if should_refresh_scores:
                        self.last_update_time = now
                else:
                    self.no_person_start_time = None
                    if not self.person_detected:
                        self.lower_bounds = self._refresh_lower_bounds()
                    self.person_detected = True

                    eye = max(self._eye_stability(face_landmarks), self.lower_bounds["eye"])
                    gesture = max(self._gesture_smoothness(hand_landmarks, pose_landmarks), self.lower_bounds["gesture"])
                    posture = max(self._posture_stability(pose_landmarks), self.lower_bounds["posture"])
                    # 教室场景下常见仅脸部入镜，适度降低手势/姿态权重，避免对总分惩罚过重。
                    confidence = max(0.0, min(1.0, eye * 0.65 + gesture * 0.2 + posture * 0.15))
                    feedback = self._feedback(eye, gesture, posture, confidence)

                    if should_refresh_scores:
                        self.display_scores = DisplayScores(
                            eye=eye,
                            gesture=gesture,
                            posture=posture,
                            confidence=confidence,
                            feedback=feedback,
                        )
                        self.last_update_time = now

                raised_hand = bool(has_person and self._detect_raise_hand(pose_landmarks, hand_landmarks))
                gesture_event = self._gesture_event(pose_landmarks, hand_landmarks) if has_person else ""
                if should_refresh_scores:
                    # 按 feedback_interval 固定采样，确保 WebUI 可稳定读取 latest_sample。
                    self._append_sample(
                        has_person=has_person,
                        has_face=has_face,
                        has_pose=has_pose,
                        has_hand=has_hand,
                        raised_hand=raised_hand,
                        gesture_event=gesture_event,
                    )

                overlay = frame.copy()
                cv2.rectangle(overlay, (0, 0), (560, 200), (0, 0, 0), -1)
                frame = cv2.addWeighted(overlay, 0.5, frame, 0.5, 0)

                frame = self._draw_text(
                    frame,
                    f"自信度: {int(self.display_scores.confidence * 100)}%",
                    (15, 40),
                    (0, 255, 0),
                    24,
                )
                frame = self._draw_text(
                    frame,
                    f"眼神: {int(self.display_scores.eye * 100)}%  手势: {int(self.display_scores.gesture * 100)}%",
                    (15, 80),
                    (255, 255, 255),
                    18,
                )
                frame = self._draw_text(
                    frame,
                    f"姿态: {int(self.display_scores.posture * 100)}%",
                    (15, 110),
                    (255, 255, 255),
                    18,
                )
                face_status = "人脸: 已检测" if has_face else "人脸: 未检测"
                frame = self._draw_text(
                    frame,
                    face_status,
                    (15, 135),
                    (90, 255, 120) if has_face else (180, 180, 180),
                    18,
                )
                frame = self._draw_text(frame, self.display_scores.feedback, (15, 162), (0, 0, 255), 18)
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

                status = "关键点显示: 开启" if self.show_landmarks else "关键点显示: 关闭"
                cv2.putText(frame, f"[S] {status}", (15, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                if raised_hand:
                    frame = self._draw_text(frame, "举手发言!", (430, 80), (0, 255, 255), 20)

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
    parser = argparse.ArgumentParser(description="AI 辩手自信度摄像头训练")
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
