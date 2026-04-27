#!/usr/bin/env python3
"""
Creates the Lex V2 bot `cc-photos-search-bot` with the SearchIntent
matching CONTRACTS.md section 6. Idempotent: skips creation if a resource
with the same name already exists. Prints the bot ID + alias ID at the end
for use as Lambda env vars (LEX_BOT_ID, LEX_BOT_ALIAS_ID).

Usage:
  AWS_PROFILE=nyu python3 scripts/create_lex_bot.py

Requires an IAM role assumable by Lex (lexv2.amazonaws.com). This script
will create one called `cc-photos-lex-runtime-role` if it doesn't exist.
"""

import json
import sys
import time

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
BOT_NAME = "cc-photos-search-bot"
LOCALE_ID = "en_US"
INTENT_NAME = "SearchIntent"
ALIAS_NAME = "prod"
LEX_ROLE_NAME = "cc-photos-lex-runtime-role"

UTTERANCES = [
    "{keyword1}",
    "{keyword1} and {keyword2}",
    "show me {keyword1}",
    "show me {keyword1} and {keyword2}",
    "find {keyword1}",
    "find {keyword1} and {keyword2}",
    "photos of {keyword1}",
    "photos of {keyword1} and {keyword2}",
    "show me photos with {keyword1} and {keyword2} in them",
    "search for {keyword1}",
]

iam = boto3.client("iam")
lex = boto3.client("lexv2-models", region_name=REGION)


def ensure_lex_role() -> str:
    trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lexv2.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    }
    try:
        r = iam.create_role(
            RoleName=LEX_ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="Lex V2 runtime role for cc-photos-search-bot",
        )
        arn = r["Role"]["Arn"]
        iam.attach_role_policy(
            RoleName=LEX_ROLE_NAME,
            PolicyArn="arn:aws:iam::aws:policy/AmazonLexFullAccess",
        )
        print(f"[iam] created role {arn}, sleeping 10s for propagation")
        time.sleep(10)
        return arn
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityAlreadyExists":
            return iam.get_role(RoleName=LEX_ROLE_NAME)["Role"]["Arn"]
        raise


def find_bot() -> str | None:
    next_token = None
    while True:
        kw = {"sortBy": {"attribute": "BotName", "order": "Ascending"}, "maxResults": 100}
        if next_token:
            kw["nextToken"] = next_token
        resp = lex.list_bots(**kw)
        for b in resp.get("botSummaries", []):
            if b["botName"] == BOT_NAME:
                return b["botId"]
        next_token = resp.get("nextToken")
        if not next_token:
            return None


def wait_until(check, target: str, timeout: int = 300):
    start = time.time()
    while time.time() - start < timeout:
        status = check()
        if status == target:
            return
        if status in ("Failed", "Deleting"):
            raise RuntimeError(f"unexpected status: {status}")
        time.sleep(4)
    raise TimeoutError(f"waiting for {target}")


def main():
    role_arn = ensure_lex_role()

    bot_id = find_bot()
    if bot_id:
        print(f"[bot] reusing existing bot {bot_id}")
    else:
        r = lex.create_bot(
            botName=BOT_NAME,
            description="Search disambiguation for cc-photos",
            roleArn=role_arn,
            dataPrivacy={"childDirected": False},
            idleSessionTTLInSeconds=300,
        )
        bot_id = r["botId"]
        print(f"[bot] created {bot_id}")
        wait_until(lambda: lex.describe_bot(botId=bot_id)["botStatus"], "Available")

    # Create or reuse en_US locale
    try:
        lex.create_bot_locale(
            botId=bot_id,
            botVersion="DRAFT",
            localeId=LOCALE_ID,
            nluIntentConfidenceThreshold=0.4,
        )
        print("[locale] created en_US")
        wait_until(
            lambda: lex.describe_bot_locale(botId=bot_id, botVersion="DRAFT", localeId=LOCALE_ID)["botLocaleStatus"],
            "NotBuilt",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("ConflictException", "PreconditionFailedException"):
            raise
        print("[locale] reusing en_US")

    # Create the intent (or get existing id)
    intent_id = None
    for it in lex.list_intents(botId=bot_id, botVersion="DRAFT", localeId=LOCALE_ID).get("intentSummaries", []):
        if it["intentName"] == INTENT_NAME:
            intent_id = it["intentId"]
            break
    if not intent_id:
        r = lex.create_intent(
            botId=bot_id, botVersion="DRAFT", localeId=LOCALE_ID,
            intentName=INTENT_NAME,
            description="Picks up keywords for photo search",
        )
        intent_id = r["intentId"]
        print(f"[intent] created {intent_id}")
    else:
        print(f"[intent] reusing {intent_id}")

    # Create slots if missing
    existing_slots = {
        s["slotName"]: s["slotId"]
        for s in lex.list_slots(
            botId=bot_id, botVersion="DRAFT", localeId=LOCALE_ID, intentId=intent_id
        ).get("slotSummaries", [])
    }

    def create_slot(name: str, required: bool):
        if name in existing_slots:
            return existing_slots[name]
        elic = {"messageGroups": [{"message": {"plainTextMessage": {"value": f"What {name}?"}}}], "maxRetries": 1}
        r = lex.create_slot(
            botId=bot_id, botVersion="DRAFT", localeId=LOCALE_ID, intentId=intent_id,
            slotName=name,
            slotTypeId="AMAZON.AlphaNumeric",
            valueElicitationSetting={
                "slotConstraint": "Required" if required else "Optional",
                "promptSpecification": elic,
            },
        )
        print(f"[slot] created {name} = {r['slotId']}")
        return r["slotId"]

    k1 = create_slot("keyword1", required=False)  # leaving optional avoids prompts in API mode
    k2 = create_slot("keyword2", required=False)

    # Update intent with sample utterances + slot priorities
    lex.update_intent(
        botId=bot_id, botVersion="DRAFT", localeId=LOCALE_ID, intentId=intent_id,
        intentName=INTENT_NAME,
        sampleUtterances=[{"utterance": u} for u in UTTERANCES],
        slotPriorities=[
            {"priority": 1, "slotId": k1},
            {"priority": 2, "slotId": k2},
        ],
        fulfillmentCodeHook={"enabled": False},
    )
    print("[intent] utterances + slots wired")

    # Build the locale
    print("[build] starting locale build (~30s)")
    lex.build_bot_locale(botId=bot_id, botVersion="DRAFT", localeId=LOCALE_ID)
    wait_until(
        lambda: lex.describe_bot_locale(botId=bot_id, botVersion="DRAFT", localeId=LOCALE_ID)["botLocaleStatus"],
        "Built",
    )
    print("[build] done")

    # Pick the highest existing numeric version, or create one.
    versions = [v["botVersion"] for v in lex.list_bot_versions(botId=bot_id).get("botVersionSummaries", []) if v["botVersion"] != "DRAFT"]
    if versions:
        version = sorted(versions, key=int)[-1]
        print(f"[version] reusing {version}")
    else:
        v = lex.create_bot_version(
            botId=bot_id,
            botVersionLocaleSpecification={LOCALE_ID: {"sourceBotVersion": "DRAFT"}},
        )
        version = v["botVersion"]
        print(f"[version] created {version}")
    # Poll list_bot_versions until it shows Available; describe_bot_version has propagation lag
    for _ in range(60):
        for vinfo in lex.list_bot_versions(botId=bot_id).get("botVersionSummaries", []):
            if vinfo["botVersion"] == version and vinfo["botStatus"] == "Available":
                break
        else:
            time.sleep(4)
            continue
        break

    # Create or update alias `prod` -> version
    alias_id = None
    for a in lex.list_bot_aliases(botId=bot_id).get("botAliasSummaries", []):
        if a["botAliasName"] == ALIAS_NAME:
            alias_id = a["botAliasId"]
            break
    if alias_id:
        lex.update_bot_alias(
            botId=bot_id, botAliasId=alias_id, botAliasName=ALIAS_NAME,
            botVersion=version,
            botAliasLocaleSettings={LOCALE_ID: {"enabled": True}},
        )
        print(f"[alias] updated {alias_id} -> v{version}")
    else:
        r = lex.create_bot_alias(
            botId=bot_id, botAliasName=ALIAS_NAME,
            botVersion=version,
            botAliasLocaleSettings={LOCALE_ID: {"enabled": True}},
        )
        alias_id = r["botAliasId"]
        print(f"[alias] created {alias_id} -> v{version}")

    print()
    print("=" * 60)
    print("Lex bot ready. Use these as Lambda env vars:")
    print(f"  LEX_BOT_ID={bot_id}")
    print(f"  LEX_BOT_ALIAS_ID={alias_id}")
    print(f"  LEX_LOCALE_ID={LOCALE_ID}")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
