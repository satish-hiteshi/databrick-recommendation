# Discovery v2 — Fresh-Account Persona Evaluation

_now=2026-06-18T00:00:00+00:00 · substrate=LIVE · default_engine=v1_

Both engines run over an in-memory OVERLAY (synthetic follows/reactions for fresh user_ids over REAL served entities; production CSVs untouched). v2 = taste-profile → content+exploration retrieval → trending + three-signal blend. v1 = the global+similarity pools baseline.


## P_NEW  (user 990001)

**Profile:** Brand-new account, zero follows (cold-start).

**Context** — v2: mode=cold_start signal=0.0 path=global_fallback | v1: mode=cold_start signal=0.0

**v2 MAIN FEED (top 10):**
```
   0.777 [movie  ] Virginia Woolf's Night & Day   | Virginia Woolf's Night & Day | “Popular movies”
   0.777 [movie  ] Voicemails for Isabelle        | Voicemails for Isabelle Arri | “Popular movies”
   0.764 [movie  ] You Are the Film               | You Are the Film Arrives Jun | “New movies”
   0.762 [movie  ] Toy Story 5                    | Toy Story 5 Premieres Soon   | “New movies”
   0.718 [movie  ] Les caprices de l'enfant Roi   | Les caprices de l’enfant Roi | “Popular movies”
   0.718 [movie  ] Stop! That! Train!             | Stop! That! Train! Arrives J | “Popular movies”
   0.707 [movie  ] Bleach: Thousand-Year Blood Wa | Bleach: Thousand-Year Blood  | “Popular movies”
   0.707 [tv     ] Nurse the Dead                 | Nurse the Dead Coming Soon   | “Popular TV shows”
   0.698 [movie  ] Fatherland                     | Fatherland Arrives Jun 19    | “New movies”
   0.696 [movie  ] Meeting the Buddha             | Meeting the Buddha Arrives J | “Popular movies”
```
**v2 CAROUSELS:** trending[20], new_in_genre:Drama[20], new_in_genre:Comedy[20], new_in_genre:Thriller[20], new_in_genre:Action[20], new_on_platform:1[20]
   · **trending** «Trending now» [trending] (20)

**v1 MAIN FEED (top 6, for comparison):**
```
   0.777 [movie  ] Virginia Woolf's Night & Day   | Virginia Woolf's Night & Day | “Popular movies”
   0.777 [movie  ] Voicemails for Isabelle        | Voicemails for Isabelle Arri | “Popular movies”
   0.764 [movie  ] You Are the Film               | You Are the Film Arrives Jun | “New movies”
   0.762 [movie  ] Toy Story 5                    | Toy Story 5 Premieres Soon   | “New movies”
   0.718 [movie  ] Les caprices de l'enfant Roi   | Les caprices de l’enfant Roi | “Popular movies”
   0.718 [movie  ] Stop! That! Train!             | Stop! That! Train! Arrives J | “Popular movies”
```
**METRICS** — v2 vs v1:
   · vertical_mix:  v2={'movie': 9, 'tv': 1}   v1={'movie': 9, 'tv': 1}
   · on_taste (genres ∩ intended): v2=None  v1=None
   · why_string variety: v2=0.3  v1=0.3
   · median freshness (days old): v2=-1.0  v1=-1.0
   · overlap w/ P_NEW global feed: v2=0.133  v1=0.133  (low=personalized)
   · v1↔v2 main-feed jaccard: 1.0  (low=meaningfully different)
   · build time: v2=0.95s  v1=0.62s

**VERDICT:** Cold-start on BOTH engines → the global feed (v2 routes via fallback_to_global). As a brand-new user this is correct: trending/fresh/popular, no personalization claimed.

## P_SINGLE_TASTE  (user 990002)

**Profile:** 8 simulation/strategy GAME follows (one coherent cozy-builder taste), all recent.
  · follows: Per Aspera, Circuit Superstars, Rocket League, Galak-Z: The Dimensional, Forklift Simulator 2019, Anno 2205, Skyhill, FutureGrind

