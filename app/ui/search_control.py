import threading
import logging

from localization import t


class SearchControl:
    def __init__(self, parent, button, status, on_finish=None):
        self.parent = parent
        self.button = button
        self.status = status
        self.on_finish = on_finish
        self.search_text = button.cget('text')
        self.running = False
        self._cancel = threading.Event()
        self._generation = 0

    def start(self):
        self._generation += 1
        self._cancel = threading.Event()
        self.running = True
        self.button.config(text=t('ring_finder.stop'), state='normal')

    def stop(self):
        if self.running:
            self._cancel.set()
            if self.button.winfo_exists():
                self.button.config(text=t('common.stopping'), state='disabled')
                self.status.config(text=t('common.stopping'))

    def is_cancelled(self):
        return self._cancel.is_set()

    def run(self, worker, *args):
        try:
            worker(*args)
        except Exception as exc:
            logging.exception('Search failed')
            self.failed(str(exc))

    def progress(self, message):
        self.parent.after(0, self._progress, self._generation, message)

    def _progress(self, generation, message):
        if (generation == self._generation and self.running and not self.is_cancelled()
                and self.status.winfo_exists()):
            self.status.config(text=message)

    def complete(self, results, callback, *args):
        self.parent.after(0, self._finish, self._generation, results, callback, args)

    def failed(self, message):
        self.parent.after(0, self._finish, self._generation, None, None, (message,))

    def _finish(self, generation, results, callback, args):
        if generation != self._generation or not self.running:
            return
        self.running = False
        if not self.button.winfo_exists():
            return
        self.button.config(text=self.search_text, state='normal')
        try:
            if callback is not None and (results or not self.is_cancelled()):
                callback(results, *args)
            elif callback is None and not self.is_cancelled():
                self.status.config(text=t('marketplace.search_failed').format(error=args[0]))
        finally:
            if self.is_cancelled():
                self.status.config(text=t('ring_finder.search_stopped'))
            if self.on_finish:
                self.on_finish()
