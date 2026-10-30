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

/** What the theme and the cue element should be doing right now. */
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

/** Advance the audio state machine by one step. */
export function stepAudio(state: AudioState, plan: MusicPlan, ctx: AudioContext): AudioStep {
  const actions: AudioAction[] = [];
  const next: AudioState = { ...state };
  // A new game after a game over starts the theme from the top.
  const newGame = state.prevPhase === "game_over" && plan.phase === "gameplay";
  next.prevPhase = plan.phase;
  next.playlistActive =
    ctx.started && plan.phase === "gameplay" && plan.src !== null && plan.trackId !== null;

  // The cue element is independent of the theme element: it plays over
  // the paused theme, so the theme never has to be reloaded.
  if (plan.cue !== state.wantedCue) {
    next.wantedCue = plan.cue;
    if (plan.cue === null) actions.push({ type: "cue-clear" });
    else actions.push({ type: "cue-play", src: plan.cue });
  }

  // The theme element. "keep" holds whatever is loaded.
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

/** The playlist advance: a track ended, so the two theme elements swap. */
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
