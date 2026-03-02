import discord
from discord.ext import commands
import config
import asyncio
import random
from bson import ObjectId
import anthropic
import datetime

# ── Anthropic client for commentary ──────────────────────────
ai_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# ── Active matches tracker ────────────────────────────────────
active_matches = set()

# ── Position labels ───────────────────────────────────────────
POSITION_LABELS = {
    "PG": "Point Guard",
    "SG": "Shooting Guard",
    "SF": "Small Forward",
    "PF": "Power Forward",
    "C": "Center"
}

# ─────────────────────────────────────────────────────────────
# COMMENTARY ENGINE
# ─────────────────────────────────────────────────────────────
async def generate_commentary(attacker_name, attacker_pos, action, defender_name, defender_pos, result, score_a, score_b, name_a, name_b, momentum=None):
    try:
        prompt = f"""You are an NBA game commentator. Generate ONE short, exciting commentary line (max 2 sentences) for this basketball play.

Attacker: {attacker_name} ({attacker_pos})
Action chosen: {action}
Defender: {defender_name} ({defender_pos})
Result: {result}
Current score: {name_a} {score_a} — {name_b} {score_b}
{f'Momentum: {momentum}' if momentum else ''}

Rules:
- Be dramatic and exciting
- Mention the player names
- Match the energy to the result
- Keep it under 2 sentences
- End with an emoji that matches the play
- Do NOT use quotation marks"""

        response = ai_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception:
        fallbacks = {
            "make": [f"{attacker_name} gets the bucket! 🏀", f"Nothing but net! 💦", f"{attacker_name} is COOKING! 🔥"],
            "miss": [f"{attacker_name} can't buy a bucket! 😤", f"{defender_name} with the stop! 🛡️"],
            "block": [f"BLOCKED by {defender_name}! 🚫", f"{defender_name} swats it away! 🙅"],
            "steal": [f"STOLEN by {defender_name}! 😱", f"Turnover! {defender_name} picks the pocket! 🎉"],
            "turnover": [f"{attacker_name} coughs it up! 😬", f"Costly turnover! 💪"],
            "foul": [f"Foul called! Free throws coming! 🎯"]
        }
        for key in fallbacks:
            if key in result.lower():
                return random.choice(fallbacks[key])
        return f"{attacker_name} makes a move! 🏀"


# ─────────────────────────────────────────────────────────────
# OUTCOME CALCULATOR
# ─────────────────────────────────────────────────────────────
def calculate_outcome(action, atk_ratings, dfn_ratings):
    rand = random.randint(1, 100)

    if action == "drive":
        advantage = (atk_ratings["driving"] - dfn_ratings["defense"]) + random.randint(-15, 15)
        if advantage > 20:
            return ("make_2", 2)
        elif advantage > 5:
            return ("make_2", 2) if rand > 50 else ("foul", 2)
        elif advantage > -10:
            return ("miss", 0) if rand > 40 else ("block", 0)
        else:
            return ("block", 0)

    elif action == "pull_up":
        advantage = (atk_ratings["shooting"] - dfn_ratings["defense"]) + random.randint(-15, 15)
        if advantage > 25:
            return ("make_2", 2)
        elif advantage > 10:
            return ("make_2", 2) if rand > 40 else ("miss", 0)
        elif advantage > -5:
            return ("miss", 0)
        else:
            return ("miss", 0) if rand > 30 else ("steal", 0)

    elif action == "three":
        advantage = (atk_ratings["shooting"] - dfn_ratings["defense"]) + random.randint(-20, 20)
        if advantage > 30:
            return ("make_3", 3)
        elif advantage > 10:
            return ("make_3", 3) if rand > 45 else ("miss", 0)
        else:
            return ("miss", 0)

    elif action == "post_up":
        advantage = (atk_ratings["driving"] - dfn_ratings["defense"]) + random.randint(-15, 15)
        if advantage > 20:
            return ("make_2", 2)
        elif advantage > 0:
            return ("make_2", 2) if rand > 45 else ("foul", 2)
        else:
            return ("miss", 0) if rand > 40 else ("steal", 0)

    elif action == "pick_roll":
        avg_atk = (atk_ratings["passing"] + atk_ratings["driving"]) // 2
        advantage = (avg_atk - dfn_ratings["defense"]) + random.randint(-15, 15)
        if advantage > 20:
            return ("make_2", 2)
        elif advantage > 5:
            return ("make_2", 2) if rand > 50 else ("miss", 0)
        else:
            return ("turnover", 0) if rand > 65 else ("miss", 0)

    return ("miss", 0)


