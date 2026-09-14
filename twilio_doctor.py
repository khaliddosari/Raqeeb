"""Why Twilio refuses to place the dispatch call.

    uv run python twilio_doctor.py +966551234567

Answers the question the API error alone cannot: it asks Twilio, using the very credentials
the app runs with, which account those credentials belong to, whether that account may dial
this number, and what the number's own permission class is. Reads the environment the same
way agent/config.py does, so it is checking the deployment's truth rather than a console tab
that may belong to a different project.

Nothing here places a call or changes any setting.
"""

from __future__ import annotations

import sys

from agent.config import settings
from agent.intake import normalize_saudi_mobile


def _line(label: str, value: object) -> None:
    print(f"  {label:<34} {value}")


def main() -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else ""
    if not raw:
        print(__doc__)
        return 2
    try:
        to_number = normalize_saudi_mobile(raw)
    except ValueError as exc:
        print(f"{raw!r} is not a Saudi mobile: {exc}")
        return 2

    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        print("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN are not set in this environment.")
        return 2

    from twilio.base.exceptions import TwilioRestException
    from twilio.rest import Client

    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    verdicts: list[str] = []

    print("\nThe account these credentials actually belong to")
    try:
        account = client.api.accounts(settings.twilio_account_sid).fetch()
    except TwilioRestException as exc:
        print(f"  could not fetch it: {exc.msg} (code {exc.code})")
        print("\n  The credentials are rejected outright, so nothing configured in any console")
        print("  applies to them. Check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN on the Modal secret.")
        return 1
    except Exception as exc:  # noqa: BLE001 - connectivity, DNS, a proxy in the way
        print(f"  could not reach api.twilio.com: {type(exc).__name__}: {exc}")
        print("\n  This machine cannot talk to Twilio, so nothing below could be checked. Run it")
        print("  somewhere with outbound access, or `modal run` it against the deployment.")
        return 1
    _line("account sid", account.sid)
    _line("friendly name", account.friendly_name)
    _line("type", account.type)
    _line("status", account.status)
    print("\n  Compare that sid against the one shown in the console tab where you changed the")
    print("  settings. A different sid (a second project, or a subaccount) is the whole answer.")
    if account.status != "active":
        verdicts.append(f"The account is {account.status}, not active. Nothing will dial until that is resolved.")

    trial = (account.type or "").lower() == "trial"

    print("\nVerified caller IDs (a trial account may only dial these)")
    verified = {caller.phone_number for caller in client.outgoing_caller_ids.list(limit=100)}
    for number in sorted(verified):
        _line("", number)
    if not verified:
        _line("", "(none)")
    if to_number in verified:
        print(f"\n  {to_number} is verified on this account.")
    else:
        print(f"\n  {to_number} is NOT verified on this account.")
        if trial:
            verdicts.append(
                f"This is a trial account and {to_number} is not among its verified caller IDs, "
                "which is Twilio error 21219. Verifying it in a different project does not count."
            )

    print("\nOutbound voice permissions for Saudi Arabia on this account")
    try:
        sa = client.voice.v1.dialing_permissions.countries("SA").fetch()
        _line("low risk numbers enabled", sa.low_risk_numbers_enabled)
        _line("high risk special enabled", sa.high_risk_special_numbers_enabled)
        _line("high risk toll fraud enabled", sa.high_risk_tollfraud_numbers_enabled)
        if not sa.low_risk_numbers_enabled:
            verdicts.append(
                "Saudi Arabia's low-risk range is disabled on this account, which is Twilio error 21215. "
                "Console > Voice > Settings > Geo permissions."
            )
        elif not (sa.high_risk_special_numbers_enabled and sa.high_risk_tollfraud_numbers_enabled):
            verdicts.append(
                "Saudi Arabia's low-risk range is enabled but at least one high-risk range is not. "
                "Twilio classifies narrow ranges inside ordinary mobile ranges as high-risk toll fraud "
                "and does not publish them, so a normal-looking 05 number can sit in one and still be "
                "refused with 21215. Run the Phone Number Permission Check on the Geo permissions page "
                "against this exact number: that tool is the only way to see which class it is in."
            )
    except TwilioRestException as exc:
        _line("could not read them", f"{exc.msg} (code {exc.code})")

    print("\nThe 'from' number")
    _line("TWILIO_PHONE_NUMBER", settings.twilio_phone_number or "(not set)")
    owned = {n.phone_number: n for n in client.incoming_phone_numbers.list(limit=100)}
    if settings.twilio_phone_number in owned:
        _line("owned by this account", "yes")
        _line("voice capable", owned[settings.twilio_phone_number].capabilities.get("voice"))
    else:
        _line("owned by this account", "no")
        verdicts.append(
            f"{settings.twilio_phone_number} is not one of this account's numbers, so it cannot be "
            "the 'from' of an outbound call."
        )

    print("\n" + "=" * 78)
    if verdicts:
        print("What is refusing the call:\n")
        for verdict in verdicts:
            print(f"  - {verdict}\n")
    else:
        print("Nothing here explains a refusal: the account is active, the number is permitted,")
        print("and the 'from' number is owned and voice capable. If the call is still refused,")
        print("read the error code off the Modal log line that starts [telephony INC-...]:")
        print("  21215 geo permissions, 21219 an unverified number on a trial account,")
        print("  21216 a call Twilio blocked as high-risk regardless of your permissions.")
        print("  https://www.twilio.com/docs/api/errors/<code>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
