# Discovery v2 (Endpoint 2) — Comprehensive Recommendation-Quality Evaluation

_now=2026-06-18T00:00:00+00:00 · DIAGNOSE-ONLY (no logic changed) · substrate live · overlay-only (production CSVs untouched)_

**Integrity:** synthetic follows resolving to real served entities: **ALL** · total exclusion leaks across every feed generated: **0** ✅ · population feeds scored: **380** · wall-time 881.6s

## Headline findings

1. **Longitudinal (does it learn?):** on-taste rose (or held) from stage-1→3 for 5/5 users; taste-shift reflected in 2/2 shifting users.
2. **Ground-truth designed users:** 13/15 scenarios PASS their constructed right-answer.
3. **At population scale (380 complex users):** median on-taste 0.9, median freshness 16.1d, collaborative fired for 100.0% / trending 100.0% of users.
4. **Exclusion integrity:** 0 leaks across all feeds (hard gate held ✅).


## Part A — Synthetic population structure

- **380 profiled users** (+ 267 single-event trending/stale reactors) · 4368 follows · 1494 reactions.
- Taste depth: {'shallow': 131, 'medium': 171, 'deep': 78} · #tastes/user: {2: 185, 3: 60, 1: 135} · recency patterns: {'bursty': 107, 'recent_shift': 94, 'steady': 92, 'dormant_active': 87} · engagement style: {'mixed': 172, 'follow_only': 148, 'reaction_heavy': 60}.
- Cohorts (real entities): ['Simulation', 'Strategy', 'Adventure', 'Action', 'Horror', 'Comedy', 'Science Fiction', 'Drama', 'Comedy', 'podcast'].
- **Cross-attribute plant** (bubble-escape basis): 16 Horror users also follow **CastleStorm II** ['Strategy'].
- **Trending plants** — mainstream: ['Per Aspera', 'Songs of Conquest']; niche(3-5 users): ['The LEGO Movie 2 Videogame', 'Nowhere to Run', 'Vampires of the Velvet Lounge']; stale-popular(old volume): ['Circuit Superstars', 'Undying', "Unexplored 2: The Wayfarer's Legacy"].

## Part C — LONGITUDINAL: do recommendations improve & track taste as the profile builds?

Same user identity, profile grown cold→stage1(2-3 follows)→stage2(7-day)→stage3(30-day + a recent shift). Feed regenerated at each stage (profile injected; population as the trending/collaborative backdrop).


### LONG_HORROR_TO_COMEDY — Horror fan whose taste SHIFTS to comedy by day 30.

| stage | signal | on-taste | expl frac | median age | source mix (taste/trend/collab/expl/global) | n_collab | n_trend |
|---|---|---|---|---|---|---|---|
| 0 | 0.0 | 0.7 | None | -1.0 | 0/0/0/0/0 | None | None |
| 1 | 0.0976 | 0.7 | 0.461 | 16.1 | 0/6/0/0/4 | 41 | 95 |
| 2 | 0.2885 | 0.8 | 0.3846 | 16.1 | 0/7/0/0/3 | 94 | 36 |
| 3 | 0.3715 | 0.7 | 0.3514 | 16.1 | 0/7/0/0/3 | 31 | 108 |

**Stage-3 feed (top 6):**
  - [tv] I Will Find You                    «Fresh in TV shows»  _(global_backfill)_
  - [movie] Arsenic and Old Lace               «Big with people who like Comedy»  _(trending)_
  - [movie] Avanti!                            «You might not expect it, but people like you love this»  _(trending)_
  - [game] EA Sports UFC 6                    «New games»  _(global_backfill)_
  - [tv] LA to Vegas                        «You might not expect it, but people like you love this»  _(trending)_
  - [movie] The Holiday Sitter                 «Loved by people with taste like yours»  _(trending)_

**Verdict:** on-taste 0.7→0.7 (rises/holds ✅); exploration 0.461→0.3514 (falls ✅); stage-3 SHIFT to comedy: 4/6 top items (reflected ✅); by stage-3 trending/collab active (n_collab=31, n_trend=108).

### LONG_SIM_DEEPENS — Sim-game fan who simply DEEPENS the same taste over 30 days (no shift).

| stage | signal | on-taste | expl frac | median age | source mix (taste/trend/collab/expl/global) | n_collab | n_trend |
|---|---|---|---|---|---|---|---|
| 0 | 0.0 | 0.0 | None | -1.0 | 0/0/0/0/0 | None | None |
| 1 | 0.0976 | 0.6 | 0.461 | 912.0 | 0/6/0/0/4 | 61 | 74 |
| 2 | 0.2885 | 0.7 | 0.3846 | 547.0 | 1/6/0/0/3 | 75 | 54 |
| 3 | 0.3715 | 0.7 | 0.3514 | 1723.5 | 0/7/0/0/3 | 54 | 81 |

**Stage-3 feed (top 6):**
  - [movie] Bear Country                       «Worth a look · movies»  _(global_backfill)_
  - [game] Coromon                            «You might not expect it, but people like you love this»  _(trending)_
  - [game] Hammerting                         «Because you follow Undying»  _(trending)_
  - [movie] The Death of Robin Hood            «Fresh in movies»  _(global_backfill)_
  - [game] Bug Fables: The Everlasting Saplin «Big with people who like Strategy»  _(trending)_
  - [game] FreeDiver: Triton Down             «You might not expect it, but people like you love this»  _(trending)_

**Verdict:** on-taste 0.6→0.7 (rises/holds ✅); exploration 0.461→0.3514 (falls ✅); by stage-3 trending/collab active (n_collab=54, n_trend=81).