def calculate_free_throws(atk_ratings):
    made = 0
    for _ in range(2):
        if random.randint(1, 100) <= 30 + (atk_ratings["shooting"] * 0.5):
            made += 1
    return made


# ─────────────────────────────────────────────────────────────
# POSSESSION POLL VIEW — shown in channel
# ─────────────────────────────────────────────────────────────
class PossessionPollView(discord.ui.View):
    def __init__(self, options, user_id, timeout=30):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.chosen = None

        for i, (label, value) in enumerate(options):
            btn = discord.ui.Button(
                label=label,
                custom_id=value,
                style=discord.ButtonStyle.primary,
                row=i // 2
            )
            btn.callback = self.make_callback(value)
            self.add_item(btn)

    def make_callback(self, value):
        async def callback(interaction: discord.Interaction):
            if str(interaction.user.id) != self.user_id:
                await interaction.response.send_message(
                    "❌ It's not your turn!",
                    ephemeral=True
                )
                return
            self.chosen = value
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(view=self)
            self.stop()
        return callback

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ─────────────────────────────────────────────────────────────
# MATCH ENGINE
# ─────────────────────────────────────────────────────────────
class MatchEngine:
    def __init__(self, channel, player_a, player_b, team_a, team_b, amount, ppq, db):
        self.channel = channel
        self.player_a = player_a
        self.player_b = player_b
        self.team_a = team_a
        self.team_b = team_b
        self.amount = amount
        self.ppq = ppq
        self.db = db
        self.score_a = 0
        self.score_b = 0
        self.momentum = None

    def get_attack_options(self, team):
        pg = team.get("PG")
        sg = team.get("SG")
        c = team.get("C")
        options = []
        if pg:
            options.append((f"🏃 Drive (DRV:{pg['ratings']['driving']})", "drive"))
            options.append((f"🎯 Pull Up (SHT:{pg['ratings']['shooting']})", "pull_up"))
        if sg:
            options.append((f"🌐 SG Three (SHT:{sg['ratings']['shooting']})", "three"))
        if c:
            options.append((f"💪 Post Up (DRV:{c['ratings']['driving']})", "post_up"))
        if pg and c:
            options.append((f"🔄 Pick & Roll (PAS:{pg['ratings']['passing']})", "pick_roll"))
        return options[:4]

    def get_defense_options(self, team, attack_action):
        pg = team.get("PG")
        sg = team.get("SG")
        pf = team.get("PF")
        c = team.get("C")
        options = []
        if attack_action == "drive":
            if c:
                options.append((f"🛡️ Contest Rim (DEF:{c['ratings']['defense']})", "contest"))
            if pg:
                options.append((f"⚡ Gamble Steal (CLU:{pg['ratings']['clutch']})", "steal_attempt"))
            options.append(("🚧 Drop Back", "drop_back"))
            options.append(("🤝 Intentional Foul", "foul"))
        elif attack_action in ["pull_up", "three"]:
            if sg:
                options.append((f"🖐️ Contest Shot (DEF:{sg['ratings']['defense']})", "contest"))
            if pg:
                options.append((f"⚡ Rush Shooter (DEF:{pg['ratings']['defense']})", "rush"))
            options.append(("📐 Sag Off", "sag"))
            if pf:
                options.append((f"🔀 Switch (DEF:{pf['ratings']['defense']})", "switch"))
        elif attack_action == "post_up":
            if c:
                options.append((f"🛡️ Hold Position (DEF:{c['ratings']['defense']})", "contest"))
            if pf:
                options.append((f"🤝 Double Team (DEF:{pf['ratings']['defense']})", "double"))
            options.append(("⚡ Reach for Steal", "steal_attempt"))
            options.append(("🤝 Intentional Foul", "foul"))
        elif attack_action == "pick_roll":
            if pg:
                options.append((f"💨 Fight Through (CLU:{pg['ratings']['clutch']})", "fight_through"))
            options.append(("🔀 Switch", "switch"))
            if pf:
                options.append((f"🛡️ Help Defense (DEF:{pf['ratings']['defense']})", "help"))
            options.append(("📐 Drop Coverage", "drop"))
        return options[:4]

    def get_attacker_ratings(self, team, action):
        if action in ["drive", "pull_up", "pick_roll"]:
            player = team.get("PG")
        elif action == "three":
            player = team.get("SG") or team.get("SF")
        elif action == "post_up":
            player = team.get("C") or team.get("PF")
        else:
            player = team.get("PG")
        if not player:
            player = list(team.values())[0]
        return player

    def get_defender_ratings(self, team, action):
        if action == "drive":
            player = team.get("C") or team.get("PF")
        elif action in ["pull_up", "three"]:
            player = team.get("SG") or team.get("PG")
        elif action == "post_up":
            player = team.get("C") or team.get("PF")
        elif action == "pick_roll":
            player = team.get("PG") or team.get("C")
        else:
            player = team.get("PG")
        if not player:
            player = list(team.values())[0]
        return player

    async def run_possession(self, attacker, attacker_team, defender, defender_team, possession_num, quarter):
        action_labels = {
            "drive": "🏃 Driving to basket",
            "pull_up": "🎯 Pulling up for jumper",
            "three": "🌐 Kicking out for three",
            "post_up": "💪 Posting up",
            "pick_roll": "🔄 Running pick and roll"
        }

        # ── ATTACK POLL ──
        attack_options = self.get_attack_options(attacker_team)
        attack_view = PossessionPollView(attack_options, str(attacker.id), timeout=30)

        atk_msg = await self.channel.send(
            f"🏀 **Q{quarter} | Possession {possession_num}** | {self.player_a.display_name} **{self.score_a}** — **{self.score_b}** {self.player_b.display_name}\n"
            f"{attacker.mention} **Your turn to ATTACK!** Choose your play:",
            view=attack_view
        )

        await attack_view.wait()

        if attack_view.chosen is None:
            attack_view.chosen = attack_options[0][1]
            await atk_msg.edit(content=f"⏰ **{attacker.display_name}** took too long! Auto-selected: **{attack_options[0][0]}**", view=attack_view)

        attack_choice = attack_view.chosen

        # ── DEFENSE POLL ──
        defense_options = self.get_defense_options(defender_team, attack_choice)
        defense_view = PossessionPollView(defense_options, str(defender.id), timeout=30)

        def_msg = await self.channel.send(
            f"🛡️ **{attacker.display_name}** chose: **{action_labels.get(attack_choice, attack_choice)}**\n"
            f"{defender.mention} **Choose your DEFENSE:**",
            view=defense_view
        )

        await defense_view.wait()

        if defense_view.chosen is None:
            defense_view.chosen = defense_options[0][1]
            await def_msg.edit(content=f"⏰ **{defender.display_name}** took too long! Auto-selected: **{defense_options[0][0]}**", view=defense_view)

        # ── CALCULATE OUTCOME ──
        atk_player = self.get_attacker_ratings(attacker_team, attack_choice)
        dfn_player = self.get_defender_ratings(defender_team, attack_choice)

        result_type, points = calculate_outcome(attack_choice, atk_player["ratings"], dfn_player["ratings"])

        # Handle foul free throws
        if result_type == "foul":
            ft_made = calculate_free_throws(atk_player["ratings"])
            points = ft_made

        # Update score
        if result_type in ["make_2", "make_3", "foul"]:
            if attacker == self.player_a:
                self.score_a += points
            else:
                self.score_b += points
            self.momentum = "a" if attacker == self.player_a else "b"
        else:
            self.momentum = "a" if defender == self.player_a else "b"

        # ── COMMENTARY ──
        result_descriptions = {
            "make_2": "Success — 2 point basket",
            "make_3": "Success — 3 point basket",
            "miss": "Miss — shot didn't fall",
            "block": "Blocked — spectacular block",
            "steal": "Stolen — turnover",
            "turnover": "Turnover — lost the ball",
            "foul": f"Foul — {points}/2 free throws made"
        }

        commentary = await generate_commentary(
            atk_player["name"],
            next((POSITION_LABELS.get(pos, pos) for pos, p in attacker_team.items() if p and p.get("_id") == atk_player.get("_id")), "Player"),
            action_labels.get(attack_choice, attack_choice),
            dfn_player["name"],
            next((POSITION_LABELS.get(pos, pos) for pos, p in defender_team.items() if p and p.get("_id") == dfn_player.get("_id")), "Player"),
            result_descriptions.get(result_type, result_type),
            self.score_a,
            self.score_b,
            self.player_a.display_name,
            self.player_b.display_name,
            "🔥 ON FIRE!" if self.momentum else None
        )

        # Color based on result
        if result_type in ["make_2", "make_3"]:
            color = 0x00FF00
        elif result_type == "foul":
            color = 0xFFFF00
        elif result_type in ["block", "steal", "turnover"]:
            color = 0xFF0000
        else:
            color = 0x888888

        result_embed = discord.Embed(description=commentary, color=color)
        result_embed.set_footer(text=f"🏀 {self.player_a.display_name} {self.score_a} — {self.score_b} {self.player_b.display_name}")
        await self.channel.send(embed=result_embed)
        await asyncio.sleep(2)

        return True

    async def run_quarter(self, quarter):
        await self.channel.send(
            f"```\n🏀 QUARTER {quarter} STARTING!\n"
            f"{self.player_a.display_name} {self.score_a} — {self.score_b} {self.player_b.display_name}\n```"
        )
        await asyncio.sleep(3)

        for possession in range(1, self.ppq + 1):
            if possession % 2 == 1:
                attacker, attacker_team = self.player_a, self.team_a
                defender, defender_team = self.player_b, self.team_b
            else:
                attacker, attacker_team = self.player_b, self.team_b
                defender, defender_team = self.player_a, self.team_a

            success = await self.run_possession(attacker, attacker_team, defender, defender_team, possession, quarter)
            if not success:
                return False

        return True

    async def run_match(self):
        # Tip off
        c_a = self.team_a.get("C")
        c_b = self.team_b.get("C")
        c_a_rating = c_a["ratings"]["overall"] if c_a else 50
        c_b_rating = c_b["ratings"]["overall"] if c_b else 50

        tipoff_embed = discord.Embed(
            title="🏀 TIP OFF!",
            description=(
                f"**{self.player_a.display_name}** vs **{self.player_b.display_name}**\n\n"
                f"🔴 {c_a['name'] if c_a else 'Unknown'} (OVR:{c_a_rating}) jumps for **{self.player_a.display_name}**\n"
                f"🔵 {c_b['name'] if c_b else 'Unknown'} (OVR:{c_b_rating}) jumps for **{self.player_b.display_name}**\n\n"
                f"⏳ Rolling for tip off..."
            ),
            color=config.COLOR_GOLD
        )
        await self.channel.send(embed=tipoff_embed)
        await asyncio.sleep(3)

        a_roll = c_a_rating + random.randint(-10, 10)
        b_roll = c_b_rating + random.randint(-10, 10)

        if a_roll >= b_roll:
            await self.channel.send(f"🏆 **{self.player_a.display_name}** wins the tip off! First possession is theirs! 🔥")
        else:
            await self.channel.send(f"🏆 **{self.player_b.display_name}** wins the tip off! First possession is theirs! 🔥")

        await asyncio.sleep(3)

        # Run 4 quarters
        for quarter in range(1, 5):
            success = await self.run_quarter(quarter)
            if not success:
                await self.channel.send("❌ Match cancelled due to inactivity.")
                return

            if quarter < 4:
                quarter_embed = discord.Embed(
                    title=f"🏁 END OF QUARTER {quarter}",
                    description=(
                        f"**{self.player_a.display_name}** {self.score_a} — {self.score_b} **{self.player_b.display_name}**\n\n"
                        f"⏸️ Quarter {quarter + 1} starts in 10 seconds..."
                    ),
                    color=config.COLOR_PRIMARY
                )
                await self.channel.send(embed=quarter_embed)
                await asyncio.sleep(10)

        await self.end_match()

    async def end_match(self):
        if self.score_a > self.score_b:
            winner, loser = self.player_a, self.player_b
        elif self.score_b > self.score_a:
            winner, loser = self.player_b, self.player_a
        else:
            # Tie
            await self.channel.send(embed=discord.Embed(
                title="🤝 IT'S A TIE!",
                description=(
                    f"**{self.player_a.display_name}** {self.score_a} — {self.score_b} **{self.player_b.display_name}**\n\n"
                    f"Coins returned to both players!"
                ),
                color=config.COLOR_PRIMARY
            ))
            await self.db.users.update_one({"user_id": str(self.player_a.id)}, {"$inc": {"currency": self.amount}})
            await self.db.users.update_one({"user_id": str(self.player_b.id)}, {"$inc": {"currency": self.amount}})
            return

        await self.db.users.update_one(
            {"user_id": str(winner.id)},
            {"$inc": {"wins": 1, "currency": self.amount * 2, "skill_points": 3}}
        )
        await self.db.users.update_one(
            {"user_id": str(loser.id)},
            {"$inc": {"losses": 1, "skill_points": 1}}
        )

        db_record = {
    "player_a_id": str(self.player_a.id),
    "player_a_name": self.player_a.display_name,
    "player_b_id": str(self.player_b.id),
    "player_b_name": self.player_b.display_name,
    "score_a": self.score_a,
    "score_b": self.score_b,
    "winner_id": str(winner.id),
    "amount": self.amount,
    "date": datetime.datetime.utcnow().strftime("%b %d %Y")
}
await self.db.match_history.insert_one(db_record)

        final_embed = discord.Embed(
            title="🏆 FINAL SCORE",
            description=(
                f"**{self.player_a.display_name}** {self.score_a} — {self.score_b} **{self.player_b.display_name}**\n\n"
                f"🎉 **{winner.mention} WINS!**\n"
                f"💰 +**{self.amount * 2}** coins\n"
                f"⭐ +**3** skill points\n\n"
                f"😤 **{loser.mention}** — Better luck next time!\n"
                f"⭐ +**1** skill point for competing"
            ),
            color=config.COLOR_GOLD
        )
        final_embed.set_footer(text="Basketball GOAT 🐐 | Use bg play to run it back!")
        await self.channel.send(embed=final_embed)


