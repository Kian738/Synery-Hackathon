import { useFrame, useThree } from "@react-three/fiber";
import { useRef } from "react";

export interface Detail { near: boolean; y: number }

/** Tells the scene whether the viewer is close enough to see furniture detail, and at which height they are looking. Small buildings
 *  are always "near"; for large ones the switch happens when the camera is closer than about half the building's span (with
 *  hysteresis, so it never flickers). The height is rounded to 2 m steps so a floor only re-renders when the view really moves. */
export function DetailWatcher({ span, onChange }: { span: number; onChange: (d: Detail) => void }) {
  const { camera, controls } = useThree();
  const last = useRef<Detail | null>(null);
  useFrame(() => {
    const target = (controls as unknown as { target?: { y: number; distanceTo(v: unknown): number } } | null)?.target;
    const distance = target ? camera.position.distanceTo(target as never) : 0;
    const enter = Math.max(35, span * 0.42), leave = enter * 1.2, before = last.current;
    const near = span < 60 ? true : before === null ? distance < leave : before.near ? distance < leave : distance < enter;
    const y = target ? Math.round(target.y / 2) * 2 : 0;
    if (!before || before.near !== near || before.y !== y) { last.current = { near, y }; onChange(last.current); }
  });
  return null;
}
