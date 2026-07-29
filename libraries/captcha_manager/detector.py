import re
from urllib.parse import urlparse

from .models import CaptchaResult
from .config import CAPTCHA_CONFIG, CAPTCHA_FINGERPRINTS


class CaptchaDetector:

    def __init__(self, sb):

        self.sb = sb

    # ======================================================
    # Selenium helpers
    # ======================================================

    def visible(self, selector):

        try:
            return self.sb.cdp.is_element_visible(selector)

        except Exception:

            return False

    def any_visible(self, selectors):

        for selector in selectors:

            if self.visible(selector):

                return selector

        return None

    # ======================================================
    # Text scanning
    # ======================================================

    def get_page_text(self):
        """
        Faster than full page source.
        """

        try:

            text = self.sb.execute_script("""
                return document.body
                ? document.body.innerText
                : "";
                """)

            return (text or "").lower()

        except Exception:

            return ""

    # ======================================================
    # Full HTML scanning
    # ======================================================

    def get_html(self):

        try:

            return self.sb.get_page_source().lower()

        except Exception:

            return ""

    # ======================================================
    # iframe inventory
    # ======================================================

    def scan_iframes(self):
        """
        Finds hidden CAPTCHA frames.

        Returns:
            [
                {
                  src:"",
                  title:""
                }
            ]
        """

        if not CAPTCHA_CONFIG["scan_iframes"]:

            return []

        try:

            frames = self.sb.execute_script("""
                let result=[];

                document
                .querySelectorAll("iframe")
                .forEach(frame=>{

                    result.push({

                        src:
                        frame.src || "",

                        title:
                        frame.title || "",

                        name:
                        frame.name || ""

                    });

                });

                return result;
                """)

            return frames or []

        except Exception:

            return []

    # ======================================================
    # Shadow DOM scan
    # ======================================================

    def scan_shadow_dom(self):
        """
        Detect CAPTCHA hidden in shadow roots.
        """

        if not CAPTCHA_CONFIG["scan_shadow_dom"]:

            return ""

        try:

            result = self.sb.execute_script("""

                let output="";


                function scan(node){

                    if(!node)
                        return;


                    if(node.shadowRoot){

                        output +=
                        node.shadowRoot.innerHTML;

                        scan(
                            node.shadowRoot
                        );

                    }


                    node.children &&
                    [...node.children]
                    .forEach(scan);

                }


                scan(document.body);


                return output;

                """)

            return (result or "").lower()

        except Exception:

            return ""

    # ======================================================
    # Javascript CAPTCHA detection
    # ======================================================

    def scan_javascript(self):
        """
        Detect invisible CAPTCHA APIs.
        """

        if not CAPTCHA_CONFIG["scan_javascript"]:

            return ""

        try:

            scripts = self.sb.execute_script("""

                let data="";

                document
                .querySelectorAll("script")
                .forEach(s=>{

                    data += s.innerHTML;

                });


                return data;

                """)

            return (scripts or "").lower()

        except Exception:

            return ""

    # ======================================================
    # Fingerprint matching
    # ======================================================

    def analyze_fingerprint(
        self, name, fingerprint, text, html, frames, shadow, javascript
    ):

        confidence = 0

        reasons = []

        # -------------------------
        # selectors
        # -------------------------

        matched = self.any_visible(fingerprint["selectors"])

        if matched:

            confidence += 5

            reasons.append(f"selector:{matched}")

        # -------------------------
        # page text
        # -------------------------

        for word in fingerprint["text"]:

            if word.lower() in text:

                confidence += fingerprint.get("score", {}).get("text", 2)

                reasons.append(f"text:{word}")

        # -------------------------
        # iframe scan
        # -------------------------

        for frame in frames:

            data = (
                frame.get("src", "") + frame.get("title", "") + frame.get("name", "")
            ).lower()

            for word in fingerprint["text"]:

                if word.lower() in data:

                    confidence += 5

                    reasons.append(f"iframe:{word}")

        # -------------------------
        # shadow DOM
        # -------------------------

        for word in fingerprint["text"]:

            if word.lower() in shadow:

                confidence += 3

                reasons.append(f"shadow:{word}")

        # -------------------------
        # javascript
        # -------------------------

        js_keywords = {
            "recaptcha": ["grecaptcha"],
            "hcaptcha": ["hcaptcha"],
            "cloudflare": ["turnstile"],
        }

        if name in js_keywords:

            for item in js_keywords[name]:

                if item in javascript:

                    confidence += 3

                    reasons.append(f"javascript:{item}")

        return confidence, reasons

    # ======================================================
    # Main detector
    # ======================================================

    def detect(self):

        result = CaptchaResult()

        try:

            self.sb.wait_for_ready_state_complete()

        except:

            pass

        text = self.get_page_text()

        html = self.get_html()

        shadow = self.scan_shadow_dom()

        javascript = self.scan_javascript()

        frames = self.scan_iframes()

        result.metadata["iframes"] = frames

        # Current URL

        try:

            result.url_before = self.sb.get_current_url()

        except:

            pass

        for name, fingerprint in CAPTCHA_FINGERPRINTS.items():

            confidence, reasons = self.analyze_fingerprint(
                name, fingerprint, text, html, frames, shadow, javascript
            )

            if confidence >= CAPTCHA_CONFIG["confidence_threshold"]:

                result.detected = True

                result.add_match(name, confidence, reasons)

        return result
