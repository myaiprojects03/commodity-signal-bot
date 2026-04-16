# 📈 Commodity Signal Bot

**Gold (GC=F) · Silver (SI=F) · WTI Oil (CL=F)**

A professional-grade trading signal system for commodities.
Runs every 30 minutes. Sends clean, structured signals to your Gmail.
Deployable on free servers (PythonAnywhere, Render, Railway).

---

## 🎯 What It Does

- Monitors **Gold, Silver, and WTI Crude Oil** across 5 timeframes
- Generates **LONG / SHORT signals** with Entry, Stop Loss, TP1 / TP2 / TP3
- Assigns a **Confidence Score (0–100)** using 7 analysis modules
- Sends a **structured HTML email** every signal + a **status update every 30 min**
- Avoids overtrading with cooldown rules and hard discard logic

---

## 📊 Signal Example

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  BUY SIGNAL  |  Gold (GC=F)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Price        : $3,245.60
  Signal       : BUY  [STRONG]  78/100
  Timeframe    : 1H

  STRUCTURE
  ─────────────────────────────────────
  Zone Type    : SUPPORT
  Zone Range   : $3,220.00 – $3,238.00
  Touch Count  : 2x
  Zone Strength: Strong (Daily confluence)
  Round Number : Yes

  INDICATORS
  ─────────────────────────────────────
  EMA Trend    : Bullish ↑
  RSI (14)     : 28.4  🟢 Oversold
  MACD         : Bullish cross ↑
  BB Position  : At Lower Band
  Stochastic   : Oversold (K=18.2)
  Volume       : 🟢 High (1.8x avg)

  TREND ALIGNMENT
  ─────────────────────────────────────
  Weekly       : Bullish
  Daily        : Bullish
  4H           : Range
  Alignment    : ⚠️ Partial (2/3)

  RISK / REWARD
  ─────────────────────────────────────
  Entry        : $3,245.60
  Stop Loss    : $3,214.00
  TP1          : $3,290.00
  TP2          : $3,340.00
  TP3          : $3,420.00
  R:R Ratio    : 2.8:1  (STANDARD)

  CONFIDENCE   : 78/100  [STRONG]
  SIGNAL       : BUY

  📌 ENTRY ADVICE:
  Consider entering between $3,214.00 and
  $3,245.60 to avoid early stop-loss hit.
  Do NOT chase — wait for price to come to the zone.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🔧 Indicators Used

| Indicator | Purpose |
|-----------|---------|
| **EMA 20 / 50 / 200** | Trend direction, dynamic S/R, golden/death cross |
| **RSI (14)** | Momentum — 75/25 thresholds (commodities stay overbought longer) |
| **MACD (12/26/9)** | Momentum crossovers and divergence confirmation |
| **Bollinger Bands (20,2)** | Volatility squeezes and price extremes |
| **Stochastic (14,3)** | Short-term reversal confirmation |
| **ATR (14)** | Dynamic SL/TP sizing based on volatility |
| **RSI Divergence** | Bullish/bearish divergence detection |
| **Volume Analysis** | Confirms strength of moves |

---

## 🏗️ System Architecture

```
main.py (scheduler)
    │
    └── core/engine.py (every 30 min)
            │
            ├── data/fetcher.py          → yfinance (GC=F, SI=F, CL=F)
            │
            ├── analysis/
            │   ├── support_resistance.py → ATR-based S/R zones
            │   ├── trend.py             → Multi-TF HH/HL structure
            │   ├── indicators.py        → RSI, MACD, EMA, BB, Stoch
            │   ├── candle_patterns.py   → 16 pattern library
            │   ├── liquidity.py         → Sweeps, FVGs, equal levels
            │   ├── session.py           → COMEX/NYMEX session filter
            │   ├── risk_reward.py       → SL + 3 TPs + R:R filter
            │   └── confidence_scorer.py → Master score 0–100
            │
            ├── alerts/
            │   ├── cooldown.py          → 90-min per instrument/direction
            │   ├── formatter.py         → HTML + plain text email builder
            │   └── email_notifier.py    → Gmail SMTP sender
            │
            └── storage/db.py            → SQLite signal log
```

---

## ⚡ Quick Setup

### 1. Clone / Download

