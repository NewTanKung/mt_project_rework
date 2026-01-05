"""
PDF Export Service
Export meeting transcriptions to PDF with Thai font support (THSarabunPSK)
"""
import os
import json
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from database.db_manager import execute_query
from services.storage_service import get_storage_settings


# Global flag to check if fonts are registered
_fonts_registered = False
_thai_font_available = False


def _register_thai_fonts():
    """Register Thai fonts for PDF generation - THSarabunPSK"""
    global _fonts_registered, _thai_font_available
    
    if _fonts_registered:
        return
    
    try:
        # Use THSarabunPSK from project font folder
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        font_dir = os.path.join(base_path, 'font', 'THSarabunPSK')
        
        font_paths = {
            'normal': os.path.join(font_dir, 'THSarabun.ttf'),
            'bold': os.path.join(font_dir, 'THSarabun Bold.ttf'),
            'italic': os.path.join(font_dir, 'THSarabun Italic.ttf'),
            'bolditalic': os.path.join(font_dir, 'THSarabun BoldItalic.ttf')
        }
        
        font_found = False
        bold_found = False
        
        # Register normal font
        if os.path.exists(font_paths['normal']):
            pdfmetrics.registerFont(TTFont('ThaiFont', font_paths['normal']))
            font_found = True
            print(f"[PDF] ✅ Registered Thai font: THSarabunPSK")
        else:
            print(f"[PDF] ⚠️ Font not found: {font_paths['normal']}")
        
        # Register bold font
        if os.path.exists(font_paths['bold']):
            pdfmetrics.registerFont(TTFont('ThaiFontBold', font_paths['bold']))
            bold_found = True
            print(f"[PDF] ✅ Registered Thai bold font: THSarabunPSK Bold")
        else:
            print(f"[PDF] ⚠️ Bold font not found: {font_paths['bold']}")
        
        if not font_found:
            print("[PDF] ⚠️ No Thai font found, Thai text may not display correctly")
        
        _thai_font_available = font_found and bold_found
        _fonts_registered = True
        
    except Exception as e:
        print(f"[PDF] ❌ Error registering fonts: {e}")
        import traceback
        traceback.print_exc()
        _fonts_registered = True
        _thai_font_available = False


def _create_styles():
    """Create custom paragraph styles with THSarabunPSK"""
    styles = getSampleStyleSheet()
    
    # Determine which fonts to use
    if _thai_font_available:
        font_normal = 'ThaiFont'
        font_bold = 'ThaiFontBold'
    else:
        font_normal = 'Helvetica'
        font_bold = 'Helvetica-Bold'
    
    # Title style
    styles.add(ParagraphStyle(
        name='CustomTitle',
        parent=styles['Title'],
        fontName=font_bold,
        fontSize=20,
        textColor=colors.HexColor('#1e3a8a'),
        spaceAfter=12,
        alignment=TA_CENTER
    ))
    
    # Heading style
    styles.add(ParagraphStyle(
        name='CustomHeading',
        parent=styles['Heading1'],
        fontName=font_bold,
        fontSize=16,
        textColor=colors.HexColor('#1e3a8a'),
        spaceBefore=10,
        spaceAfter=6
    ))
    
    # Normal text style
    styles.add(ParagraphStyle(
        name='CustomNormal',
        parent=styles['Normal'],
        fontName=font_normal,
        fontSize=14,
        leading=20,
        textColor=colors.black
    ))
    
    # Speaker name style
    styles.add(ParagraphStyle(
        name='CustomSpeaker',
        parent=styles['Normal'],
        fontName=font_bold,
        fontSize=14,
        textColor=colors.HexColor('#2563eb'),
        spaceBefore=8
    ))
    
    # Time style
    styles.add(ParagraphStyle(
        name='CustomTime',
        parent=styles['Normal'],
        fontName=font_normal,
        fontSize=12,
        textColor=colors.HexColor('#6b7280'),
        spaceAfter=4
    ))
    
    # Info style
    styles.add(ParagraphStyle(
        name='CustomInfo',
        parent=styles['Normal'],
        fontName=font_normal,
        fontSize=13,
        textColor=colors.HexColor('#4b5563'),
        spaceAfter=6
    ))
    
    return styles


