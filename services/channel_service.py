"""
Channel service - Audio channel mapping management.
"""
import logging
from database import query_all, query_one, execute

logger = logging.getLogger(__name__)


def get_all_channels() -> list[dict]:
    """Get all active audio channels."""
    return query_all(
        "SELECT * FROM audio_channels WHERE is_active = 1 ORDER BY name"
    )


def get_channel_by_id(channel_id: int) -> dict | None:
    """Get channel by ID."""
    return query_one(
        "SELECT * FROM audio_channels WHERE id = ?",
        (channel_id,)
    )


def create_channel(name: str, device_name: str, device_index: int, channel_index: int) -> int:
    """Create a new channel mapping."""
    return execute(
        """INSERT INTO audio_channels (name, device_name, device_index, channel_index, is_active)
           VALUES (?, ?, ?, ?, 1)""",
        (name, device_name, device_index, channel_index)
    )


def update_channel(channel_id: int,
                   name: str | None = None,
                   device_name: str | None = None,
                   device_index: int | None = None,
                   channel_index: int | None = None,
                   is_active: int | bool | None = None) -> bool:
    """Update channel mapping properties."""
    updates = []
    params = []

    if name is not None:
        updates.append("name = ?")
        params.append(name)

    if device_name is not None:
        updates.append("device_name = ?")
        params.append(device_name)

    if device_index is not None:
        updates.append("device_index = ?")
        params.append(device_index)

    if channel_index is not None:
        updates.append("channel_index = ?")
        params.append(channel_index)

    if is_active is not None:
        updates.append("is_active = ?")
        params.append(1 if is_active else 0)

    if not updates:
        return False

    params.append(channel_id)
    sql = f"UPDATE audio_channels SET {', '.join(updates)} WHERE id = ?"
    execute(sql, tuple(params))
    return True


def delete_channel(channel_id: int) -> bool:
    """Soft delete channel by marking is_active = 0."""
    execute("UPDATE audio_channels SET is_active = 0 WHERE id = ?", (channel_id,))
    return True


def get_device_channels(device_index: int, max_channels: int) -> list[int]:
    """Get available channel indices for a device."""
    return list(range(max_channels))
