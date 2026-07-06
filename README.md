🎬 Netflix Cookie Checker Bot
A powerful Telegram bot that validates Netflix cookies and extracts detailed account information in seconds. Whether you're managing multiple accounts, verifying session integrity, or need quick account access links—this bot has you covered.

✨ What This Bot Can Do
🔐 Cookie Validation
Multi-format Support: Accept cookies in any format you throw at it:
Raw Cookie header lines (Cookie: netflixid=...; securenetflixid=...)
Netscape browser export format (both tab and space-delimited)
JSON array format
Simple key=value pairs
Smart Parsing: The bot intelligently detects which format you've provided and parses it accordingly—no manual conversion needed!
🎫 Session Access Links
Instantly generate three types of login links from a single cookie:

📱 Mobile Link: Access Netflix on your phone
🖥️ Desktop Link: Full browser experience
📺 TV Link: Stream on your TV device
All links use secure nftoken authentication—no password needed!

👤 Comprehensive Account Details
Get a complete snapshot of the Netflix account in seconds:

Basic Info: Account owner name, email, country
Subscription Details: Plan type, price, membership start date, next billing date
Profile Info: List of all user profiles on the account
Payment Info: Payment method type, masked card numbers
Contact Verification: Phone number, phone verification status, email verification status
Streaming Info: Maximum video quality, concurrent stream limits
Account Status: Payment hold status, premium/free tier, extra member access
🛡️ Security & Privacy
Direct Netflix API validation—no third-party intermediaries
Real-time verification ensures cookies aren't expired or revoked
Secure token generation for session access
SSL/TLS enabled by default
⚡ Instant Results
Real-time cookie verification using Netflix's official API
Account information extracted directly from Netflix servers
Fast response times even under load
🚀 How to Use
For End Users (via Telegram):
Start the bot: Send /start
Paste your cookies: Copy and paste your Netflix cookies in any format
Get results: Within seconds, receive:
Validation status
Three session login links (phone, desktop, TV)
Complete account information
For Developers (Self-hosting):
bash

Copy code
# Set environment variables
export BOT_TOKEN="your_telegram_bot_token"
export PORT=10000

# Run the bot
python your_bot_file.py

The bot runs on Flask (HTTP server) + Telegram Polling (message handling) in a dual-thread architecture.

📋 Supported Cookie Formats
The bot accepts cookies in these formats:

graphql

Copy code
# Format 1: Cookie Header
Cookie: NetflixId=abc123; SecureNetflixId=def456; nfvdid=ghi789

# Format 2: Netscape Export (Tab-delimited)
.netflix.com	TRUE	/	TRUE	1735689600	NetflixId	abc123
.netflix.com	TRUE	/	TRUE	1735689600	SecureNetflixId	def456

# Format 3: Netscape Export (Space-delimited)
.netflix.com TRUE / TRUE 1735689600 NetflixId abc123
.netflix.com TRUE / TRUE 1735689600 SecureNetflixId def456

# Format 4: JSON Array
[
  {"name": "NetflixId", "value": "abc123"},
  {"name": "SecureNetflixId", "value": "def456"}
]

# Format 5: Key=Value Pairs
NetflixId=abc123; SecureNetflixId=def456; nfvdid=ghi789

🔍 Account Information Retrieved
Field	Description
Premium Status	Whether account is premium or free tier
Account Name	Primary account holder name
Plan Type	Subscription plan (Basic, Standard, Premium, etc.)
Plan Price	Monthly subscription cost
Profiles	List of all user profiles
Country	Account signup country
Email	Primary email address
Member Since	Account creation date
Next Billing	Next payment date
Video Quality	Maximum streaming quality (SD, HD, 4K)
Max Streams	Concurrent streaming limit
Payment Method	Payment type (card, PayPal, etc.)
Masked Card	Last 4 digits of card on file
Phone	Associated phone number
Payment Hold	Whether account is suspended due to payment issues
Email Verified	Email verification status
Phone Verified	Phone verification status
⚙️ Technical Architecture
Dual-Thread Design:

Thread 1: Telegram bot polling (receives messages, validates cookies)
Thread 2: Flask web server (health checks, status monitoring)
Cookie Validation Pipeline:

Parse input into standard cookie header format
Extract NetflixId from parsed cookies
Call Netflix's official iOS token generation API
Generate session nftokens for different device types
Validate account by accessing Netflix account pages
Extract and parse account information from HTML/JSON responses
Security Features:

✅ HTTPS/SSL verification enabled
✅ Direct API calls (no proxies)
✅ Timeout protection (25s max per request)
✅ HTML entity escaping for output
✅ Comprehensive error handling
🌐 Endpoints
GET / - Bot status dashboard
GET /health - Health check (returns JSON)
📊 Recognized Netflix Cookies
The bot recognizes these cookie names:

NetflixId (Primary session cookie)
SecureNetflixId (Secure variant)
NetflixCookies / __Secure-NetflixCookies
nfvdid (Device ID)
flwssn (Flash session)
And 8+ others for comprehensive parsing
✅ What Makes This Bot Special
✨ Smart Format Detection - No need to tell the bot which format you're using

⚡ Blazing Fast - Average response time under 5 seconds

🎯 Highly Accurate - Uses Netflix's official APIs

🛡️ Secure - Direct Netflix API validation, no man-in-the-middle

📱 Multi-Device Links - Get access links for any device type

📊 Detailed Info - Gets everything Netflix exposes about the account

🔧 Easy Deployment - Single Python file, minimal dependencies

🔗 Quick Links
Commands: /start | /help
Health Check: /health
Status Page: /