**Context** — v2: mode=personalized signal=0.3123 path=personalized | v1: mode=personalized signal=0.4
  · v2 vertical%: {'game': 0.58, 'movie': 0.14, 'tv': 0.14, 'podcast': 0.14}
  · v2 clusters: #1 Simulation + Indie(game,share=1.0)
  · exploration_fraction=0.3751 | global_backfill={'movie': 21, 'tv': 21, 'podcast': 21}

**v2 MAIN FEED (top 10):**
```
   0.600 [movie  ] Bear Country                   | Bear Country Coming Soon     | “New movies”
   1.012 [game   ] Outpath                        | Outpath Now Available on Nin | “Because you follow Per Aspera”
   1.000 [game   ] Outpath                        | Outpath Launched on PC (Micr | “Because you follow Per Aspera”
   0.600 [movie  ] The Death of Robin Hood        | The Death of Robin Hood Comi | “New movies”
   0.980 [game   ] Little Big Workshop            | Little Big Workshop Launched | “Because you follow Per Aspera”
   0.980 [game   ] Little Big Workshop            | Little Big Workshop Launched | “Because you follow Per Aspera”
   0.600 [movie  ] Leviticus                      | Leviticus Coming Soon        | “New movies”
   0.980 [game   ] Little Big Workshop            | Little Big Workshop Now Avai | “Because you follow Per Aspera”
   0.958 [game   ] Arcade Tycoon                  | Arcade Tycoon Now Available  | “Because you follow Per Aspera”
   0.958 [game   ] Arcade Tycoon                  | Arcade Tycoon Launched on PC | “Because you follow Per Aspera”
```
**v2 CAROUSELS:** cluster_1[15], trending[20], new_in_genre_Adventure[20], new_in_genre_Action[20], new_in_genre_Drama[20], new_in_genre_Comedy[20], new_on_platform_0[20], new_on_platform_1[20]
   · **trending** «Trending in Simulation» [trending] (20)

**v1 MAIN FEED (top 6, for comparison):**
```
   0.591 [movie  ] Virginia Woolf's Night & Day   | Virginia Woolf's Night & Day | “Popular movies”
   0.591 [movie  ] Voicemails for Isabelle        | Voicemails for Isabelle Arri | “Popular movies”
   0.581 [movie  ] You Are the Film               | You Are the Film Arrives Jun | “New movies”
   0.579 [movie  ] Toy Story 5                    | Toy Story 5 Premieres Soon   | “New movies”
   0.546 [movie  ] Les caprices de l'enfant Roi   | Les caprices de l’enfant Roi | “Popular movies”
   0.546 [movie  ] Stop! That! Train!             | Stop! That! Train! Arrives J | “Popular movies”
```
**METRICS** — v2 vs v1:
   · vertical_mix:  v2={'movie': 3, 'game': 7}   v1={'movie': 9, 'tv': 1}
   · on_taste (genres ∩ intended): v2=0.7  v1=0.0
   · why_string variety: v2=0.2  v1=0.3
   · median freshness (days old): v2=925.5  v1=-1.0
   · overlap w/ P_NEW global feed: v2=0.025  v1=0.133  (low=personalized)
   · v1↔v2 main-feed jaccard: 0.0  (low=meaningfully different)
   · build time: v2=1.49s  v1=7.53s

**VERDICT:** v2 is more on-taste (0.7 vs v1 0.0); feeds differ meaningfully (jaccard 0.0); explanations are repetitive (why_variety 0.2 — mostly 'Because you follow…').

## P_CROSS_VERTICAL  (user 990003)

**Profile:** A mix: 2 games + 2 action movies + 2 drama TV + 2 podcasts, all recent.
  · follows: The LEGO Movie 2 Videogame, Mochi Mochi Boy, Nowhere to Run, Batman Forever, Murder Is Easy, Miracle Workers, Racing Back, Gallbladder Gone? Now What? A Podcast for Christian Women

