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
        # Fokussiert auf Small-Cap und Mid-Cap (< $30)
        tickers = [
            "ABCL", "ABEO", "ABOS", "ABSI", "ABUS", "ACAD", "ACET", "ACHL", "ACIU", "ACLX",
            "ACOR", "ACRS", "ACST", "ACTG", "ADAG", "ADAP", "ADCT", "ADIL", "ADMA", "ADMP",
            "ADPT", "ADRT", "ADTX", "AEON", "AEZS", "AFMD", "AGEN", "AGIO", "AGLE", "AGPH",
            "AKBA", "AKRO", "AKTS", "ALBO", "ALDX", "ALEC", "ALGM", "ALIM", "ALKS", "ALLO",
            "ALNY", "ALPN", "ALRN", "ALRS", "ALT", "ALVR", "ALXO", "AMAM", "AMBI", "AMGN",
            "AMKR", "AMPH", "AMRN", "AMRX", "ANAB", "ANEB", "ANGO", "ANIK", "ANIP", "ANIX",
            "ANVS", "APDN", "APGE", "APLM", "APLS", "APLT", "APM", "APRE", "APTO", "ARAV",
            "ARAY", "ARCB", "ARCT", "ARDX", "AREN", "ARGX", "ARHS", "ARIK", "ARKO", "ARL",
            "ARNA", "ARNC", "AROC", "AROW", "ARQT", "ARRY", "ARVN", "ARWR", "ASLN", "ASND",
            "ASRT", "ATAI", "ATEC", "ATEX", "ATHA", "ATHE", "ATHX", "ATNM", "ATOS", "ATRA",
            "ATRC", "ATRI", "ATRO", "ATXS", "AUB", "AUBN", "AUDC", "AUNA", "AUPH", "AUTL",
            "AVAH", "AVAL", "AVBP", "AVDL", "AVEO", "AVGR", "AVIR", "AVNS", "AVNT", "AVNW",
            "AVO", "AVRO", "AVT", "AVTE", "AVTX", "AVXL", "AXGN", "AXLA", "AXNX", "AXSM",
            "AYTU", "AZTA", "BAND", "BANF", "BANR", "BAOS", "BARK", "BASE", "BATRA", "BATRK",
            "BBIG", "BBI", "BCAB", "BCAX", "BCEL", "BCLI", "BCML", "BCPC", "BCRX", "BCTX",
            "BDTX", "BEAM", "BECN", "BEEM", "BELFA", "BELFB", "BENE", "BFC", "BFIN", "BFRI",
            "BFS", "BGCP", "BGFV", "BGI", "BGM", "BGSF", "BHB", "BHC", "BHE", "BHF", "BHG",
            "BHLB", "BHRB", "BHVN", "BIGC", "BIIB", "BIO", "BIOC", "BIOL", "BIOR", "BIOX",
            "BIP", "BITF", "BIVI", "BJRI", "BKCC", "BKEP", "BKH", "BKKT", "BKSC", "BKU",
            "BL", "BLBD", "BLBX", "BLCM", "BLDE", "BLDP", "BLFS", "BLFY", "BLI", "BLIN",
            "BLNK", "BLPH", "BLRX", "BLTE", "BLUE", "BLU", "BLZE", "BMEA", "BMRA", "BMRN",
            "BMTX", "BMY", "BNGO", "BNOX", "BNR", "BNTC", "BNTX", "BOOM", "BOWL", "BOX",
            "BPMC", "BPTH", "BQ", "BRAG", "BRBR", "BRCC", "BRDG", "BREZ", "BRFH", "BRID",
            "BRKR", "BRLS", "BRLT", "BRMK", "BROG", "BRP", "BRQS", "BRSP", "BRT", "BRTX",
            "BRY", "BSBK", "BSET", "BSGM", "BSIG", "BSKY", "BSRR", "BSVN", "BTAI", "BTBD",
            "BTBT", "BTCM", "BTMD", "BTOG", "BTRS", "BTTX", "BTU", "BTWN", "BUR", "BVS",
            "BVXV", "BWAY", "BWMN", "BWMX", "BXRX", "BY", "BYFC", "BYN", "BYND", "BYRN",
            "BYSI", "CAAP", "CABA", "CAC", "CACC", "CADL", "CAE", "CAF", "CAG", "CAH",
            "CAKE", "CAL", "CALA", "CALB", "CALM", "CALT", "CAMT", "CAN", "CANC", "CANF",
            "CAPL", "CAPR", "CAR", "CARA", "CARE", "CARG", "CARM", "CARV", "CASA", "CASH",
            "CASI", "CASS", "CASY", "CATC", "CATO", "CATY", "CBAN", "CBAY", "CBFV", "CBIO",
            "CBL", "CBLL", "CBNK", "CBOE", "CBRL", "CBSH", "CBT", "CBUS", "CBZ", "CC",
            "CCAP", "CCB", "CCBG", "CCCC", "CCEP", "CCF", "CCH", "CCI", "CCK", "CCL",
            "CCLP", "CCM", "CCNE", "CCRN", "CCS", "CCSI", "CCT", "CCTG", "CCXI", "CDAK",
            "CDE", "CDIO", "CDLX", "CDMO", "CDNA", "CDRE", "CDRO", "CDT", "CDTX", "CDW",
            "CDXC", "CDXS", "CDZI", "CE", "CECE", "CEE", "CELC", "CELH", "CELU", "CELZ",
            "CENN", "CENT", "CENX", "CERE", "CERS", "CERT", "CETX", "CEV", "CEVA", "CF",
            "CFB", "CFBK", "CFFI", "CFFN", "CFG", "CFLT", "CFMS", "CFO", "CFR", "CFRX",
            "CG", "CGA", "CGBD", "CGC", "CGEM", "CGEN", "CGNT", "CGNX", "CGO", "CGRN",
            "CGTX", "CHCI", "CHCO", "CHCT", "CHDN", "CHE", "CHEF", "CHEK", "CHGG", "CHH",
            "CHK", "CHMG", "CHMI", "CHNR", "CHRS", "CHRW", "CHS", "CHTR", "CHUY", "CHW",
            "CHX", "CI", "CIA", "CIB", "CIEN", "CIF", "CIFR", "CIG", "CIGI", "CII", "CIM",
            "CINF", "CING", "CINT", "CIO", "CION", "CIR", "CIT", "CIVB", "CIVI", "CIX",
            "CJJD", "CKPT", "CL", "CLAR", "CLBK", "CLBR", "CLBT", "CLDI", "CLDT", "CLDX",
            "CLEU", "CLF", "CLFD", "CLGN", "CLH", "CLIN", "CLIR", "CLLS", "CLM", "CLMT",
            "CLNE", "CLNN", "CLOV", "CLPR", "CLPS", "CLPT", "CLRB", "CLRC", "CLRO", "CLSD",
            "CLSK", "CLSM", "CLST", "CLVT", "CLW", "CLWT", "CLX", "CM", "CMA", "CMAX",
            "CMBM", "CMBT", "CMC", "CMCL", "CMCM", "CMCO", "CMCSA", "CMCT", "CME", "CMG",
            "CMI", "CMLS", "CMMB", "CMP", "CMPO", "CMPR", "CMPS", "CMPX", "CMRE", "CMRX",
            "CMS", "CMT", "CMTG", "CMTL", "CMU", "CNA", "CNC", "CNCE", "CNC", "CNC",
            "CNCK", "CNCR", "CNDA", "CNDT", "CNET", "CNF", "CNFR", "CNFRL", "CNGL", "CNHC",
            "CNHI", "CNI", "CNK", "CNM", "CNMD", "CNNB", "CNO", "CNOB", "CNP", "CNQ",
            "CNS", "CNSL", "CNSP", "CNTA", "CNTB", "CNTG", "CNTX", "CNTY", "CNVS", "CNX",
            "CNXC", "CNXN", "COCO", "COCP", "CODA", "CODI", "CODX", "COE", "COEP", "COF",
            "COFS", "COGT", "COHN", "COHR", "COHU", "COIN", "COKE", "COLB", "COLD", "COLL",
            "COLM", "COMM", "COMP", "COMS", "COMSP", "CONN", "CONX", "COO", "COOK", "COOL",
            "COOP", "COP", "COR", "CORS", "CORZ", "COSM", "COTY", "COUR", "COVA", "COWN",
            "CP", "CPA", "CPAC", "CPB", "CPE", "CPF", "CPG", "CPHC", "CPHI", "CPI", "CPIX",
            "CPK", "CPLP", "CPRT", "CPRX", "CPS", "CPSI", "CPSS", "CPST", "CPT", "CPTK",
            "CRAI", "CRBP", "CRBU", "CRC", "CRCT", "CRDA", "CRDF", "CRDL", "CRDO", "CREC",
            "CREG", "CRESY", "CREX", "CRGE", "CRGY", "CRH", "CRI", "CRIS", "CRKN", "CRL",
            "CRM", "CRMD", "CRMT", "CRNC", "CRNT", "CRNX", "CROX", "CRSR", "CRT", "CRTO",
            "CRUS", "CRVL", "CRVS", "CRWD", "CRWS", "CRXT", "CRYP", "CRZN", "CS", "CSBR",
            "CSCO", "CSGP", "CSGS", "CSII", "CSIQ", "CSL", "CSLM", "CSLR", "CSPI", "CSR",
            "CSTE", "CSTL", "CSTM", "CSTR", "CSV", "CSWC", "CSWI", "CSX", "CTAS", "CTBI",
            "CTCX", "CTEK", "CTG", "CTGO", "CTHR", "CTIB", "CTIC", "CTKB", "CTK", "CTL",
            "CTLT", "CTM", "CTMX", "CTNM", "CTNT", "CTO", "CTOS", "CTR", "CTRA", "CTRE",
            "CTRI", "CTRN", "CTRP", "CTSH", "CTSO", "CTXR", "CUBB", "CUBE", "CUBI", "CUE",
            "CUK", "CULP", "CURV", "CUTR", "CUZ", "CVAC", "CVBF", "CVCO", "CVC", "CVE",
            "CVEO", "CVGI", "CVGW", "CVI", "CVLG", "CVLT", "CVLY", "CVM", "CVNA", "CVNC",
            "CVO", "CVS", "CVT", "CVU", "CVV", "CVX", "CW", "CWAN", "CWBC", "CWCO", "CWH",
            "CWK", "CWST", "CWT", "CX", "CXDO", "CXM", "CXO", "CXT", "CXW", "CYBN", "CYBR",
            "CYCC", "CYCN", "CYD", "CYH", "CYN", "CYRX", "CYTH", "CYTK", "CZFS", "CZNC",
            "CZR", "CZWI", "DADA", "DAIO", "DAKT", "DAL", "DAN", "DAO", "DAP", "DAPP",
            "DAR", "DARE", "DASH", "DATS", "DAVA", "DAVE", "DB", "DBA", "DBD", "DBGI",
            "DBI", "DBRG", "DBS", "DBTX", "DBVT", "DBX", "DCBO", "DCF", "DCI", "DCO",
            "DCOM", "DCPH", "DCT", "DCUE", "DCY", "DD", "DDD", "DDE", "DDF", "DDI", "DDL",
            "DDOG", "DDS", "DDT", "DE", "DEA", "DEC", "DECK", "DEI", "DELL", "DEN", "DENN",
            "DEO", "DERM", "DESP", "DEX", "DFH", "DFIN", "DFLI", "DFP", "DFRG", "DFS",
            "DG", "DGICA", "DGICB", "DGII", "DGLY", "DGX", "DH", "DHC", "DHI", "DHIL",
            "DHR", "DHT", "DHX", "DIA", "DIBS", "DICE", "DIN", "DINO", "DIOD", "DIS",
            "DISA", "DISCA", "DISCB", "DISCK", "DISH", "DIT", "DIX", "DK", "DKL", "DKNG",
            "DKS", "DLA", "DLB", "DLCA", "DLHC", "DLNG", "DLPN", "DLR", "DLS", "DLTH",
            "DLTR", "DLX", "DM", "DMA", "DMAC", "DMC", "DMLP", "DMO", "DMRC", "DMTK",
            "DMYS", "DNB", "DNLI", "DNMR", "DNN", "DNOW", "DNP", "DNUT", "DO", "DOC",
            "DOCN", "DOCS", "DOCU", "DOG", "DOGZ", "DOLE", "DOMA", "DOMO", "DOOO", "DORM",
            "DOUG", "DOV", "DOW", "DPCS", "DPG", "DPRO", "DPZ", "DQ", "DRCT", "DRD",
            "DRH", "DRI", "DRIO", "DRMA", "DRQ", "DRRX", "DRS", "DRTS", "DRVN", "DRX",
            "DS", "DSAQ", "DSEY", "DSGX", "DSKE", "DSL", "DSM", "DSP", "DSS", "DSWL",
            "DSX", "DT", "DTB", "DTE", "DTF", "DTG", "DTH", "DTI", "DTIL", "DTM", "DTM",
            "DTOC", "DTSS", "DTST", "DTW", "DUET", "DUK", "DUOT", "DUR", "DUSA", "DUSN",
            "DUST", "DV", "DVA", "DVAX", "DVN", "DWAC", "DWSN", "DX", "DXCM", "DXF",
            "DXLG", "DXPE", "DXR", "DXYN", "DY", "DYAI", "DYN", "DYNT", "DZSI", "E",
            "EA", "EAC", "EAD", "EAF", "EAI", "EARN", "EAST", "EAT", "EBAY", "EBET",
            "EBF", "EBMT", "EBON", "EBS", "EBTC", "EC", "ECAT", "ECC", "ECCC", "ECF",
            "ECG", "ECHO", "ECL", "ECOR", "ECPG", "ECVT", "ED", "EDAP", "EDBL", "EDD",
            "EDF", "EDN", "EDOG", "EDR", "EDRY", "EDSA", "EDTX", "EDU", "EDUC", "EE",
            "EEA", "EEX", "EF", "EFC", "EFG", "EFI", "EFII", "EFL", "EFM", "EFOI", "EFSC",
            "EFX", "EGAN", "EGBN", "EGFS", "EGHT", "EGIO", "EGLE", "EGO", "EGP", "EGRX",
            "EGY", "EH", "EHC", "EHI", "EIG", "EIM", "EIX", "EJH", "EKSO", "EL", "ELA",
            "ELAN", "ELBM", "ELC", "ELDN", "ELEV", "ELF", "ELFM", "ELG", "ELMD", "ELOX",
            "ELP", "ELS", "ELSE", "ELTK", "ELTX", "ELUT", "ELV", "ELVT", "ELY", "EM",
            "EMAN", "EMBC", "EMB", "EMCF", "EME", "EMF", "EMKR", "EML", "EMN", "EMN",
            "EMO", "EMP", "EMR", "EMX", "ENB", "ENBA", "ENBL", "ENCP", "ENDP", "ENFN",
            "ENG", "ENIC", "ENJ", "ENLC", "ENLV", "ENOB", "ENOV", "ENPC", "ENPH", "ENR",
            "ENS", "ENSC", "ENSG", "ENSV", "ENTA", "ENTF", "ENTG", "ENTX", "ENV", "ENVA",
            "ENVB", "ENVX", "ENZ", "EOLS", "EOSE", "EP", "EPAC", "EPAM", "EPAY", "EPC",
            "EPD", "EPHY", "EPIX", "EPM", "EPR", "EPRT", "EPSN", "EPZM", "EQ", "EQBK",
            "EQC", "EQH", "EQIX", "EQR", "EQRX", "EQS", "EQT", "ERAS", "ERC", "ERESU",
            "ERF", "ERH", "ERIC", "ERIE", "ERII", "ERJ", "ERNA", "ERO", "ES", "ESAB",
            "ESAC", "ESBA", "ESBK", "ESCA", "ESE", "ESEA", "ESGR", "ESGU", "ESI", "ESLT",
            "ESNT", "ESOA", "ESP", "ESPR", "ESQ", "ESRT", "ESSA", "ESTA", "ESTC", "ESTE",
            "ET", "ETAC", "ETB", "ETD", "ETG", "ETH", "ETN", "ETNB", "ETO", "ETON",
            "ETR", "ETRN", "ETSY", "ETV", "ETW", "ETWO", "ETY", "EU", "EUCR", "EUFN",
            "EURN", "EVA", "EVBG", "EVBN", "EVC", "EVCM", "EVE", "EVG", "EVGN", "EVGO",
            "EVH", "EVI", "EVK", "EVL", "EVLO", "EVLV", "EVN", "EVO", "EVOJ", "EVOK",
            "EVOL", "EVOP", "EVR", "EVRG", "EVRI", "EVTV", "EVTX", "EVV", "EW", "EWBC",
            "EWCZ", "EWTX", "EXAI", "EXAS", "EXC", "EXD", "EXEL", "EXFY", "EXG", "EXI",
            "EXK", "EXLS", "EXP", "EXPD", "EXPE", "EXPI", "EXPO", "EXPR", "EXR", "EXRX",
            "EXTN", "EXTR", "EYE", "EYEN", "EYPT", "EZFL", "EZGO", "EZPW", "F", "FA",
            "FAAR", "FAB", "FACT", "FAD", "FAF", "FALN", "FAMI", "FANG", "FANH", "FARM",
            "FARO", "FAST", "FAT", "FATBB", "FATBP", "FATBW", "FATES", "FATH", "FATP",
            "FAX", "FBC", "FBIO", "FBIZ", "FBK", "FBLG", "FBMS", "FBNC", "FBP", "FBRT",
            "FBRX", "FBYD", "FC", "FCAL", "FCAP", "FCBC", "FCCO", "FCEF", "FCEL", "FCF",
            "FCFS", "FCN", "FCNCA", "FCNCO", "FCNCP", "FCO", "FCPT", "FCRD", "FCRX",
            "FCT", "FCUV", "FCX", "FDBC", "FDEU", "FDFF", "FDMT", "FDP", "FDRR", "FDRV",
            "FDS", "FDUS", "FDX", "FE", "FEAM", "FEDU", "FEIM", "FELE", "FEM", "FEMB",
            "FEMY", "FEN", "FENC", "FENG", "FENY", "FEP", "FER", "FERG", "FES", "FET",
            "FEX", "FF", "FFBC", "FFC", "FFIC", "FFIE", "FFIN", "FFIU", "FFNW", "FFWM",
            "FGB", "FGBI", "FGEN", "FGF", "FGI", "FGMC", "FGN", "FGR", "FGRX", "FH",
            "FHB", "FHI", "FHLT", "FHN", "FHTX", "FI", "FIBK", "FIBR", "FICO", "FICS",
            "FID", "FIDI", "FIDU", "FIEE", "FIEN", "FIF", "FIII", "FIS", "FISI", "FITB",
            "FITBI", "FITBO", "FITBP", "FITE", "FIVE", "FIVN", "FIX", "FIXD", "FIXX",
            "FIZZ", "FJP", "FKU", "FLA", "FLAC", "FLAU", "FLAX", "FLBL", "FLBR", "FLCA",
            "FLCB", "FLCH", "FLCO", "FLDR", "FLEE", "FLEU", "FLEX", "FLFV", "FLGB", "FLGR",
            "FLHK", "FLHY", "FLIA", "FLIC", "FLIN", "FLIO", "FLIY", "FLJH", "FLJP", "FLKR",
            "FLMX", "FLN", "FLO", "FLOT", "FLQL", "FLQM", "FLQS", "FLR", "FLRG", "FLRN",
            "FLRT", "FLS", "FLSA", "FLSP", "FLSW", "FLT", "FLTB", "FLTW", "FLUD", "FLUX",
            "FLV", "FLWS", "FLXS", "FLY", "FLYD", "FLYL", "FLYN", "FLYW", "FM", "FMAO",
            "FMB", "FMBH", "FMBI", "FMBIO", "FMBIP", "FMC", "FMCI", "FMET", "FMF", "FMHI",
            "FMIL", "FMN", "FMNB", "FMO", "FMS", "FMTX", "FMY", "FN", "FNA", "FNB",
            "FNBG", "FNCB", "FNCH", "FNCL", "FND", "FNDA", "FNDB", "FNDE", "FNDF", "FNDX",
            "FNF", "FNGS", "FNI", "FNKO", "FNLC", "FNWB", "FNWD", "FNX", "FNXE", "FNXT",
            "FOA", "FOAX", "FOCS", "FOF", "FOLD", "FOM", "FONR", "FOR", "FORA", "FORB",
            "FORD", "FOREX", "FORG", "FORH", "FORL", "FORM", "FORR", "FORTY", "FOSL",
            "FOSLL", "FOSS", "FOTO", "FOUR", "FOX", "FOXA", "FOXF", "FOXX", "FP", "FPA",
            "FPAY", "FPE", "FPH", "FPI", "FPL", "FPRX", "FPXE", "FPXI", "FR", "FRA",
            "FRAF", "FRBA", "FRBK", "FRC", "FRD", "FRDM", "FREE", "FREQ", "FREY", "FRG",
            "FRGAP", "FRGE", "FRGT", "FRHC", "FRI", "FRLN", "FRME", "FRMEP", "FRO",
            "FROG", "FRON", "FRPH", "FRPT", "FRSH", "FRSX", "FRT", "FRTY", "FRXB",
            "FSBC", "FSBD", "FSBW", "FSC", "FSCO", "FSD", "FSEC", "FSEP", "FSFG", "FSI",
            "FSK", "FSLR", "FSLY", "FSM", "FSMB", "FSMD", "FSNB", "FSP", "FSR", "FSS",
            "FSV", "FSZ", "FT", "FTA", "FTAG", "FTAI", "FTC", "FTCH", "FTCI", "FTCS",
            "FTDR", "FTEC", "FTEK", "FTF", "FTFT", "FTHI", "FTHM", "FTHY", "FTI", "FTII",
            "FTK", "FTNT", "FTPA", "FTR", "FTRP", "FTS", "FTSL", "FTSM", "FTV", "FTXG",
            "FTXH", "FTXL", "FTXN", "FTXO", "FTXR", "FUL", "FULT", "FULTP", "FUN", "FUNC",
            "FUND", "FUSB", "FUSN", "FUTU", "FUV", "FV", "FVAL", "FVC", "FVCB", "FVD",
            "FVE", "FVRR", "FWAC", "FWBI", "FWONA", "FWONK", "FWP", "FWRD", "FWRG", "FX",
            "FXA", "FXB", "FXC", "FXD", "FXE", "FXF", "FXG", "FXH", "FXI", "FXL", "FXN",
            "FXO", "FXP", "FXR", "FXU", "FXY", "FXZ", "FYC", "FYLD", "FYT", "FYX",
            "G", "GAA", "GAB", "GABC", "GABF", "GAC", "GADC", "GAIA", "GAIN", "GAL",
            "GALT", "GAM", "GAMB", "GAMC", "GAME", "GAMR", "GAN", "GAPA", "GASS", "GATE",
            "GAU", "GBCI", "GBDC", "GBIO", "GBLI", "GBNH", "GBNY", "GBR", "GBRG", "GBRGR",
            "GBRGU", "GBRGW", "GBS", "GBT", "GBX", "GC", "GCI", "GCMG", "GCO", "GCOW",
            "GCP", "GCV", "GD", "GDDY", "GDEN", "GDL", "GDLC", "GDM", "GDNR", "GDO",
            "GDOT", "GDP", "GDRX", "GDS", "GDV", "GDVD", "GDX", "GDXJ", "GE", "GECC",
            "GEF", "GEG", "GEL", "GEM", "GEN", "GENE", "GENI", "GENY", "GEO", "GEOS",
            "GER", "GERN", "GES", "GEVO", "GF", "GFAI", "GFF", "GFGD", "GFI", "GFL",
            "GFLU", "GFR", "GFS", "GFX", "GGAA", "GGAL", "GGB", "GGG", "GGN", "GGZ",
            "GH", "GHAC", "GHC", "GHDX", "GHG", "GHI", "GHIX", "GHL", "GHLD", "GHM",
            "GHRS", "GHSI", "GHY", "GIB", "GIC", "GIFI", "GIGB", "GIGM", "GIII", "GIK",
            "GIL", "GILD", "GILT", "GIM", "GIPR", "GIS", "GJH", "GJO", "GJP", "GJR",
            "GJS", "GKOS", "GL", "GLAD", "GLBE", "GLBL", "GLBZ", "GLD", "GLDD", "GLDG",
            "GLEE", "GLEN", "GLLI", "GLNG", "GLO", "GLOB", "GLOP", "GLP", "GLPG", "GLPI",
            "GLRE", "GLRY", "GLS", "GLT", "GLTA", "GLTO", "GLTR", "GLUE", "GLV", "GLW",
            "GLYC", "GM", "GMAB", "GMBL", "GMDA", "GME", "GMED", "GMF", "GMGI", "GMRE",
            "GMS", "GMVD", "GNE", "GNET", "GNFT", "GNK", "GNL", "GNLN", "GNPX", "GNRC",
            "GNS", "GNT", "GNTX", "GNTY", "GNUS", "GO", "GOAU", "GOCO", "GOEV", "GOGL",
            "GOGN", "GOGO", "GOLD", "GOLF", "GOOD", "GOOG", "GOOGL", "GOOS", "GORO",
            "GOSS", "GOTU", "GOV", "GOVX", "GOVZ", "GP", "GPAC", "GPAK", "GPC", "GPI",
            "GPK", "GPL", "GPM", "GPN", "GPOR", "GPRE", "GPRK", "GPRO", "GPS", "GPT",
            "GPUS", "GPX", "GQRE", "GRAB", "GRBK", "GRC", "GRCL", "GRFS", "GRID", "GRIN",
            "GRMN", "GRN", "GRNB", "GRNQ", "GRNT", "GROM", "GROV", "GROW", "GRPH", "GRPN",
            "GRTS", "GRTX", "GRVY", "GRWG", "GRX", "GS", "GSAT", "GSBC", "GSBD", "GSE",
            "GSEV", "GSHD", "GSIT", "GSK", "GSL", "GSLC", "GSM", "GSMG", "GSP", "GSS",
            "GSUM", "GSUN", "GSY", "GT", "GTE", "GTEC", "GTES", "GTH", "GTHX", "GTI",
            "GTIM", "GTLB", "GTLS", "GTN", "GTPA", "GTPB", "GTR", "GTS", "GTX", "GTY",
            "GTYH", "GUG", "GULF", "GUNR", "GURE", "GURU", "GUSH", "GUT", "GVA", "GVAL",
            "GVI", "GVIP", "GVP", "GW", "GWH", "GWRE", "GWRS", "GWW", "GXG", "GXTG",
            "GYRO", "H", "HA", "HAE", "HAFC", "HAIA", "HAIL", "HAIN", "HAL", "HALL",
            "HALO", "HAPP", "HARP", "HAS", "HASI", "HAUZ", "HAWX", "HAYN", "HAYW", "HBAN",
            "HBANM", "HBANP", "HBB", "HBCP", "HBI", "HBIO", "HBNC", "HBT", "HCA", "HCAT",
            "HCC", "HCCI", "HCDI", "HCI", "HCKT", "HCM", "HCMA", "HCP", "HCSG", "HCWB",
            "HCXY", "HD", "HDB", "HDSN", "HE", "HEAR", "HEES", "HEET", "HEFA", "HEI",
            "HELE", "HELO", "HEP", "HEPA", "HEPS", "HEQ", "HERD", "HERO", "HES", "HESM",
            "HEWC", "HEWG", "HEWJ", "HEWK", "HEWL", "HEWU", "HEWY", "HEXO", "HEZU",
            "HFBL", "HFFG", "HFRO", "HFWA", "HG", "HGBL", "HGEN", "HGLB", "HGTY", "HGV",
            "HHGC", "HHS", "HI", "HIBB", "HIE", "HIFS", "HIG", "HIHO", "HII", "HIL",
            "HIMS", "HIMX", "HIO", "HIPO", "HITI", "HIVE", "HIW", "HIX", "HJEN", "HKIB",
            "HL", "HLF", "HLG", "HLI", "HLIO", "HLIT", "HLLY", "HLMN", "HLNE", "HLT",
            "HLX", "HMC", "HMCO", "HMNF", "HMPT", "HMST", "HMTV", "HMY", "HNI", "HNNA",
            "HNNAZ", "HNO", "HNP", "HNRG", "HNST", "HNW", "HOFT", "HOFV", "HOG", "HOLI",
            "HOLX", "HOMB", "HON", "HONE", "HOOD", "HOOK", "HOPE", "HORI", "HOTH", "HOTL",
            "HOV", "HOVNP", "HOVR", "HOWL", "HP", "HPE", "HPF", "HPI", "HPK", "HPLT",
            "HPP", "HPQ", "HPS", "HQH", "HQI", "HQL", "HQY", "HR", "HRB", "HRC", "HRI",
            "HRL", "HRMY", "HROW", "HRT", "HRTG", "HRTX", "HRZN", "HSAQ", "HSC", "HSDT",
            "HSIC", "HSII", "HSKA", "HSON", "HSPO", "HST", "HSTM", "HSTO", "HSY", "HT",
            "HTAB", "HTBI", "HTBK", "HTBX", "HTCR", "HTD", "HTEC", "HTFA", "HTGC", "HTGM",
            "HTH", "HTHT", "HTIA", "HTIBP", "HTLD", "HTLF", "HTLFP", "HTOO", "HTY", "HUBB",
            "HUBG", "HUBS", "HUDI", "HUGE", "HUIZ", "HUM", "HUMA", "HUN", "HURC", "HUSA",
            "HUSV", "HUYA", "HVBC", "HVB", "HVT", "HWBK", "HWC", "HWCPZ", "HWEL", "HWKN",
            "HWM", "HXL", "HY", "HYAC", "HYB", "HYFM", "HYG", "HYI", "HYLB", "HYLN",
            "HYLV", "HYMC", "HYMCL", "HYMCW", "HYMT", "HYMU", "HYPR", "HYRE", "HYT",
            "HYTR", "HYW", "HYXF", "HZNP", "HZO", "HZON", "I", "IAA", "IAC", "IAD",
            "IAE", "IAF", "IAG", "IART", "IAS", "IAU", "IAUF", "IBA", "IBB", "IBBQ",
            "IBCE", "IBCP", "IBD", "IBEX", "IBIO", "IBKR", "IBM", "IBN", "IBOC", "IBP",
            "IBRX", "IBTA", "IBTE", "IBTF", "IBTG", "IBTH", "IBTI", "IBTJ", "IBTK", "IBTL",
            "IBTM", "IBTO", "IBTP", "IBTR", "IBTS", "IBTX", "IBUY", "ICAD", "ICCC", "ICCH",
            "ICD", "ICE", "ICF", "ICFI", "ICHR", "ICL", "ICLK", "ICLN", "ICLR", "ICMB",
            "ICNC", "ICOW", "ICPT", "ICUI", "ICVX", "ID", "IDA", "IDAI", "IDCC", "IDEX",
            "IDN", "IDRA", "IDT", "IDU", "IDX", "IDXX", "IDYA", "IEA", "IEAWW", "IEC",
            "IEF", "IEI", "IEP", "IESC", "IEUS", "IF", "IFBD", "IFED", "IFF", "IFGL",
            "IFN", "IFRA", "IFRX", "IFS", "IFV", "IG", "IGA", "IGAC", "IGC", "IGD",
            "IGE", "IGF", "IGHG", "IGI", "IGIB", "IGIC", "IGLD", "IGM", "IGN", "IGOV",
            "IGR", "IGRO", "IGSB", "IGT", "IGTA", "IGV", "IHC", "IHD", "IHDG", "IHF",
            "IHRT", "IHT", "IHTA", "IIF", "IIGD", "III", "IIIN", "IIIV", "IINN", "IIPR",
            "IJH", "IJJ", "IJK", "IJR", "IJS", "IJT", "IL", "ILF", "ILMN", "ILPT",
            "ILTB", "IMAB", "IMAC", "IMAQ", "IMAX", "IMBI", "IMCC", "IMCR", "IMGN",
            "IMH", "IMKTA", "IMMP", "IMMR", "IMNM", "IMOS", "IMPL", "IMPP", "IMPPP",
            "IMRN", "IMRX", "IMTE", "IMTX", "IMUX", "IMV", "IMVT", "IMXI", "INAB",
            "INBK", "INBX", "INCR", "INCY", "INDB", "INDI", "INDO", "INDP", "INDV",
            "INFA", "INFN", "INFR", "INFU", "INFY", "ING", "INGN", "INGR", "INKA",
            "INKT", "INLX", "INM", "INMB", "INMD", "INN", "INNO", "INNV", "INO",
            "INOD", "INOV", "INPX", "INSE", "INSG", "INSI", "INSM", "INSP", "INST",
            "INSW", "INT", "INTA", "INTC", "INTE", "INTF", "INTG", "INTR", "INTT",
            "INTU", "INTX", "INUV", "INVA", "INVE", "INVH", "INVO", "INVZ", "INZY",
            "IOAC", "IOBT", "IONM", "IONQ", "IONS", "IOVA", "IP", "IPA", "IPAR",
            "IPDN", "IPG", "IPGP", "IPHA", "IPI", "IPKW", "IPL", "IPOA", "IPOB",
            "IPOC", "IPOD", "IPOE", "IPOF", "IPOS", "IPSC", "IPV", "IPVA", "IPVF",
            "IPVI", "IPW", "IPWR", "IQ", "IQI", "IQMD", "IQM", "IQV", "IR", "IRBT",
            "IRDM", "IREN", "IRIX", "IRM", "IRMD", "IROQ", "IRTC", "IRWD", "IS",
            "ISAA", "ISD", "ISDR", "ISEE", "ISEM", "ISHG", "ISHP", "ISIG", "ISMD",
            "ISPC", "ISPO", "ISPR", "ISRA", "ISRG", "ISSC", "ISTB", "ISTR", "ISUN",
            "IT", "ITB", "ITCI", "ITGR", "ITI", "ITIC", "ITOS", "ITQ", "ITRG",
            "ITRI", "ITRM", "ITRN", "ITRT", "ITT", "ITW", "ITWO", "IUS", "IUSB",
            "IUSG", "IUSV", "IVA", "IVAC", "IVAL", "IVAN", "IVC", "IVCA", "IVCB",
            "IVCP", "IVDA", "IVDG", "IVEG", "IVE", "IVH", "IVOL", "IVOO", "IVR",
            "IVT", "IVV", "IVW", "IVZ", "IW", "IWB", "IWC", "IWD", "IWF", "IWFG",
            "IWH", "IWL", "IWM", "IWN", "IWO", "IWP", "IWR", "IWS", "IWV", "IWX",
            "IWY", "IX", "IXC", "IXG", "IXJ", "IXN", "IXP", "IXUS", "IYC", "IYE",
            "IYF", "IYG", "IYH", "IYJ", "IYK", "IYLD", "IYM", "IYR", "IYT", "IYW",
            "IYZ", "IZEA", "J", "JAAA", "JACK", "JAGX", "JAKK", "JAMF", "JAN",
            "JANX", "JAVA", "JAZZ", "JBGS", "JBHT", "JBI", "JBL", "JBLU", "JBSS",
            "JBT", "JCAP", "JCE", "JCI", "JCIC", "JCO", "JCS", "JCTCF", "JD",
            "JEF", "JELD", "JEMA", "JEMD", "JEQ", "JETS", "JFIN", "JFR", "JFU",
            "JG", "JGH", "JGN", "JGV", "JHC", "JHCS", "JHE", "JHG", "JHI", "JHM",
            "JHMB", "JHMC", "JHMD", "JHMF", "JHMG", "JHMI", "JHMU", "JHS", "JHSC",
            "JHX", "JIB", "JIG", "JILL", "JJA", "JJC", "JJE", "JJG", "JJM", "JJN",
            "JJP", "JJS", "JJSF", "JJT", "JKL", "JLD", "JLL", "JLS", "JMIA",
            "JMM", "JMN", "JMP", "JMSB", "JNJ", "JNK", "JNPR", "JNUG", "JO",
            "JOAN", "JOB", "JOBY", "JOE", "JOET", "JOF", "JOUT", "JP", "JPC",
            "JPI", "JPM", "JPMB", "JPME", "JPN", "JPS", "JPSE", "JPST", "JPT",
            "JPUS", "JQC", "JRI", "JRO", "JRS", "JRSH", "JRVR", "JSM", "JSN",
            "JSPR", "JTEK", "JUGG", "JUGGU", "JUN", "JUNT", "JUST", "JVA", "JVAL",
            "JWN", "JWSM", "JXI", "JYNT", "JZ", "K", "KACL", "KAI", "KALA",
            "KALU", "KALV", "KAMN", "KAR", "KARO", "KAVL", "KB", "KBE", "KBH",
            "KBR", "KBSF", "KBSX", "KBWB", "KBWD", "KBWP", "KBWR", "KBWY", "KC",
            "KCCA", "KCE", "KCG", "KCLI", "KDP", "KE", "KELYA", "KELYB", "KEN",
            "KEP", "KEQU", "KERN", "KEX", "KEY", "KEYS", "KF", "KFFB", "KFRC",
            "KFS", "KFYP", "KGC", "KGHG", "KHC", "KIDS", "KIM", "KIO", "KIQ",
            "KIRK", "KITT", "KITL", "KJAN", "KJUL", "KKR", "KLAC", "KLAQ", "KLIC",
            "KLR", "KLTR", "KMDA", "KMF", "KMI", "KMPB", "KMPR", "KMT", "KMX",
            "KN", "KNDI", "KNOP", "KNOW", "KNSA", "KNSL", "KNTE", "KNTK", "KNW",
            "KNX", "KO", "KOD", "KODK", "KOF", "KOP", "KOPN", "KORE", "KOS",
            "KOSS", "KPLT", "KPRX", "KPTI", "KR", "KRC", "KREF", "KRG", "KRKR",
            "KRMD", "KRNL", "KRNT", "KRNY", "KRO", "KRON", "KROS", "KRP", "KRT",
            "KRTX", "KRUS", "KRYS", "KSCP", "KSM", "KSPN", "KSS", "KSTR", "KT",
            "KTB", "KTCC", "KTF", "KTH", "KTN", "KTOS", "KTRA", "KTP", "KTTA",
            "KUKE", "KULR", "KURA", "KURE", "KVHI", "KVLE", "KVSA", "KVSC", "KVT",
            "KWE", "KWEB", "KWR", "KXIN", "KYCH", "KYMR", "KYN", "KZIA", "KZR",
            "L", "LAAA", "LAB", "LABD", "LABU", "LAC", "LAD", "LADR", "LAGE",
            "LAKE", "LALT", "LAMR", "LANC", "LAND", "LARK", "LASR", "LAUR",
            "LAW", "LAZ", "LAZR", "LBAI", "LBBB", "LBC", "LBPH", "LBRDA",
            "LBRDK", "LBRDP", "LBTYA", "LBTYB", "LBTYK", "LC", "LCA", "LCAA",
            "LCAP", "LCCC", "LCE", "LCFY", "LCI", "LCID", "LCII", "LCNB", "LCUT",
            "LDEM", "LDI", "LDP", "LDR", "LDSF", "LDWY", "LE", "LEA", "LEAD",
            "LECO", "LEDS", "LEE", "LEG", "LEGH", "LEGN", "LEGR", "LEJU", "LEN",
            "LENZ", "LEO", "LESL", "LEU", "LEV", "LEVI", "LEXX", "LFAC", "LFLY",
            "LFMD", "LFMDP", "LFST", "LFT", "LFTR", "LFUS", "LFVN", "LGAC",
            "LGCB", "LGHL", "LGHLW", "LGI", "LGIH", "LGL", "LGMK", "LGND", "LGO",
            "LGP", "LGST", "LGTY", "LH", "LHC", "LHCG", "LHDX", "LHE", "LHI",
            "LHK", "LHX", "LI", "LIDR", "LIFE", "LII", "LILA", "LILAK", "LINC",
            "LIND", "LINX", "LION", "LIQT", "LIT", "LITE", "LITH", "LITT", "LITM",
            "LIVE", "LIVN", "LIXT", "LIZI", "LJPC", "LKCO", "LKFN", "LKOR", "LKSB",
            "LKT", "LL", "LLAP", "LLL", "LLY", "LMACA", "LMACU", "LMAT", "LMB",
            "LMBS", "LMFA", "LMND", "LMNL", "LMNR", "LMRK", "LMST", "LMT", "LN",
            "LNC", "LND", "LNDC", "LNG", "LNN", "LNSR", "LNT", "LNTH", "LOAN",
            "LOB", "LOCO", "LOGC", "LOGI", "LOKM", "LOLA", "LOMA", "LON", "LOOP",
            "LOPE", "LORL", "LOT", "LOTZ", "LOVE", "LOW", "LPCN", "LPG", "LPI",
            "LPL", "LPLA", "LPSN", "LPTV", "LPX", "LQD", "LQDA", "LQDT", "LR",
            "LRCX", "LRFC", "LRGE", "LRMR", "LRN", "LRNZ", "LSAK", "LSBK", "LSCC",
            "LSEA", "LSEAW", "LSF", "LSI", "LSPD", "LSTR", "LSXMA", "LSXMB",
            "LSXMK", "LTBR", "LTC", "LTCH", "LTH", "LTHM", "LTL", "LTLS", "LTM",
            "LTRN", "LTRPA", "LTRPB", "LTRX", "LTRY", "LU", "LUCD", "LUCK", "LULU",
            "LUMO", "LUNA", "LUNG", "LUV", "LVAC", "LVLU", "LVO", "LVOX", "LVRO",
            "LVS", "LVTX", "LVWR", "LW", "LWAY", "LX", "LXEH", "LXFR", "LXP",
            "LXRX", "LXU", "LYB", "LYEL", "LYFT", "LYG", "LYL", "LYLT", "LYRA",
            "LYTS", "LYV", "LZ", "LZAG", "LZEA", "LZGI", "LZRG", "LZWS", "M",
            "MA", "MAA", "MAAV", "MAC", "MACE", "MACK", "MAG", "MAGA", "MAGN",
            "MAIN", "MAMB", "MAN", "MANH", "MANT", "MANU", "MAPS", "MAQC", "MAR",
            "MARA", "MARK", "MARPS", "MART", "MARX", "MAS", "MASI", "MASS", "MAT",
            "MATW", "MATX", "MAV", "MAX", "MAXN", "MAXR", "MAYB", "MBC", "MBCN",
            "MBII", "MBIN", "MBINN", "MBINO", "MBINP", "MBIO", "MBI", "MBOT",
            "MBRX", "MBSC", "MBTC", "MBUU", "MBWM", "MC", "MCA", "MCAA", "MCB",
            "MCBC", "MCBS", "MCD", "MCF", "MCFT", "MCHP", "MCHX", "MCI", "MCK",
            "MCMJ", "MCN", "MCO", "MCR", "MCRB", "MCRI", "MCS", "MCW", "MCY",
            "MD", "MDB", "MDC", "MDGL", "MDGS", "MDH", "MDIA", "MDIV", "MDJH",
            "MDL", "MDLZ", "MDNA", "MDRR", "MDRX", "MDT", "MDU", "MDWD", "MDXG",
            "MDXH", "ME", "MEC", "MED", "MEDP", "MEDS", "MEG", "MEGI", "MEI",
            "MEIP", "MEKA", "MELI", "MEM", "MEOH", "MER", "MERC", "MESA", "MESO",
            "MET", "META", "METF", "METX", "MEXX", "MF", "MFA", "MFC", "MFD",
            "MFG", "MFGP", "MFH", "MFIC", "MFIN", "MFM", "MFMS", "MFNC", "MFSF",
            "MFT", "MFV", "MG", "MGA", "MGEE", "MGEN", "MGI", "MGIC", "MGK",
            "MGLD", "MGM", "MGNI", "MGNX", "MGP", "MGPI", "MGR", "MGRB", "MGRC",
            "MGRI", "MGRM", "MGS", "MGTA", "MGTX", "MGY", "MGYR", "MHD", "MHF",
            "MHH", "MHI", "MHK", "MHLA", "MHLD", "MHN", "MHNC", "MHO", "MHP",
            "MHR", "MHS", "MHT", "MHY", "MI", "MICT", "MIDD", "MIDU", "MIE",
            "MIGI", "MII", "MILN", "MIMO", "MINT", "MIR", "MIRM", "MIST", "MIT",
            "MITK", "MITT", "MIXT", "MIY", "MJO", "MKAM", "MKC", "MKC.V", "MKD",
            "MKL", "MKOR", "MKSI", "MKTW", "MKTX", "ML", "MLAB", "MLAC", "MLCO",
            "MLI", "MLKN", "MLM", "MLNK", "MLP", "MLR", "MLSS", "MLTX", "MLVF",
            "MMAT", "MMC", "MMD", "MMI", "MMLP", "MMM", "MMMB", "MMP", "MMS",
            "MMSI", "MMT", "MMU", "MMX", "MN", "MNDO", "MNDT", "MNE", "MNKD",
            "MNMD", "MNN", "MNOV", "MNP", "MNPR", "MNRL", "MNSB", "MNSBP", "MNST",
            "MNTS", "MNTX", "MO", "MOBQ", "MOBV", "MOB", "MOD", "MODG", "MODN",
            "MODV", "MOFG", "MOGO", "MOGU", "MOH", "MOLN", "MOMO", "MOO", "MOR",
            "MORF", "MORN", "MOS", "MOSS", "MOT", "MOTS", "MOV", "MOVE", "MP",
            "MPA", "MPAA", "MPB", "MPC", "MPLN", "MPLX", "MPW", "MPWR", "MPX",
            "MQ", "MRAI", "MRAM", "MRBK", "MRC", "MRCC", "MRCY", "MREO", "MRIN",
            "MRK", "MRKR", "MRM", "MRNA", "MRNS", "MRO", "MRSN", "MRTN", "MRTX",
            "MRUS", "MRVI", "MRVL", "MS", "MSA", "MSB", "MSBI", "MSC", "MSCI",
            "MSD", "MSDA", "MSEX", "MSFT", "MSGE", "MSGM", "MSGS", "MSI", "MSM",
            "MSN", "MSP", "MSSA", "MSSS", "MSTR", "MSVX", "MT", "MTA", "MTAC",
            "MTB", "MTBC", "MTBCP", "MTC", "MTCH", "MTCR", "MTD", "MTDR", "MTEK",
            "MTEM", "MTEX", "MTG", "MTH", "MTL", "MTLS", "MTN", "MTNB", "MTOR",
            "MTP", "MTR", "MTRN", "MTRX", "MTSI", "MTTR", "MTW", "MTX", "MTZ",
            "MU", "MUA", "MUB", "MUC", "MUE", "MUFG", "MUI", "MUJ", "MULN",
            "MUN", "MUR", "MUSA", "MUSI", "MUST", "MUX", "MVBF", "MVF", "MVI",
            "MVIS", "MVST", "MVT", "MWA", "MX", "MXC", "MXCT", "MXE", "MXF",
            "MXL", "MYD", "MYE", "MYFW", "MYGN", "MYI", "MYMD", "MYN", "MYNA",
            "MYNZ", "MYO", "MYOV", "MYPS", "MYRG", "MYSZ", "MYTE", "NA", "NAAC",
            "NAAS", "NABL", "NAC", "NAD", "NAII", "NAK", "NAN", "NANR", "NAOV",
            "NAPA", "NARI", "NAT", "NATH", "NATI", "NATR", "NAUT", "NAVB", "NAVI",
            "NBR", "NBRV", "NBSE", "NBST", "NBXG", "NC", "NCA", "NCAC", "NCBS",
            "NCL", "NCLH", "NCMI", "NCNA", "NCNO", "NCPB", "NCPL", "NCR", "NCSM",
            "NCTY", "NCV", "NCZ", "NDAC", "NDAQ", "NDLS", "NDMO", "NDP", "NDRA",
            "NDSN", "NE", "NEA", "NEE", "NEGG", "NEM", "NEN", "NEO", "NEOG",
            "NEON", "NEOV", "NEP", "NEPH", "NEPT", "NERV", "NESR", "NET", "NETC",
            "NETI", "NETL", "NEU", "NEUE", "NEV", "NEW", "NEWP", "NEWT", "NEX",
            "NEXI", "NEXN", "NEXT", "NFBK", "NFE", "NFG", "NFGC", "NFLX", "NFTG",
            "NFYS", "NG", "NGC", "NGD", "NGE", "NGG", "NGL", "NGS", "NGVC",
            "NGVT", "NH", "NHC", "NHI", "NHIC", "NHLD", "NHS", "NHTC", "NI",
            "NICE", "NICK", "NID", "NIE", "NIM", "NIO", "NIU", "NJAN", "NJUL",
            "NKE", "NKLA", "NKSH", "NKTR", "NKTX", "NL", "NLIT", "NLOK", "NLR",
            "NLS", "NLSN", "NLSP", "NLTX", "NLY", "NM", "NMAI", "NMCO", "NMD",
            "NMFC", "NMG", "NMI", "NMIH", "NMIV", "NML", "NMM", "NMR", "NMRD",
            "NMRK", "NMS", "NMT", "NMTC", "NMZ", "NN", "NNA", "NNBR", "NNDM",
            "NNE", "NNI", "NNN", "NNOX", "NNVC", "NOA", "NOAC", "NOAH", "NOBL",
            "NOC", "NODK", "NOG", "NOK", "NOM", "NOMD", "NORW", "NOTV", "NOV",
            "NOVA", "NOVN", "NOVT", "NOVV", "NOVZ", "NPAB", "NPCT", "NPFD", "NPK",
            "NPO", "NPPC", "NPTN", "NPV", "NQP", "NR", "NRAC", "NRBO", "NRC",
            "NRCG", "NRDS", "NRDY", "NREF", "NRG", "NRGV", "NRIM", "NRIX", "NRK",
            "NRO", "NRP", "NRSN", "NRT", "NRUC", "NRXP", "NS", "NSA", "NSC",
            "NSEC", "NSIT", "NSP", "NSPR", "NSSC", "NSTC", "NSTG", "NSTS", "NSYS",
            "NTAP", "NTB", "NTBL", "NTCO", "NTCT", "NTES", "NTEST", "NTGR", "NTIC",
            "NTIP", "NTLA", "NTNX", "NTR", "NTRB", "NTRP", "NTRS", "NTSX", "NTUS",
            "NTWK", "NU", "NUBI", "NUE", "NUGO", "NULG", "NULV", "NUM", "NUO",
            "NUS", "NUSC", "NUV", "NUVA", "NUVB", "NUVL", "NUW", "NUWE", "NUZE",
            "NVAX", "NVCN", "NVCR", "NVCT", "NVDA", "NVEC", "NVEE", "NVEI", "NVET",
            "NVGS", "NVIV", "NVMI", "NVNO", "NVO", "NVOS", "NVRO", "NVR", "NVRI",
            "NVRO", "NVSA", "NVST", "NVT", "NVTA", "NVTS", "NVVE", "NVX", "NWBI",
            "NWE", "NWFL", "NWG", "NWL", "NWLI", "NWN", "NWPX", "NWS", "NWSA",
            "NX", "NXC", "NXDT", "NXE", "NXGL", "NXGN", "NXI", "NXJ", "NXN",
            "NXP", "NXPL", "NXRT", "NXST", "NXT", "NXTC", "NXTG", "NYC", "NYCB",
            "NYMT", "NYMX", "NYT", "NYXH", "NZF", "O", "OACB", "OAKU", "OAS",
            "OASP", "OAS", "OB", "OBCI", "OBE", "OBIO", "OBLG", "OBNK", "OBSV",
            "OC", "OCC", "OCCI", "OCDX", "OCFC", "OCFCP", "OCG", "OCN", "OCSL",
            "OCUL", "OCUP", "OCX", "ODC", "ODFL", "ODP", "OEC", "OESX", "OFED",
            "OFG", "OFIX", "OFLX", "OFS", "OG", "OGE", "OGI", "OGN", "OGS",
            "OHI", "OI", "OII", "OIIM", "OIS", "OKE", "OKTA", "OLB", "OLED",
            "OLK", "OLLI", "OLMA", "OLN", "OLO", "OLP", "OLPX", "OM", "OMAB",
            "OMC", "OMCL", "OMER", "OMEX", "OMF", "OMGA", "OMI", "OMIC", "OMQS",
            "ON", "ONB", "ONBPO", "ONBPP", "ONCR", "ONCS", "ONCT", "ONCY", "ONE",
            "ONEO", "ONEW", "ONL", "ONON", "ONTF", "ONTO", "ONTX", "ONVO", "OOMA",
            "OP", "OPAD", "OPAL", "OPBK", "OPCH", "OPEN", "OPFI", "OPHC", "OPI",
            "OPINL", "OPK", "OPNT", "OPOF", "OPRA", "OPRT", "OPRX", "OPT", "OPTN",
            "OPTT", "OPY", "OR", "ORA", "ORAN", "ORC", "ORCC", "ORCL", "ORGN",
            "ORGO", "ORGS", "ORI", "ORIC", "ORLA", "ORLY", "ORMP", "ORN", "ORRF",
            "ORTX", "OSBC", "OSCR", "OSG", "OSIS", "OSK", "OSPN", "OSS", "OST",
            "OSTK", "OSUR", "OSW", "OTEX", "OTIC", "OTIS", "OTLK", "OTLY", "OTRK",
            "OTTR", "OUST", "OUT", "OVBC", "OVID", "OVV", "OWL", "OWLT", "OXAC",
            "OXBR", "OXFD", "OXLC", "OXM", "OXSQ", "OXY", "OYST", "OZK", "OZON",
            "P", "PAAS", "PAC", "PACB", "PACW", "PACK", "PAGS", "PAHC", "PAL",
            "PALI", "PALL", "PALT", "PAM", "PANL", "PANW", "PAPL", "PAR", "PARA",
            "PARAA", "PARR", "PASG", "PATH", "PATK", "PAVM", "PAX", "PAY", "PAYC",
            "PAYO", "PAYS", "PB", "PBA", "PBBK", "PBD", "PBE", "PBFS", "PBH",
            "PBHC", "PBI", "PBJ", "PBLA", "PBPB", "PBR", "PBR.A", "PBS", "PBSV",
            "PBT", "PBTP", "PBW", "PCAR", "PCB", "PCBK", "PCCW", "PCEF", "PCG",
            "PCH", "PCI", "PCK", "PCM", "PCN", "PCQ", "PCRX", "PCSB", "PCT",
            "PCTI", "PCTTU", "PCTY", "PCVX", "PCYG", "PCYO", "PD", "PDBC", "PDCO",
            "PDD", "PDEX", "PDFS", "PDI", "PDLB", "PDM", "PDN", "PDO", "PDP",
            "PDS", "PDSB", "PDT", "PEAK", "PEB", "PEBK", "PEBO", "PECO", "PED",
            "PEG", "PEGA", "PEGR", "PEGY", "PEJ", "PEN", "PENN", "PEO", "PEP",
            "PEPL", "PERF", "PERI", "PESI", "PETQ", "PETS", "PETZ", "PEY", "PEZ",
            "PFBC", "PFC", "PFD", "PFE", "PFF", "PFFA", "PFFD", "PFFL", "PFFR",
            "PFFV", "PFG", "PFGC", "PFH", "PFI", "PFIE", "PFIN", "PFIS", "PFL",
            "PFLT", "PFM", "PFMT", "PFN", "PFO", "PFSA", "PFSI", "PFS", "PFSW",
            "PG", "PGC", "PGEN", "PGNY", "PGR", "PGRE", "PGRW", "PGTI", "PGX",
            "PH", "PHAR", "PHAS", "PHAT", "PHB", "PHCF", "PHD", "PHDG", "PHG",
            "PHGE", "PHI", "PHIO", "PHK", "PHM", "PHO", "PHR", "PHUN", "PHVS",
            "PI", "PIAI", "PIC", "PICK", "PICO", "PII", "PILL", "PIM", "PIN",
            "PINC", "PINE", "PINK", "PINS", "PIPR", "PIRS", "PIXY", "PIZ", "PJT",
            "PK", "PKB", "PKBK", "PKE", "PKG", "PKI", "PKOH", "PKST", "PKX",
            "PL", "PLAB", "PLAG", "PLAN", "PLAY", "PLBC", "PLBY", "PLCE", "PLD",
            "PLG", "PLL", "PLM", "PLMR", "PLNT", "PLOW", "PLRX", "PLSE", "PLTK",
            "PLTR", "PLUG", "PLUS", "PLX", "PLXP", "PLXS", "PLYA", "PM", "PMCB",
            "PMD", "PME", "PMF", "PML", "PMM", "PMO", "PMT", "PMTS", "PMVP",
            "PMX", "PNBK", "PNC", "PNFP", "PNFPP", "PNI", "PNM", "PNNT", "PNR",
            "PNRG", "PNST", "PNT", "PNTG", "PNTM", "PNW", "POAI", "PODD", "POET",
            "POL", "POLA", "POOL", "POR", "PORT", "POST", "POTX", "POW", "POWI",
            "POWL", "POWW", "PPBI", "PPBT", "PPC", "PPG", "PPGH", "PPHP", "PPIH",
            "PPL", "PPSI", "PPT", "PPTA", "PPX", "PQG", "PQIN", "PR", "PRA",
            "PRAA", "PRAX", "PRB", "PRCH", "PRCT", "PRDO", "PRDS", "PRE", "PRFT",
            "PRFX", "PRG", "PRGO", "PRGS", "PRI", "PRIM", "PRK", "PRLB", "PRLD",
            "PRLH", "PRM", "PRMW", "PRN", "PRO", "PROC", "PROF", "PROK", "PROV",
            "PRPB", "PRPH", "PRPL", "PRPO", "PRQR", "PRS", "PRT", "PRTA", "PRTC",
            "PRTG", "PRTH", "PRTS", "PRTY", "PRU", "PRVA", "PRVB", "PSA", "PSB",
            "PSC", "PSCC", "PSCD", "PSCE", "PSCF", "PSCH", "PSCI", "PSCT", "PSEC",
            "PSF", "PSFE", "PSI", "PSJ", "PSL", "PSLV", "PSMB", "PSMC", "PSMD",
            "PSMG", "PSMM", "PSMT", "PSN", "PSNL", "PSO", "PST", "PSTG", "PSTL",
            "PSTP", "PSTX", "PSX", "PSXP", "PT", "PTC", "PTCT", "PTE", "PTEN",
            "PTF", "PTGX", "PTH", "PTIC", "PTIX", "PTLC", "PTLO", "PTMN", "PTN",
            "PTNR", "PTON", "PTPI", "PTR", "PTRA", "PTRS", "PTSI", "PTVE", "PTWO",
            "PUBM", "PUCK", "PULM", "PUMP", "PUNK", "PURE", "PURI", "PUYI", "PV",
            "PVBC", "PVG", "PVH", "PVL", "PW", "PWFL", "PWOD", "PWP", "PWR",
            "PWS", "PWSC", "PYCR", "PYPD", "PYPL", "PYT", "PYX", "PZC", "PZG",
            "PZN", "PZZA", "QABA", "QAT", "QBTS", "QCLN", "QCOM", "QCRH", "QD",
            "QDEL", "QDEV", "QEFA", "QEMA", "QEP", "QEPC", "QEMM", "QES", "QETF",
            "QFIN", "QGEN", "QGRO", "QH", "QHY", "QID", "QINT", "QIPT", "QK",
            "QLC", "QLD", "QLGN", "QLI", "QLTA", "QLV", "QMAR", "QMCO", "QMN",
            "QMOM", "QNST", "QNRX", "QNT", "QNTA", "QNTM", "QNWG", "QOCT", "QOM",
            "QQQ", "QQQA", "QQQE", "QQQG", "QQQJ", "QQQM", "QQQX", "QQXT", "QRHC",
            "QRTEA", "QRTEB", "QRTEP", "QRVO", "QS", "QSI", "QSR", "QSWN", "QTEC",
            "QTNT", "QTRX", "QTT", "QTUM", "QUAD", "QUAL", "QUIK", "QULL", "QURE",
            "QUS", "QVAL", "QVCC", "QVCD", "QWLD", "R", "RA", "RACE", "RAD",
            "RADA", "RAIL", "RAMP", "RAND", "RAPT", "RARE", "RARR", "RAS", "RAVE",
            "RAVI", "RBBN", "RBC", "RBCAA", "RBCN", "RBKB", "RBLX", "RBNC", "RBOT",
            "RC", "RCAT", "RCEL", "RCFA", "RCHG", "RCI", "RCII", "RCKT", "RCKY",
            "RCL", "RCLF", "RCM", "RCMT", "RCON", "RCRT", "RCS", "RCUS", "RDBX",
            "RDCM", "RDFN", "RDN", "RDNT", "RDS.A", "RDS.B", "RDUS", "RDVT", "RDW",
            "RDWR", "RDY", "RE", "REAL", "REAX", "REDU", "REED", "REET", "REFR",
            "REG", "REGN", "REI", "REIT", "REKR", "RELI", "RELL", "RELX", "RELY",
            "RENN", "RENT", "REPH", "REPL", "RES", "RETA", "RETO", "REV", "REVB",
            "REVG", "REVH", "REX", "REXR", "REYN", "RF", "RFAC", "RFDA", "RFEM",
            "RFEU", "RFIL", "RFL", "RFM", "RFMZ", "RFP", "RFUN", "RGA", "RGC",
            "RGCO", "RGEN", "RGF", "RGI", "RGLD", "RGLS", "RGNX", "RGP", "RGR",
            "RGS", "RGT", "RGTI", "RH", "RHE", "RHI", "RHP", "RHRX", "RIBT",
            "RICK", "RIDE", "RIG", "RIGL", "RILY", "RILYG", "RILYK", "RILYL",
            "RILYM", "RILYN", "RILYO", "RILYP", "RILYT", "RILYZ", "RINF", "RING",
            "RIO", "RIOT", "RIV", "RIVN", "RJF", "RKLB", "RKLY", "RKT", "RL",
            "RLAY", "RLGT", "RLGY", "RLI", "RLJ", "RLMD", "RLX", "RM", "RMAX",
            "RMBI", "RMBL", "RMBS", "RMCF", "RMGC", "RMI", "RMM", "RMP", "RMR",
            "RMRM", "RMT", "RMTI", "RNDV", "RNG", "RNGR", "RNLC", "RNLX", "RNP",
            "RNR", "RNST", "RNW", "RNWK", "RNXT", "ROAD", "ROCK", "ROCL", "ROG",
            "ROIC", "ROIV", "ROK", "ROKU", "ROL", "ROLL", "ROM", "ROOT", "ROP",
            "ROST", "ROVR", "RPAY", "RPD", "RPHM", "RPM", "RPRX", "RPT", "RPTX",
            "RQI", "RRAC", "RRC", "RRD", "RRGB", "RRGB", "RRR", "RS", "RSG",
            "RSI", "RSKD", "RSLS", "RSSS", "RSVR", "RSX", "RTX", "RUBY", "RUN",
            "RUSHA", "RUSHB", "RUTH", "RVAC", "RVLP", "RVLV", "RVMD", "RVNC",
            "RVP", "RVPH", "RVSB", "RVT", "RVTY", "RW", "RWL", "RWLK", "RWT",
            "RXDX", "RXRX", "RXST", "RXT", "RY", "RYAAY", "RYAM", "RYAN", "RYB",
            "RYI", "RYJ", "RYN", "RZLT", "S", "SA", "SABR", "SABS", "SACH",
            "SAFE", "SAFM", "SAFT", "SAGE", "SAH", "SAIA", "SAIC", "SAIL", "SAL",
            "SALM", "SAM", "SAMG", "SAN", "SANA", "SAND", "SANM", "SANW", "SAP",
            "SAR", "SASR", "SAT", "SATS", "SAVA", "SAVE", "SB", "SBAC", "SBBA",
            "SBE", "SBEV", "SBFG", "SBFM", "SBFMW", "SBI", "SBIO", "SBLK", "SBNY",
            "SBNYP", "SBOW", "SBR", "SBRA", "SBS", "SBSI", "SBT", "SBUX", "SC",
            "SCCO", "SCD", "SCE", "SCE", "SCHL", "SCHN", "SCHP", "SCHV", "SCHW",
            "SCI", "SCKT", "SCL", "SCLE", "SCM", "SCOR", "SCPH", "SCPL", "SCS",
            "SCSC", "SCU", "SCVL", "SCWO", "SCWX", "SCX", "SCYX", "SD", "SDAC",
            "SDC", "SDGR", "SDHC", "SDIG", "SDPI", "SDRL", "SDY", "SE", "SEAC",
            "SEAS", "SEAT", "SECO", "SEDG", "SEE", "SEED", "SEEL", "SEER", "SEIC",
            "SELB", "SELF", "SEM", "SEMR", "SENEA", "SENEB", "SENS", "SERA", "SES",
            "SESN", "SES", "SF", "SFBC", "SFBS", "SFET", "SFIX", "SFL", "SFLM",
            "SFM", "SFNC", "SFST", "SFT", "SGA", "SGBX", "SGC", "SGD", "SGEN",
            "SGH", "SGLY", "SGMA", "SGML", "SGMO", "SGRP", "SGRY", "SGU", "SH",
            "SHBI", "SHC", "SHCR", "SHE", "SHEN", "SHG", "SHI", "SHIP", "SHLS",
            "SHO", "SHOO", "SHOP", "SHPW", "SHUA", "SHW", "SHYF", "SI", "SIAF",
            "SID", "SIEB", "SIEN", "SIF", "SIG", "SIGA", "SIGI", "SII", "SIL",
            "SILC", "SILK", "SILV", "SIM", "SIMO", "SINT", "SIRI", "SITC", "SITE",
            "SITM", "SIVB", "SIX", "SJ", "SJI", "SJIJ", "SJIV", "SJM", "SJNK",
            "SJT", "SJW", "SK", "SKIL", "SKIN", "SKLZ", "SKM", "SKOR", "SKT",
            "SKX", "SKY", "SKYA", "SKYH", "SKYT", "SKYW", "SLAB", "SLAC", "SLAM",
            "SLB", "SLCA", "SLDB", "SLDP", "SLF", "SLG", "SLGC", "SLGG", "SLGL",
            "SLGN", "SLI", "SLM", "SLN", "SLNG", "SLNH", "SLNO", "SLP", "SLQT",
            "SLRC", "SLRX", "SLS", "SLVM", "SM", "SMAR", "SMBC", "SMBK", "SMCI",
            "SMCP", "SMED", "SMFG", "SMG", "SMHI", "SMID", "SMI", "SMIT", "SMLP",
            "SMLR", "SMM", "SMMF", "SMMT", "SMP", "SMPL", "SMR", "SMRT", "SMSI",
            "SMTC", "SMTI", "SMTS", "SMURF", "SMWB", "SNA", "SNAK", "SNAP", "SND",
            "SNDL", "SNDX", "SNES", "SNEX", "SNFCA", "SNGX", "SNN", "SNOA", "SNOW",
            "SNP", "SNPO", "SNPS", "SNPX", "SNRH", "SNSE", "SNV", "SNX", "SNY",
            "SO", "SOAR", "SOBR", "SOC", "SOFI", "SOFO", "SOG", "SOHO", "SOHOB",
            "SOHON", "SOHOO", "SOHU", "SOI", "SOIL", "SOL", "SOLO", "SON", "SOND",
            "SONM", "SONN", "SONO", "SONY", "SOPA", "SOR", "SOS", "SOTK", "SOUN",
            "SOVO", "SP", "SPAB", "SPB", "SPCB", "SPCE", "SPCM", "SPD", "SPE",
            "SPEM", "SPEU", "SPFI", "SPG", "SPGI", "SPGM", "SPH", "SPHB", "SPHD",
            "SPHQ", "SPHY", "SPI", "SPIB", "SPIP", "SPIR", "SPK", "SPKB", "SPLG",
            "SPLK", "SPLV", "SPMD", "SPNS", "SPNT", "SPOK", "SPOT", "SPPI", "SPR",
            "SPRB", "SPRC", "SPRO", "SPRX", "SPRY", "SPSC", "SPT", "SPTI", "SPTN",
            "SPTS", "SPWH", "SPWR", "SPXC", "SPXX", "SQ", "SQFT", "SQFTP", "SQL",
            "SQLL", "SQM", "SQNS", "SQSP", "SR", "SRAD", "SRAX", "SRC", "SRCE",
            "SRCL", "SRDX", "SRE", "SREA", "SRET", "SRG", "SRGA", "SRI", "SRL",
            "SRNE", "SRNG", "SRPT", "SRRA", "SRRK", "SRSA", "SRSR", "SRT", "SRTS",
            "SRTY", "SRZN", "SSAA", "SSB", "SSBI", "SSBK", "SSD", "SSIC", "SSKN",
            "SSL", "SSNC", "SSNT", "SSP", "SSRM", "SSSS", "SST", "SSTI", "SSTK",
            "SSY", "SSYS", "ST", "STAA", "STAB", "STAF", "STAG", "STAR", "STBA",
            "STC", "STCN", "STE", "STEM", "STEP", "STER", "STET", "STG", "STGW",
            "STIM", "STK", "STKL", "STKS", "STLA", "STLD", "STLK", "STM", "STMP",
            "STN", "STNE", "STNG", "STOK", "STON", "STOR", "STP", "STPC", "STRA",
            "STRL", "STRM", "STRN", "STRO", "STRR", "STRS", "STRT", "STSA", "STSS",
            "STT", "STTK", "STVN", "STWD", "STX", "STXS", "STZ", "SU", "SUAC",
            "SUI", "SUM", "SUMO", "SUN", "SUNL", "SUNW", "SUP", "SUPN", "SUPV",
            "SURF", "SURG", "SUZ", "SVC", "SVFA", "SVFD", "SVM", "SVRA", "SVRE",
            "SVS", "SVT", "SVVC", "SWAG", "SWAN", "SWAR", "SWAV", "SWBI", "SWCH",
            "SWET", "SWI", "SWIM", "SWIR", "SWK", "SWKH", "SWKS", "SWM", "SWN",
            "SWSS", "SWTX", "SWVL", "SWX", "SWZ", "SXC", "SXI", "SXTC", "SXT",
            "SXTP", "SY", "SYBX", "SYF", "SYK", "SYN", "SYNA", "SYNH", "SYNL",
            "SYPR", "SYRS", "SYTA", "SYX", "SYY", "SZC", "SZNE", "T", "TA",
            "TAC", "TACT", "TAIT", "TAK", "TAL", "TALK", "TALO", "TAN", "TANNI",
            "TANNL", "TANNZ", "TAOP", "TAP", "TARO", "TARS", "TAST", "TAT", "TATT",
            "TAYD", "TBB", "TBBK", "TBC", "TBD", "TBI", "TBIO", "TBK", "TBLA",
            "TBLT", "TBNK", "TBPH", "TBRG", "TBSA", "TC", "TCBC", "TCBI", "TCBIO",
            "TCBK", "TCBS", "TCCO", "TCI", "TCMD", "TCN", "TCOM", "TCPC", "TCRR",
            "TCRT", "TCRX", "TCS", "TCVA", "TD", "TDC", "TDCX", "TDF", "TDG",
            "TDS", "TDUP", "TDW", "TDY", "TEAF", "TEAM", "TECH", "TECTP", "TEDU",
            "TEF", "TEI", "TEL", "TELA", "TELZ", "TEN", "TENB", "TENX", "TEO",
            "TER", "TERP", "TESS", "TFC", "TFF", "TFII", "TFIN", "TFINP", "TFSA",
            "TFSL", "TFX", "TG", "TGAA", "TGAN", "TGC", "TGEN", "TGLS", "TGN",
            "TGP", "TGS", "TGT", "TGTX", "TGVC", "TH", "THC", "THCH", "THCP",
            "THFF", "THG", "THM", "THO", "THQ", "THR", "THRM", "THRN", "THRX",
            "THS", "THTX", "THW", "TI", "TIG", "TIGO", "TIGR", "TIIX", "TIL",
            "TILE", "TIMB", "TINV", "TIOA", "TIPT", "TIRX", "TISI", "TITN", "TIVC",
            "TIXT", "TJX", "TK", "TKAT", "TKC", "TKLF", "TKNO", "TKR", "TLGA",
            "TLGY", "TLH", "TLIS", "TLK", "TLMD", "TLRY", "TLS", "TLSA", "TLT",
            "TLYS", "TM", "TMC", "TMCI", "TMDX", "TME", "TMHC", "TMKR", "TMO",
            "TMP", "TMPM", "TMQ", "TMST", "TMT", "TMUS", "TMX", "TNC", "TNDM",
            "TNET", "TNGX", "TNK", "TNL", "TNP", "TNXP", "TNYA", "TOI", "TOL",
            "TOMZ", "TOON", "TOP", "TOPS", "TORC", "TORO", "TOT", "TOTA", "TOTL",
            "TOUR", "TOWN", "TPB", "TPC", "TPG", "TPH", "TPHS", "TPIC", "TPR",
            "TPST", "TPTA", "TPVG", "TPX", "TPZ", "TR", "TRAK", "TRC", "TRCA",
            "TRDA", "TRDG", "TREE", "TREX", "TRGP", "TRHC", "TRI", "TRIB", "TRIN",
            "TRIP", "TRIS", "TRKA", "TRMB", "TRMD", "TRMK", "TRMR", "TRN", "TRNO",
            "TRNS", "TRON", "TROO", "TROW", "TROX", "TRP", "TRS", "TRST", "TRT",
            "TRTX", "TRU", "TRUE", "TRUP", "TRV", "TRVG", "TRVI", "TRVN", "TRX",
            "TS", "TSAT", "TSBK", "TSCO", "TSE", "TSEM", "TSHA", "TSI", "TSIB",
            "TSLA", "TSLX", "TSM", "TSN", "TSQ", "TSRI", "TSVT", "TT", "TTC",
            "TTCF", "TTD", "TTE", "TTEC", "TTEK", "TTGT", "TTI", "TTM", "TTMI",
            "TTNP", "TTOO", "TTP", "TTSH", "TTWO", "TU", "TUP", "TUR", "TURN",
            "TUSA", "TUSK", "TUYA", "TV", "TVC", "TVE", "TVTX", "TW", "TWB",
            "TWC", "TWCB", "TWIN", "TWKS", "TWLO", "TWLV", "TWLVU", "TWND", "TWNK",
            "TWOU", "TWST", "TWT", "TWTR", "TX", "TXG", "TXMD", "TXN", "TXRH",
            "TXT", "TY", "TYD", "TYG", "TYL", "TYME", "TYRA", "TZOO", "U",
            "UA", "UAA", "UAL", "UAMY", "UAN", "UAPR", "UAVS", "UBA", "UBCP",
            "UBER", "UBFO", "UBOH", "UBOT", "UBP", "UBS", "UBSI", "UBX", "UCBI",
            "UCBIO", "UCC", "UCL", "UCO", "UCON", "UCTT", "UDN", "UDOW", "UDR",
            "UE", "UEC", "UEIC", "UEVM", "UFAB", "UFCS", "UFI", "UFO", "UFPI",
            "UFPT", "UFS", "UG", "UGI", "UGP", "UGRO", "UHAL", "UHS", "UHT",
            "UI", "UIS", "UK", "UL", "ULBI", "ULCC", "ULE", "ULH", "ULST",
            "ULTA", "UMBF", "UMC", "UMDD", "UMH", "UMI", "UMPQ", "UNAM", "UNB",
            "UNCY", "UNF", "UNFI", "UNH", "UNIT", "UNL", "UNM", "UNMA", "UNP",
            "UNTY", "UONE", "UONEK", "UP", "UPAR", "UPC", "UPH", "UPLD", "UPS",
            "UPST", "UPTD", "UPW", "UPWK", "URA", "URBN", "URE", "URG", "URGN",
            "URI", "UROY", "USA", "USAC", "USAI", "USAP", "USAS", "USAU", "USB",
            "USCB", "USCI", "USCT", "USDU", "USEA", "USEG", "USFD", "USGO", "USIO",
            "USLM", "USM", "USMC", "USMF", "USMI", "USMV", "USOI", "USPH", "USRT",
            "UST", "USVM", "USX", "UTAA", "UTEN", "UTES", "UTF", "UTG", "UTHR",
            "UTI", "UTL", "UTMD", "UTME", "UTRS", "UTSI", "UTZ", "UUA", "UUP",
            "UUU", "UVE", "UVSP", "UVV", "UWMC", "UXIN", "UYLD", "UZA", "UZB",
            "V", "VABK", "VAC", "VACC", "VAL", "VALE", "VALN", "VALU", "VAMO",
            "VAPO", "VAQC", "VATE", "VAW", "VB", "VBF", "VBFC", "VBIV", "VBLT",
            "VBND", "VBNK", "VBR", "VBTX", "VC", "VCEL", "VCIF", "VCIT", "VCLT",
            "VCNX", "VCSA", "VCSH", "VCTR", "VCV", "VCXA", "VCXB", "VCYT", "VEC",
            "VECO", "VEDU", "VEEE", "VEEV", "VEL", "VENA", "VENB", "VENC", "VEND",
            "VENE", "VENF", "VENG", "VENI", "VENU", "VEON", "VERA", "VERB", "VERC",
            "VERF", "VERI", "VERO", "VERU", "VERV", "VERX", "VET", "VEV", "VFC",
            "VFF", "VG", "VGI", "VGIT", "VGLT", "VGM", "VGSH", "VGT", "VGZ",
            "VHAI", "VHC", "VHI", "VHNA", "VHNI", "VIA", "VIAC", "VIACA", "VIAV",
            "VICI", "VICR", "VIEW", "VIG", "VIGI", "VINC", "VINO", "VINP", "VIOT",
            "VIPS", "VIR", "VIRC", "VIRI", "VIRT", "VIRX", "VIS", "VISL", "VIST",
            "VITL", "VIV", "VIVE", "VIVK", "VIXM", "VIXY", "VJET", "VKI", "VKQ",
            "VKTX", "VLAT", "VLDR", "VLEE", "VLGEA", "VLN", "VLNS", "VLO", "VLON",
            "VLRS", "VLS", "VLY", "VLYPO", "VLYPP", "VMAR", "VMC", "VMCA", "VMD",
            "VMEO", "VMI", "VMO", "VMW", "VNCE", "VNDA", "VNET", "VNO", "VNOM",
            "VNRX", "VNT", "VNTR", "VOC", "VOD", "VOLT", "VOR", "VORB", "VOX",
            "VOXX", "VOYA", "VPG", "VPV", "VRA", "VRAI", "VRAR", "VRAY", "VRCA",
            "VRDN", "VRE", "VREX", "VRM", "VRME", "VRNS", "VRNT", "VRPX", "VRRM",
            "VRS", "VRSK", "VRSN", "VRTS", "VRTX", "VS", "VSAC", "VSAT", "VSCO",
            "VSDA", "VSEC", "VSH", "VSHG", "VSI", "VSLU", "VSMV", "VSPY", "VSS",
            "VST", "VSTA", "VSTM", "VSTO", "VTA", "VTEX", "VTGN", "VTHR", "VTI",
            "VTIP", "VTIQ", "VTN", "VTNR", "VTR", "VTRS", "VTSI", "VTV", "VTVT",
            "VTWG", "VTWO", "VTWV", "VTYX", "VUG", "VUSE", "VUZI", "VV", "VVI",
            "VVOS", "VVPR", "VVV", "VWOB", "VXRT", "VXUS", "VYGG", "VYGR", "VYNE",
            "VYNT", "VYMI", "VYNE", "VZ", "VZIO", "VZLA", "VZLA", "W", "WAB",
            "WABC", "WAFD", "WAFDP", "WAFU", "WAL", "WALD", "WALDW", "WANT", "WAR",
            "WASH", "WAT", "WATT", "WBA", "WBD", "WBS", "WBS", "WBX", "WCC",
            "WCFB", "WCN", "WD", "WDAY", "WDC", "WDFC", "WDH", "WDI", "WDS",
            "WE", "WEA", "WEAT", "WEBL", "WEBS", "WEC", "WEI", "WEJL", "WEJS",
            "WEL", "WEN", "WERN", "WES", "WETF", "WEX", "WEYS", "WF", "WFC",
            "WFCF", "WFE", "WFRD", "WGO", "WGS", "WH", "WHD", "WHF", "WHG",
            "WHLM", "WHLR", "WHR", "WIA", "WILC", "WIMI", "WINA", "WING", "WINT",
            "WINV", "WIP", "WIRE", "WISA", "WISH", "WIW", "WIX", "WK", "WKEY",
            "WKHS", "WKSP", "WLDN", "WLFC", "WLK", "WLKP", "WLY", "WLYB", "WM",
            "WMB", "WMC", "WMG", "WMK", "WMPN", "WMS", "WMT", "WNC", "WNEB",
            "WNNR", "WNS", "WNW", "WOOD", "WOOF", "WOR", "WORK", "WORX", "WOW",
            "WPC", "WPCA", "WPM", "WPP", "WPRT", "WPS", "WRB", "WRB", "WRE",
            "WRK", "WRLD", "WRN", "WSBC", "WSBCP", "WSBF", "WSC", "WSFS", "WSM",
            "WSO", "WSR", "WST", "WSTG", "WT", "WTBA", "WTER", "WTFC", "WTFCM",
            "WTFCP", "WTMA", "WTRG", "WTS", "WTT", "WTTR", "WU", "WULF", "WVE",
            "WVVI", "WW", "WWAC", "WWD", "WWE", "WWW", "WY", "WYNN", "WYY",
            "X", "XAIR", "XB", "XBI", "XBIO", "XBIT", "XCUR", "XEL", "XELA",
            "XELB", "XENE", "XENT", "XERS", "XFIN", "XFLT", "XFOR", "XGN", "XHR",
            "XIN", "XLB", "XLC", "XLE", "XLF", "XLG", "XLI", "XLK", "XLO",
            "XLP", "XLRE", "XLU", "XLV", "XLY", "XM", "XME", "XMHQ", "XMMO",
            "XMPT", "XMTR", "XNET", "XNTK", "XOM", "XONE", "XOS", "XPER", "XPL",
            "XPO", "XPOA", "XPRO", "XRAY", "XRT", "XRX", "XSD", "XSHD", "XSHQ",
            "XSLV", "XSOE", "XSPA", "XT", "XTL", "XTNT", "XTR", "XVV", "XXII",
            "XYF", "XYL", "Y", "YALA", "YANG", "YELP", "YETI", "YEXT", "YGMZ",
            "YI", "YINN", "YJ", "YLD", "YMAB", "YMTX", "YNDX", "YORW", "YOSH",
            "YOTA", "YOTAR", "YOTAU", "YOU", "YPF", "YRD", "YSG", "YTEN", "YTPG",
            "YTRG", "YUM", "YUMC", "YVR", "YY", "Z", "ZBH", "ZBRA", "ZCN",
            "ZD", "ZDGE", "ZEAL", "ZENV", "ZEPP", "ZEST", "ZETA", "ZEUS", "ZG",
            "ZGEN", "ZGN", "ZGRO", "ZIM", "ZIMV", "ZION", "ZIONL", "ZIONO", "ZIONP",
            "ZIP", "ZIXI", "ZK", "ZKH", "ZLAB", "ZM", "ZNH", "ZNTL", "ZOM",
            "ZONE", "ZOOZ", "ZPIN", "ZS", "ZTA", "ZTEK", "ZTO", "ZTR", "ZTS",
            "ZUMZ", "ZUO", "ZURA", "ZURAW", "ZVIA", "ZVO", "ZVSA", "ZVZZT", "ZWET",
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
            
            # Verwende den Previous Close Endpunkt (kostenlos)
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
            f"🎯 Alerts bei +{os.getenv('ALERT_THRESHOLD', '5.0')}% oder mehr"
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
        
        # Konfiguration
        self.max_price = float(os.getenv('MAX_PRICE', '30.0'))
        self.threshold_pct = float(os.getenv('ALERT_THRESHOLD', '5.0'))
        self.cycle_minutes = int(os.getenv('CYCLE_MINUTES', '15'))
        self.min_volume = int(os.getenv('MIN_VOLUME', '10000'))
        
        # Tracking
        self.alerted_stocks: Dict[str, datetime] = {}
        self.all_tickers: List[str] = []
        self.last_ticker_update = None
        
    def is_market_hours(self) -> bool:
        """Prüft ob gerade Marktzeiten sind (Pre-Market, Regular, Post-Market)"""
        now = datetime.now(timezone.utc)
        
        # In EST umrechnen (UTC-4 oder UTC-5)
        # Für die Sommerzeit-Erkennung: März bis November = UTC-4, sonst UTC-5
        is_dst = now.month > 3 and now.month < 11
        utc_offset = 4 if is_dst else 5
        
        est_hour = now.hour - utc_offset
        if est_hour < 0:
            est_hour += 24
        
        est_minute = now.minute
        current_time = est_hour + (est_minute / 60)
        
        # Marktzeiten in EST
        pre_market_start = 4.0    # 4:00
        regular_open = 9.5        # 9:30
        regular_close = 16.0      # 16:00
        post_market_end = 20.0    # 20:00
        
        # Prüfe ob in Pre-Market, Regular oder Post-Market
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
        
        # Prüfe Marktzeiten
        if not self.is_market_hours():
            market_session = self.get_market_session()
            logger.info(f"Außerhalb der Marktzeiten ({market_session}). Warte...")
            return {'elapsed': 0, 'total': 0, 'positive': 0, 'alerts': 0, 'top_movers': []}
        
        # 1. Ticker-Liste aktualisieren
        await self.update_ticker_list()
        
        if not self.all_tickers:
            logger.warning("Keine Ticker zum Scannen gefunden!")
            return {'elapsed': 0, 'total': 0, 'positive': 0, 'alerts': 0, 'top_movers': []}
        
        # 2. Preise holen & filtern
        quotes = await self.api.fetch_snapshot_filtered(self.all_tickers, self.max_price)
        
        # 3. Alerts senden
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
        
        # 4. Stats
        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        positive = sum(1 for q in quotes.values() if q.change_pct > 0)
        
        market_session = self.get_market_session()
        logger.info(f"VVPA Cycle [{market_session}]: {len(quotes)} stocks <${self.max_price}, {positive}↑, {alerts_sent} alerts | {elapsed:.1f}s")
        
        # 5. Zusammenfassung senden
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
        
        # Teste API-Key
        if not await self.api.test_api_key():
            logger.error("❌ API-Key Test fehlgeschlagen! Bitte überprüfen Sie Ihren Polygon API-Key.")
            logger.error("   Gehen Sie zu https://polygon.io/dashboard um Ihren Key zu prüfen.")
            return
        
        # Sende Startnachricht
        await self.telegram.send_startup_message()
        
        cycle_count = 0
        last_market_status = None
        
        try:
            while True:
                cycle_count += 1
                
                # Prüfe Marktstatus
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
                
                # Warte bis zum nächsten Zyklus
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
