// Regression test for the music state machine.
//
// The audio bugs the owner reported (owner request 2026-10-29) were all
// in this bookkeeping:
// - the music fell silent for a second, sometimes several times a
//   minute, because a `src` change forced a reload of the whole file;
// - the celebration music looped until Enter was pressed.
//
// The music is driven by src/audioPlan.ts, so the transitions can be
// checked here without a browser. Run with: npm test
import assert from "node:assert/strict";
import {
  advancePlaylist,
  initialAudioState,
  planMusic,
  stepAudio,
  type AudioAction,
  type AudioState,
} from "../src/audioPlan.ts";

const TRACKS = {
  "02": "loginska",
  "03": "bradinsky",
  "04": "kalinka",
  "05": "troika",
};
const THEMES = { "01": "intro", ...TRACKS };
const CYCLE = ["02", "03", "04", "05"];

type Scenario = {
  started: boolean;
  atOptions?: boolean;
  menuTouched?: boolean;
  menuMusicId?: string | null;
  phase?: string;
  track?: string | null;
  paused?: boolean;
};

function step(state: AudioState, sc: Scenario) {
  const plan = planMusic({
    started: sc.started,
    atOptions: sc.atOptions ?? false,
    menuTouched: sc.menuTouched ?? false,
    menuMusicId: sc.menuMusicId ?? null,
    phase: sc.phase ?? "gameplay",
    track: sc.track ?? null,
    introSrc: "intro",
    trackUrls: TRACKS,
    endOfStageSrc: "endofstage",
    victorySrc: "victory",
    gameOverSrc: "gameover",
  });
  return stepAudio(state, plan, {
    started: sc.started,
    paused: sc.paused ?? false,
    cycle: CYCLE,
    themeUrls: THEMES,
  });
}

const kinds = (actions: AudioAction[]) => actions.map((a) => a.type);
const of = <T extends AudioAction["type"]>(
  actions: AudioAction[],
  type: T,
): Extract<AudioAction, { type: T }>[] =>
  actions.filter((a): a is Extract<AudioAction, { type: T }> => a.type === type);

let checks = 0;
function check(name: string, fn: () => void) {
  fn();
  checks += 1;
  console.log(`  ok  ${name}`);
}

console.log("music state machine");

check("the title screen loads the introduction theme, looping", () => {
  const r = step(initialAudioState(), { started: false });
  assert.deepEqual(kinds(r.actions), ["theme-load"]);
  assert.equal(of(r.actions, "theme-load")[0].src, "intro");
  assert.equal(of(r.actions, "theme-load")[0].loop, true);
});

check("the options page is silent until a track is previewed", () => {
  const r = step(initialAudioState(), { started: false, atOptions: true });
  assert.deepEqual(kinds(r.actions), ["theme-unload", "theme-pause"]);
});

check("a menu preview loads the selected track", () => {
  const r = step(initialAudioState(), {
    started: false,
    atOptions: true,
    menuTouched: true,
    menuMusicId: "03",
  });
  assert.deepEqual(kinds(r.actions), ["theme-load"]);
  assert.equal(of(r.actions, "theme-load")[0].src, "bradinsky");
});

check("the game loads the selected theme and preloads the next track", () => {
  const r = step(initialAudioState(), { started: true, track: "02" });
  assert.deepEqual(kinds(r.actions), ["theme-load", "preload"]);
  assert.equal(of(r.actions, "theme-load")[0].src, "loginska");
  assert.equal(of(r.actions, "theme-load")[0].loop, false);
  assert.equal(of(r.actions, "preload")[0].src, "bradinsky");
});

check("the end-of-stage cue plays on its own element, over the paused theme", () => {
  const r = step(initialAudioState(), { started: true, track: "02", phase: "level_complete" });
  assert.deepEqual(kinds(r.actions), ["cue-play", "theme-pause"]);
  assert.equal(of(r.actions, "cue-play")[0].src, "endofstage");
});

check("the theme is NOT reloaded when the celebration ends", () => {
  const before = step(initialAudioState(), { started: true, track: "02" });
  const during = step(before.state, { started: true, track: "02", phase: "level_complete" });
  const after = step(during.state, { started: true, track: "02" });
  assert.deepEqual(kinds(after.actions), ["cue-clear", "theme-play"]);
  assert.equal(
    of(after.actions, "theme-load").length,
    0,
    "the theme must resume in place, not reload the file",
  );
});

