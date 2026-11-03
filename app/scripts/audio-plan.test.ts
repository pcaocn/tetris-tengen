// ============================================================
// WHAT THIS FILE DOES
// ============================================================
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
//
// HOW THE TESTS WORK
// ------------------
// Every check feeds a Scenario into the real planMusic() + stepAudio()
// pair and asserts on the EMITTED ACTIONS, not on internal fields. That
// is the right level to test: actions are the contract with App.tsx
// ("load this src", "pause the theme"), and any regression in the
// reload rule shows up as an unexpected theme-load in the action list.
// The checks build on each other where a scenario needs history (the
// state from a previous step is fed forward), and the two long runs
// (30-level game, 8-track playlist) are the real regression guards:
// each once swallowed several bugs that only showed up after minutes
// of play.
//
// Node runs these .ts files directly (Node 22+ strips types); no test
// framework — just assert + a counter, so `npm test` stays fast.
import assert from "node:assert/strict";
import {
  advancePlaylist,
  initialAudioState,
  planMusic,
  stepAudio,
  type AudioAction,
  type AudioState,
} from "../src/audioPlan.ts";

// Fixture track table: the IDS are the real protocol ids ("02".."05"),
// the VALUES are fake one-word URLs — the machine only compares and
// forwards them, so there is no need for real paths here.
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

// One full machine step from `state` through a Scenario. The optional
// Scenario fields get neutral defaults, so a check names only the knobs
// it is exercising.
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

// Test helpers. `kinds` strips actions to their type names for whole-list
// assertions ("exactly these things happened, in this order"). `of` pulls
// out one action TYPE with its payload, using the Extract<> generic so
// TypeScript narrows the fields correctly — an empty result would mean
// the expected action never fired.
const kinds = (actions: AudioAction[]) => actions.map((a) => a.type);
const of = <T extends AudioAction["type"]>(
  actions: AudioAction[],
  type: T,
): Extract<AudioAction, { type: T }>[] =>
  actions.filter((a): a is Extract<AudioAction, { type: T }> => a.type === type);

// Micro test harness: run, count, report. No framework — a failed assert
// throws and aborts the whole run (exit code != 0 is the failure signal).
let checks = 0;
function check(name: string, fn: () => void) {
  fn();
  checks += 1;
  console.log(`  ok  ${name}`);
}

console.log("music state machine");

// -- The pre-game screens ------------------------------------------------

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

// -- The reload rule (the 2026-10-29 bug, in one check) ------------------
// Three chained steps: gameplay -> celebration -> back. The assertion
// that matters is the ABSENCE of a theme-load in the third step: the
// buggy code reloaded the file (a second of silence) here.

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

// The longest-run guard: 30 level transitions plus a game over. This is
// the check that would have caught the original bug immediately — the
// old code loaded the file twice per level (out of and back into the
// celebration), i.e. 61 loads; the correct count is exactly one.

check("a whole game never reloads the theme except at the start", () => {
  let s = initialAudioState();
  const loads: string[] = [];
  // `play` steps the machine forward AND records every theme-load that
  // comes out, so the final list is a history of the whole run.
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

// The one deliberate exception to the no-reload rule: same intent key,
// but a fresh game must restart the track from 0:00.

check("a new game after a game over starts the theme from the top", () => {
  const over = step(initialAudioState(), { started: true, track: "02", phase: "game_over" });
  const again = step(over.state, { started: true, track: "02" });
  assert.equal(of(again.actions, "theme-load").length, 1);
  assert.equal(of(again.actions, "theme-load")[0].src, "loginska");
});

// -- The playlist (gapless advance) ---------------------------------------
// advancePlaylist is driven by the element's "ended" event, so it is
// tested directly: step into gameplay, then call it as App.tsx would.

check("the playlist advances by swapping the preloaded elements", () => {
  const playing = step(initialAudioState(), { started: true, track: "02" });
  const adv = advancePlaylist(playing.state, { cycle: CYCLE, themeUrls: THEMES });
  assert.deepEqual(kinds(adv.actions), ["swap"]);
  assert.equal(of(adv.actions, "swap")[0].next, "bradinsky");
  assert.equal(of(adv.actions, "swap")[0].after, "kalinka");
  assert.equal(adv.state.playlistPos, "03");
  assert.equal(adv.state.spareTrack, "04");
});

// A celebration pauses the theme; an "ended" that fires then (or a stray
// one arriving late) must not swap tracks under the cue.

check("the playlist does not advance during a celebration", () => {
  const playing = step(initialAudioState(), { started: true, track: "02" });
  const during = step(playing.state, { started: true, track: "02", phase: "level_complete" });
  const adv = advancePlaylist(during.state, { cycle: CYCLE, themeUrls: THEMES });
  assert.deepEqual(adv.actions, []);
});

// Eight advances = two full laps of the 4-track cycle: proves the wrap
// arithmetic and that the advance never degrades into a reload.

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

// -- Pause / resume -------------------------------------------------------

check("the music pauses with the game and resumes in place", () => {
  const playing = step(initialAudioState(), { started: true, track: "02" });
  const paused = step(playing.state, { started: true, track: "02", paused: true });
  assert.deepEqual(kinds(paused.actions), ["theme-pause"]);
  const resumed = step(paused.state, { started: true, track: "02" });
  assert.deepEqual(kinds(resumed.actions), ["theme-play"]);
  assert.equal(of(resumed.actions, "theme-load").length, 0);
});

// Pausing DURING a celebration is the tricky corner: both elements must
// pause together, and resuming must bring the CUE back too (it was half
// played), not restart it from zero.

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

// Silent selection: the theme is UNLOADED (src removed), not merely
// paused — an empty <audio> element cannot leak a previously playing
// track back on resume.

check("Silent stays silent", () => {
  const r = step(initialAudioState(), { started: true, track: null });
  assert.deepEqual(kinds(r.actions), ["theme-unload", "theme-pause"]);
});

console.log(`\n${checks} checks passed`);