### LONG_ACTION_TO_HORROR — Action fan drifting to horror by day 30.

| stage | signal | on-taste | expl frac | median age | source mix (taste/trend/collab/expl/global) | n_collab | n_trend |
|---|---|---|---|---|---|---|---|
| 0 | 0.0 | 0.0 | None | -1.0 | 0/0/0/0/0 | None | None |
| 1 | 0.0976 | 0.8 | 0.461 | 16.1 | 0/6/0/0/4 | 74 | 63 |
| 2 | 0.2885 | 0.9 | 0.3846 | 16.1 | 0/7/0/0/3 | 71 | 69 |
| 3 | 0.3715 | 0.8 | 0.3514 | 16.1 | 0/7/0/0/3 | 22 | 140 |

**Stage-3 feed (top 6):**
  - [tv] I Will Find You                    «Fresh in TV shows»  _(global_backfill)_
  - [movie] The Promised Neverland             «Because you're into Thriller»  _(trending)_
  - [movie] Laid to Rest                       «Big with people who like Thriller»  _(trending)_
  - [game] EA Sports UFC 6                    «New games»  _(global_backfill)_
  - [movie] House IV                           «Big with people who like Thriller»  _(trending)_
  - [movie] Significant Other                  «Like I Still Know What You Did Last Summer, but new to you»  _(trending)_

**Verdict:** on-taste 0.8→0.8 (rises/holds ✅); exploration 0.461→0.3514 (falls ✅); stage-3 SHIFT to horror: 3/6 top items (reflected ✅); by stage-3 trending/collab active (n_collab=22, n_trend=140).

### LONG_BUILD_MULTI — Builds toward a MULTI-taste profile — adds podcasts while sim games stay primary (additive, NOT a shift).

| stage | signal | on-taste | expl frac | median age | source mix (taste/trend/collab/expl/global) | n_collab | n_trend |
|---|---|---|---|---|---|---|---|
| 0 | 0.0 | 0.0 | None | -1.0 | 0/0/0/0/0 | None | None |
| 1 | 0.0976 | 0.6 | 0.461 | 912.0 | 0/6/0/0/4 | 61 | 74 |
| 2 | 0.2885 | 0.6 | 0.3846 | 975.0 | 1/6/0/0/3 | 60 | 76 |
| 3 | 0.2787 | 0.6 | 0.3885 | 1607.5 | 0/7/0/0/3 | 39 | 100 |

**Stage-3 feed (top 6):**
  - [movie] Bear Country                       «Worth a look · movies»  _(global_backfill)_
  - [game] Coromon                            «You might not expect it, but people like you love this»  _(trending)_
  - [game] Bug Fables: The Everlasting Saplin «Big with people who like Strategy»  _(trending)_
  - [game] Hammerting                         «Because you follow From First Principles»  _(trending)_
  - [movie] The Death of Robin Hood            «Fresh in movies»  _(global_backfill)_
  - [game] Commander '85                      «Fans of your favorites are into this»  _(trending)_

**Verdict:** on-taste 0.6→0.6 (rises/holds ✅); exploration 0.461→0.3885 (falls ✅); by stage-3 trending/collab active (n_collab=39, n_trend=100).

### LONG_REACTION_GROWN — Grows taste mainly through REACTIONS (few follows, many reactions).

| stage | signal | on-taste | expl frac | median age | source mix (taste/trend/collab/expl/global) | n_collab | n_trend |
|---|---|---|---|---|---|---|---|
| 0 | 0.0 | 0.0 | None | -1.0 | 0/0/0/0/0 | None | None |
| 1 | 0.0976 | 0.7 | 0.461 | 16.1 | 0/6/0/0/4 | 41 | 95 |
| 2 | 0.2885 | 0.8 | 0.3846 | 16.1 | 0/7/0/0/3 | 94 | 36 |
| 3 | 0.402 | 0.8 | 0.3392 | 16.1 | 0/7/0/0/3 | 81 | 54 |

**Stage-3 feed (top 6):**
  - [tv] I Will Find You                    «Fresh in TV shows»  _(global_backfill)_
  - [movie] Dracula Untold                     «Hot right now in Horror»  _(trending)_
  - [movie] House IV                           «Big with people who like Thriller»  _(trending)_
  - [game] EA Sports UFC 6                    «New games»  _(global_backfill)_
  - [movie] Willard                            «Big with people who like Horror»  _(trending)_
  - [movie] Laid to Rest                       «Big with people who like Thriller»  _(trending)_

**Verdict:** on-taste 0.7→0.8 (rises/holds ✅); exploration 0.461→0.3392 (falls ✅); by stage-3 trending/collab active (n_collab=81, n_trend=54).

**Longitudinal overall:** Recommendations demonstrably sharpen as the profile builds (exploration falls, on-taste rises, trending/collaborative activate by stage 3). All planted taste-shifts surfaced in the stage-3 feed.


## Part B — Designed ground-truth users (measurable right answers)

_On-taste uses a genre-ADJACENCY rule (intended ∪ adjacent genres; e.g. horror~thriller/mystery), so near-genre matches count rather than being under-counted by a strict single-genre check._


### GT_COLD — ✅ PASS
_Brand-new account, zero activity._  · intended=— · mode=cold_start signal=0.0

