"""
api_check.py - test that the assistant service is reachable.

    .\\run.bat api      (or: python api_check.py)

Prints PASS/FAIL plus, on failure, the most likely cause and fix.
"""

import ai_engine


def main():
    print("testing the assistant service ...")
    try:
        reply = ai_engine.complete(
            [{"role": "user", "content": "Reply with exactly: ok"}], max_tokens=30)
        print("[PASS] service reachable ->", repr((reply or "").strip()[:60]))
        return 0
    except Exception as e:
        print("[FAIL]", e)
        print("\nIf it mentions 403 / access denied:")
        print("  - turn off any VPN (TurboVPN / Proton VPN) and retry")
        print("  - check your internet connection")
        print("  - confirm GROQ_API_KEY in the .env file")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
