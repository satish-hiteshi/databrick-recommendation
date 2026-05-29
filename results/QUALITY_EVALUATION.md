# Ground Truth Quality Evaluation

## Section 1 — Per-Query Evaluation

### Q1: "What games feel like Hollow Knight: Silksong?"
**Mode:** `entity_single` | **Verdict: POOR** | Overlap: 2/10 | P@10=20.0% | R@10=20.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | Ender Magnolia: Bloom in the Mist | 0.3437 | Little Nightmares III | 27 | Yes |
| 2 | Inayah: Life after Gods | 0.2775 | Haste | 26 |  |
| 3 | Sophie: Starlight Whispers | 0.2679 | Adorable Adventures | 26 | Yes |
| 4 | Possessor(s) | 0.2341 | Silent Hill f | 25 |  |
| 5 | Plus Ultra: Legado | 0.2195 | Time Flies | 24 |  |
| 6 | Somber Echoes | 0.1892 | Primal Planet | 24 |  |
| 7 | Blade Chimera | 0.1817 | Ender Magnolia: Bloom in the Mist | 23 |  |
| 8 | SteamDolls: Order of Chaos | 0.1366 | Is This Seat Taken? | 23 |  |
| 9 | Spirit of the North 2 | 0.1352 | Clair Obscur: Expedition 33 | 22 |  |
| 10 | Shadow Labyrinth | 0.1312 | Sophie: Starlight Whispers | 21 |  |

**Missed (in ideal, not in pipeline):** Little Nightmares III (gt=27), Haste (gt=26), Adorable Adventures (gt=26), Silent Hill f (gt=25), Time Flies (gt=24)

### Q2: "Find me movies that have a similar vibe to Predator: Badlands"
**Mode:** `entity_single` | **Verdict: FAIR** | Overlap: 4/10 | P@10=40.0% | R@10=40.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | Predator: Wastelands | 0.5479 | The Jurassic Games: Extinction | 10 | Yes |
| 2 | Jurassic World Rebirth | 0.2416 | TRON: Ares | 10 |  |
| 3 | War Machine | 0.2314 | Dune: Part Three | 10 |  |
| 4 | Worldbreaker | 0.2091 | Star Wars: The Mandalorian and Grogu | 10 |  |
| 5 | Primitive War | 0.2025 | The Land That Time Forgot | 10 |  |
| 6 | Star Wars: The Mandalorian and Grogu | 0.1567 | Predator: Wastelands | 9 | Yes |
| 7 | The Land That Time Forgot | 0.1474 | The Fantastic 4: First Steps | 9 | Yes |
| 8 | Apex | 0.1362 | The Electric State | 9 |  |
| 9 | Avatar: Fire and Ash | 0.1295 | Thunderbolts* | 9 |  |
| 10 | Thunderbolts* | 0.0798 | Superman | 9 | Yes |

**Missed (in ideal, not in pipeline):** The Jurassic Games: Extinction (gt=10), TRON: Ares (gt=10), Dune: Part Three (gt=10), The Fantastic 4: First Steps (gt=9), The Electric State (gt=9)

### Q3: "TV shows like Alien: Earth"
**Mode:** `entity_single` | **Verdict: EXCELLENT** | Overlap: 7/10 | P@10=70.0% | R@10=70.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | Marvel Zombies | 0.2100 | The Beauty | 13 | Yes |
| 2 | Star City | 0.2041 | Something Very Bad Is Going to Happen | 10 | Yes |
| 3 | Nine Bodies in a Mexican Morgue | 0.2014 | Pluribus | 9 |  |
| 4 | The Beauty | 0.1875 | Common Side Effects | 9 | Yes |
| 5 | Something Very Bad Is Going to Happen | 0.1804 | Star City | 9 | Yes |
| 6 | The Institute | 0.1707 | The Institute | 9 | Yes |
| 7 | Pluribus | 0.1674 | Marvel Zombies | 7 | Yes |
| 8 | Unchosen | 0.1445 | Murderbot | 7 |  |
| 9 | Murderbot | 0.1433 | Paradise | 7 | Yes |
| 10 | The Last Frontier | 0.1397 | The Terminal List: Dark Wolf | 7 |  |

**Missed (in ideal, not in pipeline):** Common Side Effects (gt=9), Paradise (gt=7), The Terminal List: Dark Wolf (gt=7)

