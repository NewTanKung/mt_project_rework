"""
Device service - Audio device detection and management
"""
import sounddevice as sd
from database.db_manager import execute_query, list_from_rows


def scan_audio_devices():
    """
    Scan for available audio input devices using sounddevice
    
    Returns:
        list: List of device dictionaries
    """
    devices = []
    device_list = sd.query_devices()
    
    for idx, device in enumerate(device_list):
        # Only include input devices
        if device['max_input_channels'] > 0:
            devices.append({
                'device_index': idx,
                'name': device['name'],
                'max_input_channels': device['max_input_channels'],
                'host_api': sd.query_hostapis(device['hostapi'])['name']
            })
    
    return devices


def save_devices_to_db(devices):
    """
    Save scanned devices to database
    Updates existing devices or inserts new ones
    
    Returns:
        int: Number of devices saved
    """
    count = 0
    
    for device in devices:
        # Check if device already exists
        existing = execute_query(
            "SELECT id FROM audio_devices WHERE name = ?",
            (device['name'],),
            fetch_one=True
        )
        
        if existing:
            # Update existing device
            execute_query(
                """UPDATE audio_devices 
                   SET device_index = ?, max_input_channels = ?, host_api = ?, status = 'ready'
                   WHERE name = ?""",
                (device['device_index'], device['max_input_channels'], 
                 device['host_api'], device['name']),
                commit=True
            )
        else:
            # Insert new device
            execute_query(
                """INSERT INTO audio_devices (name, device_index, max_input_channels, host_api, status)
                   VALUES (?, ?, ?, ?, 'ready')""",
                (device['name'], device['device_index'], 
                 device['max_input_channels'], device['host_api']),
                commit=True
            )
        
        count += 1
    
    return count


def get_all_devices():
    """
    Get all audio devices from database
    
    Returns:
        list: List of device dictionaries
    """
    query = "SELECT * FROM audio_devices ORDER BY device_index"
    devices = execute_query(query, fetch_all=True)
    return list_from_rows(devices)


def update_device_status(device_id, status):
    """
    Update device status
    
    Args:
        device_id: Device ID
        status: 'ready', 'disabled', 'not_connected'
    
    Returns:
        bool: True if successful
    """
    query = "UPDATE audio_devices SET status = ? WHERE id = ?"
    execute_query(query, (status, device_id), commit=True)
    return True


def delete_device(device_id):
    """
    Delete device from database
    
    Args:
        device_id: Device ID to delete
    """
    execute_query(
        "DELETE FROM audio_devices WHERE id = ?",
        (device_id,),
        commit=True
    )


def sync_device_indices():
    """
    Sync device indices by matching device names
    
    Process:
    1. Scan current devices
    2. Get devices from database
    3. Match by name (exact match)
    4. Update device_index if changed
    5. Mark missing devices
    
    Returns:
        dict: {
            success: bool,
            updates: list of updated devices,
            missing: list of missing devices,
            total_scanned: int
        }
    """
    # 1. Scan current devices
    current_devices = scan_audio_devices()
    current_device_map = {d['name']: d for d in current_devices}
    
    # 2. Get DB devices
    db_devices = get_all_devices()
    
    updates = []
    missing = []
    
    for db_device in db_devices:
        device_name = db_device['name']
        
        if device_name in current_device_map:
            # อุปกรณ์ยังมีอยู่
            current = current_device_map[device_name]
            
            if current['device_index'] != db_device['device_index']:
                # Index เปลี่ยน → อัปเดต
                old_index = db_device['device_index']
                new_index = current['device_index']
                
                updates.append({
                    'id': db_device['id'],
                    'old_index': old_index,
                    'new_index': new_index,
                    'name': device_name
                })
                
                # Update audio_devices table
                execute_query(
                    "UPDATE audio_devices SET device_index = ? WHERE id = ?",
                    (new_index, db_device['id']),
                    commit=True
                )
                
                # Update audio_channels table ที่ใช้อุปกรณ์นี้
                execute_query(
                    "UPDATE audio_channels SET device_index = ? WHERE device_name = ?",
                    (new_index, device_name),
                    commit=True
                )
        else:
            # อุปกรณ์หายไป
            missing.append({
                'id': db_device['id'],
                'name': device_name,
                'index': db_device['device_index']
            })
    
    return {
        'success': True,
        'updates': updates,
        'missing': missing,
        'total_scanned': len(current_devices)
    }


