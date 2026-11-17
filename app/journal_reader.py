"""Byte-based cursors for journals that the game may still be writing."""

import os


def journal_resume_offset(path):
    """Skip existing complete records, retaining any unfinished final record."""
    with open(path, 'rb') as journal:
        position = journal.seek(0, os.SEEK_END)
        while position:
            start = max(0, position - 4096)
            journal.seek(start)
            chunk = journal.read(position - start)
            newline = chunk.rfind(b'\n')
            if newline >= 0:
                return start + newline + 1
            position = start
        return 0


def read_complete_journal_lines(path, offset):
    """Return complete lines and the byte offset immediately after them."""
    if os.path.getsize(path) == offset:
        return [], offset
    with open(path, 'rb') as journal:
        size = journal.seek(0, os.SEEK_END)
        if offset > size:
            offset = 0
        journal.seek(offset)
        data = journal.read()
    end = data.rfind(b'\n') + 1
    # Leave an unfinished JSON record (including split UTF-8) for the next poll.
    lines = data[:end].decode('utf-8', errors='replace').splitlines()
    return lines, offset + end
