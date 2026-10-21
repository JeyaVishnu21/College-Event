"""
PDF Report Generator Service
----------------------------
Generates institutional, publication-quality PDF crowd monitoring reports
using ReportLab and Matplotlib for the Crowd Event Management System.
"""

import io
from datetime import datetime
from typing import Dict, Any, List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
    KeepTogether,
    HRFlowable
)
from reportlab.lib.units import inch


# Color Palette
PRIMARY_COLOR = colors.HexColor('#0f172a')     # Slate 900
SECONDARY_COLOR = colors.HexColor('#0284c7')   # Sky 600
TEXT_MAIN = colors.HexColor('#1e293b')         # Slate 800
TEXT_MUTED = colors.HexColor('#64748b')        # Slate 500
BORDER_COLOR = colors.HexColor('#cbd5e1')      # Slate 300
BG_LIGHT = colors.HexColor('#f8fafc')          # Slate 50
BG_HEADER = colors.HexColor('#f1f5f9')         # Slate 100

CRITICAL_COLOR = colors.HexColor('#dc2626')    # Red 600
WARNING_COLOR = colors.HexColor('#d97706')     # Amber 600
SAFE_COLOR = colors.HexColor('#16a34a')        # Green 600


def _generate_history_chart(history: List[Dict[str, Any]], venue_capacity: Optional[int]) -> Optional[io.BytesIO]:
    """
    Renders a clean, high-resolution line chart of estimated crowd count over time
    using Matplotlib and returns the PNG in an in-memory BytesIO buffer.
    """
    if not history or len(history) < 2:
        return None

    timestamps = []
    counts = []

    for item in history:
        ts = item.get('analysis_timestamp')
        if isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except Exception:
                try:
                    dt = datetime.strptime(ts[:19], '%Y-%m-%d %H:%M:%S')
                except Exception:
                    continue
        elif isinstance(ts, datetime):
            dt = ts
        else:
            continue

        cnt = item.get('predicted_count', 0)
        timestamps.append(dt)
        counts.append(cnt)

    if len(timestamps) < 2:
        return None

    # Sort chronological
    paired = sorted(zip(timestamps, counts), key=lambda x: x[0])
    timestamps, counts = zip(*paired)

    fig, ax = plt.subplots(figsize=(6.8, 2.5), dpi=200)
    fig.patch.set_facecolor('#ffffff')
    ax.set_facecolor('#f8fafc')

    # Plot crowd trend line
    ax.plot(
        timestamps,
        counts,
        color='#0284c7',
        linewidth=2.2,
        marker='o',
        markersize=6,
        markerfacecolor='#0369a1',
        markeredgecolor='#ffffff',
        markeredgewidth=1.5,
        label='Estimated Crowd Headcount',
        zorder=3
    )

    # Fill under line
    ax.fill_between(timestamps, counts, color='#38bdf8', alpha=0.18, zorder=2)

    # Plot capacity threshold line if available
    if venue_capacity and venue_capacity > 0:
        ax.axhline(
            y=venue_capacity,
            color='#ef4444',
            linestyle='--',
            linewidth=1.5,
            label=f'Venue Capacity ({venue_capacity:,})',
            zorder=4
        )

    # Formatting
    ax.set_title(
        'Crowd Density Over Time (Surveillance Observations)',
        fontsize=10,
        fontweight='bold',
        color='#0f172a',
        pad=8
    )
    ax.set_ylabel('Headcount', fontsize=8, color='#475569', labelpad=4)
    ax.grid(True, linestyle=':', alpha=0.6, color='#cbd5e1', zorder=1)

    # Time axis formatting
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M\n%b %d'))
    ax.tick_params(axis='both', which='major', labelsize=7.5, colors='#475569')

    # Spines styling
    for spine in ax.spines.values():
        spine.set_color('#cbd5e1')
        spine.set_linewidth(0.8)

    ax.legend(loc='upper left', fontsize=7.5, framealpha=0.9, facecolor='#ffffff', edgecolor='#cbd5e1')

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=200)
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_pdf_report(report_data: Dict[str, Any]) -> io.BytesIO:
    """
    Builds a complete PDF report from structured event report data.
    Returns an in-memory BytesIO buffer containing the PDF bytes.
    """
    event = report_data.get('event', {})
    summary = report_data.get('summary', {})
    history = report_data.get('history', [])
    alerts = report_data.get('alerts', [])

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom Typography Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=PRIMARY_COLOR,
        spaceAfter=3
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=SECONDARY_COLOR,
        spaceAfter=6
    )

    meta_style = ParagraphStyle(
        'DocMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=TEXT_MUTED
    )

    section_heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=PRIMARY_COLOR,
        spaceBefore=10,
        spaceAfter=5
    )

    cell_bold_style = ParagraphStyle(
        'CellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=PRIMARY_COLOR
    )

    cell_style = ParagraphStyle(
        'CellRegular',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=TEXT_MAIN
    )

    cell_muted_style = ParagraphStyle(
        'CellMuted',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=TEXT_MUTED
    )

    story = []

    # 1. Header Banner
    story.append(Paragraph("CAMPUS EVENT MANAGEMENT & CROWD SAFETY AUDIT", subtitle_style))
    story.append(Paragraph(f"Official Event Crowd Report: {event.get('event_name', 'Event')}", title_style))
    gen_time_str = datetime.now().strftime("%B %d, %Y at %H:%M:%S")
    story.append(Paragraph(f"Document Generated: {gen_time_str} | Event ID: #{event.get('id', 'N/A')}", meta_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=SECONDARY_COLOR, spaceAfter=10))

    # 2. Event & Venue Details Table
    story.append(Paragraph("1. Event & Venue Information", section_heading_style))

    # Format date and schedule
    event_date = event.get('approved_date') or event.get('requested_date') or 'Not Scheduled'
    start_time = str(event.get('approved_start_time') or event.get('requested_start_time') or '')
    end_time = str(event.get('approved_end_time') or event.get('requested_end_time') or '')
    schedule_str = f"{start_time} - {end_time}" if start_time and end_time else "TBD"

    venue_name = event.get('venue_name') or 'Unallocated'
    venue_loc = event.get('venue_location') or ''
    venue_display = f"{venue_name} ({venue_loc})" if venue_loc else venue_name
    capacity_val = summary.get('venue_capacity')
    capacity_str = f"{capacity_val:,} attendees" if capacity_val and capacity_val > 0 else "Not specified"

    status_str = str(event.get('status', 'Pending')).upper()

    event_info_data = [
        [
            Paragraph("Event Name:", cell_bold_style),
            Paragraph(f"<b>{event.get('event_name', '')}</b> (ID #{event.get('id')})", cell_style),
            Paragraph("Event Status:", cell_bold_style),
            Paragraph(f"<b>{status_str}</b>", cell_style),
        ],
        [
            Paragraph("Organizer:", cell_bold_style),
            Paragraph(f"{event.get('organizer_name', 'N/A')} ({event.get('organizer_email', '')})", cell_style),
            Paragraph("Fest / Series:", cell_bold_style),
            Paragraph(str(event.get('series_name') or 'Independent Event'), cell_style),
        ],
        [
            Paragraph("Allocated Venue:", cell_bold_style),
            Paragraph(venue_display, cell_style),
            Paragraph("Venue Capacity:", cell_bold_style),
            Paragraph(capacity_str, cell_style),
        ],
        [
            Paragraph("Scheduled Date:", cell_bold_style),
            Paragraph(str(event_date), cell_style),
            Paragraph("Scheduled Time:", cell_bold_style),
            Paragraph(schedule_str, cell_style),
        ],
    ]

    event_table = Table(event_info_data, colWidths=[1.3 * inch, 2.3 * inch, 1.2 * inch, 2.2 * inch])
    event_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 5),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(event_table)
    story.append(Spacer(1, 10))

    # 3. Crowd Analytics & Peak Summary Table
    story.append(Paragraph("2. Crowd Analysis & Occupancy Summary", section_heading_style))

    max_crowd = summary.get('max_crowd')
    max_crowd_str = f"{max_crowd:,} persons" if max_crowd is not None else "No data"

    util_pct = summary.get('peak_utilization_percent')
    util_str = f"{util_pct}%" if util_pct is not None else "N/A"

    crowd_level = summary.get('highest_crowd_level', 'No Data')
    analyzed_count = summary.get('analyzed_images', 0)
    total_imgs = summary.get('total_images', 0)
    alerts_count = summary.get('alerts_count', 0)

    summary_kpi_data = [
        [
            Paragraph("Total Images Uploaded", cell_bold_style),
            Paragraph("Successfully Analyzed", cell_bold_style),
            Paragraph("Peak Estimated Crowd", cell_bold_style),
            Paragraph("Venue Capacity Util.", cell_bold_style),
            Paragraph("Crowd Safety Level", cell_bold_style),
            Paragraph("Threshold Alerts", cell_bold_style),
        ],
        [
            Paragraph(str(total_imgs), cell_style),
            Paragraph(str(analyzed_count), cell_style),
            Paragraph(f"<b>{max_crowd_str}</b>", cell_style),
            Paragraph(f"<b>{util_str}</b>", cell_style),
            Paragraph(f"<b>{crowd_level}</b>", cell_style),
            Paragraph(str(alerts_count), cell_style),
        ]
    ]

    summary_table = Table(summary_kpi_data, colWidths=[1.15 * inch, 1.15 * inch, 1.25 * inch, 1.15 * inch, 1.25 * inch, 1.05 * inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BG_HEADER),
        ('BACKGROUND', (0, 1), (-1, 1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10))

    # 4. Crowd Density Chart (if historical data exists)
    if summary.get('has_data') and len(history) >= 2:
        chart_buf = _generate_history_chart(history, capacity_val)
        if chart_buf:
            story.append(Paragraph("3. Crowd Density Timeline", section_heading_style))
            story.append(RLImage(chart_buf, width=6.8 * inch, height=2.5 * inch))
            story.append(Spacer(1, 8))

    # 5. Chronological Crowd Analysis History Table
    section_num = 4 if (summary.get('has_data') and len(history) >= 2) else 3
    story.append(Paragraph(f"{section_num}. Chronological Analysis History", section_heading_style))

    if not history:
        empty_msg = (
            "No crowd analysis results are available for this event yet. "
            "Surveillance photographs have either not been uploaded or have not yet been evaluated by the computer vision pipeline."
        )
        empty_table = Table([[Paragraph(empty_msg, cell_muted_style)]], colWidths=[7.0 * inch])
        empty_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
            ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('PADDING', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        story.append(empty_table)
        story.append(Spacer(1, 10))
    else:
        history_table_data = [
            [
                Paragraph("#", cell_bold_style),
                Paragraph("Analysis Timestamp", cell_bold_style),
                Paragraph("Image ID", cell_bold_style),
                Paragraph("Predicted Crowd", cell_bold_style),
                Paragraph("Capacity Util.", cell_bold_style),
                Paragraph("Density Level", cell_bold_style),
                Paragraph("Model", cell_bold_style),
            ]
        ]

        for idx, item in enumerate(history, 1):
            ts_str = str(item.get('analysis_timestamp', ''))[:19]
            count_val = item.get('predicted_count', 0)
            u_pct = item.get('utilization_percent')
            u_str = f"{u_pct}%" if u_pct is not None else "N/A"
            lvl = item.get('crowd_level', 'Normal')
            mdl = item.get('model_name', 'CSRNet')
            img_id = str(item.get('image_id', 'N/A'))

            history_table_data.append([
                Paragraph(str(idx), cell_style),
                Paragraph(ts_str, cell_style),
                Paragraph(f"#{img_id}", cell_style),
                Paragraph(f"<b>{count_val:,}</b>", cell_style),
                Paragraph(u_str, cell_style),
                Paragraph(lvl, cell_style),
                Paragraph(mdl, cell_style),
            ])

        hist_table = Table(history_table_data, colWidths=[0.4 * inch, 1.8 * inch, 0.8 * inch, 1.1 * inch, 1.0 * inch, 1.1 * inch, 0.8 * inch])
        table_style_commands = [
            ('BACKGROUND', (0, 0), (-1, 0), BG_HEADER),
            ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]
        # Alternating row colors
        for r_idx in range(1, len(history_table_data)):
            if r_idx % 2 == 0:
                table_style_commands.append(('BACKGROUND', (0, r_idx), (-1, r_idx), BG_LIGHT))

        hist_table.setStyle(TableStyle(table_style_commands))
        story.append(hist_table)
        story.append(Spacer(1, 10))

    # 6. Crowd Threshold Alerts Section
    alerts_section_num = section_num + 1
    story.append(Paragraph(f"{alerts_section_num}. Safety Threshold Alerts Log", section_heading_style))

    if not alerts:
        alerts_note = "No automated capacity breach alerts were logged for this event."
        alerts_table = Table([[Paragraph(alerts_note, cell_muted_style)]], colWidths=[7.0 * inch])
        alerts_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
            ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('PADDING', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        story.append(alerts_table)
    else:
        alert_rows = [
            [
                Paragraph("#", cell_bold_style),
                Paragraph("Alert Time", cell_bold_style),
                Paragraph("Detected", cell_bold_style),
                Paragraph("Threshold", cell_bold_style),
                Paragraph("Status", cell_bold_style),
                Paragraph("Message", cell_bold_style),
            ]
        ]
        for a_idx, alt in enumerate(alerts, 1):
            created_str = str(alt.get('created_at', ''))[:19]
            det = alt.get('detected_count', 0)
            thr = alt.get('threshold', 0)
            st = str(alt.get('status', 'unread')).upper()
            msg = alt.get('message', '')

            alert_rows.append([
                Paragraph(str(a_idx), cell_style),
                Paragraph(created_str, cell_style),
                Paragraph(str(det), cell_style),
                Paragraph(str(thr), cell_style),
                Paragraph(st, cell_style),
                Paragraph(msg, cell_style),
            ])

        alt_table = Table(alert_rows, colWidths=[0.4 * inch, 1.5 * inch, 0.8 * inch, 0.8 * inch, 0.8 * inch, 2.7 * inch])
        alt_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), BG_HEADER),
            ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ('PADDING', (0, 0), (-1, -1), 4),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(alt_table)

    # 7. Document Footer Note
    story.append(Spacer(1, 15))
    footer_text = (
        "Institutional Notice: This official report is generated automatically by the Crowd Event Management System. "
        "Estimated headcounts are evaluated using convolutional neural crowd analysis models (CSRNet). "
        "All metrics reflect verified database surveillance records."
    )
    story.append(Paragraph(footer_text, cell_muted_style))

    doc.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer
