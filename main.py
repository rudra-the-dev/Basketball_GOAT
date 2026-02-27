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

client = motor.motor_asyncio.AsyncIOMotorClient(
    config.MONGO_URI,
    tls=True,
    tlsAllowInvalidCertificates=True
)

@bot.event
async def on_ready():
  print(f"Logged in as {bot.user} (ID: {bot.user.id})")
  

@bot.command()
async def hello(ctx):
  await ctx.send(f"Hey{ctx.author.mention}")

@bot.command()
async def goodbye(ctx):
  await ctx.send(f"Goodbye{ctx.author.mention}")

@bot.command()
async def myhelp(ctx):
  await ctx.send("My commands are: ping,hello,goodbye,help")



async def load_cogs():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")
            print(f"Loaded: {filename}")


async def main():
    try:
        await client.admin.command('ping')
        print("✅ Connected to MongoDB successfully!")
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
    
    await load_cogs()
    await bot.start(config.BOT_TOKEN)

asyncio.run(main())
  