### Q4: "I love the game Vampire: The Masquerade - Bloodlines 2, what movies sh"
**Mode:** `entity_single` | **Verdict: POOR** | Overlap: 2/10 | P@10=20.0% | R@10=20.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | Tales from Black Manor | 1.0279 | The Rats: A Witcher Tale | 4 |  |
| 2 | Vampires of the Velvet Lounge | 0.5912 | The Anacondas | 4 |  |
| 3 | In the Lost Lands | 0.4561 | Ice Beast | 4 |  |
| 4 | Until Dawn | 0.4232 | Return to Silent Hill | 4 |  |
| 5 | Return to Silent Hill | 0.4087 | Night of the Zoopocalypse | 4 | Yes |
| 6 | The Rats: A Witcher Tale | 0.3624 | Enola Holmes 3 | 4 | Yes |
| 7 | Peaky Blinders: The Immortal Man | 0.2059 | Stitch Head | 4 |  |
| 8 | Sherlock Holmes Mare of the Night | 0.2038 | Wormtown | 4 |  |
| 9 | Witchboard | 0.1907 | Fear Below | 4 |  |
| 10 | Bone Hill | 0.1907 | Anaconda | 4 |  |

**Missed (in ideal, not in pipeline):** The Anacondas (gt=4), Ice Beast (gt=4), Night of the Zoopocalypse (gt=4), Enola Holmes 3 (gt=4), Stitch Head (gt=4)
**No metadata overlap:** Peaky Blinders: The Immortal Man

### Q5: "I really enjoyed the TV show Devil May Cry, what games would I like?"
**FAILED**: NLU failed after 3 attempts: Error code: 400 - {'error': {'message': 'tool call validation failed: parameters for tool analyze_query did not match schema: errors: [`/query_mode`: value must be one of "entity_single", "entity_multi", "theme_based", "descriptive", "mixed"]', 'type': 'invalid_request_error', 'code': 'tool_use_failed', 'failed_generation': '<function=analyze_query>{"query_mode": "cross_vertical", "query_type": "cross_vertical", "positive_entities": ["Devil May Cry"], "negative_entities": [], "additional_keywords": [], "description_derived_keywords": [], "target_verticals": ["game"]} </function>'}}

### Q6: "Based on the movie Avatar: Fire and Ash, recommend me TV shows and gam"
**Mode:** `entity_single` | **Verdict: POOR** | Overlap: 2/10 | P@10=10.0% | R@10=20.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | The Mighty Nein | 0.7000 | RoboGobo | 9 |  |
| 2 | Gabriel and the Guardians | 0.6958 | Mermicorno: Starfall | 9 | Yes |
| 3 | Eyes of Wakanda | 0.6083 | Wolf King | 9 |  |
| 4 | Fire and Water: Making the Avatar Films | 0.5040 | Mickey Mouse Clubhouse+ | 9 |  |
| 5 | Armorsaurs | 0.3418 | Iron Man and His Awesome Friends | 9 |  |
| 6 | The Black Dagger Brotherhood | 0.3014 | Gabriel and the Guardians | 9 |  |
| 7 | The Dinosaurs | 0.2766 | Goosebumps: The Vanishing | 9 |  |
| 8 | Chief of War | 0.2702 | Star Wars: Tales of the Underworld | 9 |  |
| 9 | Iyanu | 0.2226 | LEGO Star Wars: Rebuild the Galaxy - Pieces of the Past | 9 |  |
| 10 | Wolf King | 0.1781 | LEGO Marvel Avengers: Strange Tails | 9 | Yes |

**Missed (in ideal, not in pipeline):** RoboGobo (gt=9), Mermicorno: Starfall (gt=9), Mickey Mouse Clubhouse+ (gt=9), Iron Man and His Awesome Friends (gt=9), Goosebumps: The Vanishing (gt=9)
**No metadata overlap:** The Dinosaurs, Chief of War