# ─────────────────────────────────────────────────────────────
# MATCH ACCEPT VIEW
# ─────────────────────────────────────────────────────────────
class MatchAcceptView(discord.ui.View):
    def __init__(self, challenger, amount, ppq, db, channel):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.amount = amount
        self.ppq = ppq
        self.db = db
        self.channel = channel
        self.accepted = False

    @discord.ui.button(label="✅ Accept Challenge", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        opponent = interaction.user

        if opponent.id == self.challenger.id:
            await interaction.response.send_message("❌ You can't accept your own challenge!", ephemeral=True)
            return

        user_id = str(opponent.id)
        opponent_data = await self.db.users.find_one({"user_id": user_id})

        if not opponent_data:
            await interaction.response.send_message("❌ You don't have an account! Use `bg start` first.", ephemeral=True)
            return

        if not opponent_data.get("team"):
            await interaction.response.send_message("❌ You don't have a team! Use `bg claim` first.", ephemeral=True)
            return

        lineup = opponent_data.get("lineup", {})
        if not all(lineup.get(pos) for pos in ["PG", "SG", "SF", "PF", "C"]):
            await interaction.response.send_message("❌ Your lineup isn't set! Use `bg lineup` first.", ephemeral=True)
            return

        if opponent_data.get("currency", 0) < self.amount:
            await interaction.response.send_message(f"❌ You need **{self.amount}** coins to accept!", ephemeral=True)
            return

        if user_id in active_matches:
            await interaction.response.send_message("❌ You're already in a match!", ephemeral=True)
            return

        self.accepted = True
        self.stop()

        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"🔥 **{self.challenger.display_name}** vs **{opponent.display_name}** — Match Starting! 🏀",
            embed=None,
            view=self
        )

        # Deduct coins
        await self.db.users.update_one({"user_id": str(self.challenger.id)}, {"$inc": {"currency": -self.amount}})
        await self.db.users.update_one({"user_id": user_id}, {"$inc": {"currency": -self.amount}})

        # Add to active matches
        active_matches.add(str(self.challenger.id))
        active_matches.add(user_id)

        # Build teams
        challenger_data = await self.db.users.find_one({"user_id": str(self.challenger.id)})
        challenger_lineup = challenger_data.get("lineup", {})

        async def build_team(lineup_data):
            team = {}
            for pos, player_id in lineup_data.items():
                if player_id:
                    player = await self.db.players.find_one({"_id": ObjectId(player_id)})
                    if player:
                        team[pos] = player
            return team

        team_a = await build_team(challenger_lineup)
        team_b = await build_team(lineup)

        engine = MatchEngine(
            self.channel,
            self.challenger,
            opponent,
            team_a,
            team_b,
            self.amount,
            self.ppq,
            self.db
        )

        try:
            await engine.run_match()
        finally:
            active_matches.discard(str(self.challenger.id))
            active_matches.discard(user_id)

    async def on_timeout(self):
        self.accepted = False
        for item in self.children:
            item.disabled = True


