import { useCallback, useEffect, useRef, useState } from "react";
import { useErrorDialog } from "../components/ErrorDialogProvider.jsx";

const CAMERA_OWNER_KEY = "ai-debate-camera-owner";
const CAMERA_LEASE_MS = 6000;
const CAMERA_RELEASE_DELAY_MS = 1500;
const TAB_CAMERA_ID =
  typeof globalThis !== "undefined" && globalThis.crypto?.randomUUID
    ? globalThis.crypto.randomUUID()
    : `tab-${Date.now()}-${Math.random().toString(16).slice(2)}`;

const sharedCamera = {
  stream: null,
  pending: null,
  refs: 0,
  heartbeat: null,
  releaseTimer: null,
};

const CAMERA_ERROR_HINTS = {
  NotFoundError: "未检测到摄像头设备，可继续辩论",
  DevicesNotFoundError: "未检测到摄像头设备，可继续辩论",
  NotAllowedError: "摄像头权限被拒绝，请在浏览器设置中允许",
  PermissionDeniedError: "摄像头权限被拒绝，请在浏览器设置中允许",
  NotReadableError: "摄像头被占用或硬件资源不足，请关闭其他摄像头应用后重试",
  AbortError: "摄像头启动被中断，请稍后重试",
  CameraInUseInThisBrowser: "摄像头已在本机另一个辩论页面使用，请关闭那边的摄像头或改用另一个设备",
};

function mapCameraError(err) {
  const name = err?.name || "";
  const message = String(err?.message || "");
  if (/0xC00D3704|MFT|硬件资源|hardware/i.test(message)) {
    return "摄像头硬件资源不足或被占用，可关闭其他视频应用后继续辩论";
  }
  return CAMERA_ERROR_HINTS[name] || message || "无法打开摄像头";
}

function readCameraOwner() {
  try {
    return JSON.parse(window.localStorage.getItem(CAMERA_OWNER_KEY) || "null");
  } catch {
    return null;
  }
}

function writeCameraOwner() {
  try {
    window.localStorage.setItem(
      CAMERA_OWNER_KEY,
      JSON.stringify({ id: TAB_CAMERA_ID, expiresAt: Date.now() + CAMERA_LEASE_MS }),
    );
  } catch {
    /* ignore storage failures */
  }
}

function claimCameraLease() {
  if (typeof window === "undefined") return true;
  const owner = readCameraOwner();
  if (owner?.id && owner.id !== TAB_CAMERA_ID && Number(owner.expiresAt || 0) > Date.now()) {
    const err = new Error("摄像头已在本机另一个辩论页面使用");
    err.name = "CameraInUseInThisBrowser";
    throw err;
  }
  writeCameraOwner();
  if (!sharedCamera.heartbeat) {
    sharedCamera.heartbeat = window.setInterval(writeCameraOwner, 2000);
  }
  return true;
}

function releaseCameraLease() {
  if (typeof window === "undefined") return;
  if (sharedCamera.heartbeat) {
    window.clearInterval(sharedCamera.heartbeat);
    sharedCamera.heartbeat = null;
  }
  try {
    const owner = readCameraOwner();
    if (!owner?.id || owner.id === TAB_CAMERA_ID) {
      window.localStorage.removeItem(CAMERA_OWNER_KEY);
    }
  } catch {
    /* ignore storage failures */
  }
}

async function openCameraStream() {
  let media = null;
  try {
    media = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false,
    });
  } catch (primaryErr) {
    try {
      media = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    } catch {
      throw primaryErr;
    }
  }
  return media;
}

async function acquireSharedCamera() {
  if (typeof window !== "undefined" && sharedCamera.releaseTimer) {
    window.clearTimeout(sharedCamera.releaseTimer);
    sharedCamera.releaseTimer = null;
  }
  claimCameraLease();
  sharedCamera.refs += 1;
  if (sharedCamera.stream) return sharedCamera.stream;
  if (!sharedCamera.pending) {
    sharedCamera.pending = openCameraStream()
      .then((stream) => {
        sharedCamera.stream = stream;
        stream.getTracks().forEach((track) => {
          track.addEventListener(
            "ended",
            () => {
              if (sharedCamera.stream === stream) {
                sharedCamera.stream = null;
                sharedCamera.refs = 0;
                releaseCameraLease();
              }
            },
            { once: true },
          );
        });
        return stream;
      })
      .finally(() => {
        sharedCamera.pending = null;
      });
  }
  try {
    return await sharedCamera.pending;
  } catch (error) {
    sharedCamera.refs = Math.max(0, sharedCamera.refs - 1);
    if (sharedCamera.refs === 0) releaseCameraLease();
    throw error;
  }
}

