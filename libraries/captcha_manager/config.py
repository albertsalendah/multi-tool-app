CAPTCHA_CONFIG = {
    # ----------------------------------
    # Detection
    # ----------------------------------
    "confidence_threshold": 5,
    # ----------------------------------
    # Cache
    # ----------------------------------
    "cache_seconds": 10,
    "domain_failure_limit": 3,
    # ----------------------------------
    # Verification
    # ----------------------------------
    "verify_timeout": 30,
    "verify_interval": 2,
    # ----------------------------------
    # Manual solving
    # ----------------------------------
    "manual_timeout": 120,
    # ----------------------------------
    # Advanced scans
    # ----------------------------------
    "scan_iframes": True,
    "scan_shadow_dom": True,
    "scan_javascript": True,
    # ----------------------------------
    # Solver
    # ----------------------------------
    "use_solver": True,
}


# =================================================
# CAPTCHA fingerprints
# =================================================


CAPTCHA_FINGERPRINTS = {
    "cloudflare": {
        "selectors": [
            "iframe[src*='cloudflare']",
            "iframe[src*='turnstile']",
            "[class*='cf-turnstile']",
            "[id*='turnstile']",
            "[data-cf-beacon]",
        ],
        "text": [
            "just a moment",
            "checking your browser",
            "verify you are human",
            "attention required",
            "cloudflare",
            "security verification",
        ],
        "score": {"iframe": 5, "text": 3},
    },
    "recaptcha": {
        "selectors": ["iframe[src*='recaptcha']", ".g-recaptcha", ".grecaptcha-badge"],
        "text": ["recaptcha", "protected by recaptcha"],
        "score": {"iframe": 5, "text": 3},
    },
    "hcaptcha": {
        "selectors": ["iframe[src*='hcaptcha']", ".h-captcha"],
        "text": ["hcaptcha"],
        "score": {"iframe": 5, "text": 3},
    },
    "geetest": {
        "selectors": [".geetest_holder", ".geetest_panel", "[class*='geetest']"],
        "text": ["geetest"],
        "score": {"selector": 5, "text": 3},
    },
    "arkose": {
        "selectors": ["iframe[src*='arkose']", "iframe[src*='funcaptcha']"],
        "text": ["funcaptcha", "arkose"],
        "score": {"iframe": 5, "text": 3},
    },
    "imperva": {
        "selectors": ["iframe[src*='imperva']", "iframe[src*='incap']"],
        "text": ["imperva", "incapsula"],
        "score": {"iframe": 5, "text": 3},
    },
    "datadome": {
        "selectors": ["iframe[src*='datadome']"],
        "text": ["datadome"],
        "score": {"iframe": 5, "text": 3},
    },
    "perimeterx": {
        "selectors": ["[id*='px-captcha']", "[class*='px-captcha']"],
        "text": ["perimeterx", "human security"],
        "score": {"selector": 5, "text": 3},
    },
    "aws_waf": {
        "selectors": ["iframe[src*='awswaf']"],
        "text": ["aws waf", "captcha challenge"],
        "score": {"iframe": 5, "text": 3},
    },
}