# ─────────────────────────────────────────────────────────────
# MATCH COG
# ─────────────────────────────────────────────────────────────
class Match(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="play")
    async def play(self, ctx, amount: int = 100, ppq: str = "5/q"):
        user_id = str(ctx.author.id)

        try:
            possessions = int(ppq.replace("/q", "").replace("q", "").strip())
        except ValueError:
            await ctx.send("❌ Invalid format! Use like `bg play 500 6/q`")
            return

        if possessions < 3:
            await ctx.send("❌ Minimum is **3/q**!")
            return
        if possessions > 10:
            await ctx.send("❌ Maximum is **10/q**!")
            return
        if amount < 100:
            await ctx.send("❌ Minimum wager is **100 coins**!")
            return

        user = await self.bot.db.users.find_one({"user_id": user_id})
        if not user:
            await ctx.send("❌ You don't have an account! Use `bg start` first.")
            return

        if not user.get("team"):
            await ctx.send("❌ You don't have a team! Use `bg claim` first.")
            return

        lineup = user.get("lineup", {})
        if not all(lineup.get(pos) for pos in ["PG", "SG", "SF", "PF", "C"]):
            await ctx.send("❌ Your lineup isn't fully set! Use `bg lineup` first.")
            return

        if user.get("currency", 0) < amount:
            await ctx.send(f"❌ You need **{amount}** coins to play!")
            return

        if user_id in active_matches:
            await ctx.send("❌ You're already in a match!")
            return

        embed = discord.Embed(
            title="🏀 OPEN CHALLENGE!",
            description=(
                f"**{ctx.author.display_name}** is looking for a match!\n\n"
                f"💰 Wager: **{amount}** coins\n"
                f"📊 Possessions/Quarter: **{possessions}/q**\n"
                f"⏳ **60 seconds** to accept!\n\n"
                f"Click ✅ to accept!"
            ),
            color=config.COLOR_GOLD
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)

        view = MatchAcceptView(ctx.author, amount, possessions, self.bot.db, ctx.channel)
        msg = await ctx.send(embed=embed, view=view)

        await view.wait()

        if not view.accepted:
            for item in view.children:
                item.disabled = True
            await msg.edit(
                content="❌ **Matchmaking timed out!** No one accepted.",
                embed=None,
                view=view
            )


async def setup(bot):
    await bot.add_cog(Match(bot))
      