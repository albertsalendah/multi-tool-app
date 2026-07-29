import time


class CaptchaVerifier:

    def __init__(self, sb):

        self.sb = sb

    # =====================================================
    # URL check
    # =====================================================

    def url_changed(self, before):

        try:

            after = self.sb.get_current_url()

            return (after != before, after)

        except:

            return False, ""

    # =====================================================
    # CAPTCHA visibility check
    # =====================================================

    def captcha_still_visible(self):

        selectors = [
            "iframe[src*='captcha']",
            "iframe[src*='recaptcha']",
            "iframe[src*='hcaptcha']",
            "iframe[src*='turnstile']",
            ".g-recaptcha",
            ".h-captcha",
            "#challenge-running",
        ]

        for selector in selectors:

            try:

                if self.sb.cdp.is_element_visible(selector):

                    return True

            except:

                pass

        return False

    # =====================================================
    # Wait until cleared
    # =====================================================

    def wait_until_clear(self, result):

        timeout = 30

        interval = 2

        start = time.time()

        while time.time() - start < timeout:

            blocked = self.captcha_still_visible()

            changed, url = self.url_changed(result.url_before)

            if not blocked or changed:

                result.solved = True

                result.remaining = False

                result.url_after = url

                print("[+] CAPTCHA cleared")

                return result

            time.sleep(interval)

        # timeout

        result.remaining = True

        print("[!] CAPTCHA still active")

        return result
