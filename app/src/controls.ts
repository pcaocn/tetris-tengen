// Single key-map table (spec section 7). `down` is sent on keydown, `up` on
// keyup. Browser auto-repeat is ignored; left/right auto-repeat comes from
// Python's DAS (spec 2.4). `start` (Enter) is handled specially as
// Start/Pause (spec section 5, 7).
//
// Protocol note: `left_off`/`right_off` are a documented extension to the
// spec 2.2 action list — Python-side DAS needs key-release events (spec 2.4
// says "stop on keyup" but omits the release actions).
export interface KeyBinding {
  down: string;
  up?: string;
}

export const KEY_MAP: Record<string, KeyBinding> = {
  ArrowLeft: { down: "left", up: "left_off" },
  ArrowRight: { down: "right", up: "right_off" },
  ArrowDown: { down: "soft_drop_on", up: "soft_drop_off" },
  KeyZ: { down: "rotate_ccw" },
  KeyX: { down: "rotate_cw" },
  Enter: { down: "start" },
};
