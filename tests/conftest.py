"""Pytest setup: force stubs so no test touches the network."""
import os

os.environ["SEEN_IT_STUBS"] = "1"