check("a whole game never reloads the theme except at the start", () => {
  let s = initialAudioState();
  const loads: string[] = [];
  const play = (sc: Scenario) => {
    const r = step(s, sc);
    s = r.state;
    for (const a of of(r.actions, "theme-load")) loads.push(a.src);
    return r;
  };
  play({ started: true, track: "02" });
  for (let level = 0; level < 30; level += 1) {
    play({ started: true, track: "02", phase: "level_complete" });
    play({ started: true, track: "02" });
  }
  play({ started: true, track: "02", phase: "game_over" });
  assert.deepEqual(loads, ["loginska"], "the theme is loaded once per game");
});

check("the milestone cue is the victory track", () => {
  const r = step(initialAudioState(), { started: true, track: "02", phase: "milestone" });
  assert.equal(of(r.actions, "cue-play")[0].src, "victory");
});

check("game over plays the game-over cue", () => {
  const r = step(initialAudioState(), { started: true, track: "02", phase: "game_over" });
  assert.deepEqual(kinds(r.actions), ["cue-play", "theme-pause"]);
  assert.equal(of(r.actions, "cue-play")[0].src, "gameover");
});

check("a new game after a game over starts the theme from the top", () => {
  const over = step(initialAudioState(), { started: true, track: "02", phase: "game_over" });
  const again = step(over.state, { started: true, track: "02" });
  assert.equal(of(again.actions, "theme-load").length, 1);
  assert.equal(of(again.actions, "theme-load")[0].src, "loginska");
});

check("the playlist advances by swapping the preloaded elements", () => {
  const playing = step(initialAudioState(), { started: true, track: "02" });
  const adv = advancePlaylist(playing.state, { cycle: CYCLE, themeUrls: THEMES });
  assert.deepEqual(kinds(adv.actions), ["swap"]);
  assert.equal(of(adv.actions, "swap")[0].next, "bradinsky");
  assert.equal(of(adv.actions, "swap")[0].after, "kalinka");
  assert.equal(adv.state.playlistPos, "03");
  assert.equal(adv.state.spareTrack, "04");
});

check("the playlist does not advance during a celebration", () => {
  const playing = step(initialAudioState(), { started: true, track: "02" });
  const during = step(playing.state, { started: true, track: "02", phase: "level_complete" });
  const adv = advancePlaylist(during.state, { cycle: CYCLE, themeUrls: THEMES });
  assert.deepEqual(adv.actions, []);
});

check("the playlist keeps advancing over a long game", () => {
  let s = initialAudioState();
  s = step(s, { started: true, track: "02" }).state;
  const seen: string[] = [];
  for (let i = 0; i < 8; i += 1) {
    const adv = advancePlaylist(s, { cycle: CYCLE, themeUrls: THEMES });
    s = adv.state;
    seen.push(s.playlistPos ?? "?");
    // The theme must not be reloaded by an advance.
    assert.equal(of(adv.actions, "theme-load").length, 0);
  }
  assert.deepEqual(seen, ["03", "04", "05", "02", "03", "04", "05", "02"]);
});

check("the music pauses with the game and resumes in place", () => {
  const playing = step(initialAudioState(), { started: true, track: "02" });
  const paused = step(playing.state, { started: true, track: "02", paused: true });
  assert.deepEqual(kinds(paused.actions), ["theme-pause"]);
  const resumed = step(paused.state, { started: true, track: "02" });
  assert.deepEqual(kinds(resumed.actions), ["theme-play"]);
  assert.equal(of(resumed.actions, "theme-load").length, 0);
});

check("a celebration paused and resumed comes back with its cue", () => {
  const playing = step(initialAudioState(), { started: true, track: "02" });
  const during = step(playing.state, { started: true, track: "02", phase: "level_complete" });
  const paused = step(during.state, {
    started: true,
    track: "02",
    phase: "level_complete",
    paused: true,
  });
  assert.deepEqual(kinds(paused.actions), ["theme-pause", "cue-pause"]);
  const resumed = step(paused.state, { started: true, track: "02", phase: "level_complete" });
  assert.ok(kinds(resumed.actions).includes("cue-resume"));
});

check("Silent stays silent", () => {
  const r = step(initialAudioState(), { started: true, track: null });
  assert.deepEqual(kinds(r.actions), ["theme-unload", "theme-pause"]);
});

console.log(`\n${checks} checks passed`);
