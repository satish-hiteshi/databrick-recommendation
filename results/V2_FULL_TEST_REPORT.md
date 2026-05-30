# V2 Full Test Report

## Section 1 — System Status

- **Total entities:** 6945
- **By vertical:** {'game': 1997, 'movie': 1653, 'podcast': 1998, 'tv': 1297}
- **Release date coverage:** {'game': 1997, 'movie': 1627, 'tv': 1193, 'podcast': 0}
- **Backend:** http://192.168.100.191:8000 (running)
- **Frontend:** http://192.168.100.191:3000 (running)

## Section 2 — Per-Query Results

### Q1: "Games similar to Hades II"
**Category:** entity_single | **Status:** success

**NLU:** mode=`entity_single`, pos=`['Hades II']`, neg=`[]`, kw=`[]`, verticals=`['game']`
**Date:** start=`None`, end=`None` | Applied: False | Desc: 
**Results:** 10 | **Latency:** 746ms


| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Curse of the Dead Gods | game | 100% | 2020-03-03 | Shares the difficult energy and isometric atmosphere th |
| 2 | Loot River | game | 96% | 2022-05-03 | Built on the same dungeon-crawler foundation that makes |
| 3 | Sword of the Necromancer | game | 44% | 2021-01-28 | Carries the same isometric spirit that defines Hades II |
| 4 | God of War Ragnarök: Valhalla | game | 43% | 2023-12-12 | A natural companion to Hades II — both thrive on hack-a |
| 5 | Backpack Hero | game | 43% | 2022-01-31 | Much like Hades II, this leans into dungeon-crawler wit |
| ... | *5 more results* | | | | |

---

### Q2: "Movies like The Last of Us"
**Category:** entity_single | **Status:** success

**NLU:** mode=`entity_single`, pos=`['The Last of Us']`, neg=`[]`, kw=`[]`, verticals=`['movie']`
**Date:** start=`None`, end=`None` | Applied: False | Desc: 
**Results:** 10 | **Latency:** 631ms


| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Silent Zone | movie | 100% | 2020-12-31 | A different medium, same emotional DNA as The Last of U |
| 2 | Apocalypse Z: The Beginning of the End | movie | 99% | 2024-10-04 | Carries The Last of Us's spirit into the world of movie |
| 3 | Worldbreaker | movie | 97% | 2025-10-30 | Translates the The Last of Us experience into movies fo |
| 4 | 28 Years Later | movie | 95% | 2025-06-18 | What The Last of Us does for TV shows, this does for mo |
| 5 | Resident Evil: Welcome to Raccoon City | movie | 94% | 2021-11-24 | If you want the The Last of Us feeling in a movies, thi |
| ... | *5 more results* | | | | |

---

### Q3: "TV shows similar to Severance"
**Category:** entity_single | **Status:** success

**NLU:** mode=`entity_single`, pos=`['Severance']`, neg=`[]`, kw=`[]`, verticals=`['tv']`
**Date:** start=`None`, end=`None` | Applied: False | Desc: 
**Results:** 10 | **Latency:** 781ms


| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Dark Matter | tv | 100% | 2024-05-07 | Carries the same apple tv+ spirit that defines Severanc |
| 2 | Constellation | tv | 97% | 2024-02-21 | Much like Severance, this leans into apple tv+ with a s |
| 3 | Pluribus | tv | 96% | 2025-11-06 | Shares the cerebral energy and dystopian atmosphere tha |
| 4 | The Copenhagen Test | tv | 94% | 2025-12-27 | Built on the same cerebral foundation that makes Severa |
| 5 | Silo | tv | 92% | 2023-05-04 | Silo captures a similar blend of apple tv+ and dystopia |
| ... | *5 more results* | | | | |

---

### Q4: "I love Hades II, recommend me movies and TV shows"
**Category:** cross_vertical | **Status:** success

**NLU:** mode=`entity_single`, pos=`['Hades II']`, neg=`[]`, kw=`[]`, verticals=`['movie', 'tv']`
**Date:** start=`None`, end=`None` | Applied: False | Desc: 
**Results:** 20 | **Latency:** 618ms

**MOVIE** (10):
**TV** (10):

| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Ne Zha 2 | movie | 100% | 2025-01-29 | A different medium, same emotional DNA as Hades II |
| 2 | The Old Guard 2 | movie | 97% | 2025-07-01 | If you want the Hades II feeling in a movies, this is i |
| 3 | Mythos | movie | 48% | 2026-04-27 | Carries Hades II's spirit into the world of movies |
| 4 | The Monkey Hero | movie | 47% | 2026-04-30 | The movies equivalent of what Hades II offers |
| 5 | Masters of the Universe | movie | 46% | 2026-06-03 | Translates the Hades II experience into movies form |
| ... | *15 more results* | | | | |

---

### Q5: "Based on the movie Dungeons & Dragons: Honor Among Thieves, suggest games"
**Category:** cross_vertical | **Status:** success

**NLU:** mode=`entity_single`, pos=`['Dungeons & Dragons: Honor Among Thieves']`, neg=`[]`, kw=`[]`, verticals=`['game']`
**Date:** start=`None`, end=`None` | Applied: False | Desc: 
**Results:** 10 | **Latency:** 708ms


| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Demeo | game | 100% | 2021-05-06 | Carries Dungeons & Dragons: Honor Among Thieves's spiri |
| 2 | Voice of Cards: The Isle Dragon Roars | game | 87% | 2021-10-27 | What Dungeons & Dragons: Honor Among Thieves does for m |
| 3 | Atlas Fallen | game | 45% | 2023-08-10 | Translates the Dungeons & Dragons: Honor Among Thieves  |
| 4 | Marvel's Guardians of the Galaxy | game | 44% | 2021-10-26 | If you want the Dungeons & Dragons: Honor Among Thieves |
| 5 | Hogwarts Legacy | game | 44% | 2023-02-07 | The games equivalent of what Dungeons & Dragons: Honor  |
| ... | *5 more results* | | | | |

---

### Q6: "I enjoy the TV show INVINCIBLE, find me similar games and movies"
**Category:** cross_vertical | **Status:** success

**NLU:** mode=`entity_single`, pos=`['INVINCIBLE']`, neg=`[]`, kw=`[]`, verticals=`['game', 'movie']`
**Date:** start=`None`, end=`None` | Applied: False | Desc: 
**Results:** 10 | **Latency:** 709ms

**MOVIE** (10):

| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Superman: Red Son | movie | 100% | 2020-02-24 | A different medium, same emotional DNA as INVINCIBLE |
| 2 | Justice League Dark: Apokolips War | movie | 92% | 2020-05-05 | Translates the INVINCIBLE experience into movies form |
| 3 | Apex | movie | 92% | 2026-03-15 | The movies equivalent of what INVINCIBLE offers |
| 4 | Spider-Man: Across the Spider-Verse | movie | 90% | 2023-05-31 | If you want the INVINCIBLE feeling in a movies, this is |
| 5 | Thunderbolts* | movie | 87% | 2025-04-30 | Carries INVINCIBLE's spirit into the world of movies |
| ... | *5 more results* | | | | |

---

### Q7: "I love both Monster Hunter Rise and Hollow Knight: Silksong, find me similar games"
**Category:** multi_entity | **Status:** success

**NLU:** mode=`entity_multi`, pos=`['Monster Hunter Rise', 'Hollow Knight: Silksong']`, neg=`[]`, kw=`[]`, verticals=`['game']`
**Date:** start=`None`, end=`None` | Applied: False | Desc: 
**Results:** 10 | **Latency:** 794ms


| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Monster Hunter Rise: Sunbreak | game | 100% | 2022-06-29 | Continues the Monster Hunter story you're already inves |
| 2 | Monster Hunter Wilds | game | 98% | 2024-10-31 | More from the Monster Hunter world — a natural next ste |
| 3 | Monster Hunter Stories 2: Wings of Ruin | game | 96% | 2021-07-08 | Part of the Monster Hunter universe you already enjoy |
| 4 | Aeterna Noctis | game | 99% | 2021-12-15 | Especially connected to Monster Hunter Rise through the |
| 5 | Afterimage | game | 99% | 2023-04-25 | Strongest connection is to Monster Hunter Rise and its  |
| ... | *5 more results* | | | | |

---

### Q8: "Based on The Last of Us and Severance, recommend movies"
**Category:** multi_entity | **Status:** success

