# Discovery v2 — V2-P9 Persona Eval (COLLABORATIVE OFF → ON; controlled A/B; trending live)

_now=2026-06-18T00:00:00+00:00 · collaborative knobs: W_COLLABORATIVE(max)=0.8 SIM_MIN=0.1 CONF_FULL=3.0 MIN_ENDORSERS=2_

BEFORE = collaborative OFF (V2-P8). AFTER = collaborative ON (V2-P9). Same overlay + trending; collaborative is the ONLY change. No-regression = on-taste held, leak=0, exploration unchanged.


**VERDICT: ALL PASS — no on-taste/leak regression; collaborative activated on the population; bubble-escape proven at scale**


## P_NEW — Brand-new account, zero follows (cold-start).
context: mode=cold_start signal=0.0 | collab: confidence=None neighbors=None n_new=None

**AFTER (collaborative ON) feed (top 8):**
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

| metric | BEFORE (collab OFF) | AFTER (collab ON) |
|---|---|---|
| on-taste | None | None |
| median age (days) | -1.0 | -1.0 |
| why variety | 0.3 | 0.3 |
| vertical mix | {'movie': 9, 'tv': 1} | {'movie': 9, 'tv': 1} |
| exploration frac | None | None |
| followed leak | 0 | 0 |

## P_SINGLE_TASTE — 8 simulation/strategy GAME follows (one coherent cozy-builder taste), all recent.
context: mode=personalized signal=0.3123 | collab: confidence=1.0 neighbors=300 n_new=0

**AFTER (collaborative ON) feed (top 8):**
```
   0.350 [movie  ] Bear Country                   | Bear Country Coming Soon     | “Worth a look · movies”
   1.070 [game   ] Garden Story                   | Garden Story Launched on PC  | “Hot right now in Adventure”
   1.012 [game   ] Fall Guys                      | Fall Guys Now Available on X | “Picking up steam in Simulation”
   0.350 [movie  ] The Death of Robin Hood        | The Death of Robin Hood Comi | “Fresh in movies”
   1.007 [game   ] Outpath                        | Outpath Now Available on Nin | “Because you're into Indie”
   0.984 [game   ] Garden of the Sea VR           | Garden of the Sea VR Launche | “Hot right now in Indie”
   0.350 [movie  ] Leviticus                      | Leviticus Coming Soon        | “Worth a look · movies”
   0.979 [game   ] Path of Titans                 | Path of Titans Now Available | “Loved by people with taste like yours”
```

| metric | BEFORE (collab OFF) | AFTER (collab ON) |
|---|---|---|
| on-taste | 0.7 | 0.7 |
| median age (days) | 108.5 | 999.0 |
| why variety | 0.9 | 0.9 |
| vertical mix | {'movie': 3, 'game': 7} | {'movie': 3, 'game': 7} |
| exploration frac | 0.3751 | 0.3751 |
| followed leak | 0 | 0 |

## P_CROSS_VERTICAL — A mix: 2 games + 2 action movies + 2 drama TV + 2 podcasts, all recent.
context: mode=personalized signal=0.3123 | collab: confidence=1.0 neighbors=300 n_new=1

**AFTER (collaborative ON) feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   1.686 [movie  ] Gone in 60 Seconds             | Gone in 60 Seconds Trailer A | “You might not expect it, but people like you love this”
   0.339 [tv     ] The Season                     | The Season Premieres Soon    | “Fresh in TV shows”
   1.336 [tv     ] Trust Me                       | Trust Me Watch Trailer       | “Picking up steam in Thriller”
   1.276 [movie  ] Absolution                     | Absolution Trailer Available | “Fans of your favorites are into this”
   0.307 [tv     ] See You at Work Tomorrow!      | See You at Work Tomorrow! Pr | “Worth a look · TV shows”
   1.261 [movie  ] Night Crossing                 | Night Crossing Watch Trailer | “Big with people who like Drama”
   1.205 [movie  ] The Long Good Friday           | The Long Good Friday Trailer | “Matches your taste in Thriller”
