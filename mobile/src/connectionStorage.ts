import AsyncStorage from '@react-native-async-storage/async-storage';
import { DEFAULT_PORT } from './protocol';

const KEY = 'clicx.connection.v1';

export type ConnectionMode = 'wifi' | 'usb' | 'qr' | 'bluetooth';

export type SavedConnection = {
  mode: ConnectionMode;
  host: string;
  port: number;
};

export async function loadSavedConnection(): Promise<SavedConnection | null> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as Partial<SavedConnection>;
    const mode = data.mode;
    if (mode !== 'wifi' && mode !== 'usb' && mode !== 'qr' && mode !== 'bluetooth') {
      return null;
    }
    const host = typeof data.host === 'string' ? data.host : '';
    const port =
      typeof data.port === 'number' && data.port > 0 && data.port < 65536
        ? data.port
        : DEFAULT_PORT;
    return { mode, host, port };
  } catch {
    return null;
  }
}

export async function saveConnection(data: SavedConnection): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(data));
  } catch {
    // ignore storage failures
  }
}
