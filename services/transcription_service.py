"""
Transcription service - Forwarder to services.transcription and services.exporters for backward compatibility.
"""
from services.transcription import *
from services.exporters import (
    export_meeting_to_txt,
    export_meeting_to_srt,
    export_meeting_to_docx,
    export_meeting_to_pdf,
    export_meeting_to_json,
)

# Compatibility aliases
get_meeting_transcriptions = get_transcript