**NLU:** mode=`entity_multi`, pos=`['The Last of Us', 'Severance']`, neg=`[]`, kw=`[]`, verticals=`['movie']`
**Date:** start=`None`, end=`None` | Applied: False | Desc: 
**Results:** 10 | **Latency:** 808ms


| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Possessor | movie | 100% | 2020-10-02 | Translates the The Last of Us experience into movies fo |
| 2 | Silent Zone | movie | 97% | 2020-12-31 | The movies equivalent of what The Last of Us offers |
| 3 | Apocalypse Z: The Beginning of the End | movie | 97% | 2024-10-04 | What The Last of Us does for TV shows, this does for mo |
| 4 | Paradise | movie | 97% | 2023-06-24 | Carries The Last of Us's spirit into the world of movie |
| 5 | Spiderhead | movie | 95% | 2022-06-15 | If you want the The Last of Us feeling in a movies, thi |
| ... | *5 more results* | | | | |

---

### Q9: "I enjoy Crime Junkie and Dateline NBC podcasts, find me similar podcasts"
**Category:** multi_entity | **Status:** success

**NLU:** mode=`entity_multi`, pos=`['Crime Junkie', 'Dateline NBC']`, neg=`[]`, kw=`[]`, verticals=`['podcast']`
**Date:** start=`None`, end=`None` | Applied: False | Desc: 
**Results:** 10 | **Latency:** 752ms


| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Truly Criminal | podcast | 100% | — | Combines the courtroom quality of Crime Junkie with the |
| 2 | 48 Hours | podcast | 71% | — | Mirrors Crime Junkie's courtroom identity more than any |
| 3 | True Crime Garage | podcast | 70% | — | Especially connected to Crime Junkie through their shar |
| 4 | 20/20 | podcast | 68% | — | If Crime Junkie is your favourite of the bunch, this is |
| 5 | The Vanished Podcast | podcast | 67% | — | The cold-cases hallmarks of Crime Junkie are unmistakab |
| ... | *5 more results* | | | | |

---

### Q10: "Horror content across all categories"
**Category:** theme | **Status:** success

**NLU:** mode=`theme_based`, pos=`[]`, neg=`[]`, kw=`['horror']`, verticals=`['game', 'movie', 'tv', 'podcast']`
**Date:** start=`None`, end=`None` | Applied: False | Desc: 
**Results:** 16 | **Latency:** 5141ms

**GAME** (6):
**MOVIE** (10):

| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Choo-Choo Charles | game | 97% | 2022-12-09 | The horror here is front and centre, supported by stron |
| 2 | World of Horror | game | 96% | 2020-02-20 | Exactly the kind of horror, adventure experience you as |
| 3 | Bye Sweet Carole | game | 94% | 2025-10-09 | Nails the horror mood you're after, with rich adventure |
| 4 | Squirrel Stapler | game | 92% | 2023-09-11 | Goes all in on horror — the action adds real texture |
| 5 | Slitterhead | game | 88% | 2024-11-05 | One of the stronger horror picks, enriched by its adven |
| ... | *11 more results* | | | | |

---

### Q11: "I want something with political intrigue and power struggles"
**Category:** descriptive | **Status:** success

**NLU:** mode=`theme_based`, pos=`[]`, neg=`[]`, kw=`['political intrigue', 'power struggles']`, verticals=`['game', 'movie', 'tv', 'podcast']`
**Date:** start=`None`, end=`None` | Applied: False | Desc: 
**Results:** 25 | **Latency:** 7924ms

**GAME** (5):
**MOVIE** (10):
**TV** (10):

| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Fallen Legion Revenants | game | 100% | 2021-02-16 | Built around political intrigue and power struggles — r |
| 2 | The Legend of Heroes: Trails Through Daybreak | game | 93% | 2021-09-30 | Dripping with political intrigue atmosphere and grounde |
| 3 | The Legend of Heroes: Trails through Daybreak II | game | 91% | 2022-09-29 | Matches the political intrigue and power struggles atmo |
| 4 | The Life and Suffering of Sir Brante | game | 83% | 2021-03-04 | Delivers on the political intrigue front with genuine p |
| 5 | Rise of the Third Power | game | 83% | 2022-02-10 | Unmistakably political intrigue, and the power struggle |
| ... | *20 more results* | | | | |

