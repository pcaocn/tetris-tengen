#!/usr/bin/env python3
"""
Sweep autopilot strategy variants over a seed set and compare them.

Every variant is measured on the SAME seeds under the SAME frame budget,
so the comparison is apples-to-apples. A run that dies early stops
accruing score; a run that survives scores for the whole budget. The
headline metric is therefore "score in the first N frames", not "final
score", which would be censored.

Usage:
    uv run python sweep_autopilot.py --seeds 100 --cap 250000

WHAT THIS SCRIPT IS FOR
-----------------------
It is the tuning workbench for the "highscore" autopilot profile. The
profile is a set of weights in `core/tetris_core/autopilot.py`; this
script builds MANY candidate profiles (each one a small change to the
current best), plays every candidate on the same seeds, and prints a
comparison table so a better profile can be picked on evidence rather
than on a hunch.

THE MEASUREMENT RULES THAT MAKE THE RESULTS TRUSTWORTHY
-------------------------------------------------------
1. SAME SEEDS FOR EVERY VARIANT. The seeds are drawn once from a master
   seed, and every variant plays exactly those seeds. A variant is
   therefore never lucky or unlucky -- it is only different.
2. A FIXED FRAME BUDGET. Every run gets `--cap` frames (250,000 by
   default, about 69 minutes of game time at 60 Hz). A run that dies
   early stops earning score, so the score at the cap measures "how far
   did this profile get", and a variant that survives longer scores
   more. This is why the metric is score@cap and not final score.
3. EARLY DEATHS ARE COUNTED SEPARATELY. A run that topes out with fewer
   than 3000 lines is an "early death" -- the failure mode the board-
   fullness work was about. The count is the survival metric.
4. STATISTICS, NOT JUST MEANS. The output prints median and mean score,
   because the score distribution is heavily skewed: a few great runs
   pull the mean far above the typical run.

READING THE OUTPUT
------------------
    score@cap: mean / median   -- higher is better
    lines median                -- how far the typical run got
    early deaths=X/N           -- LOWER is better (survival)
    died=X/N                   -- any death at all, within the budget
    pts/line                    -- the score efficiency of the clears
    tetrises                    -- average tetris count per run

The final ranking is by MEDIAN score, with early deaths as the
tiebreak. The median is used because it is not dragged around by the
handful of runs that get lucky.

SEE ALSO
--------
    core/analyze_frontier.py   -- paired statistical comparison of the
                                   variants in the CSV this writes
    core/simulate_autopilot.py -- a full-game benchmark of one strategy
"""

from __future__ import annotations

import argparse
import copy
import multiprocessing as mp
import random
import statistics
import sys

from tetris_core import autopilot
from tetris_core.game import Game, Status
from tetris_core.rng import PieceRNG

# The pre-2026-10-29 profile, kept as the sweep's baseline.
#
# This is the profile as it was BEFORE the board-fullness work: no
# danger ramp at all, so it plays for score all the way to the ceiling.
# Every later variant is measured against this baseline to show what the
# danger ramp bought.
BASELINE = {
    "landing_w": autopilot.W_LANDING,
    "landing_free": 4.0,
    "lines_w": 0.0,
    "points_w": 1.0,
    "defer_w": 25.0,
    "safe_h": 10,
    "well_w": -2.0,
    "holes_w": -12.0,
}


def variant(name: str, **overrides) -> tuple[str, dict]:
    """Build a variant profile from the current highscore profile.

    A variant is the SHIPPED profile with one or two values changed.
    Starting from the shipped profile (rather than from scratch) is what
    makes the sweep results interpretable: every variant differs from
    the current best by exactly the amount under test.

    `danger_w` is special: it is a nested dict of the survival weights,
    so it is MERGED into the existing danger dict rather than replacing
    it. That way `danger_w={"points_w": 3.0}` changes only the points
    weight and leaves the other danger weights alone.

    An unknown key is an error, not a silent no-op -- a typo in a
    variant name would otherwise produce a variant that is identical to
    the baseline and quietly corrupt the comparison.
    """
    # Deep copy: the profile contains nested dicts, and a shallow copy
    # would let one variant's edit leak into the next one.
    profile = copy.deepcopy(autopilot.STRATEGIES["highscore"])
    # Pull the nested override out before the flat-key loop, because
    # "danger_w" is not a top-level key of the profile.
    danger_w = overrides.pop("danger_w", None)
    for key, value in overrides.items():
        if key in profile:
            profile[key] = value
        else:
            raise KeyError(f"unknown profile key: {key}")
    if danger_w is not None:
        # Merge the given danger weights over the existing ones.
        profile["danger_w"] = {**profile.get("danger_w", {}), **danger_w}
    return name, profile


