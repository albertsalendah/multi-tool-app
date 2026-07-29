import time
from urllib.parse import urlparse


from .detector import CaptchaDetector
from .solver import CaptchaSolver
from .verifier import CaptchaVerifier
from .cache import CaptchaCache
from .logger import CaptchaLogger


class CaptchaManager:

    def __init__(self, sb, logging=True):

        self.sb = sb

        self.detector = CaptchaDetector(sb)

        self.solver = CaptchaSolver(sb)

        self.verifier = CaptchaVerifier(sb)

        self.cache = CaptchaCache()

        self.logger = CaptchaLogger() if logging else None

    # ==================================================
    # Domain helper
    # ==================================================

    def current_domain(self):

        try:

            return urlparse(self.sb.get_current_url()).netloc

        except:

            return ""

    # ==================================================
    # Main API
    # ==================================================

    def check(self, solve=True):

        start = time.time()

        domain = self.current_domain()

        # ----------------------------------
        # Check hostile memory
        # ----------------------------------

        if self.cache.is_hostile(domain):

            print("[!] Domain marked hostile")

        # ----------------------------------
        # Cache
        # ----------------------------------

        if not self.cache.should_check():

            cached = self.cache.get()

            print("[*] Returning cached CAPTCHA result")

            return cached

        # ----------------------------------
        # Detect
        # ----------------------------------

        result = self.detector.detect()

        # ----------------------------------
        # Save detection
        # ----------------------------------

        # Do not cache active manual challenges
        if not result.manual_required:
            self.cache.save(result)

        if not result.detected:

            result.duration = time.time() - start

            return result

        print("[!] CAPTCHA:", result.types, "confidence:", result.confidence)

        # ----------------------------------
        # Solve
        # ----------------------------------

        if solve:

            result = self.solver.solve(result)

            if result.manual_required:

                print("[!] Waiting for manual CAPTCHA completion...")

                timeout = 120

                start = time.time()

                while time.time() - start < timeout:

                    time.sleep(3)

                check = self.detector.detect()

                if not check.detected:

                    result.solved = True
                    result.remaining = False
                    result.manual_required = False

                    print("[+] Manual CAPTCHA solved")

                    return result

                print("[!] Manual solve timeout")

                result.remaining = True

                return result

            # ----------------------------------
            # Verify
            # ----------------------------------

            if not result.manual_required:

                result = self.verifier.wait_until_clear(result)

        # ----------------------------------
        # Failure tracking
        # ----------------------------------

        if result.remaining:

            self.cache.add_failure(domain)

        else:

            self.cache.reset_domain(domain)

        result.duration = time.time() - start

        # ----------------------------------
        # Logging
        # ----------------------------------

        if self.logger:

            self.logger.log(result)

            self.logger.print_summary(result)

        return result