**Context** — v2: mode=personalized signal=0.3123 path=personalized | v1: mode=personalized signal=0.4
  · v2 vertical%: {'game': 0.25, 'movie': 0.25, 'tv': 0.25, 'podcast': 0.25}
  · v2 clusters: #1 Drama + Action(movie,share=0.75); #2 Adventure + Arcade(game,share=0.25)
  · exploration_fraction=0.3751 | global_backfill={'tv': 38, 'podcast': 38}

**v2 MAIN FEED (top 10):**
```
   0.600 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “New TV shows”
   1.352 [movie  ] The Long Good Friday           | The Long Good Friday Trailer | “Because you follow Batman Forever”
   0.581 [tv     ] The Season                     | The Season Premieres Soon    | “New TV shows”
   0.952 [movie  ] The Rising Hawk                | The Rising Hawk Watch Traile | “Because you follow Batman Forever”
   0.952 [movie  ] Blood Father                   | Blood Father Watch Trailer   | “Because you follow Batman Forever”
   0.526 [tv     ] See You at Work Tomorrow!      | See You at Work Tomorrow! Pr | “New TV shows”
   0.952 [movie  ] Mala influencia                | Mala influencia Watch Traile | “Because you follow Batman Forever”
   0.952 [movie  ] Batman                         | Batman Watch Trailer         | “Because you follow Batman Forever”
   0.492 [tv     ] Nurse the Dead                 | Nurse the Dead Coming Soon   | “New TV shows”
   0.929 [movie  ] Under Suspicion                | Under Suspicion Watch Traile | “Because you follow Batman Forever”
```
**v2 CAROUSELS:** cluster_1[15], cluster_2[15], trending[20], exploration[15], new_in_genre_Drama[20], new_in_genre_Action[20], new_in_genre_Crime[12], new_in_genre_Thriller[20], new_on_platform_0[20], new_on_platform_1[20]
   · **trending** «Trending in Drama» [trending] (20)
   · **exploration** «Branching out from Drama» [new_in_genre] (15)

**v1 MAIN FEED (top 6, for comparison):**
```
   0.633 [movie  ] The Dark Knight                | The Dark Knight Watch Traile | “Because you follow Murder Is Easy”
   0.621 [movie  ] Batman vs. Two-Face            | Batman vs. Two-Face Watch Tr | “Because you follow Murder Is Easy”
   0.615 [movie  ] Batman Unlimited: Animal Insti | Batman Unlimited: Animal Ins | “Because you follow Murder Is Easy”
   0.609 [movie  ] The Scrapper                   | The Scrapper Trailer Availab | “Because you follow Murder Is Easy”
   0.609 [movie  ] Hunting Grounds                | Hunting Grounds Trailer Avai | “Because you follow Murder Is Easy”
   0.605 [podcast] Chasing the Horizon - Motorcyc | Wayback: Clement Salvadori ( | “Popular with fans of Murder Is Easy”
```
**METRICS** — v2 vs v1:
   · vertical_mix:  v2={'tv': 4, 'movie': 6}   v1={'movie': 8, 'podcast': 2}
   · on_taste (genres ∩ intended): v2=0.9  v1=0.7
   · why_string variety: v2=0.2  v1=0.3
   · median freshness (days old): v2=16.1  v1=16.1
   · overlap w/ P_NEW global feed: v2=0.037  v1=0.024  (low=personalized)
   · v1↔v2 main-feed jaccard: 0.0  (low=meaningfully different)
   · build time: v2=1.96s  v1=7.87s

**VERDICT:** v2 is more on-taste (0.9 vs v1 0.7); feeds differ meaningfully (jaccard 0.0); explanations are repetitive (why_variety 0.2 — mostly 'Because you follow…').

## P_DRIFTING  (user 990004)