def _format_thai_date(iso_date_str):
    """Format ISO date to Thai readable format"""
    try:
        dt = datetime.fromisoformat(iso_date_str.replace('Z', '+00:00'))
        thai_months = [
            'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
            'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม'
        ]
        thai_year = dt.year + 543
        return f"{dt.day} {thai_months[dt.month-1]} {thai_year} เวลา {dt.strftime('%H:%M:%S')}"
    except:
        return iso_date_str


def export_meeting_to_pdf(meeting_id):
    """
    Export meeting transcription to PDF
    
    Args:
        meeting_id: Meeting ID to export
        
    Returns:
        dict: {'success': bool, 'filepath': str, 'message': str}
    """
    try:
        # Register fonts
        _register_thai_fonts()
        
        # Get storage settings
        storage_settings = get_storage_settings()
        export_root = storage_settings.get('export_path', 'storage/exports')
        transcription_root = storage_settings.get('transcription_path', 'storage/transcriptions')
        
        # Create export directory
        os.makedirs(export_root, exist_ok=True)
        
        # Get meeting info
        meeting = execute_query(
            """SELECT meeting_id, meeting_name, meeting_date, status 
               FROM meetings WHERE meeting_id = ?""",
            (meeting_id,),
            fetch_one=True
        )
        
        if not meeting:
            return {'success': False, 'message': 'Meeting not found'}
        
        meeting_dict = dict(meeting)
        
        # Load JSON transcription
        json_path = os.path.join(transcription_root, f'meeting_{meeting_id}', f'meeting_{meeting_id}_transcription.json')
        
        if not os.path.exists(json_path):
            return {'success': False, 'message': 'Transcription not found'}
        
        with open(json_path, 'r', encoding='utf-8') as f:
            transcription_data = json.load(f)
        
        # Create PDF filename
        pdf_filename = f"meeting_{meeting_id}_{meeting_dict['meeting_name']}_transcription.pdf"
        pdf_filepath = os.path.join(export_root, pdf_filename)
        
        # Create PDF document
        doc = SimpleDocTemplate(
            pdf_filepath,
            pagesize=A4,
            rightMargin=20*mm,
            leftMargin=20*mm,
            topMargin=20*mm,
            bottomMargin=20*mm
        )
        
        # Build content
        story = []
        styles = _create_styles()
        
        # Determine font for table
        table_font = 'ThaiFont' if _thai_font_available else 'Helvetica'
        table_font_bold = 'ThaiFontBold' if _thai_font_available else 'Helvetica-Bold'
        
        # Title
        title = Paragraph(f"การประชุม: {meeting_dict['meeting_name']}", styles['CustomTitle'])
        story.append(title)
        story.append(Spacer(1, 6*mm))
        
        # Meeting info table
        info_data = [
            ['วันที่ประชุม:', meeting_dict['meeting_date'] or 'ไม่ระบุ'],
            ['วันที่ถอดเสียง:', _format_thai_date(transcription_data.get('transcription_date', ''))],
            ['โมเดลที่ใช้:', transcription_data.get('model_used', 'N/A')],
            ['ภาษา:', 'ภาษาไทย' if transcription_data.get('language') == 'th' else transcription_data.get('language', 'N/A')],
            ['จำนวนไฟล์:', str(len(transcription_data.get('transcriptions', [])))]
        ]
        
        info_table = Table(info_data, colWidths=[40*mm, 130*mm])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), table_font_bold),
            ('FONTNAME', (1, 0), (1, -1), table_font),
            ('FONTSIZE', (0, 0), (-1, -1), 13),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#4b5563')),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.HexColor('#1f2937')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        
        story.append(info_table)
        story.append(Spacer(1, 8*mm))
        
        # Separator line
        line_table = Table([['']], colWidths=[170*mm])
        line_table.setStyle(TableStyle([
            ('LINEABOVE', (0, 0), (-1, 0), 2, colors.HexColor('#3b82f6')),
        ]))
        story.append(line_table)
        story.append(Spacer(1, 6*mm))
        
        # Transcriptions
        transcriptions = transcription_data.get('transcriptions', [])
        
        for i, trans in enumerate(transcriptions):
            # Speaker name
            speaker = Paragraph(
                f"<b>ผู้พูด:</b> {trans.get('speaker_name', 'ไม่ระบุ')}",
                styles['CustomSpeaker']
            )
            story.append(speaker)
            
            # Time range
            time_text = f"เวลา: {trans.get('start_time', '00:00:00')} - {trans.get('end_time', '00:00:00')}"
            time_para = Paragraph(time_text, styles['CustomTime'])
            story.append(time_para)
            
            # Transcription text
            text = trans.get('text', '').strip()
            if text:
                text_para = Paragraph(text, styles['CustomNormal'])
                story.append(text_para)
            
            # Add spacer between entries
            story.append(Spacer(1, 4*mm))
            
            # Add page break every 10 entries to avoid overflow
            if (i + 1) % 10 == 0 and i < len(transcriptions) - 1:
                story.append(PageBreak())
        
        # Build PDF
        doc.build(story)
        
        print(f"[PDF] ✅ Created PDF: {pdf_filename}")
        
        return {
            'success': True,
            'filepath': pdf_filepath,
            'filename': pdf_filename,
            'message': 'PDF created successfully'
        }
        
    except Exception as e:
        print(f"[PDF] ❌ Error creating PDF: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'message': f'Error creating PDF: {str(e)}'
        }