### Q7: "I love both Code Vein II and Monster Hunter Wilds, find me similar gam"
**Mode:** `entity_multi` | **Verdict: GOOD** | Overlap: 5/10 | P@10=50.0% | R@10=50.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | Monster Hunter Stories 3: Twisted Reflection | 0.8144 | Monster Hunter Stories 3: Twisted Reflection | 31 | Yes |
| 2 | Beast of Reincarnation | 0.4697 | Wuchang: Fallen Feathers | 27 |  |
| 3 | AI Limit | 0.3772 | Titan Quest II | 27 |  |
| 4 | Mongil: Star Dive | 0.3663 | Elden Ring Nightreign | 27 |  |
| 5 | The Blood of Dawnwalker | 0.3438 | The Blood of Dawnwalker | 26 | Yes |
| 6 | Elden Ring Nightreign | 0.3317 | Hytale | 25 | Yes |
| 7 | Duet Night Abyss | 0.3211 | The Seven Deadly Sins: Origin | 25 | Yes |
| 8 | Tails of Iron II: Whiskers of Winter | 0.3062 | Duet Night Abyss | 25 |  |
| 9 | Wuchang: Fallen Feathers | 0.2970 | Atomfall | 25 | Yes |
| 10 | Crimson Desert | 0.2838 | Legend of Ymir | 25 |  |

**Missed (in ideal, not in pipeline):** Titan Quest II (gt=27), Hytale (gt=25), The Seven Deadly Sins: Origin (gt=25), Atomfall (gt=25), Legend of Ymir (gt=25)

### Q8: "Movies like both Predator: Badlands and The Old Guard 2"
**Mode:** `entity_multi` | **Verdict: FAIR** | Overlap: 4/10 | P@10=40.0% | R@10=40.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | Predator: Wastelands | 0.9899 | The Jurassic Games: Extinction | 17 | Yes |
| 2 | Red Sonja | 0.4934 | The Land That Time Forgot | 16 | Yes |
| 3 | Avatar: Fire and Ash | 0.4304 | Red Sonja | 13 |  |
| 4 | Jurassic World Rebirth | 0.4153 | TRON: Ares | 13 |  |
| 5 | Lost Horizon | 0.3240 | Dune: Part Three | 13 |  |
| 6 | Suky | 0.3156 | Star Wars: The Mandalorian and Grogu | 13 |  |
| 7 | Star Wars: The Mandalorian and Grogu | 0.3017 | Predator: Wastelands | 12 | Yes |
| 8 | Thunderbolts* | 0.2593 | The Fantastic 4: First Steps | 12 | Yes |
| 9 | Apex | 0.1698 | The Electric State | 12 |  |
| 10 | War Machine | 0.1634 | Thunderbolts* | 12 |  |

**Missed (in ideal, not in pipeline):** The Jurassic Games: Extinction (gt=17), The Land That Time Forgot (gt=16), TRON: Ares (gt=13), Dune: Part Three (gt=13), The Fantastic 4: First Steps (gt=12)

### Q9: "I enjoy Resident Evil Requiem and Silent Hill f as games, recommend me"
**Mode:** `entity_multi` | **Verdict: POOR** | Overlap: 1/10 | P@10=7.1% | R@10=10.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | Return to Silent Hill | 0.8500 | Ice Beast | 12 |  |
| 2 | Until Dawn | 0.7822 | Marvel Zombies | 12 |  |
| 3 | Silent Zone | 0.6836 | The Anacondas | 11 |  |
| 4 | George A. Romero's Resident Evil | 0.6106 | Fear Below | 11 |  |
| 5 | Evil Dead Burn | 0.6014 | The Land That Time Forgot | 11 |  |
| 6 | The Strangers: Chapter 3 | 0.4511 | Mission: Impossible - The Final Reckoning | 10 |  |
| 7 | Final Destination Bloodlines | 0.4500 | TRON: Ares | 10 |  |
| 8 | American Psychopath | 0.4254 | Dune: Part Three | 10 |  |
| 9 | Passenger | 0.4178 | Karate Kid: Legends | 10 |  |
| 10 | Scream 7 | 0.3919 | Star Wars: The Mandalorian and Grogu | 10 |  |

**Missed (in ideal, not in pipeline):** Ice Beast (gt=12), The Anacondas (gt=11), Fear Below (gt=11), The Land That Time Forgot (gt=11), Mission: Impossible - The Final Reckoning (gt=10)

### Q10: "Based on Marvel Zombies TV show and Alien: Earth TV show, what games s"
**FAILED**: No entities resolved from: ['Marvel Zombies TV show', 'Alien: Earth TV show']

