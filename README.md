# 💰 Split Bill Buddy

A Telegram bot to easily split bills with **GST** and **Service Charge**, supporting both **SGD 🇸🇬** and **MYR 🇲🇾**.  
Perfect for dining out with friends — no more messy mental math.

Try it on Telegram! Just add @Splitbillcalculator_bot to your groups and give admin permission or just chat with it :)


---

## ✨ Features
- Split bills equally or by custom amounts.
- Automatically calculate GST and Service Charge.
- Interactive Telegram menus with buttons.
- Auto-cleans old messages for a clutter-free chat.
- Works in **private** or **group** chats.

---

## 📦 Requirements
- **Python 3.9+**
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather)

---

## 🚀 Setup

### 1️⃣ Clone the Repository
```bash
git clone https://github.com/davidgoh24/Split_Bill_Buddy.git
cd Split_Bill_Buddy
```

### 2️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

### 3️⃣ Add Your Bot Token

**Option A: Using `.env` (Recommended)**
```bash
pip install python-dotenv
```
Create a `.env` file in your project folder:
```env
BOT_TOKEN=your_real_token_here
```

**Option B: Hardcode (Less Secure)**  
Replace `"YOUR_BOT_TOKEN_HERE"` inside `split_bill_bot.py` with your actual token.

### 4️⃣ Run the Bot
```bash
python split_bill_bot.py
```

---

## 💡 Bot Commands

| Command                       | Description                         |
| ----------------------------- | ----------------------------------- |
| `/start`                      | Begin setup to split a bill         |
| `/help`                       | Show usage instructions             |
| `/addamount <name> <amount>`  | Add a person’s subtotal              |
| `/editamount <name> <amount>` | Edit a person’s subtotal             |
| `/remove <name>`              | Remove a person                      |
| `/list`                       | Show all entries                     |
| `/settotal <amount>`          | Change the bill total                |
| `/calculate`                  | Finalize and show breakdown          |
| `/reset`                      | Restart the bill-splitting process   |
| `/stop`                       | Stop and clear everything            |
| `/delete`                     | Manually delete setup messages       |

---
