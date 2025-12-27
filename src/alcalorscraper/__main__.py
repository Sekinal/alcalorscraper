"""Entry point for running alcalorscraper as a module."""
import asyncio
from alcalorscraper.main import main

if __name__ == "__main__":
    asyncio.run(main())