### Q11: "I like the movie In the Lost Lands and the game Crimson Desert, find m"
**Mode:** `entity_multi` | **Verdict: FAIR** | Overlap: 4/10 | P@10=40.0% | R@10=40.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | American Primeval | 1.3500 | Star Wars: Tales of the Underworld | 11 |  |
| 2 | Devil May Cry | 1.1290 | Iyanu | 10 | Yes |
| 3 | A Knight of the Seven Kingdoms | 1.0500 | Wolf King | 10 |  |
| 4 | The Abandons | 0.9660 | Mickey Mouse Clubhouse+ | 10 |  |
| 5 | The Black Dagger Brotherhood | 0.8344 | Devil May Cry | 10 |  |
| 6 | Marshals | 0.7820 | Iron Man and His Awesome Friends | 10 | Yes |
| 7 | The Mighty Nein | 0.7388 | Gabriel and the Guardians | 10 |  |
| 8 | Star Wars: Tales of the Underworld | 0.6462 | Goosebumps: The Vanishing | 10 | Yes |
| 9 | Gabriel and the Guardians | 0.5551 | LEGO Star Wars: Rebuild the Galaxy - Pieces of the Past | 10 | Yes |
| 10 | Spartacus: House of Ashur | 0.4695 | Marshals | 10 |  |

**Missed (in ideal, not in pipeline):** Iyanu (gt=10), Wolf King (gt=10), Mickey Mouse Clubhouse+ (gt=10), Iron Man and His Awesome Friends (gt=10), Goosebumps: The Vanishing (gt=10)

### Q12: "I want survival horror with psychological elements across all categori"
**Mode:** `theme_based` | **Verdict: FAIR** | Overlap: 4/10 | P@10=23.5% | R@10=40.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | Dark Atlas: Infernum | 0.8422 | Silent Hill f | 4 | Yes |
| 2 | Saint of Chains | 0.7600 | Beneath | 3 |  |
| 3 | Post Trauma | 0.7222 | Deathground | 2 | Yes |
| 4 | Greek Tragedy | 0.5554 | Post Trauma | 2 |  |
| 5 | Winter Survival | 0.5245 | Labyrinth of the Demon King | 2 |  |
| 6 | Silent Hill f | 0.5000 | The Alters | 2 | Yes |
| 7 | Memoreum | 0.4848 | Dark Atlas: Infernum | 2 |  |
| 8 | Beneath | 0.4000 | Oxide Room 208 | 2 | Yes |
| 9 | Ire: A Prologue | 0.3102 | Dark Hours | 2 |  |
| 10 | Order 13 | 0.2831 | Ground Zero | 2 |  |

**Missed (in ideal, not in pipeline):** Deathground (gt=2), Labyrinth of the Demon King (gt=2), The Alters (gt=2), Oxide Room 208 (gt=2), Dark Hours (gt=2)
**No metadata overlap:** Saint of Chains, Ire: A Prologue

### Q13: "Find me content about space exploration and alien civilizations"
**Mode:** `theme_based` | **Verdict: N/A (no metadata-based ideal)** | Overlap: 0/10 | P@10=0.0% | R@10=0.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | Terra Invicta | 0.8000 | — | — |  |
| 2 | Star Trek: Voyager - Across the Unknown | 0.4948 | — | — |  |
| 3 | Calx | 0.3507 | — | — |  |
| 4 | One Lonely Outpost | 0.2448 | — | — |  |
| 5 | Empyreal | 0.2084 | — | — |  |
| 6 | Ambrosia Sky: Act One | 0.1802 | — | — |  |
| 7 | Space for Sale | 0.1737 | — | — |  |
| 8 | The Alters | 0.1572 | — | — |  |
| 9 | Arknights: Endfield | 0.1019 | — | — |  |
| 10 | Revenge of the Savage Planet | 0.0971 | — | — |  |

**No metadata overlap:** Terra Invicta, Star Trek: Voyager - Across the Unknown, Calx, One Lonely Outpost, Empyreal

### Q14: "I enjoy stories with political intrigue and power struggles"
**Mode:** `theme_based` | **Verdict: GOOD** | Overlap: 5/10 | P@10=17.2% | R@10=100.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | Disciples: Domination | 0.7348 | Fall of an Empire | 1 | Yes |
| 2 | Fall of an Empire | 0.3500 | Disciples: Domination | 1 | Yes |
| 3 | Chains of Freedom | 0.0429 | Wild Horse Nine | 1 |  |
| 4 | Sacre Bleu | 0.0300 | Dune: Part Three | 1 |  |
| 5 | Netherworld | 0.0000 | The Residence | 1 |  |
| 6 | Hytale | 0.0000 | — | — |  |
| 7 | AI Limit | 0.0000 | — | — |  |
| 8 | Kingdom of Night | 0.0000 | — | — |  |
| 9 | Naïca | 0.0000 | — | — |  |
| 10 | Vampire: The Masquerade - Bloodlines 2 | 0.0000 | — | — |  |

