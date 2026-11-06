from __future__ import annotations

import pytest

from cascade.board.context import set_project_context
from cascade.board.store import reset_id_reservations
from cascade.epic.graph import clear_epic_graph_sessions
from cascade.feature.graph import clear_feature_graph_sessions
from cascade.task.graph import clear_task_graph_sessions
from cascade.workspace.kickoff import reset_kickoff_test_state, wait_for_background_kickoffs
from tests.support import (
    SyntheticDependencyLifecycle,
    make_synthetic_dependency_lifecycle,
)


@pytest.fixture
def synthetic_dependency_lifecycle(tmp_path) -> SyntheticDependencyLifecycle:
    """Canonical epic_036 completion with an unreadable stale active copy."""

    return make_synthetic_dependency_lifecycle(tmp_path)


@pytest.fixture(autouse=True)
def _drain_background_kickoffs():
    """War Room POSTs queue model turns on worker threads; keep them inside their test."""

    reset_kickoff_test_state()
    reset_id_reservations()
    set_project_context(None)
    yield
    wait_for_background_kickoffs()
    reset_kickoff_test_state()
    reset_id_reservations()
    clear_epic_graph_sessions()
    clear_feature_graph_sessions()
    clear_task_graph_sessions()
    set_project_context(None)
