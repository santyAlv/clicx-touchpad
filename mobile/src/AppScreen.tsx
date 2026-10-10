import { useState } from 'react';
import type { DeckPage } from './deckConfig';
import type { ClicxMessage } from './protocol';
import type { HostFeatures } from './useClicxConnection';
import { ActionsScreen } from './ActionsScreen';
import { AppVolumeScreen } from './AppVolumeScreen';
import { ClipboardScreen } from './ClipboardScreen';
import { FilesScreen } from './FilesScreen';
import { HomeScreen, type HomeScreenId } from './HomeScreen';
import { KeyboardScreen } from './KeyboardScreen';
import { MediaScreen } from './MediaScreen';
import { SystemScreen } from './SystemScreen';
import { UsageScreen } from './UsageScreen';
import { Touchpad, type TouchpadProps } from './Touchpad';
import { WindowsScreen } from './WindowsScreen';

export type AppScreenId = 'home' | HomeScreenId;

type Props = {
  screen: AppScreenId;
  setScreen: (s: AppScreenId) => void;
  hostName: string;
  features: HostFeatures | null;
  send: (msg: ClicxMessage) => void;
  onReply: (cb: (data: Record<string, unknown>) => void) => () => void;
  sendString: (data: string) => void;
  sendBinary: (data: ArrayBuffer | Uint8Array) => void;
  onBinary: (cb: (data: ArrayBuffer) => void) => () => void;
  touchpadProps: TouchpadProps;
};

/** Top-level navigator: Touchpad (home hidden) ⇄ Home ⇄ Control Center sub-screens. */
export function AppScreen({
  screen,
  setScreen,
  hostName,
  send,
  onReply,
  sendString,
  sendBinary,
  onBinary,
  touchpadProps,
}: Props) {
  if (screen === 'home') {
    return <HomeScreen hostName={hostName} onOpen={(id) => setScreen(id)} />;
  }
  if (screen === 'touchpad') {
    return (
      <Touchpad
        {...touchpadProps}
        onHome={() => setScreen('home')}
      />
    );
  }
  const back = () => setScreen('home');
  switch (screen) {
    case 'system':
      return <SystemScreen send={send} onReply={onReply} onBack={back} />;
    case 'actions':
      return <ActionsScreen send={send} onBack={back} />;
    case 'media':
      return <MediaScreen send={send} onBack={back} />;
    case 'keyboard':
      return <KeyboardScreen send={send} onBack={back} />;
    case 'appvolume':
      return <AppVolumeScreen send={send} onReply={onReply} onBack={back} />;
    case 'windows':
      return <WindowsScreen send={send} onReply={onReply} onBack={back} />;
    case 'clipboard':
      return <ClipboardScreen send={send} onReply={onReply} onBack={back} />;
    case 'usage':
      return <UsageScreen send={send} onReply={onReply} onBack={back} />;
    case 'files':
      return (
        <FilesScreen
          send={send}
          sendString={sendString}
          sendBinary={sendBinary}
          onBinary={onBinary}
          onReply={onReply}
          onBack={back}
        />
      );
    default:
      return <Touchpad {...touchpadProps} onHome={() => setScreen('home')} />;
  }
}
