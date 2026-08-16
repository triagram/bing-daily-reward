"""
Search-term generation.

A fixed list reshuffled every day still sends the same strings forever, which is the
opposite of what a person's search history looks like. Terms are built by combining
topics with refinements and seeded from the date, so a given day is reproducible for
debugging while consecutive days share little vocabulary.

Refinements are matched to the *kind* of topic rather than drawn from one pool. An
earlier version applied any modifier to any subject and produced "film noir for small
spaces" and "wildlife photography for small spaces" — grammatical, but not phrases a
person would type. Nonsensical queries are one of the signals Rewards is documented to
act on, so the shape of the text matters, not just its variety.

Terms are also grown in small clusters: a broad query followed by a refinement of it,
the way someone actually narrows in on what they wanted.
"""

import random
from datetime import date

# Topics grouped by what you would sensibly ask about them.
TOPICS: dict[str, list[str]] = {
    "gear": [
        "mechanical keyboards", "espresso machines", "hiking boots", "running shoes",
        "solar panels", "bread knives", "wool jumpers", "record players",
        "walking poles", "cast iron pans",
    ],
    "skill": [
        "sourdough bread", "chess openings", "watercolour", "language learning",
        "fermentation", "pottery", "wildlife photography", "touch typing",
        "bread baking", "knife sharpening",
    ],
    "place": [
        "coastal walks", "cycling routes", "trail running", "national parks",
        "dry stone walls", "canal paths", "hill forts", "tidal islands",
    ],
    "media": [
        "film noir", "jazz records", "vinyl records", "board games",
        "radio drama", "nature documentaries", "detective novels",
    ],
    "home": [
        "houseplants", "urban gardening", "moss gardens", "home insulation",
        "draught proofing", "window boxes", "compost bins",
    ],
    "nature": [
        "bird migration", "night sky", "storm chasing", "rock pools",
        "fungi foraging", "hedgerow plants", "moth trapping",
    ],
}

# Refinement patterns that read naturally for each kind of topic.
REFINEMENTS: dict[str, list[str]] = {
    "gear": [
        "best {t} uk", "{t} worth the money", "how much do {t} cost",
        "{t} for beginners", "cheap {t} that last", "{t} buying guide",
        "how to clean {t}", "{t} common problems",
    ],
    "skill": [
        "how to get started with {t}", "{t} for beginners", "{t} common mistakes",
        "{t} practice routine", "is {t} hard to learn", "{t} step by step",
        "how long to learn {t}",
    ],
    "place": [
        "best {t} in the uk", "{t} near me", "easy {t} for beginners",
        "{t} with a dog", "{t} in winter", "how to plan {t}",
    ],
    "media": [
        "best {t} of all time", "where to start with {t}", "{t} recommendations",
        "underrated {t}", "{t} for beginners", "history of {t}",
    ],
    "home": [
        "{t} for small spaces", "low maintenance {t}", "{t} in winter",
        "how to look after {t}", "{t} on a budget", "common {t} mistakes",
    ],
    "nature": [
        "when to see {t}", "{t} in the uk", "how to photograph {t}",
        "{t} for beginners", "best places for {t}", "identifying {t}",
    ],
}


def _rng(seed_date: date | None, salt: str = "") -> random.Random:
    return random.Random(f"{(seed_date or date.today()).isoformat()}{salt}")


def generate(count: int, seed_date: date | None = None) -> list[str]:
    """
    Build `count` search terms for a given day.

    Roughly a third are refinements of the topic just searched, which is what genuine
    sequential searching looks like — and the refinement is drawn from the pool that
    suits that topic, so the result stays idiomatic.
    """
    rng = _rng(seed_date)

    pool = [(kind, topic) for kind, topics in TOPICS.items() for topic in topics]
    rng.shuffle(pool)

    terms: list[str] = []
    index = 0
    previous: tuple[str, str] | None = None

    while len(terms) < count and index <= len(pool) * 3:
        if previous and rng.random() < 0.35:
            kind, topic = previous
            term = rng.choice(REFINEMENTS[kind]).format(t=topic)
        else:
            kind, topic = pool[index % len(pool)]
            index += 1
            previous = (kind, topic)
            term = topic

        term = " ".join(term.split())
        if term not in terms:
            terms.append(term)

    return terms[:count]
