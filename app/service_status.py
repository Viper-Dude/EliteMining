"""Report service availability from requests already needed by searches."""

import requests


status_callback = None


def tracked_request(service, request, *args, **kwargs):
    try:
        response = request(*args, **kwargs)
    except requests.exceptions.RequestException:
        if status_callback is not None:
            status_callback(service, 'offline')
        raise
    if status_callback is not None:
        status_callback(service, 'online' if 200 <= response.status_code < 300 else 'offline')
    return response
