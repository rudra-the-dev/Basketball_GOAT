import discord
from discord.ext import commands
import aiohttp
import config
import random
from bson import ObjectId


# ── Position eligibility ──────────────────────────────────────
def get_eligible_positions(position, target_pos):
    position = position.upper()
    if target_pos in ["PG", "SG"] and "G" in position:
        return True
    if target_pos in ["SF", "PF"] and "F" in position:
        return True
    if target_pos == "C" and "C" in position:
        return True
    if not any(x in position for x in ["G", "F", "C"]):
        return True  # unknown position can play anywhere
    return False


POSITIONS = ["PG", "SG", "SF", "PF", "C"]
POSITION_LABELS = {
    "PG": "🟢 Point Guard",
    "SG": "🔵 Shooting Guard",
    "SF": "🟡 Small Forward",
    "PF": "🟠 Power Forward",
    "C":  "🔴 Center"
}


# ── Single Position Select View ───────────────────────────────
class PositionSelectView(discord.ui.View):
    def __init__(self, pos, user_id, db, selections, all_players):
        super().__init__(timeout=120)
        self.pos = pos
        self.user_id = user_id
        self.db = db
        self.selections = selections
        self.all_players = all_players

        # Filter out already selected players AND check position eligibility
        already_selected = list(self.selections.values())
        eligible = [
            p for p in all_players
            if get_eligible_positions(p.get("position", ""), pos)
            and str(p["_id"]) not in already_selected
        ]

        # Fallback to all unselected players if none eligible for position
        if not eligible:
            eligible = [
                p for p in all_players
                if str(p["_id"]) not in already_selected
            ]

        options = [
            discord.SelectOption(
                label=f"{p['name']} (OVR: {p['ratings']['overall']})",
                value=str(p["_id"]),
                description=f"{p.get('position','?')} | {p['tier']} | {p.get('team','?')[:40]}"
            )
            for p in eligible[:25]
        ]

        select = discord.ui.Select(
            placeholder=f"Choose your {POSITION_LABELS[pos]}",
            options=options
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message(
                "❌ This lineup screen is not yours!",
                ephemeral=True
            )
            return

        # Save selection
        selected_id = interaction.data["values"][0]
        self.selections[self.pos] = selected_id

        # Find selected player name
        selected_player = next(
            (p for p in self.all_players if str(p["_id"]) == selected_id),
            None
        )
        player_name = selected_player["name"] if selected_player else "Unknown"

        # Disable this dropdown
        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content=f"✅ **{POSITION_LABELS[self.pos]}** → **{player_name}**",
            view=self
        )

        # Move to next position or finish
        current_index = POSITIONS.index(self.pos)
        next_index = current_index + 1

        if next_index < len(POSITIONS):
            next_pos = POSITIONS[next_index]
            next_view = PositionSelectView(
                next_pos,
                self.user_id,
                self.db,
                self.selections,
                self.all_players
            )
            await interaction.followup.send(
                f"🏀 Now select your **{POSITION_LABELS[next_pos]}**:",
                view=next_view
            )
        else:
            # All positions filled — save to MongoDB
            await self.db.users.update_one(
                {"user_id": self.user_id},
                {"$set": {"lineup": self.selections}}
            )
            await interaction.followup.send(
                "🐐 **Lineup saved! Your starting 5 is set and you're ready to play!**\n"
                "Use `bg play` to challenge someone! 🏀🔥"
            )


# ── Helper to start lineup flow ───────────────────────────────
async def start_lineup_flow(ctx, players, user_id, db):
    selections = {}
    first_pos = POSITIONS[0]
    view = PositionSelectView(first_pos, user_id, db, selections, players)
    await ctx.send(
        f"🏀 **Set Your Starting Lineup!**\nStart by selecting your **{POSITION_LABELS[first_pos]}**:",
        view=view
    )