```
**COLLABORATIVE carousel** «People who like Drama are loving these»: ['Anchors Aweigh']
**cross-attribute additions** (bubble-escape — off-genre, neighbor-endorsed): [('Anchors Aweigh', 'movie')]

| metric | BEFORE (collab OFF) | AFTER (collab ON) |
|---|---|---|
| on-taste | 1.0 | 1.0 |
| median age (days) | 16.1 | 16.1 |
| why variety | 0.7 | 0.8 |
| vertical mix | {'tv': 4, 'movie': 6} | {'tv': 5, 'movie': 5} |
| exploration frac | 0.3751 | 0.3751 |
| followed leak | 0 | 0 |

## P_DRIFTING — OLDER comedy (4 follows, 35d ago) + RECENT horror (4 follows, 2d ago) — taste is drifting to horror.
context: mode=personalized signal=0.2165 | collab: confidence=1.0 neighbors=300 n_new=6

**AFTER (collaborative ON) feed (top 8):**
```
   0.339 [game   ] EA Sports UFC 6                | EA Sports UFC 6 Unveiled on  | “New games”
   1.722 [movie  ] They Wait                      | They Wait Trailer Available  | “Fans of your favorites are into this”
   1.654 [movie  ] I Still Know What You Did Last | I Still Know What You Did La | “Big with people who like Horror”
   1.539 [movie  ] Night of the Living Dead       | Night of the Living Dead Tra | “Fans of your favorites are into this”
   1.507 [movie  ] Chained                        | Chained Watch Trailer        | “Fans of your favorites are into this”
   1.501 [movie  ] My Son, My Son, What Have Ye D | My Son, My Son, What Have Ye | “You might not expect it, but people like you love this”
   1.499 [movie  ] Brimstone & Treacle            | Brimstone & Treacle Trailer  | “Loved by people with taste like yours”
   0.283 [game   ] Hogwarts Legacy                | Hogwarts Legacy DLC          | “Worth a look · games”
