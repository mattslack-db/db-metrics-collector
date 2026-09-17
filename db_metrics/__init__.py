"""Azure PostgreSQL Flexible Server performance-metrics collector.

Control-plane only: pulls Azure Monitor platform metrics and server
configuration via the Azure SDK. Never connects to the database and never
reads row-level data.
"""

__version__ = "1.0.0"