**No metadata overlap:** Chains of Freedom, Sacre Bleu, Netherworld, Hytale, AI Limit

### Q15: "Content that feels like exploring ancient magical ruins and forgotten "
**Mode:** `theme_based` | **Verdict: POOR** | Overlap: 2/10 | P@10=11.1% | R@10=20.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | Regions of Ruin: Runegate | 1.3000 | Hollow Knight: Silksong | 9 | Yes |
| 2 | Echoes of the End | 1.0010 | Vessels of Decay | 9 |  |
| 3 | Vessels of Decay | 0.8864 | Sophie: Starlight Whispers | 9 | Yes |
| 4 | The Light of Celestia | 0.7047 | Regions of Ruin: Runegate | 9 |  |
| 5 | Strings of Fate XI: Magic Dream | 0.5208 | Sandwalkers | 9 |  |
| 6 | Shrine's Legacy | 0.4924 | Sword of the Sea | 9 |  |
| 7 | Under the Island | 0.4878 | Kun’tewiktuk: A Mi’kmaw Adventure | 9 |  |
| 8 | Gecko Gods | 0.4490 | Into the Emberlands | 9 |  |
| 9 | The Adventures of Elliot: The Millennium Tales | 0.4432 | Roots Devour | 9 |  |
| 10 | Heart of Altai | 0.4273 | Mario Kart World | 9 |  |

**Missed (in ideal, not in pipeline):** Hollow Knight: Silksong (gt=9), Sophie: Starlight Whispers (gt=9), Sandwalkers (gt=9), Sword of the Sea (gt=9), Kun’tewiktuk: A Mi’kmaw Adventure (gt=9)

### Q16: "I love Elden Ring Nightreign and dark fantasy but I absolutely hate an"
**Mode:** `mixed` | **Verdict: FAIR** | Overlap: 4/10 | P@10=40.0% | R@10=40.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | In the Lost Lands | 1.5312 | The Jurassic Games: Extinction | 5 | Yes |
| 2 | Tales from Black Manor | 1.1946 | In the Lost Lands | 5 |  |
| 3 | The Rats: A Witcher Tale | 1.1211 | The Witcher: Sirens of the Deep | 5 |  |
| 4 | The Witcher: Sirens of the Deep | 1.0384 | The Land That Time Forgot | 5 | Yes |
| 5 | Peter Pan's Neverland Nightmare | 0.6518 | The Anacondas | 4 |  |
| 6 | Predator: Badlands | 0.6187 | Predator: Wastelands | 4 |  |
| 7 | Until Dawn | 0.5890 | Red Sonja | 4 |  |
| 8 | The Old Guard 2 | 0.5765 | G20 | 4 | Yes |
| 9 | The Jurassic Games: Extinction | 0.4658 | The Old Guard 2 | 4 | Yes |
| 10 | Wizard of Oz: Dead Walk | 0.4544 | Dust Bunny | 4 |  |

**Missed (in ideal, not in pipeline):** The Land That Time Forgot (gt=5), The Anacondas (gt=4), Predator: Wastelands (gt=4), Red Sonja (gt=4), G20 (gt=4)

### Q17: "Games similar to Resident Evil Requiem but nothing like sports or raci"
**Mode:** `entity_single` | **Verdict: FAIR** | Overlap: 3/10 | P@10=30.0% | R@10=30.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | Silent Hill f: Deluxe Edition | 0.2776 | Greek Tragedy | 20 |  |
| 2 | Cronos: The New Dawn | 0.2722 | Cronos: The New Dawn | 20 | Yes |
| 3 | Echoes of the Living | 0.2572 | Silent Hill f | 19 |  |
| 4 | Tormented Souls II | 0.2399 | Tormented Souls II | 19 | Yes |
| 5 | World War Z VR | 0.2169 | I Hate this Place | 19 |  |
| 6 | Ground Zero | 0.2123 | Deathground | 18 |  |
| 7 | Silent Hill f | 0.1973 | Dread Meridian | 17 | Yes |
| 8 | Post Trauma | 0.1843 | Death Relives | 16 |  |
| 9 | Code Violet | 0.1679 | Saborus | 16 |  |
| 10 | The Mute House | 0.1438 | Level Zero: Extraction | 16 |  |

**Missed (in ideal, not in pipeline):** Greek Tragedy (gt=20), I Hate this Place (gt=19), Deathground (gt=18), Dread Meridian (gt=17), Death Relives (gt=16)

