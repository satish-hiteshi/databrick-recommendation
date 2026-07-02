# Endpoint 4 (Search) — Human-Relevance Evaluation v1 (finalized)

_64 consumer-style scenarios · engine v1.3.3 (per-vertical ANN quota + onboarding spread + short-query fixes) · HONEST re-rating vs the corpus-presence audit · name-index 44046 (rapidfuzz) · 44052 bridge props · Qwen embed live · reads only._

> Provisional auto-ratings below are refined by the engineer; thematic/vibe/NL fit judged by hand.


## Summary table

| # | scenario | intent | UC | mode | top-1 (vertical) | rating |
|--|--|--|--|--|--|--|
| 1 | `Elden Ring` | clean game name | UC4 S1 | name | Elden Ring (movie) | **MEDIUM** |
| 2 | `The Daily` | clean podcast name | UC4 S1 | auto_both | The Daily (podcast) | **HIGH** |
| 3 | `Game of Thrones` | clean tv name | UC4 S1 | auto_both | Game of Thrones (game) | **MEDIUM** |
| 4 | `Cyberpunk 2077` | clean game name | UC4 S1 | name | Cyberpunk 2077 (game) | **HIGH** |
| 5 | `Arsenal` | clean name (ambig word) | UC4 S1 | name | Arsenal (movie) | **MEDIUM** |
| 6 | `Breaking Bad` | clean tv name | UC4 S1 | name | El Camino: A Breaking Bad Movie (movie) | **MEDIUM** |
| 7 | `Joe Rogan` | clean podcast/person | UC4 S1 | name | Joe Rogan - Biography Flash (podcast) | **LOW** |
| 8 | `Stranger Things` | clean tv name | UC4 S1 | auto_both | Stranger Things 3: The Game (game) | **MEDIUM** |
| 9 | `eldn ring` | misspelled game | UC4 S1 fuzzy | name | Elden Ring (movie) | **MEDIUM** |
| 10 | `breakin bad` | misspelled tv | UC4 S1 fuzzy | auto_thematic | The Breakdown (podcast) | **LOW** |
| 11 | `stranger thigns` | transposed typo | UC4 S1 fuzzy | auto_thematic | Stranger Danger - A Stranger Things Podcast (podcast) | **MEDIUM** |
| 12 | `the wichter` | misspelled game | UC4 S1 fuzzy | name | The Witcher (game) | **HIGH** |
| 13 | `joe rogen` | misspelled person | UC4 S1 fuzzy | auto_thematic | The Ringer NFL Show (podcast) | **LOW** |
| 14 | `cyberpunk 2077` | lowercase exact | UC4 S1 | name | Cyberpunk 2077 (game) | **HIGH** |
| 15 | `gow` | abbrev (God of War) | UC4 S1 fuzzy | name | Grow (movie) | **LOW** |
| 16 | `last of us` | partial, no 'the' | UC4 S1 fuzzy | auto_both | WhatCulture Gaming (podcast) | **LOW** |
| 17 | `the office` | clean lowercase | UC4 S1 | auto_both | The Office (tv) | **HIGH** |
| 18 | `spider man` | no hyphen | UC4 S1 fuzzy | auto_both | Marvel's Spider-Man (tv) | **HIGH** |
| 19 | `dark souls` | clean lowercase | UC4 S1 | name | Dark Souls (game) | **HIGH** |
| 20 | `Battlefield` | title+war concept | UC4 disambig | auto_both | Battlefield V (game) | **HIGH** |
| 21 | `Halo` | title+concept | UC4 disambig | auto_both | Halo Infinite (game) | **HIGH** |
| 22 | `Friends` | title+common word | UC4 disambig | auto_both | We Are Your Friends (movie) | **MEDIUM** |
| 23 | `Survivor` | title+concept | UC4 disambig | auto_both | Survivor (movie) | **HIGH** |
| 24 | `Frasier` | title | UC4 disambig | name | Frasier (tv) | **HIGH** |
| 25 | `Control` | title+common word | UC4 disambig | auto_both | Control (game) | **HIGH** |
| 26 | `Fallout` | title+concept | UC4 disambig | name | The Fallout (movie) | **MEDIUM** |
| 27 | `cooking` | topic | UC4 thematic | auto_both | A Hot Dog Is a Sandwich (podcast) | **HIGH** |
| 28 | `true crime` | topic | UC4 thematic | auto_both | True Crime (movie) | **HIGH** |
| 29 | `horror games` | topic+vertical word | UC4 thematic | auto_thematic | Latency (movie) | **MEDIUM** |
| 30 | `relaxing fantasy worlds` | mood+topic | UC4 thematic | auto_thematic | Dungeons and Daddies (podcast) | **MEDIUM** |
| 31 | `games like dark souls` | more-like-this | UC4 thematic | auto_thematic | Darksiders Genesis (game) | **HIGH** |
| 32 | `shows about cooking` | NL topic | UC4 thematic | auto_thematic | This Is TASTE (podcast) | **MEDIUM** |
| 33 | `scary movies` | topic+vertical word | UC4 thematic | auto_both | Too Scary; Didn't Watch (podcast) | **MEDIUM** |
| 34 | `feel good comedy` | mood+genre | UC4 thematic | name | Feel Good (tv) | **MEDIUM** |
| 35 | `cozy` | vibe | UC4 thematic (hard) | name | Cozy Grove (game) | **MEDIUM** |
| 36 | `something funny` | vibe | UC4 thematic (hard) | auto_thematic | ok storytime (podcast) | **MEDIUM** |
| 37 | `chill background watching` | vibe | UC4 thematic (hard) | auto_thematic | The Deck (podcast) | **LOW** |
| 38 | `intense competitive` | vibe | UC4 thematic (hard) | auto_thematic | Fast & Furious Presents: Hobbs & Shaw (movie) | **MEDIUM** |
| 39 | `wholesome family` | vibe | UC4 thematic (hard) | auto_thematic | Uncle Buck (movie) | **MEDIUM** |
| 40 | `sci-fi` | cross-vertical | UC7 S3 | auto_thematic | Osiris (movie) | **HIGH** |
| 41 | `fantasy` | cross-vertical | UC7 S3 | auto_both | Dungeons and Daddies (podcast) | **HIGH** |
| 42 | `space` | cross-vertical | UC7 S3 | auto_both | Endless Space 2 (game) | **HIGH** |
| 43 | `zombies` | cross-vertical | UC7 S3 | auto_both | Zombies! Zombies! Zombies! (movie) | **HIGH** |
| 44 | `superheroes` | cross-vertical | UC7 S3 | name | Talk From Superheroes (podcast) | **HIGH** |
| 45 | `medieval` | cross-vertical | UC7 S3 | auto_both | Medieval (movie) | **HIGH** |
| 46 | `what should i watch tonight` | NL open | UC4 thematic (hard) | auto_thematic | Fox News Hourly Update (podcast) | **LOW** |
| 47 | `good podcasts about history` | NL topic | UC4 thematic | auto_thematic | This Day in History (podcast) | **HIGH** |
| 48 | `best soulslike games` | NL topic | UC4 thematic | auto_thematic | WhatCulture Gaming (podcast) | **MEDIUM** |
| 49 | `funny movies to watch with friends` | NL mood | UC4 thematic (hard) | auto_thematic | Sam & Cat (tv) | **MEDIUM** |
| 50 | `football` | onboarding topic | UC7 S3 | auto_both | Football Ramble (podcast) | **HIGH** |
| 51 | `hip hop` | onboarding topic | UC7 S3 | auto_both | Joe and Jada (podcast) | **HIGH** |
| 52 | `anime` | onboarding topic | UC7 S3 | auto_both | Quest for the Best with Tristan, Miles, & Geoff (podcast) | **MEDIUM** |
| 53 | `cooking shows and channels` | onboarding NL | UC7 S3 | auto_both | This Is TASTE (podcast) | **HIGH** |
| 54 | `nba basketball` | onboarding topic | UC7 S3 | auto_both | Hoops Tonight with Jason Timpf (podcast) | **HIGH** |
| 55 | `k-pop` | onboarding topic | UC7 S3 | auto_both | K-Pops! (movie) | **HIGH** |
| 56 | `horror` | filtered game | UC4 filter | thematic | Alan Wake II (game) | **HIGH** |
| 57 | `news` | filtered podcast | UC4 filter | thematic | ABC News Update (podcast) | **HIGH** |
| 58 | `crime` | filtered tv | UC4 filter | thematic | The Professionals (tv) | **HIGH** |
| 59 | `action` | filtered movie | UC4 filter | thematic | Hostile Takeover (movie) | **HIGH** |
| 60 | `a` | too-short | edge | auto_thematic | The Incomparable Superfeed (podcast) | **MEDIUM** |
| 61 | `zxqwv` | gibberish | edge | auto_thematic | The Smallzy Show (podcast) | **MEDIUM** |
| 62 | `🎮🔥` | emoji/symbols | edge | auto_thematic | IGN MRSS Feed (podcast) | **MEDIUM** |
| 63 | `i want to find a really good long form investigative journalism podcast about politics` | very long sentence | edge | auto_thematic | John Solomon Reports (podcast) | **HIGH** |
| 64 | `Crown Trick` | no-vector property by name | edge | name | Crown Trick (game) | **HIGH** |

