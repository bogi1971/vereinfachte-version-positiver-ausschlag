#!/usr/bin/env python3
"""
VVPA - Volume & Volatility Price Alert
Auto-Scan: Alle Biotech & Pharma Aktien < $30
Zyklus: 15 Minuten
Unterstützt Pre-Market, Regular und Post-Market Stunden
"""

import os
import sys
import asyncio
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class PriceAlert:
    symbol: str
    price: float
    change_pct: float
    volume: int
    timestamp: datetime


class PolygonAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.polygon.io"
        self._session: Optional[aiohttp.ClientSession] = None
        self.request_times = []
        self.cache = {}
        
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=10)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session
    
    async def _rate_limit(self):
        """Rate Limiting für kostenlose API - 5 Anfragen pro Minute"""
        now = datetime.now()
        self.request_times = [t for t in self.request_times if (now - t).total_seconds() < 60]
        
        if len(self.request_times) >= 5:
            oldest = self.request_times[0]
            wait_time = 60 - (now - oldest).total_seconds()
            if wait_time > 0:
                logger.debug(f"Rate Limit: Warte {wait_time:.1f} Sekunden...")
                await asyncio.sleep(wait_time)
        
        self.request_times.append(now)
    
    async def test_api_key(self) -> bool:
        """Testet ob der API-Key funktioniert"""
        session = await self._get_session()
        url = f"{self.base_url}/v1/meta/symbols/AAPL/company"
        params = {"apiKey": self.api_key}
        
        try:
            await self._rate_limit()
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    logger.info("✅ Polygon API-Key ist gültig")
                    return True
                else:
                    text = await resp.text()
                    logger.error(f"❌ Polygon API-Key Fehler {resp.status}: {text[:200]}")
                    return False
        except Exception as e:
            logger.error(f"❌ API-Test fehlgeschlagen: {e}")
            return False
    
    async def get_biotech_pharma_tickers(self) -> List[str]:
        """Hole Biotech & Pharma Aktien (vordefinierte Liste für kostenlose API)"""
        # Umfangreiche Liste der wichtigsten Biotech und Pharma Aktien
        tickers = [
            "ABCL", "ABEO", "ABOS", "ABSI", "ABUS", "ACAD", "ACET", "ACHL", "ACIU", "ACLX",
            "ACOR", "ACRS", "ACST", "ADAG", "ADAP", "ADCT", "ADIL", "ADMA", "ADMP", "ADPT",
            "ADTX", "AEON", "AEZS", "AFMD", "AGEN", "AGIO", "AKBA", "AKRO", "ALBO", "ALDX",
            "ALEC", "ALIM", "ALKS", "ALLO", "ALNY", "ALPN", "ALRN", "ALRS", "ALT", "ALVR",
            "ALXO", "AMAM", "AMGN", "AMPH", "AMRN", "AMRX", "ANAB", "ANEB", "ANIK", "ANIP",
            "ANVS", "APDN", "APGE", "APLS", "APLT", "APM", "APRE", "APTO", "ARAV", "ARCT",
            "ARDX", "ARGX", "ARNA", "ARQT", "ARVN", "ARWR", "ASLN", "ASND", "ASRT", "ATAI",
            "ATEC", "ATHA", "ATHE", "ATHX", "ATNM", "ATOS", "ATRA", "ATRC", "ATRI", "ATXS",
            "AUPH", "AUTL", "AVAH", "AVBP", "AVDL", "AVEO", "AVIR", "AVRO", "AVTE", "AVTX",
            "AVXL", "AXGN", "AXNX", "AXSM", "AYTU", "AZTA", "BCAB", "BCAX", "BCEL", "BCLI",
            "BCRX", "BDTX", "BEAM", "BIIB", "BIOC", "BIOL", "BIOR", "BIVI", "BLCM", "BLFS",
            "BLPH", "BLRX", "BLTE", "BLUE", "BMEA", "BMRA", "BMRN", "BMY", "BNGO", "BNOX",
            "BNTC", "BNTX", "BPMC", "BPTH", "BRAG", "BTAI", "BTMD", "BXRX", "CABA", "CADL",
            "CALA", "CALT", "CANC", "CANF", "CAPR", "CARA", "CARM", "CASI", "CBAY", "CBIO",
            "CCCC", "CCXI", "CDAK", "CDIO", "CDMO", "CDNA", "CDT", "CDTX", "CDXC", "CDXS",
            "CELC", "CELH", "CELU", "CELZ", "CERE", "CERS", "CGTX", "CHRS", "CING", "CKPT",
            "CLDI", "CLDX", "CLGN", "CLLS", "CLNN", "CLOV", "CLPT", "CLRB", "CLSD", "CLSK",
            "CMPS", "CMPX", "CMRX", "CNCE", "CNSP", "CNTA", "CNTB", "CNTG", "CNTX", "COCP",
            "COGT", "COLL", "CORS", "CPHI", "CPIX", "CPRX", "CRBP", "CRBU", "CRDF", "CRDL",
            "CRIS", "CRMD", "CRNX", "CRVS", "CRXT", "CSBR", "CSTE", "CSTL", "CTCX", "CTIC",
            "CTKB", "CTMX", "CTNM", "CTNT", "CTXR", "CUE", "CURV", "CUTR", "CVAC", "CVGW",
            "CVM", "CVNC", "CYBN", "CYCC", "CYCN", "CYRX", "CYTH", "CYTK", "DARE", "DATS",
            "DAVE", "DBVT", "DCPH", "DENN", "DERM", "DICE", "DMTK", "DNLI", "DNMR", "DOMO",
            "DORM", "DOUG", "DRMA", "DRRX", "DRTS", "DTIL", "DVAX", "DYAI", "DYN", "DYNT",
            "EBS", "ECOR", "EDAP", "EDBL", "EDSA", "EDTX", "EGAN", "EGRX", "EIGR", "ELEV",
            "ELDN", "ELOX", "ELTX", "ELUT", "ELVN", "EMKR", "ENLV", "ENOB", "ENTA", "ENTX",
            "ENVB", "ENZ", "EOLS", "EOSE", "EPIX", "EPZM", "ERAS", "ERIE", "ERII", "ERNA",
            "ESPR", "ESTA", "ETNB", "ETON", "EVBG", "EVGN", "EVGO", "EVH", "EVLO", "EVOK",
            "EVOL", "EVOP", "EVTV", "EVTX", "EWTX", "EXAI", "EXAS", "EXEL", "EXRX", "EYE",
            "EYEN", "EYPT", "FARM", "FATE", "FBIO", "FBLG", "FBRX", "FCEL", "FCRX", "FDMT",
            "FEMY", "FENC", "FGEN", "FHTX", "FIXX", "FOLD", "FORA", "FORG", "FPRX", "FREQ",
            "FREY", "FRGE", "FRSX", "FSR", "FTFT", "FTHM", "FULC", "FUSB", "FUSN", "FWBI",
            "GALT", "GAMB", "GASS", "GBIO", "GBS", "GENE", "GENI", "GERN", "GEVO", "GH",
            "GHRS", "GHSI", "GILD", "GLAD", "GLBE", "GLBL", "GLDG", "GLNG", "GLPG", "GLRE",
            "GLUE", "GLYC", "GMAB", "GMDA", "GNFT", "GNLN", "GNPX", "GOSS", "GOVX", "GPRE",
            "GRCL", "GRFS", "GRPH", "GRTS", "GRTX", "GSAT", "GTHX", "GTIM", "GURE", "GVP",
            "GYRO", "HALO", "HAPP", "HARP", "HAYN", "HBT", "HCAT", "HCCI", "HCDI", "HCM",
            "HCWB", "HEAR", "HEPA", "HEPS", "HERD", "HGEN", "HGTY", "HIMS", "HITI", "HLTH",
            "HMST", "HOFV", "HOOK", "HOTH", "HOWL", "HROW", "HRTX", "HSDT", "HSKA", "HTBX",
            "HTCR", "HTGM", "HTOO", "HUGE", "HUMA", "HURA", "HUT", "HWBK", "HYFM", "HYLN",
            "HYMC", "HYPR", "HZNP", "IART", "IBIO", "IBRX", "ICAD", "ICCC", "ICD", "ICHR",
            "ICLK", "ICPT", "ICUI", "IDEX", "IDN", "IDRA", "IDYA", "IEA", "IFRX", "IGC",
            "IGMS", "IKNA", "IKT", "ILMN", "IMAB", "IMAC", "IMBI", "IMCC", "IMCR", "IMGN",
            "IMNM", "IMPL", "IMPP", "IMRN", "IMRX", "IMTE", "IMTX", "IMUX", "IMV", "IMVT",
            "IMXI", "INAB", "INBX", "INCR", "INCY", "INDI", "INDP", "INDV", "INFN", "INFU",
            "INGN", "INKT", "INLX", "INMB", "INMD", "INNV", "INO", "INOD", "INOV", "INSE",
            "INSG", "INSM", "INSP", "INST", "INTG", "INTR", "INTT", "INUV", "INVA", "INVE",
            "INZY", "IOBT", "IONM", "IONQ", "IONS", "IOVA", "IPHA", "IPSC", "IPW", "IRMD",
            "IRON", "IRTC", "IRWD", "ISEE", "ISPC", "ISPO", "ISPR", "ITCI", "ITOS", "ITRM",
            "JAGX", "JANX", "JAZZ", "JNPR", "JOBY", "JSPR", "JUNS", "JYNT", "KALA", "KALV",
            "KARO", "KAVL", "KDP", "KELYA", "KELYB", "KERN", "KEQU", "KFFB", "KFS", "KHC",
            "KIDS", "KIQ", "KIRK", "KITT", "KITL", "KLIC", "KLTR", "KMDA", "KNDI", "KNOP",
            "KNSA", "KNSL", "KNTE", "KNW", "KOD", "KODK", "KOPN", "KORE", "KOS", "KOSS",
            "KPLT", "KPRX", "KPTI", "KRKR", "KRMD", "KRNL", "KRNT", "KRNY", "KROS", "KRUS",
            "KRYS", "KSCP", "KSPN", "KTRA", "KTTA", "KULR", "KURA", "KVHI", "KVSA", "KVSC",
            "KWE", "KXIN", "KYCH", "KYMR", "KZIA", "KZR", "LAB", "LABD", "LABU", "LAC",
            "LADR", "LAKE", "LALT", "LAMR", "LANC", "LAND", "LARK", "LASR", "LAUR", "LAW",
            "LBAI", "LBBB", "LBC", "LBPH", "LBRDA", "LBRDK", "LBTYA", "LBTYB", "LBTYK", "LC",
            "LCA", "LCAA", "LCAP", "LCCC", "LCE", "LCFY", "LCI", "LCID", "LCII", "LCNB",
            "LCUT", "LDEM", "LDI", "LDP", "LDR", "LDSF", "LDWY", "LE", "LEA", "LEAD",
            "LECO", "LEDS", "LEE", "LEG", "LEGH", "LEGN", "LEGR", "LEJU", "LEN", "LENZ",
            "LEO", "LESL", "LEU", "LEV", "LEVI", "LEXX", "LFAC", "LFLY", "LFMD", "LFMDP",
            "LFST", "LFT", "LFTR", "LFUS", "LFVN", "LGAC", "LGCB", "LGHL", "LGI", "LGIH",
            "LGL", "LGMK", "LGND", "LGO", "LGP", "LGST", "LGTY", "LH", "LHC", "LHCG",
            "LHDX", "LHE", "LHI", "LHK", "LHX", "LI", "LIDR", "LIFE", "LII", "LILA",
            "LILAK", "LINC", "LIND", "LINX", "LION", "LIQT", "LIT", "LITE", "LITH", "LITT",
            "LITM", "LIVE", "LIVN", "LIXT", "LIZI", "LJPC", "LKCO", "LKFN", "LKOR", "LKSB",
            "LKT", "LL", "LLAP", "LLL", "LLY", "LMACA", "LMACU", "LMAT", "LMB", "LMBS",
            "LMFA", "LMND", "LMNL", "LMNR", "LMRK", "LMST", "LMT", "LN", "LNC", "LND",
            "LNDC", "LNG", "LNN", "LNSR", "LNT", "LNTH", "LOAN", "LOB", "LOCO", "LOGC",
            "LOGI", "LOKM", "LOLA", "LOMA", "LON", "LOOP", "LOPE", "LORL", "LOT", "LOTZ",
            "LOVE", "LOW", "LPCN", "LPG", "LPI", "LPL", "LPLA", "LPSN", "LPTV", "LPX",
            "LQD", "LQDA", "LQDT", "LR", "LRCX", "LRFC", "LRGE", "LRMR", "LRN", "LRNZ",
            "LSAK", "LSBK", "LSCC", "LSEA", "LSF", "LSI", "LSPD", "LSTR", "LSXMA", "LSXMB",
            "LSXMK", "LTBR", "LTC", "LTCH", "LTH", "LTHM", "LTL", "LTLS", "LTM", "LTRN",
            "LTRPA", "LTRPB", "LTRX", "LTRY", "LU", "LUCD", "LUCK", "LULU", "LUMO", "LUNA",
            "LUNG", "LUV", "LVAC", "LVLU", "LVO", "LVOX", "LVRO", "LVS", "LVTX", "LVWR",
            "LW", "LWAY", "LX", "LXEH", "LXFR", "LXP", "LXRX", "LXU", "LYB", "LYEL",
            "LYFT", "LYG", "LYL", "LYLT", "LYRA", "LYTS", "LYV", "LZ", "LZAG", "LZEA",
            "LZGI", "LZRG", "LZWS", "M", "MA", "MAA", "MAAV", "MAC", "MACE", "MACK",
            "MAG", "MAGA", "MAGN", "MAIN", "MAMB", "MAN", "MANH", "MANT", "MANU", "MAPS",
            "MAQC", "MAR", "MARA", "MARK", "MARPS", "MART", "MARX", "MAS", "MASI", "MASS",
            "MAT", "MATW", "MATX", "MAV", "MAX", "MAXN", "MAXR", "MAYB", "MBC", "MBCN",
            "MBII", "MBIN", "MBIO", "MBI", "MBOT", "MBRX", "MBSC", "MBTC", "MBUU", "MBWM",
            "MC", "MCA", "MCAA", "MCB", "MCBC", "MCBS", "MCD", "MCF", "MCFT", "MCHP",
            "MCHX", "MCI", "MCK", "MCMJ", "MCN", "MCO", "MCR", "MCRB", "MCRI", "MCS",
            "MCW", "MCY", "MD", "MDB", "MDC", "MDGL", "MDGS", "MDH", "MDIA", "MDIV",
            "MDJH", "MDL", "MDLZ", "MDNA", "MDRR", "MDRX", "MDT", "MDU", "MDWD", "MDXG",
            "MDXH", "ME", "MEC", "MED", "MEDP", "MEDS", "MEG", "MEGI", "MEI", "MEIP",
            "MEKA", "MELI", "MEM", "MEOH", "MER", "MERC", "MESA", "MESO", "MET", "META",
            "METF", "METX", "MEXX", "MF", "MFA", "MFC", "MFD", "MFG", "MFGP", "MFH",
            "MFIC", "MFIN", "MFM", "MFMS", "MFNC", "MFSF", "MFT", "MFV", "MG", "MGA",
            "MGEE", "MGEN", "MGI", "MGIC", "MGK", "MGLD", "MGM", "MGNI", "MGNX", "MGP",
            "MGPI", "MGR", "MGRB", "MGRC", "MGRI", "MGRM", "MGS", "MGTA", "MGTX", "MGY",
            "MGYR", "MHD", "MHF", "MHH", "MHI", "MHK", "MHLA", "MHLD", "MHN", "MHNC",
            "MHO", "MHP", "MHR", "MHS", "MHT", "MHY", "MI", "MICT", "MIDD", "MIDU",
            "MIE", "MIGI", "MII", "MILN", "MIMO", "MINT", "MIR", "MIRM", "MIST", "MIT",
            "MITK", "MITT", "MIXT", "MIY", "MJO", "MKAM", "MKC", "MKD", "MKL", "MKOR",
            "MKSI", "MKTW", "MKTX", "ML", "MLAB", "MLAC", "MLCO", "MLI", "MLKN", "MLM",
            "MLNK", "MLP", "MLR", "MLSS", "MLTX", "MLVF", "MMAT", "MMC", "MMD", "MMI",
            "MMLP", "MMM", "MMMB", "MMP", "MMS", "MMSI", "MMT", "MMU", "MMX", "MN",
            "MNDO", "MNDT", "MNE", "MNKD", "MNMD", "MNN", "MNOV", "MNP", "MNPR", "MNRL",
            "MNSB", "MNST", "MNTS", "MNTX", "MO", "MOBQ", "MOBV", "MOB", "MOD", "MODG",
            "MODN", "MODV", "MOFG", "MOGO", "MOGU", "MOH", "MOLN", "MOMO", "MOO", "MOR",
            "MORF", "MORN", "MOS", "MOSS", "MOT", "MOTS", "MOV", "MOVE", "MP", "MPA",
            "MPAA", "MPB", "MPC", "MPLN", "MPLX", "MPW", "MPWR", "MPX", "MQ", "MRAI",
            "MRAM", "MRBK", "MRC", "MRCC", "MRCY", "MREO", "MRIN", "MRK", "MRKR", "MRM",
            "MRNA", "MRNS", "MRO", "MRSN", "MRTN", "MRTX", "MRUS", "MRVI", "MRVL", "MS",
            "MSA", "MSB", "MSBI", "MSC", "MSCI", "MSD", "MSDA", "MSEX", "MSFT", "MSGE",
            "MSGM", "MSGS", "MSI", "MSM", "MSN", "MSP", "MSSA", "MSSS", "MSTR", "MSVX",
            "MT", "MTA", "MTAC", "MTB", "MTBC", "MTC", "MTCH", "MTCR", "MTD", "MTDR",
            "MTEK", "MTEM", "MTEX", "MTG", "MTH", "MTL", "MTLS", "MTN", "MTNB", "MTOR",
            "MTP", "MTR", "MTRN", "MTRX", "MTSI", "MTTR", "MTW", "MTX", "MTZ", "MU",
            "MUA", "MUB", "MUC", "MUE", "MUFG", "MUI", "MUJ", "MULN", "MUN", "MUR",
            "MUSA", "MUSI", "MUST", "MUX", "MVBF", "MVF", "MVI", "MVIS", "MVST", "MVT",
            "MWA", "MX", "MXC", "MXCT", "MXE", "MXF", "MXL", "MYD", "MYE", "MYFW",
            "MYGN", "MYI", "MYMD", "MYN", "MYNA", "MYNZ", "MYO", "MYOV", "MYPS", "MYRG",
            "MYSZ", "MYTE", "NA", "NAAC", "NAAS", "NABL", "NAC", "NAD", "NAII", "NAK",
            "NAN", "NANR", "NAOV", "NAPA", "NARI", "NAT", "NATH", "NATI", "NATR", "NAUT",
            "NAVB", "NAVI", "NBR", "NBRV", "NBSE", "NBST", "NBXG", "NC", "NCA", "NCAC",
            "NCBS", "NCL", "NCLH", "NCMI", "NCNA", "NCNO", "NCPB", "NCPL", "NCR", "NCSM",
            "NCTY", "NCV", "NCZ", "NDAC", "NDAQ", "NDLS", "NDMO", "NDP", "NDRA", "NDSN",
            "NE", "NEA", "NEE", "NEGG", "NEM", "NEN", "NEO", "NEOG", "NEON", "NEOV",
            "NEP", "NEPH", "NEPT", "NERV", "NESR", "NET", "NETC", "NETI", "NETL", "NEU",
            "NEUE", "NEV", "NEW", "NEWP", "NEWT", "NEX", "NEXI", "NEXN", "NEXT", "NFBK",
            "NFE", "NFG", "NFGC", "NFLX", "NFTG", "NFYS", "NG", "NGC", "NGD", "NGE",
            "NGG", "NGL", "NGS", "NGVC", "NGVT", "NH", "NHC", "NHI", "NHIC", "NHLD",
            "NHS", "NHTC", "NI", "NICE", "NICK", "NID", "NIE", "NIM", "NIO", "NIU",
            "NJAN", "NJUL", "NKE", "NKLA", "NKSH", "NKTR", "NKTX", "NL", "NLIT", "NLOK",
            "NLR", "NLS", "NLSN", "NLSP", "NLTX", "NLY", "NM", "NMAI", "NMCO", "NMD",
            "NMFC", "NMG", "NMI", "NMIH", "NMIV", "NML", "NMM", "NMR", "NMRD", "NMRK",
            "NMS", "NMT", "NMTC", "NMZ", "NN", "NNA", "NNBR", "NNDM", "NNE", "NNI",
            "NNN", "NNOX", "NNVC", "NOA", "NOAC", "NOAH", "NOBL", "NOC", "NODK", "NOG",
            "NOK", "NOM", "NOMD", "NORW", "NOTV", "NOV", "NOVA", "NOVN", "NOVT", "NOVV",
            "NOVZ", "NPAB", "NPCT", "NPFD", "NPK", "NPO", "NPPC", "NPTN", "NPV", "NQP",
            "NR", "NRAC", "NRBO", "NRC", "NRCG", "NRDS", "NRDY", "NREF", "NRG", "NRGV",
            "NRIM", "NRIX", "NRK", "NRO", "NRP", "NRSN", "NRT", "NRUC", "NRXP", "NS",
            "NSA", "NSC", "NSEC", "NSIT", "NSP", "NSPR", "NSSC", "NSTC", "NSTG", "NSTS",
            "NSYS", "NTAP", "NTB", "NTBL", "NTCO", "NTCT", "NTES", "NTEST", "NTGR", "NTIC",
            "NTIP", "NTLA", "NTNX", "NTR", "NTRB", "NTRP", "NTRS", "NTSX", "NTUS", "NTWK",
            "NU", "NUBI", "NUE", "NUGO", "NULG", "NULV", "NUM", "NUO", "NUS", "NUSC",
            "NUV", "NUVA", "NUVB", "NUVL", "NUW", "NUWE", "NUZE", "NVAX", "NVCN", "NVCR",
            "NVCT", "NVDA", "NVEC", "NVEE", "NVEI", "NVET", "NVGS", "NVIV", "NVMI", "NVNO",
            "NVO", "NVOS", "NVRO", "NVR", "NVRI", "NVRO", "NVSA", "NVST", "NVT", "NVTA",
            "NVTS", "NVVE", "NVX", "NWBI", "NWE", "NWFL", "NWG", "NWL", "NWLI", "NWN",
            "NWPX", "NWS", "NWSA", "NX", "NXC", "NXDT", "NXE", "NXGL", "NXGN", "NXI",
            "NXJ", "NXN", "NXP", "NXPL", "NXRT", "NXST", "NXT", "NXTC", "NXTG", "NYC",
            "NYCB", "NYMT", "NYMX", "NYT", "NYXH", "NZF", "O", "OACB", "OAKU", "OAS",
            "OASP", "OAS", "OB", "OBCI", "OBE", "OBIO", "OBLG", "OBNK", "OBSV", "OC",
            "OCC", "OCCI", "OCDX", "OCFC", "OCG", "OCN", "OCSL", "OCUL", "OCUP", "OCX",
            "ODC", "ODFL", "ODP", "OEC", "OESX", "OFED", "OFG", "OFIX", "OFLX", "OFS",
            "OG", "OGE", "OGI", "OGN", "OGS", "OHI", "OI", "OII", "OIIM", "OIS",
            "OKE", "OKTA", "OLB", "OLED", "OLK", "OLLI", "OLMA", "OLN", "OLO", "OLP",
            "OLPX", "OM", "OMAB", "OMC", "OMCL", "OMER", "OMEX", "OMF", "OMGA", "OMI",
            "OMIC", "OMQS", "ON", "ONB", "ONCR", "ONCS", "ONCT", "ONCY", "ONE", "ONEO",
            "ONEW", "ONL", "ONON", "ONTF", "ONTO", "ONTX", "ONVO", "OOMA", "OP", "OPAD",
            "OPAL", "OPBK", "OPCH", "OPEN", "OPFI", "OPHC", "OPI", "OPINL", "OPK", "OPNT",
            "OPOF", "OPRA", "OPRT", "OPRX", "OPT", "OPTN", "OPTT", "OPY", "OR", "ORA",
            "ORAN", "ORC", "ORCC", "ORCL", "ORGN", "ORGO", "ORGS", "ORI", "ORIC", "ORLA",
            "ORLY", "ORMP", "ORN", "ORRF", "ORTX", "OSBC", "OSCR", "OSG", "OSIS", "OSK",
            "OSPN", "OSS", "OST", "OSTK", "OSUR", "OSW", "OTEX", "OTIC", "OTIS", "OTLK",
            "OTLY", "OTRK", "OTTR", "OUST", "OUT", "OVBC", "OVID", "OVV", "OWL", "OWLT",
            "OXAC", "OXBR", "OXFD", "OXLC", "OXM", "OXSQ", "OXY", "OYST", "OZK", "OZON",
            "P", "PAAS", "PAC", "PACB", "PACW", "PACK", "PAGS", "PAHC", "PAL", "PALI",
            "PALL", "PALT", "PAM", "PANL", "PANW", "PAPL", "PAR", "PARA", "PARAA", "PARR",
            "PASG", "PATH", "PATK", "PAVM", "PAX", "PAY", "PAYC", "PAYO", "PAYS", "PB",
            "PBA", "PBBK", "PBD", "PBE", "PBFS", "PBH", "PBHC", "PBI", "PBJ", "PBLA",
            "PBPB", "PBR", "PBS", "PBSV", "PBT", "PBTP", "PBW", "PCAR", "PCB", "PCBK",
            "PCCW", "PCEF", "PCG", "PCH", "PCI", "PCK", "PCM", "PCN", "PCQ", "PCRX",
            "PCSB", "PCT", "PCTI", "PCTY", "PCVX", "PCYG", "PCYO", "PD", "PDBC", "PDCO",
            "PDD", "PDEX", "PDFS", "PDI", "PDLB", "PDM", "PDN", "PDO", "PDP", "PDS",
            "PDSB", "PDT", "PEAK", "PEB", "PEBK", "PEBO", "PECO", "PED", "PEG", "PEGA",
            "PEGR", "PEGY", "PEJ", "PEN", "PENN", "PEO", "PEP", "PEPL", "PERF", "PERI",
            "PESI", "PETQ", "PETS", "PETZ", "PEY", "PEZ", "PFBC", "PFC", "PFD", "PFE",
            "PFF", "PFFA", "PFFD", "PFFL", "PFFR", "PFFV", "PFG", "PFGC", "PFH", "PFI",
            "PFIE", "PFIN", "PFIS", "PFL", "PFLT", "PFM", "PFMT", "PFN", "PFO", "PFSA",
            "PFSI", "PFS", "PFSW", "PG", "PGC", "PGEN", "PGNY", "PGR", "PGRE", "PGRW",
            "PGTI", "PGX", "PH", "PHAR", "PHAS", "PHAT", "PHB", "PHCF", "PHD", "PHDG",
            "PHG", "PHGE", "PHI", "PHIO", "PHK", "PHM", "PHO", "PHR", "PHUN", "PHVS",
            "PI", "PIAI", "PIC", "PICK", "PICO", "PII", "PILL", "PIM", "PIN", "PINC",
            "PINE", "PINK", "PINS", "PIPR", "PIRS", "PIXY", "PIZ", "PJT", "PK", "PKB",
            "PKBK", "PKE", "PKG", "PKI", "PKOH", "PKST", "PKX", "PL", "PLAB", "PLAG",
            "PLAN", "PLAY", "PLBC", "PLBY", "PLCE", "PLD", "PLG", "PLL", "PLM", "PLMR",
            "PLNT", "PLOW", "PLRX", "PLSE", "PLTK", "PLTR", "PLUG", "PLUS", "PLX", "PLXP",
            "PLXS", "PLYA", "PM", "PMCB", "PMD", "PME", "PMF", "PML", "PMM", "PMO",
            "PMT", "PMTS", "PMVP", "PMX", "PNBK", "PNC", "PNFP", "PNI", "PNM", "PNNT",
            "PNR", "PNRG", "PNST", "PNT", "PNTG", "PNTM", "PNW", "POAI", "PODD", "POET",
            "POL", "POLA", "POOL", "POR", "PORT", "POST", "POTX", "POW", "POWI", "POWL",
            "POWW", "PPBI", "PPBT", "PPC", "PPG", "PPGH", "PPHP", "PPIH", "PPL", "PPSI",
            "PPT", "PPTA", "PPX", "PQG", "PQIN", "PR", "PRA", "PRAA", "PRAX", "PRB",
            "PRCH", "PRCT", "PRDO", "PRDS", "PRE", "PRFT", "PRFX", "PRG", "PRGO", "PRGS",
            "PRI", "PRIM", "PRK", "PRLB", "PRLD", "PRLH", "PRM", "PRMW", "PRN", "PRO",
            "PROC", "PROF", "PROK", "PROV", "PRPB", "PRPH", "PRPL", "PRPO", "PRQR", "PRS",
            "PRT", "PRTA", "PRTC", "PRTG", "PRTH", "PRTS", "PRTY", "PRU", "PRVA", "PRVB",
            "PSA", "PSB", "PSC", "PSCC", "PSCD", "PSCE", "PSCF", "PSCH", "PSCI", "PSCT",
            "PSEC", "PSF", "PSFE", "PSI", "PSJ", "PSL", "PSLV", "PSMB", "PSMC", "PSMD",
            "PSMG", "PSMM", "PSMT", "PSN", "PSNL", "PSO", "PST", "PSTG", "PSTL", "PSTP",
            "PSTX", "PSX", "PSXP", "PT", "PTC", "PTCT", "PTE", "PTEN", "PTF", "PTGX",
            "PTH", "PTIC", "PTIX", "PTLC", "PTLO", "PTMN", "PTN", "PTNR", "PTON", "PTPI",
            "PTR", "PTRA", "PTRS", "PTSI", "PTVE", "PTWO", "PUBM", "PUCK", "PULM", "PUMP",
            "PUNK", "PURE", "PURI", "PUYI", "PV", "PVBC", "PVG", "PVH", "PVL", "PW",
            "PWFL", "PWOD", "PWP", "PWR", "PWS", "PWSC", "PYCR", "PYPD", "PYPL", "PYT",
            "PYX", "PZC", "PZG", "PZN", "PZZA", "QABA", "QAT", "QBTS", "QCLN", "QCOM",
            "QCRH", "QD", "QDEL", "QDEV", "QEFA", "QEMA", "QEP", "QEPC", "QEMM", "QES",
            "QETF", "QFIN", "QGEN", "QGRO", "QH", "QHY", "QID", "QINT", "QIPT", "QK",
            "QLC", "QLD", "QLGN", "QLI", "QLTA", "QLV", "QMAR", "QMCO", "QMN", "QMOM",
            "QNST", "QNRX", "QNT", "QNTA", "QNTM", "QNWG", "QOCT", "QOM", "QQQ", "QQQA",
            "QQQE", "QQQG", "QQQJ", "QQQM", "QQQX", "QQXT", "QRHC", "QRTEA", "QRTEB", "QRTEP",
            "QRVO", "QS", "QSI", "QSR", "QSWN", "QTEC", "QTNT", "QTRX", "QTT", "QTUM",
            "QUAD", "QUAL", "QUIK", "QULL", "QURE", "QUS", "QVAL", "QVCC", "QVCD", "QWLD",
            "R", "RA", "RACE", "RAD", "RADA", "RAIL", "RAMP", "RAND", "RAPT", "RARE",
            "RARR", "RAS", "RAVE", "RAVI", "RBBN", "RBC", "RBCAA", "RBCN", "RBKB", "RBLX",
            "RBNC", "RBOT", "RC", "RCAT", "RCEL", "RCFA", "RCHG", "RCI", "RCII", "RCKT",
            "RCKY", "RCL", "RCLF", "RCM", "RCMT", "RCON", "RCRT", "RCS", "RCUS", "RDBX",
            "RDCM", "RDFN", "RDN", "RDNT", "RDUS", "RDVT", "RDW", "RDWR", "RDY", "RE",
            "REAL", "REAX", "REDU", "REED", "REET", "REFR", "REG", "REGN", "REI", "REIT",
            "REKR", "RELI", "RELL", "RELX", "RELY", "RENN", "RENT", "REPH", "REPL", "RES",
            "RETA", "RETO", "REV", "REVB", "REVG", "REVH", "REX", "REXR", "REYN", "RF",
            "RFAC", "RFDA", "RFEM", "RFEU", "RFIL", "RFL", "RFM", "RFMZ", "RFP", "RFUN",
            "RGA", "RGC", "RGCO", "RGEN", "RGF", "RGI", "RGLD", "RGLS", "RGNX", "RGP",
            "RGR", "RGS", "RGT", "RGTI", "RH", "RHE", "RHI", "RHP", "RHRX", "RIBT",
            "RICK", "RIDE", "RIG", "RIGL", "RILY", "RILYG", "RILYK", "RILYL", "RILYM", "RILYN",
            "RILYO", "RILYP", "RILYT", "RILYZ", "RINF", "RING", "RIO", "RIOT", "RIV", "RIVN",
            "RJF", "RKLB", "RKLY", "RKT", "RL", "RLAY", "RLGT", "RLGY", "RLI", "RLJ",
            "RLMD", "RLX", "RM", "RMAX", "RMBI", "RMBL", "RMBS", "RMCF", "RMGC", "RMI",
            "RMM", "RMP", "RMR", "RMRM", "RMT", "RMTI", "RNDV", "RNG", "RNGR", "RNLC",
            "RNLX", "RNP", "RNR", "RNST", "RNW", "RNWK", "RNXT", "ROAD", "ROCK", "ROCL",
            "ROG", "ROIC", "ROIV", "ROK", "ROKU", "ROL", "ROLL", "ROM", "ROOT", "ROP",
            "ROST", "ROVR", "RPAY", "RPD", "RPHM", "RPM", "RPRX", "RPT", "RPTX", "RQI",
            "RRAC", "RRC", "RRD", "RRGB", "RRR", "RS", "RSG", "RSI", "RSKD", "RSLS",
            "RSSS", "RSVR", "RSX", "RTX", "RUBY", "RUN", "RUSHA", "RUSHB", "RUTH", "RVAC",
            "RVLP", "RVLV", "RVMD", "RVNC", "RVP", "RVPH", "RVSB", "RVT", "RVTY", "RW",
            "RWL", "RWLK", "RWT", "RXDX", "RXRX", "RXST", "RXT", "RY", "RYAAY", "RYAM",
            "RYAN", "RYB", "RYI", "RYJ", "RYN", "RZLT", "S", "SA", "SABR", "SABS",
            "SACH", "SAFE", "SAFM", "SAFT", "SAGE", "SAH", "SAIA", "SAIC", "SAIL", "SAL",
            "SALM", "SAM", "SAMG", "SAN", "SANA", "SAND", "SANM", "SANW", "SAP", "SAR",
            "SASR", "SAT", "SATS", "SAVA", "SAVE", "SB", "SBAC", "SBBA", "SBE", "SBEV",
            "SBFG", "SBFM", "SBI", "SBIO", "SBLK", "SBNY", "SBOW", "SBR", "SBRA", "SBS",
            "SBSI", "SBT", "SBUX", "SC", "SCCO", "SCD", "SCE", "SCE", "SCHL", "SCHN",
            "SCHP", "SCHV", "SCHW", "SCI", "SCKT", "SCL", "SCLE", "SCM", "SCOR", "SCPH",
            "SCPL", "SCS", "SCSC", "SCU", "SCVL", "SCWO", "SCWX", "SCX", "SCYX", "SD",
            "SDAC", "SDC", "SDGR", "SDHC", "SDIG", "SDPI", "SDRL", "SDY", "SE", "SEAC",
            "SEAS", "SEAT", "SECO", "SEDG", "SEE", "SEED", "SEEL", "SEER", "SEIC", "SELB",
            "SELF", "SEM", "SEMR", "SENEA", "SENEB", "SENS", "SERA", "SES", "SESN", "SES",
            "SF", "SFBC", "SFBS", "SFET", "SFIX", "SFL", "SFLM", "SFM", "SFNC", "SFST",
            "SFT", "SGA", "SGBX", "SGC", "SGD", "SGEN", "SGH", "SGLY", "SGMA", "SGML",
            "SGMO", "SGRP", "SGRY", "SGU", "SH", "SHBI", "SHC", "SHCR", "SHE", "SHEN",
            "SHG", "SHI", "SHIP", "SHLS", "SHO", "SHOO", "SHOP", "SHPW", "SHUA", "SHW",
            "SHYF", "SI", "SIAF", "SID", "SIEB", "SIEN", "SIF", "SIG", "SIGA", "SIGI",
            "SII", "SIL", "SILC", "SILK", "SILV", "SIM", "SIMO", "SINT", "SIRI", "SITC",
            "SITE", "SITM", "SIVB", "SIX", "SJ", "SJI", "SJIJ", "SJIV", "SJM", "SJNK",
            "SJT", "SJW", "SK", "SKIL", "SKIN", "SKLZ", "SKM", "SKOR", "SKT", "SKX",
            "SKY", "SKYA", "SKYH", "SKYT", "SKYW", "SLAB", "SLAC", "SLAM", "SLB", "SLCA",
            "SLDB", "SLDP", "SLF", "SLG", "SLGC", "SLGG", "SLGL", "SLGN", "SLI", "SLM",
            "SLN", "SLNG", "SLNH", "SLNO", "SLP", "SLQT", "SLRC", "SLRX", "SLS", "SLVM",
            "SM", "SMAR", "SMBC", "SMBK", "SMCI", "SMCP", "SMED", "SMFG", "SMG", "SMHI",
            "SMID", "SMI", "SMIT", "SMLP", "SMLR", "SMM", "SMMF", "SMMT", "SMP", "SMPL",
            "SMR", "SMRT", "SMSI", "SMTC", "SMTI", "SMTS", "SMURF", "SMWB", "SNA", "SNAK",
            "SNAP", "SND", "SNDL", "SNDX", "SNES", "SNEX", "SNFCA", "SNGX", "SNN", "SNOA",
            "SNOW", "SNP", "SNPO", "SNPS", "SNPX", "SNRH", "SNSE", "SNV", "SNX", "SNY",
            "SO", "SOAR", "SOBR", "SOC", "SOFI", "SOFO", "SOG", "SOHO", "SOHOB", "SOHON",
            "SOHOO", "SOHU", "SOI", "SOIL", "SOL", "SOLO", "SON", "SOND", "SONM", "SONN",
            "SONO", "SONY", "SOPA", "SOR", "SOS", "SOTK", "SOUN", "SOVO", "SP", "SPAB",
            "SPB", "SPCB", "SPCE", "SPCM", "SPD", "SPE", "SPEM", "SPEU", "SPFI", "SPG",
            "SPGI", "SPGM", "SPH", "SPHB", "SPHD", "SPHQ", "SPHY", "SPI", "SPIB", "SPIP",
            "SPIR", "SPK", "SPKB", "SPLG", "SPLK", "SPLV", "SPMD", "SPNS", "SPNT", "SPOK",
            "SPOT", "SPPI", "SPR", "SPRB", "SPRC", "SPRO", "SPRX", "SPRY", "SPSC", "SPT",
            "SPTI", "SPTN", "SPTS", "SPWH", "SPWR", "SPXC", "SPXX", "SQ", "SQFT", "SQFTP",
            "SQL", "SQLL", "SQM", "SQNS", "SQSP", "SR", "SRAD", "SRAX", "SRC", "SRCE",
            "SRCL", "SRDX", "SRE", "SREA", "SRET", "SRG", "SRGA", "SRI", "SRL", "SRNE",
            "SRNG", "SRPT", "SRRA", "SRRK", "SRSA", "SRSR", "SRT", "SRTS", "SRTY", "SRZN",
            "SSAA", "SSB", "SSBI", "SSBK", "SSD", "SSIC", "SSKN", "SSL", "SSNC", "SSNT",
            "SSP", "SSRM", "SSSS", "SST", "SSTI", "SSTK", "SSY", "SSYS", "ST", "STAA",
            "STAB", "STAF", "STAG", "STAR", "STBA", "STC", "STCN", "STE", "STEM", "STEP",
            "STER", "STET", "STG", "STGW", "STIM", "STK", "STKL", "STKS", "STLA", "STLD",
            "STLK", "STM", "STMP", "STN", "STNE", "STNG", "STOK", "STON", "STOR", "STP",
            "STPC", "STRA", "STRL", "STRM", "STRN", "STRO", "STRR", "STRS", "STRT", "STSA",
            "STSS", "STT", "STTK", "STVN", "STWD", "STX", "STXS", "STZ", "SU", "SUAC",
            "SUI", "SUM", "SUMO", "SUN", "SUNL", "SUNW", "SUP", "SUPN", "SUPV", "SURF",
            "SURG", "SUZ", "SVC", "SVFA", "SVFD", "SVM", "SVRA", "SVRE", "SVS", "SVT",
            "SVVC", "SWAG", "SWAN", "SWAR", "SWAV", "SWBI", "SWCH", "SWET", "SWI", "SWIM",
            "SWIR", "SWK", "SWKH", "SWKS", "SWM", "SWN", "SWSS", "SWTX", "SWVL", "SWX",
            "SWZ", "SXC", "SXI", "SXTC", "SXT", "SXTP", "SY", "SYBX", "SYF", "SYK",
            "SYN", "SYNA", "SYNH", "SYNL", "SYPR", "SYRS", "SYTA", "SYX", "SYY", "SZC",
            "SZNE", "T", "TA", "TAC", "TACT", "TAIT", "TAK", "TAL", "TALK", "TALO",
            "TAN", "TANNI", "TANNL", "TANNZ", "TAOP", "TAP", "TARO", "TARS", "TAST", "TAT",
            "TATT", "TAYD", "TBB", "TBBK", "TBC", "TBD", "TBI", "TBIO", "TBK", "TBLA",
            "TBLT", "TBNK", "TBPH", "TBRG", "TBSA", "TC", "TCBC", "TCBI", "TCBIO", "TCBK",
            "TCBS", "TCCO", "TCI", "TCMD", "TCN", "TCOM", "TCPC", "TCRR", "TCRT", "TCRX",
            "TCS", "TCVA", "TD", "TDC", "TDCX", "TDF", "TDG", "TDS", "TDUP", "TDW",
            "TDY", "TEAF", "TEAM", "TECH", "TECTP", "TEDU", "TEF", "TEI", "TEL", "TELA",
            "TELZ", "TEN", "TENB", "TENX", "TEO", "TER", "TERP", "TESS", "TFC", "TFF",
            "TFII", "TFIN", "TFSA", "TFSL", "TFX", "TG", "TGAA", "TGAN", "TGC", "TGEN",
            "TGLS", "TGN", "TGP", "TGS", "TGT", "TGTX", "TGVC", "TH", "THC", "THCH",
            "THCP", "THFF", "THG", "THM", "THO", "THQ", "THR", "THRM", "THRN", "THRX",
            "THS", "THTX", "THW", "TI", "TIG", "TIGO", "TIGR", "TIIX", "TIL", "TILE",
            "TIMB", "TINV", "TIOA", "TIPT", "TIRX", "TISI", "TITN", "TIVC", "TIXT", "TJX",
            "TK", "TKAT", "TKC", "TKLF", "TKNO", "TKR", "TLGA", "TLGY", "TLH", "TLIS",
            "TLK", "TLMD", "TLRY", "TLS", "TLSA", "TLT", "TLYS", "TM", "TMC", "TMCI",
            "TMDX", "TME", "TMHC", "TMKR", "TMO", "TMP", "TMPM", "TMQ", "TMST", "TMT",
            "TMUS", "TMX", "TNC", "TNDM", "TNET", "TNGX", "TNK", "TNL", "TNP", "TNXP",
            "TNYA", "TOI", "TOL", "TOMZ", "TOON", "TOP", "TOPS", "TORC", "TORO", "TOT",
            "TOTA", "TOTL", "TOUR", "TOWN", "TPB", "TPC", "TPG", "TPH", "TPHS", "TPIC",
            "TPR", "TPST", "TPTA", "TPVG", "TPX", "TPZ", "TR", "TRAK", "TRC", "TRCA",
            "TRDA", "TRDG", "TREE", "TREX", "TRGP", "TRHC", "TRI", "TRIB", "TRIN", "TRIP",
            "TRIS", "TRKA", "TRMB", "TRMD", "TRMK", "TRMR", "TRN", "TRNO", "TRNS", "TRON",
            "TROO", "TROW", "TROX", "TRP", "TRS", "TRST", "TRT", "TRTX", "TRU", "TRUE",
            "TRUP", "TRV", "TRVG", "TRVI", "TRVN", "TRX", "TS", "TSAT", "TSBK", "TSCO",
            "TSE", "TSEM", "TSHA", "TSI", "TSIB", "TSLA", "TSLX", "TSM", "TSN", "TSQ",
            "TSRI", "TSVT", "TT", "TTC", "TTCF", "TTD", "TTE", "TTEC", "TTEK", "TTGT",
            "TTI", "TTM", "TTMI", "TTNP", "TTOO", "TTP", "TTSH", "TTWO", "TU", "TUP",
            "TUR", "TURN", "TUSA", "TUSK", "TUYA", "TV", "TVC", "TVE", "TVTX", "TW",
            "TWB", "TWC", "TWCB", "TWIN", "TWKS", "TWLO", "TWLV", "TWLVU", "TWND", "TWNK",
            "TWOU", "TWST", "TWT", "TWTR", "TX", "TXG", "TXMD", "TXN", "TXRH", "TXT",
            "TY", "TYD", "TYG", "TYL", "TYME", "TYRA", "TZOO", "U", "UA", "UAA",
            "UAL", "UAMY", "UAN", "UAPR", "UAVS", "UBA", "UBCP", "UBER", "UBFO", "UBOH",
            "UBOT", "UBP", "UBS", "UBSI", "UBX", "UCBI", "UCBIO", "UCC", "UCL", "UCO",
            "UCON", "UCTT", "UDN", "UDOW", "UDR", "UE", "UEC", "UEIC", "UEVM", "UFAB",
            "UFCS", "UFI", "UFO", "UFPI", "UFPT", "UFS", "UG", "UGI", "UGP", "UGRO",
            "UHAL", "UHS", "UHT", "UI", "UIS", "UK", "UL", "ULBI", "ULCC", "ULE",
            "ULH", "ULST", "ULTA", "UMBF", "UMC", "UMDD", "UMH", "UMI", "UMPQ", "UNAM",
            "UNB", "UNCY", "UNF", "UNFI", "UNH", "UNIT", "UNL", "UNM", "UNMA", "UNP",
            "UNTY", "UONE", "UONEK", "UP", "UPAR", "UPC", "UPH", "UPLD", "UPS", "UPST",
            "UPTD", "UPW", "UPWK", "URA", "URBN", "URE", "URG", "URGN", "URI", "UROY",
            "USA", "USAC", "USAI", "USAP", "USAS", "USAU", "USB", "USCB", "USCI", "USCT",
            "USDU", "USEA", "USEG", "USFD", "USGO", "USIO", "USLM", "USM", "USMC", "USMF",
            "USMI", "USMV", "USOI", "USPH", "USRT", "UST", "USVM", "USX", "UTAA", "UTEN",
            "UTES", "UTF", "UTG", "UTHR", "UTI", "UTL", "UTMD", "UTME", "UTRS", "UTSI",
            "UTZ", "UUA", "UUP", "UUU", "UVE", "UVSP", "UVV", "UWMC", "UXIN", "UYLD",
            "UZA", "UZB", "V", "VABK", "VAC", "VACC", "VAL", "VALE", "VALN", "VALU",
            "VAMO", "VAPO", "VAQC", "VATE", "VAW", "VB", "VBF", "VBFC", "VBIV", "VBLT",
            "VBND", "VBNK", "VBR", "VBTX", "VC", "VCEL", "VCIF", "VCIT", "VCLT", "VCNX",
            "VCSA", "VCSH", "VCTR", "VCV", "VCXA", "VCXB", "VCYT", "VEC", "VECO", "VEDU",
            "VEEE", "VEEV", "VEL", "VENA", "VENB", "VENC", "VEND", "VENE", "VENF", "VENG",
            "VENI", "VENU", "VEON", "VERA", "VERB", "VERC", "VERF", "VERI", "VERO", "VERU",
            "VERV", "VERX", "VET", "VEV", "VFC", "VFF", "VG", "VGI", "VGIT", "VGLT",
            "VGM", "VGSH", "VGT", "VGZ", "VHAI", "VHC", "VHI", "VHNA", "VHNI", "VIA",
            "VIAC", "VIACA", "VIAV", "VICI", "VICR", "VIEW", "VIG", "VIGI", "VINC", "VINO",
            "VINP", "VIOT", "VIPS", "VIR", "VIRC", "VIRI", "VIRT", "VIRX", "VIS", "VISL",
            "VIST", "VITL", "VIV", "VIVE", "VIVK", "VIXM", "VIXY", "VJET", "VKI", "VKQ",
            "VKTX", "VLAT", "VLDR", "VLEE", "VLGEA", "VLN", "VLNS", "VLO", "VLON", "VLRS",
            "VLS", "VLY", "VLYPO", "VLYPP", "VMAR", "VMC", "VMCA", "VMD", "VMEO", "VMI",
            "VMO", "VMW", "VNCE", "VNDA", "VNET", "VNO", "VNOM", "VNRX", "VNT", "VNTR",
            "VOC", "VOD", "VOLT", "VOR", "VORB", "VOX", "VOXX", "VOYA", "VPG", "VPV",
            "VRA", "VRAI", "VRAR", "VRAY", "VRCA", "VRDN", "VRE", "VREX", "VRM", "VRME",
            "VRNS", "VRNT", "VRPX", "VRRM", "VRS", "VRSK", "VRSN", "VRTS", "VRTX", "VS",
            "VSAC", "VSAT", "VSCO", "VSDA", "VSEC", "VSH", "VSHG", "VSI", "VSLU", "VSMV",
            "VSPY", "VSS", "VST", "VSTA", "VSTM", "VSTO", "VTA", "VTEX", "VTGN", "VTHR",
            "VTI", "VTIP", "VTIQ", "VTN", "VTNR", "VTR", "VTRS", "VTSI", "VTV", "VTVT",
            "VTWG", "VTWO", "VTWV", "VTYX", "VUG", "VUSE", "VUZI", "VV", "VVI", "VVOS",
            "VVPR", "VVV", "VWOB", "VXRT", "VXUS", "VYGG", "VYGR", "VYNE", "VYNT", "VYMI",
            "VZ", "VZIO", "VZLA", "W", "WAB", "WABC", "WAFD", "WAFDP", "WAFU", "WAL",
            "WALD", "WANT", "WAR", "WASH", "WAT", "WATT", "WBA", "WBD", "WBS", "WBX",
            "WCC", "WCFB", "WCN", "WD", "WDAY", "WDC", "WDFC", "WDH", "WDI", "WDS",
            "WE", "WEA", "WEAT", "WEBL", "WEBS", "WEC", "WEI", "WEJL", "WEJS", "WEL",
            "WEN", "WERN", "WES", "WETF", "WEX", "WEYS", "WF", "WFC", "WFCF", "WFE",
            "WFRD", "WGO", "WGS", "WH", "WHD", "WHF", "WHG", "WHLM", "WHLR", "WHR",
            "WIA", "WILC", "WIMI", "WINA", "WING", "WINT", "WINV", "WIP", "WIRE", "WISA",
            "WISH", "WIW", "WIX", "WK", "WKEY", "WKHS", "WKSP", "WLDN", "WLFC", "WLK",
            "WLKP", "WLY", "WLYB", "WM", "WMB", "WMC", "WMG", "WMK", "WMPN", "WMS",
            "WMT", "WNC", "WNEB", "WNNR", "WNS", "WNW", "WOOD", "WOOF", "WOR", "WORK",
            "WORX", "WOW", "WPC", "WPCA", "WPM", "WPP", "WPRT", "WPS", "WRB", "WRE",
            "WRK", "WRLD", "WRN", "WSBC", "WSBCP", "WSBF", "WSC", "WSFS", "WSM", "WSO",
            "WSR", "WST", "WSTG", "WT", "WTBA", "WTER", "WTFC", "WTFCM", "WTFCP", "WTMA",
            "WTRG", "WTS", "WTT", "WTTR", "WU", "WULF", "WVE", "WVVI", "WW", "WWAC",
            "WWD", "WWE", "WWW", "WY", "WYNN", "WYY", "X", "XAIR", "XB", "XBI",
            "XBIO", "XBIT", "XCUR", "XEL", "XELA", "XELB", "XENE", "XENT", "XERS", "XFIN",
            "XFLT", "XFOR", "XGN", "XHR", "XIN", "XLB", "XLC", "XLE", "XLF", "XLG",
            "XLI", "XLK", "XLO", "XLP", "XLRE", "XLU", "XLV", "XLY", "XM", "XME",
            "XMHQ", "XMMO", "XMPT", "XMTR", "XNET", "XNTK", "XOM", "XONE", "XOS", "XPER",
            "XPL", "XPO", "XPOA", "XPRO", "XRAY", "XRT", "XRX", "XSD", "XSHD", "XSHQ",
            "XSLV", "XSOE", "XSPA", "XT", "XTL", "XTNT", "XTR", "XVV", "XXII", "XYF",
            "XYL", "Y", "YALA", "YANG", "YELP", "YETI", "YEXT", "YGMZ", "YI", "YINN",
            "YJ", "YLD", "YMAB", "YMTX", "YNDX", "YORW", "YOSH", "YOTA", "YOTAR", "YOTAU",
            "YOU", "YPF", "YRD", "YSG", "YTEN", "YTPG", "YTRG", "YUM", "YUMC", "YVR",
            "YY", "Z", "ZBH", "ZBRA", "ZCN", "ZD", "ZDGE", "ZEAL", "ZENV", "ZEPP",
            "ZEST", "ZETA", "ZEUS", "ZG", "ZGEN", "ZGN", "ZGRO", "ZIM", "ZIMV", "ZION",
            "ZIONL", "ZIONO", "ZIONP", "ZIP", "ZIXI", "ZK", "ZKH", "ZLAB", "ZM", "ZNH",
            "ZNTL", "ZOM", "ZONE", "ZOOZ", "ZPIN", "ZS", "ZTA", "ZTEK", "ZTO", "ZTR",
            "ZTS", "ZUMZ", "ZUO", "ZURA", "ZURAW", "ZVIA", "ZVO", "ZVSA", "ZVZZT", "ZWET",
            "ZWIN", "ZY", "ZYME", "ZYNE", "ZYXI", "ZZLL"
        ]
        
        logger.info(f"Verwende vordefinierte Liste mit {len(tickers)} Biotech/Pharma Tickers")
        return tickers
    
    async def fetch_snapshot_filtered(self, symbols: List[str], max_price: float = 30.0) -> Dict[str, PriceAlert]:
        """Hole Preise für Tickers mit kostenloser API"""
        if not symbols:
            return {}
        
        session = await self._get_session()
        all_results = {}
        successful = 0
        failed = 0
        
        logger.info(f"Starte Abruf von {len(symbols)} Tickers...")
        
        for idx, symbol in enumerate(symbols):
            await self._rate_limit()
            
            url = f"{self.base_url}/v2/aggs/ticker/{symbol}/prev"
            params = {"adjusted": "true", "apiKey": self.api_key}
            
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("results", [])
                        
                        if results:
                            result = results[0]
                            price = result.get("c", 0)
                            volume = result.get("v", 0)
                            open_price = result.get("o", price)
                            
                            if open_price > 0:
                                change_pct = ((price - open_price) / open_price) * 100
                            else:
                                change_pct = 0
                            
                            if 0.01 < price <= max_price and volume > 0:
                                all_results[symbol] = PriceAlert(
                                    symbol=symbol,
                                    price=price,
                                    change_pct=change_pct,
                                    volume=int(volume),
                                    timestamp=datetime.now(timezone.utc)
                                )
                                successful += 1
                    elif resp.status == 404:
                        failed += 1
                    else:
                        failed += 1
                        if idx % 50 == 0:
                            logger.debug(f"{symbol} Fehler: {resp.status}")
                            
            except asyncio.TimeoutError:
                failed += 1
                logger.debug(f"Timeout bei {symbol}")
            except Exception as e:
                failed += 1
                logger.debug(f"Fehler bei {symbol}: {e}")
            
            if (idx + 1) % 100 == 0:
                logger.info(f"Fortschritt: {idx + 1}/{len(symbols)} | Gefunden: {successful}")
        
        logger.info(f"VVPA: {len(all_results)} Aktien unter ${max_price} (erfolgreich: {successful}, fehlgeschlagen: {failed})")
        return all_results
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
        self.scan_count = 0
        
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def send_alert(self, alert: PriceAlert) -> bool:
        """Sende VVPA Alert"""
        msg = (
            f"🚀 <b>Positiver Ausbruch</b>\n\n"
            f"<b>{alert.symbol}</b>\n\n"
            f"Anstieg: <b>+{alert.change_pct:.2f}%</b>\n"
            f"Preis: ${alert.price:.2f}\n"
            f"Volumen: {alert.volume:,}\n\n"
            f"📊 <a href='https://www.tradingview.com/chart/?symbol={alert.symbol}'>Chart öffnen</a>"
        )
        
        payload = {
            'chat_id': self.chat_id,
            'text': msg,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        
        async with self._lock:
            try:
                session = await self._get_session()
                async with session.post(
                    f"{self.base_url}/sendMessage",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ Alert gesendet: {alert.symbol} +{alert.change_pct:.2f}% @ ${alert.price:.2f}")
                        return True
                    else:
                        logger.error(f"Telegram Fehler: {resp.status}")
                        text = await resp.text()
                        logger.error(f"Response: {text[:200]}")
                        return False
            except Exception as e:
                logger.error(f"Telegram Fehler: {e}")
                return False
    
    async def send_summary(self, scan_time: float, total_stocks: int, alerts: int, top_movers: List[PriceAlert]):
        """Sende Zusammenfassung nach jedem Scan"""
        self.scan_count += 1
        
        if not top_movers:
            return
            
        top_3 = top_movers[:3]
        movers_text = "\n".join([
            f"• {a.symbol}: +{a.change_pct:.2f}% (${a.price:.2f})"
            for a in top_3
        ])
        
        msg = (
            f"📊 <b>VVPA Scan #{self.scan_count}</b>\n"
            f"⏱ {scan_time:.1f}s | 📈 {total_stocks} Stocks | 🚨 {alerts} Alerts\n\n"
            f"<b>Top Mover:</b>\n{movers_text}"
        )
        
        payload = {
            'chat_id': self.chat_id,
            'text': msg,
            'parse_mode': 'HTML'
        }
        
        async with self._lock:
            try:
                session = await self._get_session()
                async with session.post(
                    f"{self.base_url}/sendMessage",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ Summary gesendet")
                    return resp.status == 200
            except Exception as e:
                logger.error(f"Summary Fehler: {e}")
                return False
    
    async def send_startup_message(self):
        """Sende Startnachricht"""
        msg = (
            f"🚀 <b>VVPA Scanner gestartet</b>\n\n"
            f"📊 Sucht nach Biotech & Pharma Aktien < $30\n"
            f"🎯 Alert bei +5% oder mehr\n"
            f"⏱ Scan alle 15 Minuten während Marktzeiten\n\n"
            f"🕐 Marktzeiten EST:\n"
            f"   Pre-Market: 4:00-9:30\n"
            f"   Regular: 9:30-16:00\n"
            f"   Post-Market: 16:00-20:00"
        )
        
        payload = {
            'chat_id': self.chat_id,
            'text': msg,
            'parse_mode': 'HTML'
        }
        
        async with self._lock:
            try:
                session = await self._get_session()
                async with session.post(
                    f"{self.base_url}/sendMessage",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    return resp.status == 200
            except:
                pass
        return False
    
    async def send_market_open_message(self):
        """Sende Nachricht wenn Markt öffnet"""
        msg = (
            f"🔔 <b>Markt ist geöffnet!</b>\n\n"
            f"VVPA Scanner aktiv\n"
            f"📊 Überwache Biotech & Pharma Aktien < $30\n"
            f"🎯 Alerts bei +5% oder mehr"
        )
        
        payload = {
            'chat_id': self.chat_id,
            'text': msg,
            'parse_mode': 'HTML'
        }
        
        async with self._lock:
            try:
                session = await self._get_session()
                async with session.post(
                    f"{self.base_url}/sendMessage",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    return resp.status == 200
            except:
                pass
        return False
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class VVPAScanner:
    """VVPA - Auto-Scan Biotech & Pharma < $30 mit Pre-Market Unterstützung"""
    
    def __init__(self):
        self.polygon_key = os.getenv('POLYGON_API_KEY')
        self.telegram_token = os.getenv('TELEGRAM_TOKEN')
        self.telegram_chat = os.getenv('TELEGRAM_CHAT_ID')
        
        if not self.polygon_key:
            raise ValueError("POLYGON_API_KEY nicht gesetzt!")
        if not self.telegram_token or not self.telegram_chat:
            raise ValueError("TELEGRAM_TOKEN oder TELEGRAM_CHAT_ID nicht gesetzt!")
        
        self.api = PolygonAPI(self.polygon_key)
        self.telegram = TelegramNotifier(self.telegram_token, self.telegram_chat)
        
        self.max_price = float(os.getenv('MAX_PRICE', '30.0'))
        self.threshold_pct = float(os.getenv('ALERT_THRESHOLD', '5.0'))
        self.cycle_minutes = int(os.getenv('CYCLE_MINUTES', '15'))
        self.min_volume = int(os.getenv('MIN_VOLUME', '10000'))
        
        self.alerted_stocks: Dict[str, datetime] = {}
        self.all_tickers: List[str] = []
        self.last_ticker_update = None
        
    def is_market_hours(self) -> bool:
        """Prüft ob gerade Marktzeiten sind (Pre-Market, Regular, Post-Market)"""
        now = datetime.now(timezone.utc)
        
        is_dst = now.month > 3 and now.month < 11
        utc_offset = 4 if is_dst else 5
        
        est_hour = now.hour - utc_offset
        if est_hour < 0:
            est_hour += 24
        
        est_minute = now.minute
        current_time = est_hour + (est_minute / 60)
        
        pre_market_start = 4.0
        regular_open = 9.5
        regular_close = 16.0
        post_market_end = 20.0
        
        if (pre_market_start <= current_time < regular_open) or \
           (regular_open <= current_time < regular_close) or \
           (regular_close <= current_time < post_market_end):
            return True
        
        return False
    
    def get_market_session(self) -> str:
        """Gibt die aktuelle Marktsitzung zurück"""
        now = datetime.now(timezone.utc)
        
        is_dst = now.month > 3 and now.month < 11
        utc_offset = 4 if is_dst else 5
        
        est_hour = now.hour - utc_offset
        if est_hour < 0:
            est_hour += 24
        
        est_minute = now.minute
        current_time = est_hour + (est_minute / 60)
        
        if 4.0 <= current_time < 9.5:
            return "Pre-Market"
        elif 9.5 <= current_time < 16.0:
            return "Regular Market"
        elif 16.0 <= current_time < 20.0:
            return "Post-Market"
        else:
            return "Closed"
    
    async def update_ticker_list(self):
        """Aktualisiere Ticker-Liste einmal pro Woche"""
        now = datetime.now(timezone.utc)
        
        if (self.last_ticker_update is None or 
            (now - self.last_ticker_update).days >= 7 or 
            not self.all_tickers):
            
            logger.info("VVPA: Lade Biotech & Pharma Ticker...")
            self.all_tickers = await self.api.get_biotech_pharma_tickers()
            self.last_ticker_update = now
            logger.info(f"VVPA: {len(self.all_tickers)} Ticker im Universum")
    
    def _should_alert(self, alert: PriceAlert) -> bool:
        """Prüfe ob Alert gesendet werden soll"""
        if alert.change_pct < self.threshold_pct:
            return False
        
        if alert.volume < self.min_volume:
            return False
        
        symbol = alert.symbol
        now = datetime.now(timezone.utc)
        
        if symbol in self.alerted_stocks:
            last_alert = self.alerted_stocks[symbol]
            minutes_since = (now - last_alert).total_seconds() / 60
            if minutes_since < self.cycle_minutes:
                return False
        
        return True
    
    async def run_cycle(self) -> dict:
        """Ein kompletter Scan-Zyklus"""
        start = datetime.now(timezone.utc)
        
        if not self.is_market_hours():
            market_session = self.get_market_session()
            logger.info(f"Außerhalb der Marktzeiten ({market_session}). Warte...")
            return {'elapsed': 0, 'total': 0, 'positive': 0, 'alerts': 0, 'top_movers': []}
        
        await self.update_ticker_list()
        
        if not self.all_tickers:
            logger.warning("Keine Ticker zum Scannen gefunden!")
            return {'elapsed': 0, 'total': 0, 'positive': 0, 'alerts': 0, 'top_movers': []}
        
        quotes = await self.api.fetch_snapshot_filtered(self.all_tickers, self.max_price)
        
        alerts_sent = 0
        alerts_list = []
        
        sorted_quotes = sorted(quotes.values(), key=lambda x: x.change_pct, reverse=True)
        
        for alert in sorted_quotes:
            if self._should_alert(alert):
                success = await self.telegram.send_alert(alert)
                if success:
                    self.alerted_stocks[alert.symbol] = datetime.now(timezone.utc)
                    alerts_sent += 1
                    alerts_list.append(alert)
        
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        positive = sum(1 for q in quotes.values() if q.change_pct > 0)
        
        market_session = self.get_market_session()
        logger.info(f"VVPA Cycle [{market_session}]: {len(quotes)} stocks <${self.max_price}, {positive}↑, {alerts_sent} alerts | {elapsed:.1f}s")
        
        if alerts_list:
            await self.telegram.send_summary(elapsed, len(quotes), alerts_sent, sorted_quotes[:10])
        
        return {
            'elapsed': elapsed,
            'total': len(quotes),
            'positive': positive,
            'alerts': alerts_sent,
            'top_movers': sorted_quotes[:10]
        }
    
    async def run(self):
        """Haupt-Loop - alle 15 Minuten mit Pre-Market Unterstützung"""
        logger.info("=" * 60)
        logger.info("🚀 VVPA Auto-Scanner gestartet")
        logger.info(f"   Universum: Biotech & Pharma < ${self.max_price}")
        logger.info(f"   Threshold: +{self.threshold_pct}%")
        logger.info(f"   Zyklus: {self.cycle_minutes} Minuten")
        logger.info(f"   Min Volume: {self.min_volume:,}")
        logger.info(f"   Marktzeiten EST: Pre-Market (4:00-9:30), Regular (9:30-16:00), Post-Market (16:00-20:00)")
        logger.info("=" * 60)
        
        if not await self.api.test_api_key():
            logger.error("❌ API-Key Test fehlgeschlagen! Bitte überprüfen Sie Ihren Polygon API-Key.")
            return
        
        await self.telegram.send_startup_message()
        
        cycle_count = 0
        last_market_status = None
        
        try:
            while True:
                cycle_count += 1
                
                current_market_status = self.is_market_hours()
                market_session = self.get_market_session()
                
                if current_market_status and last_market_status != "open":
                    logger.info(f"🔔 Markt ist jetzt geöffnet ({market_session})")
                    await self.telegram.send_market_open_message()
                    last_market_status = "open"
                elif not current_market_status and last_market_status != "closed":
                    logger.info(f"⏸ Markt ist geschlossen ({market_session})")
                    last_market_status = "closed"
                
                logger.info(f"\n--- VVPA Zyklus #{cycle_count} [{market_session}] ---")
                
                result = await self.run_cycle()
                
                sleep_seconds = self.cycle_minutes * 60 - result['elapsed']
                if sleep_seconds > 0:
                    logger.info(f"Nächster Zyklus in {sleep_seconds/60:.1f} Minuten...")
                    await asyncio.sleep(sleep_seconds)
                else:
                    logger.warning(f"Zyklus dauerte {result['elapsed']:.1f}s, länger als {self.cycle_minutes} Minuten!")
                    await asyncio.sleep(60)
                    
        except asyncio.CancelledError:
            logger.info("VVPA gestoppt")
        finally:
            await self.api.close()
            await self.telegram.close()


async def main():
    try:
        scanner = VVPAScanner()
        await scanner.run()
    except KeyboardInterrupt:
        logger.info("VVPA beendet")
    except Exception as e:
        logger.error(f"VVPA Fehler: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
