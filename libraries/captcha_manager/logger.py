import json
import time
from pathlib import Path


class CaptchaLogger:

    def __init__(self, filename="captcha_events.json"):

        self.filename = Path(filename)

    def serialize(self, result):

        return {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "detected": result.detected,
            "types": result.types,
            "confidence": result.confidence,
            "solver_attempted": result.solver_attempted,
            "solved": result.solved,
            "remaining": result.remaining,
            "manual_required": result.manual_required,
            "duration": result.duration,
            "url_before": result.url_before,
            "url_after": result.url_after,
            "metadata": result.metadata,
        }

    def log(self, result):

        data = self.serialize(result)

        history = []

        if self.filename.exists():

            try:

                history = json.loads(self.filename.read_text())

            except:

                history = []

        history.append(data)

        self.filename.write_text(json.dumps(history, indent=4))

    def print_summary(self, result):

        print("\n========== CAPTCHA REPORT ==========")

        print("Detected:", result.detected)

        print("Types:", result.types)

        print("Confidence:", result.confidence)

        print("Solver:", result.solver_attempted)

        print("Solved:", result.solved)

        print("Manual:", result.manual_required)

        print("Remaining:", result.remaining)

        print("====================================\n")
