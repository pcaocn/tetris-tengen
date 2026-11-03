// The music state machine (pure).
//
// Owner request 2026-10-29: the music used to fall silent for a second
// at a time, sometimes several times a minute, and the sound effects
// died completely later in a game. Both bugs lived in the audio
// bookkeeping, so it is kept here -- away from the DOM -- where it can
// be tested without a browser (see scripts/audio-plan.test.ts).
//
// The rules the machine follows:
// - The theme element is reloaded ONLY when the *intent* changes. The
//   intent is a key ("title", "preview:03", "gameplay:02") rather than
//   a source, so coming back from a celebration resumes the theme in
//   place instead of loading the file again (a reload costs a second
//   of silence: the browser has to load and decode the whole track).
// - The celebration cues (06 end of stage, 09 victory, 08 game over)
//   play on their own element, over the paused theme. The theme keeps
//   its source and its position.
// - The gameplay playlist advances by swapping two theme elements: the
//   next track is preloaded in the spare one, so the handover is
//   gapless.

// ============================================================
// THE THREE ELEMENTS, AND THE INTENT KEY
// ============================================================
// App.tsx owns three <audio> elements; this machine tells them what to do:
//   theme element A/B (two, swapping) -- the currently selected theme or
//       playlist track. Two of them so a playlist advance preloads the
//       next track in the spare and hands over without a gap.
//   cue element -- one-shot celebrations (06 end of stage, 09 victory,
//       08 game over), played OVER the paused theme.
//
// The central trick is the intent `key`. Instead of comparing audio
// sources (strings of file URLs), the machine compares INTENT keys:
//   "title"         -- title screen, introduction theme looping
//   "preview:03"    -- options page, previewing track 03
//   "gameplay:02"   -- playing, core-selected track 02
//   "silence"       -- options page before a preview (or Silent)
//   "keep"          -- special: whatever is loaded stays loaded, just
//                      paused (celebrations, game over)
// A key change is the ONLY thing that reloads a source, because a reload
// costs a second of silence (load + decode of a ~2 MB ogg). Everything
// else -- pause, resume, cue -- keeps the element's src and position
// intact.

export type MusicPlan = {
  /** What the theme element should be doing. "keep" means "hold
   * whatever is loaded and just pause it". */
  key: string;
  /** The source to load when the intent changes; null means silence. */
  src: string | null;
  /** Loop the theme (title, preview) or play it once (gameplay). */
  loop: boolean;
  /** The one-shot cue to play over the theme; null means none. */
  cue: string | null;
  /** The music phase the plan was made for ("gameplay", ...). */
  phase: string;
  /** The gameplay track the core has selected, when there is one. */
  trackId: string | null;
};

export type PlanInput = {
  started: boolean;
  atOptions: boolean;
  menuTouched: boolean;
  /** The menu's music id (null for Silent). */
  menuMusicId: string | null;
  phase: string;
  /** The track the core has selected for gameplay. */
  track: string | null;
  introSrc: string;
  trackUrls: Record<string, string>;
  endOfStageSrc: string;
  victorySrc: string;
  gameOverSrc: string;
};

/**
 * Half 1 of the machine: decide the INTENT from the game's situation.
 * Pure and side-effect free — it returns a description, never touches an
 * element. Decision order matters:
 *   1. not started  -> title / options / preview (menu preview wins over
 *                      the title theme once a track has been touched)
 *   2. celebration phases -> "keep" the theme paused, name the cue
 *   3. otherwise    -> the gameplay playlist, keyed by the core's track
 */
