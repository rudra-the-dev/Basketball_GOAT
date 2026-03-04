import discord
from discord.ext import commands
import config
import datetime

class Basic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @commands.command()
    async def suggest(self, ctx, *, suggestion: str):
        try:
            # Save suggestion to MongoDB
            await self.bot.db.suggestions.insert_one({
                "user_id": str(ctx.author.id),
                "username": ctx.author.display_name,
                "suggestion": suggestion,
                "date": datetime.datetime.utcnow().strftime("%b %d %Y")
            })

            # Confirm to user
            embed = discord.Embed(
                title="💡 Suggestion Received!",
                description=f"Thanks **{ctx.author.display_name}**! Your suggestion has been sent to the dev!",
                color=config.COLOR_SUCCESS
            )
            embed.add_field(name="Your Suggestion", value=suggestion, inline=False)
            embed.set_footer(text="The best suggestions get added to the game! 🐐")
            await ctx.send(embed=embed)

            # DM you the suggestion
            dev = await self.bot.fetch_user(int(config.DEV_ID))
            if dev:
                dm_embed = discord.Embed(
                    title="💡 New Suggestion!",
                    color=config.COLOR_GOLD
                )
                dm_embed.add_field(name="From", value=f"{ctx.author.display_name} ({ctx.author.id})", inline=False)
                dm_embed.add_field(name="Suggestion", value=suggestion, inline=False)
                dm_embed.add_field(name="Server", value=ctx.guild.name, inline=False)
                await dev.send(embed=dm_embed)

        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    

    @commands.command()
    async def ping(self, ctx):
        await ctx.send("Pong!")

    @commands.command()
    async def start(self, ctx):
        try:
            # Step 1 - Get the user's Discord ID as a string
            user_id = str(ctx.author.id)

            # Step 2 - Search the database for this user
            existing = await self.bot.db.users.find_one({"user_id": user_id})

            # Step 3 - If they already have an account stop here
            if existing:
                embed = discord.Embed(
                    description="⚠️ You already have an account! Use `bg profile` to view it.",
                    color=config.COLOR_ERROR
                )
                await ctx.send(embed=embed)
                return

            # Step 4 - Build the new user document
            new_user = {
    "user_id": user_id,
    "username": str(ctx.author),
    "currency": config.STARTING_CURRENCY,
    "team": [],
    "wins": 0,
    "losses": 0,
    "skill_points": 0,
    "title": "Rookie",
    "lineup": {
        "PG": None,
        "SG": None,
        "SF": None,
        "PF": None,
        "C": None
    }
            }

            # Step 5 - Insert into MongoDB
            await self.bot.db.users.insert_one(new_user)

            # Step 6 - Send welcome message
            embed = discord.Embed(
                title="🐐 Welcome to Basketball GOAT!",
                description=f"Hey {ctx.author.mention}! Your journey to becoming the GOAT starts now!",
                color=config.COLOR_GOLD
            )
            embed.add_field(name="💰 Currency", value=f"**{config.STARTING_CURRENCY}** coins", inline=True)
            embed.add_field(name="🏅 Title", value="**Rookie**", inline=True)
            embed.add_field(name="📋 Next Step", value="Use `bg profile` to view your account!", inline=False)
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"❌ An error occurred: {e}")

    @commands.command()
    async def profile(self, ctx, member: discord.Member = None):
        try:
            user_id = str(member.id) if member else str(ctx.author.id)
            user = await self.bot.db.users.find_one({"user_id": user_id})

            if not user:
                await ctx.send("❌ This user doesn't have an account! Use `bg start` to create one.")
                return

            total = user["wins"] + user["losses"]
            winrate = round((user["wins"] / total) * 100) if total > 0 else 0

            name = member.display_name if member else ctx.author.display_name
            avatar = member.display_avatar.url if member else ctx.author.display_avatar.url

            embed = discord.Embed(
                title=f"🐐 {name}'s Profile",
                color=config.COLOR_GOLD
            )
            embed.set_thumbnail(url=avatar)
            embed.add_field(name="🏅 Title", value=user["title"], inline=True)
            embed.add_field(name="💰 Currency", value=f"{user['currency']} coins", inline=True)
            embed.add_field(name="⭐ Skill Points", value=str(user["skill_points"]), inline=True)
            embed.add_field(name="✅ Wins", value=str(user["wins"]), inline=True)
            embed.add_field(name="❌ Losses", value=str(user["losses"]), inline=True)
            embed.add_field(name="📊 Win Rate", value=f"{winrate}%", inline=True)
            embed.add_field(name="🏀 Team Size", value=f"{len(user['team'])} players", inline=True)
            embed.set_footer(text="Basketball GOAT 🐐")
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"❌ An error occurred: {e}")


async def setup(bot):
    await bot.add_cog(Basic(bot))