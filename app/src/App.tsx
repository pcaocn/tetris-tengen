// ============================================================
// WHAT THIS FILE DOES
// ============================================================
// The root component: the one place where the window, the keyboard, and
// the audio all meet. Everything else renders state; App *lives in time*.
//
// THE DATA FLOW, END TO END
// --------------------------
//   Python core --(JSON on stdout)--> Rust shell --(Tauri "game-state")
//     --> useGameState --> `state` HERE --> <Board/>, <ScorePanel/>, ...
//   Keyboard HERE --(invoke "send_input" / "new_game" / ...)-->
//     Rust shell --(JSON on stdin)--> Python core.
// The UI's only outputs are those invoke calls and these draw/sound
// decisions. No rule of Tetris is computed in this file.
//
// THE FOUR CONCERNS, IN FILE ORDER
// --------------------------------
//   1. CONSTANTS -- music/sfx URL tables, menu lists, cheat sequences.
//   2. INPUT     -- the window keydown/keyup effect: menu navigation,
//                   Konami detection, in-game cheats, then the KEY_MAP
//                   forwarding to the core.
//   3. MUSIC     -- the <audio>-element effects that carry out the plans
//                   from audioPlan.ts (the "why" lives there; this is the
//                   "how": which element gets which src, when).
//   4. SFX       -- the WebAudio graph for one-shot sounds (playSfx).
//
// WHY SO MANY useRef NEXT TO useState
// -----------------------------------
// The keyboard effect is attached ONCE (empty-ish deps) and therefore
// closes over stale values; the refs give the handler a current-value
// window into state that lives in React (stateRef.current = state on
// every render). The pattern repeats for every value the handler reads:
// a state for rendering, a ref mirror for the listener. If you add a new
// pre-game option, you will need both halves.
import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  BACKGROUND,
  FONT_SMOOTH,
  LOGICAL_HEIGHT,
  LOGICAL_WIDTH,
  LAYOUT,
  PANEL_BG,
  TEXT_BRIGHT,
} from "./theme";
import { KEY_MAP } from "./controls";
import { useGameState } from "./hooks/useGameState";
import {
  advancePlaylist,
  initialAudioState,
  planMusic,
  stepAudio,
  type AudioState,
} from "./audioPlan";
import {
  afterResume,
  planSfx,
  type SfxContextState,
} from "./sfxPlan";
import type { OverlayPhase } from "./components/Overlay";
// (The component imports below pull in the renderers; each is commented
// in its own file.)
import { Board } from "./components/Board";
import { NextPreview } from "./components/NextPreview";
import { ScorePanel } from "./components/ScorePanel";
import { StatsPanel } from "./components/StatsPanel";
import { Overlay } from "./components/Overlay";

// Music (owner request 2026-10-25). The title screen previews the four
// gameplay themes (02-05); the choice is sent with new_game. The core
// reports the music phase, which picks the one-shot cue:
//   "level_complete" -> 06 (end of stage), played ONCE; the next level
//                       then starts by itself (owner change 2026-10-29).
//                       There is no Katyusha (07) chain and no wait for
//                       Enter — which is why 07 is not imported below.
//   "milestone"      -> 09 (victory), on cleared levels 9/19/29...
//   "game_over"      -> 08, once.
// The cue plays over the paused theme (see audioPlan.ts); the theme keeps
// its source and position, so a celebration never costs a reload.
import introUrl from "../../music/01_-_Tetris_Tengen_-_NES_-_Introduction.ogg?url";
import loginskaUrl from "../../music/02_-_Tetris_Tengen_-_NES_-_Loginska.ogg?url";
import bradinskyUrl from "../../music/03_-_Tetris_Tengen_-_NES_-_Bradinsky.ogg?url";
import kalinkaUrl from "../../music/04_-_Tetris_Tengen_-_NES_-_Kalinka.ogg?url";
import troikaUrl from "../../music/05_-_Tetris_Tengen_-_NES_-_Troika.ogg?url";
import endOfStageUrl from "../../music/06_-_Tetris_Tengen_-_NES_-_End_of_Stage.ogg?url";
import gameOverMusicUrl from "../../music/08_-_Tetris_Tengen_-_NES_-_Game_Over.ogg?url";
import victoryUrl from "../../music/09_-_Tetris_Tengen_-_NES_-_Victory.ogg?url";
// The `?url` suffix is a Vite convention: instead of bundling the file's
// bytes, the import evaluates to a hashed URL the browser can fetch (e.g.
// "/assets/01_-_...ogg"). Vite's declare-module shims for "*.ogg?url" and
// "*.mp3?url" live in vite-env.d.ts, which is why these imports typecheck.
// Sound effects (owner request 2026-10-25): the exact original drop,
// line-clear, and menu-select sounds, plus the game-over firework
// rockets, from the owner's files in music/.
import blockDropUrl from "../../music/tetris_block_drop.mp3?url";
import lineClearUrl from "../../music/tetris_line_clear.mp3?url";
import select1Url from "../../music/tetris_select1.mp3?url";
import select2Url from "../../music/tetris_select2.mp3?url";
import firework1Url from "../../music/tetris_firework1.mp3?url";
import firework2Url from "../../music/tetris_firework2.mp3?url";
import firework3Url from "../../music/tetris_firework3.mp3?url";
import firework4Url from "../../music/tetris_firework4.mp3?url";

