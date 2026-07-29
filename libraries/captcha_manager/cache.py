import time
from collections import defaultdict

from .config import CAPTCHA_CONFIG


class CaptchaCache:

    def __init__(self):

        self.last_check = 0

        self.last_result = None

        self.domain_failures = defaultdict(int)

    def should_check(self):

        elapsed = time.time() - self.last_check

        return elapsed >= CAPTCHA_CONFIG["cache_seconds"] or self.last_result is None

    def get(self):

        return self.last_result

    def save(self, result):

        self.last_check = time.time()

        self.last_result = result

    def add_failure(self, domain):

        self.domain_failures[domain] += 1

    def is_hostile(self, domain):

        return self.domain_failures[domain] >= CAPTCHA_CONFIG["domain_failure_limit"]

    def reset_domain(self, domain):

        if domain in self.domain_failures:

            del self.domain_failures[domain]
