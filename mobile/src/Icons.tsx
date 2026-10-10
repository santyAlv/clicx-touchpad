import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';

type IconProps = {
  size?: number;
  color?: string;
};

/** Icons via Expo vector set (no react-native-svg — avoids Metro/codegen issues in Expo Go). */

export function IconSettings({ size = 22, color = '#fff' }: IconProps) {
  return <Ionicons name="settings-outline" size={size} color={color} />;
}

export function IconWifi({ size = 16, color = '#fff' }: IconProps) {
  return <Ionicons name="wifi" size={size} color={color} />;
}

export function IconClose({ size = 22, color = '#fff' }: IconProps) {
  return <Ionicons name="close" size={size} color={color} />;
}

export function IconChevronLeft({ size = 26, color = '#fff' }: IconProps) {
  return <Ionicons name="chevron-back" size={size} color={color} />;
}

export function IconChevronRight({ size = 26, color = '#fff' }: IconProps) {
  return <Ionicons name="chevron-forward" size={size} color={color} />;
}

export function IconChevronDown({ size = 14, color = '#fff' }: IconProps) {
  return <Ionicons name="chevron-down" size={size} color={color} />;
}

export function IconChevronUp({ size = 14, color = '#fff' }: IconProps) {
  return <Ionicons name="chevron-up" size={size} color={color} />;
}

export function IconVolume({ size = 20, color = '#fff' }: IconProps) {
  return <Ionicons name="volume-high" size={size} color={color} />;
}

export function IconVolumeMute({ size = 20, color = '#fff' }: IconProps) {
  return <Ionicons name="volume-mute" size={size} color={color} />;
}

/** Mouse cursor / presentation pointer. Change `color` for laser color. */
export function IconPointer({ size = 26, color = '#9CB080' }: IconProps) {
  return (
    <MaterialCommunityIcons name="cursor-default" size={size} color={color} />
  );
}
