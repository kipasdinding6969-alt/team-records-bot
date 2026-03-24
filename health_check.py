#!/usr/bin/env python3
"""Health check script for Team Records Bot monitoring."""
import asyncio
import json
import sys
from main import ralph_loop


async def main():
    """Run health check and exit with appropriate code."""
    try:
        # Initialize the bot components
        await ralph_loop.initialize()

        # Run health check
        health = await ralph_loop.health_check()

        # Print health status as JSON
        print(json.dumps(health, indent=2, ensure_ascii=False))

        # Exit with appropriate code
        if health['status'] == 'healthy':
            sys.exit(0)
        elif health['status'] == 'degraded':
            sys.exit(1)
        else:
            sys.exit(2)

    except Exception as e:
        error_response = {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': None
        }
        print(json.dumps(error_response, indent=2, ensure_ascii=False))
        sys.exit(2)


if __name__ == '__main__':
    asyncio.run(main())