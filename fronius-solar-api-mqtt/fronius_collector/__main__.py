"""Main entry point for Fronius Collector."""

import argparse
import asyncio
import logging
import signal
import sys
from typing import Optional

from .collector import FroniusCollector
from .config import load_config, setup_logging
from .influxdb_client import InfluxClient
from .mqtt_client import MQTTClient

logger = logging.getLogger(__name__)


class Application:
    """Main application class with graceful shutdown handling."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize the application.

        Args:
            config_path: Path to configuration file.
        """
        self.config_path = config_path
        self.config = None
        self.mqtt: Optional[MQTTClient] = None
        self.influx: Optional[InfluxClient] = None
        self.collector: Optional[FroniusCollector] = None
        self._shutdown_event: Optional[asyncio.Event] = None

    async def start(self) -> None:
        """Start all components."""
        # Load configuration
        try:
            self.config = load_config(self.config_path)
        except FileNotFoundError as e:
            logger.error(f"Configuration error: {e}")
            sys.exit(1)
        except ValueError as e:
            logger.error(f"Invalid configuration: {e}")
            sys.exit(1)

        # Setup logging
        setup_logging(self.config.logging)
        logger.info("Fronius Collector starting...")

        # Initialize MQTT client
        if self.config.mqtt.enabled:
            self.mqtt = MQTTClient(self.config.mqtt)
            await self.mqtt.start()

        # Initialize InfluxDB client
        if self.config.influxdb.enabled:
            self.influx = InfluxClient(self.config.influxdb)
            await self.influx.start()

        # Initialize collector
        self.collector = FroniusCollector(
            fronius_config=self.config.fronius,
            mqtt_client=self.mqtt,
            influx_client=self.influx,
        )
        await self.collector.start()

        logger.info("Fronius Collector started successfully")

    async def stop(self) -> None:
        """Stop all components gracefully."""
        logger.info("Shutting down Fronius Collector...")

        # Stop collector first
        if self.collector:
            await self.collector.stop()

        # Then stop outputs
        if self.influx:
            await self.influx.stop()

        if self.mqtt:
            await self.mqtt.stop()

        logger.info("Fronius Collector stopped")

    async def run(self) -> None:
        """Run the application until shutdown signal."""
        # Create event in the running loop
        self._shutdown_event = asyncio.Event()

        await self.start()

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        await self.stop()

    def shutdown(self) -> None:
        """Signal the application to shutdown."""
        logger.info("Shutdown signal received")
        if self._shutdown_event:
            self._shutdown_event.set()


def setup_signal_handlers(app: Application, loop: asyncio.AbstractEventLoop) -> None:
    """Setup signal handlers for graceful shutdown.

    Args:
        app: Application instance.
        loop: Event loop.
    """
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, app.shutdown)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Fronius Collector - Collect data from Fronius devices"
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=None,
        help="Path to configuration file (default: config.yaml or FRONIUS_CONFIG env)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Collect data once and exit (useful for testing)",
    )
    return parser.parse_args()


async def run_once(config_path: Optional[str]) -> None:
    """Run a single collection cycle and print results.

    Args:
        config_path: Path to configuration file.
    """
    config = load_config(config_path)
    setup_logging(config.logging)

    collector = FroniusCollector(fronius_config=config.fronius)
    await collector.start()

    try:
        data = await collector.collect_once()
        print("\n=== Power Flow ===")
        if data["power_flow"]:
            for key, value in data["power_flow"].items():
                print(f"  {key}: {value}")

        print("\n=== Meter ===")
        for meter_id, meter_data in data["meter"].items():
            print(f"  Meter {meter_id}:")
            if meter_data:
                for key, value in meter_data.items():
                    print(f"    {key}: {value}")

        print("\n=== Inverters ===")
        for inv_id, inv_data in data["inverters"].items():
            print(f"  Inverter {inv_id}:")
            if inv_data:
                for key, value in inv_data.items():
                    print(f"    {key}: {value}")

    finally:
        await collector.stop()


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Override log level if verbose
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    if args.once:
        # Single collection mode
        asyncio.run(run_once(args.config))
    else:
        # Normal operation mode
        app = Application(config_path=args.config)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Setup signal handlers (Unix only)
        if sys.platform != "win32":
            setup_signal_handlers(app, loop)

        try:
            loop.run_until_complete(app.run())
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
            loop.run_until_complete(app.stop())
        finally:
            loop.close()


if __name__ == "__main__":
    main()
