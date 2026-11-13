from fastapi import APIRouter, Depends

from app.models.tasks import User
from app.schemas.users import UserResponse
from app.utils.security import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserResponse,
    responses={
        401: {"description": "Missing, invalid or expired token"},
        403: {"description": "Account is inactive"},
    },
    summary="Get the authenticated user's profile",
)
def get_my_profile(current_user: User = Depends(get_current_user)):
    """
    Return the profile of the user the Bearer token belongs to.

    - **Auth:** required (`Authorization: Bearer <token>`)
    - **200:** the user's `id`, `name`, `email`, `is_active` and `created_at` (never the password)
    - **401:** missing, invalid or expired token, or the user in the token no longer exists
    - **403:** the account is inactive
    """
    return current_user
