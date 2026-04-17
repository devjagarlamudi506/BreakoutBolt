import asyncio

from breakoutbolt.config import settings
from breakoutbolt.db.sqlite_store import SQLiteStore
from breakoutbolt.logging_config import configure_logging
from breakoutbolt.services.ai_review import AIReviewLayer
from breakoutbolt.services.alert_dispatcher import AlertDispatcher
from breakoutbolt.services.execution import OrderExecutionService
from breakoutbolt.services.market_data import MarketDataCollector
from breakoutbolt.services.orchestrator import BreakoutBoltOrchestrator
from breakoutbolt.services.position_tracker import PositionTracker
from breakoutbolt.services.risk_manager import RiskManager
from breakoutbolt.services.signal_engine import SignalEngine
from breakoutbolt.services.state_cache import StateCache
from breakoutbolt.services.universe_selector import UniverseSelector
from breakoutbolt.services.ws_data_feed import WsDataFeed
from breakoutbolt.services.ws_monitor import WebSocketExitMonitor


def create_orchestrator() -> tuple[BreakoutBoltOrchestrator, WebSocketExitMonitor | None, WsDataFeed | None]:
    store = SQLiteStore(db_path=settings.sqlite_path, schema_path="breakoutbolt/db/schema.sql")
    store.seed_watchlist(settings.watchlist)
    alerts = AlertDispatcher(settings.discord_webhook_url)
    cache = StateCache(settings.redis_url)
    execution = OrderExecutionService(settings)

    orchestrator = BreakoutBoltOrchestrator(
        settings=settings,
        store=store,
        data_collector=MarketDataCollector(settings.polygon_api_key, settings.polygon_base_url, settings.finnhub_api_key),
        signal_engine=SignalEngine(settings),
        risk_manager=RiskManager(settings),
        ai_review=AIReviewLayer(),
        execution=execution,
        tracker=PositionTracker(),
        alerts=alerts,
        cache=cache,
        universe_selector=UniverseSelector(settings),
    )

    ws_monitor = None
    ws_data_feed = None

    # Finnhub WS data feed for real-time signal scanning (50 symbols)
    if settings.finnhub_api_key:
        ws_data_feed = WsDataFeed(finnhub_api_key=settings.finnhub_api_key)
        orchestrator.ws_data_feed = ws_data_feed

    # Alpaca IEX WS exit monitor (real-time stop/target exits)
    if settings.websocket_exit_enabled and settings.alpaca_api_key and settings.alpaca_api_secret:
        ws_monitor = WebSocketExitMonitor(
            alpaca_api_key=settings.alpaca_api_key,
            alpaca_api_secret=settings.alpaca_api_secret,
            store=store,
            alerts=alerts,
            cache=cache,
            execution=execution,
        )
        orchestrator.ws_monitor = ws_monitor

    return orchestrator, ws_monitor, ws_data_feed


async def main() -> None:
    configure_logging(settings.log_level)
    orchestrator, ws_monitor, ws_data_feed = create_orchestrator()

    tasks = [asyncio.create_task(orchestrator.run_forever())]
    if ws_monitor:
        tasks.append(asyncio.create_task(ws_monitor.run_forever()))
        tasks.append(asyncio.create_task(ws_monitor.periodic_sync()))
    if ws_data_feed:
        tasks.append(asyncio.create_task(ws_data_feed.run_forever()))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
