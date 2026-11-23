"""Shared alternating row colors for application tables."""
from tkinter import ttk


class StripedTreeview(ttk.Treeview):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stripe_pending = None
        # Optional callable(item) -> key; neighbouring rows with the same non-None key share one shade
        self.stripe_group = None
        self.bind('<Map>', self._queue_stripes, add='+')
        self.bind('<<TreeviewOpen>>', self._queue_stripes, add='+')
        self.bind('<<TreeviewClose>>', self._queue_stripes, add='+')

    def _queue_stripes(self, event=None):
        if self._stripe_pending is None:
            self._stripe_pending = self.after_idle(self._stripe_rows)

    def _stripe_rows(self):
        self._stripe_pending = None
        if 'headings' not in tuple(map(str, self['show'])):
            return
        from config import load_theme
        from ui.theme import modern_color
        theme = load_theme()
        if theme in ('modern', 'modern_slate', 'modern_orange'):
            colors = (modern_color('#232A31'), modern_color('#1D2228'))
        else:
            colors = ('#252525' if theme == 'elite_orange' else '#282828', '#1e1e1e')
        # Existing semantic tags retain priority over the fallback stripe.
        for tag, color in zip(('_stripe_even', '_stripe_odd'), colors):
            self.tag_configure(tag, background=color)
        def rows(parent=''):
            for item in self.get_children(parent):
                yield item
                if self.item(item, 'open'):
                    yield from rows(item)
        band, band_key = -1, None
        for row_index, item in enumerate(rows()):
            key = self.stripe_group(item) if self.stripe_group else None
            if key is None:
                index = row_index
            else:
                if key != band_key:
                    band, band_key = band + 1, key
                index = band
            parity = 'evenrow' if index % 2 == 0 else 'oddrow'
            tags = []
            for tag in self.item(item, 'tags'):
                if tag.startswith('_stripe_'):
                    continue
                if tag.startswith(('evenrow', 'oddrow')):
                    suffix = tag[7:] if tag.startswith('evenrow') else tag[6:]
                    tag = parity + suffix
                    self.tag_configure(tag, background=colors[index % 2])
                tags.append(tag)
            tags.append('_stripe_even' if index % 2 == 0 else '_stripe_odd')
            super().item(item, tags=tags)

    def insert(self, *args, **kwargs):
        item = super().insert(*args, **kwargs)
        self._queue_stripes()
        return item

    def move(self, *args, **kwargs):
        result = super().move(*args, **kwargs)
        self._queue_stripes()
        return result

    reattach = move

    def delete(self, *items):
        super().delete(*items)
        self._queue_stripes()

    def detach(self, *items):
        super().detach(*items)
        self._queue_stripes()

    def item(self, item, option=None, **kwargs):
        result = super().item(item, option, **kwargs)
        if 'tags' in kwargs or 'open' in kwargs:
            self._queue_stripes()
        return result
