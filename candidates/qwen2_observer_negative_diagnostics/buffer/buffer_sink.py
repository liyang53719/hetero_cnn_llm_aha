class BoundedEvidenceSink:
    """Diagnostic-only, whole-frame bounded userspace buffer.

    Returning from write acknowledges RAM acceptance, NOT storage persistence.
    Explicit flush/close drains RAM. Unexpected exit may lose <= capacity bytes.
    After a storage error, never retry an uncertain write or flush on close.
    A successful OS write is not power-loss durability; seal's fsync is separate.
    """
    def __init__(self, raw, capacity):
        self.raw, self.capacity = raw, capacity
        self.pending = bytearray()
        self.persisted_bytes = self.storage_write_calls = 0
        self.persisted_hash = hashlib.sha256()
        self.failure = None
        self.uncertain = self.closed = False

    def _drain(self):
        if self.failure is not None:
            raise OSError('buffer storage failed; no retry: ' + self.failure)
        if not self.pending:
            return
        self.storage_write_calls += 1
        try:
            written = self.raw.write(self.pending)
        except BaseException as error:
            # A write may have changed the file before raising. Only the prior
            # acknowledged prefix is known; inspect the actual file separately.
            self.uncertain = True
            self.failure = type(error).__name__ + ': ' + str(error)
            raise
        if type(written) is not int or not 0 <= written <= len(self.pending):
            self.uncertain = True
            self.failure = 'invalid raw write result'
            raise OSError(self.failure)
        self.persisted_hash.update(self.pending[:written])
        self.persisted_bytes += written
        del self.pending[:written]
        if self.pending:
            self.failure = 'short buffered event stream write; partial prefix preserved'
            raise OSError(self.failure)

    def write(self, raw):
        if self.closed or self.failure is not None:
            raise OSError('closed/failed bounded evidence sink')
        if len(raw) > self.capacity:
            raise ValueError('single write exceeds fixed buffer capacity')
        if len(self.pending) + len(raw) > self.capacity:
            self._drain()
        self.pending.extend(raw)
        return len(raw)

    def flush(self):
        self._drain()
        self.raw.flush()

    def fileno(self):
        return self.raw.fileno()

    def close(self):
        if self.closed:
            return
        try:
            if self.failure is None:
                self.flush()
        finally:
            self.closed = True
            self.raw.close()

