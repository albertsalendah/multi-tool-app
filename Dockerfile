FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Real Google Chrome, not Debian's Chromium build - undetected-chromedriver
# mode (uc=True, used for CAPTCHA-solving - see libraries/captcha_manager
# and tools/video_downloader/selenium_detector.py) is calibrated against
# actual Chrome; Chromium's slightly different binary fingerprint makes it
# more detectable as automation.
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget gnupg ca-certificates \
    && wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm /tmp/chrome.deb \
    && rm -rf /var/lib/apt/lists/*

# Matching chromedriver, managed by SeleniumBase (auto-detects the
# installed Chrome version rather than hardcoding one).
RUN seleniumbase install chromedriver

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
