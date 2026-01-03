"""
Group Routes
"""
from fastapi import APIRouter, HTTPException, Depends, Request

from app.models.group import (
    GroupCreate, GroupUpdate, GroupResponse, GroupListResponse
)
from app.routes.auth import get_current_user_id_optional

router = APIRouter()


async def get_db(request: Request):
    """Get database service from app state"""
    if not hasattr(request.app.state, 'db') or not request.app.state.db:
        raise HTTPException(status_code=500, detail="Database not available")
    return request.app.state.db


@router.post("", response_model=GroupResponse)
async def create_group(
    group_data: GroupCreate,
    user_id: str = Depends(get_current_user_id_optional),
    db = Depends(get_db)
):
    """
    Create a new video group.
    """
    try:
        group = await db.create_group(
            user_id=user_id,
            name=group_data.name,
            description=group_data.description,
            color=group_data.color or "#3B82F6"
        )

        return GroupResponse(**group)

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=GroupListResponse)
async def list_groups(
    user_id: str = Depends(get_current_user_id_optional),
    db = Depends(get_db)
):
    """
    List all groups for the current user.

    Includes video count for each group.
    """
    try:
        groups = await db.list_groups(user_id)

        return GroupListResponse(
            groups=[GroupResponse(**g) for g in groups],
            total=len(groups)
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: str,
    user_id: str = Depends(get_current_user_id_optional),
    db = Depends(get_db)
):
    """
    Get a specific group by ID.
    """
    try:
        group = await db.get_group(group_id, user_id)

        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

        return GroupResponse(**group)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: str,
    group_data: GroupUpdate,
    user_id: str = Depends(get_current_user_id_optional),
    db = Depends(get_db)
):
    """
    Update a group's details.
    """
    try:
        # Verify group exists and user owns it
        existing = await db.get_group(group_id, user_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Group not found")

        # Prepare updates
        updates = {}
        if group_data.name is not None:
            updates["name"] = group_data.name
        if group_data.description is not None:
            updates["description"] = group_data.description
        if group_data.color is not None:
            updates["color"] = group_data.color

        if updates:
            await db.update_group(group_id, user_id, updates)

        # Return updated group
        group = await db.get_group(group_id, user_id)
        return GroupResponse(**group)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{group_id}")
async def delete_group(
    group_id: str,
    user_id: str = Depends(get_current_user_id_optional),
    db = Depends(get_db)
):
    """
    Delete a group.

    Videos in the group are not deleted, they become ungrouped.
    """
    try:
        # Verify group exists and user owns it
        existing = await db.get_group(group_id, user_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Group not found")

        await db.delete_group(group_id, user_id)

        return {"message": "Group deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
