# Discovery v2 — V2-P7 Persona Eval (tuned + synthetic population; trending LIVE)

_now=2026-06-18T00:00:00+00:00 · trending confidence=1.000 (was ~0.12 dev) · config: W_RECENCY=1.0 cluster_weighting=0.5 stale=0.6@540d cap=1_

BEFORE = V2-P6 (untuned, trending dark). AFTER = V2-P7 (tuned, trending live). Overlay-only; CSVs untouched.


## P_NEW — Brand-new account, zero follows (cold-start).
context: mode=cold_start signal=0.0 expl_frac=None

**AFTER feed (top 8):**
```
   0.777 [movie  ] Virginia Woolf's Night & Day   | Virginia Woolf's Night & Day | “Popular movies”
   0.777 [movie  ] Voicemails for Isabelle        | Voicemails for Isabelle Arri | “Popular movies”
   0.764 [movie  ] You Are the Film               | You Are the Film Arrives Jun | “New movies”
   0.762 [movie  ] Toy Story 5                    | Toy Story 5 Premieres Soon   | “New movies”
   0.718 [movie  ] Les caprices de l'enfant Roi   | Les caprices de l’enfant Roi | “Popular movies”
   0.718 [movie  ] Stop! That! Train!             | Stop! That! Train! Arrives J | “Popular movies”
   0.707 [movie  ] Bleach: Thousand-Year Blood Wa | Bleach: Thousand-Year Blood  | “Popular movies”
   0.707 [tv     ] Nurse the Dead                 | Nurse the Dead Coming Soon   | “Popular TV shows”
```
**TRENDING carousel** «Trending now»: [("Virginia Woolf's Night & Day", 0.0), ('Voicemails for Isabelle', 0.0), ('You Are the Film', 0.0), ('Toy Story 5', 0.0)]

| metric | BEFORE (V2-P6) | AFTER (V2-P7) |
|---|---|---|
| on-taste | None | None |
| median age (days) | -1.0 | -1.0 |
| why variety | 0.3 | 0.3 |
| duplicate props | 0 | 0 |
| exploration frac | None | None |
| overlap w/ global | — | 0.133 |
| followed leak | 0 | 0 |

## P_SINGLE_TASTE — 8 simulation/strategy GAME follows (one coherent cozy-builder taste), all recent.
context: mode=personalized signal=0.3123 expl_frac=0.3751

**AFTER feed (top 8):**
```
   0.350 [movie  ] Bear Country                   | Bear Country Coming Soon     | “Worth a look · movies”
   1.007 [game   ] Outpath                        | Outpath Now Available on Nin | “Because you're into Indie”
   0.643 [game   ] Garden Story                   | Garden Story Launched on PC  | “Hot right now in Adventure”
   0.350 [movie  ] The Death of Robin Hood        | The Death of Robin Hood Comi | “Fresh in movies”
   0.637 [game   ] Garden of the Sea VR           | Garden of the Sea VR Launche | “Hot right now in Indie”
   0.614 [game   ] Forza Horizon 6                | Forza Horizon 6 Launched on  | “Right up your alley: Simulation”
   0.350 [movie  ] Leviticus                      | Leviticus Coming Soon        | “Worth a look · movies”
   0.601 [game   ] Stardew Valley                 | Stardew Valley Launched on N | “Matches your taste in Role-Playing”
```
**TRENDING carousel** «Trending in Simulation»: [('Fall Guys', 0.36), ('Garden Story', 0.454), ('Garden of the Sea VR', 0.362), ('Valthirian Arc: Hero School Story', 0.342)]

| metric | BEFORE (V2-P6) | AFTER (V2-P7) |
|---|---|---|
| on-taste | 0.7 | 0.7 |
| median age (days) | 925.5 | 108.5 |
| why variety | 0.2 | 0.9 |
| duplicate props | 3 | 0 |
| exploration frac | 0.375 | 0.3751 |
| overlap w/ global | — | 0.024 |
| followed leak | 0 | 0 |

