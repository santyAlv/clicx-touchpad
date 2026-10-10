import { CameraView, useCameraPermissions } from 'expo-camera';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import {
  loadSavedConnection,
  saveConnection,
  type ConnectionMode,
} from './connectionStorage';
import { DEFAULT_PORT, normalizeHostInput } from './protocol';
import { parseConnectPayload } from './qrConnect';
import { DokkeBackdrop, DokkeCard } from './DokkeGlass';
import { DOKKE_GLASS } from './dokkeTokens';
import type { ConnStatus } from './useClicxConnection';
import { type Palette, useStyles, useTheme } from './palette';

type Props = {
  status: ConnStatus;
  error: string | null;
  onConnect: (host: string, port: number) => void;
};

export function ConnectScreen({ status, error, onConnect }: Props) {
  const { DOKKE_GLASS } = useTheme();
  const styles = useStyles(makeStyles);
  const [mode, setMode] = useState<ConnectionMode>('wifi');
  const [host, setHost] = useState('');
  const [port, setPort] = useState(String(DEFAULT_PORT));
  const [scanError, setScanError] = useState<string | null>(null);
  const [permission, requestPermission] = useCameraPermissions();
  const scannedRef = useRef(false);
  const busy = status === 'connecting';

  useEffect(() => {
    let active = true;
    loadSavedConnection().then((saved) => {
      if (!active || !saved) return;
      setMode(saved.mode);
      setHost(saved.host);
      setPort(String(saved.port));
    });
    return () => {
      active = false;
    };
  }, []);

  const remember = useCallback(
    (next: { mode: ConnectionMode; host: string; port: number }) => {
      void saveConnection(next);
    },
    [],
  );

  /// Bluetooth tethering hands the phone an IP route to the host, so it dials
  /// the same WebSocket as Wi-Fi — only the address belongs to the PAN link.
  const connectAddress = (as: ConnectionMode) => {
    const trimmed = normalizeHostInput(host);
    if (!trimmed) return;
    const portNum = Number(port) || DEFAULT_PORT;
    remember({ mode: as, host: trimmed, port: portNum });
    onConnect(trimmed, portNum);
  };

  const connectUsb = () => {
    const portNum = Number(port) || DEFAULT_PORT;
    remember({ mode: 'usb', host, port: portNum });
    onConnect('127.0.0.1', portNum);
  };

  const onBarcode = useCallback(
    ({ data }: { data: string }) => {
      if (busy || scannedRef.current) return;
      const target = parseConnectPayload(data);
      if (!target) {
        setScanError('QR no válido. Escaneá el del host ClicX.');
        return;
      }
      scannedRef.current = true;
      setScanError(null);
      setHost(target.host);
      setPort(String(target.port));
      remember({ mode: 'qr', host: target.host, port: target.port });
      onConnect(target.host, target.port);
      setTimeout(() => {
        scannedRef.current = false;
      }, 2500);
    },
    [busy, onConnect, remember],
  );

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <DokkeBackdrop />
      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
        bounces={false}
      >
        <View style={styles.hero}>
          <Text style={styles.brand}>ClicX</Text>
          <View style={styles.statusRow}>
            <View style={[styles.dot, busy && styles.dotBusy]} />
            <Text style={styles.statusText}>
              {busy ? 'Conectando…' : 'Listo para conectar'}
            </Text>
          </View>
          <Text style={styles.tagline}>
            El teléfono como trackpad. Wi‑Fi, Bluetooth, USB o QR.
          </Text>
        </View>

        <View style={styles.modeRow}>
          {(
            [
              ['wifi', 'Wi‑Fi'],
              ['bluetooth', 'Bluetooth'],
              ['usb', 'USB'],
              ['qr', 'QR'],
            ] as const
          ).map(([id, label]) => (
            <Pressable
              key={id}
              style={[styles.modeChip, mode === id && styles.modeChipOn]}
              onPress={() => {
                setMode(id);
                setScanError(null);
                if (id === 'qr') scannedRef.current = false;
                remember({
                  mode: id,
                  host,
                  port: Number(port) || DEFAULT_PORT,
                });
              }}
              disabled={busy}
            >
              <Text
                numberOfLines={1}
                style={[styles.modeText, mode === id && styles.modeTextOn]}
              >
                {label}
              </Text>
            </Pressable>
          ))}
        </View>

        <DokkeCard style={styles.card} radius={22}>
          {mode === 'wifi' || mode === 'bluetooth' ? (
            <>
              {mode === 'bluetooth' ? (
                <>
                  <Text style={styles.usbTitle}>Conexión por Bluetooth</Text>
                  <Text style={styles.usbBody}>
                    1. Emparejá el teléfono con la PC.{'\n'}
                    2. Activá el anclaje Bluetooth en el teléfono.{'\n'}
                    3. En el host: elegí la conexión Bluetooth y mirá la dirección.{'\n'}
                    4. Escribila acá abajo → Conectar.
                  </Text>
                </>
              ) : null}
              <Text style={styles.label}>Host IP</Text>
              <TextInput
                style={styles.input}
                value={host}
                onChangeText={setHost}
                placeholder="192.168.1.20"
                placeholderTextColor={DOKKE_GLASS.ink3}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="numbers-and-punctuation"
                editable={!busy}
              />

              <Text style={styles.label}>Port</Text>
              <TextInput
                style={styles.input}
                value={port}
                onChangeText={setPort}
                placeholder={String(DEFAULT_PORT)}
                placeholderTextColor={DOKKE_GLASS.ink3}
                keyboardType="number-pad"
                editable={!busy}
              />

              {error ? <Text style={styles.error}>{error}</Text> : null}

              <Pressable
                style={[styles.button, busy && styles.buttonDisabled]}
                disabled={busy || !host.trim()}
                onPress={() => connectAddress(mode)}
              >
                {busy ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.buttonText}>
                    {mode === 'bluetooth' ? 'Conectar por Bluetooth' : 'Conectar'}
                  </Text>
                )}
              </Pressable>
            </>
          ) : null}

          {mode === 'usb' ? (
            <>
              <Text style={styles.usbTitle}>Conexión por cable</Text>
              <Text style={styles.usbBody}>
                1. En el host PC: Activar USB (adb reverse).{'\n'}
                2. USB debugging encendido en el teléfono.{'\n'}
                3. Cable conectado → Connect abajo.
              </Text>
              <Text style={styles.label}>Port</Text>
              <TextInput
                style={styles.input}
                value={port}
                onChangeText={setPort}
                placeholder={String(DEFAULT_PORT)}
                placeholderTextColor={DOKKE_GLASS.ink3}
                keyboardType="number-pad"
                editable={!busy}
              />
              <Text style={styles.hintMono}>ws://127.0.0.1:{port || DEFAULT_PORT}</Text>
              {error ? <Text style={styles.error}>{error}</Text> : null}
              <Pressable
                style={[styles.button, busy && styles.buttonDisabled]}
                disabled={busy}
                onPress={connectUsb}
              >
                {busy ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.buttonText}>Conectar por USB</Text>
                )}
              </Pressable>
            </>
          ) : null}

          {mode === 'qr' ? (
            <>
              <Text style={styles.usbTitle}>Escaneá el QR del host</Text>
              {!permission?.granted ? (
                <>
                  <Text style={styles.usbBody}>
                    Necesitamos la cámara para leer el código del panel ClicX.
                  </Text>
                  <Pressable style={styles.button} onPress={requestPermission}>
                    <Text style={styles.buttonText}>Permitir cámara</Text>
                  </Pressable>
                </>
              ) : (
                <View style={styles.cameraWrap}>
                  <CameraView
                    style={styles.camera}
                    facing="back"
                    barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
                    onBarcodeScanned={busy ? undefined : onBarcode}
                  />
                </View>
              )}
              {scanError ? <Text style={styles.error}>{scanError}</Text> : null}
              {error ? <Text style={styles.error}>{error}</Text> : null}
              {busy ? (
                <ActivityIndicator color="#fff" style={{ marginTop: 12 }} />
              ) : null}
            </>
          ) : null}
        </DokkeCard>

        <Text style={styles.help}>
          {mode === 'usb'
            ? 'El host debe tener “Activar USB” y el cable conectado.'
            : mode === 'qr'
              ? 'Abrí “Mostrar QR” en el host ClicX de la PC.'
              : mode === 'bluetooth'
                ? 'Con el anclaje Bluetooth activo. Alcanza para puntero, teclado y deck; los archivos van lentos.'
                : 'Misma Wi‑Fi que la PC (no datos móviles). IP exacta del host + puerto 51234.'}
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const makeStyles = ({ DOKKE_GLASS }: Palette) =>
  StyleSheet.create({
    root: {
      flex: 1,
      backgroundColor: DOKKE_GLASS.canvas,
    },
    scroll: {
      flexGrow: 1,
      paddingHorizontal: 22,
      paddingVertical: 36,
      justifyContent: 'center',
    },
    hero: {
      marginBottom: 22,
      gap: 10,
    },
    brand: {
      color: DOKKE_GLASS.ink,
      fontSize: 40,
      fontWeight: '700',
      letterSpacing: -1.2,
    },
    statusRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
    },
    dot: {
      width: 8,
      height: 8,
      borderRadius: 4,
      backgroundColor: DOKKE_GLASS.inkDim,
    },
    dotBusy: {
      backgroundColor: DOKKE_GLASS.green,
    },
    statusText: {
      color: DOKKE_GLASS.ink2,
      fontSize: 14,
      fontWeight: '500',
      letterSpacing: -0.2,
    },
    tagline: {
      color: DOKKE_GLASS.ink2,
      fontSize: 15,
      lineHeight: 21,
      letterSpacing: -0.2,
    },
    modeRow: {
      flexDirection: 'row',
      gap: 2,
      marginBottom: 16,
      padding: 3,
      borderRadius: 12,
      backgroundColor: DOKKE_GLASS.glass,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: DOKKE_GLASS.edge,
    },
    modeChip: {
      flex: 1,
      paddingVertical: 9,
      borderRadius: 10,
      alignItems: 'center',
    },
    modeChipOn: {
      backgroundColor: DOKKE_GLASS.accent,
    },
    modeText: {
      color: DOKKE_GLASS.ink2,
      fontSize: 13,
      fontWeight: '600',
      letterSpacing: -0.2,
    },
    modeTextOn: {
      color: DOKKE_GLASS.ink,
    },
    card: {
      padding: 18,
      gap: 8,
    },
    label: {
      color: DOKKE_GLASS.ink2,
      fontSize: 12,
      marginTop: 6,
      fontWeight: '600',
      letterSpacing: -0.1,
    },
    input: {
      backgroundColor: 'rgba(0,0,0,0.28)',
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: DOKKE_GLASS.edge,
      borderRadius: 12,
      paddingHorizontal: 14,
      paddingVertical: 13,
      color: DOKKE_GLASS.ink,
      fontSize: 17,
      letterSpacing: -0.3,
    },
    button: {
      marginTop: 14,
      backgroundColor: DOKKE_GLASS.accent,
      borderRadius: 12,
      paddingVertical: 15,
      alignItems: 'center',
    },
    buttonDisabled: { opacity: 0.45 },
    buttonText: {
      color: DOKKE_GLASS.ink,
      fontSize: 17,
      fontWeight: '600',
      letterSpacing: -0.3,
    },
    error: {
      color: DOKKE_GLASS.red,
      marginTop: 6,
      fontSize: 14,
    },
    help: {
      marginTop: 24,
      color: DOKKE_GLASS.ink3,
      fontSize: 13,
      lineHeight: 19,
      textAlign: 'center',
    },
    usbTitle: {
      color: DOKKE_GLASS.ink,
      fontSize: 16,
      fontWeight: '600',
      letterSpacing: -0.3,
      marginBottom: 4,
    },
    usbBody: {
      color: DOKKE_GLASS.ink2,
      fontSize: 14,
      lineHeight: 21,
      marginBottom: 8,
    },
    hintMono: {
      color: DOKKE_GLASS.amber,
      fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
      fontSize: 13,
      marginTop: 4,
    },
    cameraWrap: {
      height: 260,
      borderRadius: 16,
      overflow: 'hidden',
      marginTop: 8,
      backgroundColor: DOKKE_GLASS.canvas,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: DOKKE_GLASS.edge,
    },
    camera: {
      flex: 1,
    },
  });
