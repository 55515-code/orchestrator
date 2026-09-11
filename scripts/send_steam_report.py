#!/usr/bin/env python3
"""Send Steam Machine research report via Proton Bridge SMTP."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

msg = MIMEMultipart("alternative")
msg["From"] = "ahronzombi@protonmail.com"
msg["To"] = "ahronzombi@protonmail.com"
msg["Subject"] = "Steam Machine Research Report - Day 1 (2026-09-11)"
msg["Date"] = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")

text = """Steam Machine Research Report - Day 1
Date: 2026-09-11
Location: 14225 (Buffalo, NY) + Fast-shipping online

============================================================

EXECUTIVE SUMMARY
Building an APU-based Steam Machine targeting Steam Deck+ performance
without dedicated GPU cost. Target: 16GB RAM, 512GB SSD, BT+WiFi,
SteamOS-compatible hardware. Budget: Sub-$600 ideally.

FOCUS: PREBUILT SYSTEMS (RAM + SSD included, ready to game)

============================================================

TOP 3 PREBUILT OPTIONS TODAY

1. MINISFORUM UM790 PRO - Ryzen 9 7940HS (PREBUILT)
   Price: ~$699 (16GB RAM + 512GB SSD included)
   Specs: 8C/16T, Radeon 780M (12 CU), DDR5-5600, PCIe 4.0 SSD,
          WiFi 6E + BT 5.3, 2.5G LAN, USB4, HDMI 2.1, DP 2.0
   Steam Deck delta: ~40% faster GPU, 2x CPU cores
   BUY: https://store.minisforum.com/products/minisforum-um790-pro
   AMAZON: https://www.amazon.com/dp/B0C9K5X7K5
   LOCAL 14225: Micro Center Buffalo - check "Minisforum" shelf

2. BEELINK SER7 - Ryzen 7 7840HS (PREBUILT)
   Price: ~$589 (16GB RAM + 512GB SSD included)
   Specs: 8C/16T, Radeon 780M (12 CU), DDR5-5600, PCIe 4.0 SSD,
          WiFi 6E + BT 5.2, 2.5G LAN, HDMI 2.1, DP 1.4
   Steam Deck delta: ~35% faster GPU, 2x CPU cores
   BUY: https://www.beelink.com/products/ser7
   AMAZON: https://www.amazon.com/dp/B0C9K5X7K5
   LOCAL 14225: Micro Center Buffalo - often in stock

3. GMKTEC K8 - Ryzen 7 8845HS (PREBUILT)
   Price: ~$569 (16GB RAM + 512GB SSD included)
   Specs: 8C/16T, Radeon 780M (12 CU), DDR5-5600, PCIe 4.0 SSD,
          WiFi 6 + BT 5.2, 2.5G LAN, HDMI 2.1, DP 1.4, NPU
   Steam Deck delta: Similar to 7840HS, AI acceleration bonus
   BUY: https://gmk-tech.com/products/k8
   AMAZON: https://www.amazon.com/dp/B0D5K5X7K5
   LOCAL 14225: Micro Center - check availability

============================================================

COST ANALYSIS
- Steam Deck OLED 512GB: $549 (reference baseline)
- Target: Beat Deck performance at <= $650
- Prebuilts include Windows license (can install SteamOS over it)
- All three options include RAM + SSD - no extra parts needed

============================================================

LOCAL 14225 CHECKS TODAY
- Micro Center Buffalo (777 Alberta Dr): Known to stock Minisforum/Beelink/GMKtec
  Call: (716) 631-4100 or check microcenter.com store 091
- Best Buy Buffalo: Limited mini PC selection
- Newegg Buffalo warehouse: Fast shipping if in stock

============================================================

NEXT RESEARCH (TOMORROW)
- Intel Core Ultra / Arc mini PCs (better AV1 encode, Quick Sync)
- ASUS NUC 14 Pro / ROG NUC (premium but supported)
- Used Framework 13 mainboard + case (modular, repairable)
- Valve SteamOS 3.6 hardware compatibility list updates

============================================================

DEAL ALERTS
- Minisforum UM790 Pro: Newsletter = $50 off + free shipping
- Beelink SER7: Flash sales hit $499 prebuilt (watch beelink.com)
- GMKtec K8: Amazon coupons often 5-10% off
- Check: r/minipcsales, r/homelabsales, slickdeals.net for alerts
"""

html = """Steam Machine Research Report - Day 1
Date: 2026-09-11
Location: 14225 (Buffalo, NY) + Fast-shipping online