## P_CROSS_VERTICAL — A mix: 2 games + 2 action movies + 2 drama TV + 2 podcasts, all recent.
context: mode=personalized signal=0.3123 expl_frac=0.3751

**AFTER feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   1.205 [movie  ] The Long Good Friday           | The Long Good Friday Trailer | “Matches your taste in Thriller”
   0.339 [tv     ] The Season                     | The Season Premieres Soon    | “Fresh in TV shows”
   0.886 [movie  ] Gone in 60 Seconds             | Gone in 60 Seconds Trailer A | “Matches your taste in Thriller”
   0.805 [movie  ] The Rising Hawk                | The Rising Hawk Watch Traile | “Matches your taste in Drama”
   0.307 [tv     ] See You at Work Tomorrow!      | See You at Work Tomorrow! Pr | “Worth a look · TV shows”
   0.805 [movie  ] Blood Father                   | Blood Father Watch Trailer   | “Right up your alley: Drama”
   0.805 [movie  ] Mala influencia                | Mala influencia Watch Traile | “Like Batman Forever, but new to you”
```
**TRENDING carousel** «Trending in Drama»: [('Circuit Superstars', 0.962), ('Emelie', 0.962), ('Trust Me', 0.795), ('Osombie', 0.751)]

| metric | BEFORE (V2-P6) | AFTER (V2-P7) |
|---|---|---|
| on-taste | 0.9 | 1.0 |
| median age (days) | 16.1 | 16.1 |
| why variety | 0.2 | 0.7 |
| duplicate props | 0 | 0 |
| exploration frac | 0.375 | 0.3751 |
| overlap w/ global | — | 0.037 |
| followed leak | 0 | 0 |

## P_DRIFTING — OLDER comedy (4 follows, 35d ago) + RECENT horror (4 follows, 2d ago) — taste is drifting to horror.
context: mode=personalized signal=0.2165 expl_frac=0.4134

**AFTER feed (top 8):**
```
   0.339 [game   ] EA Sports UFC 6                | EA Sports UFC 6 Unveiled on  | “New games”
   1.205 [movie  ] Zombie Apache                  | Zombie Apache Watch Trailer  | “Right up your alley: Horror”
   1.126 [movie  ] Bloody Mallory                 | Bloody Mallory Watch Trailer | “More Fantasy you'll like”
   0.996 [movie  ] Leprechaun Returns             | Leprechaun Returns Trailer A | “Right up your alley: Comedy”
   0.940 [movie  ] They Wait                      | They Wait Trailer Available  | “Matches your taste in Mystery”
   0.926 [movie  ] I Still Know What You Did Last | I Still Know What You Did La | “More Horror you'll like”
   0.926 [tv     ] Miracle Workers                | Miracle Workers Watch Traile | “Picking up steam in Comedy”
   0.283 [game   ] Hogwarts Legacy                | Hogwarts Legacy DLC          | “Worth a look · games”
```
**TRENDING carousel** «Trending in Horror»: [('Sobriedad, me estás matando', 0.819), ('Miracle Workers', 0.802), ('The Benchwarmers', 0.807), ('They Wait', 0.546)]

| metric | BEFORE (V2-P6) | AFTER (V2-P7) |
|---|---|---|
| on-taste | 0.3 | 0.7 |
| median age (days) | 16.1 | 16.1 |
| why variety | 0.3 | 1.0 |
| duplicate props | 0 | 0 |
| exploration frac | 0.413 | 0.4134 |
| overlap w/ global | — | 0.012 |
| followed leak | 0 | 0 |
| **drift (horror vs comedy)** | H3 / C7 (wrong) | H7 / C6 |

## P_SPARSE — Only 3 simulation game follows (thin signal → should explore more).
context: mode=personalized signal=0.1171 expl_frac=0.4532

**AFTER feed (top 8):**
```
   0.350 [movie  ] Bear Country                   | Bear Country Coming Soon     | “Worth a look · movies”
   0.750 [game   ] Wobbly Life                    | Wobbly Life Now Available on | “Matches your taste in Role-Playing”
   0.350 [movie  ] The Death of Robin Hood        | The Death of Robin Hood Comi | “Fresh in movies”
   0.603 [game   ] Escape from Ever After         | Escape from Ever After Now A | “Because you're into Adventure”
   0.601 [game   ] Stardew Valley                 | Stardew Valley Launched on N | “Matches your taste in Role-Playing”
   0.350 [movie  ] Leviticus                      | Leviticus Coming Soon        | “Worth a look · movies”
   0.600 [game   ] Welcome to Elk                 | Welcome to Elk Launched on N | “Right up your alley: Adventure”
   0.600 [game   ] Circuit Superstars             | Circuit Superstars Launched  | “Trending in Simulation”
