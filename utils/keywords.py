"""
Search-term generation.

A fixed list reshuffled every day still sends the same twenty strings forever, which
is the opposite of what a person's search history looks like. This builds terms by
combining topics with modifiers and seeds the generator from the date, so a given day
is reproducible for debugging while consecutive days share little vocabulary.

Terms are also grown in small clusters: a broad query followed by a refinement of it,
the way someone actually narrows in on what they wanted.
"""

import random
from datetime import date

TOPICS = [
    "sourdough bread", "electric cars", "coastal walks", "film noir",
    "houseplants", "budget travel", "chess openings", "mechanical keyboards",
    "urban gardening", "jazz records", "hiking boots", "espresso machines",
    "wildlife photography", "board games", "sleep quality", "running shoes",
    "home insulation", "language learning", "fermentation", "watercolour",
    "solar panels", "bird migration", "pasta shapes", "night sky",
    "second hand books", "cycling routes", "tea varieties", "pottery",
    "storm chasing", "bread knives", "moss gardens", "vinyl records",
    "cold brew", "trail running", "wool jumpers", "dry stone walls",
]

MODIFIERS = [
    "for beginners", "explained", "worth it", "vs alternatives", "common mistakes",
    "how to start", "on a budget", "UK", "reviews", "guide", "tips",
    "what to look for", "step by step", "at home", "problems",
]

REFINEMENTS = [
    "best {t} {m}", "{t} {m} 2026", "is {t} worth it", "how much does {t} cost",
    "{t} for small spaces", "cheap {t} {m}", "{t} near me", "why {t}",
]


def _rng(seed_date: date | None, salt: str = "") -> random.Random:
    seed_date = seed_date or date.today()
    return random.Random(f"{seed_date.isoformat()}{salt}")


def generate(count: int, seed_date: date | None = None) -> list[str]:
    """
    Build `count` search terms for a given day.

    Roughly a third of the terms are refinements of the term immediately before them,
    which is what genuine sequential searching tends to look like.
    """
    rng = _rng(seed_date)
    topics = TOPICS[:]
    rng.shuffle(topics)

    terms: list[str] = []
    topic_idx = 0

    while len(terms) < count:
        if terms and rng.random() < 0.35:
            # Refine the previous query rather than jumping to an unrelated topic.
            base = topics[(topic_idx - 1) % len(topics)]
            template = rng.choice(REFINEMENTS)
            term = template.format(t=base, m=rng.choice(MODIFIERS))
        else:
            base = topics[topic_idx % len(topics)]
            topic_idx += 1
            term = base if rng.random() < 0.4 else f"{base} {rng.choice(MODIFIERS)}"

        term = " ".join(term.split())
        if term not in terms:
            terms.append(term)

    return terms[:count]
