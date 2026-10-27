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
import katyushaUrl from "../../music/07_-_Tetris_Tengen_-_NES_-_Katyusha.ogg?url";
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
  // Single audio element managed imperatively (see the effect below).
  const audioRef = useRef<HTMLAudioElement>(null);
  const wantedSrcRef = useRef<string | null>(null);
  const chainRef = useRef<{ src: string; loop: boolean } | null>(null);
  const needsGestureRef = useRef(false);
  const gamePausedRef = useRef(false);

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
            playSfx(dir === 1 ? "select1" : "select2"); // select1 down, select2 up
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

  // Music manager (owner request 2026-10-25): one audio element for the
  // whole app. Title: the introduction theme until the menu is touched,
  // then the previewed track (nothing for Silent). Game: the selected
  // theme loops; on end-of-stage 06 plays once and chains into 07
  // (Katyusha) until Enter; 09 (victory) for cleared levels 9/19/29...;
  // 08 on game over.
  const musicPhase = state?.music_phase ?? "gameplay";
  const track = state?.music_track ?? null;
  const paused = started && state?.status === "paused";
  let wantSrc: string | null;
  let wantLoop = true;
  let wantChain: { src: string; loop: boolean } | null = null;
  if (!started) {
    // Title: the introduction theme loops. On the options page there is
    // no background music (owner request 2026-10-25): tracks play only
    // as menu previews, and Silent means silence.
    wantSrc = atOptions
      ? menuTouched
        ? GAMEPLAY_TRACKS[MUSIC_IDS[musicSel] ?? ""] ?? null
        : null
      : introUrl;
  } else if (musicPhase === "level_complete") {
    wantSrc = endOfStageUrl;
    wantLoop = false;
    wantChain = { src: katyushaUrl, loop: true };
  } else if (musicPhase === "milestone") {
    wantSrc = victoryUrl;
  } else if (musicPhase === "game_over") {
    wantSrc = gameOverMusicUrl;
    wantLoop = false;
  } else {
    // Gameplay playlist (owner request 2026-10-25): start from the
    // selected theme, then loop through all of them; Silent stays
    // silent. Advance happens on each track's `ended` event.
    wantSrc = track ? GAMEPLAY_TRACKS[track] ?? null : null;
    wantLoop = false;
  }

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    chainRef.current = wantChain;
    // Playlist advances only during gameplay with a selected theme
    // (owner request 2026-10-25); celebrations and game over don't.
    playlistActiveRef.current =
      started && musicPhase === "gameplay" && wantSrc !== null;
    // The music pauses with the game and resumes in place (owner request
    // 2026-10-25).
    if (paused) {
      if (!gamePausedRef.current && el.src && !el.paused) {
        el.pause();
        gamePausedRef.current = true;
      }
      prevPhaseRef.current = musicPhase;
      return;
    }
    if (gamePausedRef.current) {
      gamePausedRef.current = false;
      if (el.src) el.play().catch(() => {});
    }
    const returning =
      prevPhaseRef.current === "level_complete" ||
      prevPhaseRef.current === "milestone";
    if (returning && wantSrc !== null && playlistSavedRef.current) {
      // Back from the celebration: continue the theme that was playing
      // right before the level ended, at its position (owner request
      // 2026-10-27), instead of restarting the selection.
      const saved = playlistSavedRef.current;
      playlistSavedRef.current = null;
      const url = GAMEPLAY_TRACKS[saved.id];
      if (url) {
        playlistPosRef.current = saved.id;
        wantedSrcRef.current = url;
        el.src = url;
        el.loop = wantLoop;
        const onLoaded = () => {
          el.currentTime = Math.max(0, Math.min(saved.time, el.duration || saved.time));
          el.removeEventListener("loadedmetadata", onLoaded);
        };
        el.addEventListener("loadedmetadata", onLoaded);
        el.play()
          .then(() => {
            needsGestureRef.current = false;
          })
          .catch(() => {
            needsGestureRef.current = true;
          });
        prevPhaseRef.current = musicPhase;
        return;
      }
    }
    if (wantSrc !== wantedSrcRef.current) {
      // Leaving gameplay: save the playlist position so the next level
      // continues where the music left off (owner request 2026-10-27).
      if (started && prevPhaseRef.current === "gameplay" && playlistPosRef.current) {
        playlistSavedRef.current = { id: playlistPosRef.current, time: el.currentTime };
      }
      wantedSrcRef.current = wantSrc;
      if (wantSrc === null) {
        el.pause();
        el.removeAttribute("src");
        prevPhaseRef.current = musicPhase;
        return;
      }
      el.src = wantSrc;
      el.loop = wantLoop;
      if (started && musicPhase === "gameplay") {
        playlistPosRef.current = track;
        playlistSavedRef.current = null;
      }
      el.play()
        .then(() => {
          needsGestureRef.current = false;
        })
        .catch(() => {
          // WKWebView blocks autoplay until the first user gesture.
          needsGestureRef.current = true;
        });
    } else if (el.loop !== wantLoop) {
      el.loop = wantLoop;
    }
    prevPhaseRef.current = musicPhase;
  }, [wantSrc, wantLoop, wantChain, paused, started, musicPhase, track]);

  useEffect(() => {
    const kick = () => {
      const el = audioRef.current;
      if (el && needsGestureRef.current && el.src && !gamePausedRef.current) {
        el.play()
          .then(() => {
            needsGestureRef.current = false;
          })
          .catch(() => {});
      }
    };
    window.addEventListener("keydown", kick);
    window.addEventListener("pointerdown", kick);
    return () => {
      window.removeEventListener("keydown", kick);
      window.removeEventListener("pointerdown", kick);
    };
  }, []);

  // Gameplay playlist (owner request 2026-10-25): which track is playing
  // and whether the playlist should keep advancing. SavedPos keeps the
  // track + position so the music continues where it left off after an
  // end-of-stage celebration (owner request 2026-10-27).
  const playlistPosRef = useRef<string | null>(null);
  const playlistActiveRef = useRef(false);
  const playlistSavedRef = useRef<{ id: string; time: number } | null>(null);
  const prevPhaseRef = useRef<string>("gameplay");

  const onMusicEnded = () => {
    const el = audioRef.current;
    const next = chainRef.current;
    chainRef.current = null;
    if (el && next) {
      el.src = next.src;
      el.loop = next.loop;
      el.play().catch(() => {});
      return;
    }
    // Advance the gameplay playlist: after the selected theme, loop
    // through all the others.
    if (el && playlistActiveRef.current) {
      const idx = playlistPosRef.current ? MUSIC_CYCLE.indexOf(playlistPosRef.current) : -1;
      const nextId = MUSIC_CYCLE[(idx + 1) % MUSIC_CYCLE.length];
      playlistPosRef.current = nextId;
      el.src = GAMEPLAY_TRACKS[nextId];
      el.loop = false;
      el.play().catch(() => {});
    }
  };

  // Sound effects (owner decisions 2026-10-25): the exact original
  // sounds from the owner's files — block drop on every lock, line clear
  // on every clear event, select1/select2 when a menu selection moves
  // down/up, and the firework rockets looping on a top-5 game over.
  const popCtxRef = useRef<AudioContext | null>(null);
  const sfxBuffersRef = useRef<Record<string, AudioBuffer>>({});
  const playSfx = useCallback((name: string): Promise<AudioBufferSourceNode | null> => {
    const ctx = popCtxRef.current ?? new AudioContext();
    popCtxRef.current = ctx;
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    return (async () => {
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
      src.start();
      return src;
    })();
  }, []);

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
    if (cleared) playSfx("clear");
    else if (locked) playSfx("drop");
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
      <audio ref={audioRef} onEnded={onMusicEnded} preload="auto" />
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
