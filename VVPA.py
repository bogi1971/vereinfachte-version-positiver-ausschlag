#!/usr/bin/env python3
"""
VVPA - Volume & Volatility Price Alert
Auto-Scan: Alle Biotech & Pharma Aktien < $30
Zyklus: 15 Minuten
"""

import os
import sys
import asyncio
import logging
import json
from datetime import datetime, timezone
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
        self.last_request_time = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=10)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session
    
    async def _rate_limit(self):
        """Rate Limiting für API - 5 Anfragen pro Minute für kostenlosen Plan"""
        if self.last_request_time:
            elapsed = (datetime.now() - self.last_request_time).total_seconds()
            if elapsed < 12:  # 5 pro Minute = 12 Sekunden zwischen Anfragen
                await asyncio.sleep(12 - elapsed)
        self.last_request_time = datetime.now()
    
    async def test_api_key(self) -> bool:
        """Testet ob der API-Key funktioniert"""
        session = await self._get_session()
        url = f"{self.base_url}/v1/meta/symbols/SPY/company"
        params = {"apiKey": self.api_key}
        
        try:
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
        """Hole alle Biotech & Pharma Aktien mit API-Key"""
        session = await self._get_session()
        
        # Relevante SIC Codes für Biotech und Pharma
        # 2834 = Pharmaceutical Preparations
        # 2835 = In Vitro & In Vivo Diagnostic Substances
        # 2836 = Biological Products (No Diagnostic Substances)
        sic_codes = [2834, 2835, 2836]
        
        all_tickers = []
        
        for sic in sic_codes:
            url = f"{self.base_url}/v3/reference/tickers"
            params = {
                "market": "stocks",
                "type": "CS",
                "active": "true",
                "limit": "1000",
                "sic": sic,
                "apiKey": self.api_key
            }
            
            try:
                await self._rate_limit()
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        logger.warning(f"SIC {sic} Fehler: {resp.status}")
                        text = await resp.text()
                        logger.warning(f"Response: {text[:200]}")
                        continue
                    
                    data = await resp.json()
                    results = data.get("results", [])
                    
                    for ticker in results:
                        symbol = ticker.get("ticker", "")
                        name = ticker.get("name", "")
                        # Nur echte Ticker mit max 5 Zeichen
                        if symbol and len(symbol) <= 5 and symbol.isalpha():
                            all_tickers.append(symbol)
                            logger.debug(f"Gefunden: {symbol} - {name}")
                    
                    # Pagination für mehr Ergebnisse
                    next_url = data.get("next_url")
                    while next_url and len(all_tickers) < 2000:
                        await self._rate_limit()
                        next_url_with_key = f"{next_url}&apiKey={self.api_key}"
                        async with session.get(next_url_with_key, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                            if resp.status != 200:
                                break
                            data = await resp.json()
                            for ticker in data.get("results", []):
                                symbol = ticker.get("ticker", "")
                                if symbol and len(symbol) <= 5 and symbol.isalpha():
                                    all_tickers.append(symbol)
                            next_url = data.get("next_url")
                            
            except Exception as e:
                logger.error(f"Fehler beim Laden der Tickers für SIC {sic}: {e}")
        
        # Entferne Duplikate
        unique = list(dict.fromkeys(all_tickers))
        logger.info(f"VVPA: {len(unique)} Biotech/Pharma Tickers gefunden")
        
        # Speichere Liste für Debug
        if unique:
            with open("tickers_debug.json", "w") as f:
                json.dump(unique[:100], f, indent=2)
            logger.info(f"Erste 100 Tickers in tickers_debug.json gespeichert")
        
        return unique
    
    async def fetch_snapshot_filtered(self, symbols: List[str], max_price: float = 30.0) -> Dict[str, PriceAlert]:
        """Hole Preise und filtere nach Preis < max_price"""
        if not symbols:
            return {}
        
        session = await self._get_session()
        all_results = {}
        successful = 0
        failed = 0
        
        logger.info(f"Starte Abruf von {len(symbols)} Tickers...")
        
        for idx, symbol in enumerate(symbols):
            await self._rate_limit()
            
            # Verwende den Previous Close Endpunkt (funktioniert mit kostenlosem API-Key)
            url = f"{self.base_url}/v2/aggs/ticker/{symbol}/prev"
            params = {"adjusted": "true", "apiKey": self.api_key}
            
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("results", [])
                        
                        if results:
                            result = results[0]
                            price = result.get("c", 0)  # Closing price
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
                        # Ticker existiert nicht oder hat keine Daten
                        failed += 1
                        pass
                    else:
                        failed += 1
                        if idx % 50 == 0:  # Nur gelegentlich loggen
                            logger.debug(f"{symbol} Fehler: {resp.status}")
                        
            except asyncio.TimeoutError:
                failed += 1
                logger.debug(f"Timeout bei {symbol}")
            except Exception as e:
                failed += 1
                logger.debug(f"Fehler bei {symbol}: {e}")
            
            # Fortschrittsanzeige alle 100 Ticker
            if (idx + 1) % 100 == 0:
                logger.info(f"Fortschritt: {idx + 1}/{len(symbols)} | Gefunden: {successful}")
        
        logger.info(f"VVPA: {len(all_results)} Aktien unter ${max_price} mit Daten (erfolgreich: {successful}, fehlgeschlagen: {failed})")
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
            f"⏱ Scan alle 15 Minuten während Marktzeiten"
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
    """VVPA - Auto-Scan Biotech & Pharma < $30"""
    
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
        
    async def update_ticker_list(self):
        """Aktualisiere Ticker-Liste einmal pro Woche"""
        now = datetime.now(timezone.utc)
        
        # Update einmal pro Woche (statt täglich)
        if (self.last_ticker_update is None or 
            (now - self.last_ticker_update).days >= 7 or 
            not self.all_tickers):
            
            logger.info("VVPA: Lade Biotech & Pharma Ticker...")
            self.all_tickers = await self.api.get_biotech_pharma_tickers()
            self.last_ticker_update = now
            logger.info(f"VVPA: {len(self.all_tickers)} Ticker im Universum")
    
    def _should_alert(self, alert: PriceAlert) -> bool:
        """Prüfe ob Alert gesendet werden soll"""
        # Threshold prüfen
        if alert.change_pct < self.threshold_pct:
            return False
        
        # Mindestvolumen
        if alert.volume < self.min_volume:
            return False
        
        symbol = alert.symbol
        now = datetime.now(timezone.utc)
        
        # Re-Alert nur nach 15 Minuten (ein Zyklus)
        if symbol in self.alerted_stocks:
            last_alert = self.alerted_stocks[symbol]
            minutes_since = (now - last_alert).total_seconds() / 60
            if minutes_since < self.cycle_minutes:
                return False
        
        return True
    
    async def run_cycle(self) -> dict:
        """Ein kompletter Scan-Zyklus"""
        start = datetime.now(timezone.utc)
        
        # 1. Ticker-Liste aktualisieren (wöchentlich)
        await self.update_ticker_list()
        
        if not self.all_tickers:
            logger.warning("Keine Ticker zum Scannen gefunden!")
            return {'elapsed': 0, 'total': 0, 'positive': 0, 'alerts': 0, 'top_movers': []}
        
        # 2. Preise holen & filtern
        quotes = await self.api.fetch_snapshot_filtered(self.all_tickers, self.max_price)
        
        # 3. Alerts senden
        alerts_sent = 0
        alerts_list = []
        
        # Sortiere nach Change % (höchste zuerst)
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
        
        logger.info(f"VVPA Cycle: {len(quotes)} stocks <${self.max_price}, {positive}↑, {alerts_sent} alerts | {elapsed:.1f}s")
        
        # 5. Zusammenfassung senden (nur wenn es Alerts gab)
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
        """Haupt-Loop - alle 15 Minuten"""
        logger.info("=" * 60)
        logger.info("🚀 VVPA Auto-Scanner gestartet")
        logger.info(f"   Universum: Biotech & Pharma < ${self.max_price}")
        logger.info(f"   Threshold: +{self.threshold_pct}%")
        logger.info(f"   Zyklus: {self.cycle_minutes} Minuten")
        logger.info(f"   Min Volume: {self.min_volume:,}")
        logger.info("=" * 60)
        
        # Teste API-Key
        if not await self.api.test_api_key():
            logger.error("❌ API-Key Test fehlgeschlagen! Bitte überprüfen Sie Ihren Polygon API-Key.")
            logger.error("   Gehen Sie zu https://polygon.io/dashboard um Ihren Key zu prüfen.")
            return
        
        # Sende Startnachricht
        await self.telegram.send_startup_message()
        
        cycle_count = 0
        
        try:
            while True:
                cycle_count += 1
                logger.info(f"\n--- VVPA Zyklus #{cycle_count} ---")
                
                result = await self.run_cycle()
                
                # Warte bis zum nächsten Zyklus
                sleep_seconds = self.cycle_minutes * 60 - result['elapsed']
                if sleep_seconds > 0:
                    logger.info(f"Nächster Zyklus in {sleep_seconds/60:.1f} Minuten...")
                    await asyncio.sleep(sleep_seconds)
                else:
                    logger.warning(f"Zyklus dauerte {result['elapsed']:.1f}s, länger als {self.cycle_minutes} Minuten!")
                    # Kurze Pause vor nächstem Zyklus
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
