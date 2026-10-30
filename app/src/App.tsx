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
import { Board } from "./components/Board";
import { NextPreview } from "./components/NextPreview";
import { ScorePanel } from "./components/ScorePanel";
import { StatsPanel } from "./components/StatsPanel";
import { Overlay } from "./components/Overlay";

// Music (owner request 2026-10-25). The title screen previews the four
// gameplay themes (02-05); the choice is sent with new_game. The core
// reports the music phase: 06 (end of stage) chains into 07 (Katyusha,
// the celebration), 09 (victory) marks cleared levels 9/19/29..., and 08
// plays on game over.
import introUrl from "../../music/01_-_Tetris_Tengen_-_NES_-_Introduction.ogg?url";
import loginskaUrl from "../../music/02_-_Tetris_Tengen_-_NES_-_Loginska.ogg?url";
import bradinskyUrl from "../../music/03_-_Tetris_Tengen_-_NES_-_Bradinsky.ogg?url";
import kalinkaUrl from "../../music/04_-_Tetris_Tengen_-_NES_-_Kalinka.ogg?url";
import troikaUrl from "../../music/05_-_Tetris_Tengen_-_NES_-_Troika.ogg?url";
import endOfStageUrl from "../../music/06_-_Tetris_Tengen_-_NES_-_End_of_Stage.ogg?url";
import gameOverMusicUrl from "../../music/08_-_Tetris_Tengen_-_NES_-_Game_Over.ogg?url";
import victoryUrl from "../../music/09_-_Tetris_Tengen_-_NES_-_Victory.ogg?url";
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
const MUSIC_MENU = ["Silent", "Loginska", "Bradinsky", "Kalinka", "Troika"];
const MUSIC_IDS: (string | null)[] = [null, "02", "03", "04", "05"];
// Handicap rows (owner request 2026-10-25): unfinished garbage rows.
const HANDICAP_LEVELS = [0, 3, 6, 9, 12];

// Scales the logical space to fit the window with uniform scaling and
// letterboxing; optional integer-scale mode snaps to whole numbers
// (spec 6.4). The UI is laid out in logical units only.
function fitScale(width: number, height: number, integerScale: boolean): number {
  const raw = Math.min(width / LOGICAL_WIDTH, height / LOGICAL_HEIGHT);
  if (integerScale) return Math.max(1, Math.floor(raw));
  return raw;
}

// Konami cheat (owner request 2026-10-25): typing this key sequence on
// the title screen unlocks cheat mode; digits 0-9 then jump the level
// during play.
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

