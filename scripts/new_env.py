#!/usr/bin/env python3
"""
new_env.py — first-time environment setup.

Writes SSM parameters required by CDK and the Ghost ECS task.
Must be run once per environment before `cdk deploy`.

Usage:
    uv run python scripts/new_env.py
    uv run python scripts/new_env.py --force   # overwrite existing values
"""

import argparse
import getpass
import sys

import boto3
from botocore.exceptions import ClientError

# (name, prompt, is_secret)
PARAMETERS = [
    ("/ghost/url", "Ghost public URL (e.g. https://website.dn.womblelabs.co.uk)", False),
    ("/ghost/database/password", "MySQL ghost user password", True),
]

REGION = "eu-west-2"


def confirm_account(session: boto3.Session) -> str:
    sts = session.client("sts", region_name=REGION)
    identity = sts.get_caller_identity()
    account_id = identity["Account"]
    arn = identity["Arn"]
    print(f"\nAWS account : {account_id}")
    print(f"Identity    : {arn}\n")
    answer = input("Continue with this account? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)
    return account_id


def collect_values() -> dict[str, str]:
    print()
    values: dict[str, str] = {}
    for name, prompt, is_secret in PARAMETERS:
        if is_secret:
            value = getpass.getpass(f"  {prompt}: ").strip()
        else:
            value = input(f"  {prompt}: ").strip()
        if value:
            values[name] = value
        else:
            print(f"  SKIP  {name}  (empty — skipping)")
    return values


def write_via_sdk(session: boto3.Session, values: dict[str, str], force: bool) -> bool:
    """Attempt to write parameters via SDK. Returns True on success, False on SubscriptionRequiredException."""
    ssm_client = session.client("ssm", region_name=REGION)
    print(f"\n  Writing to SSM Parameter Store ({REGION})...\n")
    for name, value in values.items():
        try:
            ssm_client.put_parameter(Name=name, Value=value, Type="String", Overwrite=force)
            print(f"  OK    {name}")
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code == "ParameterAlreadyExists":
                print(f"  SKIP  {name}  (already exists — use --force to overwrite)")
            elif code == "SubscriptionRequiredException":
                print("\n  ERROR: SubscriptionRequiredException — SSM is not available via SDK in this account.")
                return False
            else:
                raise
    return True


def print_cli_commands(values: dict[str, str]) -> None:
    print("\n" + "=" * 70)
    print("SSM SDK is blocked in this account. Write parameters manually with")
    print("the AWS CLI, then re-run `make deploy-dev`:")
    print()
    for name, value in values.items():
        safe_value = "<see above>" if any(name == p[0] and p[2] for p in PARAMETERS) else value
        print(f"  aws ssm put-parameter --region {REGION} \\")
        print(f"    --name '{name}' --type String \\")
        print(f"    --value '{safe_value}'")
        print()
    print("For the password, replace <see above> with the value you entered.")
    print()
    print("After writing all parameters, confirm SSM is working:")
    print(f"  aws ssm get-parameter --region {REGION} --name /ghost/url")
    print()
    print("NOTE: CDK uses {{{{resolve:ssm:/ghost/database/password}}}} at deploy time.")
    print("If SSM is blocked, CloudFormation will also fail. You need to resolve")
    print("the SSM access issue before `cdk deploy` will succeed.")
    print()
    print("Common causes of SubscriptionRequiredException on a new account:")
    print("  1. Account still activating — wait up to 24 hours, then retry.")
    print("  2. AWS Organization SCP blocking SSM — check with your org admin.")
    print("  3. Visit the SSM Parameter Store console in eu-west-2 and create a")
    print("     test parameter; this sometimes initialises the service.")
    print("=" * 70)


def print_next_steps(account_id: str) -> None:
    print("\nDone. Next steps:")
    print()
    print("  1. Bootstrap CDK (run once per account/region):")
    print(f"       cdk bootstrap aws://{account_id}/eu-west-2")
    print(f"       cdk bootstrap aws://{account_id}/us-east-1")
    print()
    print("  2. Deploy EcrStack first, then build and push the Ghost image:")
    print("       cdk deploy EcrStack")
    print("       aws ecr get-login-password --region eu-west-2 | \\")
    print(f"         docker login --username AWS --password-stdin {account_id}.dkr.ecr.eu-west-2.amazonaws.com")
    print("       docker build -f docker/ghost/Dockerfile -t dn-website-ghost:latest .")
    print(
        f"       docker tag dn-website-ghost:latest "
        f"{account_id}.dkr.ecr.eu-west-2.amazonaws.com/dn-website-ghost:latest"
    )
    print(f"       docker push {account_id}.dkr.ecr.eu-west-2.amazonaws.com/dn-website-ghost:latest")
    print()
    print("  3. Deploy remaining stacks:")
    print("       make deploy-dev")
    print()
    print("  4. After NetworkStack deploys, add the Route 53 NS records from the")
    print("     stack output to the parent zone (dn.womblelabs.co.uk).")
    print()
    print("  5. Create the GitHub Actions OIDC provider and deploy role:")
    print("       uv run python scripts/setup_oidc.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up a new environment's SSM parameters.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing SSM parameters.")
    args = parser.parse_args()

    session = boto3.Session()
    account_id = confirm_account(session)
    values = collect_values()

    if not values:
        print("\nNo values entered. Nothing written.")
        sys.exit(0)

    ok = write_via_sdk(session, values, args.force)
    if not ok:
        print_cli_commands(values)
        sys.exit(1)

    print_next_steps(account_id)


if __name__ == "__main__":
    main()