const SFX_URLS: Record<string, string> = {
  drop: blockDropUrl,
  clear: lineClearUrl,
  select1: select1Url,
  select2: select2Url,
  fw1: firework1Url,
  fw2: firework2Url,
  fw3: firework3Url,
  fw4: firework4Url,
};
const FIREWORK_SEQUENCE = ["fw1", "fw2", "fw3", "fw4"];
// Per-sound gain: the block drop at 3x per owner 2026-10-25.
const SFX_GAINS: Record<string, number> = { drop: 3.0 };

// Gameplay themes keyed by the two-digit music id the core reports in
// state.music_track. The ids match the original game's numbering (02..05);
// the core echoes them back so the UI and core stay in sync.
const GAMEPLAY_TRACKS: Record<string, string> = {
  "02": loginskaUrl,
  "03": bradinskyUrl,
  "04": kalinkaUrl,
  "05": troikaUrl,
};
// Every playable theme, including the introduction (01), keyed by the
// music id the core reports.
const THEME_URLS: Record<string, string> = {
  "01": introUrl,
  ...GAMEPLAY_TRACKS,
};
// Introduction (01) plays on the intro page only — it is not selectable
// and not part of the gameplay loop (owner correction 2026-10-27,
// matching the original game).
const MUSIC_CYCLE = ["02", "03", "04", "05"];
// The options-page menu, and the parallel array of ids sent in new_game.
// Index i of MUSIC_MENU pairs with MUSIC_IDS[i]: "Silent" -> null (no
// music), "Loginska" -> "02", and so on. Two arrays instead of one array
// of objects because the ids are protocol data and the labels are display
// strings; both must stay the same length and order.
const MUSIC_MENU = ["Silent", "Loginska", "Bradinsky", "Kalinka", "Troika"];
const MUSIC_IDS: (string | null)[] = [null, "02", "03", "04", "05"];
// Handicap rows (owner request 2026-10-25): unfinished garbage rows.
// Indexed in lockstep with OptionsScreen's display list; the VALUE here
// is what reaches new_game (rows dealt at spawn).
const HANDICAP_LEVELS = [0, 3, 6, 9, 12];

// Scales the logical space to fit the window with uniform scaling and
// letterboxing; optional integer-scale mode snaps to whole numbers
// (spec 6.4). The UI is laid out in logical units only.
/**
 * The window-to-logical scale factor, and the whole letterboxing story.
 *
 * The UI is laid out in logical units (2048x1920); the window can be any
 * size. One uniform scale — the SMALLER of width-ratio and height-ratio —
 * fits the whole logical rectangle inside the window; the leftover space
 * in the other dimension is the letterbox (the .game-area div is centered
 * and sized exactly to areaWidth x areaHeight below).
 *
 * @param integerScale  when on, snap the scale DOWN to a whole number
 *   (Math.floor) so logical pixels map to 1, 2, 3... device pixels evenly
 *   — the retro-pixel look, no half-pixel blur. Math.max(1, ...) floors it
 *   at 1x so a small window still shows the full layout rather than a
 *   cropped part of it.
 */
function fitScale(width: number, height: number, integerScale: boolean): number {
  const raw = Math.min(width / LOGICAL_WIDTH, height / LOGICAL_HEIGHT);
  if (integerScale) return Math.max(1, Math.floor(raw));
  return raw;
}

// Konami cheat (owner request 2026-10-25): typing this key sequence on
// the title screen unlocks cheat mode; digits 0-9 then jump the level
// during play.
//
// HOW THE MATCHING WORKS (see the keydown handler): cheatPosRef holds how
// far into the sequence we are. On each key, if it matches the NEXT
// expected entry the pointer advances; when it reaches the end, the cheat
// unlocks and the pointer resets. On a mismatch the pointer restarts at 1
// (not 0!) if the pressed key happens to be the FIRST entry — so holding
// Up, Up, Up, ... still walks the sequence despite the failed steps. This
// is the classic KMP-style prefix trick in miniature.
const CHEAT_CODE = [
  "ArrowUp",
  "ArrowUp",
  "ArrowDown",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
  "ArrowLeft",
  "ArrowRight",
  "KeyB",
  "KeyA",
];

/**
 * The root component. Reading order inside the body:
 *   1. state + ref mirrors (the listener window, see the header note)
 *   2. audio element refs and the sound-effects context
 *   3. callbacks: playSfx, send, pressStart
 *   4. effects: resize, keyboard, music manager, gesture kick
 *   5. derived layout numbers and the JSX tree
 */
