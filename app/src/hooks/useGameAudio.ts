import { useCallback, useEffect, useRef } from "react";
import type { SyntheticEvent } from "react";
import {
  advancePlaylist,
  initialAudioState,
  planMusic,
  stepAudio,
  type AudioState,
} from "../audioPlan";
import {
  afterResume,
  planSfx,
  type SfxContextState,
} from "../sfxPlan";
import type { GameState } from "../types/game";

// Music (owner request 2026-10-25). The title screen previews the four
// gameplay themes (02-05); the choice is sent with new_game. The core
// reports the music phase, which picks the one-shot cue:
//   "level_complete" -> 06 (end of stage), played ONCE; the next level
//                       then starts by itself (owner change 2026-10-29).
//   "milestone"      -> 09 (victory), on cleared levels 9/19/29...
//   "game_over"      -> 08, once.
// The cue plays over the paused theme; the theme keeps its source and
// position, so a celebration never costs a reload.
import introUrl from "../assets/audio/01_-_Tetris_Tengen_-_NES_-_Introduction.ogg?url";
import loginskaUrl from "../assets/audio/02_-_Tetris_Tengen_-_NES_-_Loginska.ogg?url";
import bradinskyUrl from "../assets/audio/03_-_Tetris_Tengen_-_NES_-_Bradinsky.ogg?url";
import kalinkaUrl from "../assets/audio/04_-_Tetris_Tengen_-_NES_-_Kalinka.ogg?url";
import troikaUrl from "../assets/audio/05_-_Tetris_Tengen_-_NES_-_Troika.ogg?url";
import endOfStageUrl from "../assets/audio/06_-_Tetris_Tengen_-_NES_-_End_of_Stage.ogg?url";
import gameOverMusicUrl from "../assets/audio/08_-_Tetris_Tengen_-_NES_-_Game_Over.ogg?url";
import victoryUrl from "../assets/audio/09_-_Tetris_Tengen_-_NES_-_Victory.ogg?url";
// Sound effects (owner request 2026-10-25): the exact original drop,
// line-clear, and menu-select sounds, plus the game-over firework
// rockets, from the owner's files in assets/audio/.
import blockDropUrl from "../assets/audio/tetris_block_drop.mp3?url";
import lineClearUrl from "../assets/audio/tetris_line_clear.mp3?url";
import select1Url from "../assets/audio/tetris_select1.mp3?url";
import select2Url from "../assets/audio/tetris_select2.mp3?url";
import firework1Url from "../assets/audio/tetris_firework1.mp3?url";
import firework2Url from "../assets/audio/tetris_firework2.mp3?url";
import firework3Url from "../assets/audio/tetris_firework3.mp3?url";
import firework4Url from "../assets/audio/tetris_firework4.mp3?url";

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
// state.music_track. The ids match the original game's numbering (02..05).
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

// The options-page menu values. Index i of MUSIC_IDS pairs with the
// display list in App: "Silent" -> null (no music), "Loginska" -> "02",
// and so on.
export const MUSIC_IDS: (string | null)[] = [null, "02", "03", "04", "05"];
// The gameplay playlist order, also used by the Backquote cheat.
export const MUSIC_CYCLE = ["02", "03", "04", "05"];

export interface GameAudioOptions {
  state: GameState | null;
  started: boolean;
  atOptions: boolean;
  musicSel: number;
  menuTouched: boolean;
}

/**
 * Owns every audio resource: the two theme elements, the one-shot cue,
 * the WebAudio sound-effects context, and the gesture unlock. The pure
 * decisions live in audioPlan.ts / sfxPlan.ts; this hook only carries
 * them out and owns their cleanup.
 */