def build_variants() -> dict[str, dict]:
    """The catalogue of candidate profiles to compare.

    This is a HISTORY of the tuning work, kept in the code so every
    result in the spec can be reproduced. The rounds are in the order
    they were run:

      baseline / no-danger / d*-s*   round 1: does the danger ramp help,
                                     and where should it start and how
                                     steep should it be?
      hard / hard-flat* / hard-holes* round 2: the round-1 winner plus a
                                     flatness penalty for the canyon-
                                     next-to-a-tower death shape.
      hard-s3/s4/s5 / hard-flat12/16  round 3: sharper ramps, stronger
                                     flatness.
      hard-flat8-c2/c3/c4, ...-fb*    round 4-5: price the clears
                                     properly as the stack fills.
      hard-flat8-agg*/maxh*          round 6: reward taking the stack
                                     DOWN. (Measured to make things
                                     worse, and dropped in round 7.)
      hard-flat8-lw*                 round 7: pay per ROW at danger
                                     instead of by point value.
      cur / sh4..sh12 / dh1 / lc*    round 9: the score/survival
                                     TRADEOFF curve, and two candidates
                                     that might bend it.
      dw0..dw60 / dwl2..dwl4         round 10: the aggressiveness dial
                                     itself -- what refusing a small
                                     clear actually buys.
      dmax1 / dmax1w2                round 11: the two fixes the
                                     measurements point at.

    Every variant is a full profile, so a variant can be copied straight
    into `autopilot.STRATEGIES["highscore"]` when it wins.

    NOTE: this list is long, and a full sweep runs every entry on every
    seed. Use `--only` to run just the variants you are interested in
    (see main()).
    """
    v: dict[str, dict] = {"baseline": copy.deepcopy(BASELINE)}
    v["no-danger"] = variant(
        "no-danger", danger_h=None, danger_w={}
    )[1]
    # danger_h = 10 (half full) with different ramps
    v["d10-s6"] = variant("d10-s6", danger_h=10.0, danger_span=6.0)[1]
    v["d8-s6"] = variant("d8-s6", danger_h=8.0, danger_span=6.0)[1]
    v["d12-s6"] = variant("d12-s6", danger_h=12.0, danger_span=6.0)[1]
    v["d10-s4"] = variant("d10-s4", danger_h=10.0, danger_span=4.0)[1]
    v["d10-s10"] = variant("d10-s10", danger_h=10.0, danger_span=10.0)[1]
    # stronger / weaker danger weights at half full
    v["d10-s6-hard"] = variant(
        "d10-s6-hard",
        danger_h=10.0,
        danger_span=6.0,
        danger_w={
            "landing_w": -14.0,
            "landing_free": 0.0,
            "well_w": -14.0,
            "holes_w": -32.0,
        },
    )[1]
    v["d10-s6-soft"] = variant(
        "d10-s6-soft",
        danger_h=10.0,
        danger_span=6.0,
        danger_w={
            "landing_w": -6.0,
            "landing_free": 2.0,
            "well_w": -5.0,
            "holes_w": -16.0,
        },
    )[1]
    # Round 2: build on the round-1 winner (d10-s6-hard) and attack the
    # failure mode the round-1 survivors still die of -- a deep canyon
    # next to a tall tower, which the well metric does not see.
    HARD = {
        "landing_w": -14.0,
        "landing_free": 0.0,
        "well_w": -14.0,
        "holes_w": -32.0,
    }
    v["hard"] = variant("hard", danger_h=10.0, danger_span=6.0, danger_w=HARD)[1]
    # Flatness penalty: the height step between neighbouring columns,
    # scaled by danger. A canyon next to a tower is the death shape.
    v["hard-flat2"] = variant(
        "hard-flat2", danger_h=10.0, danger_span=6.0, danger_w=HARD, flat_w=-2.0
    )[1]
    v["hard-flat4"] = variant(
        "hard-flat4", danger_h=10.0, danger_span=6.0, danger_w=HARD, flat_w=-4.0
    )[1]
    v["hard-flat8"] = variant(
        "hard-flat8", danger_h=10.0, danger_span=6.0, danger_w=HARD, flat_w=-8.0
    )[1]
    # Holes count as extra stack height: a dirty board is closer to death.
    v["hard-holes1"] = variant(
        "hard-holes1", danger_h=10.0, danger_span=6.0, danger_w=HARD, danger_holes=1.0
    )[1]
    v["hard-holes2"] = variant(
        "hard-holes2", danger_h=10.0, danger_span=6.0, danger_w=HARD, danger_holes=2.0
    )[1]
    # Flatness plus hole-weighted danger.
    v["hard-flat4-holes1"] = variant(
        "hard-flat4-holes1",
        danger_h=10.0,
        danger_span=6.0,
        danger_w=HARD,
        flat_w=-4.0,
        danger_holes=1.0,
    )[1]
    # An earlier ramp: danger starts at 8 instead of 10.
    v["hard-d8"] = variant(
        "hard-d8", danger_h=8.0, danger_span=6.0, danger_w=HARD, flat_w=-4.0
    )[1]
    # Round 3: sharpen the ramp (a short span goes conservative quickly
    # once past half full) and push the flatness penalty harder.
    v["hard-s3"] = variant(
        "hard-s3", danger_h=10.0, danger_span=3.0, danger_w=HARD, flat_w=-8.0
    )[1]
    v["hard-s4"] = variant(
        "hard-s4", danger_h=10.0, danger_span=4.0, danger_w=HARD, flat_w=-8.0
    )[1]
    v["hard-s5"] = variant(
        "hard-s5", danger_h=10.0, danger_span=5.0, danger_w=HARD, flat_w=-8.0
    )[1]
    v["hard-flat12"] = variant(
        "hard-flat12", danger_h=10.0, danger_span=6.0, danger_w=HARD, flat_w=-12.0
    )[1]
    v["hard-flat16"] = variant(
        "hard-flat16", danger_h=10.0, danger_span=6.0, danger_w=HARD, flat_w=-16.0
    )[1]
    v["hard-d9-flat8"] = variant(
        "hard-d9-flat8", danger_h=9.0, danger_span=6.0, danger_w=HARD, flat_w=-8.0
    )[1]
    v["hard-d9-s4-flat8"] = variant(
        "hard-d9-s4-flat8",
        danger_h=9.0,
        danger_span=4.0,
        danger_w=HARD,
        flat_w=-8.0,
    )[1]
    # Round 4: the round-3 winner survives much longer, but the deaths
    # that are left have a new shape -- the board fills up WITHOUT being
    # cleared. Measured on the survivors: at full danger the strategy
    # clears a line in only ~1 piece in 3, because the landing penalty
    # (-14 per row) is worth far more than a clear (25 for a tetris).
    # So: make clears worth more as the stack fills, and keep a share of
    # the flatness penalty even on a safe board (a canyon dug early is
    # fatal by the time it matters).
    v["hard-flat8-c2"] = variant(
        "hard-flat8-c2", danger_w={"points_w": 2.0}
    )[1]
    v["hard-flat8-c3"] = variant(
        "hard-flat8-c3", danger_w={"points_w": 3.0}
    )[1]
    v["hard-flat8-c4"] = variant(
        "hard-flat8-c4", danger_w={"points_w": 4.0}
    )[1]
    v["hard-flat8-c3-lw10"] = variant(
        "hard-flat8-c3-lw10", danger_w={"points_w": 3.0, "landing_w": -10.0}
    )[1]
    v["hard-flat8-c3-lw12"] = variant(
        "hard-flat8-c3-lw12", danger_w={"points_w": 3.0, "landing_w": -12.0}
    )[1]
    v["hard-flat8-c2-fb5"] = variant(
        "hard-flat8-c2-fb5", danger_w={"points_w": 2.0}, flat_base=0.5
    )[1]
    v["hard-flat8-c3-fb3"] = variant(
        "hard-flat8-c3-fb3", danger_w={"points_w": 3.0}, flat_base=0.3
    )[1]
    v["hard-flat8-c6-fb3"] = variant(
        "hard-flat8-c6-fb3", danger_w={"points_w": 6.0}, flat_base=0.3
    )[1]
    # Round 5: the death-seed screen picked "c3-fb3" (clears worth 3x at
    # full danger, and 30% of the flatness penalty applied even on a
    # safe board) -- 2/33 early deaths against 33/33 for hard-flat8.
    # Grid the neighbourhood to find the shape of that optimum.
    v["hard-flat8-c2-fb3"] = variant(
        "hard-flat8-c2-fb3", danger_w={"points_w": 2.0}, flat_base=0.3
    )[1]
    v["hard-flat8-c4-fb3"] = variant(
        "hard-flat8-c4-fb3", danger_w={"points_w": 4.0}, flat_base=0.3
    )[1]
    v["hard-flat8-c3-fb1"] = variant(
        "hard-flat8-c3-fb1", danger_w={"points_w": 3.0}, flat_base=0.1
    )[1]
    v["hard-flat8-c3-fb5"] = variant(
        "hard-flat8-c3-fb5", danger_w={"points_w": 3.0}, flat_base=0.5
    )[1]
    v["hard-flat8-c4-fb5"] = variant(
        "hard-flat8-c4-fb5", danger_w={"points_w": 4.0}, flat_base=0.5
    )[1]
    # Round 6: the death-seed screen turned out to be a mirage (a
    # variant that looked great on the 33 death seeds scored 20% lower
    # on fresh seeds), so the new terms are judged on fresh seeds only.
    #
    # The measured early deaths all look the same: every column at
    # height 13-20, the stack at the ceiling, holes everywhere.
    # El-Tetris has no feature for the height of the stack, so nothing
    # rewards taking it DOWN. These two terms add that reward:
    #   agg_w  -- penalty per unit of total stack height (all columns)
    #   maxh_w -- penalty per unit of the tallest column
    # A tetris lowers every column by four rows, which the landing
    # height cannot see.
    v["hard-flat8-agg2"] = variant(
        "hard-flat8-agg2", danger_w={"agg_w": -2.0}
    )[1]
    v["hard-flat8-agg4"] = variant(
        "hard-flat8-agg4", danger_w={"agg_w": -4.0}
    )[1]
    v["hard-flat8-agg8"] = variant(
        "hard-flat8-agg8", danger_w={"agg_w": -8.0}
    )[1]
    v["hard-flat8-maxh4"] = variant(
        "hard-flat8-maxh4", danger_w={"maxh_w": -4.0}
    )[1]
    v["hard-flat8-maxh8"] = variant(
        "hard-flat8-maxh8", danger_w={"maxh_w": -8.0}
    )[1]
    v["hard-flat8-agg4-maxh4"] = variant(
        "hard-flat8-agg4-maxh4", danger_w={"agg_w": -4.0, "maxh_w": -4.0}
    )[1]
    # The same terms with an earlier danger ramp.
    v["hard-d8-agg4"] = variant(
        "hard-d8-agg4", danger_h=8.0, danger_span=6.0, danger_w={"agg_w": -4.0}
    )[1]
    v["hard-d9-agg4"] = variant(
        "hard-d9-agg4", danger_h=9.0, danger_span=6.0, danger_w={"agg_w": -4.0}
    )[1]
    # Round 7: the aggregate-height terms were measured to make things
    # WORSE (early deaths 10/300 -> 19/300 -> 31/300 as the weight
    # rose), so they are dropped.
    #
    # The per-danger probe says something more useful. Sampling every
    # piece of three dying games and recording whether ANY placement
    # cleared a row:
    #
    #   danger  pieces  clear avail  taken  skipped  avg maxh  avg holes
    #      0.0    3560        73.8%     824     1802        6.6        0.6
    #      0.5     129        48.8%      45       18       13.0        8.3
    #      1.0      76        52.6%      28       12       15.8       11.8
    #
    # At danger 1.0 the strategy DOES take clears when they are on offer
    # (only 12 of 40 skipped), so "it ignores clears" is wrong. What is
    # wrong is the price of a clear: the highscore profile pays for
    # clears by their point value only (a single is worth 1 point), and
    # the danger weights then add a landing cost of 14 per row. So a
    # single clear is worth +1 against a landing cost of -14 per row --
    # it is never worth taking, and the board fills instead.
    #
    # The "quick" strategy does not have this problem: it pays
    # W_LINES = 3.418 per row cleared, and it never has an early death
    # (0/100 in the 100-game benchmark). So: pay per ROW at danger.
    # The candidates below sweep that per-row payment.
    v["hard-flat8-lw2"] = variant(
        "hard-flat8-lw2", danger_w={"lines_w": 2.0}
    )[1]
    v["hard-flat8-lw4"] = variant(
        "hard-flat8-lw4", danger_w={"lines_w": 4.0}
    )[1]
    v["hard-flat8-lw8"] = variant(
        "hard-flat8-lw8", danger_w={"lines_w": 8.0}
    )[1]
    v["hard-flat8-lw16"] = variant(
        "hard-flat8-lw16", danger_w={"lines_w": 16.0}
    )[1]
    # A per-row payment, plus a wider danger ramp so the payment starts
    # earlier (before the stack is already at the ceiling).
    v["hard-flat8-lw4-d8"] = variant(
        "hard-flat8-lw4-d8",
        danger_h=8.0,
        danger_span=6.0,
        danger_w={"lines_w": 4.0},
    )[1]
    v["hard-flat8-lw4-d9"] = variant(
        "hard-flat8-lw4-d9",
        danger_h=9.0,
        danger_span=6.0,
        danger_w={"lines_w": 4.0},
    )[1]
    # The per-row payment together with a smaller landing cost at
    # danger: the landing cost is what makes a clear look expensive, so
    # the two have to be tuned together.
    v["hard-flat8-lw4-lw10"] = variant(
        "hard-flat8-lw4-lw10",
        danger_w={"lines_w": 4.0, "landing_w": -10.0},
    )[1]
    v["hard-flat8-lw8-lw10"] = variant(
        "hard-flat8-lw8-lw10",
        danger_w={"lines_w": 8.0, "landing_w": -10.0},
    )[1]
    # Round 9: the TRADEOFF study. Two questions:
    #
    # (a) Does a tradeoff exist at all? "safe_h" is the dial that decides
    #     when the strategy stops deferring small clears to hunt a
    #     tetris. It should slide the strategy along a frontier: a lower
    #     safe_h means more eager clearing, so fewer early deaths and a
    #     lower score. The round-8 partial said yes (sh6: 12/300 deaths
    #     but -8% score) but it was measured on 300 seeds, where the
    #     counts are near the noise floor. This round measures the whole
    #     curve plus the candidates that could BEND it, on fresh seeds,
    #     and analyze_frontier.py compares them PAIRWISE (McNemar on the
    #     discordant seeds) because every variant runs on the same
    #     seeds and the paired test is far more powerful than comparing
    #     two independent death rates.
    #
    # (b) Can the frontier be bent? Two candidates:
    #     - "danger_holes": a board with buried holes is closer to death
    #       than a clean one of the same height, so holes should raise
    #       the effective stack height in the danger ramp. The measured
    #       death boards have "holes everywhere" and max height 13-20,
    #       so the ramp (which starts at 10 and saturates at 16) is
    #       fully saturated by then and cannot see the dirt. This was
    #       tried in round 2 against a much weaker baseline; worth
    #       retrying against the current profile.
    #     - "landing_credit": the landing height is measured on the
    #       PRE-lock board, so a placement is charged landing cost for
    #       the rows its own clear removes. Credit them back and a
    #       clearing placement is priced by the stack it LEAVES behind.
    v["cur"] = copy.deepcopy(autopilot.STRATEGIES["highscore"])
    # The tradeoff curve: safe_h is the dial that decides when the
    # strategy stops deferring small clears to hunt a tetris.
    v["sh4"] = variant("sh4", safe_h=4)[1]
    v["sh6"] = variant("sh6", safe_h=6)[1]
    v["sh8"] = variant("sh8", safe_h=8)[1]
    v["sh12"] = variant("sh12", safe_h=12)[1]
    # Frontier benders.
    v["dh1"] = variant("dh1", danger_holes=1.0)[1]
    v["dh2"] = variant("dh2", danger_holes=2.0)[1]
    # "landing_credit" blends base -> danger like every other weight, so
    # set both ends to pin it, or set only the danger end to make it
    # apply only when the stack is filling.
    v["lc05"] = variant("lc05", landing_credit=0.5, danger_w={"landing_credit": 0.5})[1]
    v["lc10"] = variant("lc10", landing_credit=1.0, danger_w={"landing_credit": 1.0})[1]
    v["lcd10"] = variant("lcd10", danger_w={"landing_credit": 1.0})[1]
    # Round 10: the AGGRESSIVENESS dial itself.
    #
    # "defer_w" is the cost the strategy pays to refuse a 1-2 line clear
    # while the board is clean and low. It is the single knob that says
    # "shoot for tetris" -- the higher it is, the more the strategy
    # gives up small clears in the hope of a big one later. Round 7
    # showed that the deferral buys tetrises; the question this round
    # asks is whether it buys them CHEAPLY.
    #
    # The deferprod diagnostic (core/../tmp/deferprod.py) answered that:
    # a deferred piece is followed by a tetris within 12 pieces about
    # 25-30% of the time, and a NON-deferred piece about the same. The
    # deferral is not buying extra tetrises at all -- it is just
    # refusing points. That makes defer_w the cleanest possible
    # tradeoff dial, and this sweep maps the whole curve:
    #   defer_w = 0   take every clear, never hunt a tetris
    #   defer_w = 25  the shipped profile
    #   defer_w = 60  hunt tetrises at any cost
    v["dw0"] = variant("dw0", defer_w=0.0)[1]
    v["dw10"] = variant("dw10", defer_w=10.0)[1]
    v["dw15"] = variant("dw15", defer_w=15.0)[1]
    v["dw40"] = variant("dw40", defer_w=40.0)[1]
    v["dw60"] = variant("dw60", defer_w=60.0)[1]
    # "defer_well": hold back a small clear only when a big one is
    # actually reachable -- a one-column well at least this deep. A
    # tetris needs a well four rows deep, so a board with no deep well
    # is not "saving rows for a tetris", it is just refusing points.
    v["dwl2"] = variant("dwl2", defer_well=2.0)[1]
    v["dwl3"] = variant("dwl3", defer_well=3.0)[1]
    v["dwl4"] = variant("dwl4", defer_well=4.0)[1]
    # Round 11: the two fixes the MEASUREMENTS point at, rather than
    # another sweep of the same dial.
    #
    # (1) "defer_max": the deferral refuses a 1-2 line clear. A single
    #     is worth 100 points, a double 400. Refusing a 400-point
    #     double to chase a 2500-point tetris is a far worse bet than
    #     refusing a 100-point single, so "defer singles only" is the
    #     shape the measured evidence actually supports.
    # (2) "defer_well": refuse a small clear only when a big one is
    #     genuinely reachable (a well at least this deep). Measured on
    #     live games, deferring does NOT raise the chance of a tetris
    #     within 12 pieces, so on a board with no deep well the
    #     deferral is pure point-refusal.
    v["dmax1"] = variant("dmax1", defer_max=1.0)[1]
    v["dmax1w2"] = variant("dmax1w2", defer_max=1.0, defer_well=2.0)[1]
    return v


