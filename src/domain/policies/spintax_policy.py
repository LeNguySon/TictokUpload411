"""
Spintax Engine for TikTok Profile Bio, Comments, and Captions.
Learned from Gloglin2609/engine/tiktok/spintax.py.
Supports recursive/nested Spintax syntax: {option1|option2|{sub1|sub2}}
"""

from __future__ import annotations

import random
import re


def spin_text(template: str, rng: random.Random | None = None) -> str:
    """Recursively resolve Spintax patterns: {option1|option2|option3}.

    Examples:
        >>> spin_text("{Hello|Hi|Hey} world!")
        'Hi world!'
        >>> spin_text("Welcome to {my page|{my channel|my official account}}.")
        'Welcome to my channel.'
    """
    if not template or "{" not in template or "}" not in template:
        return template

    r = rng or random.Random()
    pattern = re.compile(r"\{([^{}]+)\}")

    result = template
    limit = 50  # Prevent infinite loop on malformed strings
    while limit > 0:
        limit -= 1
        match = pattern.search(result)
        if not match:
            break
        options = match.group(1).split("|")
        chosen = r.choice(options)
        result = result[: match.start()] + chosen + result[match.end() :]

    return result