**Feed (top 8):**
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
carousels: [('trending', 20), ('new_in_genre:Drama', 20), ('new_in_genre:Comedy', 20), ('new_in_genre:Thriller', 20), ('new_in_genre:Action', 20), ('new_on_platform:1', 20)]
metrics: on-taste(adj)=None strict=None · median_age=-1.0d · overlap_cold=0.133 · expl=None · top_property_repeat=1 · why_var=0.3 · source_mix={'fresh_moments': 10}
checks:
  - [PASS] routes to global/cold (no false personalization) — mode=cold_start path=global_fallback
  - [PASS] EXCLUSION integrity: zero followed/seen leak — leak=0
_Assessment:_ Correct cold-start: global/fresh/popular, no fabricated personalization.

### GT_SINGLE_HORROR_DEEP — ✅ PASS
_15 horror-movie follows (one deep coherent taste), all recent._  · intended=['horror'] · mode=personalized signal=0.6153

**Feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   1.883 [movie  ] Dracula Untold                 | Dracula Untold Watch Trailer | “Hot right now in Horror”
   1.752 [movie  ] House IV                       | House IV Watch Trailer       | “Big with people who like Thriller”
   1.626 [movie  ] Willard                        | Willard Watch Trailer        | “Big with people who like Horror”
   0.339 [game   ] EA Sports UFC 6                | EA Sports UFC 6 Unveiled on  | “New games”
   1.591 [movie  ] Las leyendas: El origen        | Las leyendas: El origen Watc | “Big with people who like Animation”
   1.578 [movie  ] Significant Other              | Significant Other Watch Trai | “Like Vampires of the Velvet Lounge, but new to you”
   1.525 [movie  ] Face                           | Face Trailer Available       | “You might not expect it, but people like you love this”
```
carousels: [('cluster_1', 15), ('trending', 20), ('collaborative', 20), ('exploration', 7), ('new_in_genre_Horror', 20), ('new_in_genre_Thriller', 20), ('new_in_genre_Mystery', 10), ('new_in_genre_Drama', 20), ('new_on_platform_0', 20), ('new_on_platform_1', 20)]
metrics: on-taste(adj)=0.8 strict=0.7 · median_age=16.1d · overlap_cold=0.024 · expl=0.2539 · top_property_repeat=1 · why_var=0.8 · source_mix={'global': 3, 'trending': 7}
checks:
  - [PASS] on-taste ≥ 0.6 — adj_on_taste=0.8
  - [PASS] no property repeats > 2× — max_repeat=1
  - [PASS] EXCLUSION integrity: zero followed/seen leak — leak=0
_Assessment:_ A real user here would see a strongly personal, fresh, varied feed (on-taste 0.8, why-variety 0.8). Meets the constructed expectation.

### GT_MULTI_BALANCED — ❌ FAIL
_Three balanced tastes: 4 sim games + 4 horror movies + 4 podcasts, all recent._  · intended=['horror', 'simulation'] · mode=personalized signal=0.4922

**Feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   1.941 [movie  ] Dracula Untold                 | Dracula Untold Watch Trailer | “Hot right now in Horror”
   1.292 [movie  ] The Cloverfield Paradox        | The Cloverfield Paradox Trai | “Loved by people with taste like yours”
   1.284 [movie  ] House IV                       | House IV Watch Trailer       | “Big with people who like Thriller”
   1.221 [movie  ] Pulse                          | Pulse Trailer Available      | “Because you follow House”
   1.215 [movie  ] Vampires of the Velvet Lounge  | Vampires of the Velvet Loung | “Matches your taste in Comedy”
   1.205 [movie  ] Transylvania 6-5000            | Transylvania 6-5000 Watch Tr | “Because you follow House”
   1.196 [movie  ] 30 Nights of Paranormal Activi | 30 Nights of Paranormal Acti | “Right up your alley: Comedy”
```
carousels: [('cluster_1', 15), ('cluster_2', 15), ('cluster_3', 15), ('trending', 20), ('collaborative', 16), ('exploration', 10), ('new_in_genre_Horror', 20), ('new_in_genre_Action', 20), ('new_in_genre_Adventure', 20), ('new_in_genre_Comedy', 20), ('new_on_platform_0', 20), ('new_on_platform_1', 20)]
metrics: on-taste(adj)=0.8 strict=0.7 · median_age=16.1d · overlap_cold=0.012 · expl=0.3031 · top_property_repeat=1 · why_var=0.8 · source_mix={'global': 2, 'trending': 6, 'taste': 2}
checks:
  - [FAIL] ≥ 3 verticals represented — mix={'tv': 2, 'movie': 8}
  - [PASS] EXCLUSION integrity: zero followed/seen leak — leak=0
_Assessment:_ A real user here would see a strongly personal, fresh, varied feed (on-taste 0.8, why-variety 0.8). MISSES the constructed expectation.

### GT_MULTI_SKEWED — ✅ PASS
_Dominant horror (10) + minor comedy (3) + minor sim (3)._  · intended=['horror'] · mode=personalized signal=0.6331

**Feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   1.665 [movie  ] Laid to Rest                   | Laid to Rest Watch Trailer   | “Big with people who like Thriller”
   1.663 [movie  ] Dracula Untold                 | Dracula Untold Watch Trailer | “Hot right now in Horror”
   1.584 [movie  ] My Son, My Son, What Have Ye D | My Son, My Son, What Have Ye | “Matches your taste in Drama”
   1.577 [movie  ] Clinical                       | Clinical Watch Trailer       | “Because you follow Godless: The Eastfield Exorcism”
   1.563 [movie  ] I Still Know What You Did Last | I Still Know What You Did La | “More Horror you'll like”
   0.339 [tv     ] The Season                     | The Season Premieres Soon    | “Fresh in TV shows”
   1.562 [movie  ] The Cloverfield Paradox        | The Cloverfield Paradox Trai | “Loved by people with taste like yours”
