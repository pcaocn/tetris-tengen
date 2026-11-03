// ============================================================
// WHAT THIS FILE DOES
// ============================================================
// The single, complete table of keyboard bindings: browser `KeyboardEvent.code`
// -> protocol action name. App.tsx consults it on every keydown/keyup; this
// file holds nothing else, so the entire control scheme lives in one place.
//
// WHY A TABLE INSTEAD OF A SWITCH
// -------------------------------
// Each binding is data, not behavior: the value is the *name of a protocol
// action* that is forwarded verbatim to the Python core over
// `invoke("send_input", ...)`. The core owns what the action means and how
// auto-repeat works; this table only translates key identities. Adding a key
// is a one-line change here, with no UI logic touched.
//
// WHY `up` EXISTS AT ALL
// ----------------------
// Browser auto-repeat is ignored (App.tsx drops `e.repeat` events) because
// the NES-style feel comes from Python's DAS: the core counts frames itself
// after seeing `left`/`right`, and it cannot know a key is held unless it is
// also told when it is released. Hence the paired `*_off` actions on keyup --
// a documented extension to the spec 2.2 action list (spec 2.4 says "stop on
// keyup" but never names the release actions).
//
// Single key-map table (spec section 7). `down` is sent on keydown, `up` on
// keyup. Browser auto-repeat is ignored; left/right auto-repeat comes from
// Python's DAS (spec 2.4). `start` (Enter) is handled specially as
// Start/Pause (spec section 5, 7).
//
// Protocol note: `left_off`/`right_off` are a documented extension to the
// spec 2.2 action list — Python-side DAS needs key-release events (spec 2.4
// says "stop on keyup" but omits the release actions).
export interface KeyBinding {
  /** Action sent to the core on keydown. */
  down: string;
  /** Action sent on keyup, when the core needs the release (DAS keys). */
  up?: string;
}

// The map itself. Keyed by `event.code` (physical key), NOT `event.key`:
// code is layout-independent, so Z/X stay in place on AZERTY/QWERTZ and the
// arrows always work. Only Enter is special-cased by App.tsx — its value
// "start" is intercepted there and routed to the Start/Pause logic instead
// of being sent to the core as-is (spec section 5, 7).
export const KEY_MAP: Record<string, KeyBinding> = {
  // Horizontal movement needs both halves of the DAS handshake: the core
  // starts its repeat counter on `left`/`right` and stops it on the `_off`.
  ArrowLeft: { down: "left", up: "left_off" },
  ArrowRight: { down: "right", up: "right_off" },
  // Soft drop is a held state too: `soft_drop_on` switches the core to the
  // faster soft-drop gravity, `soft_drop_off` switches it back.
  ArrowDown: { down: "soft_drop_on", up: "soft_drop_off" },
  // Rotations are momentary taps — no release event needed, so no `up`.
  KeyZ: { down: "rotate_ccw" },
  KeyX: { down: "rotate_cw" },
  // Handled locally by App.tsx (title -> options -> game, pause/restart);
  // never forwarded to the core on the pre-game screens.
  Enter: { down: "start" },
};
