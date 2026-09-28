"""
providers_check.py - test every configured AI provider: reachability, key, speed.

    .\\run.bat providers        (or: python providers_check.py)

Shows the chain order, then pings each provider individually so you can see exactly which
ones work from this network right now.
"""

import time

import ai_engine


def main():
    print("provider chain (tried in this order):")
    for provider in ai_engine._ordered():
        key_state = "key set" if ai_engine._key_for(provider) else "NO KEY"
        print(f"  • {provider['name']:12} {str(provider.get('model'))[:36]:38} "
              f"{(provider['base_url'] or 'groq-default')[:46]:48} {key_state}")

    print("\ntesting each provider with a key ...")
    any_ok = False
    for provider in ai_engine.PROVIDERS:
        if not ai_engine._key_for(provider):
            print(f"  [skip] {provider['name']:12} — no {provider['api_key_env']} in .env")
            continue
        started = time.time()
        try:
            msg = ai_engine.try_provider(
                provider, [{"role": "user", "content": "Reply with exactly: ok"}], max_tokens=200)
            took = time.time() - started
            text = (getattr(msg, "content", "") or "").strip()
            print(f"  [PASS] {provider['name']:12} {took:5.1f}s  {text[:40]!r}")
            any_ok = True
        except Exception as e:
            took = time.time() - started
            print(f"  [FAIL] {provider['name']:12} {took:5.1f}s  {str(e)[:110]}")

    print()
    if any_ok:
        print("At least one provider works — the assistant will use it.")
    else:
        print("No provider works right now. Add ONE of these free keys to .env:")
        print("  GITHUB_TOKEN=...        (github.com/settings/tokens → fine-grained, 'Models: read')")
        print("  OPENROUTER_API_KEY=...  (openrouter.ai/keys → free models available)")
        print("  GEMINI_API_KEY=...      (aistudio.google.com — can be overloaded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
