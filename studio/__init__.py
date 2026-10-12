"""Stem Studio: a web API and UI around the stem agent.

The studio never runs the agent in its own process. Every command (grow,
selftest, baseline, matrix, check) is started as `python -m stem ...` in a
child process, exactly as from the command line, and the studio reads its
output and the files it writes under runs/.
"""