### Q18: "I enjoy Silent Hill f and CyberCorp but hate slow paced content, recom"
**Mode:** `mixed` | **Verdict: POOR** | Overlap: 1/10 | P@10=5.0% | R@10=10.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | The Last GunFight | 0.8500 | TRON: Ares | 8 |  |
| 2 | Return to Silent Hill | 0.7000 | Marvel Zombies | 8 |  |
| 3 | The Running Man | 0.6125 | The Anacondas | 7 |  |
| 4 | F1 | 0.5600 | Ice Beast | 7 |  |
| 5 | The Jurassic Games: Extinction | 0.5587 | Mission: Impossible - The Final Reckoning | 7 |  |
| 6 | Cheetahs Up Close with Bertie Gregory | 0.5021 | The Electric State | 7 |  |
| 7 | The Long Walk | 0.4567 | Dune: Part Three | 7 |  |
| 8 | Until Dawn | 0.4238 | Karate Kid: Legends | 7 |  |
| 9 | Predator: Wastelands | 0.4037 | Star Wars: The Mandalorian and Grogu | 7 |  |
| 10 | Havoc | 0.3582 | Fear Below | 7 |  |

**Missed (in ideal, not in pipeline):** TRON: Ares (gt=8), The Anacondas (gt=7), Ice Beast (gt=7), Mission: Impossible - The Final Reckoning (gt=7), The Electric State (gt=7)
**No metadata overlap:** Cheetahs Up Close with Bertie Gregory, Running Point, The Dark Wizard, Court of Gold, Countdown

### Q19: "Based on my love for Monster Hunter Wilds and Crimson Desert, but I di"
**Mode:** `entity_multi` | **Verdict: FAIR** | Overlap: 3/10 | P@10=16.7% | R@10=30.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | The Witcher: Sirens of the Deep | 1.2226 | Red Sonja | 12 |  |
| 2 | Lost Horizon | 1.2000 | The Jurassic Games: Extinction | 11 | Yes |
| 3 | In the Lost Lands | 1.0113 | Lost Horizon | 11 |  |
| 4 | Red Sonja | 0.9004 | Turbulence | 11 | Yes |
| 5 | Predator: Badlands | 0.8500 | The Land That Time Forgot | 11 |  |
| 6 | Desert Warrior | 0.8028 | Iyanu | 11 |  |
| 7 | The Rats: A Witcher Tale | 0.6893 | Wolf King | 11 |  |
| 8 | Avatar: Fire and Ash | 0.6422 | Mickey Mouse Clubhouse+ | 11 |  |
| 9 | Ice Beast | 0.5917 | Iron Man and His Awesome Friends | 11 |  |
| 10 | The Old Guard 2 | 0.5631 | Gabriel and the Guardians | 11 |  |

**Missed (in ideal, not in pipeline):** The Jurassic Games: Extinction (gt=11), Turbulence (gt=11), The Land That Time Forgot (gt=11), Iyanu (gt=11), Wolf King (gt=11)

### Q20: "I am a huge fan of Hollow Knight: Silksong, Elden Ring Nightreign, and"
**Mode:** `entity_multi` | **Verdict: POOR** | Overlap: 0/10 | P@10=0.0% | R@10=0.0%

| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |
|---|--------------- |---------|------------- |----------|-------|
| 1 | Nioh 3 | 0.5743 | Hades II | 47 |  |
| 2 | Ender Magnolia: Bloom in the Mist | 0.5400 | Wuchang: Fallen Feathers | 46 |  |
| 3 | The Blood of Dawnwalker | 0.5088 | Clair Obscur: Expedition 33 | 46 |  |
| 4 | Beast of Reincarnation | 0.4697 | Vessels of Decay | 45 |  |
| 5 | Inayah: Life after Gods | 0.4504 | Abiotic Factor | 45 |  |
| 6 | Sophie: Starlight Whispers | 0.4375 | Lost Soul Aside | 45 |  |
| 7 | Vampire: The Masquerade - Bloodlines 2 | 0.4282 | Dwarves: Glory, Death and Loot | 45 |  |
| 8 | Possessor(s) | 0.3917 | Primal Planet | 45 |  |
| 9 | AI Limit | 0.3772 | Little Nightmares III | 45 |  |
| 10 | Plus Ultra: Legado | 0.3718 | Dragonkin: The Banished | 45 |  |

