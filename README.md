# 💰 Split Bill Buddy

A Telegram bot that helps split bills with GST and Service Charge, supporting both SGD 🇸🇬 and MYR 🇲🇾.  
Perfect for dining out with friends — no more messy mental math.

---

## ✨ Features
- Equal or custom amount split.
- Handles GST and Service Charge percentages.
- Interactive Telegram menu with buttons.
- Automatically cleans up old messages for a tidy chat.
- Works entirely in private or group chats.

---

## 📦 Requirements
- Python **3.9+**
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

---

## 🚀 Setup

### 1️⃣ Clone the Repository

git clone https://github.com/davidgoh24/Split_Bill_Buddy.git

bash:

cd split-bill-bot

### 2️⃣ Install Dependencies

pip install -r requirements.txt

### 3️⃣ Add Your Bot Token

You have two options:

Option A: Using .env (recommended)
1. Install python-dotenv:
bash:
pip install python-dotenv

2. Create a .env file in your project folder:
BOT_TOKEN=your_real_token_here

Option B: Hardcode (less secure)
Replace "YOUR_BOT_TOKEN_HERE" in split_bill_bot.py with your token.

### 4️⃣ Run the Bot

python split_bill_bot.py


💡 Bot Commands

| Command                       | Description                    |
| ----------------------------- | ------------------------------ |
| `/start`                      | Begin setup to split a bill    |
| `/help`                       | Show usage instructions        |
| `/addamount <name> <amount>`  | Add a person’s subtotal        |
| `/editamount <name> <amount>` | Edit a person’s subtotal       |
| `/remove <name>`              | Remove a person                |
| `/list`                       | Show all entries               |
| `/settotal <amount>`          | Change the bill total          |
| `/calculate`                  | Finalize and show breakdown    |
| `/reset`                      | Start over                     |
| `/stop`                       | Stop and clear everything      |
| `/delete`                     | Delete setup messages manually |





