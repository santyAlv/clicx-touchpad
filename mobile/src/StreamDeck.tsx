import { Ionicons } from '@expo/vector-icons';
import { useEffect, useRef, useState } from 'react';
import {
  Animated,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from 'react-native';
import { DokkeAglass, DokkeBackdrop, DokkePlate } from './DokkeGlass';
import { DOKKE_GLASS } from './dokkeTokens';
import type { ClicxMessage } from './protocol';
import { type Palette, useStyles, useTheme } from './palette';
import {
  DEFAULT_DECK_PAGES,
  DECK_COLS_LANDSCAPE,
  DECK_COLS_PORTRAIT,
  DECK_ROWS_LANDSCAPE,
  DECK_ROWS_PORTRAIT,
  loadDeckPageIndex,
  saveDeckPageIndex,
  type DeckButton,
  type DeckPage,
} from './deckConfig';

type Props = {
  send: (msg: ClicxMessage) => void;
  width: number;
  isLandscape: boolean;
  pages?: DeckPage[] | null;
  fromHost?: boolean;
};

function fireAction(
  send: (msg: ClicxMessage) => void,
  button: DeckButton,
  fromHost: boolean,
) {
  if (fromHost && button.id) {
    send({ t: 'deck', id: button.id });
    return;
  }
  const action = button.action;
  if (action.kind === 'hotkey') {
    send({ t: 'hotkey', keys: action.keys });
    return;
  }
  if (action.kind === 'volume') {
    send({ t: 'volume', action: action.action });
    return;
  }
  if ((action.kind === 'shell' || action.kind === 'app') && button.id) {
    send({ t: 'deck', id: button.id });
  }
}

function DeckTile({
  button,
  tile,
  onPress,
  empty,
}: {
  button?: DeckButton;
  tile: number;
  onPress: () => void;
  empty?: boolean;
}) {
  const { DOKKE_GLASS } = useTheme();
  const styles = useStyles(makeStyles);
  const scale = useRef(new Animated.Value(1)).current;
  const r = tile * DOKKE_GLASS.tileR;
  const icon = tile * DOKKE_GLASS.tileIn;
  const iconR = tile * DOKKE_GLASS.tileInR;
  const hasAppIcon = Boolean(button?.iconB64);

  const pressIn = () => {
    if (empty) return;
    Animated.spring(scale, {
      toValue: 0.95,
      useNativeDriver: true,
      speed: 60,
      bounciness: 0,
    }).start();
  };

  const pressOut = () => {
    Animated.spring(scale, {
      toValue: 1,
      useNativeDriver: true,
      speed: 36,
      bounciness: 4,
    }).start();
  };

  if (empty || !button) {
    return (
      <View style={[styles.cell, { width: tile, height: tile }]}>
        <DokkeAglass size={tile} radius={r} empty />
      </View>
    );
  }

  return (
    <Pressable
      onPress={onPress}
      onPressIn={pressIn}
      onPressOut={pressOut}
      style={[styles.cell, { width: tile, height: tile }]}
    >
      <Animated.View style={[styles.cell, { transform: [{ scale }] }]}>
        <DokkeAglass size={tile} radius={r}>
          {hasAppIcon ? (
            <Image
              source={{ uri: `data:image/png;base64,${button.iconB64}` }}
              style={{ width: icon, height: icon, borderRadius: iconR }}
              resizeMode="contain"
              fadeDuration={0}
            />
          ) : (
            <DokkePlate size={icon} radius={iconR}>
              <Ionicons
                name={button.icon as keyof typeof Ionicons.glyphMap}
                size={icon * 0.42}
                color="rgba(0,0,0,0.62)"
              />
            </DokkePlate>
          )}
        </DokkeAglass>
      </Animated.View>
    </Pressable>
  );
}

function DeckGrid({
  page,
  send,
  width,
  height,
  isLandscape,
  fromHost,
}: {
  page: DeckPage;
  send: (msg: ClicxMessage) => void;
  width: number;
  height: number;
  isLandscape: boolean;
  fromHost: boolean;
}) {
  const styles = useStyles(makeStyles);
  const cols = isLandscape ? DECK_COLS_LANDSCAPE : DECK_COLS_PORTRAIT;
  const rows = isLandscape ? DECK_ROWS_LANDSCAPE : DECK_ROWS_PORTRAIT;
  const gap = Math.round(
    isLandscape
      ? Math.min(32, Math.max(20, width * 0.03))
      : Math.min(28, Math.max(16, width * 0.04)),
  );
  const padH = Math.round(isLandscape ? Math.max(20, width * 0.06) : Math.max(22, width * 0.08));
  const gridW = Math.max(0, width - padH * 2);
  const gridH = Math.max(0, height - 8);
  const byW = (gridW - gap * (cols - 1)) / cols;
  const byH = (gridH - gap * (rows - 1)) / rows;
  const tile = Math.floor(Math.min(byW, byH, isLandscape ? 220 : 180));
  const rowW = tile * cols + gap * (cols - 1);

  return (
    <View style={[styles.page, { width, height }]}>
      <View style={styles.grid}>
        {Array.from({ length: rows }, (_, row) => (
          <View
            key={`row-${row}`}
            style={[styles.gridRow, { width: rowW, marginTop: row === 0 ? 0 : gap }]}
          >
            {Array.from({ length: cols }, (_, col) => {
              const i = row * cols + col;
              const button = page.buttons[i];
              return (
                <View key={button?.id ?? `empty-${i}`} style={{ marginLeft: col === 0 ? 0 : gap }}>
                  <DeckTile
                    button={button}
                    tile={tile}
                    empty={!button}
                    onPress={() => button && fireAction(send, button, fromHost)}
                  />
                </View>
              );
            })}
          </View>
        ))}
      </View>
    </View>
  );
}

export function StreamDeck({ send, width, isLandscape, pages, fromHost = false }: Props) {
  const { DOKKE_GLASS } = useTheme();
  const styles = useStyles(makeStyles);
  const deckPages = pages?.length ? pages : DEFAULT_DECK_PAGES;
  const [page, setPage] = useState(0);
  const scrollRef = useRef<ScrollView>(null);
  const [box, setBox] = useState({ w: width, h: 360 });
  const pageW = box.w > 0 ? box.w : width;

  useEffect(() => {
    let active = true;
    loadDeckPageIndex().then((idx) => {
      if (!active) return;
      const clamped = Math.max(0, Math.min(deckPages.length - 1, idx));
      setPage(clamped);
      requestAnimationFrame(() => {
        scrollRef.current?.scrollTo({ x: clamped * pageW, animated: false });
      });
    });
    return () => {
      active = false;
    };
  }, [pageW, deckPages.length]);

  const onScrollEnd = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const idx = Math.round(e.nativeEvent.contentOffset.x / pageW);
    const clamped = Math.max(0, Math.min(deckPages.length - 1, idx));
    if (clamped !== page) {
      setPage(clamped);
      void saveDeckPageIndex(clamped);
    }
  };

  return (
    <View style={styles.shell}>
      <DokkeBackdrop />
      <ScrollView
        ref={scrollRef}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={onScrollEnd}
        decelerationRate="fast"
        style={styles.pager}
        contentContainerStyle={styles.pagerContent}
        onLayout={(e) => {
          const { width: w, height: h } = e.nativeEvent.layout;
          setBox({ w: Math.round(w), h: Math.max(160, Math.round(h)) });
        }}
      >
        {deckPages.map((p) => (
          <DeckGrid
            key={p.id}
            page={p}
            send={send}
            width={pageW}
            height={box.h}
            isLandscape={isLandscape}
            fromHost={fromHost}
          />
        ))}
      </ScrollView>
      <View style={styles.pageControl}>
        {deckPages.map((p, i) => (
          <View key={p.id} style={[styles.pageDot, i === page && styles.pageDotOn]} />
        ))}
      </View>
    </View>
  );
}

const makeStyles = ({ DOKKE_GLASS }: Palette) =>
  StyleSheet.create({
    shell: {
      flex: 1,
      backgroundColor: DOKKE_GLASS.canvas,
      overflow: 'hidden',
    },
    pager: { flex: 1 },
    pagerContent: {
      alignItems: 'stretch',
    },
    page: {
      justifyContent: 'center',
      alignItems: 'center',
    },
    grid: {
      alignItems: 'center',
      justifyContent: 'center',
    },
    gridRow: {
      flexDirection: 'row',
      justifyContent: 'center',
      alignItems: 'center',
    },
    cell: {
      alignItems: 'center',
      justifyContent: 'center',
    },
    pageControl: {
      flexDirection: 'row',
      justifyContent: 'center',
      alignItems: 'center',
      gap: 10,
      paddingTop: 6,
      paddingBottom: 16,
    },
    pageDot: {
      width: 6,
      height: 6,
      borderRadius: 3,
      backgroundColor: 'rgba(255,255,255,0.35)',
    },
    pageDotOn: {
      backgroundColor: '#9CB080',
    },
  });
