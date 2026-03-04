import discord 
from discord.ext import commands
import motor.motor_asyncio 
import config 
import os 
import asyncio
from flask import Flask
from threading import Thread

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=config.PREFIX, intents=intents)

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Basketball GOAT Bot is alive! 🐐🏀"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    flask_app.run(host='0.0.0.0', port=port)

Thread(target=run_flask).start()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

async def load_cogs():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")
            print(f"Loaded: {filename}")

async def main():
    global client
    client = motor.motor_asyncio.AsyncIOMotorClient(
        config.MONGO_URI,
        tls=True,
        tlsAllowInvalidCertificates=True
    )
    bot.db = client[config.DB_NAME]
    try:
        await client.admin.command('ping')
        print("✅ Connected to MongoDB successfully!")
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")

    await load_cogs()
    await bot.start(config.BOT_TOKEN)

asyncio.run(main())