export default function App() {
  const { state, notice, error, retry } = useGameState();
  const [size, setSize] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  });
  const [integerScale, setIntegerScale] = useState(false); // default off (spec 6.4)
  const hasStartedRef = useRef(false);
  const [started, setStarted] = useState(false);
  const stateRef = useRef(state);
  stateRef.current = state;
  const [cheatUnlocked, setCheatUnlocked] = useState(false);
  const cheatRef = useRef(false);
  const cheatPosRef = useRef(0);
  // Title -> options -> game flow (owner request 2026-10-25): the title
  // shows only the cathedral; Enter opens the options page.
  const [atOptions, setAtOptions] = useState(false);
  const atOptionsRef = useRef(false);
  // Title music menu (owner request 2026-10-25).
  const [musicSel, setMusicSel] = useState(0);
  const musicSelRef = useRef(0);
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
  const needsGestureRef = useRef(false);
  const gamePausedRef = useRef(false);

  // The theme element that is playing, and the one holding the next
  // track. The two swap roles when a track ends.
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

  const playSfx = useCallback(
    async (name: string): Promise<AudioBufferSourceNode | null> => {
      const emit = async (ctx: AudioContext): Promise<AudioBufferSourceNode | null> => {
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
      const build = (): AudioContext => {
        const fresh = new AudioContext();
        popCtxRef.current = fresh;
        // The decoded buffers belong to the old context's sample rate.
        sfxBuffersRef.current = {};
        fresh.onstatechange = () => {
          if (fresh.state !== "running" && fresh.state !== "closed") {
            fresh.resume().catch(() => {});
          }
        };
        return fresh;
      };
      try {
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
        if (!ctx || ctx.state !== "running") return null;
        return await emit(ctx);
      } catch {
        // A failed sound must never take the game down with it.
        return null;
      }
    },
    [],
  );

  useEffect(() => {
    const onResize = () =>
      setSize({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const send = useCallback((action: string) => {
    invoke("send_input", { action }).catch(() => {});
  }, []);

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
      invoke("new_game", {
        level: 0,
        music: MUSIC_IDS[musicSelRef.current],
        handicap: HANDICAP_LEVELS[handicapSelRef.current],
      }).catch(() => {});
    } else {
      invoke("pause").catch(() => {});
    }
  }, [error]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // Pre-game screens (owner request 2026-10-25). The cheat sequence
      // tracks on both; its arrow presses net out to no menu movement on
      // the options page (Up/Down net zero, Left/Right toggle focus
      // twice).
      if (!hasStartedRef.current && stateRef.current) {
        if (atOptionsRef.current) {
          if (e.code === "ArrowLeft" || e.code === "ArrowRight") {
            const col = activeColRef.current === 0 ? 1 : 0;
            activeColRef.current = col;
            setActiveCol(col);
          } else if (e.code === "ArrowUp" || e.code === "ArrowDown") {
            const dir = e.code === "ArrowUp" ? -1 : 1;
            void playSfx(dir === 1 ? "select1" : "select2"); // select1 down, select2 up
            if (activeColRef.current === 0) {
              setMusicSel((s) => {
                const next = (s + dir + MUSIC_MENU.length) % MUSIC_MENU.length;
                musicSelRef.current = next;
                return next;
              });
              setMenuTouched(true); // preview the track
            } else {
              setHandicapSel((s) => {
                const next = (s + dir + HANDICAP_LEVELS.length) % HANDICAP_LEVELS.length;
                handicapSelRef.current = next;
                return next;
              });
            }
          }
        }
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
    const onKeyUp = (e: KeyboardEvent) => {
      const binding = KEY_MAP[e.code];
      if (!binding?.up) return;
      e.preventDefault();
      send(binding.up);
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
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
  const musicPhase = state?.music_phase ?? "gameplay";
  const track = state?.music_track ?? null;
  const paused = started && state?.status === "paused";

  useEffect(() => {
    const el = activeEl();
    const spare = spareEl();
    const cue = cueRef.current;
    if (!el || !spare || !cue) return;
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
    const { state, actions } = stepAudio(audioStateRef.current, plan, {
      started,
      paused,
      cycle: MUSIC_CYCLE,
      themeUrls: THEME_URLS,
    });
    audioStateRef.current = state;
    for (const action of actions) {
      switch (action.type) {
        case "theme-load":
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
          el.pause();
          el.removeAttribute("src");
          spare.pause();
          spare.removeAttribute("src");
          break;
        case "theme-play":
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
          cue.src = action.src;
          cue.loop = false;
          cue.play().catch(() => {});
          break;
        case "cue-clear":
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
    gamePausedRef.current = paused;
  }, [started, atOptions, menuTouched, musicSel, musicPhase, track, paused]);

  useEffect(() => {
    const kick = () => {
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
      activeSlotRef.current = activeSlotRef.current === "a" ? "b" : "a";
      const now = activeEl();
      if (now) now.play().catch(() => {});
      el.src = action.after;
      el.loop = false;
      el.load();
    }
  };

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

  const scale = fitScale(size.width, size.height, integerScale);
  const areaWidth = Math.round(LOGICAL_WIDTH * scale);
  const areaHeight = Math.round(LOGICAL_HEIGHT * scale);

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
      {/* "NEXT" label above the preview box, as in the captures (spec 6.1). */}
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
      {/* Integer-scale toggle (spec 6.4, optional, default off). */}
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
