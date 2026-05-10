"""
NSE Universe — 311 stocks across 17 sectors.
Covers Nifty 500 range: large cap, mid cap, small cap.
Broader universe = more realistic backtest = less survivorship bias.

Format: {"symbol": "RELIANCE.NS", "display_symbol": "RELIANCE",
          "name": "Full Company Name", "sector": "Sector", "cap": "large/mid/small"}
"""

from typing import Dict, List, TypedDict


class StockMeta(TypedDict, total=False):
    symbol: str
    display_symbol: str
    name: str
    sector: str
    cap: str
    status: str  # "active" | "distressed" | "delisted"


NSE_UNIVERSE: List[StockMeta] = [
    # ── BANKING & FINANCE (44 stocks) ──────────────────────────────────────
    {"symbol": "HDFCBANK.NS",    "display_symbol": "HDFCBANK",    "name": "HDFC Bank Ltd",                "sector": "Banking",  "cap": "large"},
    {"symbol": "ICICIBANK.NS",   "display_symbol": "ICICIBANK",   "name": "ICICI Bank Ltd",               "sector": "Banking",  "cap": "large"},
    {"symbol": "SBIN.NS",        "display_symbol": "SBIN",        "name": "State Bank of India",          "sector": "Banking",  "cap": "large"},
    {"symbol": "KOTAKBANK.NS",   "display_symbol": "KOTAKBANK",   "name": "Kotak Mahindra Bank",          "sector": "Banking",  "cap": "large"},
    {"symbol": "AXISBANK.NS",    "display_symbol": "AXISBANK",    "name": "Axis Bank Ltd",                "sector": "Banking",  "cap": "large"},
    {"symbol": "INDUSINDBK.NS",  "display_symbol": "INDUSINDBK",  "name": "IndusInd Bank Ltd",            "sector": "Banking",  "cap": "large"},
    {"symbol": "BANDHANBNK.NS",  "display_symbol": "BANDHANBNK",  "name": "Bandhan Bank Ltd",             "sector": "Banking",  "cap": "mid"},
    {"symbol": "FEDERALBNK.NS",  "display_symbol": "FEDERALBNK",  "name": "Federal Bank Ltd",             "sector": "Banking",  "cap": "mid"},
    {"symbol": "IDFCFIRSTB.NS",  "display_symbol": "IDFCFIRSTB",  "name": "IDFC First Bank Ltd",          "sector": "Banking",  "cap": "mid"},
    {"symbol": "RBLBANK.NS",     "display_symbol": "RBLBANK",     "name": "RBL Bank Ltd",                 "sector": "Banking",  "cap": "mid"},
    {"symbol": "YESBANK.NS",     "display_symbol": "YESBANK",     "name": "Yes Bank Ltd",                 "sector": "Banking",  "cap": "mid"},
    {"symbol": "PNB.NS",         "display_symbol": "PNB",         "name": "Punjab National Bank",         "sector": "Banking",  "cap": "mid"},
    {"symbol": "BANKBARODA.NS",  "display_symbol": "BANKBARODA",  "name": "Bank of Baroda",               "sector": "Banking",  "cap": "mid"},
    {"symbol": "CANARABANK.NS",  "display_symbol": "CANARABANK",  "name": "Canara Bank",                  "sector": "Banking",  "cap": "mid"},
    {"symbol": "UNIONBANK.NS",   "display_symbol": "UNIONBANK",   "name": "Union Bank of India",          "sector": "Banking",  "cap": "mid"},
    {"symbol": "MAHABANK.NS",    "display_symbol": "MAHABANK",    "name": "Bank of Maharashtra",          "sector": "Banking",  "cap": "small"},
    {"symbol": "IOB.NS",         "display_symbol": "IOB",         "name": "Indian Overseas Bank",         "sector": "Banking",  "cap": "small"},
    {"symbol": "UCOBANK.NS",     "display_symbol": "UCOBANK",     "name": "UCO Bank",                     "sector": "Banking",  "cap": "small"},
    {"symbol": "CENTRALBK.NS",   "display_symbol": "CENTRALBK",   "name": "Central Bank of India",        "sector": "Banking",  "cap": "small"},
    {"symbol": "BANKINDIA.NS",   "display_symbol": "BANKINDIA",   "name": "Bank of India",                "sector": "Banking",  "cap": "mid"},
    {"symbol": "BAJFINANCE.NS",  "display_symbol": "BAJFINANCE",  "name": "Bajaj Finance Ltd",            "sector": "NBFC",     "cap": "large"},
    {"symbol": "BAJAJFINSV.NS",  "display_symbol": "BAJAJFINSV",  "name": "Bajaj Finserv Ltd",            "sector": "NBFC",     "cap": "large"},
    {"symbol": "CHOLAFIN.NS",    "display_symbol": "CHOLAFIN",    "name": "Cholamandalam Investment",     "sector": "NBFC",     "cap": "mid"},
    {"symbol": "MUTHOOTFIN.NS",  "display_symbol": "MUTHOOTFIN",  "name": "Muthoot Finance Ltd",          "sector": "NBFC",     "cap": "mid"},
    {"symbol": "MANAPPURAM.NS",  "display_symbol": "MANAPPURAM",  "name": "Manappuram Finance Ltd",       "sector": "NBFC",     "cap": "mid"},
    {"symbol": "M&MFIN.NS",      "display_symbol": "M&MFIN",      "name": "Mahindra & Mahindra Financial","sector": "NBFC",     "cap": "mid"},
    {"symbol": "CREDITACC.NS",   "display_symbol": "CREDITACC",   "name": "Credit Access Grameen",        "sector": "NBFC",     "cap": "small"},
    {"symbol": "UJJIVAN.NS",     "display_symbol": "UJJIVAN",     "name": "Ujjivan Financial Services",   "sector": "NBFC",     "cap": "small"},
    {"symbol": "ABCAPITAL.NS",   "display_symbol": "ABCAPITAL",   "name": "Aditya Birla Capital",         "sector": "NBFC",     "cap": "mid"},
    {"symbol": "CANFINHOME.NS",  "display_symbol": "CANFINHOME",  "name": "Can Fin Homes Ltd",            "sector": "NBFC",     "cap": "small"},
    {"symbol": "PNBHOUSING.NS",  "display_symbol": "PNBHOUSING",  "name": "PNB Housing Finance",          "sector": "NBFC",     "cap": "mid"},
    {"symbol": "LICHSGFIN.NS",   "display_symbol": "LICHSGFIN",   "name": "LIC Housing Finance",          "sector": "NBFC",     "cap": "mid"},
    {"symbol": "RECLTD.NS",      "display_symbol": "RECLTD",      "name": "REC Ltd",                      "sector": "NBFC",     "cap": "large"},
    {"symbol": "PFC.NS",         "display_symbol": "PFC",         "name": "Power Finance Corporation",    "sector": "NBFC",     "cap": "large"},
    {"symbol": "IRFC.NS",        "display_symbol": "IRFC",        "name": "Indian Railway Finance Corp",  "sector": "NBFC",     "cap": "large"},
    {"symbol": "HUDCO.NS",       "display_symbol": "HUDCO",       "name": "HUDCO Ltd",                    "sector": "NBFC",     "cap": "mid"},
    {"symbol": "HDFCLIFE.NS",    "display_symbol": "HDFCLIFE",    "name": "HDFC Life Insurance",          "sector": "Insurance","cap": "large"},
    {"symbol": "SBILIFE.NS",     "display_symbol": "SBILIFE",     "name": "SBI Life Insurance",           "sector": "Insurance","cap": "large"},
    {"symbol": "ICICIGI.NS",     "display_symbol": "ICICIGI",     "name": "ICICI Lombard General Ins",    "sector": "Insurance","cap": "large"},
    {"symbol": "NIACL.NS",       "display_symbol": "NIACL",       "name": "New India Assurance",          "sector": "Insurance","cap": "mid"},
    {"symbol": "STARHEALTH.NS",  "display_symbol": "STARHEALTH",  "name": "Star Health Insurance",        "sector": "Insurance","cap": "mid"},
    {"symbol": "POLICYBZR.NS",   "display_symbol": "POLICYBZR",   "name": "PB Fintech (PolicyBazaar)",    "sector": "Insurance","cap": "mid"},
    {"symbol": "LICI.NS",        "display_symbol": "LICI",        "name": "LIC of India",                 "sector": "Insurance","cap": "large"},
    {"symbol": "GICRE.NS",       "display_symbol": "GICRE",       "name": "General Insurance Corp",       "sector": "Insurance","cap": "mid"},

    # ── IT (23 stocks) ──────────────────────────────────────────────────────
    {"symbol": "TCS.NS",         "display_symbol": "TCS",         "name": "Tata Consultancy Services",    "sector": "IT",       "cap": "large"},
    {"symbol": "INFY.NS",        "display_symbol": "INFY",        "name": "Infosys Ltd",                  "sector": "IT",       "cap": "large"},
    {"symbol": "HCLTECH.NS",     "display_symbol": "HCLTECH",     "name": "HCL Technologies Ltd",         "sector": "IT",       "cap": "large"},
    {"symbol": "WIPRO.NS",       "display_symbol": "WIPRO",       "name": "Wipro Ltd",                    "sector": "IT",       "cap": "large"},
    {"symbol": "TECHM.NS",       "display_symbol": "TECHM",       "name": "Tech Mahindra Ltd",            "sector": "IT",       "cap": "large"},
    {"symbol": "LTIM.NS",        "display_symbol": "LTIM",        "name": "LTIMindtree Ltd",              "sector": "IT",       "cap": "large"},
    {"symbol": "MPHASIS.NS",     "display_symbol": "MPHASIS",     "name": "Mphasis Ltd",                  "sector": "IT",       "cap": "mid"},
    {"symbol": "COFORGE.NS",     "display_symbol": "COFORGE",     "name": "Coforge Ltd",                  "sector": "IT",       "cap": "mid"},
    {"symbol": "PERSISTENT.NS",  "display_symbol": "PERSISTENT",  "name": "Persistent Systems Ltd",       "sector": "IT",       "cap": "mid"},
    {"symbol": "TATAELXSI.NS",   "display_symbol": "TATAELXSI",   "name": "Tata Elxsi Ltd",               "sector": "IT",       "cap": "mid"},
    {"symbol": "KPITTECH.NS",    "display_symbol": "KPITTECH",    "name": "KPIT Technologies",            "sector": "IT",       "cap": "mid"},
    {"symbol": "BSOFT.NS",       "display_symbol": "BSOFT",       "name": "Birlasoft Ltd",                "sector": "IT",       "cap": "mid"},
    {"symbol": "MASTEK.NS",      "display_symbol": "MASTEK",      "name": "Mastek Ltd",                   "sector": "IT",       "cap": "small"},
    {"symbol": "ECLERX.NS",      "display_symbol": "ECLERX",      "name": "eClerx Services Ltd",          "sector": "IT",       "cap": "small"},
    {"symbol": "SONATSOFTW.NS",  "display_symbol": "SONATSOFTW",  "name": "Sonata Software Ltd",          "sector": "IT",       "cap": "small"},
    {"symbol": "RATEGAIN.NS",    "display_symbol": "RATEGAIN",    "name": "RateGain Travel Tech",         "sector": "IT",       "cap": "small"},
    {"symbol": "NEWGEN.NS",      "display_symbol": "NEWGEN",      "name": "Newgen Software Technologies", "sector": "IT",       "cap": "small"},
    {"symbol": "TANLA.NS",       "display_symbol": "TANLA",       "name": "Tanla Platforms Ltd",          "sector": "IT",       "cap": "small"},
    {"symbol": "INTELLECT.NS",   "display_symbol": "INTELLECT",   "name": "Intellect Design Arena",       "sector": "IT",       "cap": "small"},
    {"symbol": "LATENTVIEW.NS",  "display_symbol": "LATENTVIEW",  "name": "Latent View Analytics",        "sector": "IT",       "cap": "small"},
    {"symbol": "DATAMATICS.NS",  "display_symbol": "DATAMATICS",  "name": "Datamatics Global Services",   "sector": "IT",       "cap": "small"},
    {"symbol": "HAPPSTMNDS.NS",  "display_symbol": "HAPPSTMNDS",  "name": "Happiest Minds Technologies",  "sector": "IT",       "cap": "small"},
    {"symbol": "NIITLTD.NS",     "display_symbol": "NIITLTD",     "name": "NIIT Ltd",                     "sector": "IT",       "cap": "small"},

    # ── OIL & GAS (15 stocks) ───────────────────────────────────────────────
    {"symbol": "RELIANCE.NS",    "display_symbol": "RELIANCE",    "name": "Reliance Industries Ltd",      "sector": "Oil & Gas","cap": "large"},
    {"symbol": "ONGC.NS",        "display_symbol": "ONGC",        "name": "Oil & Natural Gas Corp",       "sector": "Oil & Gas","cap": "large"},
    {"symbol": "IOC.NS",         "display_symbol": "IOC",         "name": "Indian Oil Corporation",       "sector": "Oil & Gas","cap": "large"},
    {"symbol": "BPCL.NS",        "display_symbol": "BPCL",        "name": "Bharat Petroleum Corp",        "sector": "Oil & Gas","cap": "large"},
    {"symbol": "HINDPETRO.NS",   "display_symbol": "HINDPETRO",   "name": "Hindustan Petroleum Corp",     "sector": "Oil & Gas","cap": "large"},
    {"symbol": "GAIL.NS",        "display_symbol": "GAIL",        "name": "GAIL (India) Ltd",             "sector": "Oil & Gas","cap": "large"},
    {"symbol": "PETRONET.NS",    "display_symbol": "PETRONET",    "name": "Petronet LNG Ltd",             "sector": "Oil & Gas","cap": "mid"},
    {"symbol": "MRPL.NS",        "display_symbol": "MRPL",        "name": "Mangalore Refinery",           "sector": "Oil & Gas","cap": "mid"},
    {"symbol": "CPCL.NS",        "display_symbol": "CPCL",        "name": "Chennai Petroleum Corp",       "sector": "Oil & Gas","cap": "small"},
    {"symbol": "GSPL.NS",        "display_symbol": "GSPL",        "name": "Gujarat State Petronet",       "sector": "Oil & Gas","cap": "mid"},
    {"symbol": "MGL.NS",         "display_symbol": "MGL",         "name": "Mahanagar Gas Ltd",            "sector": "Oil & Gas","cap": "mid"},
    {"symbol": "IGL.NS",         "display_symbol": "IGL",         "name": "Indraprastha Gas Ltd",         "sector": "Oil & Gas","cap": "mid"},
    {"symbol": "GUJGASLTD.NS",   "display_symbol": "GUJGASLTD",   "name": "Gujarat Gas Ltd",              "sector": "Oil & Gas","cap": "mid"},
    {"symbol": "ATGL.NS",        "display_symbol": "ATGL",        "name": "Adani Total Gas Ltd",          "sector": "Oil & Gas","cap": "large"},
    {"symbol": "OIL.NS",         "display_symbol": "OIL",         "name": "Oil India Ltd",                "sector": "Oil & Gas","cap": "large"},

    # ── AUTO (25 stocks) ────────────────────────────────────────────────────
    {"symbol": "MARUTI.NS",      "display_symbol": "MARUTI",      "name": "Maruti Suzuki India",          "sector": "Auto",     "cap": "large"},
    {"symbol": "TATAMOTORS.NS",  "display_symbol": "TATAMOTORS",  "name": "Tata Motors Ltd",              "sector": "Auto",     "cap": "large"},
    {"symbol": "M&M.NS",         "display_symbol": "M&M",         "name": "Mahindra & Mahindra",          "sector": "Auto",     "cap": "large"},
    {"symbol": "BAJAJ-AUTO.NS",  "display_symbol": "BAJAJ-AUTO",  "name": "Bajaj Auto Ltd",               "sector": "Auto",     "cap": "large"},
    {"symbol": "HEROMOTOCO.NS",  "display_symbol": "HEROMOTOCO",  "name": "Hero MotoCorp Ltd",            "sector": "Auto",     "cap": "large"},
    {"symbol": "EICHERMOT.NS",   "display_symbol": "EICHERMOT",   "name": "Eicher Motors Ltd",            "sector": "Auto",     "cap": "large"},
    {"symbol": "ASHOKLEY.NS",    "display_symbol": "ASHOKLEY",    "name": "Ashok Leyland Ltd",            "sector": "Auto",     "cap": "large"},
    {"symbol": "TVSMOTOR.NS",    "display_symbol": "TVSMOTOR",    "name": "TVS Motor Company",            "sector": "Auto",     "cap": "mid"},
    {"symbol": "ESCORTS.NS",     "display_symbol": "ESCORTS",     "name": "Escorts Kubota Ltd",           "sector": "Auto",     "cap": "mid"},
    {"symbol": "FORCEMOT.NS",    "display_symbol": "FORCEMOT",    "name": "Force Motors Ltd",             "sector": "Auto",     "cap": "small"},
    {"symbol": "MOTHERSON.NS",   "display_symbol": "MOTHERSON",   "name": "Samvardhana Motherson",        "sector": "Auto",     "cap": "large"},
    {"symbol": "BOSCHLTD.NS",    "display_symbol": "BOSCHLTD",    "name": "Bosch Ltd",                    "sector": "Auto",     "cap": "large"},
    {"symbol": "BALKRISIND.NS",  "display_symbol": "BALKRISIND",  "name": "Balkrishna Industries",        "sector": "Auto",     "cap": "mid"},
    {"symbol": "MRF.NS",         "display_symbol": "MRF",         "name": "MRF Ltd",                      "sector": "Auto",     "cap": "large"},
    {"symbol": "APOLLOTYRE.NS",  "display_symbol": "APOLLOTYRE",  "name": "Apollo Tyres Ltd",             "sector": "Auto",     "cap": "mid"},
    {"symbol": "CEATLTD.NS",     "display_symbol": "CEATLTD",     "name": "CEAT Ltd",                     "sector": "Auto",     "cap": "mid"},
    {"symbol": "JKTYRE.NS",      "display_symbol": "JKTYRE",      "name": "JK Tyre & Industries",         "sector": "Auto",     "cap": "small"},
    {"symbol": "BHARATFORG.NS",  "display_symbol": "BHARATFORG",  "name": "Bharat Forge Ltd",             "sector": "Auto",     "cap": "mid"},
    {"symbol": "SUNDRMFAST.NS",  "display_symbol": "SUNDRMFAST",  "name": "Sundram Fasteners",            "sector": "Auto",     "cap": "small"},
    {"symbol": "EXIDEIND.NS",    "display_symbol": "EXIDEIND",    "name": "Exide Industries",             "sector": "Auto",     "cap": "mid"},
    {"symbol": "TIINDIA.NS",     "display_symbol": "TIINDIA",     "name": "Tube Investments of India",    "sector": "Auto",     "cap": "mid"},
    {"symbol": "GABRIEL.NS",     "display_symbol": "GABRIEL",     "name": "Gabriel India Ltd",            "sector": "Auto",     "cap": "small"},
    {"symbol": "CRAFTSMAN.NS",   "display_symbol": "CRAFTSMAN",   "name": "Craftsman Automation",         "sector": "Auto",     "cap": "small"},
    {"symbol": "SUPRAJIT.NS",    "display_symbol": "SUPRAJIT",    "name": "Suprajit Engineering",         "sector": "Auto",     "cap": "small"},
    {"symbol": "SUBROS.NS",      "display_symbol": "SUBROS",      "name": "Subros Ltd",                   "sector": "Auto",     "cap": "small"},

    # ── PHARMA (28 stocks) ──────────────────────────────────────────────────
    {"symbol": "SUNPHARMA.NS",   "display_symbol": "SUNPHARMA",   "name": "Sun Pharmaceutical",           "sector": "Pharma",   "cap": "large"},
    {"symbol": "DRREDDY.NS",     "display_symbol": "DRREDDY",     "name": "Dr. Reddy's Laboratories",     "sector": "Pharma",   "cap": "large"},
    {"symbol": "CIPLA.NS",       "display_symbol": "CIPLA",       "name": "Cipla Ltd",                    "sector": "Pharma",   "cap": "large"},
    {"symbol": "DIVISLAB.NS",    "display_symbol": "DIVISLAB",    "name": "Divi's Laboratories",          "sector": "Pharma",   "cap": "large"},
    {"symbol": "AUROPHARMA.NS",  "display_symbol": "AUROPHARMA",  "name": "Aurobindo Pharma",             "sector": "Pharma",   "cap": "large"},
    {"symbol": "TORNTPHARM.NS",  "display_symbol": "TORNTPHARM",  "name": "Torrent Pharmaceuticals",      "sector": "Pharma",   "cap": "mid"},
    {"symbol": "ALKEM.NS",       "display_symbol": "ALKEM",       "name": "Alkem Laboratories",           "sector": "Pharma",   "cap": "mid"},
    {"symbol": "IPCALAB.NS",     "display_symbol": "IPCALAB",     "name": "IPCA Laboratories",            "sector": "Pharma",   "cap": "mid"},
    {"symbol": "LUPIN.NS",       "display_symbol": "LUPIN",       "name": "Lupin Ltd",                    "sector": "Pharma",   "cap": "large"},
    {"symbol": "BIOCON.NS",      "display_symbol": "BIOCON",      "name": "Biocon Ltd",                   "sector": "Pharma",   "cap": "mid"},
    {"symbol": "ZYDUSLIFE.NS",   "display_symbol": "ZYDUSLIFE",   "name": "Zydus Lifesciences",           "sector": "Pharma",   "cap": "large"},
    {"symbol": "GLAXO.NS",       "display_symbol": "GLAXO",       "name": "GlaxoSmithKline Pharma",       "sector": "Pharma",   "cap": "mid"},
    {"symbol": "PFIZER.NS",      "display_symbol": "PFIZER",      "name": "Pfizer Ltd",                   "sector": "Pharma",   "cap": "mid"},
    {"symbol": "SANOFI.NS",      "display_symbol": "SANOFI",      "name": "Sanofi India Ltd",             "sector": "Pharma",   "cap": "mid"},
    {"symbol": "ABBOTINDIA.NS",  "display_symbol": "ABBOTINDIA",  "name": "Abbott India Ltd",             "sector": "Pharma",   "cap": "mid"},
    {"symbol": "NATCOPHARM.NS",  "display_symbol": "NATCOPHARM",  "name": "Natco Pharma Ltd",             "sector": "Pharma",   "cap": "small"},
    {"symbol": "GRANULES.NS",    "display_symbol": "GRANULES",    "name": "Granules India Ltd",           "sector": "Pharma",   "cap": "small"},
    {"symbol": "LAURUSLABS.NS",  "display_symbol": "LAURUSLABS",  "name": "Laurus Labs Ltd",              "sector": "Pharma",   "cap": "mid"},
    {"symbol": "STRIDES.NS",     "display_symbol": "STRIDES",     "name": "Strides Pharma Science",       "sector": "Pharma",   "cap": "small"},
    {"symbol": "GLENMARK.NS",    "display_symbol": "GLENMARK",    "name": "Glenmark Pharmaceuticals",     "sector": "Pharma",   "cap": "mid"},
    {"symbol": "FDC.NS",         "display_symbol": "FDC",         "name": "FDC Ltd",                      "sector": "Pharma",   "cap": "small"},
    {"symbol": "AJANTPHARM.NS",  "display_symbol": "AJANTPHARM",  "name": "Ajanta Pharma Ltd",            "sector": "Pharma",   "cap": "small"},
    {"symbol": "ERIS.NS",        "display_symbol": "ERIS",        "name": "Eris Lifesciences",            "sector": "Pharma",   "cap": "small"},
    {"symbol": "CAPLIPOINT.NS",  "display_symbol": "CAPLIPOINT",  "name": "Caplin Point Laboratories",    "sector": "Pharma",   "cap": "small"},
    {"symbol": "NEULANDLAB.NS",  "display_symbol": "NEULANDLAB",  "name": "Neuland Laboratories",         "sector": "Pharma",   "cap": "small"},
    {"symbol": "JBCHEPHARM.NS",  "display_symbol": "JBCHEPHARM",  "name": "JB Chemicals & Pharma",        "sector": "Pharma",   "cap": "small"},
    {"symbol": "SOLARA.NS",      "display_symbol": "SOLARA",      "name": "Solara Active Pharma",         "sector": "Pharma",   "cap": "small"},
    {"symbol": "SEQUENT.NS",     "display_symbol": "SEQUENT",     "name": "SeQuent Scientific",           "sector": "Pharma",   "cap": "small"},

    # ── FMCG (20 stocks) ────────────────────────────────────────────────────
    {"symbol": "HINDUNILVR.NS",  "display_symbol": "HINDUNILVR",  "name": "Hindustan Unilever Ltd",       "sector": "FMCG",     "cap": "large"},
    {"symbol": "ITC.NS",         "display_symbol": "ITC",         "name": "ITC Ltd",                      "sector": "FMCG",     "cap": "large"},
    {"symbol": "NESTLEIND.NS",   "display_symbol": "NESTLEIND",   "name": "Nestle India Ltd",             "sector": "FMCG",     "cap": "large"},
    {"symbol": "BRITANNIA.NS",   "display_symbol": "BRITANNIA",   "name": "Britannia Industries",         "sector": "FMCG",     "cap": "large"},
    {"symbol": "DABUR.NS",       "display_symbol": "DABUR",       "name": "Dabur India Ltd",              "sector": "FMCG",     "cap": "large"},
    {"symbol": "MARICO.NS",      "display_symbol": "MARICO",      "name": "Marico Ltd",                   "sector": "FMCG",     "cap": "large"},
    {"symbol": "GODREJCP.NS",    "display_symbol": "GODREJCP",    "name": "Godrej Consumer Products",     "sector": "FMCG",     "cap": "large"},
    {"symbol": "COLPAL.NS",      "display_symbol": "COLPAL",      "name": "Colgate-Palmolive India",      "sector": "FMCG",     "cap": "large"},
    {"symbol": "EMAMILTD.NS",    "display_symbol": "EMAMILTD",    "name": "Emami Ltd",                    "sector": "FMCG",     "cap": "mid"},
    {"symbol": "TATACONSUM.NS",  "display_symbol": "TATACONSUM",  "name": "Tata Consumer Products",       "sector": "FMCG",     "cap": "large"},
    {"symbol": "VBL.NS",         "display_symbol": "VBL",         "name": "Varun Beverages Ltd",          "sector": "FMCG",     "cap": "large"},
    {"symbol": "RADICO.NS",      "display_symbol": "RADICO",      "name": "Radico Khaitan Ltd",           "sector": "FMCG",     "cap": "mid"},
    {"symbol": "MCDOWELL-N.NS",  "display_symbol": "MCDOWELL-N",  "name": "United Spirits Ltd",           "sector": "FMCG",     "cap": "large"},
    {"symbol": "BIKAJI.NS",      "display_symbol": "BIKAJI",      "name": "Bikaji Foods International",   "sector": "FMCG",     "cap": "small"},
    {"symbol": "DEVYANI.NS",     "display_symbol": "DEVYANI",     "name": "Devyani International",        "sector": "FMCG",     "cap": "mid"},
    {"symbol": "SAPPHIRE.NS",    "display_symbol": "SAPPHIRE",    "name": "Sapphire Foods India",         "sector": "FMCG",     "cap": "small"},
    {"symbol": "WESTLIFE.NS",    "display_symbol": "WESTLIFE",    "name": "Westlife Foodworld",           "sector": "FMCG",     "cap": "small"},
    {"symbol": "ZYDUSWELL.NS",   "display_symbol": "ZYDUSWELL",   "name": "Zydus Wellness Ltd",           "sector": "FMCG",     "cap": "small"},
    {"symbol": "JYOTHYLAB.NS",   "display_symbol": "JYOTHYLAB",   "name": "Jyothy Labs Ltd",              "sector": "FMCG",     "cap": "small"},
    {"symbol": "PATANJALI.NS",   "display_symbol": "PATANJALI",   "name": "Patanjali Foods Ltd",          "sector": "FMCG",     "cap": "mid"},

    # ── METALS & MINING (18 stocks) ─────────────────────────────────────────
    {"symbol": "TATASTEEL.NS",   "display_symbol": "TATASTEEL",   "name": "Tata Steel Ltd",               "sector": "Metals",   "cap": "large"},
    {"symbol": "JSWSTEEL.NS",    "display_symbol": "JSWSTEEL",    "name": "JSW Steel Ltd",                "sector": "Metals",   "cap": "large"},
    {"symbol": "HINDALCO.NS",    "display_symbol": "HINDALCO",    "name": "Hindalco Industries",          "sector": "Metals",   "cap": "large"},
    {"symbol": "VEDL.NS",        "display_symbol": "VEDL",        "name": "Vedanta Ltd",                  "sector": "Metals",   "cap": "large"},
    {"symbol": "COALINDIA.NS",   "display_symbol": "COALINDIA",   "name": "Coal India Ltd",               "sector": "Metals",   "cap": "large"},
    {"symbol": "NMDC.NS",        "display_symbol": "NMDC",        "name": "NMDC Ltd",                     "sector": "Metals",   "cap": "large"},
    {"symbol": "SAIL.NS",        "display_symbol": "SAIL",        "name": "Steel Authority of India",     "sector": "Metals",   "cap": "large"},
    {"symbol": "NATIONALUM.NS",  "display_symbol": "NATIONALUM",  "name": "National Aluminium Company",   "sector": "Metals",   "cap": "mid"},
    {"symbol": "HINDCOPPER.NS",  "display_symbol": "HINDCOPPER",  "name": "Hindustan Copper",             "sector": "Metals",   "cap": "mid"},
    {"symbol": "MOIL.NS",        "display_symbol": "MOIL",        "name": "MOIL Ltd",                     "sector": "Metals",   "cap": "small"},
    {"symbol": "APLAPOLLO.NS",   "display_symbol": "APLAPOLLO",   "name": "APL Apollo Tubes",             "sector": "Metals",   "cap": "mid"},
    {"symbol": "RATNAMANI.NS",   "display_symbol": "RATNAMANI",   "name": "Ratnamani Metals & Tubes",     "sector": "Metals",   "cap": "small"},
    {"symbol": "WELSPUNIND.NS",  "display_symbol": "WELSPUNIND",  "name": "Welspun India Ltd",            "sector": "Metals",   "cap": "mid"},
    {"symbol": "JINDALSAW.NS",   "display_symbol": "JINDALSAW",   "name": "Jindal Saw Ltd",               "sector": "Metals",   "cap": "small"},
    {"symbol": "JINDALSTEL.NS",  "display_symbol": "JINDALSTEL",  "name": "Jindal Steel & Power",         "sector": "Metals",   "cap": "large"},
    {"symbol": "NSLNISP.NS",     "display_symbol": "NSLNISP",     "name": "NMDC Steel Ltd",               "sector": "Metals",   "cap": "mid"},
    {"symbol": "GPPL.NS",        "display_symbol": "GPPL",        "name": "Gujarat Pipavav Port",         "sector": "Metals",   "cap": "small"},
    {"symbol": "MIDHANI.NS",     "display_symbol": "MIDHANI",     "name": "Mishra Dhatu Nigam",           "sector": "Metals",   "cap": "small"},

    # ── CEMENT (12 stocks) ──────────────────────────────────────────────────
    {"symbol": "ULTRACEMCO.NS",  "display_symbol": "ULTRACEMCO",  "name": "UltraTech Cement Ltd",         "sector": "Cement",   "cap": "large"},
    {"symbol": "SHREECEM.NS",    "display_symbol": "SHREECEM",    "name": "Shree Cement Ltd",             "sector": "Cement",   "cap": "large"},
    {"symbol": "AMBUJACEM.NS",   "display_symbol": "AMBUJACEM",   "name": "Ambuja Cements Ltd",           "sector": "Cement",   "cap": "large"},
    {"symbol": "ACC.NS",         "display_symbol": "ACC",         "name": "ACC Ltd",                      "sector": "Cement",   "cap": "large"},
    {"symbol": "RAMCOCEM.NS",    "display_symbol": "RAMCOCEM",    "name": "The Ramco Cements Ltd",        "sector": "Cement",   "cap": "mid"},
    {"symbol": "DALMIACMT.NS",   "display_symbol": "DALMIACMT",   "name": "Dalmia Bharat Ltd",            "sector": "Cement",   "cap": "mid"},
    {"symbol": "JKLAKSHMI.NS",   "display_symbol": "JKLAKSHMI",   "name": "JK Lakshmi Cement",            "sector": "Cement",   "cap": "small"},
    {"symbol": "HEIDELBERG.NS",  "display_symbol": "HEIDELBERG",  "name": "Heidelberg Materials India",   "sector": "Cement",   "cap": "small"},
    {"symbol": "BIRLACORPN.NS",  "display_symbol": "BIRLACORPN",  "name": "Birla Corporation Ltd",        "sector": "Cement",   "cap": "small"},
    {"symbol": "JKCEMENT.NS",    "display_symbol": "JKCEMENT",    "name": "JK Cement Ltd",                "sector": "Cement",   "cap": "mid"},
    {"symbol": "NUVOCO.NS",      "display_symbol": "NUVOCO",      "name": "Nuvoco Vistas Corp",           "sector": "Cement",   "cap": "mid"},
    {"symbol": "STARCEMENT.NS",  "display_symbol": "STARCEMENT",  "name": "Star Cement Ltd",              "sector": "Cement",   "cap": "small"},

    # ── ENGINEERING & CAPITAL GOODS (22 stocks) ─────────────────────────────
    {"symbol": "LT.NS",          "display_symbol": "LT",          "name": "Larsen & Toubro Ltd",          "sector": "Engineering","cap": "large"},
    {"symbol": "SIEMENS.NS",     "display_symbol": "SIEMENS",     "name": "Siemens Ltd",                  "sector": "Engineering","cap": "large"},
    {"symbol": "ABB.NS",         "display_symbol": "ABB",         "name": "ABB India Ltd",                "sector": "Engineering","cap": "large"},
    {"symbol": "CUMMINSIND.NS",  "display_symbol": "CUMMINSIND",  "name": "Cummins India Ltd",            "sector": "Engineering","cap": "large"},
    {"symbol": "HAVELLS.NS",     "display_symbol": "HAVELLS",     "name": "Havells India Ltd",            "sector": "Engineering","cap": "large"},
    {"symbol": "CROMPTON.NS",    "display_symbol": "CROMPTON",    "name": "Crompton Greaves Consumer",    "sector": "Engineering","cap": "mid"},
    {"symbol": "VOLTAS.NS",      "display_symbol": "VOLTAS",      "name": "Voltas Ltd",                   "sector": "Engineering","cap": "mid"},
    {"symbol": "BLUESTARCO.NS",  "display_symbol": "BLUESTARCO",  "name": "Blue Star Ltd",                "sector": "Engineering","cap": "mid"},
    {"symbol": "POLYCAB.NS",     "display_symbol": "POLYCAB",     "name": "Polycab India Ltd",            "sector": "Engineering","cap": "large"},
    {"symbol": "KEI.NS",         "display_symbol": "KEI",         "name": "KEI Industries Ltd",           "sector": "Engineering","cap": "mid"},
    {"symbol": "CGPOWER.NS",     "display_symbol": "CGPOWER",     "name": "CG Power and Industrial",      "sector": "Engineering","cap": "mid"},
    {"symbol": "BHEL.NS",        "display_symbol": "BHEL",        "name": "Bharat Heavy Electricals",     "sector": "Engineering","cap": "large"},
    {"symbol": "THERMAX.NS",     "display_symbol": "THERMAX",     "name": "Thermax Ltd",                  "sector": "Engineering","cap": "mid"},
    {"symbol": "KEC.NS",         "display_symbol": "KEC",         "name": "KEC International Ltd",        "sector": "Engineering","cap": "mid"},
    {"symbol": "KALPATPOWR.NS",  "display_symbol": "KALPATPOWR",  "name": "Kalpataru Projects Int'l",     "sector": "Engineering","cap": "small"},
    {"symbol": "ELGI.NS",        "display_symbol": "ELGI",        "name": "Elgi Equipments Ltd",          "sector": "Engineering","cap": "small"},
    {"symbol": "GRINDWELL.NS",   "display_symbol": "GRINDWELL",   "name": "Grindwell Norton Ltd",         "sector": "Engineering","cap": "small"},
    {"symbol": "CARBORUNIV.NS",  "display_symbol": "CARBORUNIV",  "name": "Carborundum Universal",        "sector": "Engineering","cap": "small"},
    {"symbol": "TIMKEN.NS",      "display_symbol": "TIMKEN",      "name": "Timken India Ltd",             "sector": "Engineering","cap": "small"},
    {"symbol": "SCHAEFFLER.NS",  "display_symbol": "SCHAEFFLER",  "name": "Schaeffler India Ltd",         "sector": "Engineering","cap": "mid"},
    {"symbol": "SKFINDIA.NS",    "display_symbol": "SKFINDIA",    "name": "SKF India Ltd",                "sector": "Engineering","cap": "mid"},
    {"symbol": "SUZLON.NS",      "display_symbol": "SUZLON",      "name": "Suzlon Energy Ltd",            "sector": "Engineering","cap": "mid"},

    # ── CONSUMER & RETAIL (18 stocks) ───────────────────────────────────────
    {"symbol": "TITAN.NS",       "display_symbol": "TITAN",       "name": "Titan Company Ltd",            "sector": "Consumer", "cap": "large"},
    {"symbol": "ASIANPAINT.NS",  "display_symbol": "ASIANPAINT",  "name": "Asian Paints Ltd",             "sector": "Consumer", "cap": "large"},
    {"symbol": "PIDILITIND.NS",  "display_symbol": "PIDILITIND",  "name": "Pidilite Industries Ltd",      "sector": "Consumer", "cap": "large"},
    {"symbol": "BERGEPAINT.NS",  "display_symbol": "BERGEPAINT",  "name": "Berger Paints India",          "sector": "Consumer", "cap": "large"},
    {"symbol": "KANSAINER.NS",   "display_symbol": "KANSAINER",   "name": "Kansai Nerolac Paints",        "sector": "Consumer", "cap": "mid"},
    {"symbol": "DMART.NS",       "display_symbol": "DMART",       "name": "Avenue Supermarts Ltd",        "sector": "Consumer", "cap": "large"},
    {"symbol": "TRENT.NS",       "display_symbol": "TRENT",       "name": "Trent Ltd",                    "sector": "Consumer", "cap": "large"},
    {"symbol": "ABFRL.NS",       "display_symbol": "ABFRL",       "name": "Aditya Birla Fashion & Retail","sector": "Consumer", "cap": "mid"},
    {"symbol": "SHOPERSTOP.NS",  "display_symbol": "SHOPERSTOP",  "name": "Shopper Stop Ltd",             "sector": "Consumer", "cap": "small"},
    {"symbol": "VMART.NS",       "display_symbol": "VMART",       "name": "V-Mart Retail Ltd",            "sector": "Consumer", "cap": "small"},
    {"symbol": "BATA.NS",        "display_symbol": "BATA",        "name": "Bata India Ltd",               "sector": "Consumer", "cap": "mid"},
    {"symbol": "PAGEIND.NS",     "display_symbol": "PAGEIND",     "name": "Page Industries Ltd",          "sector": "Consumer", "cap": "large"},
    {"symbol": "RELAXO.NS",      "display_symbol": "RELAXO",      "name": "Relaxo Footwears Ltd",         "sector": "Consumer", "cap": "mid"},
    {"symbol": "METRO.NS",       "display_symbol": "METRO",       "name": "Metro Brands Ltd",             "sector": "Consumer", "cap": "mid"},
    {"symbol": "KALYANKJIL.NS",  "display_symbol": "KALYANKJIL",  "name": "Kalyan Jewellers India",       "sector": "Consumer", "cap": "mid"},
    {"symbol": "RAJESHEXPO.NS",  "display_symbol": "RAJESHEXPO",  "name": "Rajesh Exports Ltd",           "sector": "Consumer", "cap": "mid"},
    {"symbol": "SENCO.NS",       "display_symbol": "SENCO",       "name": "Senco Gold Ltd",               "sector": "Consumer", "cap": "small"},
    {"symbol": "CAMPUS.NS",      "display_symbol": "CAMPUS",      "name": "Campus Activewear Ltd",        "sector": "Consumer", "cap": "small"},

    # ── HEALTHCARE (12 stocks) ──────────────────────────────────────────────
    {"symbol": "APOLLOHOSP.NS",  "display_symbol": "APOLLOHOSP",  "name": "Apollo Hospitals Enterprise",  "sector": "Healthcare","cap": "large"},
    {"symbol": "FORTIS.NS",      "display_symbol": "FORTIS",      "name": "Fortis Healthcare Ltd",        "sector": "Healthcare","cap": "mid"},
    {"symbol": "MAXHEALTH.NS",   "display_symbol": "MAXHEALTH",   "name": "Max Healthcare Institute",     "sector": "Healthcare","cap": "mid"},
    {"symbol": "NARAYANHRU.NS",  "display_symbol": "NARAYANHRU",  "name": "Narayana Hrudayalaya",         "sector": "Healthcare","cap": "mid"},
    {"symbol": "KIMS.NS",        "display_symbol": "KIMS",        "name": "Krishna Institute of Medical", "sector": "Healthcare","cap": "mid"},
    {"symbol": "ASTER.NS",       "display_symbol": "ASTER",       "name": "Aster DM Healthcare",          "sector": "Healthcare","cap": "mid"},
    {"symbol": "THYROCARE.NS",   "display_symbol": "THYROCARE",   "name": "Thyrocare Technologies",       "sector": "Healthcare","cap": "small"},
    {"symbol": "METROPOLIS.NS",  "display_symbol": "METROPOLIS",  "name": "Metropolis Healthcare",        "sector": "Healthcare","cap": "mid"},
    {"symbol": "LALPATHLAB.NS",  "display_symbol": "LALPATHLAB",  "name": "Dr Lal PathLabs Ltd",          "sector": "Healthcare","cap": "mid"},
    {"symbol": "VIJAYADIAG.NS",  "display_symbol": "VIJAYADIAG",  "name": "Vijaya Diagnostic Centre",     "sector": "Healthcare","cap": "small"},
    {"symbol": "POLYMED.NS",     "display_symbol": "POLYMED",     "name": "Poly Medicure Ltd",            "sector": "Healthcare","cap": "small"},
    {"symbol": "KRSNAA.NS",      "display_symbol": "KRSNAA",      "name": "Krsnaa Diagnostics Ltd",       "sector": "Healthcare","cap": "small"},

    # ── TELECOM (8 stocks) ──────────────────────────────────────────────────
    {"symbol": "BHARTIARTL.NS",  "display_symbol": "BHARTIARTL",  "name": "Bharti Airtel Ltd",            "sector": "Telecom",  "cap": "large"},
    {"symbol": "IDEA.NS",        "display_symbol": "IDEA",        "name": "Vodafone Idea Ltd",            "sector": "Telecom",  "cap": "small"},
    {"symbol": "TATACOMM.NS",    "display_symbol": "TATACOMM",    "name": "Tata Communications Ltd",      "sector": "Telecom",  "cap": "large"},
    {"symbol": "INDUSTOWER.NS",  "display_symbol": "INDUSTOWER",  "name": "Indus Towers Ltd",             "sector": "Telecom",  "cap": "large"},
    {"symbol": "HFCL.NS",        "display_symbol": "HFCL",        "name": "HFCL Ltd",                     "sector": "Telecom",  "cap": "small"},
    {"symbol": "STLTECH.NS",     "display_symbol": "STLTECH",     "name": "Sterlite Technologies",        "sector": "Telecom",  "cap": "small"},
    {"symbol": "ROUTE.NS",       "display_symbol": "ROUTE",       "name": "Route Mobile Ltd",             "sector": "Telecom",  "cap": "small"},
    {"symbol": "TEJASNET.NS",    "display_symbol": "TEJASNET",    "name": "Tejas Networks Ltd",           "sector": "Telecom",  "cap": "small"},

    # ── REAL ESTATE (13 stocks) ─────────────────────────────────────────────
    {"symbol": "DLF.NS",         "display_symbol": "DLF",         "name": "DLF Ltd",                      "sector": "Realty",   "cap": "large"},
    {"symbol": "GODREJPROP.NS",  "display_symbol": "GODREJPROP",  "name": "Godrej Properties Ltd",        "sector": "Realty",   "cap": "large"},
    {"symbol": "OBEROIRLTY.NS",  "display_symbol": "OBEROIRLTY",  "name": "Oberoi Realty Ltd",            "sector": "Realty",   "cap": "mid"},
    {"symbol": "PHOENIXLTD.NS",  "display_symbol": "PHOENIXLTD",  "name": "The Phoenix Mills Ltd",        "sector": "Realty",   "cap": "large"},
    {"symbol": "BRIGADE.NS",     "display_symbol": "BRIGADE",     "name": "Brigade Enterprises Ltd",      "sector": "Realty",   "cap": "mid"},
    {"symbol": "PRESTIGE.NS",    "display_symbol": "PRESTIGE",    "name": "Prestige Estates Projects",    "sector": "Realty",   "cap": "mid"},
    {"symbol": "SOBHA.NS",       "display_symbol": "SOBHA",       "name": "Sobha Ltd",                    "sector": "Realty",   "cap": "small"},
    {"symbol": "MAHLIFE.NS",     "display_symbol": "MAHLIFE",     "name": "Mahindra Lifespace Developers","sector": "Realty",   "cap": "small"},
    {"symbol": "KOLTEPATIL.NS",  "display_symbol": "KOLTEPATIL",  "name": "Kolte-Patil Developers",       "sector": "Realty",   "cap": "small"},
    {"symbol": "SUNTECK.NS",     "display_symbol": "SUNTECK",     "name": "Sunteck Realty Ltd",           "sector": "Realty",   "cap": "small"},
    {"symbol": "MACROTECH.NS",   "display_symbol": "MACROTECH",   "name": "Macrotech Developers (Lodha)", "sector": "Realty",   "cap": "large"},
    {"symbol": "SIGNATURE.NS",   "display_symbol": "SIGNATURE",   "name": "Signature Global India",       "sector": "Realty",   "cap": "small"},
    {"symbol": "ARVIND.NS",      "display_symbol": "ARVIND",      "name": "Arvind Ltd",                   "sector": "Realty",   "cap": "small"},

    # ── POWER & UTILITIES (13 stocks) ───────────────────────────────────────
    {"symbol": "POWERGRID.NS",   "display_symbol": "POWERGRID",   "name": "Power Grid Corp of India",     "sector": "Power",    "cap": "large"},
    {"symbol": "NTPC.NS",        "display_symbol": "NTPC",        "name": "NTPC Ltd",                     "sector": "Power",    "cap": "large"},
    {"symbol": "TATAPOWER.NS",   "display_symbol": "TATAPOWER",   "name": "Tata Power Company",           "sector": "Power",    "cap": "large"},
    {"symbol": "ADANIGREEN.NS",  "display_symbol": "ADANIGREEN",  "name": "Adani Green Energy",           "sector": "Power",    "cap": "large"},
    {"symbol": "ADANIPOWER.NS",  "display_symbol": "ADANIPOWER",  "name": "Adani Power Ltd",              "sector": "Power",    "cap": "large"},
    {"symbol": "JSWENERGY.NS",   "display_symbol": "JSWENERGY",   "name": "JSW Energy Ltd",               "sector": "Power",    "cap": "large"},
    {"symbol": "TORNTPOWER.NS",  "display_symbol": "TORNTPOWER",  "name": "Torrent Power Ltd",            "sector": "Power",    "cap": "mid"},
    {"symbol": "CESC.NS",        "display_symbol": "CESC",        "name": "CESC Ltd",                     "sector": "Power",    "cap": "mid"},
    {"symbol": "NHPC.NS",        "display_symbol": "NHPC",        "name": "NHPC Ltd",                     "sector": "Power",    "cap": "mid"},
    {"symbol": "SJVN.NS",        "display_symbol": "SJVN",        "name": "SJVN Ltd",                     "sector": "Power",    "cap": "mid"},
    {"symbol": "IRCTC.NS",       "display_symbol": "IRCTC",       "name": "Indian Railway Catering & Tourism","sector": "Power","cap": "large"},
    {"symbol": "RVNL.NS",        "display_symbol": "RVNL",        "name": "Rail Vikas Nigam Ltd",         "sector": "Power",    "cap": "mid"},
    {"symbol": "IRCON.NS",       "display_symbol": "IRCON",       "name": "IRCON International Ltd",      "sector": "Power",    "cap": "mid"},

    # ── CHEMICALS (17 stocks) ───────────────────────────────────────────────
    {"symbol": "ATUL.NS",        "display_symbol": "ATUL",        "name": "Atul Ltd",                     "sector": "Chemicals","cap": "mid"},
    {"symbol": "NAVINFLUOR.NS",  "display_symbol": "NAVINFLUOR",  "name": "Navin Fluorine International", "sector": "Chemicals","cap": "mid"},
    {"symbol": "FLUOROCHEM.NS",  "display_symbol": "FLUOROCHEM",  "name": "Gujarat Fluorochemicals",      "sector": "Chemicals","cap": "mid"},
    {"symbol": "DEEPAKNTR.NS",   "display_symbol": "DEEPAKNTR",   "name": "Deepak Nitrite Ltd",           "sector": "Chemicals","cap": "mid"},
    {"symbol": "AARTIIND.NS",    "display_symbol": "AARTIIND",    "name": "Aarti Industries Ltd",         "sector": "Chemicals","cap": "mid"},
    {"symbol": "CLEAN.NS",       "display_symbol": "CLEAN",       "name": "Clean Science & Technology",   "sector": "Chemicals","cap": "small"},
    {"symbol": "FINEORG.NS",     "display_symbol": "FINEORG",     "name": "Fine Organic Industries",      "sector": "Chemicals","cap": "small"},
    {"symbol": "SUDARSCHEM.NS",  "display_symbol": "SUDARSCHEM",  "name": "Sudarshan Chemical Ind",       "sector": "Chemicals","cap": "small"},
    {"symbol": "TATACHEM.NS",    "display_symbol": "TATACHEM",    "name": "Tata Chemicals Ltd",           "sector": "Chemicals","cap": "mid"},
    {"symbol": "GHCL.NS",        "display_symbol": "GHCL",        "name": "GHCL Ltd",                     "sector": "Chemicals","cap": "small"},
    {"symbol": "ALKYLAMINE.NS",  "display_symbol": "ALKYLAMINE",  "name": "Alkyl Amines Chemicals",       "sector": "Chemicals","cap": "small"},
    {"symbol": "NOCIL.NS",       "display_symbol": "NOCIL",       "name": "NOCIL Ltd",                    "sector": "Chemicals","cap": "small"},
    {"symbol": "GALAXYSURF.NS",  "display_symbol": "GALAXYSURF",  "name": "Galaxy Surfactants",           "sector": "Chemicals","cap": "small"},
    {"symbol": "JUBILANT.NS",    "display_symbol": "JUBILANT",    "name": "Jubilant Ingrevia",            "sector": "Chemicals","cap": "small"},
    {"symbol": "ASTECLTD.NS",    "display_symbol": "ASTECLTD",    "name": "Astec Lifesciences",           "sector": "Chemicals","cap": "small"},
    {"symbol": "VINDHYATEL.NS",  "display_symbol": "VINDHYATEL",  "name": "Vindhya Telelinks",            "sector": "Chemicals","cap": "small"},
    {"symbol": "SRF.NS",         "display_symbol": "SRF",         "name": "SRF Ltd",                      "sector": "Chemicals","cap": "large"},

    # ── CONGLOMERATE & INFRA (8 stocks) ─────────────────────────────────────
    {"symbol": "ADANIENT.NS",    "display_symbol": "ADANIENT",    "name": "Adani Enterprises Ltd",        "sector": "Conglomerate","cap": "large"},
    {"symbol": "ADANIPORTS.NS",  "display_symbol": "ADANIPORTS",  "name": "Adani Ports & SEZ",            "sector": "Conglomerate","cap": "large"},
    {"symbol": "ADANITRANS.NS",  "display_symbol": "ADANITRANS",  "name": "Adani Transmission Ltd",       "sector": "Conglomerate","cap": "large"},
    {"symbol": "GMRAIRPORT.NS",  "display_symbol": "GMRAIRPORT",  "name": "GMR Airports Infrastructure",  "sector": "Conglomerate","cap": "large"},
    {"symbol": "IRB.NS",         "display_symbol": "IRB",         "name": "IRB Infrastructure Developers","sector": "Conglomerate","cap": "mid"},
    {"symbol": "CONCOR.NS",      "display_symbol": "CONCOR",      "name": "Container Corporation of India","sector": "Conglomerate","cap": "large"},
    {"symbol": "GATI.NS",        "display_symbol": "GATI",        "name": "Gati Ltd",                     "sector": "Conglomerate","cap": "small"},
    {"symbol": "VRL.NS",         "display_symbol": "VRL",         "name": "VRL Logistics Ltd",            "sector": "Conglomerate","cap": "small"},

    # ── NEW ECONOMY (10 stocks) ─────────────────────────────────────────────
    {"symbol": "ZOMATO.NS",      "display_symbol": "ZOMATO",      "name": "Zomato Ltd",                   "sector": "NewEconomy","cap": "large"},
    {"symbol": "NYKAA.NS",       "display_symbol": "NYKAA",       "name": "FSN E-Commerce (Nykaa)",       "sector": "NewEconomy","cap": "mid"},
    {"symbol": "PAYTM.NS",       "display_symbol": "PAYTM",       "name": "One 97 Communications (Paytm)","sector": "NewEconomy","cap": "mid"},
    {"symbol": "DELHIVERY.NS",   "display_symbol": "DELHIVERY",   "name": "Delhivery Ltd",                "sector": "NewEconomy","cap": "mid"},
    {"symbol": "CARTRADE.NS",    "display_symbol": "CARTRADE",    "name": "CarTrade Tech Ltd",            "sector": "NewEconomy","cap": "small"},
    {"symbol": "EASEMYTRIP.NS",  "display_symbol": "EASEMYTRIP",  "name": "Easy Trip Planners",           "sector": "NewEconomy","cap": "small"},
    {"symbol": "INDIAMART.NS",   "display_symbol": "INDIAMART",   "name": "IndiaMART InterMESH",          "sector": "NewEconomy","cap": "mid"},
    {"symbol": "JUSTDIAL.NS",    "display_symbol": "JUSTDIAL",    "name": "Just Dial Ltd",                "sector": "NewEconomy","cap": "small"},
    {"symbol": "AFFLE.NS",       "display_symbol": "AFFLE",       "name": "Affle (India) Ltd",            "sector": "NewEconomy","cap": "small"},
    {"symbol": "NAZARA.NS",      "display_symbol": "NAZARA",      "name": "Nazara Technologies",          "sector": "NewEconomy","cap": "small"},
]