def export_transcription_to_pdf(voice_id):
    """
    Export single transcription to PDF
    
    Args:
        voice_id: Voice file ID to export
        
    Returns:
        dict: {'success': bool, 'filepath': str, 'message': str}
    """
    try:
        # Register fonts
        _register_thai_fonts()
        
        # Get voice file info
        voice_file = execute_query(
            """SELECT vf.voice_id, vf.meeting_id, vf.person_id, vf.name, vf.start_time, vf.end_time,
                      tf.content, p.participant_name
               FROM voice_file vf
               LEFT JOIN text_file tf ON vf.voice_id = tf.voice_id
               LEFT JOIN persons p ON vf.person_id = p.person_id
               WHERE vf.voice_id = ?""",
            (voice_id,),
            fetch_one=True
        )
        
        if not voice_file:
            return {'success': False, 'message': 'Voice file not found'}
        
        voice_dict = dict(voice_file)
        
        if not voice_dict.get('content'):
            return {'success': False, 'message': 'Transcription not found'}
        
        # Get storage settings
        storage_settings = get_storage_settings()
        export_root = storage_settings.get('export_path', 'storage/exports')
        os.makedirs(export_root, exist_ok=True)
        
        # Create PDF filename
        pdf_filename = f"transcription_{voice_id}_{voice_dict['participant_name']}.pdf"
        pdf_filepath = os.path.join(export_root, pdf_filename)
        
        # Create PDF
        doc = SimpleDocTemplate(pdf_filepath, pagesize=A4)
        story = []
        styles = _create_styles()
        
        # Title
        title = Paragraph(f"ไฟล์ถอดเสียง: {voice_dict['name']}", styles['CustomTitle'])
        story.append(title)
        story.append(Spacer(1, 6*mm))
        
        # Info
        info = [
            f"<b>ผู้พูด:</b> {voice_dict['participant_name'] or 'ไม่ระบุ'}",
            f"<b>เวลา:</b> {voice_dict['start_time']} - {voice_dict['end_time']}"
        ]
        
        for info_line in info:
            story.append(Paragraph(info_line, styles['CustomInfo']))
        
        story.append(Spacer(1, 4*mm))
        
        # Transcription text
        text_para = Paragraph(voice_dict['content'], styles['CustomNormal'])
        story.append(text_para)
        
        # Build PDF
        doc.build(story)
        
        print(f"[PDF] ✅ Created PDF: {pdf_filename}")
        
        return {
            'success': True,
            'filepath': pdf_filepath,
            'filename': pdf_filename,
            'message': 'PDF created successfully'
        }
        
    except Exception as e:
        print(f"[PDF] ❌ Error creating PDF: {e}")
        return {
            'success': False,
            'message': f'Error creating PDF: {str(e)}'
        }