# ── Players Cog ───────────────────────────────────────────────
class Players(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def generate_default_ratings(self, position):
        base = random.randint(40, 80)

        if "G" in position:
            ratings = {
                "shooting": min(99, base + random.randint(0, 15)),
                "driving":  min(99, base + random.randint(0, 10)),
                "passing":  min(99, base + random.randint(0, 15)),
                "defense":  min(99, base - random.randint(0, 10)),
                "clutch":   min(99, base + random.randint(0, 10)),
                "stamina":  min(99, base + random.randint(0, 5))
            }
        elif "F" in position:
            ratings = {
                "shooting": min(99, base + random.randint(0, 10)),
                "driving":  min(99, base + random.randint(0, 15)),
                "passing":  min(99, base + random.randint(0, 5)),
                "defense":  min(99, base + random.randint(0, 10)),
                "clutch":   min(99, base + random.randint(0, 8)),
                "stamina":  min(99, base + random.randint(0, 8))
            }
        else:
            ratings = {
                "shooting": min(99, base - random.randint(0, 10)),
                "driving":  min(99, base + random.randint(0, 15)),
                "passing":  min(99, base - random.randint(0, 5)),
                "defense":  min(99, base + random.randint(0, 15)),
                "clutch":   min(99, base + random.randint(0, 5)),
                "stamina":  min(99, base + random.randint(0, 10))
            }

        for key in ratings:
            ratings[key] = max(30, ratings[key])

        overall = round(sum(ratings.values()) / 6)
        ratings["overall"] = overall
        return ratings

    def get_tier(self, overall):
        if overall >= 90:
            return "Legend"
        elif overall >= 75:
            return "Star"
        elif overall >= 55:
            return "Average"
        else:
            return "Common"

    # ── bg fetchplayers (admin only) ─────────────────────────
    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
          if isinstance(error, commands.CommandNotFound):
            website_url =     config.WEBSITE_URL
            embed = discord.Embed(
            title="❓ Command Not Found",
            description=f"That command doesn't exist!\n\nVisit our website for more info:\n🌐 {website_url}",
            color=config.COLOR_ERROR
        )
            embed.set_footer(text="Use bg help to see all commands!")
            await ctx.send(embed=embed)
    
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def fetchplayers(self, ctx):
        await ctx.send("⏳ Fetching NBA players... this will take about 30 seconds!")

        headers = {"Authorization": config.BALL_API_KEY}
        players_added = 0

        async with aiohttp.ClientSession() as session:
            for page in range(1, 3):
                url = f"https://api.balldontlie.io/v1/players?per_page=100&page={page}"

                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        await ctx.send(f"❌ API error: {resp.status}")
                        return
                    data = await resp.json()

                players = data.get("data", [])
                if not players:
                    break

                for player in players:
                    player_id = player["id"]

                    existing = await self.bot.db.players.find_one({"player_id": player_id})
                    if existing:
                        continue

                    position = player.get("position", "")
                    ratings = self.generate_default_ratings(position)
                    tier = self.get_tier(ratings["overall"])

                    new_player = {
                        "player_id": player_id,
                        "name": f"{player['first_name']} {player['last_name']}",
                        "position": position,
                        "team": player.get("team", {}).get("full_name", "Free Agent"),
                        "ratings": ratings,
                        "tier": tier
                    }

                    await self.bot.db.players.insert_one(new_player)
                    players_added += 1

                await ctx.send(f"✅ Page {page} done!")

        await ctx.send(f"🐐 Finished! Added **{players_added}** players to the database!")

    # ── bg claim ─────────────────────────────────────────────
    @commands.command()
    async def claim(self, ctx):
        try:
            user_id = str(ctx.author.id)

            user = await self.bot.db.users.find_one({"user_id": user_id})
            if not user:
                await ctx.send("❌ You don't have an account! Use `bg start` first.")
                return

            if user.get("claimed_starter"):
                await ctx.send("⚠️ You already claimed your starter pack!")
                return

            star_player = await self.bot.db.players.aggregate([
                {"$match": {"tier": {"$in": ["Legend", "Star"]}}},
                {"$sample": {"size": 1}}
            ]).to_list(1)

            average_players = await self.bot.db.players.aggregate([
                {"$match": {"tier": "Average"}},
                {"$sample": {"size": 2}}
            ]).to_list(2)

            common_players = await self.bot.db.players.aggregate([
                {"$match": {"tier": "Common"}},
                {"$sample": {"size": 2}}
            ]).to_list(2)

            starter_pack = star_player + average_players + common_players

            if len(starter_pack) < 5:
                await ctx.send("❌ Not enough players in database! Ask admin to run `bg fetchplayers` first.")
                return

            player_ids = [str(p["_id"]) for p in starter_pack]
            await self.bot.db.users.update_one(
                {"user_id": user_id},
                {
                    "$set": {"claimed_starter": True},
                    "$push": {"team": {"$each": player_ids}}
                }
            )

            tier_emojis = {
                "Legend": "🔴 Legend",
                "Star": "🟠 Star",
                "Average": "🟡 Average",
                "Common": "⚪ Common"
            }

            embed = discord.Embed(
                title="🎁 Your Starter Pack!",
                description="Welcome to Basketball GOAT! Here are your first 5 players:",
                color=config.COLOR_GOLD
            )

            for player in starter_pack:
                r = player["ratings"]
                tier_label = tier_emojis.get(player["tier"], "⚪ Common")
                embed.add_field(
                    name=f"{tier_label} | {player['name']}",
                    value=(
                        f"**OVR: {r['overall']}** | {player['position']} | {player['team']}\n"
                        f"🎯 SHT:{r['shooting']} 🏃 DRV:{r['driving']} "
                        f"🎳 PAS:{r['passing']} 🛡️ DEF:{r['defense']} "
                        f"⚡ CLU:{r['clutch']} 💪 STM:{r['stamina']}"
                    ),
                    inline=False
                )

            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            embed.set_footer(text="Now set your starting lineup below! 🐐")
            await ctx.send(embed=embed)

            # Fetch players fresh for lineup flow
            players = []
            for player_id in player_ids:
                player = await self.bot.db.players.find_one({"_id": ObjectId(player_id)})
                if player:
                    players.append(player)

            await start_lineup_flow(ctx, players, user_id, self.bot.db)

        except Exception as e:
            await ctx.send(f"❌ An error occurred: {e}")

    # ── bg stockmarket (admin only) ──────────────────────────
    @commands.command()
    @commands.has_permissions(administrator=True)
    async def stockmarket(self, ctx):
        try:
            await ctx.send("⏳ Stocking the market with players...")

            await self.bot.db.market.delete_many({"seller_id": "bot"})

            tier_prices = {
                "Legend": 5000,
                "Star": 2000,
                "Average": 800,
                "Common": 300
            }

            total_added = 0
            for tier, price in tier_prices.items():
                players = await self.bot.db.players.aggregate([
                    {"$match": {"tier": tier}},
                    {"$sample": {"size": 50}}
                ]).to_list(50)

                for player in players:
                    await self.bot.db.market.insert_one({
                        "player_id": str(player["_id"]),
                        "seller_id": "bot",
                        "seller_name": "🤖 Bot Store",
                        "price": price
                    })
                    total_added += 1

            await ctx.send(
                f"✅ Market stocked with **{total_added}** players!\n"
                f"💰 Prices:\n"
                f"🔴 Legend — 5000 coins\n"
                f"🟠 Star — 2000 coins\n"
                f"🟡 Average — 800 coins\n"
                f"⚪ Common — 300 coins"
            )

        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    # ── bg lineup ─────────────────────────────────────────────
    @commands.command()
    async def lineup(self, ctx):
        try:
            user_id = str(ctx.author.id)

            user = await self.bot.db.users.find_one({"user_id": user_id})
            if not user:
                await ctx.send("❌ You don't have an account! Use `bg start` first.")
                return

            if not user["team"]:
                await ctx.send("❌ Your team is empty! Use `bg claim` first.")
                return

            if "lineup" not in user:
                await self.bot.db.users.update_one(
                    {"user_id": user_id},
                    {"$set": {"lineup": {"PG": None, "SG": None, "SF": None, "PF": None, "C": None}}}
                )

            players = []
            for player_id in user["team"]:
                player = await self.bot.db.players.find_one({"_id": ObjectId(player_id)})
                if player:
                    players.append(player)

            await start_lineup_flow(ctx, players, user_id, self.bot.db)

        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    # ── bg team ───────────────────────────────────────────────
    @commands.command()
    async def team(self, ctx, member: discord.Member = None):
        try:
            user_id = str(member.id) if member else str(ctx.author.id)

            user = await self.bot.db.users.find_one({"user_id": user_id})
            if not user:
                await ctx.send("❌ This user doesn't have an account! Use `bg start` first.")
                return

            if not user["team"]:
                await ctx.send("❌ This team is empty! Use `bg claim` to get a starter pack.")
                return

            players = []
            for player_id in user["team"]:
                player = await self.bot.db.players.find_one({"_id": ObjectId(player_id)})
                if player:
                    players.append(player)

            players.sort(key=lambda p: p["ratings"]["overall"], reverse=True)

            tier_emojis = {
                "Legend": "🔴",
                "Star": "🟠",
                "Average": "🟡",
                "Common": "⚪"
            }

            name = member.display_name if member else ctx.author.display_name
            avatar = member.display_avatar.url if member else ctx.author.display_avatar.url

            embed = discord.Embed(
                title=f"🏀 {name}'s Team",
                description=f"Total Players: **{len(players)}**",
                color=config.COLOR_PRIMARY
            )

            for player in players:
                r = player["ratings"]
                emoji = tier_emojis.get(player["tier"], "⚪")
                embed.add_field(
                    name=f"{emoji} {player['name']} — OVR: {r['overall']}",
                    value=(
                        f"{player['position']} | {player['team']}\n"
                        f"🎯{r['shooting']} 🏃{r['driving']} 🎳{r['passing']} "
                        f"🛡️{r['defense']} ⚡{r['clutch']} 💪{r['stamina']}"
                    ),
                    inline=False
                )

            embed.set_thumbnail(url=avatar)
            embed.set_footer(text="Basketball GOAT 🐐")
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"❌ An error occurred: {e}")


async def setup(bot):
    await bot.add_cog(Players(bot))
    