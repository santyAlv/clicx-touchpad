import { Ionicons } from '@expo/vector-icons';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { DokkeBackdrop, DokkeCard, DokkePlate } from './DokkeGlass';
import { DOKKE_GLASS } from './dokkeTokens';
import { THEME } from './theme';
import { type Palette, useStyles, useTheme } from './palette';

export type HomeScreenId =
  | 'touchpad'
  | 'system'
  | 'actions'
  | 'media'
  | 'keyboard'
  | 'appvolume'
  | 'windows'
  | 'clipboard'
  | 'files'
  | 'usage';

type Props = {
  hostName: string;
  onOpen: (id: HomeScreenId) => void;
};

const TILES: { id: HomeScreenId; icon: string; label: string; desc: string }[] = [
  { id: 'touchpad', icon: 'hand-left-outline', label: 'Trackpad', desc: 'Panel, gestos y Deck' },
  { id: 'system', icon: 'speedometer-outline', label: 'Estado de la PC', desc: 'CPU, RAM, disco, batería' },
  { id: 'actions', icon: 'flash-outline', label: 'Acciones', desc: 'Bloqueo, apagado, capturas' },
  { id: 'media', icon: 'musical-notes-outline', label: 'Multimedia', desc: 'Reproducción y volumen' },
  { id: 'keyboard', icon: 'keypad-outline', label: 'Teclado', desc: 'F1–F12, atajos y escritura' },
  { id: 'appvolume', icon: 'volume-medium-outline', label: 'Volumen por app', desc: 'Ajuste por aplicación' },
  { id: 'windows', icon: 'albums-outline', label: 'Ventanas', desc: 'Foco, minimizar, cerrar' },
  { id: 'clipboard', icon: 'clipboard-outline', label: 'Portapapeles', desc: 'Copiar/pegar entre PC y teléfono' },
  { id: 'files', icon: 'folder-open-outline', label: 'Archivos', desc: 'Enviar y recibir archivos' },
  { id: 'usage', icon: 'stats-chart-outline', label: 'Uso de IA', desc: 'Claude y Codex: semana y 5 h' },
];

/** Centro de control — pantalla de inicio con los secciones de Fase 1. */
export function HomeScreen({ hostName, onOpen }: Props) {
  const styles = useStyles(makeStyles);
  return (
    <SafeAreaView style={styles.root} edges={['top', 'left', 'right', 'bottom']}>
      <DokkeBackdrop />
      <View style={styles.header}>
        <View style={styles.titleWrap}>
          <Text style={styles.title} numberOfLines={1}>
            Centro de control
          </Text>
          <Text style={styles.subtitle} numberOfLines={1}>
            {hostName}
          </Text>
        </View>
      </View>
      <ScrollView
        style={styles.body}
        contentContainerStyle={styles.grid}
        showsVerticalScrollIndicator={false}
      >
        {TILES.map((t) => (
          <Pressable
            key={t.id}
            style={styles.tileHit}
            onPress={() => onOpen(t.id)}
          >
            <DokkeCard radius={22} style={styles.tile}>
              <DokkePlate size={46} radius={14} style={styles.iconWrap}>
                <Ionicons
                  name={t.icon as keyof typeof Ionicons.glyphMap}
                  size={24}
                  color="rgba(0,0,0,0.62)"
                />
              </DokkePlate>
              <Text style={styles.tileLabel}>{t.label}</Text>
              <Text style={styles.tileDesc} numberOfLines={2}>
                {t.desc}
              </Text>
            </DokkeCard>
          </Pressable>
        ))}
      </ScrollView>
      <Text style={styles.footer}>Colocá este panel oculto con el botón ⌂ del trackpad.</Text>
    </SafeAreaView>
  );
}

const makeStyles = ({ THEME, DOKKE_GLASS }: Palette) =>
  StyleSheet.create({
    root: {
      flex: 1,
      backgroundColor: DOKKE_GLASS.canvas,
    },
    header: {
      paddingHorizontal: 16,
      paddingTop: 8,
      paddingBottom: 12,
    },
    titleWrap: {
      alignItems: 'center',
    },
    title: {
      color: THEME.label,
      fontSize: 17,
      fontWeight: '700',
      letterSpacing: -0.3,
    },
    subtitle: {
      color: THEME.secondary,
      fontSize: 12,
      marginTop: 2,
    },
    body: {
      flex: 1,
    },
    grid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      paddingHorizontal: 12,
      paddingBottom: 32,
      gap: 10,
    },
    tileHit: {
      width: '47%',
      flexGrow: 1,
    },
    tile: {
      flex: 1,
      padding: 16,
      minHeight: 132,
    },
    iconWrap: {
      marginBottom: 10,
    },
    tileLabel: {
      color: THEME.label,
      fontSize: 14,
      fontWeight: '600',
    },
    tileDesc: {
      color: THEME.secondary,
      fontSize: 11,
      lineHeight: 15,
      marginTop: 2,
    },
    footer: {
      color: THEME.tertiary,
      fontSize: 11,
      textAlign: 'center',
      paddingVertical: 10,
    },
  });