**Missed (in ideal, not in pipeline):** Hades II (gt=47), Wuchang: Fallen Feathers (gt=46), Clair Obscur: Expedition 33 (gt=46), Vessels of Decay (gt=45), Abiotic Factor (gt=45)

---

## Section 2 — Aggregate Scores

### Verdict Distribution

| Verdict | Count |
|---------|-------|
| EXCELLENT | 1 |
| GOOD | 2 |
| FAIR | 7 |
| POOR | 7 |
| N/A (no metadata-based ideal) | 1 |
| FAILED | 2 |

- **Average Precision@10:** 24.5%
- **Average Recall@10:** 32.2%
- **Queries evaluated:** 18 (excluding failures)

---

## Section 3 — Systematic Analysis

### Frequently Missed Entities (in ideal but not pipeline)

| Entity | Times Missed | Likely Cause |
|--------|-------------|-------------|
| TRON: Ares | 4 | Low embedding similarity despite metadata overlap |
| Dune: Part Three | 4 | Low embedding similarity despite metadata overlap |
| The Anacondas | 4 | Low embedding similarity despite metadata overlap |
| The Land That Time Forgot | 4 | Low embedding similarity despite metadata overlap |
| The Jurassic Games: Extinction | 3 | Low embedding similarity despite metadata overlap |
| The Electric State | 3 | Low embedding similarity despite metadata overlap |
| Ice Beast | 3 | Low embedding similarity despite metadata overlap |
| Fear Below | 3 | Low embedding similarity despite metadata overlap |
| Mickey Mouse Clubhouse+ | 3 | Low embedding similarity despite metadata overlap |
| Iron Man and His Awesome Friends | 3 | Low embedding similarity despite metadata overlap |
| Little Nightmares III | 2 | Low embedding similarity despite metadata overlap |
| Primal Planet | 2 | Low embedding similarity despite metadata overlap |
| Clair Obscur: Expedition 33 | 2 | Low embedding similarity despite metadata overlap |
| The Fantastic 4: First Steps | 2 | Low embedding similarity despite metadata overlap |
| Goosebumps: The Vanishing | 2 | Low embedding similarity despite metadata overlap |

### Frequently Over-Ranked (no metadata overlap)

| Entity | Times Over-Ranked | Likely Cause |
|--------|------------------|-------------|
| Peaky Blinders: The Immortal Man | 1 | High embedding similarity from composition text, but metadata doesn't overlap |
| The Dinosaurs | 1 | High embedding similarity from composition text, but metadata doesn't overlap |
| Chief of War | 1 | High embedding similarity from composition text, but metadata doesn't overlap |
| Saint of Chains | 1 | High embedding similarity from composition text, but metadata doesn't overlap |
| Ire: A Prologue | 1 | High embedding similarity from composition text, but metadata doesn't overlap |
| Terra Invicta | 1 | High embedding similarity from composition text, but metadata doesn't overlap |
| Star Trek: Voyager - Across the Unknown | 1 | High embedding similarity from composition text, but metadata doesn't overlap |
| Calx | 1 | High embedding similarity from composition text, but metadata doesn't overlap |
| One Lonely Outpost | 1 | High embedding similarity from composition text, but metadata doesn't overlap |
| Empyreal | 1 | High embedding similarity from composition text, but metadata doesn't overlap |

### Performance by Query Type

| Mode | Queries | Avg P@10 | Avg R@10 | Verdicts |
|------|---------|----------|----------|----------|
| entity_multi | 6 | 25.6% | 28.3% | {'GOOD': 1, 'FAIR': 3, 'POOR': 2} |
| entity_single | 6 | 31.7% | 33.3% | {'POOR': 3, 'FAIR': 2, 'EXCELLENT': 1} |
| mixed | 2 | 22.5% | 25.0% | {'FAIR': 1, 'POOR': 1} |
| theme_based | 4 | 13.0% | 40.0% | {'FAIR': 1, 'N/A (no metadata-based ideal)': 1, 'GOOD': 1, 'POOR': 1} |

---

## Section 4 — False Negative Analysis

These entities had high metadata overlap with query anchors but were not returned by the pipeline.

