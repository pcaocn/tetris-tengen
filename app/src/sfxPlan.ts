// The sound-effects context policy (pure).
//
// Owner request 2026-10-29: "later in the game, sound of 'clear line'
// and 'block drop' are complete gone". Two causes, both here:
//
// - every sound created a GainNode that was connected to the
//   destination and never disconnected, so the audio graph grew by two
//   nodes per locked piece until the context gave up. The nodes are
//   now released when the sound ends (see the "ended" listener in
//   App.tsx).
// - the context was only resumed when its state was exactly
//   "suspended", and the resume was never awaited. WebKit spells an
//   interrupted context "interrupted", so after any interruption the
//   context stayed dead and every later sound was silent.
//
// The decision of what to do with a context is pure, so it lives here
// where it can be tested without a browser (scripts/sfx-plan.test.ts).

export type SfxContextState = "running" | "suspended" | "closed" | "interrupted";

export type SfxPlanInput = {
  /** The context's current state, or null when there is none yet. */
  state: SfxContextState | null;
};

// ============================================================
// THE FOUR CONTEXT STATES, AND WHAT EACH MEANS
// ============================================================
//   "running"     -- healthy; play.
//   "suspended"   -- the browser parked it (autoplay policy). It is NOT
//                    broken: a user gesture is wanted, and App.tsx's kick
//                    handler resumes it on the next key/click.
//   "interrupted" -- WebKit's state after the OS took the audio route
//                    (phone call, another app). A resume usually does
//                    NOT revive it; plan for a rebuild.
//   "closed"      -- explicitly closed; must never be reused.
//
// The plan types force the caller to handle all of these; there is no
// "silently try to play" path, which is exactly the bug this file exists
// to prevent.

export type SfxPlan =
  /** Create a context (there is none, or the old one is closed). */
  | { action: "create"; resume: boolean }
  /** Try to resume the existing context and use it. */
  | { action: "resume"; then: "use" | "rebuild" | "drop" }
  /** The context is dead in a way resume cannot fix: build a new one. */
  | { action: "rebuild"; resume: true }
  /** Use the context as it is. */
  | { action: "use" };

/**
 * What to do with the sound-effects AudioContext.
 *
 * "suspended" is the browser's autoplay policy: it wants a user
 * gesture, and the next key press or click provides it (see the kick
 * handler in App.tsx). A merely suspended context is therefore left
 * alone and the sound is dropped -- playing it would fail anyway.
 *
 * "interrupted" (WebKit's spelling of a context that was cut off) is
 * different: the context is dead and will not come back, so a fresh
 * one is built. That is what brought the block-drop and line-clear
 * sounds back after the game had been silent for a while.
 */
export function planSfx(input: SfxPlanInput): SfxPlan {
  const { state } = input;
  if (state === null || state === "closed") {
    return { action: "create", resume: true };
  }
  if (state === "running") {
    return { action: "use" };
  }
  if (state === "suspended") {
    // The browser wants a gesture; a resume may succeed if one just
    // happened. If it does not, the context is merely idle, not dead.
    return { action: "resume", then: "use" };
  }
  // "interrupted": resume and, if that does not bring it back, build a
  // new context. The context is never silently reused in this state --
  // that is the bug that killed the sound effects for the rest of the
  // game.
  return { action: "resume", then: "rebuild" };
}

/**
 * The second half of the resume handshake: called with the state the
 * context reports AFTER a resume was attempted. App.tsx consults this
 * because `resume()` resolves even when it did nothing — the only
 * reliable answer is the state it leaves behind.
 *
 * "running"  -> the resume worked; play.
 * "suspended"-> still gesture-blocked; leave it for the kick handler.
 * "closed"   -> replaced (create).
 * anything else (still "interrupted") -> the resume failed, rebuild.
 */
export function afterResume(state: SfxContextState): SfxPlan {
  if (state === "running") return { action: "use" };
  if (state === "suspended") return { action: "resume", then: "use" };
  if (state === "closed") return { action: "create", resume: true };
  return { action: "rebuild", resume: true };
}