export function planMusic(input: PlanInput): MusicPlan {
  const { started, atOptions, menuTouched, phase, track } = input;
  if (!started) {
    // Title: the introduction theme loops. On the options page there is
    // no background music (owner request 2026-10-25): tracks play only
    // as menu previews, and Silent means silence.
    if (atOptions) {
      if (menuTouched) {
        const id = input.menuMusicId;
        return {
          key: `preview:${id ?? ""}`,
          src: id ? input.trackUrls[id] ?? null : null,
          loop: true,
          cue: null,
          phase,
          trackId: null,
        };
      }
      return { key: "silence", src: null, loop: true, cue: null, phase, trackId: null };
    }
    return {
      key: "title",
      src: input.introSrc,
      loop: true,
      cue: null,
      phase,
      trackId: null,
    };
  }
  if (phase === "level_complete") {
    // End of stage (owner request 2026-10-29): the celebration track
    // plays once and the next level starts by itself.
    return { key: "keep", src: null, loop: true, cue: input.endOfStageSrc, phase, trackId: null };
  }
  if (phase === "milestone") {
    return { key: "keep", src: null, loop: true, cue: input.victorySrc, phase, trackId: null };
  }
  if (phase === "game_over") {
    return { key: "keep", src: null, loop: true, cue: input.gameOverSrc, phase, trackId: null };
  }
  // Gameplay playlist (owner request 2026-10-25): start from the
  // selected theme, then loop through all of them; Silent stays
  // silent. The advance happens on each track's `ended` event.
  return {
    key: `gameplay:${track ?? "none"}`,
    src: track ? input.trackUrls[track] ?? null : null,
    loop: false,
    cue: null,
    phase,
    trackId: track,
  };
}

// ============================================================
// THE STATE, AND WHY IT IS AN ARGUMENT
// ============================================================
// AudioState is everything the machine remembers between steps. It is
// passed IN and returned OUT (rather than living in module scope) so a
// test can run a hundred steps from a fresh state with no browser and no
// reset — see scripts/audio-plan.test.ts, which walks a 30-level game
// asserting the theme loads exactly once.

export type AudioState = {
  /** The intent the theme element currently satisfies. */
  loadedKey: string | null;
  /** The track id playing in the active theme element. */
  playlistPos: string | null;
  /** The track id the spare theme element is preloading. */
  spareTrack: string | null;
  /** The cue the cue element currently holds. */
  wantedCue: string | null;
  /** The music phase of the previous step. */
  prevPhase: string | null;
  /** Whether the playlist may advance right now. */
  playlistActive: boolean;
};

export function initialAudioState(): AudioState {
  return {
    loadedKey: null,
    playlistPos: null,
    spareTrack: null,
    wantedCue: null,
    prevPhase: null,
    playlistActive: false,
  };
}

export type AudioAction =
  /** Load a new source into the theme element and start it. */
  | { type: "theme-load"; src: string; loop: boolean }
  /** Unload the theme (silence). */
  | { type: "theme-unload" }
  /** Start (or resume) the theme. */
  | { type: "theme-play" }
  /** Pause the theme, keeping its source and position. */
  | { type: "theme-pause" }
  /** Play a one-shot cue on the cue element. */
  | { type: "cue-play"; src: string }
  /** Stop the cue and drop its source. */
  | { type: "cue-clear" }
  /** Pause the cue. */
  | { type: "cue-pause" }
  /** Resume the cue that is already loaded. */
  | { type: "cue-resume" }
  /** Preload a track into the spare theme element. */
  | { type: "preload"; src: string }
  /** Hand over to the preloaded track (the theme elements swap). */
  | { type: "swap"; next: string; after: string };

export type AudioContext = {
  started: boolean;
  paused: boolean;
  /** The gameplay playlist, in order. */
  cycle: string[];
  /** Every playable track, by id. */
  themeUrls: Record<string, string>;
};

export type AudioStep = { state: AudioState; actions: AudioAction[] };

/**
 * Half 2 of the machine: reconcile the CURRENT AudioState against the
 * intent the plan describes, and emit the minimal list of AudioActions
 * that gets from here to there. The no-op rule is the point: an intent
 * that matches the loaded key emits NOTHING, which is why coming back
 * from a celebration resumes in place instead of reloading.
 *
 * The step order below is load-bearing — pause/quit checks come last and
 * return early, so a paused game never also emits a load.
 */
