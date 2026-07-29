import time

from .config import CAPTCHA_CONFIG


class CaptchaSolver:

    def __init__(self, sb):

        self.sb = sb

    # =====================================================
    # Manual challenge detection
    # =====================================================

    def requires_manual(self, result):
        """
        Determines if human interaction is required.
        """

        manual_types = ["geetest", "arkose"]

        for captcha in result.types:

            if captcha in manual_types:

                return True

        # visual puzzle checks

        checks = [
            "#rc-imageselect",
            "iframe[src*='bframe']",
            "iframe[src*='challenge']",
            ".geetest_slider_button",
        ]

        for selector in checks:

            try:

                if self.sb.cdp.is_element_visible(selector):

                    return True

            except:

                pass

        return False

    # =====================================================
    # Cloudflare handler
    # =====================================================

    def solve_cloudflare(self):

        print("[*] Cloudflare challenge detected")

        # SeleniumBase normally handles:
        # - Turnstile
        # - checkbox
        # - managed challenge

        self.sb.solve_captcha()

    # =====================================================
    # Generic solver
    # =====================================================

    def solve(self, result):

        if not result.detected:

            return result

        if not CAPTCHA_CONFIG["use_solver"]:

            return result

        # -------------------------
        # Manual required
        # -------------------------

        if self.requires_manual(result):

            result.manual_required = True
            result.remaining = True

            print("[!] Manual CAPTCHA interaction required")

            return result

        # -------------------------
        # Automated solve
        # -------------------------

        result.solver_attempted = True

        start = time.time()

        try:

            if "cloudflare" in result.types:

                self.solve_cloudflare()

            else:

                print("[*] Running SeleniumBase CAPTCHA solver")

                self.sb.solve_captcha()

        except Exception as e:

            print("[!] CAPTCHA solver error:", e)

            result.metadata["solver_error"] = str(e)

        finally:

            result.metadata["solver_time"] = time.time() - start

        return result
