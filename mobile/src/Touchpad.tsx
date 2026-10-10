import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import {
  Animated,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  useWindowDimensions,
  View,
  type GestureResponderEvent,
} from 'react-native';
import { DotGrid } from './DotGrid';
import {
  IconChevronDown,
  IconChevronLeft,
  IconChevronRight,
  IconChevronUp,
  IconPointer,
  IconSettings,
  IconVolume,
  IconVolumeMute,
  IconWifi,
} from './Icons';
import type { ClicxMessage } from './protocol';
import { RemoteKeyboard } from './RemoteKeyboard';
import { StreamDeck } from './StreamDeck';
import { DokkeBackdrop, DokkeCard } from './DokkeGlass';
import { DOKKE_GLASS } from './dokkeTokens';
import { loadSurfaceMode, saveSurfaceMode, THEME, type DeckPage, type SurfaceMode } from './deckConfig';
import { VolumePill } from './VolumePill';
import { type Palette, useStyles, useTheme } from './palette';

const LASER_COLORS = [THEME.red, THEME.green, THEME.blueBright, THEME.orange] as const;

/**
 * Pad dot / glow colors (settings palette).
 *
 * Literal hexes on purpose: the forest repaint aliased orange/yellow/green/
 * blue/pink to one moss and purple/gray to another, so naming them through
 * THEME produced ten swatches with four distinct colors — and duplicate React
 * keys, since the swatch list is keyed by color.
 */
const PAD_COLORS = [
  'auto',
  '#FFFFFF',
  '#E8EDE4',
  '#9CB080',
  '#618764',
  '#2B5748',
  '#C45C4A',
] as const;

const LASER_SIZE_MIN = 24;
const LASER_SIZE_MAX = 96;
const LASER_SIZE_STEP = 8;

export type TouchpadProps = {
  send: (msg: ClicxMessage) => void;
  sendMove: (dx: number, dy: number) => void;
  sensitivity: number;
  onSensitivityChange: (value: number) => void;
  invertScroll: boolean;
  onInvertScrollChange: (value: boolean) => void;
  acceleration: boolean;
  onAccelerationChange: (value: boolean) => void;
  doubleClick: boolean;
  onDoubleClickChange: (value: boolean) => void;
  holdToSelect: boolean;
  onHoldToSelectChange: (value: boolean) => void;
  landscapeLock: boolean;
  onLandscapeLockChange: (value: boolean) => void;
  classicMouse: boolean;
  onClassicMouseChange: (value: boolean) => void;
  keyboardOnEdit: boolean;
  onKeyboardOnEditChange: (value: boolean) => void;
  textFieldFocused: boolean;
  padColor: string;
  onPadColorChange: (value: string) => void;
  laserSize: number;
  onLaserSizeChange: (value: number) => void;
  onDisconnect: () => void;
  hostInfo?: string | null;
  deckPages?: DeckPage[] | null;
  onHome?: () => void;
};

type Point = { x: number; y: number };

/** Laptop trackpad: tap = click; second tap within window = double-click. */
const DOUBLE_TAP_MS = 320;
/** Finger may jitter this far and still count as a tap. */
const TAP_SLOP = 36;
/** Hold-to-select only after this; quick taps never wait. */
const HOLD_MS = 450;
const PINCH_THRESHOLD = 14;
/** Pinch must clearly beat mid-point travel to count as zoom (not scroll). */
const PINCH_VS_SCROLL = 1.6;
/** Once scrolling, need an even clearer pinch to switch. */
const PINCH_BREAK_SCROLL = 2.4;
/** Accumulated pinch (px) before sending first zoom step. */
const PINCH_FIRE = 18;
/** How long the tap ripple stays. */
const TAP_FLASH_MS = 220;
/** Fade-in when finger lands. */
const FADE_IN_MS = 110;
/** Fade-out when finger lifts. */
const FADE_OUT_MS = 200;
/** 3/4-finger swipe distance (px) to fire OS gesture. */
const MULTI_SWIPE = 28;
/** After a OS swipe gesture, ignore more until lift. */
const SWIPE_COOLDOWN_MS = 320;

export const SENS_MIN = 0.6;
export const SENS_MAX = 4.0;
export const SENS_DEFAULT = 2.2;
export const LASER_SIZE_DEFAULT = 44;
/** `auto` follows the host's app colour; anything else is a fixed pick. */
export const PAD_COLOR_DEFAULT = 'auto';

const SURFACE_SWITCH_KEY = 'clicx.surfaceSwitch.v1';
const QUICK_ACTIONS_KEY = 'clicx.quickActions.v1';

/** A chrome toggle the user set, remembered across launches. */
function usePersistedFlag(key: string, initial: boolean) {
  const [value, setValue] = useState(initial);

  useEffect(() => {
    AsyncStorage.getItem(key)
      .then((raw) => {
        if (raw === 'on' || raw === 'off') setValue(raw === 'on');
      })
      .catch(() => {});
  }, [key]);

  const set = useCallback(
    (on: boolean) => {
      setValue(on);
      void AsyncStorage.setItem(key, on ? 'on' : 'off').catch(() => {});
    },
    [key],
  );

  return [value, set] as const;
}
const SENS_STEP = 0.2;