export function stepAudio(state: AudioState, plan: MusicPlan, ctx: AudioContext): AudioStep {
  const actions: AudioAction[] = [];
  const next: AudioState = { ...state };
  // A new game after a game over starts the theme from the top: the
  // gameplay intent is "the same key" but the game is not, so the normal
  // no-op rule must be overridden once. prevPhase is how we remember it.
  const newGame = state.prevPhase === "game_over" && plan.phase === "gameplay";
  next.prevPhase = plan.phase;
  // The playlist only runs in real gameplay with a real selected track —
  // not on the title, not during a celebration (its "ended" event would
  // otherwise fire mid-cue and swap songs under the celebration).
  next.playlistActive =
    ctx.started && plan.phase === "gameplay" && plan.src !== null && plan.trackId !== null;

  // The cue element is independent of the theme element: it plays over
  // the paused theme, so the theme never has to be reloaded.
  // Only a CHANGE of cue emits an action; the same cue again (e.g. every
  // frame of the celebration) emits nothing.
  if (plan.cue !== state.wantedCue) {
    next.wantedCue = plan.cue;
    if (plan.cue === null) actions.push({ type: "cue-clear" });
    else actions.push({ type: "cue-play", src: plan.cue });
  }

  // The theme element. "keep" holds whatever is loaded.
  // This condition IS the reload rule: load only when the intent key
  // differs (or a new game must restart the theme).
  if (plan.key !== "keep" && (plan.key !== state.loadedKey || newGame)) {
    next.loadedKey = plan.key;
    if (plan.src === null) {
      next.playlistPos = null;
      next.spareTrack = null;
      actions.push({ type: "theme-unload" });
    } else {
      actions.push({ type: "theme-load", src: plan.src, loop: plan.loop });
      // Preload the next playlist track into the spare element, so the
      // handover at the end of this track is gapless.
      if (next.playlistActive && plan.trackId) {
        next.playlistPos = plan.trackId;
        const idx = ctx.cycle.indexOf(plan.trackId);
        const nextId = ctx.cycle[(idx + 1) % ctx.cycle.length];
        next.spareTrack = nextId;
        actions.push({ type: "preload", src: ctx.themeUrls[nextId] });
      }
    }
  }

  // The music pauses with the game and resumes in place.
  const themeLoaded = plan.key !== "keep" && state.loadedKey === plan.key;
  // Pause check first, with an early return: while paused the ONLY legal
  // actions are pauses (a paused game must not start or swap tracks).
  if (ctx.paused) {
    actions.push({ type: "theme-pause" });
    if (state.wantedCue !== null) actions.push({ type: "cue-pause" });
    return { state: next, actions };
  }
  if (plan.key === "keep" || plan.src === null || plan.cue !== null) {
    // A cue plays on its own, or there is nothing to play.
    actions.push({ type: "theme-pause" });
  } else if (themeLoaded) {
    // Already loaded: resume it in place (after a celebration, a pause
    // or a playlist advance). Never reload it here -- that is what
    // caused the second of silence.
    actions.push({ type: "theme-play" });
  }
  if (plan.cue !== null && state.wantedCue !== null) {
    // The cue was already loaded (the game was paused during it).
    actions.push({ type: "cue-resume" });
  }
  return { state: next, actions };
}

/**
 * The playlist advance: a track ended, so the two theme elements swap.
 * Called from App.tsx's `ended` handler — NOT part of stepAudio, because
 * "ended" is an element event, not a state transition the plan describes.
 *
 * The swap: the spare element already holds the preloaded next track, so
 * it becomes the active one and starts instantly; the old active element
 * is handed the track AFTER that to preload for the next advance. Both
 * guards are the "do nothing" cases: no playlist running (a celebration
 * is on) or no preload ready (the advance is running ahead of the state
 * machine) — then the ended track just stops.
 */
export function advancePlaylist(
  state: AudioState,
  ctx: { cycle: string[]; themeUrls: Record<string, string> },
): AudioStep {
  if (!state.playlistActive) return { state, actions: [] };
  const nextId = state.spareTrack;
  if (!nextId) return { state, actions: [] };
  const idx = ctx.cycle.indexOf(nextId);
  const afterId = ctx.cycle[(idx + 1) % ctx.cycle.length];
  return {
    state: {
      ...state,
      playlistPos: nextId,
      spareTrack: afterId,
    },
    actions: [
      { type: "swap", next: ctx.themeUrls[nextId], after: ctx.themeUrls[afterId] },
    ],
  };
}
