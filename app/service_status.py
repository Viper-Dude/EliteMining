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


class ServiceWakeChecks:
    def __init__(self, after, checks):
        self._after = after
        self._checks = checks
        self._wake = None

    def suspend(self):
        self._wake = None

    def resume(self):
        wake = self._wake = object()
        failed = []
        retry_due = False

        def retry(probe, publish):
            def deliver(status):
                if self._wake is wake:
                    publish(status)

            probe(deliver)

        def first_result(probe, publish, status):
            if self._wake is not wake:
                return
            publish(status)
            if status == 'offline':
                if retry_due:
                    retry(probe, publish)
                else:
                    failed.append((probe, publish))

        def check_all():
            if self._wake is wake:
                for probe, publish in self._checks:
                    probe(lambda status, probe=probe, publish=publish:
                          first_result(probe, publish, status))

        def retry_failures():
            nonlocal retry_due
            if self._wake is wake:
                retry_due = True
                for probe, publish in failed:
                    retry(probe, publish)

        self._after(10_000, check_all)
        self._after(30_000, retry_failures)