---

### Q12: "Content about space exploration and alien civilizations"
**Category:** theme | **Status:** success

**NLU:** mode=`theme_based`, pos=`[]`, neg=`[]`, kw=`['space exploration', 'alien civilizations']`, verticals=`['game', 'movie', 'tv', 'podcast']`
**Date:** start=`None`, end=`None` | Applied: False | Desc: 
**Results:** 20 | **Latency:** 6169ms

**GAME** (10):
**MOVIE** (10):

| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | No Man's Sky: Nintendo Switch Edition | game | 100% | 2022-10-07 | Dripping with space exploration atmosphere and grounded |
| 2 | The Invincible | game | 78% | 2023-11-06 | The space exploration here is front and centre, support |
| 3 | Terra Invicta | game | 98% | 2022-09-26 | Takes space exploration seriously and wraps it in a sat |
| 4 | Jett: The Far Shore | game | 94% | 2021-10-05 | Checks the space exploration box emphatically, with ali |
| 5 | Outcast: A New Beginning | game | 93% | 2024-03-15 | Leans heavily into the space exploration and alien civi |
| ... | *15 more results* | | | | |

---

### Q13: "Games coming out in 2026"
**Category:** date | **Status:** success

**NLU:** mode=`theme_based`, pos=`[]`, neg=`[]`, kw=`[]`, verticals=`['game']`
**Date:** start=`2026-01-01`, end=`2026-12-31` | Applied: True | Desc: 2026-01-01 to 2026-12-31
**Results:** 10 | **Latency:** 7039ms


| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Pokémon Pokopia | game | 100% | 2026-03-05 | Recommended based on the combination of qualities you v |
| 2 | Mixtape | game | 97% | 2026-05-07 | Aligns well with your stated preferences |
| 3 | Tomodachi Life: Living the Dream | game | 92% | 2026-04-16 | A natural recommendation given everything you've descri |
| 4 | Cairn | game | 87% | 2026-01-29 | Well-suited to the kind of content you gravitate toward |
| 5 | Darwin's Paradox! | game | 84% | 2026-04-02 | Fits the pattern of what you enjoy |
| ... | *5 more results* | | | | |

---

### Q14: "Horror movies from 2025"
**Category:** date+theme | **Status:** success

**NLU:** mode=`theme_based`, pos=`[]`, neg=`[]`, kw=`['horror']`, verticals=`['movie']`
**Date:** start=`2025-01-01`, end=`2025-12-31` | Applied: True | Desc: 2025-01-01 to 2025-12-31
**Results:** 10 | **Latency:** 5711ms


| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | The Monkey | movie | 100% | 2025-02-10 | One of the stronger horror picks, enriched by its comed |
| 2 | Marshmallow | movie | 94% | 2025-04-11 | A textbook example of compelling horror layered with ho |
| 3 | Scissors | movie | 93% | 2025-09-05 | Fully committed to the horror experience, bolstered by  |
| 4 | It Feeds | movie | 92% | 2025-04-17 | Lives and breathes horror, with a undercurrent of horro |
| 5 | Wormtown | movie | 91% | 2025-09-27 | Leans heavily into the horror and adventure space you'r |
| ... | *5 more results* | | | | |

---

### Q15: "New TV shows released this year"
**Category:** date | **Status:** success

**NLU:** mode=`theme_based`, pos=`[]`, neg=`[]`, kw=`[]`, verticals=`['tv']`
**Date:** start=`2026-01-01`, end=`2026-12-31` | Applied: True | Desc: 2026-01-01 to 2026-12-31
**Results:** 10 | **Latency:** 8713ms


| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | The Miniature Wife | tv | 100% | 2026-04-09 | Fits the pattern of what you enjoy |
| 2 | Star City | tv | 98% | 2026-05-28 | Well-suited to the kind of content you gravitate toward |
| 3 | Regular Show: The Lost Tapes | tv | 88% | 2026-05-11 | Aligns well with your stated preferences |
| 4 | The WONDERfools | tv | 47% | 2026-05-15 | A strong match based on your overall taste profile |
| 5 | The Dark Wizard | tv | 47% | 2026-04-14 | Recommended based on the combination of qualities you v |
| ... | *5 more results* | | | | |

