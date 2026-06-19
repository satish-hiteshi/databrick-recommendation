# Discovery feed — offline eval report (P4)

Pipeline: profile → pools → **blended scorer** → assembler (main feed + carousels) + why_strings. Substrate: **LIVE :8000/:8010**. now = `2026-06-18T00:00:00+00:00` (config.DEFAULT_NOW_ISO). Real dev CSVs.

## Sanity checks (all fixtures)

| fixture | ms | followed-leak | seen/excl-leak | cap-max (≤3) | why∀ | reason∀ | distinct top-10 scores | inf-ties broken |
|---|--:|--:|--:|--:|:--:|:--:|--:|:--:|
| cold_start_7064 | 930 | 0 | 0 | 1 | ✓ | ✓ | 8 | ✓ |
| personalized_12305 | 33632 | 0 | 0 | 1 | ✓ | ✓ | 10 | ✓ |
| paginated_12305_offset10 | 34643 | 0 | 0 | 1 | ✓ | ✓ | 10 | ✗ |

## Personalization proof (cold-start 7064 vs personalized 12305)

- main-feed entity **overlap = 0.0%** (low → the feeds genuinely differ).
- **personalized-only carousels** present for 12305, absent for 7064: **['popular_with_fans_of', 'similar_to_followed']**.
- pagination: page1 (offset 0) ∩ page2 (offset 10) moment overlap = **0** (0 = clean paging).

## cold_start_7064  (930 ms, mode=cold_start, signal_strength=0.0)

Main feed: 10 of 248 (next_offset=10). Carousels: trending×20, new_in_genre×20, new_in_genre×20, new_in_genre×20, new_in_genre×20, new_on_platform×20.

Main-feed sample (item — why_string — score | influence/recency):
- **Virginia Woolf's Night & Day** [movie] — _Popular movies_ — score 0.777 (inf 0.975, rec 0.9675, pw 0.0, sem 0.0)
- **Voicemails for Isabelle** [movie] — _Popular movies_ — score 0.777 (inf 0.975, rec 0.9675, pw 0.0, sem 0.0)
- **You Are the Film** [movie] — _New movies_ — score 0.764 (inf 0.9423, rec 0.9675, pw 0.0, sem 0.0)
- **Toy Story 5** [movie] — _New movies_ — score 0.762 (inf 0.9379, rec 0.9675, pw 0.0, sem 0.0)

Carousels (reason_string — size — a sample item):
- `trending` — _Trending now_ — 20 props — e.g. **Virginia Woolf's Night & Day** (_Trending in Romance_)
- `new_in_genre` — _New in Drama_ — 20 props — e.g. **Virginia Woolf's Night & Day** (_New in Drama_)
- `new_in_genre` — _New in Comedy_ — 20 props — e.g. **Virginia Woolf's Night & Day** (_New in Comedy_)
- `new_in_genre` — _New in Thriller_ — 20 props — e.g. **Hungry** (_New in Thriller_)
- `new_in_genre` — _New in Action_ — 20 props — e.g. **Stop! That! Train!** (_New in Action_)
- `new_on_platform` — _New on YouTube_ — 20 props — e.g. **Bad Counselors** (_New on YouTube_)

## personalized_12305  (33632 ms, mode=personalized, signal_strength=1.0)

Main feed: 10 of 393 (next_offset=10). Carousels: similar_to_followed×20, popular_with_fans_of×20, trending×20, new_in_genre×20, new_in_genre×20, new_in_genre×20, new_in_genre×20, new_on_platform×20.

Main-feed sample (item — why_string — score | influence/recency):
- **Cosmic Peach** [podcast] — _Because you follow Dune: Part Three_ — score 0.739 (inf 0.9018, rec 0.5809, pw 0.6, sem 0.8367)
- **IAllegedly** [podcast] — _Because you follow Dune: Part Three_ — score 0.724 (inf 0.7817, rec 0.5221, pw 0.6, sem 0.8595)
- **Honeydew Me** [podcast] — _Because you follow Dune: Part Three_ — score 0.704 (inf 0.8855, rec 0.4884, pw 0.6, sem 0.8075)
- **Strange Places** [podcast] — _Because you follow Dune: Part Three_ — score 0.666 (inf 0.975, rec 0.0277, pw 0.6, sem 0.8434)

