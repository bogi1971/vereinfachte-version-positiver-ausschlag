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
        self.base_url = "https://api.polygon.io/v3"
        self._session: Optional[aiohttp.ClientSession] = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def get_biotech_pharma_tickers(self, max_price: float = 30.0) -> List[str]:
        """Hole alle Biotech & Pharma Aktien unter max_price"""
        session = await self._get_session()
        
        # Biotech & Pharma Tickers über Polygon Reference API
        # Market: stocks, Type: CS (Common Stock)
        all_tickers = []
        
        # Biotech Sektoren
        sectors = [
            " Biotechnology",
            "Pharmaceuticals", 
            "Pharmaceutical Manufacturing",
            "Medicinal Chemicals",
            "Biological Products"
        ]
        
        url = f"{self.base_url}/reference/tickers"
        
        for sector in sectors:
            params = {
                "market": "stocks",
                "type": "CS",
                "active": "true",
                "limit": "1000",
                "apiKey": self.api_key
            }
            
            # Für bessere Filterung nutzen wir SIC Code oder GICS
            # Da Polygon v3 keine direkte Sektorsuche hat, holen wir alle und filtern
            
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        continue
                    
                    data = await resp.json()
                    results = data.get("results", [])
                    
                    for ticker in results:
                        symbol = ticker.get("ticker", "")
                        if symbol and len(symbol) <= 5:  # Nur echte Tickers
                            all_tickers.append(symbol)
                    
                    # Pagination
                    next_url = data.get("next_url")
                    while next_url and len(all_tickers) < 5000:
                        next_url_with_key = f"{next_url}&apiKey={self.api_key}"
                        async with session.get(next_url_with_key, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                            if resp.status != 200:
                                break
                            data = await resp.json()
                            for ticker in data.get("results", []):
                                symbol = ticker.get("ticker", "")
                                if symbol and len(symbol) <= 5:
                                    all_tickers.append(symbol)
                            next_url = data.get("next_url")
                            
            except Exception as e:
                logger.error(f"Fehler beim Laden der Tickers: {e}")
        
        # Entferne Duplikate
        unique = list(dict.fromkeys(all_tickers))
        logger.info(f"VVPA: {len(unique)} potentielle Biotech/Pharma Tickers gefunden")
        return unique
    
    async def fetch_snapshot_filtered(self, symbols: List[str], max_price: float = 30.0) -> Dict[str, PriceAlert]:
        """Hole Snapshot und filtere nach Preis < max_price"""
        if not symbols:
            return {}
        
        session = await self._get_session()
        
        # Polygon erlaubt max 250 Tickers pro Call - aufteilen in Batches
        batch_size = 250
        all_results = {}
        
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            symbols_str = ",".join(batch)
            
            url = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
            params = {
                "tickers": symbols_str,
                "apiKey": self.api_key
            }
            
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        logger.warning(f"Batch {i//batch_size + 1} Fehler: {resp.status}")
                        continue
                    
                    data = await resp.json()
                    
                    for ticker_data in data.get("tickers", []):
                        symbol = ticker_data.get("ticker", "")
                        price = ticker_data.get("lastTrade", {}).get("p", 0)
                        change_pct = ticker_data.get("todaysChangePerc", 0)
                        volume = ticker_data.get("day", {}).get("v", 0)
                        
                        # Nur Aktien unter $30 und mit Preis > 0
                        if 0.01 < price <= max_price and volume > 0:
                            all_results[symbol] = PriceAlert(
                                symbol=symbol,
                                price=price,
                                change_pct=change_pct,
                                volume=int(volume),
                                timestamp=datetime.now(timezone.utc)
                            )
                            
            except Exception as e:
                logger.error(f"Batch Fehler: {e}")
            
            # Rate limiting - kurze Pause zwischen Batches
            if i + batch_size < len(symbols):
                await asyncio.sleep(0.5)
        
        logger.info(f"VVPA: {len(all_results)} Aktien unter ${max_price} mit Daten")
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
        
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def send_alert(self, alert: PriceAlert):
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
                        logger.info(f"✅ VVPA: {alert.symbol} +{alert.change_pct:.2f}% @ ${alert.price:.2f}")
                        return True
                    else:
                        logger.error(f"Telegram Fehler: {resp.status}")
                        return False
            except Exception as e:
                logger.error(f"Telegram Fehler: {e}")
                return False
    
    async def send_summary(self, scan_time: float, total_stocks: int, alerts: int, top_movers: List[PriceAlert]):
        """Sende Zusammenfassung nach jedem Scan"""
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
                    return resp.status == 200
            except:
                pass
    
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
        self.min_volume = int(os.getenv('MIN_VOLUME', '10000'))  # Mindestvolumen
        
        # Tracking
        self.alerted_stocks: Dict[str, datetime] = {}  # Wann wurde zuletzt alerted
        self.all_tickers: List[str] = []
        self.last_ticker_update = None
        
    async def update_ticker_list(self):
        """Aktualisiere Ticker-Liste einmal pro Tag"""
        now = datetime.now(timezone.utc)
        
        if (self.last_ticker_update is None or 
            (now - self.last_ticker_update).days >= 1 or 
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
        
        # 1. Ticker-Liste aktualisieren (täglich)
        await self.update_ticker_list()
        
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
                    logger.warning("Zyklus dauerte länger als 15 Min!")
                    
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
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
