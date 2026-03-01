import discord 
from discord.ext import commands
import motor.motor_asyncio 
import config 
import os 
import asyncio




intents=discord.Intents.default()
intents.message_content=True

bot=commands.Bot(command_prefix=config.PREFIX,intents=intents)

#database



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
  