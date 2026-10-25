"""Unchanged outer-stage process CPU/wall clock, no call instrumentation."""
import time


class Stages:
    def __init__(self):
        self.rows = []
        self.previous = (time.process_time_ns(), time.monotonic_ns())

    def mark(self, stage):
        current = (time.process_time_ns(), time.monotonic_ns())
        self.rows.append(dict(stage=stage, cpu_ns=current[0]-self.previous[0],
                             wall_ns=current[1]-self.previous[1]))
        self.previous = current

