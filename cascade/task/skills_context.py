"""Load skill playbook text and persist it on task graph state."""

from __future__ import annotations

from pathlib import Path

from cascade.watchdog.skills import effective_skill_paths


def load_skills_context(root: Path, skills: list[str]) -> list[dict]:
    """Read validated in-repo skill files as ``{path, text}`` playbook entries."""

    if not skills:
        return []
    repo = Path(root).resolve()
    relative_paths = effective_skill_paths(repo, [Path(p) for p in skills])
    playbooks: list[dict] = []
    for rel in relative_paths:
        text = (repo / rel).read_text(encoding="utf-8")
        playbooks.append({"path": rel, "text": text})
    return playbooks


def apply_skill_playbooks(task_id: str, playbooks: list[dict], *, root: Path) -> None:
    """Write playbook entries into graph state ``skill_playbooks``."""

    from cascade.task.checkpoint import thread_config
    from cascade.task.graph import ensure_task_graph

    repo = Path(root).resolve()
    graph = ensure_task_graph(task_id, root=repo)
    config = thread_config(task_id)
    snapshot = graph.get_state(config)
    if not snapshot.values:
        graph.update_state(
            config,
            {
                "task_id": task_id,
                "feature_id": "",
                "messages": [],
                "last_queue_offset": 0,
                "skill_playbooks": playbooks,
            },
        )
        return
    graph.update_state(config, {"skill_playbooks": playbooks})