# ── PARTIAL SURVIVORSHIP BIAS FIX ───────────────────────────────────────────
# Stocks that were prominent but have severely declined or been delisted.
# Included in BACKTEST ONLY — never the live screener.
DELISTED_OR_DISTRESSED: List[StockMeta] = [
    {"symbol": "RCOM.NS",        "display_symbol": "RCOM",        "name": "Reliance Communications",      "sector": "Telecom",     "cap": "small", "status": "distressed"},
    {"symbol": "JETAIRWAYS.NS",  "display_symbol": "JETAIRWAYS",  "name": "Jet Airways (India)",          "sector": "Aviation",    "cap": "small", "status": "delisted"},
    {"symbol": "VIDEOIND.NS",    "display_symbol": "VIDEOIND",    "name": "Videocon Industries",          "sector": "Consumer",    "cap": "small", "status": "distressed"},
    {"symbol": "DHFL.NS",        "display_symbol": "DHFL",        "name": "Dewan Housing Finance",        "sector": "NBFC",        "cap": "mid",   "status": "delisted"},
    {"symbol": "UNITECH.NS",     "display_symbol": "UNITECH",     "name": "Unitech Ltd",                  "sector": "Realty",      "cap": "small", "status": "distressed"},
    {"symbol": "JPASSOCIAT.NS",  "display_symbol": "JPASSOCIAT",  "name": "Jaiprakash Associates",        "sector": "Conglomerate","cap": "small", "status": "distressed"},
    {"symbol": "GMRINFRA.NS",    "display_symbol": "GMRINFRA",    "name": "GMR Infrastructure",           "sector": "Conglomerate","cap": "mid",   "status": "distressed"},
    {"symbol": "RELINFRA.NS",    "display_symbol": "RELINFRA",    "name": "Reliance Infrastructure",      "sector": "Power",       "cap": "small", "status": "distressed"},
    {"symbol": "RPOWER.NS",      "display_symbol": "RPOWER",      "name": "Reliance Power",               "sector": "Power",       "cap": "small", "status": "distressed"},
    {"symbol": "PNBHOUSFIN.NS",  "display_symbol": "PNBHOUSFIN",  "name": "PNB Housing (legacy ticker)",  "sector": "NBFC",        "cap": "small", "status": "distressed"},
]

