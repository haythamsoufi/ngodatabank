import time
from functools import wraps
from flask import request, g, current_app
from app.models.api_usage import APIUsage
from app.utils.api_helpers import get_json_safe
from app import db

def track_api_request():
    """Track API request before it's processed."""
    if request.path.startswith('/api/'):
        # Skip tracking for notifications API endpoints and refresh-csrf-token
        if 'notifications' in request.path or 'refresh-csrf-token' in request.path:
            return

        g.api_start_time = time.time()
        current_app.logger.debug(f"Starting API request tracking for: {request.path}")

def track_api_response(response):
    """Track API response after it's processed."""
    if request.path.startswith('/api/'):
        # Skip tracking for notifications API endpoints and refresh-csrf-token
        if 'notifications' in request.path or 'refresh-csrf-token' in request.path:
            return response

        try:
            # Calculate response time
            start_time = getattr(g, 'api_start_time', None)
            if start_time is None:
                # Missing start time; skip tracking for this response safely
                return response
            response_time = (time.time() - start_time) * 1000  # Convert to milliseconds

            # Create a separate database session to avoid transaction conflicts
            from sqlalchemy.orm import sessionmaker
            temp_db = sessionmaker(bind=db.engine)()
            try:
                usage = APIUsage(
                    api_endpoint=request.path,
                    ip_address=request.remote_addr,
                    method=request.method,
                    status_code=response.status_code,
                    response_time=response_time,
                    user_agent=request.user_agent.string if request.user_agent else None,
                    request_data=get_json_safe()
                )

                temp_db.add(usage)

                # Also track API key usage if a database-managed key was used
                api_key_record = getattr(g, 'api_key_record', None)
                if api_key_record:
                    from app.models.api_key_management import APIKeyUsage
                    from datetime import datetime

                    key_usage = APIKeyUsage(
                        api_key_id=api_key_record.id,
                        endpoint=request.path,
                        method=request.method,
                        ip_address=request.remote_addr,
                        user_agent=request.user_agent.string if request.user_agent else None,
                        status_code=response.status_code,
                        response_time_ms=response_time,
                        request_data=get_json_safe()
                    )

                    temp_db.add(key_usage)

                    current_app.logger.debug(
                        f"Tracked API key usage: {api_key_record.client_name} "
                        f"(key_id: {api_key_record.id}, endpoint: {request.path}, "
                        f"status: {response.status_code}, time: {response_time:.2f}ms)"
                    )

                temp_db.commit()

                current_app.logger.debug(
                    f"Tracked API usage: {request.method} {request.path} "
                    f"(status: {response.status_code}, time: {response_time:.2f}ms)"
                )
            except Exception as e:
                current_app.logger.error(f"Error saving API usage: {str(e)}", exc_info=True)
                temp_db.rollback()
            finally:
                temp_db.close()

        except Exception as e:
            current_app.logger.error(f"Error in API tracking setup: {str(e)}", exc_info=True)

    return response

def track_api_usage(f):
    """Decorator for tracking API usage (legacy support)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        track_api_request()

        try:
            response = f(*args, **kwargs)
            return track_api_response(response)
        except Exception as e:
            current_app.logger.error(f"Error in API tracking: {str(e)}", exc_info=True)
            raise

    return decorated_function