```bash
unzip commodity_signal_bot.zip
cd commodity_signal_bot
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

On PythonAnywhere:
```bash
pip install --user -r requirements.txt
```

### 3. Configure Gmail

1. Enable **2-Step Verification** on your Google account
2. Go to: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Create an App Password for "Mail"
4. Copy the 16-character password

### 4. Set Environment Variables

```bash
cp .env.example .env
```

Edit `.env`:
```
EMAIL_SENDER=your_gmail@gmail.com
EMAIL_PASSWORD=abcd efgh ijkl mnop   ← your 16-char App Password
EMAIL_RECIPIENT=destination@email.com
```

### 5. Test Everything

```bash
# Test email delivery
python main.py --email-test

# Run one analysis cycle (no scheduler)
python main.py --test
```

### 6. Run Live

```bash
python main.py
```

The bot will run immediately, then every 30 minutes automatically.

---

## 🚀 Deploy on PythonAnywhere (Free)

1. Sign up at [pythonanywhere.com](https://pythonanywhere.com)
2. Open a Bash console
3. Upload files (Files tab → Upload)
4. Install dependencies:
   ```bash
   pip3.10 install --user -r requirements.txt
   ```
5. Set up credentials in `.env`
6. **Option A** — Scheduled Task (cleaner):
   - Go to Tasks tab
   - Add: `python3.10 /home/yourusername/commodity_signal_bot/main.py --test`
   - Set interval: hourly (run twice manually = every 30 min)
   - **OR** use always-on task with `python main.py`

7. **Option B** — Always-on process (paid plan):
   - Add Always-on Task: `python3.10 /home/.../main.py`

---

## ⚙️ Tuning the Bot

All parameters live in `config.yaml`. Key ones:

```yaml
signals:
  min_confidence_score: 55   # Raise to 65 for fewer, higher-quality signals
  cooldown_minutes: 90       # Prevent repeat signals on same instrument

risk_reward:
  min_rr_ratio: 1.5          # Raise to 2.0 for better trade quality only

indicators:
  rsi_oversold: 25           # Lower = only extreme oversold (fewer buy signals)
  rsi_overbought: 75         # Raise = only extreme overbought (fewer sell signals)
```

---

## 📋 Signal Score Thresholds

| Score | Label | Action |
|-------|-------|--------|
| 85–100 | 🟣 ELITE | Highest conviction — act with full position |
| 70–84 | 🔵 STRONG | Strong setup — standard position size |
| 55–69 | ⚫ MODERATE | Valid but wait for confirmation |
| < 55 | Discarded | Signal not sent |

---

## 🚫 Hard Discard Rules (Signal Never Sent If...)

1. Dead zone session (22:00–00:00 UTC) — no liquidity
2. R:R ratio < 1.5:1 — poor risk/reward
3. Zone tested 5+ times (exhausted)
4. All 3 timeframes counter-trend
5. Climax volume without a rejection candle (exhaustion, not reversal)
6. Confidence score < threshold after full scoring

---

## 📁 File Structure

```
commodity_signal_bot/
├── main.py                    ← Entry point
├── config.yaml                ← All parameters (tune here)
├── .env                       ← Your credentials (never commit)
├── .env.example               ← Template
├── requirements.txt
│
├── core/
│   └── engine.py              ← Orchestration loop
│
├── data/
│   └── fetcher.py             ← yfinance data layer
│
├── analysis/
│   ├── indicators.py          ← RSI, MACD, EMA, BB, Stoch
│   ├── support_resistance.py  ← ATR-based S/R zones
│   ├── trend.py               ← Multi-TF HH/HL trend
│   ├── candle_patterns.py     ← 16 candle patterns
│   ├── liquidity.py           ← Sweeps, FVGs
│   ├── session.py             ← Trading session filter
│   ├── risk_reward.py         ← SL + 3×TP + R:R
│   └── confidence_scorer.py   ← Master score 0–100
│
├── alerts/
│   ├── cooldown.py            ← Signal cooldown
│   ├── formatter.py           ← Email builder (HTML + plain)
│   └── email_notifier.py      ← Gmail SMTP
│
├── storage/
│   └── db.py                  ← SQLite signal log
│
├── utils/
│   ├── helpers.py             ← ATR, indicators, swing detection
│   └── logger.py              ← Logging setup
│
└── logs/
    └── system.log             ← Auto-created on first run
```

---

## ⚠️ Disclaimer

This bot is for educational and informational purposes only.
It is NOT financial advice. Always manage your own risk.
Never trade with money you cannot afford to lose.