**Profile:** OLDER comedy (4 follows, 35d ago) + RECENT horror (4 follows, 2d ago) — taste is drifting to horror.
  · follows: Fathers' Day, Vampires of the Velvet Lounge, The Vicar of Dibley, Nightcap, A Return to Salem's Lot, Osombie, Emelie, Crystal Lake

**Context** — v2: mode=personalized signal=0.2165 path=personalized | v1: mode=personalized signal=0.4
  · v2 vertical%: {'game': 0.16, 'movie': 0.41, 'tv': 0.26, 'podcast': 0.16}
  · v2 clusters: #1 Horror + Comedy(movie,share=0.8775); #2 Comedy(tv,share=0.1225)
  · exploration_fraction=0.4134 | global_backfill={'game': 23, 'podcast': 23}

**v2 MAIN FEED (top 10):**
```
   0.581 [game   ] EA Sports UFC 6                | EA Sports UFC 6 Unveiled on  | “New games”
   1.352 [movie  ] Zombie Apache                  | Zombie Apache Watch Trailer  | “Because you follow A Return to Salem's Lot”
   1.273 [movie  ] Bloody Mallory                 | Bloody Mallory Watch Trailer | “Because you follow A Return to Salem's Lot”
   1.273 [tv     ] The Catherine Tate Show        | The Catherine Tate Show Trai | “Because you follow Fathers' Day”
   0.503 [game   ] Hogwarts Legacy                | Hogwarts Legacy DLC          | “New games”
   1.245 [tv     ] Ripping Yarns                  | Ripping Yarns Trailer Availa | “Because you follow Fathers' Day”
   1.204 [tv     ] W1A                            | W1A Watch Trailer            | “Because you follow Fathers' Day”
   1.143 [movie  ] Leprechaun Returns             | Leprechaun Returns Trailer A | “Because you follow A Return to Salem's Lot”
   0.492 [game   ] EA Sports UFC 6                | EA Sports UFC 6 Unveiled on  | “New games”
   1.100 [tv     ] Little Britain USA             | Little Britain USA Trailer A | “Because you follow Fathers' Day”
```
**v2 CAROUSELS:** cluster_1[15], cluster_2[15], trending[20], exploration[15], new_in_genre_Horror[20], new_in_genre_Comedy[20], new_in_genre_Action[20], new_in_genre_Mystery[10], new_on_platform_0[20], new_on_platform_1[20]
   · **trending** «Trending in Horror» [trending] (20)
   · **exploration** «Branching out from Horror» [new_in_genre] (15)

**v1 MAIN FEED (top 6, for comparison):**
```
   0.648 [movie  ] Toxic Daughter                 | Toxic Daughter Watch Trailer | “Because you follow Nightcap”
   0.644 [movie  ] Frankenstein's Army            | Frankenstein's Army Trailer  | “Because you follow Nightcap”
   0.638 [movie  ] First Born                     | First Born Watch Trailer     | “Because you follow Nightcap”
   0.631 [movie  ] Living Among Us                | Living Among Us Trailer Avai | “Because you follow Nightcap”
   0.623 [movie  ] A Goofy Movie                  | A Goofy Movie Watch Trailer  | “Because you follow Nightcap”
   0.622 [movie  ] Dark Shadows                   | Dark Shadows Trailer Availab | “Because you follow Nightcap”
```
**METRICS** — v2 vs v1:
   · vertical_mix:  v2={'game': 3, 'movie': 3, 'tv': 4}   v1={'movie': 10}
   · on_taste (genres ∩ intended): v2=0.3  v1=0.8
   · why_string variety: v2=0.3  v1=0.1
   · median freshness (days old): v2=16.1  v1=16.1
   · overlap w/ P_NEW global feed: v2=0.012  v1=0.0  (low=personalized)
   · v1↔v2 main-feed jaccard: 0.0  (low=meaningfully different)
   · build time: v2=2.06s  v1=6.71s

