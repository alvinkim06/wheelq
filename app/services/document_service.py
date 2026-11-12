
from io import BytesIO
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)


RED = colors.HexColor("#B30000")
YELLOW = colors.HexColor("#F5C518")
DARK = colors.HexColor("#171717")
GREY = colors.HexColor("#666666")


def money(value):
    value = Decimal(str(value or 0))
    return f"KSh {value:,.2f}"


def generate_document(
    title,
    reference,
    customer_name,
    customer_email,
    items,
    total,
    description=None
):
    """
    Generate a WheelQ PDF invoice, receipt or notice.

    items format:
        [("Description", amount), ...]
    """

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm
    )

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="WheelQTitle",
        parent=styles["Title"],
        textColor=RED,
        fontSize=23,
        spaceAfter=8
    ))

    styles.add(ParagraphStyle(
        name="WheelQSmall",
        parent=styles["Normal"],
        textColor=GREY,
        fontSize=9
    ))

    story = []

    story.append(Paragraph(
        "WHEELQ TOURS &amp; CAR HIRE",
        styles["Heading1"]
    ))

    story.append(Paragraph(
        title.upper(),
        styles["WheelQTitle"]
    ))

    story.append(Paragraph(
        f"Reference: {reference}",
        styles["Normal"]
    ))

    story.append(Spacer(1, 12))

    story.append(Paragraph(
        f"<b>Customer:</b> {customer_name or 'Customer'}",
        styles["Normal"]
    ))

    story.append(Paragraph(
        f"<b>Email:</b> {customer_email or 'N/A'}",
        styles["Normal"]
    ))

    story.append(Spacer(1, 15))

    if description:
        story.append(Paragraph(description, styles["Normal"]))
        story.append(Spacer(1, 12))

    table_data = [["Description", "Amount"]]

    for item_name, amount in items:
        table_data.append([
            Paragraph(str(item_name), styles["Normal"]),
            money(amount)
        ])

    table_data.append(["TOTAL", money(total)])

    table = Table(
        table_data,
        colWidths=[115 * mm, 45 * mm],
        repeatRows=1
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), RED),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), YELLOW),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))

    story.append(table)
    story.append(Spacer(1, 25))

    story.append(Paragraph(
        "Thank you for choosing WheelQ Tours &amp; Car Hire.",
        styles["Normal"]
    ))

    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "This document was generated electronically by WheelQ.",
        styles["WheelQSmall"]
    ))

    document.build(story)

    buffer.seek(0)
    return buffer.getvalue()