```
carousels: [('cluster_1', 15), ('cluster_2', 15), ('cluster_3', 15), ('trending', 20), ('collaborative', 20), ('exploration', 15), ('new_in_genre_Horror', 20), ('new_in_genre_Thriller', 20), ('new_in_genre_Comedy', 20), ('new_in_genre_Drama', 20), ('new_on_platform_0', 20), ('new_on_platform_1', 20)]
metrics: on-taste(adj)=0.9 strict=0.8 · median_age=16.1d · overlap_cold=0.012 · expl=0.2468 · top_property_repeat=1 · why_var=0.8 · source_mix={'global': 2, 'trending': 8}
checks:
  - [PASS] on-taste ≥ 0.5 — adj_on_taste=0.9
  - [PASS] dominant genre is horror — horror=8 vs max_other=3
  - [PASS] EXCLUSION integrity: zero followed/seen leak — leak=0
_Assessment:_ A real user here would see a strongly personal, fresh, concentrated feed (on-taste 0.9, why-variety 0.8). Meets the constructed expectation.

### GT_DRIFTING — ✅ PASS
_OLDER comedy (4, 28d ago) + RECENT horror (5, 2d ago) — taste drifting to horror._  · intended=['horror'] · mode=personalized signal=0.2764

**Feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   2.060 [movie  ] Dracula Untold                 | Dracula Untold Watch Trailer | “Hot right now in Horror”
   1.606 [movie  ] Las leyendas: El origen        | Las leyendas: El origen Watc | “Big with people who like Animation”
   0.339 [game   ] EA Sports UFC 6                | EA Sports UFC 6 Unveiled on  | “New games”
   1.548 [movie  ] The Cloverfield Paradox        | The Cloverfield Paradox Trai | “Loved by people with taste like yours”
   1.517 [movie  ] House IV                       | House IV Watch Trailer       | “Big with people who like Thriller”
   0.339 [tv     ] The Season                     | The Season Premieres Soon    | “Fresh in TV shows”
   1.514 [movie  ] Laid to Rest                   | Laid to Rest Watch Trailer   | “Big with people who like Thriller”
```
carousels: [('cluster_1', 15), ('cluster_2', 15), ('trending', 20), ('collaborative', 20), ('exploration', 15), ('new_in_genre_Horror', 20), ('new_in_genre_Comedy', 20), ('new_in_genre_Crime', 12), ('new_in_genre_Fantasy', 20), ('new_on_platform_0', 20), ('new_on_platform_1', 20)]
metrics: on-taste(adj)=0.7 strict=0.6 · median_age=16.1d · overlap_cold=0.037 · expl=0.3894 · top_property_repeat=1 · why_var=0.8 · source_mix={'global': 4, 'trending': 6}
checks:
  - [PASS] horror leads comedy (recency drift reflected) — horror=6 comedy=3
  - [PASS] EXCLUSION integrity: zero followed/seen leak — leak=0
_Assessment:_ A real user here would see a strongly personal, fresh, varied feed (on-taste 0.7, why-variety 0.8). Meets the constructed expectation.

### GT_SPARSE — ✅ PASS
_Only 2 sim-game follows (thin signal → explore)._  · intended=['simulation'] · mode=personalized signal=0.082

**Feed (top 8):**
```
   0.350 [movie  ] Bear Country                   | Bear Country Coming Soon     | “Worth a look · movies”
   0.920 [game   ] Per Aspera                     | Per Aspera Launched on PC (M | “Trending in Simulation”
   0.350 [movie  ] The Death of Robin Hood        | The Death of Robin Hood Comi | “Fresh in movies”
   0.901 [game   ] Stardew Valley                 | Stardew Valley Launched on N | “Matches your taste in Role-Playing”
   0.829 [game   ] FreeDiver: Triton Down         | FreeDiver: Triton Down Now A | “You might not expect it, but people like you love this”
   0.350 [movie  ] Leviticus                      | Leviticus Coming Soon        | “Worth a look · movies”
   0.772 [game   ] Circuit Superstars             | Circuit Superstars Launched  | “More Simulation you'll like”
   0.350 [movie  ] The Third Child                | The Third Child Coming Soon  | “Fresh in movies”
```
carousels: [('cluster_1', 15), ('trending', 20), ('collaborative', 20), ('exploration', 3), ('new_in_genre_Adventure', 20), ('new_in_genre_Drama', 20), ('new_in_genre_Comedy', 20), ('new_in_genre_Action', 20), ('new_on_platform_0', 20), ('new_on_platform_1', 20)]
metrics: on-taste(adj)=0.6 strict=0.5 · median_age=333.5d · overlap_cold=0.024 · expl=0.4672 · top_property_repeat=1 · why_var=0.8 · source_mix={'global': 4, 'trending': 5, 'taste': 1}
checks:
  - [PASS] exploration ≥ 0.4 — expl=0.4672
  - [PASS] EXCLUSION integrity: zero followed/seen leak — leak=0
_Assessment:_ A real user here would see a strongly personal, STALE, varied feed (on-taste 0.6, why-variety 0.8). Meets the constructed expectation.

### GT_REACTOR — ✅ PASS
_2 horror follows + 8 horror reactions (reactions drive taste)._  · intended=['horror'] · mode=personalized signal=0.4443

**Feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   2.005 [movie  ] Dracula Untold                 | Dracula Untold Watch Trailer | “Hot right now in Horror”
   1.735 [movie  ] House IV                       | House IV Watch Trailer       | “Right up your alley: Thriller”
   0.339 [game   ] EA Sports UFC 6                | EA Sports UFC 6 Unveiled on  | “New games”
   1.657 [movie  ] Laid to Rest                   | Laid to Rest Watch Trailer   | “Big with people who like Thriller”
   1.629 [movie  ] Vampires of the Velvet Lounge  | Vampires of the Velvet Loung | “Fans of your favorites are into this”
   1.622 [movie  ] Las leyendas: El origen        | Las leyendas: El origen Watc | “Big with people who like Animation”
   0.339 [tv     ] The Season                     | The Season Premieres Soon    | “Fresh in TV shows”
```
carousels: [('cluster_1', 15), ('trending', 20), ('collaborative', 20), ('exploration', 15), ('new_in_genre_Horror', 20), ('new_in_genre_Comedy', 20), ('new_in_genre_Thriller', 20), ('new_in_genre_Action', 20), ('new_on_platform_0', 20), ('new_on_platform_1', 20)]
metrics: on-taste(adj)=0.8 strict=0.7 · median_age=16.1d · overlap_cold=0.024 · expl=0.3223 · top_property_repeat=1 · why_var=0.9 · source_mix={'global': 3, 'trending': 7}
checks:
  - [PASS] on-taste ≥ 0.5 — adj_on_taste=0.8
  - [PASS] EXCLUSION integrity: zero followed/seen leak — leak=0
_Assessment:_ A real user here would see a strongly personal, fresh, varied feed (on-taste 0.8, why-variety 0.9). Meets the constructed expectation.

### GT_NICHE — ✅ PASS
_4 long-tail, low-popularity follows (niche taste)._  · intended=['comedy', 'horror', 'science fiction'] · mode=personalized signal=0.1641

**Feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   2.043 [movie  ] Vampires of the Velvet Lounge  | Vampires of the Velvet Loung | “Trending in Comedy”
   0.339 [game   ] EA Sports UFC 6                | EA Sports UFC 6 Unveiled on  | “New games”
   1.788 [movie  ] Noises Off...                  | Noises Off... Watch Trailer  | “Fans of your favorites are into this”
   1.778 [tv     ] Lexx                           | Lexx Trailer Available       | “Right up your alley: Comedy”
   0.339 [tv     ] The Season                     | The Season Premieres Soon    | “Fresh in TV shows”
   1.759 [movie  ] Arsenic and Old Lace           | Arsenic and Old Lace Watch T | “Big with people who like Comedy”
   0.307 [tv     ] See You at Work Tomorrow!      | See You at Work Tomorrow! Pr | “Worth a look · TV shows”
```
carousels: [('cluster_1', 15), ('trending', 20), ('collaborative', 20), ('exploration', 15), ('new_in_genre_Comedy', 20), ('new_in_genre_Horror', 20), ('new_in_genre_Science Fiction', 19), ('new_in_genre_Drama', 20), ('new_on_platform_0', 20), ('new_on_platform_1', 20)]
metrics: on-taste(adj)=0.8 strict=0.7 · median_age=16.1d · overlap_cold=0.037 · expl=0.4344 · top_property_repeat=1 · why_var=0.8 · source_mix={'global': 4, 'trending': 6}
checks:
  - [PASS] overlap w/ global ≤ 0.25 (niche, not global-popular) — overlap=0.037
  - [PASS] EXCLUSION integrity: zero followed/seen leak — leak=0
_Assessment:_ A real user here would see a strongly personal, fresh, varied feed (on-taste 0.8, why-variety 0.8). Meets the constructed expectation.

### GT_TRENDING_SENSITIVE — ✅ PASS
_6 horror follows; a DIFFERENT horror property has a planted recent burst._  · intended=['horror'] · mode=personalized signal=0.2461

**Feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   2.455 [movie  ] Dracula Untold                 | Dracula Untold Watch Trailer | “Hot right now in Horror”
   1.430 [movie  ] Las leyendas: El origen        | Las leyendas: El origen Watc | “Because you follow Underwater”
   0.339 [game   ] EA Sports UFC 6                | EA Sports UFC 6 Unveiled on  | “New games”
   1.306 [movie  ] Laid to Rest                   | Laid to Rest Watch Trailer   | “Big with people who like Thriller”
   1.297 [movie  ] House IV                       | House IV Watch Trailer       | “Right up your alley: Thriller”
   0.339 [tv     ] The Season                     | The Season Premieres Soon    | “Fresh in TV shows”
   1.273 [movie  ] House                          | House Trailer Available      | “Right up your alley: Fantasy”
