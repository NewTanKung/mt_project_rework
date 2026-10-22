"""
Device service - Audio device detection, synchronization, and management.
"""
import sounddevice as sd
import logging
from database import query_all, query_one, execute, transaction

logger = logging.getLogger(__name__)


def scan_audio_devices() -> list[dict]:
    """
    Scan for available audio input devices using sounddevice.
    """
    devices = []
    try:
        device_list = sd.query_devices()
        for idx, device in enumerate(device_list):
            if device['max_input_channels'] > 0:
                hostapi_info = sd.query_hostapis(device['hostapi'])
                devices.append({
                    'device_index': idx,
                    'name': device['name'],
                    'max_input_channels': device['max_input_channels'],
                    'host_api': hostapi_info['name']
                })
    except Exception as e:
        logger.error("Error scanning audio devices: %s", e)
        raise

    return devices


def save_devices_to_db(devices: list[dict]) -> int:
    """
    Save scanned devices to database.
    Updates existing devices or inserts new ones.
    """
    count = 0
    with transaction():
        for device in devices:
            existing = query_one(
                "SELECT id FROM audio_devices WHERE name = ?",
                (device['name'],)
            )
            if existing:
                execute(
                    """UPDATE audio_devices 
                       SET device_index = ?, max_input_channels = ?, host_api = ?, status = 'ready'
                       WHERE name = ?""",
                    (device['device_index'], device['max_input_channels'], 
                     device['host_api'], device['name'])
                )
            else:
                execute(
                    """INSERT INTO audio_devices (name, device_index, max_input_channels, host_api, status)
                       VALUES (?, ?, ?, ?, 'ready')""",
                    (device['name'], device['device_index'], 
                     device['max_input_channels'], device['host_api'])
                )
            count += 1

    return count


def get_all_devices() -> list[dict]:
    """Get all audio devices from database."""
    return query_all("SELECT * FROM audio_devices ORDER BY device_index")


def update_device_status(device_id: int, status: str) -> bool:
    """Update device status ('ready', 'disabled', 'not_connected')."""
    execute("UPDATE audio_devices SET status = ? WHERE id = ?", (status, device_id))
    return True


def delete_device(device_id: int):
    """Delete device from database."""
    execute("DELETE FROM audio_devices WHERE id = ?", (device_id,))


def sync_device_indices() -> dict:
    """
    Sync device indices by matching device names against system audio devices.
    """
    current_devices = scan_audio_devices()
    current_device_map = {d['name']: d for d in current_devices}
    db_devices = get_all_devices()
    
    updates = []
    missing = []
    
    with transaction():
        for db_device in db_devices:
            device_name = db_device['name']
            if device_name in current_device_map:
                current = current_device_map[device_name]
                if current['device_index'] != db_device['device_index']:
                    old_index = db_device['device_index']
                    new_index = current['device_index']
                    updates.append({
                        'id': db_device['id'],
                        'old_index': old_index,
                        'new_index': new_index,
                        'name': device_name
                    })
                    execute(
                        "UPDATE audio_devices SET device_index = ? WHERE id = ?",
                        (new_index, db_device['id'])
                    )
                    execute(
                        "UPDATE audio_channels SET device_index = ? WHERE device_name = ?",
                        (new_index, device_name)
                    )
            else:
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


def check_devices_availability() -> dict:
    """
    Check if all devices used in active channels are available in the system.
    """
    channels = query_all(
        """SELECT DISTINCT device_name, device_index 
           FROM audio_channels 
           WHERE is_active = 1 
           AND id IN (SELECT DISTINCT channel_id FROM preset_member)"""
    )
    
    if not channels:
        return {
            'all_available': True,
            'available': 0,
            'missing': 0,
            'missing_devices': []
        }
        
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


def verify_device_exists(device_index: int) -> bool:
    """Verify if a device with the given index exists and has inputs."""
    try:
        devices = sd.query_devices()
        if device_index < len(devices):
            return devices[device_index]['max_input_channels'] > 0
        return False
    except Exception:
        return False


def check_meeting_devices(meeting_id: int) -> dict:
    """Check if all devices for a meeting's preset are available."""
    channels = query_all(
        """SELECT DISTINCT ac.id, ac.name, ac.device_index, ac.channel_index, ac.device_name
           FROM audio_channels ac
           JOIN preset_member pm ON pm.channel_id = ac.id
           JOIN meetings m ON m.channel_preset_id = pm.preset_id
           WHERE m.meeting_id = ?""",
        (meeting_id,)
    )
    
    missing = []
    changed = []
    try:
        current_devices = sd.query_devices()
    except Exception:
        current_devices = []

    for channel in channels:
        dev_idx = channel['device_index']
        if dev_idx >= len(current_devices) or current_devices[dev_idx]['max_input_channels'] == 0:
            missing.append(channel)
        elif current_devices[dev_idx]['name'] != channel['device_name']:
            changed.append({
                **channel,
                'current_name': current_devices[dev_idx]['name']
            })
            
    return {
        'all_available': len(missing) == 0 and len(changed) == 0,
        'missing_devices': missing,
        'changed_devices': changed
    }


def clear_all_devices() -> int:
    """
    Clear all devices from database on shutdown.
    """
    try:
        count_row = query_one("SELECT COUNT(*) as count FROM audio_devices")
        count = count_row['count'] if count_row else 0
        execute("DELETE FROM audio_devices")
        logger.info("Cleared %d device(s) from database", count)
        return count
    except Exception as e:
        logger.error("Error clearing devices: %s", e)
        return 0
