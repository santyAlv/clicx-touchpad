import { memo, useMemo } from 'react';
import { Animated, StyleSheet, View } from 'react-native';

export type FingerPoint = { x: number; y: number };

type Props = {
  width: number;
  height: number;
  /** One entry per active finger — only a local patch reacts (cheap). */
  fingers: FingerPoint[];
  color?: string;
  cols?: number;
  rows?: number;
  /** 0–1 fade for the reactive patch (press in / release out). */
  reactiveOpacity?: Animated.Value | number;
};

/**
 * Static halftone field + small reactive patch near each finger.
 * The base grid is built once; finger moves only rebuild nearby dots → fluid.
 */
export const DotGrid = memo(function DotGrid({
  width,
  height,
  fingers,
  color = '#FFFFFF',
  cols = 12,
  rows = 16,
  reactiveOpacity = 1,
}: Props) {
  const layout = useMemo(() => {
    if (width < 8 || height < 8) return null;
    const padX = 22;
    const padY = 22;
    const usableW = width - padX * 2;
    const usableH = height - padY * 2;
    const stepX = usableW / Math.max(1, cols - 1);
    const stepY = usableH / Math.max(1, rows - 1);
    const points: { key: string; x: number; y: number }[] = [];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        points.push({
          key: `${r}-${c}`,
          x: padX + c * stepX,
          y: padY + r * stepY,
        });
      }
    }
    return { points, stepX, stepY };
  }, [width, height, cols, rows]);

  const baseDots = useMemo(() => {
    if (!layout) return null;
    const size = 2.4;
    return layout.points.map((p) => (
      <View
        key={p.key}
        style={[
          styles.dot,
          {
            left: p.x - size / 2,
            top: p.y - size / 2,
            width: size,
            height: size,
            borderRadius: size / 2,
            opacity: 0.2,
            backgroundColor: color,
          },
        ]}
      />
    ));
  }, [layout, color]);

  const reactiveDots = useMemo(() => {
    if (!layout || fingers.length === 0) return null;
    const radius = 95;
    const items = [];
    for (let i = 0; i < layout.points.length; i++) {
      const p = layout.points[i];
      let best = radius;
      for (let f = 0; f < fingers.length; f++) {
        const d = Math.hypot(fingers[f].x - p.x, fingers[f].y - p.y);
        if (d < best) best = d;
      }
      if (best >= radius) continue;
      const t = 1 - best / radius;
      const ease = t * t;
      const scale = 1 + ease * 2.6;
      const opacity = 0.25 + ease * 0.75;
      const size = 2.4 * scale;
      items.push(
        <View
          key={`rx-${p.key}`}
          style={[
            styles.dot,
            {
              left: p.x - size / 2,
              top: p.y - size / 2,
              width: size,
              height: size,
              borderRadius: size / 2,
              opacity,
              backgroundColor: color,
            },
          ]}
        />,
      );
    }
    return items;
  }, [layout, fingers, color]);

  if (!layout) return null;

  return (
    <View style={styles.root} pointerEvents="none">
      {baseDots}
      <Animated.View
        pointerEvents="none"
        style={[styles.reactiveLayer, { opacity: reactiveOpacity }]}
      >
        {reactiveDots}
      </Animated.View>
    </View>
  );
});

const styles = StyleSheet.create({
  root: {
    ...StyleSheet.absoluteFillObject,
  },
  reactiveLayer: {
    ...StyleSheet.absoluteFillObject,
  },
  dot: {
    position: 'absolute',
  },
});
