"""
SimEnvironment — minimal environment stub for agentsociety's StreamMemory.

StreamMemory.add() requires environment.get_datetime() to timestamp memories.
We provide this without any city gRPC infrastructure by tracking the current
simulation round as a tick counter.

Usage:
    env = SimEnvironment()
    env.set_round(round_num)   # call before each simulation round
    # StreamMemory uses env.get_datetime() → (day, seconds_since_midnight)
"""


class SimEnvironment:
    """
    Minimal environment providing get_datetime() for StreamMemory.
    No gRPC, no city simulator — just a tick counter driven by round number.
    """

    # 1 simulated round = 1 simulated hour
    SECONDS_PER_ROUND = 3600

    def __init__(self, start_hour: int = 8):
        # Start at 08:00 on day 0
        self._tick = 0
        self._start_tick = start_hour * 3600

    def set_round(self, round_num: int):
        """Advance the simulation clock to the given round."""
        self._tick = round_num * self.SECONDS_PER_ROUND

    def get_datetime(self, format_time: bool = False, format: str = "%H:%M:%S"):
        """
        Return (day, time) matching agentsociety's Environment.get_datetime().

        Returns:
            (day: int, time: int)  — day index and seconds since midnight
        """
        ticks = self._tick + self._start_tick
        day  = ticks // (24 * 3600)
        time = ticks % (24 * 3600)

        if format_time:
            hours   = time // 3600
            minutes = (time % 3600) // 60
            seconds = time % 60
            formatted = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            return (day, formatted)

        return (day, time)