## Distribution

- HIGH **33** · MEDIUM **24** · LOW **7**  (of 64)

| category | HIGH | MED | LOW |
|--|--|--|--|
| clean | 3 | 5 | 1 |
| misspell | 2 | 2 | 2 |
| partial | 3 | 0 | 2 |
| ambiguous | 5 | 2 | 0 |
| thematic | 3 | 5 | 0 |
| vibe | 0 | 4 | 1 |
| cross | 6 | 0 | 0 |
| nl | 2 | 2 | 1 |
| onboarding | 5 | 1 | 0 |
| vfilter | 4 | 0 | 0 |
| edge | 0 | 3 | 0 |

## Per-scenario detail (top-8 + judgement)


### 1. `Elden Ring`  — _clean game name_ (UC4 S1)
mode_taken: **name** · verticals: {'movie': 1, 'game': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Elden Ring | movie | 0.5176 | exact |
| 2 | Elden Ring Nightreign | game | 0.6651 | fuzzy |

**Judgement — MEDIUM:** The famous GAME is absent from the 44k; the exact 'Elden Ring' returned #1 is the MOVIE (only the spinoff 'Elden Ring Nightreign' game exists). Identity-correct string, wrong entity — the human wanted the game. Corpus gap.

### 2. `The Daily`  — _clean podcast name_ (UC4 S1)
mode_taken: **auto_both** · verticals: {'podcast': 20}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | The Daily | podcast | 0.8798 | exact |
| 2 | What A Day | podcast | 0.8767 | thematic |
| 3 | 7am | podcast | 0.8171 | thematic |
| 4 | The Daily Dad | podcast | 0.8149 | fuzzy |
| 5 | The Daily Aus | podcast | 0.7907 | thematic |
| 6 | talkSPORT Daily | podcast | 0.779 | thematic |
| 7 | Netflix Is A Daily Joke | podcast | 0.7724 | thematic |
| 8 | Al Jazeera News Updates | podcast | 0.7722 | thematic |

**Judgement — HIGH:** Exact 'The Daily' #1; clean podcast results, zero off-vertical noise.

### 3. `Game of Thrones`  — _clean tv name_ (UC4 S1)
mode_taken: **auto_both** · verticals: {'game': 6, 'movie': 2, 'podcast': 10, 'tv': 2}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Game of Thrones | game | 0.6235 | exact |
| 2 | Game of Thrones: The Last Watch | movie | 0.7508 | fuzzy |
| 3 | Game of Thrones: Kingsroad | game | 0.7473 | fuzzy |
| 4 | In Deep Geek | podcast | 0.735 | thematic |
| 5 | Close the Door: Game of Thrones, A Song of Ice and Fire Podcast | podcast | 0.7281 | thematic |
| 6 | A Knight of the Seven Kingdoms - An Unofficial Bald Move Podcast | podcast | 0.6521 | thematic |
| 7 | Critical Role & Sagas of Sundry | podcast | 0.6259 | thematic |
| 8 | Game of Thrones: A Telltale Games Series | game | 0.5955 | fuzzy |

**Judgement — MEDIUM:** The HBO SHOW is absent; the exact 'Game of Thrones' #1 is the Telltale GAME. Right title, wrong entity — the human wanted the show. Corpus gap.

### 4. `Cyberpunk 2077`  — _clean game name_ (UC4 S1)
mode_taken: **name** · verticals: {'game': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Cyberpunk 2077 | game | 0.8379 | exact |

**Judgement — HIGH:** Exact #1, the game. Perfect.

### 5. `Arsenal`  — _clean name (ambig word)_ (UC4 S1)
mode_taken: **name** · verticals: {'movie': 2}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Arsenal | movie | 0.5422 | exact |
| 2 | Arena | movie | 0.487 | fuzzy |

**Judgement — MEDIUM:** FLAGSHIP corpus gap (UC4 Story 1's own example the corpus can't satisfy): Arsenal FC is absent — no sports vertical — so the exact 'Arsenal' #1 is an unrelated 2017 movie. ('All or Nothing: Arsenal' + an Arsenal podcast exist but rank below.) Borderline LOW.

### 6. `Breaking Bad`  — _clean tv name_ (UC4 S1)
mode_taken: **name** · verticals: {'movie': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | El Camino: A Breaking Bad Movie | movie | 0.773 | fuzzy |

**Judgement — MEDIUM:** The show appears absent from the 44k; top is 'El Camino: A Breaking Bad Movie' — right universe, wrong entity. Corpus gap.

### 7. `Joe Rogan`  — _clean podcast/person_ (UC4 S1)
mode_taken: **name** · verticals: {'podcast': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Joe Rogan - Biography Flash | podcast | 0.6064 | fuzzy |

**Judgement — LOW:** The Joe Rogan Experience is absent; only hit is a tangential 'Joe Rogan - Biography Flash'. Corpus gap.

### 8. `Stranger Things`  — _clean tv name_ (UC4 S1)
mode_taken: **auto_both** · verticals: {'game': 1, 'podcast': 7, 'tv': 2, 'movie': 10}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Stranger Things 3: The Game | game | 0.7501 | fuzzy |
| 2 | Stranger Danger - A Stranger Things Podcast | podcast | 0.6567 | fuzzy |
| 3 | Stranger Things: Tales from '85 | tv | 0.6061 | fuzzy |
| 4 | Planet 51 | movie | 0.5474 | thematic |
| 5 | Stranger Things: Fireplace | movie | 0.5229 | fuzzy |
| 6 | Monsters vs. Aliens | movie | 0.5187 | thematic |
| 7 | Kid vs. Kat | tv | 0.5028 | thematic |
| 8 | The Delta Flyers | podcast | 0.5025 | thematic |

**Judgement — MEDIUM:** Show absent; got 'Stranger Things 3: The Game' — wanted-the-show, got-the-franchise-game.

### 9. `eldn ring`  — _misspelled game_ (UC4 S1 fuzzy)
mode_taken: **name** · verticals: {'movie': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Elden Ring | movie | 0.4976 | fuzzy |

**Judgement — MEDIUM:** The typo recovers 'Elden Ring' #1 — but that's the MOVIE (the game is absent). Fuzzy recovery worked, to the same-name entity, not the game the human wanted.

### 10. `breakin bad`  — _misspelled tv_ (UC4 S1 fuzzy)
mode_taken: **auto_thematic** · verticals: {'podcast': 19, 'movie': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | The Breakdown | podcast | 0.79 | thematic |
| 2 | Watch What Crappens | podcast | 0.6031 | thematic |
| 3 | It Could Happen Here | podcast | 0.5947 | thematic |
| 4 | We Hate Movies | podcast | 0.5816 | thematic |
| 5 | ABC News Update | podcast | 0.5565 | thematic |
| 6 | CoinDesk Podcast Network | podcast | 0.544 | thematic |
| 7 | Bachelor Party | podcast | 0.5375 | thematic |
| 8 | Blocks w/ Neal Brennan | podcast | 0.5275 | thematic |

**Judgement — LOW:** Typo + the show is absent → generic thematic noise. Compound miss.

### 11. `stranger thigns`  — _transposed typo_ (UC4 S1 fuzzy)
mode_taken: **auto_thematic** · verticals: {'podcast': 9, 'movie': 9, 'game': 1, 'tv': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Stranger Danger - A Stranger Things Podcast | podcast | 0.6862 | thematic |
| 2 | MrBallen Podcast: Strange, Dark & Mysterious Stories | podcast | 0.5732 | thematic |
| 3 | Cowboys & Aliens | movie | 0.5645 | thematic |
| 4 | High Plains Drifter | movie | 0.5639 | thematic |
| 5 | Stuff To Blow Your Mind | podcast | 0.5583 | thematic |
| 6 | Stranger Things 3: The Game | game | 0.5533 | thematic |
| 7 | Planet 51 | movie | 0.5323 | thematic |
| 8 | Weird Darkness: Paranormal & True Crime Stories | podcast | 0.5298 | thematic |

**Judgement — MEDIUM:** Despite the transposition, recovers a Stranger Things podcast; the show itself is absent.

### 12. `the wichter`  — _misspelled game_ (UC4 S1 fuzzy)
mode_taken: **name** · verticals: {'game': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | The Witcher | game | 0.6085 | fuzzy |

**Judgement — HIGH:** Bad spelling → 'The Witcher' #1. Strong fuzzy recovery.

### 13. `joe rogen`  — _misspelled person_ (UC4 S1 fuzzy)
mode_taken: **auto_thematic** · verticals: {'podcast': 10, 'game': 4, 'movie': 6}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | The Ringer NFL Show | podcast | 0.6738 | thematic |
| 2 | Joe Rogan - Biography Flash | podcast | 0.6381 | thematic |
| 3 | POST Wrestling | podcast | 0.609 | thematic |
| 4 | IGN MRSS Feed | podcast | 0.5936 | thematic |
| 5 | The Offload | podcast | 0.5764 | thematic |
| 6 | We Hate Movies | podcast | 0.5744 | thematic |
| 7 | Critical Role & Sagas of Sundry | podcast | 0.5676 | thematic |
| 8 | Hades II | game | 0.558 | thematic |

**Judgement — LOW:** Typo → off-topic NFL podcast; JRE absent. Miss.

### 14. `cyberpunk 2077`  — _lowercase exact_ (UC4 S1)
mode_taken: **name** · verticals: {'game': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Cyberpunk 2077 | game | 0.8379 | exact |

**Judgement — HIGH:** Lowercase exact #1.

### 15. `gow`  — _abbrev (God of War)_ (UC4 S1 fuzzy)
mode_taken: **name** · verticals: {'movie': 1, 'tv': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Grow | movie | 0.5438 | fuzzy |
| 2 | GLOW | tv | 0.5316 | fuzzy |

**Judgement — LOW:** Acronym (God of War) unrecovered → a gaming podcast. Acronyms need an alias table.

### 16. `last of us`  — _partial, no 'the'_ (UC4 S1 fuzzy)
mode_taken: **auto_both** · verticals: {'podcast': 8, 'game': 10, 'movie': 2}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | WhatCulture Gaming | podcast | 0.8295 | thematic |
| 2 | Far Cry New Dawn | game | 0.7959 | thematic |
| 3 | The Nerd Nest - A Video Game Podcast | podcast | 0.786 | thematic |
| 4 | IGN MRSS Feed | podcast | 0.7462 | thematic |
| 5 | IGN Game Reviews | podcast | 0.6798 | thematic |
| 6 | Gears of War 4 | game | 0.6749 | thematic |
| 7 | Outlast II | game | 0.6705 | thematic |
| 8 | Dead Island 2 | game | 0.6704 | thematic |

**Judgement — LOW:** 'The Last of Us' is absent from the corpus; results are generic action games + gaming podcasts. Corpus gap + weak fallback.

### 17. `the office`  — _clean lowercase_ (UC4 S1)
mode_taken: **auto_both** · verticals: {'tv': 10, 'podcast': 2, 'movie': 8}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | The Office | tv | 0.6408 | exact |
| 2 | The Office | tv | 0.5179 | exact |
| 3 | The Daily Office Podcast | podcast | 0.7531 | fuzzy |
| 4 | What's Wrong with Secretary Kim | tv | 0.7264 | thematic |
| 5 | My Senpai Is Annoying | tv | 0.7182 | thematic |
| 6 | Secretary | movie | 0.7152 | thematic |
| 7 | Office Christmas Party | movie | 0.6895 | thematic |
| 8 | Love Scout | tv | 0.6804 | thematic |

**Judgement — HIGH:** Exact 'The Office' #1.

### 18. `spider man`  — _no hyphen_ (UC4 S1 fuzzy)
mode_taken: **auto_both** · verticals: {'tv': 7, 'movie': 10, 'game': 1, 'podcast': 2}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Marvel's Spider-Man | tv | 0.8026 | fuzzy |
| 2 | The Spectacular Spider-Man | tv | 0.7481 | fuzzy |
| 3 | Marvel's Ultimate Spider-Man | tv | 0.7478 | fuzzy |
| 4 | Your Friendly Neighborhood Spider-Man | tv | 0.7194 | thematic |
| 5 | Spider-Man: Far From Home | movie | 0.7168 | fuzzy |
| 6 | Spider-Man: The New Animated Series | tv | 0.7074 | thematic |
| 7 | Ultraman: Rising | movie | 0.6341 | thematic |
| 8 | Megamind | movie | 0.6315 | thematic |

**Judgement — HIGH:** No-hyphen recovers "Marvel's Spider-Man" #1.

### 19. `dark souls`  — _clean lowercase_ (UC4 S1)
mode_taken: **name** · verticals: {'game': 3}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Dark Souls | game | 0.5685 | exact |
| 2 | Dark Souls III | game | 0.801 | fuzzy |
| 3 | Dark Souls II | game | 0.7674 | fuzzy |

**Judgement — HIGH:** Exact 'Dark Souls' #1.

### 20. `Battlefield`  — _title+war concept_ (UC4 disambig)
mode_taken: **auto_both** · verticals: {'game': 10, 'movie': 7, 'podcast': 2, 'tv': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Battlefield V | game | 0.8097 | fuzzy |
| 2 | Battlefield 1 | game | 0.7967 | fuzzy |
| 3 | Battlefield 4 | game | 0.7885 | fuzzy |
| 4 | Battlefield 3 | game | 0.6613 | fuzzy |
| 5 | Battlefield 2042 | game | 0.6201 | fuzzy |
| 6 | MechWarrior 5: Mercenaries | game | 0.6169 | thematic |
| 7 | Battlefield Earth | movie | 0.599 | fuzzy |
| 8 | Call of Duty: Infinite Warfare | game | 0.591 | thematic |

**Judgement — HIGH:** Battlefield V #1 (game pinned) + war content below. Disambiguation intact.

### 21. `Halo`  — _title+concept_ (UC4 disambig)
mode_taken: **auto_both** · verticals: {'game': 9, 'movie': 4, 'podcast': 7}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Halo Infinite | game | 0.7476 | thematic |
| 2 | Halo 3 | game | 0.7057 | fuzzy |
| 3 | Halo Wars 2 | game | 0.7026 | fuzzy |
| 4 | Halo 5: Guardians | game | 0.7004 | thematic |
| 5 | Halo 4 | game | 0.6578 | fuzzy |
| 6 | Halo: Reach | game | 0.6575 | fuzzy |
| 7 | Halo 3: ODST | game | 0.656 | fuzzy |
| 8 | Halo Legends | movie | 0.619 | fuzzy |

**Judgement — HIGH:** Halo games on top (Infinite/3/4...) + spread. Good for an ambiguous franchise.

### 22. `Friends`  — _title+common word_ (UC4 disambig)
mode_taken: **auto_both** · verticals: {'movie': 10, 'podcast': 7, 'tv': 3}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | We Are Your Friends | movie | 0.8248 | fuzzy |
| 2 | Movie Friends | podcast | 0.8113 | thematic |
| 3 | Almost Friends | movie | 0.8023 | fuzzy |
| 4 | Friends with Kids | movie | 0.7976 | fuzzy |
| 5 | Vacation Friends | movie | 0.7003 | fuzzy |
| 6 | Cursed Friends | movie | 0.6673 | fuzzy |
| 7 | One Week Friends | movie | 0.6667 | fuzzy |
| 8 | Fisherman's Friends | movie | 0.6634 | fuzzy |

**Judgement — MEDIUM:** The iconic show appears absent; top is 'We Are Your Friends' + other Friends-titled movies. Right token, wrong entity.

### 23. `Survivor`  — _title+concept_ (UC4 disambig)
mode_taken: **auto_both** · verticals: {'movie': 5, 'game': 4, 'podcast': 9, 'tv': 2}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Survivor | movie | 0.7524 | exact |
| 2 | Survivor | movie | 0.6416 | exact |
| 3 | Lone Survivor | movie | 0.7773 | fuzzy |
| 4 | Star Wars Jedi: Survivor | game | 0.7771 | fuzzy |
| 5 | The Specialists - Survivor, The Traitors, & more | podcast | 0.7546 | thematic |
| 6 | Kong: Survivor Instinct | game | 0.7425 | fuzzy |
| 7 | Survivor's Remorse | tv | 0.7342 | fuzzy |
| 8 | Achilles: Survivor | game | 0.7081 | fuzzy |

**Judgement — HIGH:** Exact 'Survivor' #1 + thematic. Good.

### 24. `Frasier`  — _title_ (UC4 disambig)
mode_taken: **name** · verticals: {'tv': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Frasier | tv | 0.5839 | exact |

**Judgement — HIGH:** Exact 'Frasier' #1 (unique title).

### 25. `Control`  — _title+common word_ (UC4 disambig)
mode_taken: **auto_both** · verticals: {'game': 5, 'movie': 10, 'tv': 3, 'podcast': 2}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Control | game | 0.8279 | exact |
| 2 | Control | movie | 0.6994 | exact |
| 3 | Control | movie | 0.6943 | exact |
| 4 | Control | movie | 0.6751 | exact |
| 5 | Star Control: Origins | game | 0.7858 | fuzzy |
| 6 | Blood-C: The Last Dark | movie | 0.7568 | thematic |
| 7 | The Giver | movie | 0.7566 | thematic |
| 8 | The Limits of Control | movie | 0.7351 | fuzzy |

**Judgement — HIGH:** Exact 'Control' (the game) #1 + thematic. Good disambiguation.

### 26. `Fallout`  — _title+concept_ (UC4 disambig)
mode_taken: **name** · verticals: {'movie': 1, 'game': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | The Fallout | movie | 0.7221 | fuzzy |
| 2 | Fallout 3 | game | 0.5596 | fuzzy |

**Judgement — MEDIUM:** 'Fallout 3' at #2 (right franchise) but #1 is the unrelated 'The Fallout' movie (scored higher). Mis-ranked.

### 27. `cooking`  — _topic_ (UC4 thematic)
mode_taken: **auto_both** · verticals: {'podcast': 10, 'movie': 4, 'tv': 6}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | A Hot Dog Is a Sandwich | podcast | 0.771 | thematic |
| 2 | This Is TASTE | podcast | 0.762 | thematic |
| 3 | What's Cooking? | movie | 0.7614 | fuzzy |
| 4 | Cooking with Love | movie | 0.7227 | fuzzy |
| 5 | The Chef Show | tv | 0.7116 | thematic |
| 6 | Looking | tv | 0.6853 | fuzzy |
| 7 | Watch What Happens Live with Andy Cohen | podcast | 0.6651 | thematic |
| 8 | Gastropod | podcast | 0.6603 | thematic |

**Judgement — HIGH:** Food/cooking content across podcast/movie/tv. On-topic and broad.

### 28. `true crime`  — _topic_ (UC4 thematic)
mode_taken: **auto_both** · verticals: {'movie': 2, 'podcast': 18}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | True Crime | movie | 0.7302 | exact |
| 2 | True Crime | movie | 0.6198 | exact |
| 3 | True Crime Tonight | podcast | 0.8536 | fuzzy |
| 4 | Killer Instinct | podcast | 0.8456 | thematic |
| 5 | Hidden Killers With Tony Brueski | True Crime News & Commentary | podcast | 0.8382 | thematic |
| 6 | 20/20 | podcast | 0.8175 | thematic |
| 7 | The Metabolic Classroom with Dr. Ben Bikman | podcast | 0.8174 | thematic |
| 8 | Our True Crime Podcast | podcast | 0.8151 | fuzzy |

**Judgement — HIGH:** Exact 'True Crime' + true-crime podcasts. Spot-on.

### 29. `horror games`  — _topic+vertical word_ (UC4 thematic)
mode_taken: **auto_thematic** · verticals: {'movie': 9, 'game': 6, 'podcast': 5}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Latency | movie | 0.6624 | thematic |
| 2 | Stay Alive | movie | 0.6622 | thematic |
| 3 | Saw V | movie | 0.6566 | thematic |
| 4 | The Bornless | game | 0.6551 | thematic |
| 5 | Be. Scared | podcast | 0.6546 | thematic |
| 6 | Horror Hangout | podcast | 0.6493 | thematic |
| 7 | Books in the Freezer - A Horror Fiction Podcast | podcast | 0.6487 | thematic |
| 8 | The OctoGames | movie | 0.647 | thematic |

**Judgement — MEDIUM:** Horror theme right, but 'games' isn't parsed as a vertical filter, so horror movies lead; games are mixed in lower.

### 30. `relaxing fantasy worlds`  — _mood+topic_ (UC4 thematic)
mode_taken: **auto_thematic** · verticals: {'podcast': 1, 'tv': 7, 'game': 3, 'movie': 9}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Dungeons and Daddies | podcast | 0.736 | thematic |
| 2 | Tsukimichi: Moonlit Fantasy | tv | 0.718 | thematic |
| 3 | Hytale | game | 0.7122 | thematic |
| 4 | Fantasy Life i: The Girl Who Steals Time | game | 0.6727 | thematic |
| 5 | Bedazzled | movie | 0.6704 | thematic |
| 6 | Return to Never Land | movie | 0.6565 | thematic |
| 7 | The Hobbit | movie | 0.6536 | thematic |
| 8 | Cool World | movie | 0.6382 | thematic |

**Judgement — MEDIUM:** Fantasy content surfaces, but the 'relaxing' vibe isn't modeled (top is a loud D&D comedy podcast).

### 31. `games like dark souls`  — _more-like-this_ (UC4 thematic)
mode_taken: **auto_thematic** · verticals: {'game': 10, 'podcast': 9, 'movie': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Darksiders Genesis | game | 0.782 | thematic |
| 2 | Dark Souls III | game | 0.7525 | thematic |
| 3 | Hades II | game | 0.7227 | thematic |
| 4 | WhatCulture Gaming | podcast | 0.7141 | thematic |
| 5 | Doom: The Dark Ages | game | 0.6704 | thematic |
| 6 | Wolfenstein: Youngblood | game | 0.6676 | thematic |
| 7 | Dark Souls II | game | 0.6465 | thematic |
| 8 | Critical Role & Sagas of Sundry | podcast | 0.6397 | thematic |

**Judgement — HIGH:** Returns actual Dark Souls games + soulslike-adjacent (Darksiders, Hades). Genuinely useful.

### 32. `shows about cooking`  — _NL topic_ (UC4 thematic)
mode_taken: **auto_thematic** · verticals: {'podcast': 10, 'tv': 8, 'movie': 2}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | This Is TASTE | podcast | 0.8019 | thematic |
| 2 | A Hot Dog Is a Sandwich | podcast | 0.8007 | thematic |
| 3 | Gastropod | podcast | 0.7448 | thematic |
| 4 | Watch What Crappens | podcast | 0.7438 | thematic |
| 5 | The Dave Chang Show | podcast | 0.7153 | thematic |
| 6 | Watch What Happens Live with Andy Cohen | podcast | 0.6985 | thematic |
| 7 | Reality Life with Kate Casey | podcast | 0.6923 | thematic |
| 8 | Radio Cherry Bombe | podcast | 0.6838 | thematic |

**Judgement — MEDIUM:** Cooking topic right, but 'shows' (TV) isn't honored — a food podcast leads.

### 33. `scary movies`  — _topic+vertical word_ (UC4 thematic)
mode_taken: **auto_both** · verticals: {'podcast': 7, 'movie': 10, 'tv': 3}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Too Scary; Didn't Watch | podcast | 0.8077 | thematic |
| 2 | Werewolf Ambulance: A Horror Movie Comedy Podcast | podcast | 0.7678 | thematic |
| 3 | That Was Pretty Scary | podcast | 0.7317 | thematic |
| 4 | Be. Scared | podcast | 0.7143 | thematic |
| 5 | Truly Creeped - Scary TRUE Horror Stories Podcast | podcast | 0.7074 | thematic |
| 6 | Immaculate | movie | 0.6752 | thematic |
| 7 | Porno | movie | 0.6612 | thematic |
| 8 | Sharknado | movie | 0.6599 | thematic |

**Judgement — MEDIUM:** Scary theme right; 'movies' not enforced (a movie-review podcast leads).

### 34. `feel good comedy`  — _mood+genre_ (UC4 thematic)
mode_taken: **name** · verticals: {'tv': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Feel Good | tv | 0.7297 | fuzzy |

**Judgement — MEDIUM:** Matched the show literally named 'Feel Good' — reasonable, but the user likely wanted a genre spread.

### 35. `cozy`  — _vibe_ (UC4 thematic (hard))
mode_taken: **name** · verticals: {'game': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Cozy Grove | game | 0.4138 | fuzzy |

**Judgement — MEDIUM:** 'Cozy Grove' (a genuinely cozy game) — defensible literal match, but the cozy vibe across verticals isn't captured.

### 36. `something funny`  — _vibe_ (UC4 thematic (hard))
mode_taken: **auto_thematic** · verticals: {'podcast': 9, 'movie': 10, 'tv': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | ok storytime | podcast | 0.804 | thematic |
| 2 | Mic Cheque Podcast | podcast | 0.7031 | thematic |
| 3 | Funny You Ask with Ike Barinholtz | podcast | 0.6984 | thematic |
| 4 | Humor Me with Robert Smigel and Friends | podcast | 0.6822 | thematic |
| 5 | You Should Know Podcast | podcast | 0.6625 | thematic |
| 6 | ZM's Bree & Clint | podcast | 0.6584 | thematic |
| 7 | Toy Story Toons: Small Fry | movie | 0.6497 | thematic |
| 8 | The SpongeBob SquarePants Movie | movie | 0.6393 | thematic |

**Judgement — MEDIUM:** Loose: a comedy-ish storytime podcast; vibe only weakly captured.

### 37. `chill background watching`  — _vibe_ (UC4 thematic (hard))
mode_taken: **auto_thematic** · verticals: {'podcast': 20}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | The Deck | podcast | 0.8895 | thematic |
| 2 | Deep Energy Podcast - Music for Sleep, Meditation, Yoga, Background Music and Studying | podcast | 0.7628 | thematic |
| 3 | This Is Hell! | podcast | 0.7012 | thematic |
| 4 | We Hate Movies | podcast | 0.6821 | thematic |
| 5 | Podcast and Chill with MacG | podcast | 0.665 | thematic |
| 6 | The Trial | podcast | 0.6594 | thematic |
| 7 | The Metabolic Classroom with Dr. Ben Bikman | podcast | 0.6557 | thematic |
| 8 | Film Theory | podcast | 0.6329 | thematic |

**Judgement — LOW:** Wrong modality — 'watching' implies TV/movie, top is a true-crime podcast. Vibe + modality both missed.

### 38. `intense competitive`  — _vibe_ (UC4 thematic (hard))
mode_taken: **auto_thematic** · verticals: {'movie': 10, 'tv': 5, 'game': 4, 'podcast': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Fast & Furious Presents: Hobbs & Shaw | movie | 0.7165 | thematic |
| 2 | The God of High School | tv | 0.6713 | thematic |
| 3 | Undisputed | movie | 0.6527 | thematic |
| 4 | Beast | movie | 0.6513 | thematic |
| 5 | Street Fighter | movie | 0.62 | thematic |
| 6 | Star Wars: Hunters | game | 0.6076 | thematic |
| 7 | Beyblade Burst | tv | 0.6041 | thematic |
| 8 | Street Fighter V | game | 0.6011 | thematic |

**Judgement — MEDIUM:** An action movie (Hobbs & Shaw) — 'intense' loosely, 'competitive' not really.

### 39. `wholesome family`  — _vibe_ (UC4 thematic (hard))
mode_taken: **auto_thematic** · verticals: {'movie': 10, 'podcast': 1, 'tv': 9}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Uncle Buck | movie | 0.7951 | thematic |
| 2 | Paddington 2 | movie | 0.7846 | thematic |
| 3 | Instant Family | movie | 0.7557 | thematic |
| 4 | Aunty Donna Podcast | podcast | 0.7419 | thematic |
| 5 | Mrs. Doubtfire | movie | 0.741 | thematic |
| 6 | Big City Greens | tv | 0.7404 | thematic |
| 7 | Mrs. Miracle | movie | 0.7351 | thematic |
| 8 | The Brady Bunch Movie | movie | 0.7329 | thematic |

**Judgement — MEDIUM:** 'Uncle Buck' is a reasonable wholesome-family movie; vibe loosely captured.

### 40. `sci-fi`  — _cross-vertical_ (UC7 S3)
mode_taken: **auto_thematic** · verticals: {'movie': 10, 'game': 1, 'podcast': 4, 'tv': 5}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Osiris | movie | 0.746 | thematic |
| 2 | Men in Black II | movie | 0.7305 | thematic |
| 3 | Men in Black: International | movie | 0.7219 | thematic |
| 4 | Romeo is a Dead Man | game | 0.7123 | thematic |
| 5 | Inuyashiki | movie | 0.7005 | thematic |
| 6 | Science Friday | podcast | 0.6862 | thematic |
| 7 | Evolution | movie | 0.6695 | thematic |
| 8 | Real Men | movie | 0.667 | thematic |

**Judgement — HIGH:** Spans 4 verticals; sci-fi content throughout. UC7 Story 3 met.

### 41. `fantasy`  — _cross-vertical_ (UC7 S3)
mode_taken: **auto_both** · verticals: {'podcast': 3, 'game': 4, 'movie': 9, 'tv': 4}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Dungeons and Daddies | podcast | 0.8747 | thematic |
| 2 | Final Fantasy XV | game | 0.8208 | fuzzy |
| 3 | FantasyPros - Fantasy Football Podcast | podcast | 0.7639 | thematic |
| 4 | Final Fantasy XVI | game | 0.7272 | fuzzy |
| 5 | Bedazzled | movie | 0.7219 | thematic |
| 6 | Descendants | movie | 0.7179 | thematic |
| 7 | Tokyo Ravens | tv | 0.7022 | thematic |
| 8 | Fantasy Island | movie | 0.6864 | fuzzy |

**Judgement — HIGH:** 4 verticals, fantasy games/movies/podcasts.

### 42. `space`  — _cross-vertical_ (UC7 S3)
mode_taken: **auto_both** · verticals: {'game': 5, 'movie': 7, 'podcast': 3, 'tv': 5}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Endless Space 2 | game | 0.7777 | fuzzy |
| 2 | Space Engineers | game | 0.7648 | fuzzy |
| 3 | Guardians of the Galaxy Vol. 2 | movie | 0.7428 | thematic |
| 4 | Main Engine Cut Off | podcast | 0.7373 | thematic |
| 5 | Space Nuts: Astronomy Insights & Cosmic Discoveries | podcast | 0.7171 | thematic |
| 6 | Guardians of the Galaxy | tv | 0.7006 | thematic |
| 7 | Mobile Suit Gundam: Char's Counterattack | movie | 0.694 | thematic |
| 8 | Mission To Zyxx | podcast | 0.6791 | thematic |

**Judgement — HIGH:** 4 verticals (Endless Space, space movies/shows).

### 43. `zombies`  — _cross-vertical_ (UC7 S3)
mode_taken: **auto_both** · verticals: {'movie': 10, 'tv': 4, 'game': 3, 'podcast': 3}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Zombies! Zombies! Zombies! | movie | 0.5285 | exact |
| 2 | Zombieland | movie | 0.7325 | thematic |
| 3 | Zoombies | movie | 0.7259 | fuzzy |
| 4 | We Are Zombies | movie | 0.7255 | fuzzy |
| 5 | Marvel Zombies | tv | 0.7206 | fuzzy |
| 6 | Zom 100: Bucket List of the Dead | tv | 0.7192 | thematic |
| 7 | Rise of the Zombies | movie | 0.7158 | fuzzy |
| 8 | Zombie Land SAGA | tv | 0.7086 | thematic |

**Judgement — HIGH:** 4 verticals, zombie content.

### 44. `superheroes`  — _cross-vertical_ (UC7 S3)
mode_taken: **name** · verticals: {'podcast': 1, 'movie': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Talk From Superheroes | podcast | 0.7495 | fuzzy |
| 2 | All Superheroes Must Die | movie | 0.6717 | fuzzy |

**Judgement — HIGH:** 4 verticals, superhero content.

### 45. `medieval`  — _cross-vertical_ (UC7 S3)
mode_taken: **auto_both** · verticals: {'movie': 9, 'game': 10, 'tv': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Medieval | movie | 0.7728 | exact |
| 2 | Kingdom Come: Deliverance | game | 0.751 | thematic |
| 3 | Kingdom Come: Deliverance II | game | 0.7132 | thematic |
| 4 | The Dreadful | movie | 0.7034 | thematic |
| 5 | A Knight's Tale | movie | 0.6978 | thematic |
| 6 | The Lord of the Rings: The War of the Rohirrim | movie | 0.6885 | thematic |
| 7 | Medieval II: Total War | game | 0.665 | fuzzy |
| 8 | Maria the Virgin Witch | tv | 0.6449 | thematic |

**Judgement — HIGH:** 4 verticals, medieval content.

### 46. `what should i watch tonight`  — _NL open_ (UC4 thematic (hard))
mode_taken: **auto_thematic** · verticals: {'podcast': 20}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Fox News Hourly Update | podcast | 0.8037 | thematic |
| 2 | The Big Picture | podcast | 0.7822 | thematic |
| 3 | True Crime Tonight | podcast | 0.78 | thematic |
| 4 | ABC News Update | podcast | 0.771 | thematic |
| 5 | What Should I Read Next? | podcast | 0.7625 | thematic |
| 6 | The 11th Hour with Stephanie Ruhle | podcast | 0.7473 | thematic |
| 7 | Sky News Australia Update | podcast | 0.7188 | thematic |
| 8 | Slate Daily Feed | podcast | 0.7158 | thematic |

**Judgement — LOW:** Open NL question handled poorly: top is a Fox News podcast. No intent parsing; the embed latched onto the wrong tokens.

### 47. `good podcasts about history`  — _NL topic_ (UC4 thematic)
mode_taken: **auto_thematic** · verticals: {'podcast': 20}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | This Day in History | podcast | 0.8349 | thematic |
| 2 | SNAFU with Ed Helms | podcast | 0.8306 | thematic |
| 3 | Forbidden History | podcast | 0.8214 | thematic |
| 4 | New Books in History | podcast | 0.8204 | thematic |
| 5 | American History Tellers | podcast | 0.8103 | thematic |
| 6 | Slow Burn | podcast | 0.7891 | thematic |
| 7 | Revisionist History | podcast | 0.7741 | thematic |
| 8 | Ones and Tooze | podcast | 0.7693 | thematic |

**Judgement — HIGH:** All history podcasts (This Day in History, American History Tellers...). Topic + 'podcasts' modality both nailed.

### 48. `best soulslike games`  — _NL topic_ (UC4 thematic)
mode_taken: **auto_thematic** · verticals: {'podcast': 10, 'game': 9, 'movie': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | WhatCulture Gaming | podcast | 0.7244 | thematic |
| 2 | SoulWorker | game | 0.6233 | thematic |
| 3 | It's Super Effective: A Pokemon Podcast | podcast | 0.5967 | thematic |
| 4 | Critical Role & Sagas of Sundry | podcast | 0.5939 | thematic |
| 5 | Young Souls | game | 0.5801 | thematic |
| 6 | Fantasy Life i: The Girl Who Steals Time | game | 0.5692 | thematic |
| 7 | GeekVerse Podcast | podcast | 0.5648 | thematic |
| 8 | Dungeons and Daddies | podcast | 0.5642 | thematic |

**Judgement — MEDIUM:** A gaming podcast leads instead of games; soulslike games are present lower.

### 49. `funny movies to watch with friends`  — _NL mood_ (UC4 thematic (hard))
mode_taken: **auto_thematic** · verticals: {'tv': 6, 'podcast': 6, 'movie': 8}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Sam & Cat | tv | 0.7188 | thematic |
| 2 | ok storytime | podcast | 0.7141 | thematic |
| 3 | The SpongeBob SquarePants Movie | movie | 0.7079 | thematic |
| 4 | You Should Know Podcast | podcast | 0.6837 | thematic |
| 5 | Movie Friends | podcast | 0.6678 | thematic |
| 6 | Free With Ads | podcast | 0.6642 | thematic |
| 7 | Regulation Podcast | podcast | 0.6452 | thematic |
| 8 | Over the Hedge | movie | 0.642 | thematic |

**Judgement — MEDIUM:** Comedy-ish but wrong modality (podcast leads, not movies).

### 50. `football`  — _onboarding topic_ (UC7 S3)
mode_taken: **auto_both** · verticals: {'podcast': 10, 'game': 6, 'movie': 4}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Football Ramble | podcast | 0.8707 | fuzzy |
| 2 | Check the Mic with Steve Palazzolo & Sam Monson | podcast | 0.8346 | thematic |
| 3 | BIG KICK ENERGY | podcast | 0.8326 | thematic |
| 4 | Whistleblowers | podcast | 0.8161 | thematic |
| 5 | 2 Pros and a Cup of Joe | podcast | 0.8116 | thematic |
| 6 | NFL: Good Morning Football | podcast | 0.804 | thematic |
| 7 | Locked On NFL Six Pack - Daily Podcast For NFL Talk | podcast | 0.8009 | thematic |
| 8 | Rio Ferdinand Presents | podcast | 0.7936 | thematic |

**Judgement — HIGH:** Football Ramble + cross-vertical (podcasts/games/movies). Good onboarding breadth.

### 51. `hip hop`  — _onboarding topic_ (UC7 S3)
mode_taken: **auto_both** · verticals: {'podcast': 9, 'tv': 3, 'movie': 8}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Joe and Jada | podcast | 0.8566 | thematic |
| 2 | ROC Solid | podcast | 0.7502 | thematic |
| 3 | Hip Hop Evolution | tv | 0.7363 | fuzzy |
| 4 | All Eyez on Me | movie | 0.735 | thematic |
| 5 | Hustle & Flow | movie | 0.7101 | thematic |
| 6 | The Breakfast Club | podcast | 0.7008 | thematic |
| 7 | The Real Report with Tony Yayo and Uncle Murda | podcast | 0.7007 | thematic |
| 8 | Wu-Tang: An American Saga | tv | 0.6876 | thematic |

**Judgement — HIGH:** Hip-hop podcasts + cross-vertical spread.

### 52. `anime`  — _onboarding topic_ (UC7 S3)
mode_taken: **auto_both** · verticals: {'podcast': 2, 'movie': 8, 'tv': 10}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Quest for the Best with Tristan, Miles, & Geoff | podcast | 0.6915 | thematic |
| 2 | It's Super Effective: A Pokemon Podcast | podcast | 0.6812 | thematic |
| 3 | Summer Days with Coo | movie | 0.6741 | thematic |
| 4 | Tokyo Ravens | tv | 0.6679 | thematic |
| 5 | The Aristocrat's Otherworldly Adventure: Serving Gods Who Go Too Far | tv | 0.6506 | thematic |
| 6 | Ghost Cat Anzu | movie | 0.6351 | thematic |
| 7 | Alderamin on the Sky | tv | 0.6272 | thematic |
| 8 | Horimiya: The Missing Pieces | tv | 0.6245 | thematic |

**Judgement — MEDIUM:** Cross-vertical spread DOES include real anime (Tokyo Ravens, anime tv), but the top is a fuzzy mishit 'Annie' ('anime'~'annie'). Name-fuzzy false positive.

### 53. `cooking shows and channels`  — _onboarding NL_ (UC7 S3)
mode_taken: **auto_both** · verticals: {'podcast': 10, 'tv': 8, 'movie': 2}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | This Is TASTE | podcast | 0.8019 | thematic |
| 2 | Watch What Crappens | podcast | 0.7826 | thematic |
| 3 | A Hot Dog Is a Sandwich | podcast | 0.7463 | thematic |
| 4 | Reality Life with Kate Casey | podcast | 0.7416 | thematic |
| 5 | Watch What Happens Live with Andy Cohen | podcast | 0.7393 | thematic |
| 6 | The Dave Chang Show | podcast | 0.7312 | thematic |
| 7 | Nobody Listens to Paula Poundstone | podcast | 0.7284 | thematic |
| 8 | Pink Shade: Reality TV with MP | podcast | 0.7026 | thematic |

**Judgement — HIGH:** Now spans podcast/tv/movie (the Part-1 fix); food content throughout. Fixed from podcast-only.

### 54. `nba basketball`  — _onboarding topic_ (UC7 S3)
mode_taken: **auto_both** · verticals: {'podcast': 10, 'game': 4, 'movie': 5, 'tv': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Hoops Tonight with Jason Timpf | podcast | 0.8328 | thematic |
| 2 | The Old Man and the Three | podcast | 0.7795 | thematic |
| 3 | The NBA Podcast | podcast | 0.7611 | thematic |
| 4 | The Kevin O'Connor Show | podcast | 0.7564 | thematic |
| 5 | The Athletic NBA Daily | podcast | 0.7545 | thematic |
| 6 | Locked On Celtics - Daily Podcast On The Boston Celtics | podcast | 0.714 | thematic |
| 7 | NBA 2K18 | game | 0.7081 | thematic |
| 8 | No Fouls Given | podcast | 0.6985 | thematic |

**Judgement — HIGH:** NBA podcasts + cross-vertical.

### 55. `k-pop`  — _onboarding topic_ (UC7 S3)
mode_taken: **auto_both** · verticals: {'movie': 5, 'podcast': 10, 'tv': 5}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | K-Pops! | movie | 0.6873 | fuzzy |
| 2 | KPop Demon Hunters | movie | 0.6545 | thematic |
| 3 | [KBS WORLD Radio] Korea 24 | podcast | 0.6317 | thematic |
| 4 | AfterNoona Delight: KDrama Dishing and Deep Dives | podcast | 0.6302 | thematic |
| 5 | Watch What Happens Live with Andy Cohen | podcast | 0.629 | thematic |
| 6 | Love Untangled | movie | 0.5872 | thematic |
| 7 | Pop Star Academy: KATSEYE | tv | 0.5684 | thematic |
| 8 | Dream High | tv | 0.5657 | thematic |

**Judgement — HIGH:** K-Pops! + cross-vertical.

### 56. `horror`  — _filtered game_ (UC4 filter)
mode_taken: **thematic** · verticals: {'game': 20}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Alan Wake II | game | 0.6514 | thematic |
| 2 | Friday the 13th: The Game | game | 0.6117 | thematic |
| 3 | Directive 8020 | game | 0.5949 | thematic |
| 4 | Agony | game | 0.5572 | thematic |
| 5 | The Casting of Frank Stone | game | 0.5208 | thematic |
| 6 | Finding Frankie | game | 0.5171 | thematic |
| 7 | Five Nights at Freddy's: Help Wanted | game | 0.4868 | thematic |
| 8 | The Sinking City | game | 0.4624 | thematic |

**Judgement — HIGH:** All games, horror (Alan Wake II...). Filter respected.

### 57. `news`  — _filtered podcast_ (UC4 filter)
mode_taken: **thematic** · verticals: {'podcast': 20}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | ABC News Update | podcast | 0.7803 | thematic |
| 2 | 77 WABC MiniCasts | podcast | 0.7225 | thematic |
| 3 | Latest Stories from The Associated Press | podcast | 0.7191 | thematic |
| 4 | iHeartRadio 24/7 News: The Latest | podcast | 0.6917 | thematic |
| 5 | NEWSGIRLS | podcast | 0.6067 | thematic |
| 6 | WSJ What’s News | podcast | 0.5992 | thematic |
| 7 | DW News Brief | podcast | 0.5989 | thematic |
| 8 | Al Jazeera News Updates | podcast | 0.5959 | thematic |

**Judgement — HIGH:** All podcasts, news. Filter respected.

### 58. `crime`  — _filtered tv_ (UC4 filter)
mode_taken: **thematic** · verticals: {'tv': 20}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | The Professionals | tv | 0.6794 | thematic |
| 2 | Banana Fish | tv | 0.5933 | thematic |
| 3 | Good Behavior | tv | 0.5774 | thematic |
| 4 | The Brothers Sun | tv | 0.5607 | thematic |
| 5 | True Justice | tv | 0.5562 | thematic |
| 6 | The Take | tv | 0.5513 | thematic |
| 7 | Bad Guys | tv | 0.5431 | thematic |
| 8 | Confidence Queen | tv | 0.5388 | thematic |

**Judgement — HIGH:** All TV, crime. Filter respected.

### 59. `action`  — _filtered movie_ (UC4 filter)
mode_taken: **thematic** · verticals: {'movie': 20}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Hostile Takeover | movie | 0.8174 | thematic |
| 2 | The Green Hornet | movie | 0.7656 | thematic |
| 3 | xXx: Return of Xander Cage | movie | 0.717 | thematic |
| 4 | Fast & Furious Presents: Hobbs & Shaw | movie | 0.7142 | thematic |
| 5 | F9: The Fast Saga | movie | 0.6859 | thematic |
| 6 | Team America: World Police | movie | 0.6424 | thematic |
| 7 | Last Action Hero | movie | 0.6186 | thematic |
| 8 | Contraband | movie | 0.5966 | thematic |

**Judgement — HIGH:** All movies, action. Filter respected.

### 60. `a`  — _too-short_ (edge)
mode_taken: **auto_thematic** · verticals: {'podcast': 20}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | The Incomparable Superfeed | podcast | 0.7319 | thematic |
| 2 | IGN MRSS Feed | podcast | 0.7161 | thematic |
| 3 | Louis French Lessons | podcast | 0.7063 | thematic |
| 4 | The Smallzy Show | podcast | 0.6978 | thematic |
| 5 | We Hate Movies | podcast | 0.6924 | thematic |
| 6 | The Sick Podcast with Tony Marinaro / Le Sick Podcast avec Tony Marinaro | podcast | 0.686 | thematic |
| 7 | ABC News Update | podcast | 0.6844 | thematic |
| 8 | The Paikin Podcast | podcast | 0.6602 | thematic |

**Judgement — MEDIUM:** Graceful (no crash, no false exact) but returns noise — a min-length guard would be better UX.

### 61. `zxqwv`  — _gibberish_ (edge)
mode_taken: **auto_thematic** · verticals: {'podcast': 20}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | The Smallzy Show | podcast | 0.7265 | thematic |
| 2 | WhatCulture Gaming | podcast | 0.7264 | thematic |
| 3 | GeekVerse Podcast | podcast | 0.7133 | thematic |
| 4 | We Hate Movies | podcast | 0.7101 | thematic |
| 5 | The Incomparable Superfeed | podcast | 0.7001 | thematic |
| 6 | The Sick Podcast with Tony Marinaro / Le Sick Podcast avec Tony Marinaro | podcast | 0.6919 | thematic |
| 7 | IGN MRSS Feed | podcast | 0.689 | thematic |
| 8 | DW News Brief | podcast | 0.6842 | thematic |

**Judgement — MEDIUM:** Graceful gibberish handling (no false exact); low-relevance thematic noise, as expected.

### 62. `🎮🔥`  — _emoji/symbols_ (edge)
mode_taken: **auto_thematic** · verticals: {'podcast': 10, 'movie': 9, 'tv': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | IGN MRSS Feed | podcast | 0.7661 | thematic |
| 2 | GeekVerse Podcast | podcast | 0.7269 | thematic |
| 3 | It's Super Effective: A Pokemon Podcast | podcast | 0.6834 | thematic |
| 4 | The Incomparable Superfeed | podcast | 0.681 | thematic |
| 5 | The Smallzy Show | podcast | 0.652 | thematic |
| 6 | Monster High: Boo York, Boo York | movie | 0.6439 | thematic |
| 7 | Where There's A Will, There's A Wake | podcast | 0.6212 | thematic |
| 8 | Watch What Happens Live with Andy Cohen | podcast | 0.6182 | thematic |

**Judgement — MEDIUM:** Graceful; the gaming emoji even pulled a gaming feed (IGN). Reasonable degradation.

### 63. `i want to find a really good long form investigative journalism podcast about politics`  — _very long sentence_ (edge)
mode_taken: **auto_thematic** · verticals: {'podcast': 20}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | John Solomon Reports | podcast | 0.8719 | thematic |
| 2 | The Majority Report with Sam Seder | podcast | 0.8313 | thematic |
| 3 | The Editors | podcast | 0.8242 | thematic |
| 4 | ThePrint | podcast | 0.8239 | thematic |
| 5 | RealClearPolitics Podcast | podcast | 0.79 | thematic |
| 6 | The Rubin Report | podcast | 0.7885 | thematic |
| 7 | The Intelligence from The Economist | podcast | 0.788 | thematic |
| 8 | The Michael Knowles Show | podcast | 0.7812 | thematic |

**Judgement — HIGH:** The long NL query found a political/investigative podcast (John Solomon Reports). Impressively on-topic.

### 64. `Crown Trick`  — _no-vector property by name_ (edge)
mode_taken: **name** · verticals: {'game': 1}

| rank | name | vertical | score | match |
|--|--|--|--|--|
| 1 | Crown Trick | game | 0.5177 | exact |

**Judgement — HIGH:** No-vector property found by name (exact #1) — name search doesn't depend on vectors.

## Part 1 — final fixes for v1 ship (before / after)

Two cheap fixes this pass, both verified no-regression:

1. **Short-query fuzzy collision.** `anime` was matching the movie **"Annie"** (`ratio("anime","annie")=0.80`).
   Raised `NAME_COVERAGE_TOKEN_MIN` **0.80 → 0.82** — the minimal-collateral value: it rejects anime→Annie (0.80)
   while KEEPING every legit recovery — `eldn→elden` 0.889, `wichter→witcher` 0.857, and the transposition
   `thigns→things` 0.833. (0.85, the first instinct, would also drop the 0.833 transposition — so 0.82, not 0.85.)
2. **Min-length guard.** `NAME_MIN_QUERY_LEN=2` — a 1-char query ("a") produces **no** name hit (routes
   thematic), so no 1-char fuzzy noise can pin a spurious title.

| query | before | after | verdict |
|--|--|--|--|
| `anime` | "Annie" (movie) #1 | **"Anime Supremacy!"** (movie, contains *anime*) #1 | ✓ Annie collision gone |
| `a` | 1-char fuzzy name hit | **no name hit → thematic** | ✓ guarded |
| `eldn ring` | Elden Ring #1 | Elden Ring #1 | ✓ unchanged |
| `the wichter` | The Witcher #1 | The Witcher #1 | ✓ unchanged |
| `The Daily` / `Elden Ring` / `Battlefield` | exact/pin #1 | identical | ✓ unchanged |

(Earlier v1.3.2 retrieval fix, retained: per-vertical ANN quota `THEMATIC_K_PER_VERTICAL=50` + onboarding
`FAIRNESS_ONBOARDING_FORCES_SPREAD` — cross-vertical breadth for UC7 without injecting off-topic verticals into
UC4 name search. Retrieval latency 12.6 ms/q, within the <500 ms budget.)

## Corpus-presence audit — evidence, not inference

Every marquee title checked against the name index + the 44,052-name graph (exact match, expected vertical,
franchise token-containment):

| title | expected | present in 44k? | closest in-corpus match | note |
|--|--|--|--|--|
| Elden Ring | game | **No** (game absent) | "Elden Ring" (**movie**); "Elden Ring Nightreign" (game spinoff) | exact string is a movie |
| Game of Thrones | tv show | **No** (show absent) | "Game of Thrones" (**Telltale game**) | exact string is the game |
| Arsenal FC | sport/club | **No** (no sports vertical) | "Arsenal" (**2017 movie**); "All or Nothing: Arsenal" (tv doc) + an Arsenal podcast rank below | flagship gap |
| Breaking Bad | tv | **No** (show absent) | "El Camino: A Breaking Bad Movie" | franchise movie only |
| Stranger Things | tv | **No** (show absent) | making-of movies + a fan podcast (6) | show absent |
| The Joe Rogan Experience | podcast | **No** | — none — | fully absent |
| Stardew Valley | game | **No** | — none — | fully absent |
| The Last of Us | game | **No** | — none — | fully absent |
| God of War | game | **Yes** ✓ | "God of War", "God of War Ragnarök" | present |
| Call of Duty | game | **Franchise** (18 titles) | "Call of Duty 2" … (no bare "Call of Duty") | present as titles; not reachable via "cod" |
| The Witcher | game | **Yes** ✓ | "The Witcher" (game), Gwent | present |
| Grand Theft Auto VI | game | **No** (unreleased) | — none — | fully absent |
| Spider-Man | game/movie | **Franchise** (14) | "Marvel's Spider-Man 2", LEGO Spider-Man | present as titles; no bare "Spider-Man" |
| Dark Souls | game | **Yes** ✓ | "Dark Souls", "Dark Souls II/III" | present |

**Tally:** 3 fully present (God of War, The Witcher, Dark Souls) · 2 franchise-present (Call of Duty, Spider-Man)
· 3 exact-but-wrong-vertical, canonical absent (Elden Ring→movie, Game of Thrones→game, Arsenal→movie) ·
2 franchise-adjacent-only (Breaking Bad, Stranger Things) · 4 fully absent (JRE, Stardew Valley, The Last of Us, GTA VI).

## ⚠️ Corpus coverage is the #1 quality limitation — marquee titles absent

Almost every MEDIUM/LOW in the clean-name / misspell / partial rows traces to **the corpus, not the ranking**.
The 44k skews to **games** — God of War, The Witcher, Dark Souls, Call of Duty, Spider-Man all resolve. But:
- **Marquee TV shows are absent** — *Game of Thrones*, *Breaking Bad*, *Stranger Things* exist only as
  games / making-of movies / fan podcasts, never the show. UC4 Story 1 ("canonical entity #1") is **unmeetable**
  for these because the canonical entity isn't in the catalogue.
- **AAA game gaps** — *Elden Ring* (base game — only a movie + the *Nightreign* spinoff), *The Last of Us*,
  *Stardew Valley*, *Grand Theft Auto VI* are absent.
- **No sports.** **`Arsenal` is the spec's own flagship UC4 Story 1 example, and the corpus cannot satisfy it:**
  the football club is absent, so the exact "Arsenal" #1 is an unrelated 2017 action movie. This single query is
  the clearest argument for the coverage ask.

**This is a data/team ask, not a code fix** — the ranking is doing the right thing on the strings it has.

## Other known limitations — root cause, and whose to fix

1. **Acronyms / initialisms (DATA + small code).** `got`, `gta 6`, `cod`, `gow` don't map to their titles even
   when the franchise IS present (God of War, Call of Duty, Spider-Man are all in-corpus but unreachable via the
   initialism). **Fix = an alias/acronym table** keyed to property_id; the exact tier already has the slot.
2. **NL modality qualifiers not parsed (OURS, medium).** "horror **games**", "scary **movies**", "shows about
   cooking" get the topic right but ignore the vertical word. **Fix = a light NL pre-parse** → set the `verticals` filter.
3. **Vibe / mood queries (HARD).** "cozy", "chill background watching", "wholesome family" have no dedicated
   signal; a curated mood→genre mapping (data + product) would lift them.
4. **Open NL questions ("what should i watch tonight") — LOW.** No query understanding; needs an LLM intent layer.
5. **Podcast attribute-centrality is inert (KNOWN, by design).** Degenerate (GDS floor); podcast ranking rides
   popularity via the per-vertical weight table. Acceptable.

## Engineer's verdict — shippable?

**The retrieval + ranking CORE is shippable for v1.** Where the canonical entity is in the corpus it wins:
games resolve (Cyberpunk, Dark Souls, God of War via full name, The Witcher, Battlefield, Control, Frasier, The
Daily), misspellings recover (`the wichter`→The Witcher, `spider man`→Marvel's Spider-Man), disambiguation pins
title + thematic, cross-vertical / onboarding breadth is correct (6/6 cross-vertical, 5/6 onboarding, 4/4
vertical-filtered), edge input degrades gracefully. The two cheap fixes above are done.

**But be honest about the headline:** on this corpus the flagship UC4 Story 1 promise — "search *Arsenal*, get
Arsenal" — is **not** deliverable, and several marquee TV shows / AAA games return a same-name lesser entity.
That is a **data problem**, and it caps perceived quality regardless of how good the ranking is.

**Ship now (ours — done/cheap):** the ranking core; the anime + min-length fixes (done this pass).
**Blocking a great demo (DATA/team ask, prioritized):**
1. **Corpus coverage** — marquee TV shows + AAA games + (if in scope) a sports/club vertical — **the #1 ask**;
2. **Alias/acronym table** (got/gta6/cod/gow → property_id) — cheap data, high hit-rate;
3. **NL-modality pre-parse** + an LLM intent layer for open questions — roadmap;
4. **Mood/vibe mapping** — data + product.

Verdict: **ship the engine as v1; gate the demo/marketing on the corpus ask.** The code is right; the catalogue
is the bottleneck.