def run_one(job) -> dict:
    """Play one full game with one variant profile and report the result.

    This runs in a worker process, so it must be self-contained: it
    takes the seed, the profile and the frame budget, and returns a
    plain dict (which is picklable -- a Game object is not).

    Note the profile is installed by OVERWRITING the global strategy
    entry. That is safe here because each worker process handles its
    jobs one at a time, and it is what lets the sweep reuse the real
    `Game` and the real `autopilot` code -- the sweep never re-implements
    the game, it only changes the weights.
    """
    seed, profile, cap = job
    # Install this run's weights as THE highscore profile.
    autopilot.STRATEGIES["highscore"] = profile
    # A fresh game on a seeded RNG: the same seed always produces the
    # same piece sequence.
    game = Game(rng=PieceRNG(seed))
    game.set_autopilot("highscore")

    # Clear-type counters, derived from how the line count changes.
    singles = doubles = triples = tetrises = 0
    prev_lines = 0
    frames = 0
    died = False
    died_at = None

    # The main loop: advance the game one frame at a time until the
    # game ends or the frame budget runs out.
    while game.status is not Status.GAME_OVER and frames < cap:
        game.update()
        frames += 1
        if game.status is Status.LEVEL_COMPLETE:
            # The end-of-stage celebration would wait for a human to
            # press Enter. Resume it the way the UI's Enter key does,
            # so the game keeps playing. (In the real app the
            # celebration plays out by itself -- spec 5.)
            game.pause()
        if game.lines > prev_lines:
            # The line count jumped: a clear just happened. The size of
            # the jump tells us the clear type.
            cleared = game.lines - prev_lines
            if cleared == 1:
                singles += 1
            elif cleared == 2:
                doubles += 1
            elif cleared == 3:
                triples += 1
            elif cleared == 4:
                tetrises += 1
            prev_lines = game.lines
        if game.status is Status.GAME_OVER and died_at is None:
            # Record the death (once) and the frame it happened on.
            died = True
            died_at = frames

    return {
        "seed": seed,
        "frames": frames,
        "score": game.score,
        "lines": game.lines,
        "level": game.level,
        "pieces": sum(game.stats.as_dict().values()),
        "tetrises": tetrises,
        "triples": triples,
        "singles": singles,
        "doubles": doubles,
        "died": died,
        "died_at": died_at,
        # The survival metric: died with fewer than 3000 lines. 3000
        # lines is roughly level 100, so this counts the runs that died
        # long before a good game would have finished.
        "died_early": bool(died and game.lines < 3000),
        # Score efficiency: how many points the run earned per line.
        "pts_per_line": game.score / game.lines if game.lines else 0.0,
    }


