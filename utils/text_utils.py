"""Small text-formatting helpers shared across notification/email code."""


def isolate(text):
    """Wrap a short left-to-right token (e.g. "#12") in Unicode
    directional-isolate marks (LRI/PDI) so it always renders as one
    left-to-right unit wherever it's dropped into Arabic (RTL) text —
    a title, an OS push notification, a comment note, etc.

    Why this is needed: a plain "#4" is just a neutral "#" followed by a
    digit. Surrounded by Arabic words and punctuation (dashes, slashes),
    the Unicode bidi algorithm has to guess how that neutral run attaches
    to its neighbors, and under a forced/ambiguous paragraph direction —
    exactly what OS-level push notifications use — it can guess wrong and
    reorder the "#", the digit, and the surrounding words relative to each
    other (reported as e.g. "# Ticket 4" showing up instead of "Ticket
    #4"). Isolating the token removes the ambiguity: whatever is inside
    never gets reordered against what's outside.
    """
    return f"⁦{text}⁩"


def ticket_ref(serial):
    """'#<serial>', isolated — the token to use any time a ticket number
    is woven into Arabic (or bilingual) notification/title text."""
    return isolate(f"#{serial}")
