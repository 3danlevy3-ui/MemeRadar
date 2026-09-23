"""Find stock tickers in Reddit text."""
import re

from . import config as C

CASHTAG = re.compile(r"\$([A-Za-z]{1,5})(?![A-Za-z])")
BARE = re.compile(r"(?<![A-Za-z$])([A-Z]{2,5})(?![A-Za-z])")


def extract(text, universe):
    """Return the set of tickers mentioned in one piece of text.

    $cashtags count for any valid ticker (any case); bare ALL-CAPS words only
    when they are valid tickers and not common WSB words.
    """
    if not text:
        return set()
    found = {m.upper() for m in CASHTAG.findall(text)}
    found = {t for t in found if t in universe}
    for m in BARE.findall(text):
        if m in universe and m not in C.STOPWORDS:
            found.add(m)
    return found