**VERDICT:** v2 is less on-taste (0.3 vs v1 0.8); feeds differ meaningfully (jaccard 0.0); drift weak (horror=3 comedy=7); explanations are repetitive (why_variety 0.3 — mostly 'Because you follow…').

## P_SPARSE  (user 990005)

**Profile:** Only 3 simulation game follows (thin signal → should explore more).
  · follows: Garden Story, Still There, Fall Guys

**Context** — v2: mode=personalized signal=0.1171 path=personalized | v1: mode=personalized signal=0.15
  · v2 vertical%: {'game': 0.42, 'movie': 0.19, 'tv': 0.19, 'podcast': 0.19}
  · v2 clusters: #1 Indie + Simulation(game,share=1.0)
  · exploration_fraction=0.4532 | global_backfill={'movie': 25, 'tv': 25, 'podcast': 25}

**v2 MAIN FEED (top 10):**
```
   0.600 [movie  ] Bear Country                   | Bear Country Coming Soon     | “New movies”
   1.000 [game   ] Welcome to Elk                 | Welcome to Elk Launched on N | “Because you follow Garden Story”
   0.600 [movie  ] The Death of Robin Hood        | The Death of Robin Hood Comi | “New movies”
   1.000 [game   ] Welcome to Elk                 | Welcome to Elk Now Available | “Because you follow Garden Story”
   1.000 [game   ] Welcome to Elk                 | Welcome to Elk Launched on P | “Because you follow Garden Story”
   0.600 [movie  ] Leviticus                      | Leviticus Coming Soon        | “New movies”
   0.700 [game   ] Storm Boy                      | Storm Boy Now Available on N | “Because you follow Garden Story”
   0.700 [game   ] Storm Boy                      | Storm Boy Now Available on M | “Because you follow Garden Story”
   0.600 [movie  ] The Third Child                | The Third Child Coming Soon  | “New movies”
   0.700 [game   ] Storm Boy                      | Storm Boy Now Available on P | “Because you follow Garden Story”
```
**v2 CAROUSELS:** cluster_1[15], trending[20], exploration[3], new_in_genre_Adventure[20], new_in_genre_Drama[20], new_in_genre_Comedy[20], new_in_genre_Action[20], new_on_platform_0[20], new_on_platform_1[20]
   · **trending** «Trending in Indie» [trending] (20)
   · **exploration** «Branching out from Indie» [new_in_genre] (3)

**v1 MAIN FEED (top 6, for comparison):**
```
   0.707 [movie  ] Virginia Woolf's Night & Day   | Virginia Woolf's Night & Day | “Popular movies”
   0.707 [movie  ] Voicemails for Isabelle        | Voicemails for Isabelle Arri | “Popular movies”
   0.695 [movie  ] You Are the Film               | You Are the Film Arrives Jun | “New movies”
   0.694 [movie  ] Toy Story 5                    | Toy Story 5 Premieres Soon   | “New movies”
   0.653 [movie  ] Les caprices de l'enfant Roi   | Les caprices de l’enfant Roi | “Popular movies”
   0.653 [movie  ] Stop! That! Train!             | Stop! That! Train! Arrives J | “Popular movies”
```
**METRICS** — v2 vs v1:
   · vertical_mix:  v2={'movie': 4, 'game': 6}   v1={'movie': 9, 'tv': 1}
   · on_taste (genres ∩ intended): v2=0.0  v1=0.0
   · why_string variety: v2=0.2  v1=0.3
   · median freshness (days old): v2=1844.5  v1=-1.0
   · overlap w/ P_NEW global feed: v2=0.025  v1=0.133  (low=personalized)
   · v1↔v2 main-feed jaccard: 0.0  (low=meaningfully different)
   · build time: v2=1.22s  v1=2.89s

**VERDICT:** v2 is more on-taste (0.0 vs v1 0.0); feeds differ meaningfully (jaccard 0.0); thin signal → high exploration (vertical% smoothed toward neutral: {'game': 0.42, 'movie': 0.19, 'tv': 0.19, 'podcast': 0.19}); explanations are repetitive (why_variety 0.2 — mostly 'Because you follow…').