export default function App() {
  // The single game-state subscription (see useGameState.ts).
  const { state, notice, error, retry } = useGameState();
  // Window size, tracked to recompute the scale on every resize.
  const [size, setSize] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  });
  const [integerScale, setIntegerScale] = useState(false); // default off (spec 6.4)
  // "Has a game ever been started" — the title/options -> game gate.
  // The ref mirror exists for the keydown handler (attached once).
  const hasStartedRef = useRef(false);
  const [started, setStarted] = useState(false);
  const stateRef = useRef(state);
  stateRef.current = state;
  const [cheatUnlocked, setCheatUnlocked] = useState(false);
  // cheatRef is the listener's view of cheatUnlocked; cheatPosRef is the
  // Konami progress pointer (index of the next expected key).
  const cheatRef = useRef(false);
  const cheatPosRef = useRef(0);
  // Title -> options -> game flow (owner request 2026-10-25): the title
  // shows only the cathedral; Enter opens the options page.
  const [atOptions, setAtOptions] = useState(false);
  const atOptionsRef = useRef(false);
  // Title music menu (owner request 2026-10-25).
  const [musicSel, setMusicSel] = useState(0);
  const musicSelRef = useRef(0);
  // "The user moved the music menu at least once" — gates the preview:
  // without it the options page would blast the selected track the moment
  // it opens. Cleared never; once touched, previews stay live.
  const [menuTouched, setMenuTouched] = useState(false);
  // Title handicap menu (owner request 2026-10-25).
  const [handicapSel, setHandicapSel] = useState(0);
  const handicapSelRef = useRef(0);
  // Options page: which column has focus (0 = music, 1 = handicap).
  const [activeCol, setActiveCol] = useState(0);
  const activeColRef = useRef(0);
  // Audio elements managed imperatively (see the effects below).
  // - audioARef / audioBRef: the theme music. Two of them, so the
  //   playlist can hand over to a preloaded track without a gap; the
  //   active one is whichever `activeSlotRef` names.
  // - cueRef: the one-shot celebration / game-over cue. It plays over
  //   the theme, so the theme keeps its position and is never reloaded.
  const audioARef = useRef<HTMLAudioElement>(null);
  const audioBRef = useRef<HTMLAudioElement>(null);
  const cueRef = useRef<HTMLAudioElement>(null);
  const activeSlotRef = useRef<"a" | "b">("a");
  // The audio bookkeeping (what is loaded, what is preloaded) lives in
  // the pure state machine, so it can be tested without a browser.
  const audioStateRef = useRef<AudioState>(initialAudioState());
  // "The browser refused autoplay; replay on the next gesture." Set by the
  // theme-play rejection below, cleared by the kick handler's success.
  const needsGestureRef = useRef(false);
  // Mirror of `paused` for the kick handler (attached once, closes over
  // nothing) so a gesture during pause doesn't yank the theme out of
  // its paused state.
  const gamePausedRef = useRef(false);

  // The theme element that is playing, and the one holding the next
  // track. The two swap roles when a track ends.
  // Plain functions (not useCallback): they read a ref, so identity is
  // irrelevant and re-creating them per render is free.
  const activeEl = () =>
    activeSlotRef.current === "a" ? audioARef.current : audioBRef.current;
  const spareEl = () =>
    activeSlotRef.current === "a" ? audioBRef.current : audioARef.current;

  // Sound effects (owner decisions 2026-10-25): the exact original
  // sounds from the owner's files — block drop on every lock, line clear
  // on every clear event, select1/select2 when a menu selection moves
  // down/up, and the firework rockets looping on a top-5 game over.
  //
  // Audio bug fix (owner request 2026-10-29): the sound effects used to
  // disappear completely later in a long game. Two causes:
  // - every sound created a GainNode that was connected to the
  //   destination and never disconnected, so the audio graph grew by two
  //   nodes per locked piece until the context gave up;
  // - the context was only resumed when its state was exactly
  //   "suspended", and the resume was never awaited. WebKit spells an
  //   interrupted context "interrupted", so after any interruption the
  //   context stayed dead and every later sound was silent.
  // Now the nodes are released when the sound ends, and the context is
  // rebuilt if it cannot be resumed.
  const popCtxRef = useRef<AudioContext | null>(null);
  const sfxBuffersRef = useRef<Record<string, AudioBuffer>>({});

  /**
   * Plays one named sound (see SFX_URLS) through the WebAudio context and
   * returns the source node (or null when nothing could be played) — the
   * firework loop below needs the node to await its `ended`.
   *
   * THE LIFECYCLE, IN STEPS:
   *   Step 1: ask the PURE policy (sfxPlan.planSfx) what to do with the
   *           context: create / resume / rebuild / use.
   *   Step 2: carry it out. "resume" is followed by a second policy call
   *           (afterResume) on the post-resume state, because a resume
   *           can fail silently — an interrupted context that will not
   *           come back gets replaced on the spot.
   *   Step 3: if the context is finally "running", decode (once, cached
   *           per context — buffers are bound to their context's sample
   *           rate) and fire the sound through its own gain node.
   *
   * Empty deps: the callback closes over only refs, so it is created once
   * and can be a stable dependency of the effects below.
   */
  const playSfx = useCallback(
    async (name: string): Promise<AudioBufferSourceNode | null> => {
      // Step 3, the actual sound: buffer -> source -> gain -> destination.
      const emit = async (ctx: AudioContext): Promise<AudioBufferSourceNode | null> => {
        // Decode cache: fetch+decode is expensive; every later play of the
        // same sound reuses the AudioBuffer (safe — sources are cheap
        // wrappers; the buffer is read-only).
        let buf = sfxBuffersRef.current[name];
        if (!buf) {
          const res = await fetch(SFX_URLS[name]);
          const raw = await res.arrayBuffer();
          buf = await ctx.decodeAudioData(raw);
          sfxBuffersRef.current[name] = buf;
        }
        const src = ctx.createBufferSource();
        src.buffer = buf;
        const gain = ctx.createGain();
        gain.gain.value = SFX_GAINS[name] ?? 1.0;
        src.connect(gain).connect(ctx.destination);
        // Release the nodes when the sound ends: leaving them attached to
        // the destination leaks a gain node per sound, and the pile-up
        // eventually silences the whole context.
        src.addEventListener("ended", () => {
          try {
            src.disconnect();
            gain.disconnect();
          } catch {
            // already released
          }
        });
        src.start();
        return src;
      };
      // The decision of what to do with the context is pure and lives in
      // sfxPlan.ts, so it can be tested without a browser.
      // Steps 1-2 helpers: build() replaces the context wholesale. Note
      // the buffer cache is WIPED here: AudioBuffers are tied to the
      // sample rate of the context that decoded them, so reusing old
      // ones on a fresh context risks wrong-pitch (or failed) playback.
      const build = (): AudioContext => {
        const fresh = new AudioContext();
        popCtxRef.current = fresh;
        // The decoded buffers belong to the old context's sample rate.
        sfxBuffersRef.current = {};
        // Self-healing hook: if the context is parked later (any state
        // that is neither running nor closed — including WebKit's
        // "interrupted"), try to bring it back on the spot. This is the
        // safety net behind the policy decisions.
        fresh.onstatechange = () => {
          if (fresh.state !== "running" && fresh.state !== "closed") {
            fresh.resume().catch(() => {});
          }
        };
        return fresh;
      };
      try {
        // Steps 1-2: consult the policy, then act on it.
        let ctx = popCtxRef.current;
        let plan = planSfx({
          state: (ctx?.state as SfxContextState | undefined) ?? null,
        });
        if (plan.action === "create") {
          ctx = build();
          await ctx.resume().catch(() => {});
        } else if (plan.action === "resume") {
          await ctx!.resume().catch(() => {});
          const after = afterResume(ctx!.state as SfxContextState);
          if (after.action === "rebuild") {
            // An interrupted context that a resume did not revive is
            // dead: build a fresh one, or every later sound would be
            // silent too. This is what brought the block-drop and
            // line-clear sounds back after the game had gone quiet.
            ctx = build();
            await ctx.resume().catch(() => {});
          } else if (after.action === "create") {
            ctx = build();
            await ctx.resume().catch(() => {});
          }
        }
        // Step 3 only on a genuinely running context — anything else is
        // dropped this frame (the next key press will retry).
        if (!ctx || ctx.state !== "running") return null;
        return await emit(ctx);
      } catch {
        // A failed sound must never take the game down with it.
        return null;
      }
    },
    [],
  );

  // Window size tracking: feeds fitScale. Cleanup removes the listener —
  // under StrictMode's double-mount a leaked listener would double-fire
  // setSize and re-render the layout twice per resize.
  useEffect(() => {
    const onResize = () =>
      setSize({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  /**
   * Forwards one protocol action to the core via the Rust shell.
   * Fire-and-forget: the core's reply arrives as the next game-state
   * event, not as a return value, so a failed invoke just means the
   * input is lost (no toast, no retry — the next input supersedes it).
   */
  const send = useCallback((action: string) => {
    invoke("send_input", { action }).catch(() => {});
  }, []);

  /**
   * The Enter button's meaning, by where you are:
   *   title screen  -> open the options page (no core call yet)
   *   options page  -> start the game: new_game(level 0, chosen music,
   *                    chosen handicap) — this is the ONLY call that
   *                    creates a game
   *   game over     -> another new_game (restart)
   *   otherwise     -> toggle pause
   * All reads go through refs: this callback is memoized once and the
   * keyboard effect holds it forever.
   */
  const pressStart = useCallback(() => {
    if (error) return;
    const current = stateRef.current;
    if (!hasStartedRef.current) {
      if (!atOptionsRef.current) {
        // Title -> options page (owner request 2026-10-25).
        atOptionsRef.current = true;
        setAtOptions(true);
        return;
      }
      // Options -> game.
      hasStartedRef.current = true;
      setStarted(true);
      invoke("new_game", {
        level: 0,
        music: MUSIC_IDS[musicSelRef.current],
        handicap: HANDICAP_LEVELS[handicapSelRef.current],
      }).catch(() => {});
      return;
    }
    if (!current || current.status === "game_over") {
      // Restart path — same parameters as the first start, so the chosen
      // music and handicap survive across games.
      invoke("new_game", {
        level: 0,
        music: MUSIC_IDS[musicSelRef.current],
        handicap: HANDICAP_LEVELS[handicapSelRef.current],
      }).catch(() => {});
    } else {
      invoke("pause").catch(() => {});
    }
  }, [error]);

  /**
   * THE KEYBOARD ROUTER. One window-level keydown/keyup pair for the
   * whole app; the branches are tried in this order:
   *
   *   1. pre-game (title/options): menu navigation for the focused
   *      column, plus Konami tracking on every key
   *   2. in-game with cheats unlocked: the four cheat keys (digits,
   *      backquote, Home, End), each short-circuiting with a preventDefault
   *   3. otherwise: the KEY_MAP lookup -> send() to the core (or the
   *      special "start" action -> pressStart)
   *
   * Two subtleties:
   *   - preventDefault() on every mapped key stops the browser from also
   *     treating arrows/Enter as scroll/activation gestures.
   *   - e.repeat is dropped because browser auto-repeat would DOUBLE the
   *     core's own DAS auto-repeat (the core counts held frames itself).
   *
   * Deps [pressStart, send]: both are stable useCallbacks, so the effect
   * (and its listeners) attach exactly once for the app's lifetime.
   */
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // Branch 1: pre-game screens (owner request 2026-10-25). The cheat
      // sequence tracks on both; its arrow presses net out to no menu
      // movement on the options page (Up/Down net zero, Left/Right
      // toggle focus twice).
      // Guarded on stateRef.current so nothing reacts before the first
      // snapshot arrives (the "CONNECTING..." phase).
      if (!hasStartedRef.current && stateRef.current) {
        if (atOptionsRef.current) {
          // Menu movement, options page. All writes go state + ref so the
          // one-time listener sees the new values next key press.
          if (e.code === "ArrowLeft" || e.code === "ArrowRight") {
            // Left/Right only switch which column is focused; the
            // selection inside each column is untouched.
            const col = activeColRef.current === 0 ? 1 : 0;
            activeColRef.current = col;
            setActiveCol(col);
          } else if (e.code === "ArrowUp" || e.code === "ArrowDown") {
            const dir = e.code === "ArrowUp" ? -1 : 1;
            void playSfx(dir === 1 ? "select1" : "select2"); // select1 down, select2 up
            if (activeColRef.current === 0) {
              // Music menu move. The functional set + ref write keep the
              // mirror in sync inside the same event; the modulo is the
              // wrap-around (down from the last entry lands on the first).
              setMusicSel((s) => {
                const next = (s + dir + MUSIC_MENU.length) % MUSIC_MENU.length;
                musicSelRef.current = next;
                return next;
              });
              setMenuTouched(true); // preview the track
            } else {
              // Handicap menu move — same wrap-around recipe, no audio.
              setHandicapSel((s) => {
                const next = (s + dir + HANDICAP_LEVELS.length) % HANDICAP_LEVELS.length;
                handicapSelRef.current = next;
                return next;
              });
            }
          }
        }
        // Konami tracking, on EVERY pre-game key (even menu keys). See the
        // CHEAT_CODE note for the restart-at-1 trick. Unlock flips both
        // the ref (for the listener) and the state (to redraw the title's
        // green dome indicator).
        if (e.code === CHEAT_CODE[cheatPosRef.current]) {
          cheatPosRef.current += 1;
          if (cheatPosRef.current === CHEAT_CODE.length) {
            cheatPosRef.current = 0;
            cheatRef.current = true;
            setCheatUnlocked(true);
          }
        } else {
          cheatPosRef.current = e.code === CHEAT_CODE[0] ? 1 : 0;
        }
      } else if (cheatRef.current && stateRef.current?.status === "playing") {
        // Branch 2: in-game cheats. Each returns after handling, so a
        // cheat key never ALSO reaches the KEY_MAP below. Every one is a
        // toggle against the current core-reported value, and the core
        // confirms via the next game-state event.
        // Digits 0-9 (top row or numpad): jump straight to that level.
        // The regex captures the digit from either code family.
        const digit = /^(?:Digit|Numpad)([0-9])$/.exec(e.code);
        if (digit) {
          e.preventDefault();
          invoke("set_level", { level: Number(digit[1]) }).catch(() => {});
          return;
        }
        if (e.code === "Backquote") {
          // Cheat (owner request 2026-10-25): cycle the gameplay music.
          e.preventDefault();
          const current = stateRef.current?.music_track ?? MUSIC_CYCLE[0];
          const idx = MUSIC_CYCLE.indexOf(current);
          const next = MUSIC_CYCLE[(idx + 1) % MUSIC_CYCLE.length];
          invoke("set_music", { music: next }).catch(() => {});
          return;
        }
        if (e.code === "Home") {
          // Cheat (owner request 2026-10-28): autopilot #2 — maximize
          // score by deferring small clears for triples and tetrises.
          e.preventDefault();
          const next =
            stateRef.current?.autopilot === "highscore" ? null : "highscore";
          invoke("set_autopilot", { mode: next }).catch(() => {});
          return;
        }
        if (e.code === "End") {
          // Autopilot #1 — clear lines as quickly as possible.
          e.preventDefault();
          const next = stateRef.current?.autopilot === "quick" ? null : "quick";
          invoke("set_autopilot", { mode: next }).catch(() => {});
          return;
        }
      }
      // Branch 3: the normal in-game controls. Anything not in KEY_MAP
      // (typing keys, F-keys, ...) falls through untouched.
      const binding = KEY_MAP[e.code];
      if (!binding) return;
      e.preventDefault();
      if (e.repeat) return; // auto-repeat comes from Python DAS (spec 2.4)
      if (binding.down === "start") {
        pressStart();
        return;
      }
      send(binding.down);
    };
    // keyup has no menu/cheat branches: only the DAS-style release
    // half-pairs (left_off, soft_drop_off, ...) matter.
    const onKeyUp = (e: KeyboardEvent) => {
      const binding = KEY_MAP[e.code];
      if (!binding?.up) return;
      e.preventDefault();
      send(binding.up);
    };
    // Focus loss may swallow the matching keyup (alt-tab, a file dialog,
    // the window manager taking focus). Release every held-key latch so
    // the core cannot keep auto-shifting or soft-dropping on return.
    const releaseHeld = () => {
      send("left_off");
      send("right_off");
      send("soft_drop_off");
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden") releaseHeld();
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", releaseHeld);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", releaseHeld);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [pressStart, send]);

  // Music manager (owner request 2026-10-25): the theme music plays on
  // its own <audio> element, the one-shot cues (06 end of stage, 09
  // victory, 08 game over) on a second one.
  //
  // Audio bug fix (owner request 2026-10-29): the music used to be cut
  // off by a second of silence, sometimes several times a minute. The
  // cause was that ONE element was reused for everything: assigning a
  // new `src` makes the browser load and decode the whole file again
  // (up to 2.9 MB) before a single sample comes out. The level-clear
  // path swapped the src to the celebration track and back again --
  // twice per level -- and the playlist advance swapped it once per
  // track.
  //
  // The fix:
  // - The theme element keeps its src and its currentTime across a
  //   celebration: it is only paused, so returning to it is instant.
  // - The celebration plays on its own element, over the paused theme.
  // - The playlist advance preloads the next track in a second element
  //   and swaps them on `ended`, so the handover is gapless.
  //
  // The bookkeeping that decides all of this lives in audioPlan.ts (a
  // pure state machine, so it can be tested without a browser); this
  // effect only carries the actions out on the elements.
  // Derived inputs for the music effect. Defaults chosen for the
  // pre-start screens: "gameplay" phase is irrelevant before start, and
  // a null track keeps the plan pointing at silence.
  const musicPhase = state?.music_phase ?? "gameplay";
  const track = state?.music_track ?? null;
  // Paused only counts once a game exists — pausing the TITLE would
  // freeze the intro theme.
  const paused = started && state?.status === "paused";

  // THE MUSIC EFFECT: re-runs whenever any music-relevant input changes
  // (screens, menu selection, core phase/track, pause). Each run asks the
  // pure machine for a plan + the minimal action list, then interprets
  // the actions against the real elements. All element manipulation —
  // the only imperative audio code — happens in this one switch.
  useEffect(() => {
    const el = activeEl();
    const spare = spareEl();
    const cue = cueRef.current;
    if (!el || !spare || !cue) return;
    // Half 1: the intent.
    const plan = planMusic({
      started,
      atOptions,
      menuTouched,
      menuMusicId: MUSIC_IDS[musicSel] ?? null,
      phase: musicPhase,
      track,
      introSrc: introUrl,
      trackUrls: GAMEPLAY_TRACKS,
      endOfStageSrc: endOfStageUrl,
      victorySrc: victoryUrl,
      gameOverSrc: gameOverMusicUrl,
    });
    // Half 2: reconcile with what is loaded, get the minimal actions.
    const { state, actions } = stepAudio(audioStateRef.current, plan, {
      started,
      paused,
      cycle: MUSIC_CYCLE,
      themeUrls: THEME_URLS,
    });
    audioStateRef.current = state;
    // Interpret the actions. Every play() promise records whether the
    // gesture gate blocked it (needsGestureRef), so the kick handler
    // below can retry on the next user input.
    for (const action of actions) {
      switch (action.type) {
        case "theme-load":
          // The one deliberately expensive path: a fresh source into the
          // ACTIVE element. Only an intent change gets here.
          el.pause();
          el.src = action.src;
          el.loop = action.loop;
          el.play()
            .then(() => {
              needsGestureRef.current = false;
            })
            .catch(() => {
              // WKWebView blocks autoplay until the first user gesture.
              needsGestureRef.current = true;
            });
          break;
        case "theme-unload":
          // Silence: both theme elements are drained so a stale track
          // cannot resurface on the next load.
          el.pause();
          el.removeAttribute("src");
          spare.pause();
          spare.removeAttribute("src");
          break;
        case "theme-play":
          // The cheap resume: src untouched, position preserved.
          if (el.paused && el.src) {
            el.play()
              .then(() => {
                needsGestureRef.current = false;
              })
              .catch(() => {
                needsGestureRef.current = true;
              });
          }
          break;
        case "theme-pause":
          el.pause();
          break;
        case "cue-play":
          // One-shot celebration over the paused theme. loop=false on
          // every load — a looping cue was exactly the old bug.
          cue.src = action.src;
          cue.loop = false;
          cue.play().catch(() => {});
          break;
        case "cue-clear":
          // Celebration over: drop the cue so it cannot restart.
          cue.pause();
          cue.removeAttribute("src");
          break;
        case "cue-pause":
          cue.pause();
          break;
        case "cue-resume":
          if (cue.paused && cue.src) cue.play().catch(() => {});
          break;
        case "preload":
          // The next playlist track is fetched and decoded in the spare
          // element, so the handover is gapless.
          spare.src = action.src;
          spare.loop = false;
          spare.load();
          break;
      }
    }
    // Mirror for the gesture handler below (it has no React deps).
    gamePausedRef.current = paused;
    // NOTE: activeEl()/spareEl() are read fresh inside because the ACTIVE
    // SLOT may have been swapped by onMusicEnded since the effect was
    // scheduled — the elements must be resolved at execution time, not
    // captured in the dep list.
  }, [started, atOptions, menuTouched, musicSel, musicPhase, track, paused]);

  // THE GESTURE KICK. WebAudio + WKWebView autoplay policy: after a play()
  // was refused (needsGestureRef set) or a context went idle, the NEXT
  // user gesture (any key, any click) is the browser's cue to let audio
  // run. Both listeners live for the app's lifetime and do nothing when
  // there is nothing to revive. keydown deliberately does NOT
  // preventDefault here — that happens (or not) in the router effect;
  // multiple keydown listeners on window are independent.
  useEffect(() => {
    const kick = () => {
      // Revive a refused theme, unless the game is paused (kicking it
      // alive mid-pause would ignore the pause).
      const el = activeEl();
      if (el && needsGestureRef.current && el.src && !gamePausedRef.current) {
        el.play()
          .then(() => {
            needsGestureRef.current = false;
          })
          .catch(() => {});
      }
      // A gesture is also what the browser wants before it lets an
      // interrupted sound-effects context run again.
      const ctx = popCtxRef.current;
      if (ctx && ctx.state !== "running" && ctx.state !== "closed") {
        ctx.resume().catch(() => {});
      }
    };
    window.addEventListener("keydown", kick);
    window.addEventListener("pointerdown", kick);
    return () => {
      window.removeEventListener("keydown", kick);
      window.removeEventListener("pointerdown", kick);
    };
  }, []);

  // Playlist advance (owner request 2026-10-25): after the selected
  // theme, loop through all the others.
  //
  // Audio bug fix (owner request 2026-10-29): the advance used to
  // assign `src` to the element that was playing, which forced a
  // reload of the whole file and a second of silence. Now the next
  // track is preloaded in the spare element and the two swap, so the
  // handover is seamless.
  const onMusicEnded = (e: React.SyntheticEvent<HTMLAudioElement>) => {
    // Bound to BOTH theme elements' "ended" event. Two filters first:
    //   - only the ACTIVE element's end advances the playlist (the spare
    //     element finishing its preload must do nothing);
    //   - the machine can veto (no playlist / no preload -> no actions).
    const el = e.currentTarget;
    const active = activeEl();
    if (!active || el !== active) return;
    const { state, actions } = advancePlaylist(audioStateRef.current, {
      cycle: MUSIC_CYCLE,
      themeUrls: THEME_URLS,
    });
    audioStateRef.current = state;
    for (const action of actions) {
      if (action.type !== "swap") continue;
      // The handover, in the order that makes it gapless:
      //   1. flip the slot -> the PRELOADED spare becomes active;
      //   2. start it immediately (it is already decoded);
      //   3. only then reload the old element with the track AFTER the
      //      one now playing, making it the next spare.
      // Steps 2 and 3 are independent: the play does not wait for the
      // load, which is the whole point of having two elements.
      activeSlotRef.current = activeSlotRef.current === "a" ? "b" : "a";
      const now = activeEl();
      if (now) now.play().catch(() => {});
      el.src = action.after;
      el.loop = false;
      el.load();
    }
  };

  // SOUND TRIGGERS FROM STATE TRANSITIONS. The core sends no "event:"
  // messages for locks/clears; instead the state carries monotonic
  // COUNTERS (lock_count, clear_count). This effect diffs them between
  // snapshots: a rising clear_count means a clear just happened, a rising
  // lock_count (without a clear) means a plain lock. Counters survive
  // coalesced/dropped snapshots, which one-shot events would not.
  const lockCount = state?.lock_count ?? 0;
  const clearCount = state?.clear_count ?? 0;
  const lastLockRef = useRef(lockCount);
  const lastClearRef = useRef(clearCount);
  useEffect(() => {
    const cleared = clearCount > lastClearRef.current;
    const locked = lockCount > lastLockRef.current;
    lastLockRef.current = lockCount;
    lastClearRef.current = clearCount;
    // A lock that clears lines plays only the line-clear sound, not the
    // drop sound on top of it (owner request 2026-10-25).
    if (cleared) void playSfx("clear");
    else if (locked) void playSfx("drop");
  }, [lockCount, clearCount, playSfx]);

  // Fireworks after a top-5 game over (owner request 2026-10-25): the
  // four rockets play in a loop until Enter restarts the game.
  const fireworksActive = state?.status === "game_over" && state?.top_run;
  // The loop is an async self-scheduling task: play rocket idx, AWAIT its
  // natural end (`src.onended` resolves the promise), move to the next.
  // Two escape hatches:
  //   - `cancelled` is checked after every await; the cleanup sets it, so
  //     restarting the game (active flips false) stops the loop promptly;
  //   - playSfx returning null (context unavailable) falls back to a 400ms
  //     delay so a dead context degrades to a slow click loop, not a
  //     busy-loop of failing play attempts.
  // current?.stop() in the cleanup cuts the rocket that is mid-flight
  // (stop() on an already-ended node throws — hence the try/catch).
  useEffect(() => {
    if (!fireworksActive) return;
    let cancelled = false;
    let current: AudioBufferSourceNode | null = null;
    const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));
    (async () => {
      let idx = 0;
      while (!cancelled) {
        const src = await playSfx(FIREWORK_SEQUENCE[idx % FIREWORK_SEQUENCE.length]);
        if (cancelled) return;
        if (!src) {
          await delay(400);
          idx += 1;
          continue;
        }
        current = src;
        await new Promise<void>((resolve) => {
          src.onended = () => resolve();
        });
        idx += 1;
        current = null;
      }
    })();
    return () => {
      cancelled = true;
      try {
        current?.stop();
      } catch {
        // already ended
      }
    };
  }, [fireworksActive, playSfx]);

  // Derived layout: the scale for this exact window size, and the on-screen
  // box of the logical rectangle. Math.round because CSS px are integral
  // (fractional sizes would blur the letterbox edge).
  const scale = fitScale(size.width, size.height, integerScale);
  const areaWidth = Math.round(LOGICAL_WIDTH * scale);
  const areaHeight = Math.round(LOGICAL_HEIGHT * scale);

  // Which overlay to show. Priority: a real error page wins over
  // everything; then the pre-game screens; then the core's status. The
  // hasStartedRef (not `started`) keeps the title up through the render
  // where the state flips, avoiding a one-frame flash of "playing".
  let phase: OverlayPhase = "connecting";
  if (state) {
    phase = hasStartedRef.current ? (state.status as OverlayPhase) : atOptions ? "options" : "start";
  }
  if (error) {
    return (
      <div
        style={{
          fontFamily: FONT_SMOOTH,
          color: TEXT_BRIGHT,
          textAlign: "center",
          lineHeight: 2,
        }}
      >
        <p>Cannot reach the Python core.</p>
        <p style={{ fontSize: 24, color: PANEL_BG, maxWidth: 960 }}>{error}</p>
        <button onClick={retry} style={{ padding: "20px 48px", fontSize: 32 }}>
          Retry
        </button>
      </div>
    );
  }

  // The letterboxed game area: exactly the scaled logical rectangle,
  // centered by styles.css. Every child positions absolutely inside it,
  // so the whole UI scales as one unit.
  return (
    <div
      className="game-area"
      style={{ width: areaWidth, height: areaHeight, background: BACKGROUND }}
    >
      <Board state={state} scale={scale} />
      {/* Autopilot indicator (owner request 2026-10-27/28): a label bar
          above the playfield showing the active strategy. */}
      {state?.autopilot && state?.status !== "game_over" && (
        <div
          style={{
            position: "absolute",
            // Anchored to the playfield's top-left minus a 56-logical-px
            // band, i.e. just above the frame — the same trick the NEXT
            // label uses below.
            left: LAYOUT.playfield.x * scale,
            top: (LAYOUT.playfield.y - 56) * scale,
            fontFamily: FONT_SMOOTH,
            fontWeight: 700,
            color: TEXT_BRIGHT,
            background: PANEL_BG,
            padding: `0 ${12 * scale}px`,
            fontSize: 36 * scale,
            lineHeight: `${36 * 1.6 * scale}px`,
          }}
        >
          {state.autopilot === "highscore" ? "AUTO - HIGH SCORE" : "AUTO - QUICK CLEAR LINES"}
        </div>
      )}
      {/* Theme music: two elements, so the playlist can hand over to a
          preloaded track without a gap, and the one-shot cues (06 end of
          stage, 09 victory, 08 game over) on a third, over the paused
          theme. */}
      <audio ref={audioARef} onEnded={onMusicEnded} preload="auto" />
      <audio ref={audioBRef} onEnded={onMusicEnded} preload="auto" />
      <audio ref={cueRef} preload="auto" />
      {/* "NEXT" label above the preview box, as in the captures (spec 6.1).
          The -labelSize*1.8 lift is its band height (fontSize * 1.6 line
          box, rounded up with margin) so the label hangs just above the
          box like the AUTO bar hangs above the playfield. */}
      <div
        style={{
          position: "absolute",
          left: LAYOUT.next.x * scale,
          top: (LAYOUT.next.y - LAYOUT.next.labelSize * 1.8) * scale,
          fontFamily: FONT_SMOOTH,
          fontWeight: 700,
          color: TEXT_BRIGHT,
          background: PANEL_BG,
          padding: `0 ${12 * scale}px`,
          fontSize: LAYOUT.next.labelSize * scale,
          lineHeight: `${LAYOUT.next.labelSize * 1.6 * scale}px`,
        }}
      >
        NEXT
      </div>
      <NextPreview state={state} scale={scale} />
      <ScorePanel state={state} scale={scale} />
      <StatsPanel state={state} scale={scale} />
      <Overlay
        phase={phase}
        score={state?.score ?? 0}
        notice={notice}
        scale={scale}
        cheat={cheatUnlocked}
        musicSel={musicSel}
        handicap={HANDICAP_LEVELS[handicapSel]}
        activeCol={activeCol}
        topScores={state?.top_scores}
        topRun={state?.top_run}
      />
      {/* Integer-scale toggle (spec 6.4, optional, default off). Kept as a
          live checkbox rather than an options entry: it affects only the
          rendering of THIS window, so it is not part of a new_game call. */}
      <label
        style={{
          position: "absolute",
          right: 16 * scale,
          bottom: 8 * scale,
          fontFamily: FONT_SMOOTH,
          color: PANEL_BG,
          fontSize: 24 * scale,
          display: "flex",
          gap: 12,
          alignItems: "center",
        }}
      >
        <input
          type="checkbox"
          checked={integerScale}
          onChange={(e) => setIntegerScale(e.target.checked)}
        />
        INT SCALE
      </label>
    </div>
  );
}