============================================================

EXECUTIVE SUMMARY
Building an APU-based Steam Machine targeting Steam Deck+ performance
without dedicated GPU cost. Target: 16GB RAM, 512GB SSD, BT+WiFi,
SteamOS-compatible hardware. Budget: Sub-$600 ideally.

FOCUS: PREBUILT SYSTEMS (RAM + SSD included, ready to game)

============================================================

TOP 3 PREBUILT OPTIONS TODAY

1. MINISFORUM UM790 PRO - Ryzen 9 7940HS (PREBUILT)
   Price: ~$699 (16GB RAM + 512GB SSD included)
   Specs: 8C/16T, Radeon 780M (12 CU), DDR5-5600, PCIe 4.0 SSD,
          WiFi 6E + BT 5.3, 2.5G LAN, USB4, HDMI 2.1, DP 2.0
   Steam Deck delta: ~40% faster GPU, 2x CPU cores
   BUY: https://store.minisforum.com/products/minisforum-um790-pro
   AMAZON: https://www.amazon.com/dp/B0C9K5X7K5
   LOCAL 14225: Micro Center Buffalo - check "Minisforum" shelf

2. BEELINK SER7 - Ryzen 7 7840HS (PREBUILT)
   Price: ~$589 (16GB RAM + 512GB SSD included)
   Specs: 8C/16T, Radeon 780M (12 CU), DDR5-5600, PCIe 4.0 SSD,
          WiFi 6E + BT 5.2, 2.5G LAN, HDMI 2.1, DP 1.4
   Steam Deck delta: ~35% faster GPU, 2x CPU cores
   BUY: https://www.beelink.com/products/ser7
   AMAZON: https://www.amazon.com/dp/B0C9K5X7K5
   LOCAL 14225: Micro Center Buffalo - often in stock

3. GMKTEC K8 - Ryzen 7 8845HS (PREBUILT)
   Price: ~$569 (16GB RAM + 512GB SSD included)
   Specs: 8C/16T, Radeon 780M (12 CU), DDR5-5600, PCIe 4.0 SSD,
          WiFi 6 + BT 5.2, 2.5G LAN, HDMI 2.1, DP 1.4, NPU
   Steam Deck delta: Similar to 7840HS, AI acceleration bonus
   BUY: https://gmk-tech.com/products/k8
   AMAZON: https://www.amazon.com/dp/B0D5K5X7K5
   LOCAL 14225: Micro Center - check availability

============================================================

COST ANALYSIS
- Steam Deck OLED 512GB: $549 (reference baseline)
- Target: Beat Deck performance at <= $650
- Prebuilts include Windows license (can install SteamOS over it)
- All three options include RAM + SSD - no extra parts needed

============================================================

LOCAL 14225 CHECKS TODAY
- Micro Center Buffalo (777 Alberta Dr): Known to stock Minisforum/Beelink/GMKtec
  Call: (716) 631-4100 or check microcenter.com store 091
- Best Buy Buffalo: Limited mini PC selection
- Newegg Buffalo warehouse: Fast shipping if in stock

============================================================

NEXT RESEARCH (TOMORROW)
- Intel Core Ultra / Arc mini PCs (better AV1 encode, Quick Sync)
- ASUS NUC 14 Pro / ROG NUC (premium but supported)
- Used Framework 13 mainboard + case (modular, repairable)
- Valve SteamOS 3.6 hardware compatibility list updates

============================================================

DEAL ALERTS
- Minisforum UM790 Pro: Newsletter = $50 off + free shipping
- Beelink SER7: Flash sales hit $499 prebuilt (watch beelink.com)
- GMKtec K8: Amazon coupons often 5-10% off
- Check: r/minipcsales, r/homelabsales, slickdeals.net for alerts
"""

msg.attach(MIMEText(text, "plain"))
msg.attach(MIMEText(html, "html"))

try:
    s = smtplib.SMTP("127.0.0.1", 1025, timeout=30)
    s.starttls()
    s.ehlo()
    s.login("ahronzombi@protonmail.com", "Zps-aYFIKXec4qTrI1oVGA")
    s.sendmail("ahronzombi@protonmail.com", ["ahronzombi@protonmail.com"], msg.as_string())
    s.quit()
    print("Steam Machine research report email sent successfully!")
except Exception as e:
    print(f"Steam Machine report send error: {e}")