def check_devices_availability():
    """
    Check if all devices used in ACTIVE channels are available
    
    Returns:
        dict: {
            all_available: bool,
            available: int,
            missing: int,
            missing_devices: list
        }
    """
    # Get only devices that are actually used in active channels
    channels = execute_query(
        """SELECT DISTINCT device_name, device_index 
           FROM audio_channels 
           WHERE is_active = 1 
           AND id IN (SELECT DISTINCT channel_id FROM preset_member)""",
        fetch_all=True
    )
    
    if not channels:
        return {
            'all_available': True,
            'available': 0,
            'missing': 0,
            'missing_devices': []
        }
    
    # Scan current devices
    current_devices = scan_audio_devices()
    current_device_map = {d['name']: d for d in current_devices}
    
    available_count = 0
    missing_count = 0
    missing_devices = []
    
    for channel in channels:
        device_name = channel['device_name']
        
        if device_name in current_device_map:
            available_count += 1
        else:
            missing_count += 1
            missing_devices.append({
                'name': device_name,
                'index': channel['device_index']
            })
    
    return {
        'all_available': missing_count == 0,
        'available': available_count,
        'missing': missing_count,
        'missing_devices': missing_devices
    }


def verify_device_exists(device_index):
    """
    Verify if a device with the given index still exists in the system
    
    Returns:
        bool: True if device exists
    """
    try:
        devices = sd.query_devices()
        if device_index < len(devices):
            device = devices[device_index]
            return device['max_input_channels'] > 0
        return False
    except:
        return False


def check_meeting_devices(meeting_id):
    """
    Check if all devices for a meeting are available
    
    Returns:
        dict: {
            'all_available': bool,
            'missing_devices': list,
            'changed_devices': list
        }
    """
    # Get channels for this meeting (via participants)
    query = """
        SELECT DISTINCT ac.id, ac.name, ac.device_index, ac.channel_index, ac.device_name
        FROM audio_channels ac
        JOIN preset_member pm ON pm.channel_id = ac.id
        JOIN meetings m ON m.channel_preset_id = pm.preset_id
        WHERE m.meeting_id = ?
    """
    channels = execute_query(query, (meeting_id,), fetch_all=True)
    
    missing = []
    changed = []
    
    for channel in channels:
        channel_dict = dict(channel)
        
        # Check if device exists
        if not verify_device_exists(channel_dict['device_index']):
            missing.append(channel_dict)
        else:
            # Check if device index matches
            current_devices = sd.query_devices()
            device = current_devices[channel_dict['device_index']]
            if device['name'] != channel_dict['device_name']:
                changed.append({
                    **channel_dict,
                    'current_name': device['name']
                })
    
    return {
        'all_available': len(missing) == 0 and len(changed) == 0,
        'missing_devices': missing,
        'changed_devices': changed
    }


def clear_all_devices():
    """
    Clear all devices from database
    Called when application exits to ensure fresh device scan on next start
    Uses direct SQLite connection to avoid Flask app context issues
    
    Returns:
        int: Number of devices deleted
    """
    import sqlite3
    import os
    
    try:
        # Use direct SQLite connection (no Flask context needed)
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database.db')
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get count before deletion
        cursor.execute("SELECT COUNT(*) FROM audio_devices")
        count = cursor.fetchone()[0]
        
        # Delete all devices
        cursor.execute("DELETE FROM audio_devices")
        conn.commit()
        conn.close()
        
        print(f"[Device Service] Cleared {count} device(s) from database")
        return count
        
    except Exception as e:
        print(f"[Device Service] Error clearing devices: {e}")
        return 0
