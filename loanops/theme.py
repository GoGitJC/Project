"""Visual system for the LoanOps workspace.

Colors are presentation tokens. They do not encode a control result;
reconciliation status is chosen in the page from ReconResult fields.
"""

NAVY = "#0B1220"
SLATE = "#172338"
BLUE = "#2563EB"
EMERALD = "#10B981"
AMBER = "#F59E0B"
RED = "#EF4444"
INK = "#0F172A"
MUTED = "#475569"
LINE = "#E2E8F0"
CANVAS = "#F4F6F8"
WHITE = "#FFFFFF"

THEME_CSS = """
<style>
  .stApp { background: #F4F6F8; color: #0F172A; }
  .block-container {
    padding-top: 1.2rem;
    padding-bottom: 3.5rem;
    max-width: 1240px;
  }
  header[data-testid="stHeader"] { background: transparent; }
  #MainMenu, footer { visibility: hidden; }
  html, body, [class*="css"] {
    font-family: "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif;
  }

  section[data-testid="stSidebar"] {
    background: #0B1220;
    border-right: 1px solid #172338;
  }
  section[data-testid="stSidebar"] [data-testid="stMarkdown"] p,
  section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
  section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
    color: #CBD5E1;
  }
  section[data-testid="stSidebar"] hr { border-color: #1E293B; }
  section[data-testid="stSidebar"] button {
    border-radius: 8px;
    justify-content: flex-start;
    text-align: left;
    font-weight: 600;
    box-shadow: none;
  }
  section[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] {
    background: transparent;
    color: #E2E8F0;
    border: 1px solid transparent;
  }
  section[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] {
    background: #172338;
    color: #FFFFFF;
    border: 1px solid #1E293B;
    box-shadow: inset 3px 0 0 #2563EB;
  }
  section[data-testid="stSidebar"] .st-key-start-briefing button {
    background: #2563EB !important;
    color: #FFFFFF !important;
    border: 1px solid #2563EB !important;
    box-shadow: none !important;
    justify-content: center;
  }
  section[data-testid="stSidebar"] .st-key-exit-briefing button {
    background: transparent !important;
    color: #CBD5E1 !important;
    border: 1px solid #334155 !important;
    box-shadow: none !important;
    justify-content: center;
  }

  [data-testid="stSelectbox"] div[data-baseweb="select"] > div,
  [data-testid="stTextInput"] input {
    background-color: #FFFFFF !important;
    color: #0F172A !important;
    border-color: #CBD5E1 !important;
  }
  [data-testid="stSelectbox"] div[data-baseweb="select"] span,
  [data-testid="stSelectbox"] input {
    color: #0F172A !important;
    -webkit-text-fill-color: #0F172A !important;
  }

  .stApp button[data-testid="stBaseButton-primary"] {
    border-radius: 8px;
    font-weight: 650;
  }
  div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px;
    border-color: #E2E8F0;
    background: #FFFFFF;
  }
  [data-testid="stDataFrame"] { border-radius: 12px; }

  .brand { display: flex; gap: 12px; align-items: center; margin: 0.2rem 0 0.8rem; }
  .brand-mark {
    width: 36px; height: 36px; border-radius: 8px;
    background: #172338; color: #FFFFFF;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; letter-spacing: 0.04em; font-size: 0.78rem;
    border: 1px solid #334155;
  }
  .brand-name { color: #F8FAFC; font-weight: 700; font-size: 1.05rem; letter-spacing: -0.02em; line-height: 1.1; }
  .brand-sub { color: #94A3B8; font-size: 0.75rem; letter-spacing: 0.08em; text-transform: uppercase; margin-top: 2px; }

  .side-note {
    margin-top: 0.8rem; padding: 0.75rem 0.8rem; border-radius: 10px;
    background: #172338; border: 1px solid #1E293B;
  }
  .side-note .label { color: #94A3B8; font-size: 0.72rem; letter-spacing: 0.06em; text-transform: uppercase; }
  .side-note .value { color: #F8FAFC; font-weight: 650; margin-top: 0.2rem; }
  .side-note .hint { color: #CBD5E1; font-size: 0.82rem; margin-top: 0.25rem; line-height: 1.35; }

  .page-kicker {
    color: #475569; font-size: 0.75rem; font-weight: 700;
    letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 0.2rem;
  }
  .page-head h1 {
    color: #0F172A; font-size: 1.7rem; line-height: 1.15;
    letter-spacing: -0.03em; margin: 0; font-weight: 700;
  }
  .page-head p { color: #475569; margin: 0.4rem 0 0; font-size: 0.98rem; line-height: 1.45; }
  .synth {
    display: inline-block; margin-top: 0.75rem;
    background: #FEF3C7; color: #92400E; border: 1px solid #FDE68A;
    border-radius: 999px; padding: 0.18rem 0.65rem;
    font-size: 0.75rem; font-weight: 700; letter-spacing: 0.02em;
  }
  .section-head { margin: 1.15rem 0 0.35rem; }
  .section-head h2 {
    color: #0F172A; font-size: 1.12rem; letter-spacing: -0.02em;
    margin: 0; font-weight: 700;
  }
  .section-head p { color: #475569; margin: 0.25rem 0 0; font-size: 0.9rem; line-height: 1.4; }

  .kpi-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 12px;
    margin: 1rem 0 0.4rem;
  }
  .kpi-grid.quarters { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .kpi {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 14px 14px 12px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    min-height: 118px;
  }
  .kpi.neutral { box-shadow: inset 3px 0 0 #2563EB, 0 1px 2px rgba(15, 23, 42, 0.04); }
  .kpi.success { box-shadow: inset 3px 0 0 #10B981, 0 1px 2px rgba(15, 23, 42, 0.04); }
  .kpi.warning { box-shadow: inset 3px 0 0 #F59E0B, 0 1px 2px rgba(15, 23, 42, 0.04); }
  .kpi.critical { box-shadow: inset 3px 0 0 #EF4444, 0 1px 2px rgba(15, 23, 42, 0.04); }
  .kpi .label {
    color: #475569; font-size: 0.72rem; font-weight: 700;
    letter-spacing: 0.05em; text-transform: uppercase;
  }
  .kpi .value {
    color: #0F172A; font-size: 1.45rem; font-weight: 700;
    letter-spacing: -0.03em; margin-top: 6px;
    font-variant-numeric: tabular-nums; line-height: 1.15;
  }
  .kpi .hint { color: #475569; font-size: 0.82rem; margin-top: 6px; line-height: 1.35; }

  .guide {
    background: #FFFFFF; border: 1px solid #BFDBFE; border-radius: 12px;
    padding: 12px 14px; margin: 0.9rem 0 0.2rem;
    box-shadow: inset 3px 0 0 #2563EB;
  }
  .guide .step { color: #1D4ED8; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; }
  .guide h3 { color: #0F172A; margin: 0.15rem 0 0; font-size: 1rem; }
  .guide p { color: #334155; margin: 0.3rem 0 0; font-size: 0.9rem; line-height: 1.4; }

  .alert {
    display: flex; gap: 10px; align-items: flex-start;
    background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px;
    padding: 10px 12px; margin-bottom: 8px;
  }
  .alert .dot { width: 8px; height: 8px; border-radius: 99px; margin-top: 6px; flex: none; }
  .alert.critical .dot { background: #EF4444; }
  .alert.warning .dot { background: #F59E0B; }
  .alert.attention .dot { background: #2563EB; }
  .alert .title { color: #0F172A; font-weight: 700; font-size: 0.92rem; }
  .alert .meta { color: #475569; font-size: 0.82rem; margin-top: 2px; }

  .dossier-top { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
  .pill {
    display: inline-block; border-radius: 999px; padding: 0.16rem 0.55rem;
    font-size: 0.75rem; font-weight: 700; letter-spacing: 0.02em;
  }
  .pill.open { background: #FEF3C7; color: #92400E; }
  .pill.clear { background: #D1FAE5; color: #065F46; }
  .pill.none { background: #F1F5F9; color: #334155; }
  .pill.critical { background: #FEE2E2; color: #991B1B; }
  .pill.warning { background: #FEF3C7; color: #92400E; }
  .pill.attention { background: #DBEAFE; color: #1E3A8A; }
  .action {
    background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 12px; padding: 12px 14px;
  }
  .action .label { color: #1E3A8A; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; }
  .action p { color: #1E3A8A; margin: 0.35rem 0 0; line-height: 1.45; }
  .empty {
    background: #FFFFFF; border: 1px dashed #CBD5E1; border-radius: 12px; padding: 22px 18px;
  }
  .empty h3 { margin: 0.2rem 0 0; color: #0F172A; font-size: 1.05rem; }
  .empty p { margin: 0.35rem 0 0; color: #475569; }

  @media (max-width: 900px) {
    .kpi-grid, .kpi-grid.quarters { grid-template-columns: 1fr; }
    .dossier-top { flex-direction: column; }
  }
</style>
"""
