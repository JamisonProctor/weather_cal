import os
import logging
from forecast_service import ForecastService
from utils.forecast_formatting import format_summary, format_detailed_forecast
from utils.logging_config import setup_logging
from utils.location_management import get_locations

setup_logging()
logger = logging.getLogger(__name__)

def main():
    locations = get_locations()
    
    try:
        # Fetch forecast objects for next 7 days
        forecasts = ForecastService.fetch_forecasts(location=locations)

        # Format and enrich each forecast object
        for forecast in forecasts:
            forecast.summary = format_summary(forecast)
            forecast.details = format_detailed_forecast(forecast)

        # Output formatted forecasts for verification
        for f in forecasts:
            print(f"Date: {f.date}")
            print(f"Summary: {f.summary}")
            print(f"Details:\n{f.details}")
            print("-" * 40)

    except Exception as e:
        logger.error(f"Failed to fetch or process forecasts: {e}", exc_info=True)

if __name__ == "__main__":
    main()