export function useGameAudio({
  state,
  started,
  atOptions,
  musicSel,
  menuTouched,
}: GameAudioOptions) {
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
  // "The browser refused autoplay; replay on the next gesture."
  const needsGestureRef = useRef(false);
  // Mirror of `paused` for the gesture handler (attached once).
  const gamePausedRef = useRef(false);

  const activeEl = () =>
    activeSlotRef.current === "a" ? audioARef.current : audioBRef.current;
  const spareEl = () =>
    activeSlotRef.current === "a" ? audioBRef.current : audioARef.current;

  // Sound effects (owner decisions 2026-10-25). The context policy is
  // pure (sfxPlan.ts); this is the browser-side execution and recovery.
  const popCtxRef = useRef<AudioContext | null>(null);
  const sfxBuffersRef = useRef<Record<string, AudioBuffer>>({});

  const playSfx = useCallback(
    async (name: string): Promise<AudioBufferSourceNode | null> => {
      // buffer -> source -> gain -> destination.
      const emit = async (
        ctx: AudioContext,
      ): Promise<AudioBufferSourceNode | null> => {
        // Decode cache: AudioBuffers are tied to their context's sample
        // rate, so they are cached per context and wiped on rebuild.
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
        // Release the nodes when the sound ends: leaving them attached
        // to the destination leaks a gain node per sound.
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

      const build = (): AudioContext => {
        const fresh = new AudioContext();
        popCtxRef.current = fresh;
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

  // Derived inputs for the music effect.
  const musicPhase = state?.music_phase ?? "gameplay";
  const track = state?.music_track ?? null;
  // Paused only counts once a game exists — pausing the TITLE would
  // freeze the intro theme.
  const paused = started && state?.status === "paused";

  // THE MUSIC EFFECT: ask the pure machine for a plan + the minimal
  // action list, then interpret the actions against the real elements.
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
    const { state: audioState, actions } = stepAudio(
      audioStateRef.current,
      plan,
      {
        started,
        paused,
        cycle: MUSIC_CYCLE,
        themeUrls: THEME_URLS,
      },
    );
    audioStateRef.current = audioState;
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
    // scheduled.
  }, [started, atOptions, menuTouched, musicSel, musicPhase, track, paused]);

  // THE GESTURE KICK. A single gesture can resume audio and still perform
  // its normal game action; this listener deliberately does not
  // preventDefault. It lives as long as playback does.
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

  // Playlist advance: after the selected theme, loop through all the
  // others. The next track is preloaded in the spare element and the two
  // swap on `ended`.
  const onMusicEnded = (e: SyntheticEvent<HTMLAudioElement>) => {
    const el = e.currentTarget;
    const active = activeEl();
    if (!active || el !== active) return;
    const { state: audioState, actions } = advancePlaylist(
      audioStateRef.current,
      {
        cycle: MUSIC_CYCLE,
        themeUrls: THEME_URLS,
      },
    );
    audioStateRef.current = audioState;
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

  // SOUND TRIGGERS FROM STATE TRANSITIONS. The core sends monotonic
  // counters; a rising clear_count means a clear, a rising lock_count
  // (without a clear) means a plain lock.
  const lockCount = state?.lock_count ?? 0;
  const clearCount = state?.clear_count ?? 0;
  const lastLockRef = useRef(lockCount);
  const lastClearRef = useRef(clearCount);
  useEffect(() => {
    const cleared = clearCount > lastClearRef.current;
    const locked = lockCount > lastLockRef.current;
    lastLockRef.current = lockCount;
    lastClearRef.current = clearCount;
    if (cleared) void playSfx("clear");
    else if (locked) void playSfx("drop");
  }, [lockCount, clearCount, playSfx]);

  // Fireworks after a top-5 game over: the four rockets play in a loop
  // until Enter restarts the game.
  const fireworksActive = state?.status === "game_over" && state?.top_run;
  useEffect(() => {
    if (!fireworksActive) return;
    let cancelled = false;
    let current: AudioBufferSourceNode | null = null;
    const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));
    (async () => {
      let idx = 0;
      while (!cancelled) {
        const src = await playSfx(
          FIREWORK_SEQUENCE[idx % FIREWORK_SEQUENCE.length],
        );
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

  // One owner for the WebAudio context: close it when the hook unmounts.
  // Audio element src is intentionally left alone; React owns those
  // elements and StrictMode's effect replay must not blank a playing
  // theme.
  useEffect(() => {
    return () => {
      const ctx = popCtxRef.current;
      if (ctx && ctx.state !== "closed") {
        void ctx.close().catch(() => {});
      }
    };
  }, []);

  return { audioARef, audioBRef, cueRef, onMusicEnded, playSfx };
}