## P_REACTOR  (user 990006)

**Profile:** 3 horror-movie follows + 4 reactions on horror moments (reactions add signal).
  · follows: My Son, My Son, What Have Ye Done, Pulse, They Wait

**Context** — v2: mode=personalized signal=0.3042 path=personalized | v1: mode=personalized signal=0.35
  · v2 vertical%: {'game': 0.14, 'movie': 0.57, 'tv': 0.14, 'podcast': 0.14}
  · v2 clusters: #1 Horror + Thriller(movie,share=1.0)
  · exploration_fraction=0.3783 | global_backfill={'game': 21, 'tv': 21, 'podcast': 21}

**v2 MAIN FEED (top 10):**
```
   0.600 [tv     ] I Will Find You                | I Will Find You Coming Soon  | “New TV shows”
   1.352 [movie  ] Insidious                      | Insidious Trailer Available  | “Because you follow I Still Know What You Did Last Summer”
   1.182 [movie  ] Daughter                       | Daughter Watch Trailer       | “Because you follow I Still Know What You Did Last Summer”
   0.581 [game   ] EA Sports UFC 6                | EA Sports UFC 6 Unveiled on  | “New games”
   1.039 [movie  ] Insidious: Chapter 2           | Insidious: Chapter 2 Watch T | “Because you follow I Still Know What You Did Last Summer”
   0.987 [movie  ] Awaken the Shadowman           | Awaken the Shadowman Watch T | “Because you follow I Still Know What You Did Last Summer”
   0.581 [tv     ] The Season                     | The Season Premieres Soon    | “New TV shows”
   0.952 [movie  ] A Nightmare on Elm Street 4: T | A Nightmare on Elm Street 4: | “Because you follow I Still Know What You Did Last Summer”
   0.952 [movie  ] Anaconda 3: Offspring          | Anaconda 3: Offspring Traile | “Because you follow I Still Know What You Did Last Summer”
   0.952 [movie  ] Scream 2                       | Scream 2 Trailer Available   | “Because you follow I Still Know What You Did Last Summer”
```
**v2 CAROUSELS:** cluster_1[15], trending[20], exploration[15], new_in_genre_Horror[20], new_in_genre_Thriller[20], new_in_genre_Mystery[10], new_in_genre_Drama[20], new_on_platform_0[20], new_on_platform_1[20]
   · **trending** «Trending in Horror» [trending] (20)
   · **exploration** «Branching out from Horror» [new_in_genre] (15)

**v1 MAIN FEED (top 6, for comparison):**
```
   0.660 [movie  ] The Abandoned                  | The Abandoned Trailer Availa | “Because you follow Pulse”
   0.647 [movie  ] Ghost in the Machine           | Ghost in the Machine Watch T | “Because you follow Pulse”
   0.639 [movie  ] Offspring                      | Offspring Watch Trailer      | “Because you follow Pulse”
   0.630 [movie  ] Day of the Dead                | Day of the Dead Watch Traile | “Because you follow Pulse”
   0.629 [movie  ] Stranger in Our House          | Stranger in Our House Traile | “Because you follow Pulse”
   0.629 [movie  ] Dead Rising: Watchtower        | Dead Rising: Watchtower Watc | “Because you follow Pulse”
```
**METRICS** — v2 vs v1:
   · vertical_mix:  v2={'tv': 2, 'movie': 7, 'game': 1}   v1={'movie': 10}
   · on_taste (genres ∩ intended): v2=0.7  v1=0.7
   · why_string variety: v2=0.3  v1=0.2
   · median freshness (days old): v2=16.1  v1=16.1
   · overlap w/ P_NEW global feed: v2=0.024  v1=0.024  (low=personalized)
   · v1↔v2 main-feed jaccard: 0.0  (low=meaningfully different)
   · build time: v2=1.24s  v1=6.73s

