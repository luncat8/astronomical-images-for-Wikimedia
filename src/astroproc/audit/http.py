"""One HTTP call with the retry contract every remote audit service needs.

Measured live 2026-09-26 against Wikidata, Sesame and MAST: a read timeout is worth retrying
(a twelve-call audit lost two counts to one), an anonymous 429 names the wait in `Retry-After`
(a shortlist was killed by one), and a server-side 504 means the request itself was too slow —
retrying that spends the WDQS budget twice for nothing, so it is left to fail.
"""

import time

import requests

RETRY_AFTER = 5.0
ATTEMPTS = 3
USER_AGENT = "astroproc/0.1 (Wikimedia astronomy coverage audit; plan.md §6.2)"

_session = requests.Session()


def request(method, url, timeout, user_agent=USER_AGENT, session=None, attempts=ATTEMPTS, **kwargs):
	"""Call `url`, retrying a read timeout and waiting out a 429. Raises on the last failure."""
	headers = {**kwargs.pop("headers", {}), "User-Agent": user_agent}
	http = session or _session
	for attempt in range(attempts):
		try:
			response = http.request(method, url, headers=headers, timeout=timeout, **kwargs)
			if response.status_code == 429 and attempt < attempts - 1:
				time.sleep(float(response.headers.get("Retry-After", RETRY_AFTER)))
				continue
			response.raise_for_status()
			return response
		except (requests.Timeout, requests.ConnectionError):
			if attempt == attempts - 1:
				raise