# Combined universe for backtest (active + distressed)
BACKTEST_UNIVERSE: List[StockMeta] = NSE_UNIVERSE + DELISTED_OR_DISTRESSED


# ── Helpers ─────────────────────────────────────────────────────────────────

def get_all_symbols() -> List[str]:
    """All symbols for the live screener (active stocks only)."""
    return [s["symbol"] for s in NSE_UNIVERSE]


def get_backtest_symbols() -> List[str]:
    """All symbols for the backtest (active + distressed). Reduces survivorship bias."""
    seen: set[str] = set()
    out: List[str] = []
    for s in BACKTEST_UNIVERSE:
        sym = s["symbol"]
        if sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def get_symbol_metadata(symbol: str) -> Dict[str, str]:
    """Return metadata for a symbol — looks across both active and distressed lists."""
    for s in BACKTEST_UNIVERSE:
        if s["symbol"] == symbol:
            return dict(s)
    return {
        "symbol": symbol,
        "display_symbol": symbol.replace(".NS", "").replace(".BO", ""),
        "name": symbol,
        "sector": "Unknown",
        "cap": "unknown",
    }


# Backward-compat alias used by some Phase 1 callers
def get_meta(symbol: str) -> Dict[str, str]:
    return get_symbol_metadata(symbol)


def get_by_sector(sector: str) -> List[StockMeta]:
    return [s for s in NSE_UNIVERSE if s.get("sector") == sector]


def get_by_cap(cap: str) -> List[StockMeta]:
    return [s for s in NSE_UNIVERSE if s.get("cap") == cap]


SECTORS: List[str] = sorted({s["sector"] for s in NSE_UNIVERSE})
TOTAL_STOCKS: int = len(NSE_UNIVERSE)

# Quick lookup by symbol (used by Phase 1 market.py and screener.py)
UNIVERSE_MAP: Dict[str, StockMeta] = {s["symbol"]: s for s in BACKTEST_UNIVERSE}


def all_symbols() -> List[str]:
    """Backward-compat: returns active symbols only."""
    return get_all_symbols()