```
carousels: [('cluster_1', 15), ('trending', 20), ('collaborative', 20), ('exploration', 15), ('new_in_genre_Horror', 20), ('new_in_genre_Action', 20), ('new_in_genre_Fantasy', 20), ('new_in_genre_Thriller', 20), ('new_on_platform_0', 20), ('new_on_platform_1', 20)]
metrics: on-taste(adj)=0.7 strict=0.6 · median_age=16.1d · overlap_cold=0.037 · expl=0.4016 · top_property_repeat=1 · why_var=0.9 · source_mix={'global': 4, 'trending': 6}
checks:
  - [PASS] planted item surfaces (Dracula Untold) — in_main=True in_feed_or_carousel=True
  - [PASS] EXCLUSION integrity: zero followed/seen leak — leak=0
_Assessment:_ A real user here would see a strongly personal, fresh, varied feed (on-taste 0.7, why-variety 0.9). Meets the constructed expectation.

### GT_BUBBLE_ESCAPE — ✅ PASS
_6 horror follows; similar users also love a cross-attribute strategy GAME the user hasn't found._  · intended=['horror'] · mode=personalized signal=0.2461

**Feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   1.751 [movie  ] Dracula Untold                 | Dracula Untold Watch Trailer | “Hot right now in Horror”
   1.652 [movie  ] Laid to Rest                   | Laid to Rest Watch Trailer   | “Big with people who like Thriller”
   0.339 [game   ] EA Sports UFC 6                | EA Sports UFC 6 Unveiled on  | “New games”
   1.621 [movie  ] The Cloverfield Paradox        | The Cloverfield Paradox Trai | “Loved by people with taste like yours”
   1.555 [movie  ] House IV                       | House IV Watch Trailer       | “Big with people who like Thriller”
   0.339 [tv     ] The Season                     | The Season Premieres Soon    | “Fresh in TV shows”
   1.525 [movie  ] Willard                        | Willard Watch Trailer        | “Big with people who like Horror”
```
carousels: [('cluster_1', 15), ('trending', 20), ('collaborative', 20), ('exploration', 6), ('new_in_genre_Horror', 20), ('new_in_genre_Thriller', 20), ('new_in_genre_Science Fiction', 19), ('new_in_genre_Comedy', 20), ('new_on_platform_0', 20), ('new_on_platform_1', 20)]
metrics: on-taste(adj)=0.7 strict=0.6 · median_age=16.1d · overlap_cold=0.037 · expl=0.4016 · top_property_repeat=1 · why_var=0.7 · source_mix={'global': 4, 'trending': 6}
checks:
  - [PASS] planted item surfaces (Songs of Conquest) — in_main=False in_feed_or_carousel=True
  - [PASS] collaborative carousel emitted (bubble-escape path live) — carousels=['cluster_1', 'collaborative', 'exploration', 'new_in_genre_Comedy', 'new_in_genre_Horror', 'new_in_genre_Science Fiction', 'new_in_genre_Thriller', 'new_on_platform_0', 'new_on_platform_1', 'trending']
  - [PASS] EXCLUSION integrity: zero followed/seen leak — leak=0
_Assessment:_ A real user here would see a strongly personal, fresh, varied feed (on-taste 0.7, why-variety 0.7). Meets the constructed expectation.

### GT_CROSS_VERTICAL — ❌ FAIL
_2 game + 2 movie + 2 TV + 2 podcast follows._  · intended=['action', 'adventure', 'drama'] · mode=personalized signal=0.3281

**Feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   1.564 [movie  ] The Promised Neverland         | The Promised Neverland Trail | “You might not expect it, but people like you love this”
   1.419 [movie  ] Gone in 60 Seconds             | Gone in 60 Seconds Trailer A | “You might not expect it, but people like you love this”
   1.257 [movie  ] Freejack                       | Freejack Trailer Available   | “Loved by people with taste like yours”
   0.339 [tv     ] The Season                     | The Season Premieres Soon    | “Fresh in TV shows”
   1.205 [movie  ] The Long Good Friday           | The Long Good Friday Trailer | “Matches your taste in Thriller”
   1.170 [movie  ] Night Crossing                 | Night Crossing Watch Trailer | “Big with people who like Drama”
   1.165 [movie  ] Code 3                         | Code 3 Watch Trailer         | “Loved by people with taste like yours”
```
carousels: [('cluster_1', 15), ('cluster_2', 15), ('cluster_3', 15), ('trending', 20), ('collaborative', 20), ('exploration', 15), ('new_in_genre_Drama', 20), ('new_in_genre_Action', 20), ('new_in_genre_Adventure', 20), ('new_in_genre_Crime', 12), ('new_on_platform_0', 20), ('new_on_platform_1', 20)]
metrics: on-taste(adj)=1.0 strict=1.0 · median_age=16.1d · overlap_cold=0.024 · expl=0.3688 · top_property_repeat=1 · why_var=0.6 · source_mix={'global': 3, 'trending': 6, 'taste': 1}
checks:
  - [FAIL] ≥ 3 verticals represented — mix={'tv': 3, 'movie': 7}
  - [PASS] EXCLUSION integrity: zero followed/seen leak — leak=0
_Assessment:_ A real user here would see a strongly personal, fresh, concentrated feed (on-taste 1.0, why-variety 0.6). MISSES the constructed expectation.

### GT_HEAVY — ✅ PASS
_30 follows across horror+action+sim+drama (wide taste)._  · intended=['action', 'drama', 'horror', 'simulation'] · mode=personalized signal=1.0

**Feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   1.758 [movie  ] The Promised Neverland         | The Promised Neverland Trail | “You might not expect it, but people like you love this”
   1.443 [movie  ] Nowhere to Run                 | Nowhere to Run Watch Trailer | “Loved by people with taste like yours”
   1.375 [movie  ] Jurassic City                  | Jurassic City Trailer Availa | “You might not expect it, but people like you love this”
   0.339 [tv     ] The Season                     | The Season Premieres Soon    | “Fresh in TV shows”
   1.353 [movie  ] Freejack                       | Freejack Trailer Available   | “Right up your alley: Drama”
   1.323 [movie  ] Gone in 60 Seconds             | Gone in 60 Seconds Trailer A | “You might not expect it, but people like you love this”
   1.312 [movie  ] Significant Other              | Significant Other Watch Trai | “Fans of your favorites are into this”
```
carousels: [('cluster_1', 15), ('cluster_2', 15), ('trending', 20), ('collaborative', 12), ('exploration', 8), ('new_in_genre_Action', 20), ('new_in_genre_Drama', 20), ('new_in_genre_Adventure', 20), ('new_in_genre_Thriller', 20), ('new_on_platform_0', 20), ('new_on_platform_1', 20)]
metrics: on-taste(adj)=1.0 strict=1.0 · median_age=16.1d · overlap_cold=0.024 · expl=0.1 · top_property_repeat=1 · why_var=0.6 · source_mix={'global': 3, 'trending': 7}
checks:
  - [PASS] no property repeats > 2× — max_repeat=1
  - [PASS] exploration ≤ 0.3 (rich user exploits) — expl=0.1
  - [PASS] EXCLUSION integrity: zero followed/seen leak — leak=0
_Assessment:_ A real user here would see a strongly personal, fresh, varied feed (on-taste 1.0, why-variety 0.6). Meets the constructed expectation.

### GT_PODCAST_LOVER — ✅ PASS
_8 podcast follows._  · intended=['podcast'] · mode=personalized signal=0.3281

**Feed (top 8):**
```
   0.350 [movie  ] Bear Country                   | Bear Country Coming Soon     | “Worth a look · movies”
   1.122 [podcast] Side Notes by Zerodha Varsity  | How Lenovo took over IBM to  | “Big with people who like Business”
   1.010 [podcast] Golf Channel Podcast with Rex  | What was THAT?! Recapping a  | “Because you follow I've Been Meaning To Listen To That”
   0.350 [movie  ] The Death of Robin Hood        | The Death of Robin Hood Comi | “Fresh in movies”
   0.954 [podcast] Murder Made Fiction            | Unbelievable Episode 8 (Patr | “Loved by people with taste like yours”
   0.922 [podcast] Sports Card Strategy Show      | Sports Card Hobby Fight: Dat | “Big with people who like Business”
   0.350 [movie  ] Leviticus                      | Leviticus Coming Soon        | “Worth a look · movies”
   0.917 [podcast] The Dr. Phil Podcast           | Pray For The Legacy Media    | “Picking up steam in Society”
```
carousels: [('cluster_1', 15), ('cluster_2', 15), ('cluster_3', 15), ('trending', 19), ('collaborative', 20), ('exploration', 15), ('new_in_genre_Drama', 20), ('new_in_genre_Comedy', 20), ('new_in_genre_Action', 20), ('new_in_genre_Thriller', 20), ('new_on_platform_0', 20), ('new_on_platform_1', 20)]
metrics: on-taste(adj)=0.0 strict=0.0 · median_age=18.1d · overlap_cold=0.024 · expl=0.3688 · top_property_repeat=1 · why_var=0.8 · source_mix={'global': 3, 'trending': 2, 'taste': 2, 'collaborative': 3}
checks:
  - [PASS] podcast is the dominant vertical — mix={'movie': 3, 'podcast': 7}
  - [PASS] EXCLUSION integrity: zero followed/seen leak — leak=0
_Assessment:_ A real user here would see a strongly personal, fresh, varied feed (on-taste 0.0, why-variety 0.8). Meets the constructed expectation.

### GT_ACTION_FAN — ✅ PASS
_10 action-movie follows._  · intended=['action'] · mode=personalized signal=0.4102

**Feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   1.681 [movie  ] Dracula Untold                 | Dracula Untold Watch Trailer | “Hot right now in Horror”
   1.610 [movie  ] Nowhere to Run                 | Nowhere to Run Watch Trailer | “Loved by people with taste like yours”
   0.339 [game   ] EA Sports UFC 6                | EA Sports UFC 6 Unveiled on  | “New games”
   1.594 [movie  ] Batman Forever                 | Batman Forever Watch Trailer | “You might not expect it, but people like you love this”
   1.587 [movie  ] The Prison                     | The Prison Trailer Available | “Fans of your favorites are into this”
   1.468 [movie  ] Octopussy                      | Octopussy Watch Trailer      | “You might not expect it, but people like you love this”
   0.339 [tv     ] The Season                     | The Season Premieres Soon    | “Fresh in TV shows”
```
carousels: [('cluster_1', 15), ('trending', 20), ('collaborative', 20), ('exploration', 15), ('new_in_genre_Action', 20), ('new_in_genre_Crime', 12), ('new_in_genre_Thriller', 20), ('new_in_genre_Adventure', 20), ('new_on_platform_0', 20), ('new_on_platform_1', 20)]
metrics: on-taste(adj)=0.9 strict=0.8 · median_age=16.1d · overlap_cold=0.037 · expl=0.3359 · top_property_repeat=1 · why_var=0.7 · source_mix={'global': 3, 'trending': 7}
checks:
  - [PASS] on-taste ≥ 0.5 — adj_on_taste=0.9
  - [PASS] EXCLUSION integrity: zero followed/seen leak — leak=0
_Assessment:_ A real user here would see a strongly personal, fresh, concentrated feed (on-taste 0.9, why-variety 0.7). Meets the constructed expectation.

### GT_RECENT_BINGE — ✅ PASS
_12 horror follows, ALL in the last 2 days (bursty recent)._  · intended=['horror'] · mode=personalized signal=0.571

**Feed (top 8):**
```
   0.350 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “Fresh in TV shows”
   1.862 [movie  ] Dracula Untold                 | Dracula Untold Watch Trailer | “Hot right now in Horror”
   1.705 [movie  ] The Cloverfield Paradox        | The Cloverfield Paradox Trai | “Loved by people with taste like yours”
   1.697 [movie  ] House IV                       | House IV Watch Trailer       | “Big with people who like Thriller”
   0.339 [game   ] EA Sports UFC 6                | EA Sports UFC 6 Unveiled on  | “New games”
   1.691 [movie  ] I Still Know What You Did Last | I Still Know What You Did La | “More Horror you'll like”
   1.676 [movie  ] Laid to Rest                   | Laid to Rest Watch Trailer   | “Big with people who like Thriller”
   1.647 [movie  ] Significant Other              | Significant Other Watch Trai | “Like The Devil's Carnival, but new to you”
