"""Sort arrow on Treeview headings, shared by the app's sortable tables."""

ARROW_UP = " ▲"
ARROW_DOWN = " ▼"


def strip_sort_arrow(text):
    """Heading text without a trailing sort arrow."""
    return text[:-len(ARROW_UP)] if text.endswith((ARROW_UP, ARROW_DOWN)) else text


def apply_sort_arrow(tree, sorted_col, descending):
    """Show ▲ (ascending) / ▼ (descending) on sorted_col's heading and clear it from every other.

    Reads each heading's current text, so dynamic/localized titles are kept as they are.
    """
    for col in tree['columns']:
        text = strip_sort_arrow(str(tree.heading(col, 'text')))
        if not text:
            continue  # spacer column
        arrow = (ARROW_DOWN if descending else ARROW_UP) if col == sorted_col else ""
        tree.heading(col, text=text + arrow)
