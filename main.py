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


def create_orchestrator() -> BreakoutBoltOrchestrator:
    store = SQLiteStore(db_path=settings.sqlite_path, schema_path="breakoutbolt/db/schema.sql")
    store.seed_watchlist(settings.watchlist)
    return BreakoutBoltOrchestrator(
        settings=settings,
        store=store,
        data_collector=MarketDataCollector(settings.polygon_api_key, settings.polygon_base_url),
        signal_engine=SignalEngine(settings),
        risk_manager=RiskManager(settings),
        ai_review=AIReviewLayer(),
        execution=OrderExecutionService(settings),
        tracker=PositionTracker(),
        alerts=AlertDispatcher(settings.discord_webhook_url),
        cache=StateCache(settings.redis_url),
        universe_selector=UniverseSelector(settings),
    )


async def main() -> None:
    configure_logging(settings.log_level)
    orchestrator = create_orchestrator()
    await orchestrator.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