Carousels (reason_string — size — a sample item):
- `similar_to_followed` — _Because you follow Dune: Part Three_ — 20 props — e.g. **Cosmic Peach** (_Because you follow Dune: Part Three_)
- `popular_with_fans_of` — _Popular with fans of Dune: Part Three_ — 20 props — e.g. **Cosmic Peach** (_Popular with fans of Dune: Part Three_)
- `trending` — _Trending now_ — 20 props — e.g. **Virginia Woolf's Night & Day** (_Trending in Romance_)
- `new_in_genre` — _New in Drama_ — 20 props — e.g. **Virginia Woolf's Night & Day** (_New in Drama_)
- `new_in_genre` — _New in Comedy_ — 20 props — e.g. **Virginia Woolf's Night & Day** (_New in Comedy_)
- `new_in_genre` — _New in Thriller_ — 20 props — e.g. **Hungry** (_New in Thriller_)
- `new_in_genre` — _New in Action_ — 20 props — e.g. **Stop! That! Train!** (_New in Action_)
- `new_on_platform` — _New on YouTube_ — 20 props — e.g. **Bad Counselors** (_New on YouTube_)

## paginated_12305_offset10  (34643 ms, mode=personalized, signal_strength=1.0)

Main feed: 10 of 393 (next_offset=20). Carousels: similar_to_followed×20, popular_with_fans_of×20, trending×20, new_in_genre×20, new_in_genre×20, new_in_genre×20, new_in_genre×20, new_on_platform×20.

Main-feed sample (item — why_string — score | influence/recency):
- **Is It Hot In Here? Midlife Podcast** [podcast] — _Because you follow Dune: Part Three_ — score 0.611 (inf 0.7534, rec 0.0283, pw 0.6, sem 0.8105)
- **Bobby on the Beat** [podcast] — _Because you follow Dune: Part Three_ — score 0.61 (inf 0.7213, rec 0.0288, pw 0.6, sem 0.8162)
- **The Lady Bod Pod** [podcast] — _Because you follow Dune: Part Three_ — score 0.609 (inf 0.7108, rec 0.0252, pw 0.6, sem 0.819)
- **The Tape Library - Archive of the Paranormal & t** [podcast] — _Because you follow Dune: Part Three_ — score 0.602 (inf 0.634, rec 0.0254, pw 0.6, sem 0.8283)

Carousels (reason_string — size — a sample item):
- `similar_to_followed` — _Because you follow Dune: Part Three_ — 20 props — e.g. **Cosmic Peach** (_Because you follow Dune: Part Three_)
- `popular_with_fans_of` — _Popular with fans of Dune: Part Three_ — 20 props — e.g. **Cosmic Peach** (_Popular with fans of Dune: Part Three_)
- `trending` — _Trending now_ — 20 props — e.g. **Virginia Woolf's Night & Day** (_Trending in Romance_)
- `new_in_genre` — _New in Drama_ — 20 props — e.g. **Virginia Woolf's Night & Day** (_New in Drama_)
- `new_in_genre` — _New in Comedy_ — 20 props — e.g. **Virginia Woolf's Night & Day** (_New in Comedy_)
- `new_in_genre` — _New in Thriller_ — 20 props — e.g. **Hungry** (_New in Thriller_)
- `new_in_genre` — _New in Action_ — 20 props — e.g. **Stop! That! Train!** (_New in Action_)
- `new_on_platform` — _New on YouTube_ — 20 props — e.g. **Bad Counselors** (_New on YouTube_)

## Non-degenerate ordering (influence ties broken)

Cold-start top-8 main feed — many share the clipped influence ceiling (0.975) yet final scores differ because recency breaks the tie:

| # | property | influence | recency | final |
|--:|---|--:|--:|--:|
| 1 | Virginia Woolf's Night & Day | 0.975 | 0.9675 | 0.777 |
| 2 | Voicemails for Isabelle | 0.975 | 0.9675 | 0.777 |
| 3 | You Are the Film | 0.9423 | 0.9675 | 0.7639 |
| 4 | Toy Story 5 | 0.9379 | 0.9675 | 0.7622 |
| 5 | Les caprices de l'enfant Roi | 0.975 | 0.8203 | 0.7181 |
| 6 | Stop! That! Train! | 0.975 | 0.8203 | 0.7181 |
| 7 | Bleach: Thousand-Year Blood War -  | 0.975 | 0.7937 | 0.7075 |
| 8 | Nurse the Dead | 0.9463 | 0.8203 | 0.7066 |
