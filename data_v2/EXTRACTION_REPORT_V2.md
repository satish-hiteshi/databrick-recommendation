# Feeds.ai V2 Entity Profile Extraction Report

**Generated:** 2026-05-28 18:10
**Verticals processed:** Movie, TV, Podcast (Games deferred)

---

## 1. Deduplication Results

For each (name, node_type) pair with duplicates, kept ONLY the row with the latest `created_at` timestamp.

| Vertical | Before dedup | Duplicates removed | After dedup |
|----------|--------------|--------------------|-------------|
| Movie | 1,160 | 503 | 657 |
| TV | 756 | 459 | 297 |
| Podcast | 18,459 | 100 | 18,359 |
| **TOTAL** | **20,375** | **1,062** | **19,313** |

## 2. Clean Unique Entity Counts

- **Movie:** 657
- **TV:** 297
- **Podcast:** 18,359
- **Total:** 19,313

## 3. Source Match Rates

### Movies
- Exact match: 626 (95.3%)
- Contains match: 5 (0.8%)
- Unmatched: 26 (4.0%)

### TV
- Exact match: 288 (97.0%)
- Contains match: 2 (0.7%)
- Unmatched: 7 (2.4%)

### Podcasts
- Exact match: 18,341 (99.9%)
- Contains match: 4 (0.0%)
- Unmatched: 14 (0.1%)

## 4. Genre Coverage (Movies/TV)

- **Movie:** 631/657 (96.0%) have at least one genre
- **TV:** 290/297 (97.6%) have at least one genre

## 5. Release Date Coverage (Movies/TV)

- **Movie:** 631/657 (96.0%)
- **TV:** 290/297 (97.6%)

## 6. Cast Coverage (Movies/TV)

- **Movie:** 457/657 (69.6%) have at least one cast member
- **TV:** 173/297 (58.2%) have at least one cast member

## 7. Podcast Description Coverage

- With description: 18,349/18,359 (99.9%)
- Dropped (no description): 10

## 8. Podcast Power Score Distribution (Top 2,000)

- Count with power_score: 2,000
- Min: 68.99
- Max: 99.0
- Median: 73.83
- Cutoff at 2,000th podcast: 68.99

### Top 5 podcasts by power_score

| Rank | Name | Power Score |
|------|------|-------------|
| 1 | Global News Podcast | 99.0 |
| 2 | Crime Junkie | 99.0 |
| 3 | Dateline NBC | 99.0 |
| 4 | Stuff You Should Know | 99.0 |
| 5 | The Joe Rogan Experience | 99.0 |

### Bottom 5 podcasts that made the cut

| Rank | Name | Power Score |
|------|------|-------------|
| 1996 | The Gooner Factory | 69.01 |
| 1997 | The Bowery Boys: New York City History | 69.0 |
| 1998 | Scary Interesting Podcast | 69.0 |
| 1999 | We're Having Gay Sex | 69.0 |
| 2000 | Gayish Podcast | 68.99 |

## 9. Total Entities Ready for Composition

- **Movies:** 657
- **TV:** 297
- **Podcasts:** 2,000 (top 2,000 by power_score)
- **TOTAL:** 2,954

## 10. Unmatched Entities

Entities that could not be matched to any source entity by name.

### Movie — 26 unmatched

- 19 Hz
- Behind the Curtain: Stranger Things: The First Shadow
- Björk: Cornucopia
- Cash Out 2: High Rollers
- Castration Movie Anthology iii. Year of the Hyaena
- Coyote vs ACME
- Den of Thieves 2: Pantera
- Descendants/ZOMBIES Worlds Collide - Concert Special
- F Marry Kill
- F1
- Final Destination Bloodlines
- I'll Never Let You Go
- JC Bratton's Dollhouse
- Karen Kingsbury's The Christmas Ring
- LEGO Frozen: Operation Puffins
- Marcel et Monsieur Pagnol
- Marked Men: Rule + Shaw
- Masaka Kids, A Rhythm Within
- Nikola Tesla's 19hz
- Ozzy: No Escape from Now
- Sherlock Holmes Mare of the Night
- Taylor Swift | The Eras Tour | The Final Show
- Terry McMillan Presents: His, Hers & Ours
- The Ainsley McGregor Mysteries: A Case for the Yarn Maker
- Wizard of Oz: Dead Walk
- Z-O-M-B-I-E-S 4: Dawn of the Vampires

### TV — 7 unmatched

- David Blaine Do Not Attempt
- E.B. White's Charlotte's Web
- Oh My God... Yes! A Series of Extremely Relatable Circumstances
- R.J. Decker
- Temonator
- The Bad Guys: The Series
- Velvet, El Nuevo Imperio

### Podcast — 14 unmatched

- 5 Daily Trivia Questions -  five ways to test your knowledge
- Agent Survival Guide Podcast
- Almost Adulting with Violet Benson
- Almost Fameless
- Darkest Mysteries Online — The Strange and Unusual Podcast 2026
- Good Sod Pod
- Hustlers Universe Network
- Joy Lab Podcast
- Michelle Foster
- Palace Intrigue : Former Prince Andrew Arrested - Royal Family gossip
- Sherapy Sessions: Cutting Toxic Family Ties
- The Life Of Phys
- The Projection Booth Podcast
- What's Wrong with Wrestling? WWE Recap Show
