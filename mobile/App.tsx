import { StatusBar } from 'expo-status-bar';
import { useKeepAwake } from 'expo-keep-awake';
import * as ScreenOrientation from 'expo-screen-orientation';
import { useEffect, useState } from 'react';
import { StyleSheet } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { ConnectScreen } from './src/ConnectScreen';
import { AppScreen, type AppScreenId } from './src/AppScreen';
import {
  LASER_SIZE_DEFAULT,
  PAD_COLOR_DEFAULT,
  SENS_DEFAULT,
  type TouchpadProps,
} from './src/Touchpad';
import { loadStoredAccent } from './src/palette';
import { useClicxConnection } from './src/useClicxConnection';

function KeepAwakeOn() {
  useKeepAwake('clicx');
  return null;
}

export default function App() {
  const { status, error, hostInfo, textFieldFocused, deckPages, features, connect, disconnect, send, sendMove, onReply, sendString, sendBinary, onBinary } =
    useClicxConnection();
  const [screen, setScreen] = useState<AppScreenId>('touchpad');
  const [sensitivity, setSensitivity] = useState(SENS_DEFAULT);
  const [invertScroll, setInvertScroll] = useState(false);
  const [acceleration, setAcceleration] = useState(true);
  const [doubleClick, setDoubleClick] = useState(true);
  const [holdToSelect, setHoldToSelect] = useState(true);
  const [landscapeLock, setLandscapeLock] = useState(false);
  const [classicMouse, setClassicMouse] = useState(false);
  const [keyboardOnEdit, setKeyboardOnEdit] = useState(true);
  const [padColor, setPadColor] = useState(PAD_COLOR_DEFAULT);
  const [laserSize, setLaserSize] = useState(LASER_SIZE_DEFAULT);

  useEffect(() => {
    ScreenOrientation.unlockAsync().catch(() => {});
  }, []);

  // Open in the colour the host last sent, before it reconnects and says so again.
  useEffect(() => {
    void loadStoredAccent();
  }, []);

  useEffect(() => {
    const apply = async () => {
      try {
        if (landscapeLock && status === 'connected') {
          await ScreenOrientation.lockAsync(
            ScreenOrientation.OrientationLock.LANDSCAPE,
          );
        } else {
          await ScreenOrientation.unlockAsync();
        }
      } catch {
        // Expo Go / platform may ignore some locks
      }
    };
    apply();
  }, [landscapeLock, status]);

  // Connection lost / disconnect → unlock orientation (back to normal)
  useEffect(() => {
    if (status === 'connected') return;
    if (!landscapeLock) return;
    setLandscapeLock(false);
    ScreenOrientation.unlockAsync().catch(() => {});
  }, [status, landscapeLock]);

  // When disconnected return to the touchpad (the ConnectScreen replaces it anyway).
  useEffect(() => {
    if (status !== 'connected') setScreen('touchpad');
  }, [status]);

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.root} edges={['top', 'left', 'right', 'bottom']}>
        <StatusBar style="light" />
        {status === 'connected' ? <KeepAwakeOn /> : null}
        {status === 'connected' ? (
          (() => {
            const touchpadProps: TouchpadProps = {
              send,
              sendMove,
              sensitivity,
              onSensitivityChange: setSensitivity,
              invertScroll,
              onInvertScrollChange: setInvertScroll,
              acceleration,
              onAccelerationChange: setAcceleration,
              doubleClick,
              onDoubleClickChange: setDoubleClick,
              holdToSelect,
              onHoldToSelectChange: setHoldToSelect,
              landscapeLock,
              onLandscapeLockChange: setLandscapeLock,
              classicMouse,
              onClassicMouseChange: setClassicMouse,
              keyboardOnEdit,
              onKeyboardOnEditChange: setKeyboardOnEdit,
              textFieldFocused,
              padColor,
              onPadColorChange: setPadColor,
              laserSize,
              onLaserSizeChange: setLaserSize,
              onDisconnect: disconnect,
              hostInfo,
              deckPages,
            };
            return (
              <AppScreen
                screen={screen}
                setScreen={setScreen}
                hostName={hostInfo ?? 'ClicX'}
                features={features}
                send={send}
                onReply={onReply}
                sendString={sendString}
                sendBinary={sendBinary}
                onBinary={onBinary}
                touchpadProps={touchpadProps}
              />
            );
          })()
        ) : (
          <ConnectScreen status={status} error={error} onConnect={connect} />
        )}
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#273338',
  },
});