def main() -> None:
    """Command-line entry point.

    USAGE
    -----
        # The full catalogue of variants (long -- several hours).
        uv run python sweep_autopilot.py --seeds 100 --cap 250000

        # Just the variants you care about (much faster).
        uv run python sweep_autopilot.py --seeds 400 --only cur,sh4,sh6

        # Keep the per-run rows for the statistical analysis.
        uv run python sweep_autopilot.py --seeds 400 --only cur,sh4 \
            --out ../stats/sweep.csv

    THE OPTIONS
    -----------
        --seeds N        how many seeds to use (default 100). More seeds
                         means less noise; 400 is the number the spec
                         quotes for the paired measurements.
        --cap N          frame budget per run (default 250,000 = about
                         69 minutes of game time at 60 Hz).
        --master-seed N  the seed the SEED LIST is drawn from (default
                         11111). This makes the whole sweep reproducible.
                         Note this is a different seed space from the
                         one in simulate_autopilot.py (20261028).
        --only A,B,C     run only these variants (names from build_variants).
        --out PATH       write the per-run rows to a CSV, for
                         analyze_frontier.py.
        --workers N      parallel worker processes (default up to 8).
                         Keep it modest on a busy machine -- 4 is a good
                         value for a long unattended sweep.

    THE PARALLELISM
    ----------------
    Variants run one after another, but the SEEDS of one variant run in
    parallel through a process pool. That keeps the machine busy without
    running every variant at once, and it means the per-variant summary
    line is printed as soon as that variant finishes -- so a long sweep
    still shows progress.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=100)
    ap.add_argument("--cap", type=int, default=250_000)
    ap.add_argument("--master-seed", type=int, default=11111)
    ap.add_argument("--only", default=None, help="comma-separated variant names")
    ap.add_argument("--out", default=None, help="write per-run CSV here")
    ap.add_argument(
        "--workers",
        type=int,
        default=min(8, mp.cpu_count()),
        help="parallel workers (keep it modest on a busy machine)",
    )
    args = ap.parse_args()

    # ---- Which variants to run --------------------------------------
    variants = build_variants()
    if args.only:
        # Keep only the named variants. An unknown name simply matches
        # nothing, so check the names against build_variants() if a
        # variant you expected is missing from the output.
        wanted = [s.strip() for s in args.only.split(",")]
        variants = {k: v for k, v in variants.items() if k in wanted}

    # ---- The shared seed list ---------------------------------------
    # Drawn ONCE from the master seed, then used by every variant. This
    # is what makes the comparison paired (see analyze_frontier.py).
    seed_rng = random.Random(args.master_seed)
    seeds = seed_rng.sample(range(1, 2**31 - 1), args.seeds)

    print(f"Sweep: {len(variants)} variants x {args.seeds} seeds, "
          f"budget {args.cap:,} frames each")
    print(f"Seed master {args.master_seed}\n")

    rows: list[dict] = []

    def write_csv() -> None:
        """Write the rows collected so far, so a long sweep stays
        analyzable while it is still running.

        Called after every variant, so the CSV is always complete up to
        the last finished variant -- if a long sweep is interrupted, the
        data so far is still on disk.
        """
        if not args.out or not rows:
            return
        import csv

        with open(args.out, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    # ---- Run every variant ------------------------------------------
    for name, profile in variants.items():
        # One job per seed: (seed, profile, frame budget).
        jobs = [(s, profile, args.cap) for s in seeds]
        results = []
        # A fresh pool per variant: the workers inherit the profile
        # through the job tuple, so no shared state leaks between them.
        with mp.Pool(processes=args.workers) as pool:
            # imap_unordered returns results as they finish, so a slow
            # seed does not hold up the rest.
            for res in pool.imap_unordered(run_one, jobs):
                res["variant"] = name
                results.append(res)
        # Sort by seed so the CSV rows are in a stable, readable order.
        results.sort(key=lambda r: r["seed"])
        rows.extend(results)
        write_csv()

        # ---- The per-variant summary line ---------------------------
        scores = [r["score"] for r in results]
        lines = [r["lines"] for r in results]
        early = sum(r["died_early"] for r in results)
        died = sum(r["died"] for r in results)
        print(f"  {name:<14} score@cap: mean={statistics.mean(scores):>12,.0f} "
              f"median={statistics.median(scores):>11,.0f} | "
              f"lines median={statistics.median(lines):>8,.0f} | "
              f"early deaths={early:>3}/{len(results)} | "
              f"died={died:>3}/{len(results)} | "
              f"pts/line={statistics.mean([r['pts_per_line'] for r in results]):>6.1f} | "
              f"tetrises={statistics.mean([r['tetrises'] for r in results]):>7.1f}",
              flush=True)

    # ---- The final ranking -----------------------------------------
    # Ranking by median score at the budget, with early deaths as the tiebreak.
    print("\n  ranked by median score@cap:")
    by_variant: dict[str, list[dict]] = {}
    for r in rows:
        by_variant.setdefault(r["variant"], []).append(r)
    # Sort by median score (descending), then by FEWER early deaths
    # (the negation makes "fewer" sort higher).
    ranked = sorted(
        by_variant.items(),
        key=lambda kv: (
            statistics.median([r["score"] for r in kv[1]]),
            -sum(r["died_early"] for r in kv[1]),
        ),
        reverse=True,
    )
    for i, (name, res) in enumerate(ranked, 1):
        print(f"    {i}. {name:<14} median score@cap="
              f"{statistics.median([r['score'] for r in res]):>12,.0f}  "
              f"early deaths={sum(r['died_early'] for r in res):>3}")

    if args.out:
        write_csv()
        print(f"\n  CSV written to {args.out}")
        # The next step of the workflow is the statistical analysis of
        # this CSV, which needs the reference variant name:
        #     uv run python analyze_frontier.py <this csv> --ref cur
        # (see the README's "Autopilot sweep" section.)


if __name__ == "__main__":
    sys.exit(main())