function releaseSharedCamera() {
  sharedCamera.refs = Math.max(0, sharedCamera.refs - 1);
  if (sharedCamera.refs > 0) return;
  if (typeof window === "undefined") {
    sharedCamera.stream?.getTracks().forEach((track) => track.stop());
    sharedCamera.stream = null;
    sharedCamera.pending = null;
    releaseCameraLease();
    return;
  }
  if (sharedCamera.releaseTimer) window.clearTimeout(sharedCamera.releaseTimer);
  sharedCamera.releaseTimer = window.setTimeout(() => {
    if (sharedCamera.refs > 0) return;
    sharedCamera.stream?.getTracks().forEach((track) => track.stop());
    sharedCamera.stream = null;
    sharedCamera.pending = null;
    sharedCamera.releaseTimer = null;
    releaseCameraLease();
  }, CAMERA_RELEASE_DELAY_MS);
}

export function useLocalCamera({ enabled = true, popupOnError = true } = {}) {
  const [stream, setStream] = useState(null);
  const [error, setError] = useState("");
  const [hasDevice, setHasDevice] = useState(true);
  const streamRef = useRef(null);
  const ownsStreamRef = useRef(false);
  const startPromiseRef = useRef(null);
  const stopRequestedRef = useRef(!enabled);
  const popupReportedRef = useRef(false);
  const { reportError } = useErrorDialog();

  const stopStream = useCallback(() => {
    stopRequestedRef.current = true;
    if (ownsStreamRef.current) {
      ownsStreamRef.current = false;
      releaseSharedCamera();
    }
    streamRef.current = null;
    setStream(null);
  }, []);

  const startStream = useCallback(async () => {
    if (!enabled) return null;
    if (streamRef.current) return streamRef.current;
    if (startPromiseRef.current) return startPromiseRef.current;
    if (!navigator.mediaDevices?.getUserMedia) {
      const message = "当前环境不支持摄像头";
      setError(message);
      setHasDevice(false);
      if (popupOnError && !popupReportedRef.current) {
        popupReportedRef.current = true;
        reportError({ title: "摄像头不可用", message, source: "useLocalCamera.unsupported" });
      }
      return null;
    }
    stopRequestedRef.current = false;
    startPromiseRef.current = (async () => {
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoInputs = devices.filter((d) => d.kind === "videoinput");
        if (!videoInputs.length) {
          const message = "未检测到摄像头设备，可继续辩论";
          setHasDevice(false);
          setError(message);
          if (popupOnError && !popupReportedRef.current) {
            popupReportedRef.current = true;
            reportError({ title: "摄像头不可用", message, source: "useLocalCamera.noDevice" });
          }
          return null;
        }
        setHasDevice(true);
        const media = await acquireSharedCamera();
        if (stopRequestedRef.current) {
          releaseSharedCamera();
          return null;
        }
        ownsStreamRef.current = true;
        streamRef.current = media;
        setStream(media);
        setError("");
        return media;
      } catch (err) {
        const message = mapCameraError(err);
        setError(message);
        if (err?.name === "NotFoundError" || err?.name === "DevicesNotFoundError") {
          setHasDevice(false);
        }
        if (popupOnError && !popupReportedRef.current) {
          popupReportedRef.current = true;
          reportError(
            {
              title: "摄像头启动失败",
              message,
              details: err?.stack || err?.message || "",
              source: "useLocalCamera.startStream",
            },
            { dedupeKey: `local-camera:${message}`, throttleMs: 30000 },
          );
        }
        return null;
      } finally {
        startPromiseRef.current = null;
      }
    })();
    return startPromiseRef.current;
  }, [enabled, popupOnError, reportError]);

  useEffect(() => {
    if (!enabled) {
      stopStream();
      return undefined;
    }
    startStream();
    return () => stopStream();
  }, [enabled, startStream, stopStream]);

  return { stream, error, hasDevice, startStream, stopStream };
}