```
**COLLABORATIVE carousel** «People who like Horror are loving these»: ['Songs of Conquest', 'Heart of Dating', 'Rocket League', 'Gone in 60 Seconds', 'Immortal Combat']
**cross-attribute additions** (bubble-escape — off-genre, neighbor-endorsed): [('Songs of Conquest', 'game'), ('Heart of Dating', 'podcast'), ('Rocket League', 'game'), ('Gone in 60 Seconds', 'movie'), ('Immortal Combat', 'movie')]

| metric | BEFORE (collab OFF) | AFTER (collab ON) |
|---|---|---|
| on-taste | 0.7 | 0.8 |
| median age (days) | 16.1 | 16.1 |
| why variety | 1.0 | 0.7 |
| vertical mix | {'game': 2, 'movie': 7, 'tv': 1} | {'game': 2, 'movie': 8} |
| exploration frac | 0.4134 | 0.4134 |
| followed leak | 0 | 0 |

## P_SPARSE — Only 3 simulation game follows (thin signal → should explore more).
context: mode=personalized signal=0.1171 | collab: confidence=1.0 neighbors=300 n_new=7

**AFTER (collaborative ON) feed (top 8):**
```
   0.350 [movie  ] Bear Country                   | Bear Country Coming Soon     | “Worth a look · movies”
   1.080 [game   ] Circuit Superstars             | Circuit Superstars Launched  | “Trending in Simulation”
   0.350 [movie  ] The Death of Robin Hood        | The Death of Robin Hood Comi | “Fresh in movies”
   0.850 [game   ] Per Aspera                     | Per Aspera Launched on PC (M | “Trending in Simulation”
   0.848 [game   ] Rocket League                  | Rocket League Launched on Xb | “Hot right now in Indie”
   0.350 [movie  ] Leviticus                      | Leviticus Coming Soon        | “Worth a look · movies”
   0.750 [game   ] Wobbly Life                    | Wobbly Life Now Available on | “Matches your taste in Role-Playing”
   0.695 [game   ] FutureGrind                    | FutureGrind Launched on Nint | “Because you follow Garden Story”
```
**COLLABORATIVE carousel** «People who like Indie are loving these»: ['Inazuma Eleven: Victory Road', 'Nowhere to Run', 'Hollow Knight', 'Need for Speed: Hot Pursuit', 'Night of the Living Dead']
**cross-attribute additions** (bubble-escape — off-genre, neighbor-endorsed): [('Inazuma Eleven: Victory Road', 'game'), ('Nowhere to Run', 'movie'), ('Hollow Knight', 'game'), ('Night of the Living Dead', 'movie'), ('Vampires of the Velvet Lounge', 'movie')]

| metric | BEFORE (collab OFF) | AFTER (collab ON) |
|---|---|---|
| on-taste | 0.4 | 0.6 |
| median age (days) | 122.0 | 617.0 |
| why variety | 0.6 | 0.7 |
| vertical mix | {'movie': 4, 'game': 6} | {'movie': 4, 'game': 6} |
| exploration frac | 0.4532 | 0.4532 |
| followed leak | 0 | 0 |

## P_REACTOR — 3 horror-movie follows + 4 reactions on horror moments (reactions add signal).
context: mode=personalized signal=0.3042 | collab: confidence=1.0 neighbors=300 n_new=7

**AFTER (collaborative ON) feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   2.102 [movie  ] Emelie                         | Emelie Trailer Available     | “Trending in Thriller”
   1.644 [movie  ] A Return to Salem's Lot        | A Return to Salem's Lot Trai | “Picking up steam in Comedy”
   0.339 [game   ] EA Sports UFC 6                | EA Sports UFC 6 Unveiled on  | “New games”
   1.346 [movie  ] Chained                        | Chained Watch Trailer        | “Like I Still Know What You Did Last Summer, but new to you”
   1.324 [movie  ] Vampires of the Velvet Lounge  | Vampires of the Velvet Loung | “Trending in Comedy”
   0.339 [tv     ] The Season                     | The Season Premieres Soon    | “Fresh in TV shows”
   1.205 [movie  ] Insidious                      | Insidious Trailer Available  | “Because you follow I Still Know What You Did Last Summer”
```
**COLLABORATIVE carousel** «People who like Horror are loving these»: ['Songs of Conquest', 'Heart of Dating', 'Rocket League', 'Immortal Combat', 'FutureGrind']
**cross-attribute additions** (bubble-escape — off-genre, neighbor-endorsed): [('Songs of Conquest', 'game'), ('Heart of Dating', 'podcast'), ('Rocket League', 'game'), ('Immortal Combat', 'movie'), ('FutureGrind', 'game')]

| metric | BEFORE (collab OFF) | AFTER (collab ON) |
|---|---|---|
| on-taste | 0.6 | 0.7 |
| median age (days) | 16.1 | 16.1 |
| why variety | 0.9 | 0.9 |
| vertical mix | {'tv': 2, 'movie': 7, 'game': 1} | {'tv': 2, 'movie': 7, 'game': 1} |
| exploration frac | 0.3783 | 0.3783 |
| followed leak | 0 | 0 |


## NO-REGRESSION summary (collaborative OFF → ON)

| persona | on-taste OFF→ON | leak | expl OFF→ON | collab conf | n_new | cross-attr |
|---|---|---|---|---|---|---|
| P_NEW | None→None | 0 | None→None | None | None | 0 |
| P_SINGLE_TASTE | 0.7→0.7 | 0 | 0.3751→0.3751 | 1.0 | 0 | 0 |
| P_CROSS_VERTICAL | 1.0→1.0 | 0 | 0.3751→0.3751 | 1.0 | 1 | 1 |
| P_DRIFTING | 0.7→0.8 | 0 | 0.4134→0.4134 | 1.0 | 6 | 6 |
| P_SPARSE | 0.4→0.6 | 0 | 0.4532→0.4532 | 1.0 | 7 | 6 |
| P_REACTOR | 0.6→0.7 | 0 | 0.3783→0.3783 | 1.0 | 7 | 7 |


## BUBBLE-ESCAPE at scale (dedicated horror cohort + cross-attribute game)

- Cohort: 9 horror users follow ['Vampires of the Velvet Lounge', "A Return to Salem's Lot", 'Osombie']…; 7 ALSO follow the cross-attribute game **Songs of Conquest** (genres=['Strategy', 'Role-Playing', 'Adventure']).
- Target (horror user 990010) follows the movies, NOT the game. collab confidence=1.0, neighbors=300.
- **collab OFF:** game present = False  ·  **collab ON:** game present = True  →  PASS — surfaced via collaborative only (content/trending can never reach a horror→strategy link)
- collaborative carousel «People who like Horror are loving these»: ['Songs of Conquest', 'Gone in 60 Seconds', 'Immortal Combat']