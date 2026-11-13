"""Reusable dependencies shared by several routers."""
from fastapi import Depends, Path
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tasks import Task, User
from app.utils.exceptions import ForbiddenException, NotFoundException
from app.utils.security import get_current_user


def get_owned_task(
    task_id: int = Path(..., ge=1, description="ID of the task"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Task:
    """Load a task and make sure it belongs to the authenticated user.

    This is the single place where task ownership is enforced, so every endpoint that takes a task_id gets the same 404 / 403 behaviour.
    """
    task = db.get(Task, task_id)
    if task is None:
        raise NotFoundException("Task", task_id)
    if task.user_id != current_user.id:
        raise ForbiddenException("You do not have permission to access this task")
    return task
