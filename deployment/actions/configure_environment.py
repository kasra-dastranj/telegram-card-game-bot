"""Owner-only GitHub setup; run after reviewing the PR, never with a collaborator token."""
import argparse
import json
import subprocess

REPO = "kasra-dastranj/telegram-card-game-bot"


def api(path, method="GET", body=None):
    command = ["gh", "api", "--method", method, path]
    if body is not None:
        command.extend(["--input", "-"])
    result = subprocess.run(command, input=json.dumps(body) if body is not None else None,
                            text=True, capture_output=True, check=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    actor = api("user")
    repo = api("repos/" + REPO)
    if actor["login"] != "kasra-dastranj" or not repo["permissions"].get("admin"):
        raise SystemExit("Only the repository owner with admin access may run this setup")
    desired = {"wait_timer": 0, "prevent_self_review": True,
               "reviewers": [{"type": "User", "id": actor["id"]}],
               "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}}
    if not args.apply:
        print(json.dumps({"environment": "production", "policy": desired, "allowed_branch": "main"}, indent=2))
        return
    path = "repos/" + REPO + "/environments/production"
    api(path, "PUT", desired)
    policies = api(path + "/deployment-branch-policies")["branch_policies"]
    if any(policy["name"] != "main" or policy.get("type") != "branch" for policy in policies):
        raise SystemExit("Owner must remove extra production branch/tag policies before adding any secrets")
    if not policies:
        api(path + "/deployment-branch-policies", "POST", {"name": "main", "type": "branch"})
    policies = api(path + "/deployment-branch-policies")["branch_policies"]
    assert len(policies) == 1 and policies[0]["name"] == "main" and policies[0]["type"] == "branch"
    print("production configured: only main, owner reviewer, no secrets installed")


if __name__ == "__main__":
    main()