function dist(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function midpoint(a: Point, b: Point): Point {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function centroid(pts: Point[]): Point {
  let x = 0;
  let y = 0;
  for (const p of pts) {
    x += p.x;
    y += p.y;
  }
  const n = Math.max(1, pts.length);
  return { x: x / n, y: y / n };
}

function accelerateDelta(
  rawDx: number,
  rawDy: number,
  dtMs: number,
  sensitivity: number,
  useAccel: boolean,
): { dx: number; dy: number } {
  const mag = Math.hypot(rawDx, rawDy);
  if (mag === 0) return { dx: 0, dy: 0 };
  if (!useAccel) {
    return { dx: rawDx * sensitivity, dy: rawDy * sensitivity };
  }
  const dt = dtMs > 0 && dtMs < 40 ? dtMs : 8;
  const speed = mag / dt;
  let gain: number;
  if (speed < 0.12) gain = 1.0 + speed * 1.5;
  else if (speed < 0.45) gain = 1.18 + (speed - 0.12) * 2.8;
  else gain = Math.min(2.0 + (speed - 0.45) * 1.6, 2.8);
  const scale = sensitivity * gain;
  return { dx: rawDx * scale, dy: rawDy * scale };
}

function RoundBtn({
  size = 56,
  active,
  onPress,
  onLongPress,
  children,
}: {
  size?: number;
  active?: boolean;
  onPress: () => void;
  onLongPress?: () => void;
  children: ReactNode;
}) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  return (
    <Pressable
      onPress={onPress}
      onLongPress={onLongPress}
      delayLongPress={280}
      style={({ pressed }) => [
        styles.roundBtn,
        { width: size, height: size, borderRadius: size / 2 },
        active && styles.roundBtnActive,
        pressed && styles.roundBtnPressed,
      ]}
    >
      {children}
    </Pressable>
  );
}

export function Touchpad({
  send,
  sendMove,
  sensitivity,
  onSensitivityChange,
  invertScroll,
  onInvertScrollChange,
  acceleration,
  onAccelerationChange,
  doubleClick,
  onDoubleClickChange,
  holdToSelect,
  onHoldToSelectChange,
  landscapeLock,
  onLandscapeLockChange,
  classicMouse,
  onClassicMouseChange,
  keyboardOnEdit,
  onKeyboardOnEditChange,
  textFieldFocused,
  padColor,
  onPadColorChange,
  laserSize,
  onLaserSizeChange,
  onDisconnect,
  hostInfo,
  deckPages,
  onHome,
}: TouchpadProps) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  // The pad stays black; its dots and touch ring are what carry the app colour.
  const dots = padColor === 'auto' ? THEME.orange : padColor;
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Chrome the user can put away to give the pad the whole screen. Both only
  // come back from settings, which is also the only way to switch surface once
  // the segment is hidden.
  const [showSurfaceSwitch, toggleSurfaceSwitch] = usePersistedFlag(
    SURFACE_SWITCH_KEY,
    true,
  );
  const [showQuickActions, toggleQuickActions] = usePersistedFlag(
    QUICK_ACTIONS_KEY,
    true,
  );
  const [surfaceMode, setSurfaceMode] = useState<SurfaceMode>('trackpad');
  const [controlsOpen, setControlsOpen] = useState(true);
  const [keyboardOpen, setKeyboardOpen] = useState(false);
  const [showVolumePill, setShowVolumePill] = useState(false);
  const [volLevel, setVolLevel] = useState(70);
  const [volMuted, setVolMuted] = useState(false);
  /** -1 = laser off; else index into LASER_COLORS */
  const [laserIdx, setLaserIdx] = useState(-1);
  const [padSize, setPadSize] = useState({ w: 0, h: 0 });
  const [fingers, setFingers] = useState<{ x: number; y: number }[]>([]);
  /** Lightweight tap ripple — does NOT rebuild DotGrid (that was stalling touchEnd). */
  const [ripple, setRipple] = useState<{ x: number; y: number; id: number } | null>(
    null,
  );
  const [leftPressed, setLeftPressed] = useState(false);
  const [rightPressed, setRightPressed] = useState(false);
  const { width, height } = useWindowDimensions();
  const isLandscape = width > height;

  const mode = useRef<
    | 'none'
    | 'move'
    | 'scroll'
    | 'pinch'
    | 'drag'
    | 'swipe3'
    | 'swipe4'
  >('none');
  const startPos = useRef<Point | null>(null);
  const lastPos = useRef<Point | null>(null);
  const lastTime = useRef(0);
  const gestureStartAt = useRef(0);
  const lastMid = useRef<Point | null>(null);
  const lastPinch = useRef(0);
  const moved = useRef(false);
  const dragging = useRef(false);
  const holdTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingClickTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastTapAt = useRef(0);
  /** Peak finger count during this gesture (for tap / swipe classification). */
  const maxFingers = useRef(1);
  const fingerCount = useRef(0);
  const padRef = useRef<View>(null);
  const padOffset = useRef({ x: 0, y: 0 });
  const classicLeftHold = useRef<ReturnType<typeof setTimeout> | null>(null);
  const classicLeftDragging = useRef(false);
  const fingerRaf = useRef<number | null>(null);
  const gestureActive = useRef(false);
  const tapFlashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Accumulated 2/3-finger mid travel for swipe detection. */
  const multiTravel = useRef({ x: 0, y: 0 });
  const swipeArmed = useRef(true);
  const lastSwipeAt = useRef(0);
  const pinchAccum = useRef(0);
  /** Track fingers by identifier — RN often drops extras from `touches` alone. */
  const activeTouches = useRef<Map<string, Point>>(new Map());
  const sensRef = useRef(sensitivity);
  const invertRef = useRef(invertScroll);
  const accelRef = useRef(acceleration);
  const doubleRef = useRef(doubleClick);
  const holdSelectRef = useRef(holdToSelect);
  sensRef.current = sensitivity;
  invertRef.current = invertScroll;
  accelRef.current = acceleration;
  doubleRef.current = doubleClick;
  holdSelectRef.current = holdToSelect;

  useEffect(
    () => () => {
      if (fingerRaf.current != null) cancelAnimationFrame(fingerRaf.current);
      if (moveFlushRaf.current != null) cancelAnimationFrame(moveFlushRaf.current);
    },
    [],
  );

  useEffect(() => {
    loadSurfaceMode().then(setSurfaceMode);
  }, []);

  const switchSurface = (mode: SurfaceMode) => {
    setSurfaceMode(mode);
    void saveSurfaceMode(mode);
    if (mode === 'deck') {
      setKeyboardOpen(false);
      setShowVolumePill(false);
    }
  };

  useEffect(() => {
    if (!keyboardOnEdit) {
      setKeyboardOpen(false);
      return;
    }
    if (textFieldFocused) setKeyboardOpen(true);
  }, [keyboardOnEdit, textFieldFocused]);

  const clearHold = () => {
    if (holdTimer.current) {
      clearTimeout(holdTimer.current);
      holdTimer.current = null;
    }
  };

  const clearPendingClick = () => {
    if (pendingClickTimer.current) {
      clearTimeout(pendingClickTimer.current);
      pendingClickTimer.current = null;
    }
  };

  const pendingVisual = useRef<Point[] | null>(null);
  const reactFade = useRef(new Animated.Value(0)).current;
  const fadeToken = useRef(0);

  const fadeReactionIn = () => {
    fadeToken.current += 1;
    Animated.timing(reactFade, {
      toValue: 1,
      duration: FADE_IN_MS,
      useNativeDriver: true,
    }).start();
  };

  const fadeReactionOut = (clearAfter = true) => {
    const token = ++fadeToken.current;
    Animated.timing(reactFade, {
      toValue: 0,
      duration: FADE_OUT_MS,
      useNativeDriver: true,
    }).start(({ finished }) => {
      if (!finished || token !== fadeToken.current) return;
      if (clearAfter) {
        pendingVisual.current = null;
        setFingers([]);
        setRipple(null);
      }
    });
  };

  /** Coalesce visual updates to 1/frame — DotGrid only rebuilds a small reactive patch. */
  const updateFingersVisual = (pagePts: Point[], { force: _force = false } = {}) => {
    const ox = padOffset.current.x;
    const oy = padOffset.current.y;
    pendingVisual.current = pagePts.map((p) => ({
      x: p.x - ox,
      y: p.y - oy,
    }));
    if (fingerRaf.current != null) return;
    fingerRaf.current = requestAnimationFrame(() => {
      fingerRaf.current = null;
      const pts = pendingVisual.current;
      if (pts) setFingers(pts);
    });
  };

  /** Accumulate dx/dy and flush once per frame — avoids WS + JS storms on fast flicks. */
  const pendingMove = useRef({ dx: 0, dy: 0 });
  const moveFlushRaf = useRef<number | null>(null);

  const queueSendMove = (dx: number, dy: number) => {
    pendingMove.current.dx += dx;
    pendingMove.current.dy += dy;
    if (moveFlushRaf.current != null) return;
    moveFlushRaf.current = requestAnimationFrame(() => {
      moveFlushRaf.current = null;
      const x = pendingMove.current.dx;
      const y = pendingMove.current.dy;
      pendingMove.current.dx = 0;
      pendingMove.current.dy = 0;
      if (x !== 0 || y !== 0) sendMove(x, y);
    });
  };

  const flushPendingMove = () => {
    if (moveFlushRaf.current != null) {
      cancelAnimationFrame(moveFlushRaf.current);
      moveFlushRaf.current = null;
    }
    const x = pendingMove.current.dx;
    const y = pendingMove.current.dy;
    pendingMove.current.dx = 0;
    pendingMove.current.dy = 0;
    if (x !== 0 || y !== 0) sendMove(x, y);
  };

  const clearFingerVisual = () => {
    if (fingerRaf.current != null) {
      cancelAnimationFrame(fingerRaf.current);
      fingerRaf.current = null;
    }
    fadeReactionOut(true);
  };

  /** Tap feedback: brief hold then fade out. */
  const flashTapVisual = (pageX: number, pageY: number) => {
    const x = pageX - padOffset.current.x;
    const y = pageY - padOffset.current.y;
    if (tapFlashTimer.current) clearTimeout(tapFlashTimer.current);
    const id = Date.now();
    setRipple({ x, y, id });
    setFingers([{ x, y }]);
    reactFade.setValue(1);
    tapFlashTimer.current = setTimeout(() => {
      tapFlashTimer.current = null;
      setRipple((r) => (r?.id === id ? null : r));
      fadeReactionOut(true);
    }, TAP_FLASH_MS);
  };

  const markMoved = () => {
    if (!moved.current) {
      moved.current = true;
      clearHold();
      clearPendingClick();
      lastTapAt.current = 0;
    }
  };

  const emitLeftTap = () => {
    // Immediate click — laptop trackpad style (no delayed first tap).
    send({ t: 'click', btn: 'left', n: 1 });
    const now = Date.now();
    if (
      doubleRef.current &&
      lastTapAt.current > 0 &&
      now - lastTapAt.current <= DOUBLE_TAP_MS
    ) {
      send({ t: 'click', btn: 'left', n: 1 });
      lastTapAt.current = 0;
      return;
    }
    lastTapAt.current = now;
  };

  const resetGesture = () => {
    mode.current = 'none';
    startPos.current = null;
    lastPos.current = null;
    lastMid.current = null;
    lastTime.current = 0;
    gestureStartAt.current = 0;
    fingerCount.current = 0;
    maxFingers.current = 1;
    moved.current = false;
    dragging.current = false;
    gestureActive.current = false;
    multiTravel.current = { x: 0, y: 0 };
    swipeArmed.current = true;
    pinchAccum.current = 0;
    lastPinch.current = 0;
    activeTouches.current.clear();
  };

  const onPadLayout = () => {
    padRef.current?.measureInWindow((x, y, w, h) => {
      padOffset.current = { x, y };
      setPadSize({ w, h });
    });
  };

  /** Merge by identifier — never trust `touches.length` alone (RN under-reports). */
  const touchId = (
    t: { identifier?: string | number },
    fallback: number,
  ): string => {
    const raw = t.identifier;
    if (typeof raw === 'number' && Number.isFinite(raw)) return String(raw);
    if (typeof raw === 'string' && raw.length > 0) return raw;
    return `f${fallback}`;
  };

  const upsertTouches = (e: GestureResponderEvent) => {
    const map = activeTouches.current;
    const ne = e.nativeEvent;
    const touches = ne.touches ?? [];
    const changed = ne.changedTouches ?? [];
    let wrote = false;
    const put = (
      t: { identifier?: string | number; pageX: number; pageY: number },
      i: number,
    ) => {
      map.set(touchId(t, i), { x: t.pageX, y: t.pageY });
      wrote = true;
    };
    touches.forEach((t, i) => put(t, i));
    changed.forEach((t, i) => put(t, 100 + i));
    if (!wrote && typeof ne.pageX === 'number' && typeof ne.pageY === 'number') {
      map.set(touchId(ne, 0), { x: ne.pageX, y: ne.pageY });
    }
  };

  const touchesSnapshot = (): Point[] => Array.from(activeTouches.current.values());

  const removeEndedTouches = (e: GestureResponderEvent) => {
    const map = activeTouches.current;
    const changed = e.nativeEvent.changedTouches ?? [];
    const still = e.nativeEvent.touches ?? [];

    if (changed.length > 0) {
      let deletedById = false;
      changed.forEach((t, i) => {
        const id = t.identifier;
        if (id !== undefined && id !== null && String(id).length > 0) {
          map.delete(String(id));
          deletedById = true;
        } else if (still.length === 0) {
          map.delete(`f${i}`);
        }
      });
      if (!deletedById && still.length === 0) {
        map.clear();
        return;
      }
    }

    still.forEach((t, i) => {
      map.set(touchId(t, i), { x: t.pageX, y: t.pageY });
    });

    // Final lift: native reports no active touches
    if (still.length === 0) map.clear();
  };

  const fireSwipe = (name: string) => {
    const now = Date.now();
    if (now - lastSwipeAt.current < SWIPE_COOLDOWN_MS) return;
    lastSwipeAt.current = now;
    swipeArmed.current = false;
    markMoved();
    // Single message — host maps GESTURES; dual hotkey would double-fire Win+Tab
    send({ t: 'gesture', name });
  };

  const fireNamedGesture = (name: string) => {
    send({ t: 'gesture', name });
  };

  const beginMulti = (pts: Point[]) => {
    if (pts.length >= 2) {
      lastMid.current = centroid(pts);
      lastPinch.current = pts.length >= 2 ? dist(pts[0], pts[1]) : 0;
      startPos.current = lastMid.current;
    } else if (pts.length === 1) {
      startPos.current = pts[0];
      lastPos.current = { ...pts[0] };
    }
    multiTravel.current = { x: 0, y: 0 };
    pinchAccum.current = 0;
    swipeArmed.current = true;
  };

  const tryMultiSwipe = (fingerN: 3 | 4) => {
    if (!swipeArmed.current) return;
    const tx = multiTravel.current.x;
    const ty = multiTravel.current.y;
    if (Math.abs(ty) < MULTI_SWIPE && Math.abs(tx) < MULTI_SWIPE) return;
    const vertical = Math.abs(ty) >= Math.abs(tx) * 0.85;
    if (fingerN === 4) {
      if (vertical) fireSwipe(ty < 0 ? 'four_finger_up' : 'four_finger_down');
      else fireSwipe(tx < 0 ? 'four_finger_left' : 'four_finger_right');
    } else {
      if (vertical) fireSwipe(ty < 0 ? 'three_finger_up' : 'three_finger_down');
      else fireSwipe(tx < 0 ? 'three_finger_left' : 'three_finger_right');
    }
  };

  const onPadTouchStart = (e: GestureResponderEvent) => {
    if (settingsOpen) return;
    upsertTouches(e);
    const pts = touchesSnapshot();
    const n = Math.max(pts.length, 1);
    const wasActive = gestureActive.current;
    const prevMax = maxFingers.current;
    fingerCount.current = n;
    maxFingers.current = Math.max(maxFingers.current, n);
    gestureActive.current = true;
    const ts = e.nativeEvent.timestamp;
    lastTime.current = typeof ts === 'number' && ts > 0 ? ts : Date.now();

    updateFingersVisual(pts, { force: true });

    if (!wasActive) {
      gestureStartAt.current = Date.now();
      moved.current = false;
      dragging.current = false;
      clearHold();
      clearPendingClick();
      maxFingers.current = n;
      fadeReactionIn();
    } else {
      maxFingers.current = Math.max(maxFingers.current, n);
      clearHold();
      lastTapAt.current = 0;
      fadeReactionIn();
    }

    if (n >= 4) {
      mode.current = 'swipe4';
      beginMulti(pts);
      return;
    }
    if (n >= 3) {
      mode.current = 'swipe3';
      beginMulti(pts);
      return;
    }
    if (n >= 2) {
      if (prevMax < 2 || !wasActive) beginMulti(pts);
      mode.current = 'scroll';
      return;
    }

    mode.current = 'move';
    const p = pts[0];
    if (!p) return;
    startPos.current = p;
    lastPos.current = { ...p };
    if (holdSelectRef.current) {
      holdTimer.current = setTimeout(() => {
        if (!moved.current && gestureActive.current && fingerCount.current === 1) {
          clearPendingClick();
          lastTapAt.current = 0;
          dragging.current = true;
          mode.current = 'drag';
          send({ t: 'down', btn: 'left' });
        }
      }, HOLD_MS);
    }
  };

  const onPadTouchMove = (e: GestureResponderEvent) => {
    if (settingsOpen || !gestureActive.current) return;
    upsertTouches(e);
    const pts = touchesSnapshot();
    const n = pts.length;
    if (n === 0) return;
    fingerCount.current = n;
    maxFingers.current = Math.max(maxFingers.current, n);
    const ts = e.nativeEvent.timestamp;
    const now = typeof ts === 'number' && ts > 0 ? ts : Date.now();

    // ——— 4 fingers: virtual desktops / Task View ———
    if (n >= 4) {
      updateFingersVisual(pts);
      clearHold();
      if (mode.current !== 'swipe4') {
        mode.current = 'swipe4';
        beginMulti(pts);
        lastTime.current = now;
        return;
      }
      const mid = centroid(pts);
      const prev = lastMid.current;
      if (prev) {
        multiTravel.current.x += mid.x - prev.x;
        multiTravel.current.y += mid.y - prev.y;
        tryMultiSwipe(4);
      }
      lastMid.current = mid;
      lastTime.current = now;
      return;
    }

    // ——— 3 fingers: Task View / desktop / app switch ———
    if (n >= 3) {
      updateFingersVisual(pts);
      clearHold();
      if (mode.current !== 'swipe3') {
        mode.current = 'swipe3';
        beginMulti(pts);
        lastTime.current = now;
        return;
      }
      const mid = centroid(pts.slice(0, 3));
      const prev = lastMid.current;
      if (prev) {
        multiTravel.current.x += mid.x - prev.x;
        multiTravel.current.y += mid.y - prev.y;
        tryMultiSwipe(3);
      }
      lastMid.current = mid;
      lastTime.current = now;
      return;
    }

    // ——— 2 fingers: scroll preferred; pinch only if clearly dominant ———
    if (n >= 2) {
      updateFingersVisual(pts);
      clearHold();
      const a = pts[0];
      const b = pts[1];
      const mid = midpoint(a, b);
      const pinch = dist(a, b);
      const prevMid = lastMid.current;
      const prevPinch = lastPinch.current || pinch;

      if (prevMid) {
        const pinchDelta = pinch - prevPinch;
        const midDx = mid.x - prevMid.x;
        const midDy = mid.y - prevMid.y;
        multiTravel.current.x += midDx;
        multiTravel.current.y += midDy;
        const speed = Math.hypot(midDx, midDy);
        const absPinch = Math.abs(pinchDelta);

        let doPinch = false;
        if (mode.current === 'pinch') {
          // Sticky pinch: stay until motion is mostly parallel (scroll)
          doPinch = !(speed > absPinch * 1.3 && speed > 1.2);
          if (!doPinch && absPinch > PINCH_THRESHOLD && absPinch > speed * 1.1) {
            doPinch = true;
          }
        } else if (mode.current === 'scroll') {
          // Sticky scroll: only break out on a strong, clear pinch
          doPinch =
            absPinch > PINCH_THRESHOLD * 1.4 &&
            absPinch > speed * PINCH_BREAK_SCROLL;
        } else {
          // Undecided — default scroll unless pinch clearly dominates
          doPinch =
            absPinch > PINCH_THRESHOLD && absPinch > speed * PINCH_VS_SCROLL;
        }

        if (doPinch) {
          mode.current = 'pinch';
          pinchAccum.current += pinchDelta;
          if (Math.abs(pinchAccum.current) >= PINCH_FIRE) {
            send({
              t: 'zoom',
              factor: pinchAccum.current > 0 ? 1.12 : 0.88,
            });
            pinchAccum.current = 0;
            markMoved();
          }
        } else if (speed > 0.35) {
          mode.current = 'scroll';
          pinchAccum.current = 0;
          const s = sensRef.current;
          const scrollSign = invertRef.current ? -1 : 1;
          const boost = speed > 12 ? 2.4 : speed > 6 ? 1.7 : 1.0;
          send({
            t: 'scroll',
            dx: midDx * s * 1.75 * scrollSign * boost,
            dy: -midDy * s * 1.75 * scrollSign * boost,
          });
          markMoved();
        }
      } else {
        beginMulti(pts);
      }

      lastMid.current = mid;
      lastPinch.current = pinch;
      lastTime.current = now;
      return;
    }

    // ——— 1 finger: cursor / drag — send moves first, then light pad visuals ———
    if (n === 1 && (mode.current === 'move' || mode.current === 'drag')) {
      const x = pts[0].x;
      const y = pts[0].y;
      const prev = lastPos.current;
      if (!prev) {
        lastPos.current = { x, y };
        lastTime.current = now;
        updateFingersVisual(pts, { force: true });
        return;
      }

      const rawDx = x - prev.x;
      const rawDy = y - prev.y;
      const dt = now - lastTime.current;

      if (startPos.current) {
        const fromStart = Math.hypot(
          x - startPos.current.x,
          y - startPos.current.y,
        );
        if (fromStart > TAP_SLOP) {
          if (!moved.current) {
            markMoved();
            lastPos.current = { x, y };
            lastTime.current = now;
            updateFingersVisual(pts, { force: true });
            return;
          }
          prev.x = x;
          prev.y = y;
          lastTime.current = now;
          if (rawDx !== 0 || rawDy !== 0) {
            const { dx, dy } = accelerateDelta(
              rawDx,
              rawDy,
              dt,
              sensRef.current,
              accelRef.current,
            );
            if (dx !== 0 || dy !== 0) queueSendMove(dx, dy);
          }
          // Throttled — dots follow the finger without blocking the move stream
          updateFingersVisual(pts);
        }
      }
    }
  };

  const onPadTouchEnd = (e: GestureResponderEvent) => {
    if (!gestureActive.current) return;
    removeEndedTouches(e);
    const remaining = activeTouches.current.size;
    fingerCount.current = remaining;

    if (remaining > 0) {
      const pts = touchesSnapshot();
      updateFingersVisual(pts);
      if (pts.length >= 4) {
        if (mode.current !== 'swipe4') beginMulti(pts);
        mode.current = 'swipe4';
      } else if (pts.length >= 3) {
        if (mode.current !== 'swipe3') beginMulti(pts);
        mode.current = 'swipe3';
      } else if (pts.length >= 2) {
        beginMulti(pts);
        if (mode.current !== 'pinch') mode.current = 'scroll';
      } else if (pts.length === 1) {
        lastPos.current = { ...pts[0] };
        startPos.current = pts[0];
        if (mode.current !== 'drag') mode.current = 'move';
      }
      return;
    }

    // Release: finish pending 3/4-finger swipe if not fired yet
    if (swipeArmed.current && maxFingers.current >= 4) tryMultiSwipe(4);
    else if (swipeArmed.current && maxFingers.current >= 3) tryMultiSwipe(3);

    gestureActive.current = false;
    clearHold();
    flushPendingMove();

    if (dragging.current) {
      clearFingerVisual();
      send({ t: 'up', btn: 'left' });
      send({ t: 'stop' });
      resetGesture();
      return;
    }

    const lift = (() => {
      const ch = e.nativeEvent.changedTouches?.[0];
      if (ch) return { x: ch.pageX, y: ch.pageY };
      return startPos.current;
    })();

    let travel = moved.current ? TAP_SLOP + 1 : 0;
    if (startPos.current && lift) {
      travel = Math.hypot(lift.x - startPos.current.x, lift.y - startPos.current.y);
    }
    const multiMag = Math.hypot(multiTravel.current.x, multiTravel.current.y);
    if (multiMag > TAP_SLOP) moved.current = true;

    const isTap = !moved.current && travel <= TAP_SLOP && multiMag <= TAP_SLOP;

    if (isTap) {
      if (maxFingers.current >= 4) {
        lastTapAt.current = 0;
        fireNamedGesture('four_finger_tap');
      } else if (maxFingers.current >= 3) {
        lastTapAt.current = 0;
        fireNamedGesture('three_finger_tap');
      } else if (maxFingers.current >= 2) {
        lastTapAt.current = 0;
        send({ t: 'click', btn: 'right', n: 1 });
      } else {
        emitLeftTap();
      }
      if (lift) flashTapVisual(lift.x, lift.y);
      else clearFingerVisual();
    } else {
      clearFingerVisual();
    }

    send({ t: 'stop' });
    resetGesture();
  };

  const bumpSens = (delta: number) => {
    const next = Math.round((sensitivity + delta) * 10) / 10;
    onSensitivityChange(Math.min(SENS_MAX, Math.max(SENS_MIN, next)));
  };

  const onClassicLeftPressIn = () => {
    setLeftPressed(true);
    classicLeftDragging.current = false;
    if (classicLeftHold.current) clearTimeout(classicLeftHold.current);
    if (holdSelectRef.current) {
      classicLeftHold.current = setTimeout(() => {
        classicLeftHold.current = null;
        classicLeftDragging.current = true;
        send({ t: 'down', btn: 'left' });
      }, HOLD_MS);
    }
  };

  const onClassicLeftPressOut = () => {
    setLeftPressed(false);
    if (classicLeftHold.current) {
      clearTimeout(classicLeftHold.current);
      classicLeftHold.current = null;
    }
    if (classicLeftDragging.current) {
      classicLeftDragging.current = false;
      send({ t: 'up', btn: 'left' });
      send({ t: 'stop' });
    } else {
      emitLeftTap();
    }
  };

  const hot = (keys: string[]) => send({ t: 'hotkey', keys });

  /** Prev/next for slides, YouTube, photos, etc. */
  const mediaPrev = () => hot(['left']);
  const mediaNext = () => hot(['right']);

  const volAppliedRef = useRef(volLevel);
  const volTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const applyVolumeLevel = (next: number) => {
    const clamped = Math.max(0, Math.min(100, Math.round(next)));
    if (volMuted && clamped > 0) setVolMuted(false);
    setVolLevel(clamped);
    volAppliedRef.current = clamped;
    // Debounce absolute set so drag doesn't flood the socket
    if (volTimer.current) clearTimeout(volTimer.current);
    volTimer.current = setTimeout(() => {
      volTimer.current = null;
      send({ t: 'volume', action: 'set', level: clamped });
    }, 40);
  };

  const toggleMute = () => {
    setVolMuted((m) => {
      const next = !m;
      send({ t: 'volume', action: next ? 'mute' : 'unmute' });
      return next;
    });
  };

  const cycleLaser = () => {
    setLaserIdx((prev) => {
      const next = prev + 1;
      if (next >= LASER_COLORS.length) {
        send({ t: 'laser', on: false, size: laserSize });
        return -1;
      }
      const color = LASER_COLORS[next];
      send({ t: 'laser', on: true, color, size: laserSize });
      return next;
    });
  };

  const bumpLaserSize = (delta: number) => {
    const next = Math.min(
      LASER_SIZE_MAX,
      Math.max(LASER_SIZE_MIN, laserSize + delta),
    );
    onLaserSizeChange(next);
    if (laserIdx >= 0) {
      send({
        t: 'laser',
        on: true,
        color: LASER_COLORS[laserIdx],
        size: next,
      });
    }
  };

  const laserColor =
    laserIdx >= 0 ? LASER_COLORS[laserIdx] : THEME.orange;
  const laserOn = laserIdx >= 0;

  const deckFullBleed = surfaceMode === 'deck' && isLandscape;

  return (
    <View style={styles.root}>
      <DokkeBackdrop />
      {deckFullBleed ? (
        <View style={styles.dockChrome} pointerEvents="box-none">
          <Pressable onPress={() => setSettingsOpen(true)} hitSlop={12} style={styles.dockGhost}>
            <IconSettings size={20} color="rgba(255,255,255,0.55)" />
          </Pressable>
          <Pressable
            onPress={() => switchSurface('trackpad')}
            hitSlop={12}
            style={styles.dockGhost}
          >
            <Ionicons name="hand-left-outline" size={18} color="rgba(255,255,255,0.55)" />
          </Pressable>
          <Pressable
            onPress={() => {
              setKeyboardOpen(false);
              setSettingsOpen(false);
              onDisconnect();
            }}
            hitSlop={12}
            style={styles.dockGhost}
            accessibilityLabel="Cerrar y desconectar"
          >
            <Ionicons name="close" size={22} color="rgba(255,255,255,0.55)" />
          </Pressable>
        </View>
      ) : (
        <>
      <View style={[styles.header, { paddingTop: isLandscape ? 6 : 12 }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          {onHome ? (
            <Pressable
              onPress={onHome}
              hitSlop={12}
              style={styles.iconHit}
              accessibilityLabel="Centro de control"
            >
              <Ionicons name="home-outline" size={22} color="#FFFFFF" />
            </Pressable>
          ) : null}
          <Pressable onPress={() => setSettingsOpen(true)} hitSlop={12} style={styles.iconHit}>
            <IconSettings size={22} color="#FFFFFF" />
          </Pressable>
        </View>

        <View style={styles.statusRow}>
          <View style={styles.statusDot} />
          <Text style={styles.statusText}>Connected</Text>
          <View style={{ marginLeft: 6 }}>
            <IconWifi size={15} color="#FFFFFF" />
          </View>
        </View>

        <Pressable
          onPress={() => {
            setKeyboardOpen(false);
            setSettingsOpen(false);
            onDisconnect();
          }}
          hitSlop={12}
          style={styles.iconHit}
          accessibilityLabel="Cerrar y desconectar"
        >
          <Ionicons name="close" size={24} color="#FFFFFF" />
        </Pressable>
      </View>

      {showSurfaceSwitch ? (
      <View style={[styles.modeRow, styles.collapsibleRow]}>
        <View style={styles.modeSegment}>
          <Pressable
            style={[
              styles.modeSegmentBtn,
              surfaceMode === 'trackpad' && styles.modeSegmentBtnOn,
            ]}
            onPress={() => switchSurface('trackpad')}
          >
            <Ionicons
              name="hand-left-outline"
              size={15}
              color={surfaceMode === 'trackpad' ? THEME.label : THEME.secondary}
            />
            <Text
              style={[
                styles.modeSegmentText,
                surfaceMode === 'trackpad' && styles.modeSegmentTextOn,
              ]}
            >
              Trackpad
            </Text>
          </Pressable>
          <Pressable
            style={[
              styles.modeSegmentBtn,
              surfaceMode === 'deck' && styles.modeSegmentBtnOn,
            ]}
            onPress={() => switchSurface('deck')}
          >
            <Ionicons
              name="grid-outline"
              size={15}
              color={surfaceMode === 'deck' ? THEME.label : THEME.secondary}
            />
            <Text
              style={[
                styles.modeSegmentText,
                surfaceMode === 'deck' && styles.modeSegmentTextOn,
              ]}
            >
              Deck
            </Text>
          </Pressable>
        </View>
        <Pressable
          onPress={() => toggleSurfaceSwitch(false)}
          hitSlop={10}
          style={styles.collapseBtn}
          accessibilityLabel="Ocultar selector"
        >
          <IconChevronUp size={14} color={THEME.secondary} />
        </Pressable>
      </View>
      ) : (
        <Pressable
          onPress={() => toggleSurfaceSwitch(true)}
          hitSlop={10}
          style={styles.revealStrip}
          accessibilityLabel="Mostrar selector"
        >
          <IconChevronDown size={14} color={THEME.tertiary} />
        </Pressable>
      )}
        </>
      )}

      {classicMouse && surfaceMode === 'trackpad' ? (
        <View style={styles.classicRow}>
          <Pressable
            style={[styles.classicBtn, leftPressed && styles.classicBtnActive]}
            onPressIn={onClassicLeftPressIn}
            onPressOut={onClassicLeftPressOut}
          >
            <Text style={styles.classicBtnTitle}>Izquierdo</Text>
          </Pressable>
          <Pressable
            style={[styles.classicBtn, rightPressed && styles.classicBtnActive]}
            onPress={() => {
              setRightPressed(true);
              send({ t: 'click', btn: 'right', n: 1 });
              setTimeout(() => setRightPressed(false), 120);
            }}
          >
            <Text style={styles.classicBtnTitle}>Derecho</Text>
          </Pressable>
        </View>
      ) : null}

      {surfaceMode === 'deck' ? (
        <View style={styles.dockBleed}>
          <StreamDeck
            send={send}
            width={width}
            isLandscape={isLandscape}
            pages={deckPages}
            fromHost={Boolean(deckPages?.length)}
          />
        </View>
      ) : (
      <View
        ref={padRef}
        style={styles.pad}
        onLayout={onPadLayout}
        // Only onTouch* — mixing Responder + onTouch causes trackedTouchCount warnings
        onTouchStart={onPadTouchStart}
        onTouchMove={onPadTouchMove}
        onTouchEnd={onPadTouchEnd}
        onTouchCancel={onPadTouchEnd}
      >
        <DotGrid
          width={padSize.w}
          height={padSize.h}
          fingers={fingers}
          color={dots}
          cols={isLandscape ? 14 : 11}
          rows={isLandscape ? 10 : 15}
          reactiveOpacity={reactFade}
        />
        {ripple ? (
          <Animated.View
            pointerEvents="none"
            style={[
              styles.tapRipple,
              {
                left: ripple.x - 36,
                top: ripple.y - 36,
                borderColor: dots,
                backgroundColor: `${dots}33`,
                opacity: reactFade,
              },
            ]}
          />
        ) : null}
        <Animated.View
          pointerEvents="none"
          style={[StyleSheet.absoluteFill, { opacity: reactFade }]}
        >
          {fingers.map((f, i) => (
            <View
              key={`fg-${i}`}
              pointerEvents="none"
              style={[
                styles.fingerGlow,
                {
                  left: f.x - 40,
                  top: f.y - 40,
                  backgroundColor: `${dots}30`,
                  borderColor: `${dots}aa`,
                },
              ]}
            />
          ))}
        </Animated.View>
      </View>
      )}

      {/* Collapsible presenter / volume bar */}
      {surfaceMode === 'trackpad' && showQuickActions ? (
      <View style={styles.bottomBar}>
        <Pressable
          onPress={() => toggleQuickActions(false)}
          hitSlop={10}
          style={styles.revealStrip}
          accessibilityLabel="Ocultar accesos directos"
        >
          <IconChevronDown size={14} color={THEME.tertiary} />
        </Pressable>
        <View style={styles.shortcutRow}>
          {(
            [
              ['Escritorio', ['win', 'd']],
              ['Tareas', ['win', 'tab']],
              ['Esc', ['esc']],
            ] as const
          ).map(([label, keys]) => (
            <Pressable
              key={label}
              style={styles.shortcutChip}
              onPress={() => hot([...keys])}
            >
              <Text style={styles.shortcutText}>{label}</Text>
            </Pressable>
          ))}
          {keyboardOnEdit ? (
            <Pressable
              style={[
                styles.shortcutChip,
                keyboardOpen && styles.shortcutChipOn,
              ]}
              onPress={() => setKeyboardOpen((v) => !v)}
            >
              <Text style={styles.shortcutText}>Teclado</Text>
            </Pressable>
          ) : null}
        </View>

        <Pressable
          onPress={() => {
            setControlsOpen((v) => {
              if (v) setShowVolumePill(false);
              return !v;
            });
          }}
          hitSlop={10}
          style={styles.bottomToggle}
        >
          {controlsOpen ? (
            <IconChevronDown size={14} color="#FFFFFF" />
          ) : (
            <IconChevronUp size={14} color="#FFFFFF" />
          )}
          <Text style={styles.bottomLabel}>
            {controlsOpen ? 'Do Not Disturb Disabled' : 'Controls'}
          </Text>
        </Pressable>

        {controlsOpen ? (
          <View style={styles.presenterBlock}>
            {showVolumePill ? (
              <VolumePill
                level={volLevel}
                muted={volMuted}
                onLevelChange={applyVolumeLevel}
                onMuteToggle={toggleMute}
                onClose={() => setShowVolumePill(false)}
              />
            ) : null}

            {/* <  volume  pointer  > */}
            <View style={styles.presenterRow}>
              <RoundBtn size={56} onPress={mediaPrev}>
                <IconChevronLeft size={28} color="#FFFFFF" />
              </RoundBtn>

              <RoundBtn
                size={52}
                active={showVolumePill || volMuted}
                onPress={() => {
                  if (showVolumePill) toggleMute();
                  else setShowVolumePill(true);
                }}
                onLongPress={toggleMute}
              >
                {volMuted ? (
                  <IconVolumeMute size={22} color={THEME.orange} />
                ) : (
                  <IconVolume size={22} color="#FFFFFF" />
                )}
              </RoundBtn>

              <RoundBtn size={56} active={laserOn} onPress={cycleLaser}>
                <IconPointer size={26} color={laserColor} />
              </RoundBtn>

              <RoundBtn size={56} onPress={mediaNext}>
                <IconChevronRight size={28} color="#FFFFFF" />
              </RoundBtn>
            </View>

            {laserOn ? (
              <Text style={styles.laserHint}>
                Láser activo · tocá el puntero para color / apagar
              </Text>
            ) : (
              <Text style={styles.laserHint}>
                {'<'} {'>'} diapositivas / video · volumen · láser
              </Text>
            )}
          </View>
        ) : null}
      </View>
      ) : surfaceMode === 'trackpad' ? (
        <Pressable
          onPress={() => toggleQuickActions(true)}
          hitSlop={10}
          style={styles.revealStrip}
          accessibilityLabel="Mostrar accesos directos"
        >
          <IconChevronUp size={14} color={THEME.tertiary} />
        </Pressable>
      ) : null}

      <RemoteKeyboard
        visible={keyboardOnEdit && keyboardOpen}
        onClose={() => setKeyboardOpen(false)}
        send={send}
      />

      <Modal
        visible={settingsOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setSettingsOpen(false)}
      >
        <View style={styles.modalBackdrop}>
          <Pressable
            style={StyleSheet.absoluteFill}
            onPress={() => setSettingsOpen(false)}
          />
          <DokkeCard style={styles.sheet} radius={28}>
            <View style={styles.sheetHeader}>
              <Text style={styles.sheetTitle}>Ajustes</Text>
              <Pressable onPress={() => setSettingsOpen(false)} hitSlop={8}>
                <Text style={styles.sheetClose}>Cerrar</Text>
              </Pressable>
            </View>
            <ScrollView
              bounces={false}
              showsVerticalScrollIndicator={false}
              style={isLandscape ? { maxHeight: 260 } : undefined}
            >
              <Text style={styles.meta} numberOfLines={1}>
                {hostInfo ?? 'Host conectado'}
              </Text>

              <SettingRow label="Sensibilidad">
                <View style={styles.sensControls}>
                  <Pressable style={styles.sensBtn} onPress={() => bumpSens(-SENS_STEP)}>
                    <Text style={styles.sensBtnText}>−</Text>
                  </Pressable>
                  <Text style={styles.sensValue}>{sensitivity.toFixed(1)}×</Text>
                  <Pressable style={styles.sensBtn} onPress={() => bumpSens(SENS_STEP)}>
                    <Text style={styles.sensBtnText}>+</Text>
                  </Pressable>
                </View>
              </SettingRow>

              <ToggleRow
                label="Teclado al escribir"
                hint="Al clickear un campo de texto, abre el teclado del teléfono"
                value={keyboardOnEdit}
                onChange={onKeyboardOnEditChange}
              />
              <ToggleRow
                label="Mouse clásico"
                hint="Botones izquierdo / derecho separados"
                value={classicMouse}
                onChange={onClassicMouseChange}
              />
              <ToggleRow
                label="Pantalla horizontal"
                hint="Bloquea landscape"
                value={landscapeLock}
                onChange={onLandscapeLockChange}
              />
              <ToggleRow
                label="Doble click"
                hint="Dos taps rápidos"
                value={doubleClick}
                onChange={onDoubleClickChange}
              />
              <ToggleRow
                label="Mantener para seleccionar"
                hint="Hold + mover = arrastrar"
                value={holdToSelect}
                onChange={onHoldToSelectChange}
              />
              <ToggleRow
                label="Aceleración"
                hint="Más velocidad en flicks"
                value={acceleration}
                onChange={onAccelerationChange}
              />
              <ToggleRow
                label="Invertir scroll"
                hint="Dirección natural / clásica"
                value={invertScroll}
                onChange={onInvertScrollChange}
              />

              <View style={styles.paletteBlock}>
                <Text style={styles.rowLabel}>Color de los puntitos</Text>
                <Text style={styles.paletteHint}>
                  Color del pad al tocar (puntos y glow)
                </Text>
                <View style={styles.paletteRow}>
                  {PAD_COLORS.map((c) => {
                    const selected = padColor.toLowerCase() === c.toLowerCase();
                    const swatch = c === 'auto' ? THEME.orange : c;
                    return (
                      <Pressable
                        key={c}
                        onPress={() => onPadColorChange(c)}
                        style={[
                          styles.swatch,
                          { backgroundColor: swatch },
                          c === 'auto' && styles.swatchAuto,
                          selected && styles.swatchSelected,
                        ]}
                      />
                    );
                  })}
                </View>
              </View>

              <SettingRow label="Tamaño del puntero">
                <View style={styles.sensControls}>
                  <Pressable
                    style={styles.sensBtn}
                    onPress={() => bumpLaserSize(-LASER_SIZE_STEP)}
                  >
                    <Text style={styles.sensBtnText}>−</Text>
                  </Pressable>
                  <Text style={styles.sensValue}>{laserSize}px</Text>
                  <Pressable
                    style={styles.sensBtn}
                    onPress={() => bumpLaserSize(LASER_SIZE_STEP)}
                  >
                    <Text style={styles.sensBtnText}>+</Text>
                  </Pressable>
                </View>
              </SettingRow>

              <Text style={styles.gestureHelp}>
                1 dedo: mover / tap / hold+arrastrar · 2 dedos: scroll y zoom ·
                tap 2 dedos: click derecho · 3 dedos: Win+Tab / escritorio /
                cambiar apps · 4 dedos: escritorios virtuales
              </Text>

              <Pressable
                style={styles.disconnectBtn}
                onPress={() => {
                  setSettingsOpen(false);
                  onDisconnect();
                }}
              >
                <Text style={styles.disconnectText}>Salir / Desconectar</Text>
              </Pressable>
            </ScrollView>
          </DokkeCard>
        </View>
      </Modal>
    </View>
  );
}

function SettingRow({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      {children}
    </View>
  );
}

function ToggleRow({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  return (
    <View style={styles.row}>
      <View style={styles.rowText}>
        <Text style={styles.rowLabel}>{label}</Text>
        <Text style={styles.rowHint}>{hint}</Text>
      </View>
      <Switch
        value={value}
        onValueChange={onChange}
        trackColor={{ false: THEME.surface2, true: THEME.green }}
        thumbColor={value ? '#FFFFFF' : THEME.gray}
      />
    </View>
  );
}

const makeStyles = ({ THEME, DOKKE_GLASS }: Palette) =>
  StyleSheet.create({
    root: {
      flex: 1,
      backgroundColor: DOKKE_GLASS.canvas,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: 20,
      paddingBottom: 8,
    },
    iconHit: {
      width: 40,
      height: 40,
      alignItems: 'center',
      justifyContent: 'center',
    },
    statusRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
    },
    statusDot: {
      width: 8,
      height: 8,
      borderRadius: 4,
      backgroundColor: THEME.green,
    },
    statusText: {
      color: THEME.label,
      fontSize: 14,
      fontWeight: '500',
      letterSpacing: -0.2,
    },
    modeRow: {
      paddingHorizontal: 20,
      marginBottom: 10,
    },
    // The segment takes the room it needs; the chevron rides beside it.
    collapsibleRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
    },
    collapseBtn: {
      paddingVertical: 8,
      paddingHorizontal: 4,
    },
    // What is left behind when a strip is put away: a thin bar you can tap to
    // bring it back, so hiding chrome never strands the control that undoes it.
    revealStrip: {
      alignItems: 'center',
      justifyContent: 'center',
      paddingVertical: 6,
    },
    modeSegment: {
      flex: 1,
      flexDirection: 'row',
      backgroundColor: THEME.surface,
      borderRadius: 12,
      padding: 3,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
    },
    modeSegmentBtn: {
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
      paddingVertical: 8,
      borderRadius: 9,
    },
    modeSegmentBtnOn: {
      backgroundColor: THEME.blue,
    },
    modeSegmentText: {
      color: THEME.secondary,
      fontSize: 13,
      fontWeight: '600',
      letterSpacing: -0.2,
    },
    modeSegmentTextOn: {
      color: THEME.label,
    },
    classicRow: {
      flexDirection: 'row',
      gap: 10,
      paddingHorizontal: 16,
      marginBottom: 8,
    },
    classicBtn: {
      flex: 1,
      minHeight: 52,
      borderRadius: 16,
      backgroundColor: THEME.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
      alignItems: 'center',
      justifyContent: 'center',
    },
    classicBtnActive: {
      borderColor: THEME.label,
      backgroundColor: THEME.surface2,
    },
    classicBtnTitle: {
      color: THEME.label,
      fontWeight: '600',
      fontSize: 14,
      letterSpacing: -0.2,
    },
    pad: {
      flex: 1,
      marginHorizontal: 14,
      borderRadius: 28,
      backgroundColor: THEME.padSurface,
      overflow: 'hidden',
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
    },
    dockBleed: {
      flex: 1,
    },
    dockChrome: {
      position: 'absolute',
      top: 8,
      left: 12,
      right: 12,
      zIndex: 8,
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
    },
    dockGhost: {
      width: 36,
      height: 36,
      alignItems: 'center',
      justifyContent: 'center',
    },
    tapRipple: {
      position: 'absolute',
      width: 72,
      height: 72,
      borderRadius: 36,
      borderWidth: 1.5,
    },
    fingerGlow: {
      position: 'absolute',
      width: 80,
      height: 80,
      borderRadius: 40,
      borderWidth: 1.5,
    },
    bottomBar: {
      alignItems: 'center',
      paddingTop: 6,
      paddingBottom: 14,
      paddingHorizontal: 16,
      gap: 8,
    },
    shortcutRow: {
      flexDirection: 'row',
      justifyContent: 'center',
      alignItems: 'center',
      alignSelf: 'stretch',
      gap: 8,
      paddingHorizontal: 4,
    },
    shortcutChip: {
      paddingHorizontal: 14,
      paddingVertical: 8,
      borderRadius: 12,
      backgroundColor: THEME.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
    },
    shortcutChipOn: {
      borderColor: THEME.blue,
      backgroundColor: THEME.surface2,
    },
    shortcutText: {
      color: THEME.label,
      fontSize: 12,
      fontWeight: '600',
      letterSpacing: -0.1,
    },
    bottomToggle: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      paddingVertical: 6,
      paddingHorizontal: 12,
    },
    bottomLabel: {
      color: THEME.secondary,
      fontSize: 12,
      fontWeight: '500',
    },
    presenterBlock: {
      alignItems: 'center',
      gap: 10,
      width: '100%',
    },
    volumePillWrap: {
      position: 'absolute',
      right: 8,
      bottom: 72,
      zIndex: 20,
    },
    volumeDismiss: {
      alignSelf: 'center',
      marginTop: 8,
      paddingVertical: 4,
      paddingHorizontal: 10,
    },
    volumeDismissText: {
      color: THEME.secondary,
      fontSize: 12,
      fontWeight: '600',
    },
    laserHint: {
      marginTop: 8,
      textAlign: 'center',
      color: THEME.secondary,
      fontSize: 11,
      fontWeight: '600',
    },
    presenterRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 14,
    },
    volumeRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 12,
      paddingVertical: 4,
      paddingHorizontal: 10,
      borderRadius: 20,
      backgroundColor: THEME.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
    },
    volumeClose: {
      marginLeft: 4,
      padding: 4,
    },
    roundBtn: {
      backgroundColor: THEME.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
      alignItems: 'center',
      justifyContent: 'center',
    },
    roundBtnActive: {
      borderColor: THEME.orange,
      borderWidth: 1.5,
    },
    roundBtnPressed: {
      backgroundColor: THEME.surface2,
    },
    modalBackdrop: {
      flex: 1,
      backgroundColor: 'rgba(27, 17, 7, 0.72)',
      justifyContent: 'flex-end',
    },
    sheet: {
      paddingHorizontal: 20,
      paddingTop: 16,
      paddingBottom: 36,
      maxHeight: '92%',
    },
    sheetHeader: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 4,
    },
    sheetTitle: {
      color: THEME.label,
      fontSize: 20,
      fontWeight: '700',
      letterSpacing: -0.4,
    },
    sheetClose: {
      color: THEME.blueBright,
      fontSize: 16,
      fontWeight: '600',
    },
    meta: {
      color: THEME.secondary,
      fontSize: 13,
      marginBottom: 16,
    },
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingVertical: 14,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: THEME.hairline,
      gap: 12,
    },
    rowText: { flex: 1, gap: 2 },
    rowLabel: { color: THEME.label, fontSize: 16, fontWeight: '600', letterSpacing: -0.3 },
    rowHint: { color: THEME.secondary, fontSize: 12 },
    paletteBlock: {
      marginTop: 14,
      marginBottom: 6,
      gap: 8,
    },
    paletteHint: {
      color: THEME.secondary,
      fontSize: 12,
    },
    paletteRow: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 10,
      marginTop: 4,
    },
    swatch: {
      width: 32,
      height: 32,
      borderRadius: 16,
      borderWidth: 2,
      borderColor: 'transparent',
    },
    swatchSelected: {
      borderColor: THEME.label,
    },
    // The "auto" swatch is the app colour itself — dashed so it reads as a rule
    // ("whatever the host says") rather than one more fixed colour.
    swatchAuto: {
      borderStyle: 'dashed',
      borderColor: THEME.label,
    },
    sensControls: { flexDirection: 'row', alignItems: 'center', gap: 8 },
    sensBtn: {
      width: 36,
      height: 36,
      borderRadius: 18,
      backgroundColor: THEME.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
      alignItems: 'center',
      justifyContent: 'center',
    },
    sensBtnText: { color: THEME.label, fontSize: 20, fontWeight: '600' },
    sensValue: {
      color: THEME.label,
      fontSize: 15,
      fontWeight: '600',
      minWidth: 44,
      textAlign: 'center',
    },
    disconnectBtn: {
      marginTop: 18,
      backgroundColor: 'rgba(255, 69, 58, 0.12)',
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: 'rgba(255, 69, 58, 0.35)',
      borderRadius: 14,
      paddingVertical: 14,
      alignItems: 'center',
    },
    gestureHelp: {
      marginTop: 14,
      color: THEME.secondary,
      fontSize: 12,
      lineHeight: 18,
    },
    disconnectText: { color: THEME.red, fontSize: 16, fontWeight: '600' },
  });