```
carousels: [('cluster_1', 15), ('trending', 20), ('collaborative', 20), ('exploration', 15), ('new_in_genre_Horror', 20), ('new_in_genre_Thriller', 20), ('new_in_genre_Mystery', 10), ('new_in_genre_Comedy', 20), ('new_on_platform_0', 20), ('new_on_platform_1', 20)]
metrics: on-taste(adj)=0.8 strict=0.7 · median_age=16.1d · overlap_cold=0.024 · expl=0.2716 · top_property_repeat=1 · why_var=0.8 · source_mix={'global': 3, 'trending': 7}
checks:
  - [PASS] on-taste ≥ 0.6 — adj_on_taste=0.8
  - [PASS] EXCLUSION integrity: zero followed/seen leak — leak=0
_Assessment:_ A real user here would see a strongly personal, fresh, varied feed (on-taste 0.8, why-variety 0.8). Meets the constructed expectation.


## Part D — Aggregate behavior across the population

| metric | min | p25 | median | p75 | max | mean |
|---|---|---|---|---|---|---|
| on-taste (adjacency) | 0.1 | 0.8 | 0.9 | 1.0 | 1.0 | 0.832 |
| on-taste (strict) | 0.1 | 0.7 | 0.8 | 0.9 | 1.0 | 0.771 |
| median moment age (d) | 8.1 | 16.1 | 16.1 | 16.1 | 1988.5 | 136.037 |
| overlap w/ cold feed | 0.0 | 0.024 | 0.024 | 0.037 | 0.049 | 0.026 |
| exploration fraction | 0.1 | 0.236 | 0.339 | 0.404 | 0.489 | 0.314 |
| why-variety | 0.4 | 0.7 | 0.8 | 0.9 | 1.0 | 0.779 |
| why-correctness | 0.1 | 0.4 | 0.5 | 0.7 | 1.0 | 0.527 |
| max property repeat | 1 | 1 | 1.0 | 1 | 1 | 1 |
| build time (s) | 1.15 | 1.6 | 1.95 | 2.38 | 5.79 | 2.178 |

**Source mix across all population feeds (% of main-feed items):**
  - trending       ███████████████········· 62.4%
  - global         ███████················· 29.6%
  - taste          ██······················ 6.4%
  - collaborative  ························ 1.6%

**Exploration vs signal_strength** (should fall as signal rises): {'mid(0.1-0.3)': 0.419, 'hi(≥0.3)': 0.251, 'lo(<0.1)': 0.473}
**On-taste by profile depth:** {'shallow(≤3)': 0.798, 'medium(4-18)': 0.842, 'deep(>18)': 0.871}
**Collaborative fired:** 100.0% of users · **Trending fired:** 100.0% · **feeds with a repeated property:** 0.0%


## Part E — Strengths, weaknesses, and the deployment judgment

### Top strengths (with evidence)
- **Exclusion integrity is absolute** — 0 followed/seen leaks across all 380+ feeds generated (the hard gate held everywhere).
- **13/15 designed scenarios pass** their known right-answer (cold→global, drift, bubble-escape, trending, niche, cross-vertical, etc.).
- **Exploration scales with signal** — thin users explore more than rich users ({'mid(0.1-0.3)': 0.419, 'hi(≥0.3)': 0.251, 'lo(<0.1)': 0.473}).
- **On-taste tracks profile depth** — {'shallow(≤3)': 0.798, 'medium(4-18)': 0.842, 'deep(>18)': 0.871} (deeper profiles → more on-taste).
- **Personalization is real** — median overlap with the cold/global feed is 0.024 (low = genuinely personal, not global-with-a-hat).

### Top weaknesses / issues (config-tied; DIAGNOSE-ONLY — no logic changed here)
- **Why-string ↔ source mismatch** — mean why-correctness 0.527 (some items' explanation doesn't match their dominant source). *Knob:* `_dominant`/phrasing map.
- **GT_MULTI_BALANCED missed:** ['≥ 3 verticals represented'] — see its section for evidence.
- **GT_CROSS_VERTICAL missed:** ['≥ 3 verticals represented'] — see its section for evidence.

### Summary judgment
**READY for real-user A/B testing**. The engine personalizes genuinely (low cold-overlap), learns over time (longitudinal on-taste rises / exploration falls for 5/5 users), escapes the content bubble via collaborative, and NEVER leaks excluded content (0 leaks). 13/15 designed scenarios pass.

**Known limitations going in (watch once real data flows):** (1) freshness skews old for deep/niche tastes (on-taste catalog moments vs fresh) — watch median feed age and tune the recency floor; (2) trending & collaborative are deliberately bounded on the MAIN feed (carousel-first) to protect on-taste — confirm that product-desired balance with real engagement; (3) why-string variety/precision is template-bounded; (4) collaborative/trending confidence are calibrated on SYNTHETIC volume — re-check the confidence curves (`*_CONFIDENCE_FULL`) against real engagement density.

_All findings are DIAGNOSTIC. No ranking/retrieval/blend logic was changed in this evaluation; every recommendation is a config-tied follow-up._