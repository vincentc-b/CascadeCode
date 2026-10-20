from __future__ import annotations

import pytest

from cascade.epic.graph import clear_epic_graph_sessions
from cascade.feature.graph import clear_feature_graph_sessions
from cascade.task.graph import clear_task_graph_sessions
from cascade.workspace.kickoff import wait_for_background_kickoffs


@pytest.fixture(autouse=True)
def _drain_background_kickoffs():
    """War Room POSTs queue model turns on worker threads; keep them inside their test."""

    yield
    wait_for_background_kickoffs()
    clear_epic_graph_sessions()
    clear_feature_graph_sessions()
    clear_task_graph_sessions()
