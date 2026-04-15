"""
Cape Flats SANDF Deployment — Simulation Seed PDF
Clean, properly formatted newspaper article + agent cards.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak, NextPageTemplate,
    CondPageBreak,
)
from reportlab.platypus.flowables import Flowable
from reportlab.pdfbase import pdfmetrics

W, H    = A4
M       = 18 * mm   # margin
GUTTER  = 6 * mm    # column gutter
COL2    = (W - 2*M - GUTTER) / 2
FULL    = W - 2*M

# ── Palette ───────────────────────────────────────────────────────────────────
INK     = colors.HexColor("#111111")
RED     = colors.HexColor("#BB2222")
GOLD    = colors.HexColor("#C8A84B")
DARK    = colors.HexColor("#1C2636")
STEEL   = colors.HexColor("#3D5166")
LGREY   = colors.HexColor("#F5F5F5")
RULE    = colors.HexColor("#CCCCCC")
MUTED   = colors.HexColor("#777777")
WHITE   = colors.white

# ── Styles ────────────────────────────────────────────────────────────────────
def sty(name, **kw):
    return ParagraphStyle(name, **kw)

# Masthead
MASTHEAD   = sty("Masthead",   fontName="Helvetica-Bold",   fontSize=30, leading=34,
                               textColor=INK,  alignment=TA_CENTER, spaceAfter=0)
KICKER     = sty("Kicker",     fontName="Helvetica",        fontSize=7.5,
                               textColor=MUTED, alignment=TA_CENTER, spaceAfter=0)
DATELINE   = sty("Dateline",   fontName="Helvetica-Oblique",fontSize=7.5,
                               textColor=MUTED, alignment=TA_LEFT,  spaceAfter=0)
EDITION    = sty("Edition",    fontName="Helvetica",        fontSize=7.5,
                               textColor=MUTED, alignment=TA_RIGHT, spaceAfter=0)

# Article
SECTION    = sty("Section",    fontName="Helvetica-Bold",   fontSize=7,  letterSpacing=1.5,
                               textColor=RED,   alignment=TA_LEFT,  spaceAfter=3, spaceBefore=4)
HEADLINE   = sty("Headline",   fontName="Helvetica-Bold",   fontSize=22, leading=26,
                               textColor=INK,   alignment=TA_LEFT,  spaceAfter=4)
SUBHEAD    = sty("Subhead",    fontName="Helvetica-Oblique",fontSize=11, leading=15,
                               textColor=MUTED, alignment=TA_LEFT,  spaceAfter=6)
BYLINE     = sty("Byline",     fontName="Helvetica-Bold",   fontSize=7.5,
                               textColor=MUTED, alignment=TA_LEFT,  spaceAfter=1)
BODY       = sty("Body",       fontName="Helvetica",        fontSize=9,  leading=14,
                               textColor=INK,   alignment=TA_JUSTIFY, spaceAfter=6, firstLineIndent=10)
BODY_FIRST = sty("BodyFirst",  fontName="Helvetica",        fontSize=9,  leading=14,
                               textColor=INK,   alignment=TA_JUSTIFY, spaceAfter=6)
CAPTION    = sty("Caption",    fontName="Helvetica-Oblique",fontSize=7.5,
                               textColor=MUTED, alignment=TA_CENTER, spaceAfter=4)
PULL       = sty("Pull",       fontName="Helvetica-BoldOblique", fontSize=13, leading=18,
                               textColor=RED,   alignment=TA_CENTER, spaceAfter=0)

# Agent cards
CARD_HEAD  = sty("CardHead",   fontName="Helvetica-Bold",   fontSize=11,
                               textColor=WHITE, alignment=TA_LEFT,  spaceAfter=0)
CARD_ROLE  = sty("CardRole",   fontName="Helvetica",        fontSize=8,
                               textColor=colors.HexColor("#AABBCC"), alignment=TA_LEFT, spaceAfter=0)
CARD_LABEL = sty("CardLabel",  fontName="Helvetica-Bold",   fontSize=6.5, letterSpacing=0.8,
                               textColor=STEEL, alignment=TA_LEFT,  spaceAfter=1, spaceBefore=5)
CARD_BODY  = sty("CardBody",   fontName="Helvetica",        fontSize=8.5, leading=13,
                               textColor=INK,   alignment=TA_JUSTIFY, spaceAfter=3)
CARD_ITAL  = sty("CardItal",   fontName="Helvetica-Oblique",fontSize=8.5, leading=13,
                               textColor=INK,   alignment=TA_JUSTIFY, spaceAfter=3)
CARD_STANCE= sty("CardStance", fontName="Helvetica-Bold",   fontSize=7.5,
                               textColor=WHITE, spaceAfter=0)
CARD_META  = sty("CardMeta",   fontName="Helvetica",        fontSize=7.5,
                               textColor=MUTED, spaceAfter=0)
TOPICS_STY = sty("Topics",     fontName="Helvetica-Oblique",fontSize=7.5,
                               textColor=MUTED, spaceAfter=0)

# Section banner (agents page)
BANNER_STY = sty("Banner",     fontName="Helvetica-Bold",   fontSize=10, letterSpacing=1.2,
                               textColor=WHITE, alignment=TA_CENTER, spaceAfter=0)

# ── Custom Flowables ──────────────────────────────────────────────────────────

class FilledRect(Flowable):
    """A simple coloured rectangle spacer."""
    def __init__(self, w, h, fill):
        super().__init__()
        self.width, self._h, self.fill = w, h, fill
    def wrap(self, aW, aH): return self.width, self._h
    def draw(self):
        self.canv.setFillColor(self.fill)
        self.canv.rect(0, 0, self.width, self._h, fill=1, stroke=0)

class DropCapPara(Flowable):
    """First paragraph with an oversized drop-cap first letter."""
    def __init__(self, text, width, cap_size=36, body_size=9, leading=14):
        super().__init__()
        self._text    = text
        self._width   = width
        self._cap     = cap_size
        self._body    = body_size
        self._leading = leading
        self.hAlign   = "LEFT"

    def wrap(self, aW, aH):
        # Estimate height: drop cap is ~3 lines tall
        cap_w = self._cap * 0.65
        rest_w = self._width - cap_w - 3
        chars_per_line = int(rest_w / (self._body * 0.55))
        first_word = self._text.split()[0]
        rest = self._text[len(first_word):]
        lines_beside = int(self._cap * 2.4 / self._leading)
        rest_lines = len(rest) // max(1, chars_per_line) + lines_beside + 2
        self._h = max(self._cap + 4, rest_lines * self._leading + 4)
        return self._width, self._h

    def draw(self):
        c = self.canv
        first_letter = self._text[0]
        rest = self._text[1:]
        cap_w = self._cap * 0.65 + 4

        # Drop cap
        c.setFont("Helvetica-Bold", self._cap)
        c.setFillColor(INK)
        c.drawString(0, self._h - self._cap - 2, first_letter)

        # Rest of paragraph beside and below cap
        from reportlab.platypus import Paragraph as Para
        from reportlab.lib.styles import ParagraphStyle as PS
        side_w = self._width - cap_w - 2
        side_h = self._cap + 4
        p = Para(rest, BODY_FIRST)
        pw, ph = p.wrap(side_w, 9999)
        p.drawOn(c, cap_w, self._h - ph - 2)

# ── Page decorators ───────────────────────────────────────────────────────────

def article_page(canvas, doc):
    canvas.saveState()
    # Thin red top bar
    canvas.setFillColor(RED)
    canvas.rect(0, H - 4, W, 4, fill=1, stroke=0)
    # Footer rule + text
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(M, 12*mm, W - M, 12*mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(M, 8*mm, "THE CAPE HERALD  |  Saturday, 12 April 2026")
    canvas.drawRightString(W - M, 8*mm, f"Page {doc.page}")
    canvas.restoreState()

def agents_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(DARK)
    canvas.rect(0, H - 4, W, 4, fill=1, stroke=0)
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(M, 12*mm, W - M, 12*mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(M, 8*mm, "FUB POLICY SIM  |  Operation Restore Order  |  Simulation Agent Profiles")
    canvas.drawRightString(W - M, 8*mm, f"Page {doc.page}")
    canvas.restoreState()

# ── Document setup ────────────────────────────────────────────────────────────

OUTPUT = "D:/Fub-agentsociety/cape_flats_simulation.pdf"

art_frame = Frame(M, 14*mm, FULL, H - 14*mm - M, id="article", showBoundary=0)
ag_frame  = Frame(M, 14*mm, FULL, H - 14*mm - M, id="agents",  showBoundary=0)

doc = BaseDocTemplate(
    OUTPUT,
    pagesize=A4,
    leftMargin=M, rightMargin=M,
    topMargin=M,  bottomMargin=14*mm,
    title="Cape Flats SANDF Deployment — Simulation Seed",
    author="FUB Policy Sim",
)
doc.addPageTemplates([
    PageTemplate(id="article", frames=[art_frame], onPage=article_page),
    PageTemplate(id="agents",  frames=[ag_frame],  onPage=agents_page),
])

story = []

# ════════════════════════════════════════════════════════════════════════════════
# MASTHEAD
# ════════════════════════════════════════════════════════════════════════════════

# Top meta row
meta_row = Table(
    [[Paragraph("Saturday, 12 April 2026", DATELINE),
      Paragraph("THE CAPE HERALD", MASTHEAD),
      Paragraph("Est. 1994  |  R10.00", EDITION)]],
    colWidths=[FULL*0.25, FULL*0.5, FULL*0.25],
)
meta_row.setStyle(TableStyle([
    ("VALIGN",        (0,0), (-1,-1), "BOTTOM"),
    ("TOPPADDING",    (0,0), (-1,-1), 0),
    ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ("LEFTPADDING",   (0,0), (-1,-1), 0),
    ("RIGHTPADDING",  (0,0), (-1,-1), 0),
]))
story.append(meta_row)
story.append(Spacer(1, 2*mm))
story.append(HRFlowable(width=FULL, thickness=3, color=INK, spaceAfter=1))
story.append(HRFlowable(width=FULL, thickness=1, color=INK, spaceAfter=2))
story.append(Paragraph(
    "CAPE TOWN  ·  WESTERN CAPE  ·  SOUTH AFRICA  ·  POLICY, CRIME &amp; COMMUNITY",
    KICKER))
story.append(HRFlowable(width=FULL, thickness=0.5, color=RULE, spaceAfter=5))

# ════════════════════════════════════════════════════════════════════════════════
# ARTICLE — full-width headline block
# ════════════════════════════════════════════════════════════════════════════════

story.append(Paragraph("NATIONAL SECURITY", SECTION))
story.append(Paragraph(
    "Ramaphosa to Deploy SANDF on Cape Flats as Murder Rate Defies Police",
    HEADLINE))
story.append(Paragraph(
    "President signs extension of Operation Restore Order amid warnings from rights groups "
    "and community leaders that soldiers cannot solve a social crisis",
    SUBHEAD))
story.append(Paragraph(
    "By Sipho Ndlovu and Karen van Wyk  ·  Cape Town Bureau  ·  12 April 2026",
    BYLINE))
story.append(HRFlowable(width=FULL, thickness=0.5, color=RULE, spaceAfter=4))

# ── Two-column article body ───────────────────────────────────────────────────

P1 = (
    "President Cyril Ramaphosa has authorised a fresh deployment of South African National "
    "Defence Force soldiers to the Cape Flats, extending Operation Restore Order for a further "
    "six months after murder statistics for the region showed no sustained decline. The deployment "
    "will see approximately 1 400 troops from the SA Army's 7 Infantry Battalion and supporting "
    "elements operating alongside SAPS units across Manenberg, Hanover Park, Bonteheuwel, "
    "Mitchell's Plain, Nyanga and Khayelitsha."
)
P2 = (
    "The announcement came after Western Cape Premier Alan Winde wrote to the presidency in "
    "March, citing a 14 percent year-on-year increase in gang-related murders across the Cape "
    "Flats corridor and describing the SAPS Anti-Gang Unit as 'critically under-resourced and "
    "overwhelmed.' Nyanga has recorded a murder rate of 197 per 100 000 residents — among the "
    "highest of any precinct in the world — for the third consecutive year."
)
P3 = (
    "Speaking at a briefing in Cape Town, Ramaphosa described the deployment as a stabilisation "
    "measure to allow police to rebuild investigative capacity. Critics noted that similar "
    "commitments accompanied the 2019 deployment, which ended with crime returning to "
    "pre-deployment levels within weeks of the drawdown."
)
P4 = (
    "The South African Human Rights Commission, which has an open inquiry into alleged "
    "misconduct during previous deployments — including sjambok incidents and unlawful "
    "entry into homes — issued a statement welcoming efforts to protect communities "
    "but insisting on binding oversight mechanisms and an independent complaints channel."
)
P5 = (
    "On the ground, reactions are sharply divided. In Hanover Park, residents described "
    "exhaustion more than hope. 'We've seen them come and go,' said one 52-year-old woman. "
    "'The gangs just wait. They're still here when the trucks leave.' Her neighbour "
    "disagreed: 'At least my children can walk to school in the morning. Last year I "
    "couldn't do that.' In Khayelitsha, EFF branch members staged a protest at a SANDF "
    "checkpoint on the NY1 arterial holding placards reading 'Soldiers Are Not Social Workers.'"
)
P6 = (
    "Criminologists at UCT's Centre of Criminology published data showing that the "
    "2019 Operation Lockdown reduced shootings in targeted areas by 31 percent over "
    "six weeks, but that the rate returned to baseline within ten weeks of drawdown. "
    "'The evidence is consistent across multiple deployments internationally,' said "
    "Associate Professor Reza Solomon. 'Military presence suppresses surface-level activity. "
    "It does not disrupt the economic and social conditions that sustain gang structures. "
    "Until we address the 60-plus-percent youth unemployment rate on the Cape Flats, "
    "we are patching a burst pipe with a cloth.'"
)
P7 = (
    "The Western Cape Department of Community Safety, which has long lobbied for permanent "
    "SANDF presence, welcomed the extension. MEC Reagen Allen described it as 'a necessary "
    "intervention by a national government that has for too long left Western Cape communities "
    "to bear the consequences of its own policy failures on housing and employment.' The ANC's "
    "Western Cape provincial structure hit back, accusing the DA of 'using the bodies of Cape "
    "Flats residents as a political prop while opposing every national programme designed to "
    "address the root causes of poverty.'"
)
P8 = (
    "The deployment is scheduled to begin 1 May 2026. Community policing forums in "
    "Mitchell's Plain and Manenberg have been invited to briefings with the SANDF "
    "operational commander, Brigadier-General Thulani Mbatha, on 22 April. Residents "
    "and civil society organisations have until 30 April to submit to the SAHRC monitoring "
    "desk that will operate for the duration of the deployment."
)

PULL_TEXT = (
    '"We are not abandoning these communities to gangsters.\n'
    'The state will be visible, and it will be firm."\n'
    '— President Ramaphosa'
)

# Column 1: P1, P2, P3 | pull quote | Column 2: P4–P8

def art(text):
    return Paragraph(text, BODY)

def art_first(text):
    return Paragraph(text, BODY_FIRST)

col1 = [
    art_first(P1),
    art(P2),
    art(P3),
]
col2 = [
    art(P4),
    art(P5),
    art(P6),
    art(P7),
    art(P8),
]

def vstack(items, width):
    """Wrap a list of flowables into a single-column Table cell."""
    rows = [[item] for item in items]
    t = Table(rows, colWidths=[width])
    t.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
    ]))
    return t

pull_cell = Table(
    [[Paragraph(PULL_TEXT, PULL)]],
    colWidths=[COL2],
)
pull_cell.setStyle(TableStyle([
    ("TOPPADDING",    (0,0), (-1,-1), 8),
    ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ("RIGHTPADDING",  (0,0), (-1,-1), 6),
    ("LINEABOVE",     (0,0), (-1,-1), 1.5, RED),
    ("LINEBELOW",     (0,0), (-1,-1), 1.5, RED),
]))

left_col_items = [
    vstack(col1, COL2),
    Spacer(1, 4*mm),
    pull_cell,
]

two_col = Table(
    [[vstack(left_col_items, COL2), vstack(col2, COL2)]],
    colWidths=[COL2, COL2],
    hAlign="LEFT",
)
two_col.setStyle(TableStyle([
    ("VALIGN",       (0,0), (-1,-1), "TOP"),
    ("TOPPADDING",   (0,0), (-1,-1), 0),
    ("BOTTOMPADDING",(0,0), (-1,-1), 0),
    ("LEFTPADDING",  (0,0), (-1,-1), 0),
    ("RIGHTPADDING", (0,0), (-1,-1), 0),
    ("LINEBEFORE",   (1,0), (1,-1),  0.5, RULE),
    ("LEFTPADDING",  (1,0), (1,-1),  GUTTER),
]))
story.append(two_col)

# ════════════════════════════════════════════════════════════════════════════════
# AGENTS SECTION
# ════════════════════════════════════════════════════════════════════════════════

story.append(NextPageTemplate("agents"))
story.append(PageBreak())

# Section banner
banner = Table(
    [[Paragraph("SIMULATION AGENTS", BANNER_STY)]],
    colWidths=[FULL],
)
banner.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,-1), DARK),
    ("TOPPADDING",    (0,0), (-1,-1), 7),
    ("BOTTOMPADDING", (0,0), (-1,-1), 7),
    ("LEFTPADDING",   (0,0), (-1,-1), 0),
]))
story.append(banner)
story.append(Spacer(1, 2*mm))
story.append(Paragraph(
    "Eight agents seeded from this article. Each holds a distinct position, background, "
    "and set of constraints shaped by life on the Cape Flats.",
    sty("Intro", fontName="Helvetica-Oblique", fontSize=8.5, textColor=MUTED,
        alignment=TA_CENTER, spaceAfter=5)
))
story.append(HRFlowable(width=FULL, thickness=0.5, color=RULE, spaceAfter=4))

# ── Agent data ────────────────────────────────────────────────────────────────

AGENTS = [
    {
        "name": "Leticia September",
        "role": "Unemployed single mother  ·  Bonteheuwel",
        "meta": [
            ("Age", "34"), ("Gender", "Female"), ("Education", "Grade 11"),
            ("Occupation", "Unemployed"), ("Marital Status", "Single"), ("Province", "Western Cape"),
        ],
        "persona": (
            "A desperate Bonteheuwel mother surviving on child support grants whose teenage son "
            "is drifting toward gang life. She clings to the deployment as the first time the "
            "state has felt present on her street."
        ),
        "background": (
            "Leticia has lived in the same damp Council flat in Bonteheuwel her whole life. "
            "She has three children and receives R1 590 in child support grants each month. "
            "Her 16-year-old son Deon has been coming home later and later; she found a "
            "knife in his school bag last month. When soldiers came during the last deployment, "
            "Deon was home before dark for the first time in months. Load-shedding terrifies "
            "her because it darkens the streets and the gangs move in the dark."
        ),
        "stance": "Strongly pro-deployment",
        "stance_color": colors.HexColor("#1A6B3C"),
        "topics": "social grants  ·  housing  ·  child safety  ·  load-shedding  ·  gang recruitment",
    },
    {
        "name": "Thabo Sithole",
        "role": "Community development worker  ·  Manenberg",
        "meta": [
            ("Age", "34"), ("Gender", "Male"), ("Education", "GED (completed in prison)"),
            ("Occupation", "NGO Youth Worker"), ("Marital Status", "Single"), ("Province", "Western Cape"),
        ],
        "persona": (
            "A reformed 28s gang member who speaks with the authority of lived experience. "
            "Deeply sceptical of military solutions — believes community-led rehabilitation "
            "is the only durable answer."
        ),
        "background": (
            "Thabo grew up in Manenberg's 7th Avenue flats and was recruited into the Hard Livings "
            "at 14. Seven years in Pollsmoor changed him slowly — a prison chaplain and a UCT law "
            "student planted the seed. He now runs Second Chance SA, a youth diversion programme, "
            "from his grandmother's garage. He has seen SANDF deployments come and go. "
            "Load-shedding kills the computers in his study centre and darkens the streets "
            "where gang recruiters wait."
        ),
        "stance": "Anti-deployment",
        "stance_color": RED,
        "topics": "gang rehabilitation  ·  youth unemployment  ·  Pollsmoor conditions  ·  social grants",
    },
    {
        "name": "Fatima Davids",
        "role": "Primary school teacher  ·  Hanover Park",
        "meta": [
            ("Age", "46"), ("Gender", "Female"), ("Education", "B.Ed, UNISA"),
            ("Occupation", "Teacher"), ("Marital Status", "Married"), ("Province", "Western Cape"),
        ],
        "persona": (
            "A Cape Malay schoolteacher shaped by 19 years on the front line of gang-affected "
            "education. Pragmatic: she wants soldiers AND social workers, not one without the other."
        ),
        "background": (
            "Fatima's family was forcibly removed from the Foreshore to Hanover Park under "
            "apartheid. She has taught at Hanover Park Primary for 19 years and keeps "
            "photographs of two students killed in crossfire on her classroom wall — one in 2019, "
            "one in 2022. She supports the deployment but is furious the announcement came with "
            "no social services budget. Her husband drives a minibus taxi on the Hanover Park "
            "to CBD route, navigating the taxi industry's relationship with gang protection."
        ),
        "stance": "Conditional support",
        "stance_color": colors.HexColor("#B07D10"),
        "topics": "school safety  ·  GBV  ·  education funding  ·  community policing  ·  trauma",
    },
    {
        "name": "Ayanda Nkosi",
        "role": "EFF Youth Organiser (unemployed)  ·  Khayelitsha",
        "meta": [
            ("Age", "22"), ("Gender", "Male"), ("Education", "Incomplete BA Politics, Stellenbosch"),
            ("Occupation", "Unemployed / Organiser"), ("Marital Status", "Single"), ("Province", "Western Cape"),
        ],
        "persona": (
            "A radicalised EFF youth organiser who frames gang violence as a product of apartheid "
            "spatial planning and fiercely opposes military presence in Black working-class communities."
        ),
        "background": (
            "Ayanda arrived at Stellenbosch on NSFAS in 2021 and dropped out in 2022 after "
            "load-shedding knocked out the library generators during exam season. He returned to "
            "Khayelitsha Site B and joined the EFF Youth Command. He organises marches at SANDF "
            "roadblocks on the NY1 and documents soldier behaviour on WhatsApp groups. Youth "
            "unemployment at 60-plus percent is not a statistic to him. It is his life."
        ),
        "stance": "Strongly anti-deployment",
        "stance_color": RED,
        "topics": "land reform  ·  youth unemployment  ·  police brutality  ·  racial inequality",
    },
    {
        "name": "Yusuf Jacobs",
        "role": "CPF Chairman / hardware store owner  ·  Mitchell's Plain",
        "meta": [
            ("Age", "58"), ("Gender", "Male"), ("Education", "Matric"),
            ("Occupation", "Business Owner / CPF Chair"), ("Marital Status", "Married"), ("Province", "Western Cape"),
        ],
        "persona": (
            "A grizzled Mitchell's Plain CPF chairman who has spent 30 years building community "
            "intelligence no soldier can replicate. Wants deployment to work but insists it must "
            "follow local knowledge."
        ),
        "background": (
            "Yusuf was born in District Six in 1967 and forcibly removed to Mitchell's Plain at 11. "
            "He opened a hardware store in 1995 and has chaired the CPF for three elected terms. "
            "He has personally mediated two gang truces and knows gang leaders by their street names "
            "and their mothers' names. He believes SANDF soldiers are well-meaning but blind: "
            "a patrol route that crosses rival gang borders at the wrong hour can spark a retaliatory "
            "shooting."
        ),
        "stance": "Cautious support",
        "stance_color": colors.HexColor("#B07D10"),
        "topics": "community policing  ·  gang mediation  ·  SAPS resourcing  ·  social cohesion",
    },
    {
        "name": "Councillor Nomsa Dlamini",
        "role": "ANC Ward Councillor  ·  Nyanga",
        "meta": [
            ("Age", "51"), ("Gender", "Female"), ("Education", "Diploma in Public Administration, UNISA"),
            ("Occupation", "Ward Councillor"), ("Marital Status", "Widowed"), ("Province", "Western Cape"),
        ],
        "persona": (
            "An ANC ward councillor representing Nyanga — South Africa's murder capital — "
            "navigating the impossible terrain between party loyalty, community desperation, "
            "and gang threats on her own life."
        ),
        "background": (
            "Nomsa was born in Nyanga East. Her husband, a COSATU shop steward, was killed in a "
            "taxi dispute in 2014. She won her seat in 2016 and inherited a ward with a murder rate "
            "of 197 per 100 000. Gang structures control the informal housing rental market. She "
            "has received three written threats since 2021. She supports the deployment because "
            "SAPS Nyanga has lost half its detectives to transfers and corruption investigations — "
            "but knows the ANC is not blameless on housing delivery."
        ),
        "stance": "Reluctant support",
        "stance_color": colors.HexColor("#B07D10"),
        "topics": "housing  ·  unemployment  ·  ANC accountability  ·  social grants  ·  SAPS capacity",
    },
    {
        "name": "Dr. Reza Solomon",
        "role": "UCT Criminologist  ·  Observatory, Cape Town",
        "meta": [
            ("Age", "49"), ("Gender", "Male"), ("Education", "PhD Criminology, UCT"),
            ("Occupation", "Academic / Media Commentator"), ("Marital Status", "Divorced"), ("Province", "Western Cape"),
        ],
        "persona": (
            "A UCT criminologist who argues from data that military deployment treats symptoms "
            "not causes, and that 60-plus percent youth unemployment is the variable that actually "
            "drives gang membership."
        ),
        "background": (
            "Reza grew up in Bo-Kaap and earned his doctorate examining the sociological origins "
            "of the Numbers Gangs. His book 'The Numbers and the State' is taught at four South "
            "African universities. His data from 2019 shows a 31 percent reduction in shootings "
            "over six weeks and a return to baseline within ten weeks of drawdown. He is not "
            "anti-police — he is pro-evidence. He worries each deployment cycle raises expectations "
            "and then shatters them, deepening distrust of the state in the communities that most "
            "need it."
        ),
        "stance": "Anti-deployment",
        "stance_color": RED,
        "topics": "gang sociology  ·  policing reform  ·  evidence-based policy  ·  rehabilitation",
    },
    {
        "name": "Marcia van Rooyen",
        "role": "Social Worker, Western Cape DSD  ·  Manenberg",
        "meta": [
            ("Age", "38"), ("Gender", "Female"), ("Education", "BSocSci Social Work, UWC"),
            ("Occupation", "Social Worker"), ("Marital Status", "Married"), ("Province", "Western Cape"),
        ],
        "persona": (
            "A frontline social worker who has absorbed 12 years of gang-related trauma and "
            "insists that soldiers without social workers is a wasted and potentially harmful "
            "intervention."
        ),
        "background": (
            "Marcia chose social work at UWC because her uncle was shot in a gang fight when she "
            "was 15 and no one helped his family process what happened. She has carried more than "
            "60 active cases in Manenberg since 2013 — gang-affected children, mothers in "
            "abusive relationships, young men from Pollsmoor with no resettlement support. She "
            "has written to the Western Cape DSD MEC three times demanding a social services "
            "budget accompany the deployment. No response."
        ),
        "stance": "Neutral — furious at the lack of social services funding",
        "stance_color": STEEL,
        "topics": "GBV  ·  trauma counselling  ·  child welfare  ·  rehabilitation  ·  social grants",
    },
]

# ── Render agent cards ────────────────────────────────────────────────────────

def make_card(ag):
    """Build one full-width agent card."""
    # Stance badge colour
    sc = ag["stance_color"]

    # Demographics mini-table
    meta = ag["meta"]
    meta_rows = []
    for i in range(0, len(meta), 3):
        chunk = meta[i:i+3]
        row = []
        for label, val in chunk:
            row.append(Paragraph(f"<b>{label}</b>", CARD_META))
            row.append(Paragraph(val, CARD_META))
        # Pad to 6 cols if short
        while len(row) < 6:
            row.append(Paragraph("", CARD_META))
        meta_rows.append(row)

    col_w = FULL / 6
    demo = Table(meta_rows, colWidths=[col_w] * 6)
    demo.setStyle(TableStyle([
        ("FONTNAME",      (0,0), (-1,-1), "Helvetica"),
        ("FONTNAME",      (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME",      (2,0), (2,-1), "Helvetica-Bold"),
        ("FONTNAME",      (4,0), (4,-1), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 7.5),
        ("TEXTCOLOR",     (0,0), (0,-1),  STEEL),
        ("TEXTCOLOR",     (2,0), (2,-1),  STEEL),
        ("TEXTCOLOR",     (4,0), (4,-1),  STEEL),
        ("TOPPADDING",    (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ]))

    # Stance badge
    stance_badge = Table(
        [[Paragraph(ag["stance"].upper(), CARD_STANCE)]],
        colWidths=[50*mm],
    )
    stance_badge.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), sc),
        ("TOPPADDING",    (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
    ]))

    # Assemble card content
    card_content = [
        # Header bar
        Table(
            [[Paragraph(ag["name"], CARD_HEAD), Paragraph(ag["role"], CARD_ROLE)]],
            colWidths=[70*mm, FULL - 70*mm],
        ),
        # Demo row
        demo,
        # Divider
        HRFlowable(width=FULL, thickness=0.3, color=RULE, spaceAfter=2, spaceBefore=2),
        # Persona
        Paragraph("PERSONA", CARD_LABEL),
        Paragraph(ag["persona"], CARD_ITAL),
        # Background
        Paragraph("BACKGROUND", CARD_LABEL),
        Paragraph(ag["background"], CARD_BODY),
        # Footer row: stance + topics
        Table(
            [[stance_badge, Paragraph(ag["topics"], TOPICS_STY)]],
            colWidths=[52*mm, FULL - 52*mm],
        ),
    ]

    # Style header bar
    card_content[0].setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), DARK),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))

    # Style footer row
    card_content[-1].setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), LGREY),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (0,-1),  0),
        ("LEFTPADDING",   (1,0), (1,-1),  8),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]))

    # Wrap in outer card table
    rows = [[item] for item in card_content]
    outer = Table(rows, colWidths=[FULL])
    outer.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,1), (-1,-2), 0),
        ("BOTTOMPADDING", (0,1), (-1,-2), 0),
        ("LEFTPADDING",   (0,1), (-1,-2), 8),
        ("RIGHTPADDING",  (0,1), (-1,-2), 8),
        ("TOPPADDING",    (0,2), (-1,2),  3),  # divider row
        ("BOTTOMPADDING", (0,2), (-1,2),  0),
        ("BOX",           (0,0), (-1,-1), 0.5, RULE),
    ]))
    return outer

for ag in AGENTS:
    story.append(KeepTogether([make_card(ag), Spacer(1, 4*mm)]))

# ── Build ─────────────────────────────────────────────────────────────────────
doc.build(story)
print(f"PDF written: {OUTPUT}")
