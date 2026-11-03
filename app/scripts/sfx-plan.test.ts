// ============================================================
// WHAT THIS FILE DOES
// ============================================================
// Regression test for the sound-effects context policy.
//
// The owner reported (2026-10-29): "later in the game, sound of
// 'clear line' and 'block drop' are complete gone". The cause was the
// AudioContext policy, which is pure and lives in src/sfxPlan.ts, so
// it can be checked here without a browser.
//
// Run with: npm test
//
// HOW THE TESTS WORK: planSfx() and afterResume() take a context state
// string and return a decision. Each check pins one decision for one
// state — a table of "given X, do Y" cases. The two that matter most
// historically are the interrupted-context ones: the old code never
// rebuilt in that state, which is what silenced every sound for the
// rest of a game after the first interruption.
import assert from "node:assert/strict";
import { afterResume, planSfx } from "../src/sfxPlan.ts";

// Same micro harness as audio-plan.test.ts: run, count, report; a failed
// assert aborts the run with a non-zero exit code.
let checks = 0;
function check(name: string, fn: () => void) {
  fn();
  checks += 1;
  console.log(`  ok  ${name}`);
}

console.log("sound-effects context policy");

// -- planSfx: the decision BEFORE a resume attempt ------------------------

check("with no context yet, one is created", () => {
  const p = planSfx({ state: null });
  assert.equal(p.action, "create");
});

check("a closed context is replaced", () => {
  const p = planSfx({ state: "closed" });
  assert.equal(p.action, "create");
});

check("a running context is used as it is", () => {
  const p = planSfx({ state: "running" });
  assert.equal(p.action, "use");
});

check("a suspended context is resumed, not replaced", () => {
  // The browser's autoplay policy: it wants a user gesture, and the
  // next key press or click gives it one. Replacing the context here
  // would throw away a perfectly good one on every quiet moment.
  const p = planSfx({ state: "suspended" });
  assert.equal(p.action, "resume");
  assert.equal(p.then, "use");
});

check("an interrupted context is resumed, then replaced if that fails", () => {
  // WebKit's spelling of a context that was cut off. This is the bug
  // that killed the sound effects for the rest of the game: the old
  // code only ever resumed a context whose state was exactly
  // "suspended", so an interrupted one stayed dead and silent.
  const p = planSfx({ state: "interrupted" });
  assert.equal(p.action, "resume");
  assert.equal(p.then, "rebuild");
});

// -- afterResume: the decision AFTER a resume was attempted ---------------
// planSfx("interrupted") says "resume, then rebuild if needed" — these
// checks pin what "if needed" resolves to for each resulting state.

check("a resume that worked leaves the context usable", () => {
  assert.equal(afterResume("running").action, "use");
});

check("a resume that did not work on an interrupted context rebuilds it", () => {
  const p = afterResume("interrupted");
  assert.equal(p.action, "rebuild");
});

check("a context closed under us is replaced", () => {
  assert.equal(afterResume("closed").action, "create");
});

check("a still-suspended context is only resumed", () => {
  const p = afterResume("suspended");
  assert.equal(p.action, "resume");
  assert.equal(p.then, "use");
});

console.log(`\n${checks} checks passed`);
