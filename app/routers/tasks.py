from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tasks import Priority, Task, User
from app.schemas.tasks import (
    AISuggestResponse,
    SuggestRequest,
    TaskCreate,
    TaskPatch,
    TaskResponse,
)
from app.utils.dependencies import get_owned_task
from app.utils.exceptions import AppException
from app.utils.notifications import send_notification
from app.utils.rate_limit import limiter
from app.utils.security import get_current_user

router = APIRouter(prefix="/tasks", tags=["Tasks"])

# Responses shared by every endpoint that works on one specific task.
OWNED_TASK_RESPONSES = {
    401: {"description": "Missing or invalid Bearer token"},
    403: {"description": "The task belongs to another user"},
    404: {"description": "No task with this id"},
    422: {"description": "task_id is not a positive integer, or the body is invalid"},
    429: {"description": "Rate limit exceeded"},
}


# "" matches /tasks exactly as the spec says; "/" keeps /tasks/ working with no redirect.
@router.get(
    "",
    response_model=list[TaskResponse],
    responses={
        401: {"description": "Missing or invalid Bearer token"},
        422: {"description": "Invalid filter or pagination value"},
        429: {"description": "Rate limit exceeded"},
    },
    summary="List the current user's tasks",
)
@router.get("/", response_model=list[TaskResponse], include_in_schema=False)
@limiter.limit("60/minute")
def list_tasks(
    request: Request,
    completed: Optional[bool] = Query(None, description="Only tasks with this completed value"),
    priority: Optional[Priority] = Query(None, description="Only tasks with this priority"),
    skip: int = Query(default=0, ge=0, description="Number of tasks to skip"),
    limit: int = Query(default=10, ge=1, le=50, description="Maximum number of tasks to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List the authenticated user's tasks (never anyone else's), oldest first.

    - **Auth:** required
    - **Rate limit:** 60 requests/minute
    - **Query:** `completed` (true/false), `priority` (low, medium, high), `skip` (>= 0), `limit` (1-50, default 10)
    - **200:** JSON array of tasks (empty array `[]` if none match)
    - **401:** missing/invalid token
    - **422:** a query value is invalid or out of range
    """
    query = db.query(Task).filter(Task.user_id == current_user.id)
    if completed is not None:
        query = query.filter(Task.completed == completed)
    if priority is not None:
        query = query.filter(Task.priority == priority)

    # order_by makes pagination stable: the same skip/limit always returns the same page.
    return query.order_by(Task.id).offset(skip).limit(limit).all()


@router.post(
    "",
    response_model=TaskResponse,
    status_code=201,
    responses={
        401: {"description": "Missing or invalid Bearer token"},
        422: {"description": "Request body failed validation"},
        429: {"description": "Rate limit exceeded"},
    },
    summary="Create a new task",
)
@router.post("/", response_model=TaskResponse, status_code=201, include_in_schema=False)
@limiter.limit("20/minute")
def create_task(
    request: Request,
    task: TaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a task owned by the authenticated user.

    - **Auth:** required
    - **Rate limit:** 20 requests/minute
    - **Body:** `title` (1-200), optional `description` (1-2000), optional `priority` (low, medium, high), optional `completed` (default `false`)
    - **Side effect:** a background notification is logged for the current user
    - **201:** the created task, including `id`, `user_id` and `created_at`
    - **401:** missing/invalid token
    - **422:** body fails validation (missing `title`, invalid priority, unknown field, etc.)
    """
    db_task = Task(**task.model_dump(), user_id=current_user.id)
    db.add(db_task)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppException("Task could not be created due to a database constraint", 400)
    db.refresh(db_task)

    background_tasks.add_task(
        send_notification,
        current_user.email,
        f"Task created: {db_task.title!r} (id={db_task.id})",
    )
    return db_task


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    responses=OWNED_TASK_RESPONSES,
    summary="Get a specific task",
)
@limiter.limit("60/minute")
def get_task(request: Request, task: Task = Depends(get_owned_task)):
    """
    Get one of your tasks by id.

    - **Auth:** required
    - **Rate limit:** 60 requests/minute
    - **Path:** `task_id` (positive integer)
    - **200:** that task's record
    - **401:** missing/invalid token
    - **403:** the task belongs to another user
    - **404:** no task with that id
    - **422:** `task_id` is not a positive integer
    """
    return task


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    responses=OWNED_TASK_RESPONSES,
    summary="Partially update a task",
)
@limiter.limit("20/minute")
def update_task(
    request: Request,
    task_data: TaskPatch,
    background_tasks: BackgroundTasks,
    task: Task = Depends(get_owned_task),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Partially update one of your tasks; fields you leave out keep their value.

    - **Auth:** required
    - **Rate limit:** 20 requests/minute
    - **Body:** any non-empty subset of `title`, `description`, `priority`, `completed` (`title` and `completed` cannot be null)
    - **Side effect:** a background notification is logged for the current user
    - **200:** the task after the patch
    - **401:** missing/invalid token
    - **403:** the task belongs to another user
    - **404:** no task with that id
    - **422:** a field is invalid (empty title, invalid priority, null title, empty body, etc.)
    """
    for field, value in task_data.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppException("Task could not be updated due to a database constraint", 400)
    db.refresh(task)

    background_tasks.add_task(
        send_notification,
        current_user.email,
        f"Task updated: {task.title!r} (id={task.id})",
    )
    return task


@router.delete(
    "/{task_id}",
    status_code=204,
    responses={**OWNED_TASK_RESPONSES, 204: {"description": "Deleted (empty body)"}},
    summary="Delete a specific task",
)
@limiter.limit("20/minute")
def delete_task(
    request: Request,
    background_tasks: BackgroundTasks,
    task: Task = Depends(get_owned_task),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete one of your tasks.

    - **Auth:** required
    - **Rate limit:** 20 requests/minute
    - **Side effect:** a background notification is logged for the current user
    - **204:** deleted (empty body - do not parse JSON)
    - **401:** missing/invalid token
    - **403:** the task belongs to another user
    - **404:** no task with that id
    """
    task_id, title = task.id, task.title
    db.delete(task)
    db.commit()

    background_tasks.add_task(
        send_notification,
        current_user.email,
        f"Task deleted: {title!r} (id={task_id})",
    )
    return Response(status_code=204)


@router.post(
    "/{task_id}/suggest",
    response_model=AISuggestResponse,
    responses=OWNED_TASK_RESPONSES,
    summary="Get an AI suggestion for a task",
)
@limiter.limit("20/minute")
def suggest_ai(
    request: Request,
    body: Optional[SuggestRequest] = None,
    task: Task = Depends(get_owned_task),
):
    """
    Return a placeholder "AI" suggestion 

    - **Auth:** required
    - **Rate limit:** 20 requests/minute
    - **Body (optional):** `description` - text to base the suggestion on; defaults to the task's stored description
    - **200:** `task_id`, a placeholder `suggestion`, and `is_placeholder: true`
    - **401:** missing/invalid token
    - **403:** the task belongs to another user
    - **404:** no task with that id
    """
    description = (body.description if body and body.description else task.description) or task.title
    suggestion = (
        f"[Placeholder AI response] For '{task.title}': break '{description}' into smaller "
        "steps, set a deadline, and start with the most important one."
    )
    return AISuggestResponse(task_id=task.id, suggestion=suggestion)
