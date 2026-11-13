from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.tasks import Priority


class TaskCreate(BaseModel):
    """What a client sends us to create a new task."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(
        min_length=1, max_length=200,
        description="The title of the task (1-200 characters)",
        examples=["Clean"]
    )
    description: Optional[str] = Field(
        default=None,
        min_length=1, max_length=2000,
        description="The description of the task (up to 2000 characters)",
        examples=["Clean my room monday"]
    )
    priority: Optional[Priority] = Field(
        default=None,
        description="Priority of the task: low, medium or high",
        examples=["low"]
    )
    completed: bool = Field(
        default=False,
        description="Whether the task is completed",
        examples=[False]
    )


class TaskPatch(BaseModel):
    """What a client sends us to partially update a task (send only what changes)."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Optional[str] = Field(
        default=None,
        min_length=1, max_length=200,
        description="The title of the task",
        examples=["Clean"]
    )
    description: Optional[str] = Field(
        default=None,
        min_length=1, max_length=2000,
        description="The description of the task",
        examples=["Clean my room monday"]
    )
    priority: Optional[Priority] = Field(
        default=None,
        description="Priority of the task: low, medium or high",
        examples=["low"]
    )
    completed: Optional[bool] = Field(
        default=None,
        description="Whether the task is completed",
        examples=[False]
    )

    @field_validator("title", "completed")
    @classmethod
    def required_columns_cannot_be_null(cls, value, info):
        # Only runs for fields the client actually sent. title/completed are
        # NOT NULL in the database, so an explicit null must be a 422, not a 500.
        if value is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return value

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("provide at least one field to update")
        return self


class TaskResponse(BaseModel):
    """What we send back for a task."""
    id: int
    title: str
    description: Optional[str] = None
    priority: Optional[Priority] = None
    completed: bool
    user_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 2,
                "title": "Clean",
                "description": "Clean my room monday",
                "priority": "low",
                "completed": False,
                "user_id": 1,
                "created_at": "2026-08-28T00:30:00",
                "updated_at": "2026-09-08T00:30:00",
            }
        },
    )


class SuggestRequest(BaseModel):
    """Optional body for the suggest endpoint."""
    model_config = ConfigDict(extra="forbid")

    description: Optional[str] = Field(
        default=None,
        min_length=1, max_length=2000,
        description="Text to base the suggestion on. If omitted, the task's stored description is used.",
        examples=["Clean my room monday"]
    )


class AISuggestResponse(BaseModel):
    """Placeholder AI suggestion for a task."""
    task_id: int
    suggestion: str
    is_placeholder: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": 2,
                "suggestion": "[Placeholder AI response] For 'Clean': break 'Clean my room monday' into smaller steps and start with the most important one.",
                "is_placeholder": True,
            }
        }
    )
