"""
Channel service - Channel mapping CRUD
"""
from database.db_manager import execute_query, list_from_rows, dict_from_row


def get_all_channels():
    """
    Get all audio channels
    
    Returns:
        list: List of channel dictionaries
    """
    query = """
        SELECT * FROM audio_channels 
        WHERE is_active = 1
        ORDER BY name
    """
    channels = execute_query(query, fetch_all=True)
    return list_from_rows(channels)


def get_channel_by_id(channel_id):
    """
    Get channel by ID
    
    Returns:
        dict: Channel dictionary
    """
    query = "SELECT * FROM audio_channels WHERE id = ?"
    channel = execute_query(query, (channel_id,), fetch_one=True)
    return dict_from_row(channel)


def create_channel(name, device_name, device_index, channel_index):
    """
    Create new channel mapping
    
    Returns:
        int: New channel ID
    """
    query = """
        INSERT INTO audio_channels (name, device_name, device_index, channel_index, is_active)
        VALUES (?, ?, ?, ?, 1)
    """
    return execute_query(query, (name, device_name, device_index, channel_index), commit=True)


def update_channel(channel_id, name=None, device_name=None, device_index=None, 
                   channel_index=None, is_active=None):
    """
    Update channel mapping
    
    Returns:
        bool: True if successful
    """
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
        params.append(is_active)
    
    if not updates:
        return False
    
    params.append(channel_id)
    query = f"UPDATE audio_channels SET {', '.join(updates)} WHERE id = ?"
    execute_query(query, tuple(params), commit=True)
    return True


def delete_channel(channel_id):
    """
    Delete channel (soft delete by setting is_active = 0)
    
    Returns:
        bool: True if successful
    """
    query = "UPDATE audio_channels SET is_active = 0 WHERE id = ?"
    execute_query(query, (channel_id,), commit=True)
    return True


def get_device_channels(device_index, max_channels):
    """
    Get available channel indices for a device
    
    Returns:
        list: List of available channel indices
    """
    return list(range(max_channels))
