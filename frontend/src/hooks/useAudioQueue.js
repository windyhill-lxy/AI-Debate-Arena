import { useCallback, useRef, useState } from "react";
import { stripMarkdownForSubtitle } from "../utils/debateDisplay.js";
import { canStartQueuedAudio } from "./audioQueueControl.js";

/**
 * 顺序播放 TTS，避免重叠；支持暂停/继续/跳过/停止，不影响辩论主流程。
 */
export function useAudioQueue() {
  const queueRef = useRef([]);
  const playingRef = useRef(false);
  const audioRef = useRef(null);
  const generationRef = useRef(0);
  const enqueuedMessagesRef = useRef(new Set());
  const replayModeRef = useRef(false);
  const disabledRef = useRef(false);
  const pausedRef = useRef(false);
  const [current, setCurrent] = useState(null);
  const [queueLength, setQueueLength] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [isDisabled, setIsDisabled] = useState(false);
  const [subtitle, setSubtitle] = useState({
    text: "",
    progress: 0,
    speakerName: "",
    visibleChars: 0,
    messageId: null,
  });

  const stopActiveAudio = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.onended = null;
    audio.onerror = null;
    audio.ontimeupdate = null;
    try {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    } catch {
      // ignore teardown errors
    }
    audioRef.current = null;
  }, []);

  const updateSubtitleProgress = useCallback((audio, item) => {
    if (!audio.duration || !Number.isFinite(audio.duration)) return;
    const ratio = Math.min(1, Math.max(0, audio.currentTime / audio.duration));
    const plain = item.text || "";
    const chars = Math.floor(plain.length * ratio);
    setSubtitle({
      text: plain,
      progress: ratio,
      speakerName: item.speakerName || "",
      visibleChars: chars,
      messageId: item.messageId || null,
    });
  }, []);

  const playNext = useCallback((options = {}) => {
    const force = options.force === true;
    if (!force && !canStartQueuedAudio({
      playing: playingRef.current,
      disabled: disabledRef.current,
      paused: pausedRef.current,
      hasActiveAudio: Boolean(audioRef.current),
    })) {
      return;
    }
    if (force && (disabledRef.current || pausedRef.current)) return;

    const next = queueRef.current.shift();
    setQueueLength(queueRef.current.length);
    if (!next) {
      setCurrent(null);
      if (!playingRef.current) {
        setSubtitle({ text: "", progress: 0, speakerName: "", visibleChars: 0, messageId: null });
      }
      return;
    }

    const generation = ++generationRef.current;
    playingRef.current = true;
    setCurrent(next);

    if (force) {
      stopActiveAudio();
    }

    const audio = new Audio(next.url);
    audioRef.current = audio;

    const plain = stripMarkdownForSubtitle(next.text || "");
    setSubtitle({
      text: plain,
      progress: 0,
      speakerName: next.speakerName || "",
      visibleChars: 0,
      messageId: next.messageId || null,
    });

    const release = (advance) => {
      if (generation !== generationRef.current) return;
      playingRef.current = false;
      audioRef.current = null;
      setCurrent(null);
      if (advance && !disabledRef.current && !pausedRef.current) playNext();
      else if (queueRef.current.length === 0) {
        setSubtitle({ text: "", progress: 0, speakerName: "", visibleChars: 0, messageId: null });
      }
    };

    audio.ontimeupdate = () => updateSubtitleProgress(audio, { ...next, text: plain });
    audio.onended = () => release(true);
    audio.onerror = () => release(true);
    audio.play().catch(() => release(true));
  }, [stopActiveAudio, updateSubtitleProgress]);

  const enqueue = useCallback(
    (urls, meta = {}, options = {}) => {
      if (disabledRef.current) return;
      const list = Array.isArray(urls) ? urls : [urls];
      const messageId = meta.messageId;
      const allowRepeat = options.replay || replayModeRef.current;

      if (messageId && !allowRepeat && enqueuedMessagesRef.current.has(messageId)) {
        return;
      }
      if (messageId && !allowRepeat) {
        enqueuedMessagesRef.current.add(messageId);
      }

      for (const url of list) {
        if (url) {
          const segment = queueRef.current.filter((item) => item.messageId === messageId).length + 1;
          queueRef.current.push({
            url,
            segment,
            text: meta.text || "",
            speakerName: meta.speakerName || "",
            messageId,
            ...meta,
          });
        }
      }
      setQueueLength(queueRef.current.length);
      playNext();
    },
    [playNext],
  );

  const playMessage = useCallback(
    (urls, meta = {}) => {
      if (disabledRef.current) return;
      replayModeRef.current = true;
      generationRef.current += 1;
      stopActiveAudio();
      playingRef.current = false;
      pausedRef.current = false;
      setIsPaused(false);
      queueRef.current = [];
      setQueueLength(0);
      enqueue(urls, meta, { replay: true });
    },
    [enqueue, stopActiveAudio],
  );

  const setReplayMode = useCallback((enabled) => {
    replayModeRef.current = enabled;
    if (enabled) {
      enqueuedMessagesRef.current.clear();
    }
  }, []);

  const pause = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || audio.paused) return;
    audio.pause();
    pausedRef.current = true;
    setIsPaused(true);
  }, []);

  const resume = useCallback(() => {
    if (disabledRef.current) return;
    pausedRef.current = false;
    setIsPaused(false);
    const audio = audioRef.current;
    if (audio) {
      audio.play().catch(() => {});
      return;
    }
    if (!playingRef.current && queueRef.current.length) {
      playNext({ force: true });
    }
  }, [playNext]);

  const skipCurrent = useCallback(() => {
    generationRef.current += 1;
    pausedRef.current = false;
    setIsPaused(false);
    stopActiveAudio();
    playingRef.current = false;
    setCurrent(null);
    setQueueLength(queueRef.current.length);
    playNext({ force: true });
  }, [playNext, stopActiveAudio]);

  const skipAll = useCallback(() => {
    generationRef.current += 1;
    queueRef.current = [];
    pausedRef.current = false;
    setIsPaused(false);
    stopActiveAudio();
    playingRef.current = false;
    setCurrent(null);
    setQueueLength(0);
    setSubtitle({ text: "", progress: 0, speakerName: "", visibleChars: 0, messageId: null });
  }, [stopActiveAudio]);

  const clear = useCallback(() => {
    generationRef.current += 1;
    queueRef.current = [];
    if (!replayModeRef.current) {
      enqueuedMessagesRef.current.clear();
    }
    stopActiveAudio();
    playingRef.current = false;
    pausedRef.current = false;
    setIsPaused(false);
    setCurrent(null);
    setQueueLength(0);
    setSubtitle({ text: "", progress: 0, speakerName: "", visibleChars: 0, messageId: null });
  }, [stopActiveAudio]);

  const setDisabled = useCallback(
    (disabled) => {
      disabledRef.current = disabled;
      setIsDisabled(disabled);
      if (disabled) {
        clear();
      }
    },
    [clear],
  );

  return {
    enqueue,
    playMessage,
    setReplayMode,
    pause,
    resume,
    skipCurrent,
    skipAll,
    clear,
    setDisabled,
    current,
    queueLength,
    isPaused,
    isDisabled,
    subtitle,
  };
}
