"""
goal_context.py — build goal chain context for injection into heartbeat/routine prompts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy import text

WORKSPACE = Path(__file__).resolve().parent.parent.parent


def _get_session():
    """Return a SQLAlchemy session using the shared engine from db.session."""
    from db.session import get_session
    return get_session()


def build_goal_context(
    project_id: Optional[str] = None,
    goal_id: Optional[str] = None,
) -> str:
    """
    Build a context string for injection into agent prompts.

    Args:
        project_id: slug of the project (e.g. "evo-ai")
        goal_id: slug of the goal (e.g. "evo-ai-100-customers")

    Returns:
        Context string or empty string if goals disabled / IDs not found.
    """
    if not project_id and not goal_id:
        return ""

    try:
        with _get_session() as session:
            if goal_id:
                return _context_from_goal(session, goal_id)
            elif project_id:
                return _context_from_project(session, project_id)
            return ""
    except Exception as exc:
        # Never crash the runner — log and skip
        print(f"[goal_context] WARNING: failed to build context: {exc}")
        return ""


def _context_from_goal(session, goal_slug: str) -> str:
    """Full Mission → Project → Goal chain for a specific goal."""
    row = session.execute(text("""
        SELECT g.id, g.title, g.current_value, g.target_value, g.metric_type, g.due_date, g.status,
               p.title AS project_title, p.id AS project_id,
               m.title AS mission_title, m.target_value AS mission_target, m.due_date AS mission_due,
               m.status AS mission_status,
               (SELECT COUNT(*) FROM goal_tasks t WHERE t.goal_id = g.id AND t.status = 'open') AS open_tasks
        FROM goals g
        JOIN projects p ON p.id = g.project_id
        LEFT JOIN missions m ON m.id = p.mission_id
        WHERE g.slug = :slug
    """), {"slug": goal_slug}).fetchone()

    if not row:
        return ""

    lines = ["## Goal Context"]
    if row.mission_title:
        lines.append(
            f"Mission: {row.mission_title} "
            f"(target: {row.mission_target}, due {row.mission_due}, status {row.mission_status})"
        )
    lines.append(f"Project: {row.project_title}")
    lines.append(
        f"Goal: {row.title} "
        f"({row.current_value}/{row.target_value} {row.metric_type}, due {row.due_date})"
    )
    lines.append(f"Open tasks on this goal: {row.open_tasks}")
    lines.append("")
    return "\n".join(lines)


def _context_from_project(session, project_slug: str) -> str:
    """List active goals for a project when only project_id is declared."""
    proj = session.execute(text("""
        SELECT p.id, p.title, m.title AS mission_title
        FROM projects p
        LEFT JOIN missions m ON m.id = p.mission_id
        WHERE p.slug = :slug
    """), {"slug": project_slug}).fetchone()

    if not proj:
        return ""

    active_goals = session.execute(text("""
        SELECT title, current_value, target_value, metric_type, due_date
        FROM goals
        WHERE project_id = :pid AND status = 'active'
        ORDER BY due_date ASC NULLS LAST
    """), {"pid": proj.id}).fetchall()

    lines = ["## Goal Context"]
    if proj.mission_title:
        lines.append(f"Mission: {proj.mission_title}")
    lines.append(f"Project: {proj.title}")
    if active_goals:
        lines.append("Active goals:")
        for g in active_goals:
            lines.append(
                f"  - {g.title} ({g.current_value}/{g.target_value} {g.metric_type}, due {g.due_date})"
            )
    else:
        lines.append("Active goals: none")
    lines.append("")
    return "\n".join(lines)


def inject_into_prompt(prompt: str, project_id: Optional[str] = None, goal_id: Optional[str] = None) -> str:
    """
    Prepend goal context to a prompt if applicable.
    Returns the original prompt unchanged if no context applies.
    """
    ctx = build_goal_context(project_id=project_id, goal_id=goal_id)
    if not ctx:
        return prompt
    return ctx + "\n---\n\n" + prompt