---

### Q16: "Games like Elden Ring releasing in 2025 or 2026"
**Category:** date+entity | **Status:** success

**NLU:** mode=`entity_single`, pos=`['Elden Ring']`, neg=`[]`, kw=`[]`, verticals=`['game']`
**Date:** start=`2025-01-01`, end=`2026-12-31` | Applied: True | Desc: 2025-01-01 to 2026-12-31
**Results:** 10 | **Latency:** 6860ms


| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Elden Ring Nightreign | game | 100% | 2025-05-30 | Built on the same bandai namco foundation that makes El |
| 2 | Mandragora: Whispers of the Witch Tree | game | 97% | 2025-04-17 | Rooted in the dark fantasy tradition that Elden Ring ex |
| 3 | Crimson Desert | game | 95% | 2026-03-19 | Shares the exploration energy and medieval atmosphere t |
| 4 | Nioh 3 | game | 92% | 2026-02-06 | A natural companion to Elden Ring — both thrive on role |
| 5 | Kingdom Come: Deliverance II | game | 92% | 2025-02-04 | Carries the same medieval spirit that defines Elden Rin |
| ... | *5 more results* | | | | |

---

### Q17: "Sci-fi movies from the last 2 years similar to INVINCIBLE"
**Category:** date+entity | **Status:** success

**NLU:** mode=`entity_single`, pos=`['INVINCIBLE']`, neg=`[]`, kw=`['sci-fi']`, verticals=`['movie']`
**Date:** start=`2024-01-01`, end=`2026-05-29` | Applied: True | Desc: 2024-01-01 to 2026-05-29
**Results:** 10 | **Latency:** 6319ms


| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Immortal Combat | movie | 34% | 2026-04-24 | Translates the INVINCIBLE experience into movies form |
| 2 | Apex | movie | 100% | 2026-03-15 | What INVINCIBLE does for TV shows, this does for movies |
| 3 | Thunderbolts* | movie | 97% | 2025-04-30 | If you want the INVINCIBLE feeling in a movies, this is |
| 4 | The Punisher: One Last Kill | movie | 95% | 2026-05-12 | Carries INVINCIBLE's spirit into the world of movies |
| 5 | Predator: Killer of Killers | movie | 93% | 2025-06-05 | A different medium, same emotional DNA as INVINCIBLE |
| ... | *5 more results* | | | | |

---

### Q18: "I love Hades II and Monster Hunter Rise but hate sports games, recommend me 2025 movies"
**Category:** mixed+date | **Status:** success

**NLU:** mode=`entity_multi`, pos=`['Hades II', 'Monster Hunter Rise']`, neg=`['sports games']`, kw=`[]`, verticals=`['movie']`
**Date:** start=`2025-01-01`, end=`2025-12-31` | Applied: True | Desc: 2025-01-01 to 2025-12-31
**Results:** 10 | **Latency:** 7246ms


| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Red Sonja | movie | 100% | 2025-07-31 | Sits at the intersection of what you love about Hades I |
| 2 | The Rats: A Witcher Tale | movie | 96% | 2025-10-29 | Picked up signals from both Hades II and Monster Hunter |
| 3 | Ne Zha 2 | movie | 82% | 2025-01-29 | Where Hades II meets Monster Hunter Rise — this lives i |
| 4 | Troll 2 | movie | 80% | 2025-11-30 | The mythology of Hades II and the fantasy of Monster Hu |
| 5 | The Old Guard 2 | movie | 55% | 2025-07-01 | The movies equivalent of what Hades II offers |
| ... | *5 more results* | | | | |

---

### Q19: "Horror content from 2024 onwards, not comedy, across all categories"
**Category:** mixed+date | **Status:** success

**NLU:** mode=`theme_based`, pos=`[]`, neg=`['comedy']`, kw=`['horror']`, verticals=`['game', 'movie', 'tv', 'podcast']`
**Date:** start=`2024-01-01`, end=`2026-12-31` | Applied: True | Desc: 2024-01-01 to 2026-12-31
**Results:** 10 | **Latency:** 6940ms

**MOVIE** (10):

| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | The Monkey | movie | 100% | 2025-02-10 | A prime example of horror done with comedy conviction |
| 2 | Evil Dead Burn | movie | 98% | 2026-07-08 | Leans heavily into the horror and horror space you're e |
| 3 | The Jester 2 | movie | 48% | 2025-09-15 | Dripping with horror atmosphere and grounded in crime |
| 4 | Darbie's Scream House | movie | 48% | 2026-01-20 | Takes horror seriously and wraps it in a satisfying lay |
| 5 | Die'ced: Reloaded | movie | 47% | 2025-08-08 | Delivers on the horror front with genuine horror depth |
| ... | *5 more results* | | | | |

---

### Q20: "I am a huge fan of The Last of Us, Severance, and Crime Junkie. I dislike reality TV and family content. Recommend me the best games, movies, and TV shows from the last 2 years"
**Category:** max_complex | **Status:** success

**NLU:** mode=`mixed`, pos=`['The Last of Us', 'Severance', 'Crime Junkie']`, neg=`['reality TV', 'family content']`, kw=`[]`, verticals=`['game', 'movie', 'tv']`
**Date:** start=`2024-05-29`, end=`2026-05-29` | Applied: True | Desc: 2024-05-29 to 2026-05-29
**Results:** 30 | **Latency:** 7284ms

**GAME** (10):
**MOVIE** (10):
**TV** (10):

| # | Name | Vertical | Match% | Release Date | Reasoning |
|---|------|----------|--------|-------------|-----------|
| 1 | Death Stranding 2: On the Beach | game | 100% | 2025-06-24 | If The Last of Us is your favourite of the bunch, this  |
| 2 | Metro Awakening VR | game | 97% | 2024-11-05 | Especially connected to The Last of Us through their sh |
| 3 | Horizon Zero Dawn Remastered | game | 96% | 2024-10-31 | The post-apocalyptic hallmarks of The Last of Us are un |
| 4 | S.T.A.L.K.E.R.: Shadow of Chornobyl - Enhanced Edition | game | 96% | 2025-05-20 | The post-apocalyptic DNA of The Last of Us is what conn |
| 5 | S.T.A.L.K.E.R. 2: Heart of Chornobyl | game | 93% | 2024-11-20 | Closely aligned with The Last of Us — sharing its post- |
| ... | *25 more results* | | | | |

---

## Section 3 — Feature Verification

### Reasoning
- Results with reasoning: 261/261
- Results without reasoning: 0
- Forbidden technical terms found: 0

### Date Filtering

| Query | Date Start | Date End | Filter Applied | Results in Range |
|-------|-----------|---------|---------------|-----------------|
| Q13 | 2026-01-01 | 2026-12-31 | True | 10 in / 0 out |
| Q14 | 2025-01-01 | 2025-12-31 | True | 10 in / 0 out |
| Q15 | 2026-01-01 | 2026-12-31 | True | 10 in / 0 out |
| Q16 | 2025-01-01 | 2026-12-31 | True | 10 in / 0 out |
| Q17 | 2024-01-01 | 2026-05-29 | True | 10 in / 0 out |
| Q18 | 2025-01-01 | 2025-12-31 | True | 10 in / 0 out |
| Q19 | 2024-01-01 | 2026-12-31 | True | 10 in / 0 out |

### Negative Filtering

- **Q18:** 0 penalized, 0 removed from candidates
- **Q19:** 0 penalized, 0 removed from candidates
- **Q20:** 0 penalized, 0 removed from candidates

## Section 4 — Quality Assessment

- **Success rate:** 20/20 queries returned results
- **Average results per query:** 13.1
- **Average latency:** 4095ms
- **Min latency:** 618ms
- **Max latency:** 8713ms

| Category | Success | Avg Latency |
|----------|---------|------------|
| cross_vertical | 3/3 | 678ms |
| date | 2/2 | 7876ms |
| date+entity | 2/2 | 6589ms |
| date+theme | 1/1 | 5711ms |
| descriptive | 1/1 | 7924ms |
| entity_single | 3/3 | 720ms |
| max_complex | 1/1 | 7284ms |
| mixed+date | 2/2 | 7093ms |
| multi_entity | 3/3 | 785ms |
| theme | 2/2 | 5655ms |

## Section 5 — Issues Found

No issues found.

