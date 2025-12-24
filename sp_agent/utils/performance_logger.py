"""Performance logging utility for tracking agent execution times."""

import time
import logging
from typing import Optional, Dict
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class PerformanceTracker:
    """Track and log performance metrics for agent execution."""
    
    def __init__(self):
        self.timings: Dict[str, float] = {}
        self.start_times: Dict[str, float] = {}
    
    def start(self, label: str) -> None:
        """Start timing for a labeled operation."""
        self.start_times[label] = time.time()
        logger.info(f"⏱️  [{label}] Started")
    
    def end(self, label: str) -> float:
        """End timing for a labeled operation and return duration."""
        if label not in self.start_times:
            logger.warning(f"No start time found for label: {label}")
            return 0.0
        
        duration = time.time() - self.start_times[label]
        self.timings[label] = duration
        
        logger.info(f"✅ [{label}] Completed in {duration:.2f}s")
        return duration
    
    @contextmanager
    def measure(self, label: str):
        """Context manager for measuring execution time."""
        self.start(label)
        try:
            yield
        finally:
            self.end(label)
    
    def get_summary(self) -> str:
        """Get a formatted summary of all timings."""
        if not self.timings:
            return "No timing data available"
        
        lines = ["\n" + "="*60]
        lines.append("⏱️  PERFORMANCE SUMMARY")
        lines.append("="*60)
        
        total_time = sum(self.timings.values())
        
        for label, duration in sorted(self.timings.items(), key=lambda x: x[1], reverse=True):
            percentage = (duration / total_time * 100) if total_time > 0 else 0
            lines.append(f"  {label:40s} {duration:8.2f}s ({percentage:5.1f}%)")
        
        lines.append("-"*60)
        lines.append(f"  {'TOTAL':40s} {total_time:8.2f}s (100.0%)")
        lines.append("="*60 + "\n")
        
        return "\n".join(lines)
    
    def reset(self) -> None:
        """Reset all timing data."""
        self.timings.clear()
        self.start_times.clear()


# Global tracker instance
_global_tracker: Optional[PerformanceTracker] = None


def get_tracker() -> PerformanceTracker:
    """Get or create the global performance tracker."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = PerformanceTracker()
    return _global_tracker


def log_performance_summary() -> None:
    """Log the performance summary."""
    tracker = get_tracker()
    summary = tracker.get_summary()
    logger.info(summary)
    print(summary)  # Also print to console for visibility
