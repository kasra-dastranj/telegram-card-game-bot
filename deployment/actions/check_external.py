"""Public reachability only; authentication is never supplied to these requests."""
import json
import os
import urllib.error
import urllib.request

results = {}
for name, url, expected in (("admin", "https://taraz.gwfarsi.ir/card-admin/", 401),
                            ("miniapp", "https://89-106-206-220.nip.io/miniapp", 200)):
    try:
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
        results[name] = {"status": status, "expected": expected, "ok": status == expected}
    except (urllib.error.URLError, TimeoutError, OSError):
        results[name] = {"ok": False, "error": "DNS/network/TLS unavailable from this runner"}
with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as output:
    output.write("External reachability (does not change the internal deployment result)\n\n```json\n" + json.dumps(results, indent=2) + "\n```\n")
print(json.dumps(results))
if any(not result["ok"] for result in results.values()):
    print("::warning::External reachability differs from expectation; inspect the separate network report")
