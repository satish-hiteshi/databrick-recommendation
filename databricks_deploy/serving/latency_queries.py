"""latency_queries.py — categorized query bank for per-path latency testing (~50 per type).

Each bucket is built to BIAS toward one router path, so you can see how latency differs by the engine
work each path does:

  vector_mood        pure vector establish (fast baseline)     -> VECTOR_CONSTRAIN
  vector_structural  vector establish + graph rerank           -> VECTOR_CONSTRAIN__GRAPH_RERANK
  seed_single        single "like X" seed                      -> SEED_VECTOR…
  seed_multi         "like X and Y"                            -> MULTISEED…
  graph_negate       negation / graph-heavy                    -> GRAPH_…NEGATE
  multivertical      cross-vertical fan-out                    -> MULTIVERTICAL[…]
  multi_intent       two distinct asks                         -> MULTI_INTENT

The LLM picks the final path, so a bucket is a STRONG bias, not a guarantee — the runner prints the
actual `path_taken` so you can see routing too. Pure stdlib: `from latency_queries import QUERIES_BY_TYPE`.
"""

GAMES = ["Stardew Valley", "Elden Ring", "Hades", "Hollow Knight", "Slay the Spire", "The Witcher 3",
         "Celeste", "Disco Elysium", "Stray", "Baldur's Gate 3", "Animal Crossing", "Minecraft",
         "Dark Souls", "Breath of the Wild", "Portal", "Terraria", "Outer Wilds", "Cuphead",
         "Factorio", "Spiritfarer"]
MOVIES = ["Inception", "Interstellar", "The Matrix", "Spirited Away", "Parasite", "Blade Runner 2049",
          "La La Land", "Whiplash", "Arrival", "Knives Out", "Everything Everywhere All at Once",
          "Mad Max Fury Road"]
TV = ["Breaking Bad", "The Last of Us", "Stranger Things", "The Witcher", "Severance", "The Bear",
      "Ted Lasso", "Dark", "Black Mirror", "Arcane", "The Boys", "Avatar The Last Airbender"]
PODS = ["Serial", "This American Life", "Hardcore History", "Radiolab", "Lex Fridman", "SmartLess",
        "Conan O'Brien Needs a Friend", "Darknet Diaries", "99% Invisible", "Reply All"]

MOODS = ["cozy", "dark and atmospheric", "lighthearted", "intense", "relaxing", "thought-provoking",
         "feel-good", "gritty", "whimsical", "melancholic", "fast-paced", "slow-burn", "wholesome", "eerie"]
GENRES = ["horror", "sci-fi", "fantasy", "roguelike", "narrative-driven", "open-world", "puzzle",
          "survival", "mystery", "noir", "post-apocalyptic", "cyberpunk"]
MODES = ["co-op", "couch co-op", "split-screen", "single-player", "local multiplayer", "turn-based",
         "base-building", "deckbuilding", "open-world", "crafting", "story-rich", "sandbox"]
OCCASIONS = ["for a rainy night", "after a long day", "with my partner", "with friends",
             "for the whole family", "on my commute", "to fall asleep to", "for a date night",
             "this weekend", "to unwind"]
NEGATIONS = ["jump scares", "grinding", "microtransactions", "gore", "permadeath", "violence",
             "a steep learning curve", "too much hand-holding", "filler episodes", "cliffhangers"]
VERTS = ["games", "movies", "shows", "podcasts"]


def _take(seq, n=50):
    """Dedupe preserving order, return the first n."""
    out, seen = [], set()
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
        if len(out) >= n:
            break
    return out


def _g(lst, i):
    return lst[i % len(lst)]


# ── pure vector establish — mood/descriptive, single vertical (fast baseline) ──
vector_mood = _take(
    [f"{_g(MOODS, i)} {_g(VERTS, i)} {_g(OCCASIONS, i)}" for i in range(70)])

# ── structural mode/feature → vector establish + graph rerank (games) ──
vector_structural = _take(
    [f"{m} {g} games" for g in GENRES for m in MODES] +
    [f"a {g} game with {m}" for g in GENRES for m in MODES])

# ── single seed "like X" (across verticals) ──
_seed_tpl = []
for i in range(60):
    _seed_tpl += [
        f"games like {_g(GAMES, i)}",
        f"movies like {_g(MOVIES, i)}",
        f"shows like {_g(TV, i)}",
        f"podcasts like {_g(PODS, i)}",
        f"something like {_g(GAMES, i + 5)} but more {_g(MOODS, i)}",
    ]
seed_single = _take(_seed_tpl)

# ── multi-seed "like X and Y" ──
seed_multi = _take(
    [f"games like {_g(GAMES, i)} and {_g(GAMES, i + off)}" for off in (7, 11, 3) for i in range(20)] +
    [f"if I loved {_g(TV, i)} and {_g(TV, i + 5)}, what should I watch next?" for i in range(12)] +
    [f"movies like {_g(MOVIES, i)} and {_g(MOVIES, i + 4)}" for i in range(12)])

# ── negation / graph-heavy ──
graph_negate = _take(
    [f"{_g(GENRES, i)} games without {_g(NEGATIONS, i)}" for i in range(30)] +
    [f"{_g(GENRES, i)} games that aren't too {_g(MOODS, i)}" for i in range(30)] +
    [f"{_g(MOODS, i)} shows but not {_g(GENRES, i + 3)}" for i in range(20)])

# ── cross-vertical fan-out ──
multivertical = _take(
    [f"games and shows like {_g(GAMES, i)}" for i in range(20)] +
    [f"{_g(MOODS, i)} games and movies {_g(OCCASIONS, i)}" for i in range(20)] +
    [f"{_g(GENRES, i)} across games, movies, and TV" for i in range(20)] +
    [f"something {_g(MOODS, i)} to play, watch, or listen to {_g(OCCASIONS, i)}" for i in range(20)])

# ── two distinct asks (multi-intent) ──
multi_intent = _take(
    [f"a {_g(MODES, i)} game for tonight and a {_g(MOODS, i)} podcast for my commute" for i in range(25)] +
    [f"{_g(GENRES, i)} movies to watch and {_g(GENRES, i + 2)} games to play" for i in range(25)] +
    [f"something funny for my drive and something {_g(MOODS, i)} to wind down with" for i in range(20)])

QUERIES_BY_TYPE = {
    "vector_mood": vector_mood,
    "vector_structural": vector_structural,
    "seed_single": seed_single,
    "seed_multi": seed_multi,
    "graph_negate": graph_negate,
    "multivertical": multivertical,
    "multi_intent": multi_intent,
}

if __name__ == "__main__":
    for t, qs in QUERIES_BY_TYPE.items():
        print(f"{t:<18} {len(qs):>3} queries   e.g. {qs[0]!r}")
