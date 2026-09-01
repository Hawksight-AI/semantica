"""
Semantica Worker Entry Point

This module provides the worker process for the Semantica framework,
enabling distributed and background task processing.
"""

import signal
import time

from .core.orchestrator import Semantica
from .utils.logging import get_logger, setup_logging

# Initialize logging
setup_logging()
logger = get_logger("semantica.worker")

class SemanticaWorker:
    """Worker for processing Semantica tasks."""
    
    def __init__(self):
        self.framework = Semantica()
        self.running = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.handle_exit)
        signal.signal(signal.SIGTERM, self.handle_exit)
    
    def handle_exit(self, signum, frame):
        """Graceful shutdown."""
        logger.info("Worker shutting down...")
        self.running = False
    
    def run(self):
        """Main worker loop."""
        logger.info("Semantica worker started")
        self.running = True
        
        while self.running:
            try:
                # Poll for tasks or process queue
                # logger.debug("Polling for tasks...")
                time.sleep(5)
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
                time.sleep(10)
        
        logger.info("Worker stopped")

def main():
    """Worker entry point."""
    worker = SemanticaWorker()
    worker.run()

if __name__ == "__main__":
    main()