| Query | Missed Entity | Vertical | GT Score | Likely Reason |
|-------|-------------- |----------|----------|---------------|
| Q20 | Hades II | game | 47 | Embedding captures experiential essence rather than metadata attributes |
| Q20 | Wuchang: Fallen Feathers | game | 46 | Embedding captures experiential essence rather than metadata attributes |
| Q20 | Clair Obscur: Expedition 33 | game | 46 | Embedding captures experiential essence rather than metadata attributes |
| Q20 | Vessels of Decay | game | 45 | Embedding captures experiential essence rather than metadata attributes |
| Q20 | Abiotic Factor | game | 45 | Embedding captures experiential essence rather than metadata attributes |
| Q20 | Lost Soul Aside | game | 45 | Embedding captures experiential essence rather than metadata attributes |
| Q20 | Dwarves: Glory, Death and Loot | game | 45 | Embedding captures experiential essence rather than metadata attributes |
| Q20 | Primal Planet | game | 45 | Embedding captures experiential essence rather than metadata attributes |
| Q20 | Little Nightmares III | game | 45 | Embedding captures experiential essence rather than metadata attributes |
| Q20 | Dragonkin: The Banished | game | 45 | Embedding captures experiential essence rather than metadata attributes |
| Q1 | Little Nightmares III | game | 27 | Embedding captures experiential essence rather than metadata attributes |
| Q7 | Titan Quest II | game | 27 | Embedding captures experiential essence rather than metadata attributes |
| Q1 | Haste | game | 26 | Embedding captures experiential essence rather than metadata attributes |
| Q1 | Adorable Adventures | game | 26 | Embedding captures experiential essence rather than metadata attributes |
| Q1 | Silent Hill f | game | 25 | Embedding captures experiential essence rather than metadata attributes |
| Q7 | Hytale | game | 25 | Embedding captures experiential essence rather than metadata attributes |
| Q7 | The Seven Deadly Sins: Origin | game | 25 | Embedding captures experiential essence rather than metadata attributes |
| Q7 | Atomfall | game | 25 | Embedding captures experiential essence rather than metadata attributes |
| Q7 | Legend of Ymir | game | 25 | Embedding captures experiential essence rather than metadata attributes |
| Q1 | Time Flies | game | 24 | Embedding captures experiential essence rather than metadata attributes |
| Q1 | Primal Planet | game | 24 | Embedding captures experiential essence rather than metadata attributes |
| Q1 | Is This Seat Taken? | game | 23 | Embedding captures experiential essence rather than metadata attributes |
| Q1 | Clair Obscur: Expedition 33 | game | 22 | Embedding captures experiential essence rather than metadata attributes |
| Q17 | Greek Tragedy | game | 20 | Embedding captures experiential essence rather than metadata attributes |
| Q17 | I Hate this Place | game | 19 | Embedding captures experiential essence rather than metadata attributes |

### Why Pipeline Misses High-Metadata Entities

The pipeline uses **experiential embeddings** (based on 180-word compositions describing how content *feels*) rather than metadata matching. This creates a deliberate tradeoff:

- **Embedding advantage:** Captures subjective similarity — two entities can feel alike despite having different genres/themes in metadata (e.g., a horror game and a thriller movie)
- **Metadata advantage:** Captures objective overlap — shared genres, developers, and franchises are strong signals that metadata catches but embeddings may miss
- **BM25 bridge:** The keyword search partially bridges this gap by matching genre terms directly

---

## Section 5 — Recommendations for Improvement

### 5.1 Scoring Weight Adjustments
- The current 0.7 vector / 0.3 BM25 split favors experiential similarity over metadata matching
- Consider testing 0.6/0.4 or 0.5/0.5 to give BM25 keywords more influence, especially for within-vertical queries where genre matching matters more

### 5.2 Metadata-Augmented Retrieval
- Add a third retrieval signal: direct metadata overlap scoring (genre + theme + franchise)
- Weight: 0.5 vector + 0.25 BM25 + 0.25 metadata
- This would capture entities that the ground truth identifies as relevant but embeddings miss

### 5.3 Composition Improvements
- Entities whose compositions don't reflect their genre metadata well will have low embedding similarity despite high metadata overlap
- Consider appending genre/theme tags to compositions before embedding, or generating a secondary 'genre-focused' embedding per entity

### 5.4 Franchise and Developer Boosting
- Only 119/1,757 entities have franchise data — enriching this would improve franchise-based boosting
- Developer/publisher matches are a strong signal for game recommendations but are currently unused in scoring

### 5.5 Hybrid Ideal Metric
- The ground truth metric here is purely metadata-based, which penalizes the pipeline for making subjectively good recommendations that don't share metadata tags
- A better evaluation would combine metadata overlap + human relevance judgments