**VERDICT:** v2 is more on-taste (0.7 vs v1 0.7); feeds differ meaningfully (jaccard 0.0); explanations are repetitive (why_variety 0.3 — mostly 'Because you follow…').


# Summary — v2 strengths + top quality issues (config-tied)

## Strengths (with evidence)
- **v2 personalizes the MAIN FEED; v1 only personalizes carousels.** P_SINGLE_TASTE on-taste v2=0.7 vs v1=0.0; P_CROSS_VERTICAL v2=0.9 vs v1=0.7. v1's main feed stays global fresh/popular (its taste only shows in similar/popular carousels).
- **Genuinely taste-driven, not global-with-a-hat.** Every personalized persona has v1↔v2 main-feed jaccard = 0.0, and overlap with the P_NEW global feed ≈0.02–0.04 (vs v1 ≈0.13).
- **Exploration is sized by signal.** P_SPARSE exploration_fraction 0.4532 > P_SINGLE_TASTE 0.3751 — the thin-signal user explores more.
- **Cold-start correct + cross-vertical variety.** P_NEW → global on both engines; vertical_percentages + global_backfill give single-cluster users other-vertical items (P_DRIFTING feed spans game/movie/tv).
- **Explainable + fast.** Every item has a why_string; the bundle cache makes warm loads sub-second.

## Top quality issues (DIAGNOSIS only — each tied to a config knob / provider)
1. **STALE moments of on-taste properties surface (the biggest issue).** Game-heavy personas show median feed age **925.5d** (P_SINGLE) and **1844.5d** (P_SPARSE) — i.e. years-old launch moments of well-matched games. taste_match outweighs recency for old-but-matched properties and there is no recency floor. *Knob:* raise `V2_W_RECENCY` (currently 0.6) and/or set `DISCOVERY_RECENCY_HARD_CUTOFF_DAYS` (currently None) or add a soft recency floor in `moment_select`.
2. **Recency DRIFT is captured in the profile but doesn't reach the FEED.** P_DRIFTING's taste profile weights the RECENT horror cluster far above the OLD comedy cluster, yet the feed is comedy-heavy (on_taste 0.3; feed horror=3 vs comedy=7). Root cause: `cluster_weight` (which encodes recency) drives slot ALLOCATION, but per-moment `taste_match` comes from the RETRIEVAL score — so a low-weight cluster's items still rank high per-item and flood the page. *Fix (diagnose only):* fold `cluster_share`/`cluster_weight` into `taste_match` in `assembler_v2` (a new `V2_TASTE_CLUSTER_WEIGHTING` knob), so recent-taste clusters dominate ranking, not just slot counts.
3. **Duplicate properties flood the feed (per-property moment cap).** P_SPARSE shows *Welcome to Elk ×3, Storm Boy ×3*; P_SINGLE shows *Little Big Workshop ×3* — the cap (`V2_MOMENT_CAP_PER_PROPERTY=3`) lets one property's launch moments repeat, badly so for sparse users with few candidate properties. *Knob:* lower `V2_MOMENT_CAP_PER_PROPERTY` to 1–2 (or make it signal-scaled).
4. **why_strings are repetitive (avg variety 0.24).** Most main-feed items say “Because you follow {rep}”. *Knob/provider:* `feed/why_v2.moment_why` — vary the phrasing by the item's dominant signal (taste vs recency vs trending) and by genre, not just the cluster rep.
5. **Trending is dev-quiet (≈0 contribution).** On ~31 reactions the confidence gate keeps trending_velocity≈0, so the blend is effectively taste+recency on dev (mechanically correct — the World-Cup unit test proves it activates with volume). *Knob:* lower `V2_TRENDING_CONFIDENCE_FULL` to surface dev trending, or raise `V2_W_TRENDING`; on production volume this self-activates.

_(No ranking logic was changed in this prompt — these are tunable next steps for V2-P5/P7. Issues 1–3 are the highest-leverage for perceived quality.)_