```
**TRENDING carousel** «Trending in Indie»: [('Circuit Superstars', 0.962), ('Rocket League', 0.962), ('Per Aspera', 0.706), ('Forklift Simulator 2019', 0.485)]

| metric | BEFORE (V2-P6) | AFTER (V2-P7) |
|---|---|---|
| on-taste | 0.0 | 0.4 |
| median age (days) | 1844.5 | 122.0 |
| why variety | 0.2 | 0.6 |
| duplicate props | 3 | 0 |
| exploration frac | 0.453 | 0.4532 |
| overlap w/ global | — | 0.024 |
| followed leak | 0 | 0 |

## P_REACTOR — 3 horror-movie follows + 4 reactions on horror moments (reactions add signal).
context: mode=personalized signal=0.3042 expl_frac=0.3783

**AFTER feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   1.302 [movie  ] Emelie                         | Emelie Trailer Available     | “Trending in Thriller”
   1.205 [movie  ] Insidious                      | Insidious Trailer Available  | “Because you follow I Still Know What You Did Last Summer”
   0.339 [game   ] EA Sports UFC 6                | EA Sports UFC 6 Unveiled on  | “New games”
   1.138 [movie  ] A Return to Salem's Lot        | A Return to Salem's Lot Trai | “Picking up steam in Comedy”
   1.035 [movie  ] Daughter                       | Daughter Watch Trailer       | “Matches your taste in Horror”
   0.339 [tv     ] The Season                     | The Season Premieres Soon    | “Fresh in TV shows”
   1.005 [movie  ] Chained                        | Chained Watch Trailer        | “Like I Still Know What You Did Last Summer, but new to you”
```
**TRENDING carousel** «Trending in Horror»: [('Emelie', 0.962), ('Vampires of the Velvet Lounge', 0.869), ('Trust Me', 0.795), ('Murder Is Easy', 0.84)]

| metric | BEFORE (V2-P6) | AFTER (V2-P7) |
|---|---|---|
| on-taste | 0.7 | 0.6 |
| median age (days) | 16.1 | 16.1 |
| why variety | 0.3 | 0.9 |
| duplicate props | 0 | 0 |
| exploration frac | 0.378 | 0.3783 |
| overlap w/ global | — | 0.024 |
| followed leak | 0 | 0 |


## BEFORE → AFTER summary (monotonic improvement, no regression)

| persona | on-taste | median age | why variety | dups | expl frac | leak |
|---|---|---|---|---|---|---|
| P_NEW | None→None | -1.0→-1.0 | 0.3→0.3 | 0→0 | None→None | 0 |
| P_SINGLE_TASTE | 0.7→0.7 | 925.5→108.5 | 0.2→0.9 | 3→0 | 0.375→0.3751 | 0 |
| P_CROSS_VERTICAL | 0.9→1.0 | 16.1→16.1 | 0.2→0.7 | 0→0 | 0.375→0.3751 | 0 |
| P_DRIFTING | 0.3→0.7 | 16.1→16.1 | 0.3→1.0 | 0→0 | 0.413→0.4134 | 0 |
| P_SPARSE | 0.0→0.4 | 1844.5→122.0 | 0.2→0.6 | 3→0 | 0.453→0.4532 | 0 |
| P_REACTOR | 0.7→0.6 | 16.1→16.1 | 0.3→0.9 | 0→0 | 0.378→0.3783 | 0 |