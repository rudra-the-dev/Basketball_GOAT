import discord
from discord.ext import commands
import config
import asyncio
import random
from bson import ObjectId
import anthropic

# ── Anthropic client for commentary ──────────────────────────
ai_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# ── Active matches tracker ────────────────────────────────────
# Prevents same user from being in 2 matches at once
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
    """Uses Claude API to generate unique match commentary."""
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
- Match the energy to the result (big play = big energy, turnover = shocked energy)
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
        # Fallback commentary if API fails
        fallbacks = {
            "make": [
                f"{attacker_name} gets the bucket! 🏀",
                f"Nothing but net for {attacker_name}! 💦",
                f"{attacker_name} is COOKING tonight! 🔥",
            ],
            "miss": [
                f"{attacker_name} can't buy a bucket! 😤",
                f"{defender_name} with the stop! 🛡️",
                f"Off the rim! {defender_name} holds strong! 💪",
            ],
            "block": [
                f"BLOCKED by {defender_name}! GET THAT OUTTA HERE! 🚫",
                f"{defender_name} swats it away! Incredible defense! 🙅",
            ],
            "steal": [
                f"{defender_name} picks the pocket! Turnover! 😱",
                f"STOLEN by {defender_name}! The crowd goes wild! 🎉",
            ],
            "turnover": [
                f"{attacker_name} coughs it up! Costly mistake! 😬",
                f"Turnover! {defender_name}'s defense was too much! 💪",
            ],
            "foul": [
                f"Foul called! {attacker_name} heads to the line! 🎯",
                f"Contact! Free throws coming up! 🎯",
            ]
        }
        result_key = result.lower()
        for key in fallbacks:
            if key in result_key:
                return random.choice(fallbacks[key])
        return f"{attacker_name} makes a move! 🏀"


# ─────────────────────────────────────────────────────────────
# OUTCOME CALCULATOR
# ─────────────────────────────────────────────────────────────
def calculate_outcome(action, attacker_player, attacker_ratings, defender_player, defender_ratings):
    """
    Takes both players' choices and calculates what happened.
    Returns (result_type, points, description)
    result_type: 'make_2', 'make_3', 'miss', 'block', 'steal', 'turnover', 'foul'
    """
    rand = random.randint(1, 100)

    if action == "drive":
        # Drive to basket — uses attacker DRV vs defender DEF
        atk = attacker_ratings["driving"]
        dfn = defender_ratings["defense"]
        advantage = (atk - dfn) + random.randint(-15, 15)

        if advantage > 20:
            return ("make_2", 2, "drive")
        elif advantage > 5:
            # Coin flip between make and foul
            if rand > 50:
                return ("make_2", 2, "drive")
            else:
                return ("foul", 2, "drive")  # 2 free throws
        elif advantage > -10:
            if rand > 60:
                return ("miss", 0, "drive")
            else:
                return ("block", 0, "drive")
        else:
            return ("block", 0, "drive")

    elif action == "pull_up":
        # Pull up jumper — uses attacker SHT vs defender DEF
        atk = attacker_ratings["shooting"]
        dfn = defender_ratings["defense"]
        advantage = (atk - dfn) + random.randint(-15, 15)

        if advantage > 25:
            return ("make_2", 2, "pull_up")
        elif advantage > 10:
            if rand > 40:
                return ("make_2", 2, "pull_up")
            else:
                return ("miss", 0, "pull_up")
        elif advantage > -5:
            return ("miss", 0, "pull_up")
        else:
            if rand > 70:
                return ("miss", 0, "pull_up")
            else:
                return ("steal", 0, "pull_up")

    elif action == "three":
        # Three pointer — uses SG/SF shooting vs defender DEF
        atk = attacker_ratings["shooting"]
        dfn = defender_ratings["defense"]
        advantage = (atk - dfn) + random.randint(-20, 20)

        if advantage > 30:
            return ("make_3", 3, "three")
        elif advantage > 10:
            if rand > 45:
                return ("make_3", 3, "three")
            else:
                return ("miss", 0, "three")
        else:
            return ("miss", 0, "three")

    elif action == "post_up":
        # Post up — uses C/PF driving vs defender DEF
        atk = attacker_ratings["driving"]
        dfn = defender_ratings["defense"]
        advantage = (atk - dfn) + random.randint(-15, 15)

        if advantage > 20:
            return ("make_2", 2, "post_up")
        elif advantage > 0:
            if rand > 45:
                return ("make_2", 2, "post_up")
            else:
                return ("foul", 2, "post_up")
        else:
            if rand > 60:
                return ("miss", 0, "post_up")
            else:
                return ("steal", 0, "post_up")

    elif action == "pick_roll":
        # Pick and roll — uses PG passing + C driving vs defender
        atk = (attacker_ratings["passing"] + attacker_ratings["driving"]) // 2
        dfn = defender_ratings["defense"]
        advantage = (atk - dfn) + random.randint(-15, 15)

        if advantage > 20:
            return ("make_2", 2, "pick_roll")
        elif advantage > 5:
            if rand > 50:
                return ("make_2", 2, "pick_roll")
            else:
                return ("miss", 0, "pick_roll")
        else:
            if rand > 65:
                return ("turnover", 0, "pick_roll")
            else:
                return ("miss", 0, "pick_roll")

    return ("miss", 0, "unknown")


def calculate_free_throws(attacker_ratings):
    """Calculate free throw results."""
    shooting = attacker_ratings["shooting"]
    made = 0
    for _ in range(2):
        threshold = 30 + (shooting * 0.5)
        if random.randint(1, 100) <= threshold:
            made += 1
    return made


# ─────────────────────────────────────────────────────────────
# POLL VIEW — Interactive possession polls
# ─────────────────────────────────────────────────────────────
class PossessionPollView(discord.ui.View):
    def __init__(self, options, user_id, timeout=30):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.chosen = None

        for i, (label, value, description) in enumerate(options):
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
                    "❌ This is not your play to make!",
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
    def __init__(self, channel, player_a, player_b, team_a, team_b, lineup_a, lineup_b, amount, ppq, db):
        self.channel = channel
        self.player_a = player_a  # Discord user object
        self.player_b = player_b
        self.team_a = team_a      # dict of position -> player document
        self.team_b = team_b
        self.lineup_a = lineup_a  # dict of position -> player_id string
        self.lineup_b = lineup_b
        self.amount = amount
        self.ppq = ppq
        self.db = db

        self.score_a = 0
        self.score_b = 0
        self.quarter = 1
        self.momentum = None  # 'a' or 'b' or None

    def get_attack_options(self, lineup, team):
        """Generate attack options based on lineup ratings."""
        pg = team.get("PG")
        sg = team.get("SG")
        sf = team.get("SF")
        pf = team.get("PF")
        c = team.get("C")

        options = []

        if pg:
            options.append((
                f"🏃 Drive (PG DRV:{pg['ratings']['driving']})",
                "drive",
                f"{pg['name']} drives to the basket"
            ))
            options.append((
                f"🎯 Pull Up (PG SHT:{pg['ratings']['shooting']})",
                "pull_up",
                f"{pg['name']} pulls up for the jumper"
            ))

        if sg:
            options.append((
                f"🌐 Pass to SG 3PT (SG SHT:{sg['ratings']['shooting']})",
                "three",
                f"Kick out to {sg['name']} for three"
            ))

        if c:
            options.append((
                f"💪 Post Up C (C DRV:{c['ratings']['driving']})",
                "post_up",
                f"Feed {c['name']} in the post"
            ))

        if pg and c:
            options.append((
                f"🔄 Pick & Roll (PG PAS:{pg['ratings']['passing']})",
                "pick_roll",
                f"{pg['name']} runs pick and roll with {c['name']}"
            ))

        return options[:4]  # max 4 options

    def get_defense_options(self, lineup, team, attack_action):
        """Generate defense options based on attack action."""
        pg = team.get("PG")
        sg = team.get("SG")
        pf = team.get("PF")
        c = team.get("C")

        options = []

        if attack_action == "drive":
            if c:
                options.append((f"🛡️ Contest at Rim (C DEF:{c['ratings']['defense']})", "contest", "Contest at rim"))
            if pg:
                options.append((f"⚡ Gamble Steal (PG CLU:{pg['ratings']['clutch']})", "steal_attempt", "Gamble for steal"))
            options.append(("🚧 Drop Back", "drop_back", "Drop back and protect paint"))
            options.append(("🤝 Intentional Foul", "foul", "Foul to stop the drive"))

        elif attack_action in ["pull_up", "three"]:
            if sg:
                options.append((f"🖐️ Contest Shot (SG DEF:{sg['ratings']['defense']})", "contest", "Contest the shot"))
            if pg:
                options.append((f"⚡ Rush the Shooter (PG DEF:{pg['ratings']['defense']})", "rush", "Rush the shooter"))
            options.append(("📐 Sag Off", "sag", "Sag off and protect paint"))
            if pf:
                options.append((f"🔀 Switch (PF DEF:{pf['ratings']['defense']})", "switch", "Switch defensively"))

        elif attack_action == "post_up":
            if c:
                options.append((f"🛡️ Hold Position (C DEF:{c['ratings']['defense']})", "contest", "Hold position in post"))
            if pf:
                options.append((f"🤝 Double Team (PF DEF:{pf['ratings']['defense']})", "double", "Send double team"))
            options.append(("⚡ Reach for Steal", "steal_attempt", "Reach for steal"))
            options.append(("🤝 Intentional Foul", "foul", "Foul in the post"))

        elif attack_action == "pick_roll":
            if pg:
                options.append((f"💨 Fight Through (PG CLU:{pg['ratings']['clutch']})", "fight_through", "Fight through screen"))
            options.append(("🔀 Switch", "switch", "Switch on the pick"))
            if pf:
                options.append((f"🛡️ Help Defense (PF DEF:{pf['ratings']['defense']})", "help", "Help defense on roll man"))
            options.append(("📐 Drop Coverage", "drop", "Drop and protect paint"))

        return options[:4]

    def get_attacker_ratings(self, team, action):
        """Get relevant player and ratings for the attack action."""
        if action in ["drive", "pull_up"]:
            player = team.get("PG")
        elif action == "three":
            player = team.get("SG") or team.get("SF")
        elif action == "post_up":
            player = team.get("C") or team.get("PF")
        elif action == "pick_roll":
            player = team.get("PG")
        else:
            player = team.get("PG")

        if not player:
            player = list(team.values())[0]

        return player, player["ratings"]

    def get_defender_ratings(self, team, action):
        """Get relevant defending player and ratings."""
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

        return player, player["ratings"]

    async def send_poll(self, user, options, prompt):
        """Send a poll to a user via DM and wait for response."""
        view = PossessionPollView(
            [(label, value, desc) for label, value, desc in options],
            str(user.id),
            timeout=30
        )
        try:
            msg = await user.send(prompt, view=view)
        except discord.Forbidden:
            await self.channel.send(f"❌ {user.mention} has DMs disabled! Match cancelled.")
            return None

        await view.wait()

        if view.chosen is None:
            # Auto pick first option on timeout
            view.chosen = options[0][1]
            await msg.edit(content=f"{prompt}\n⏰ Time ran out! Auto-selected: **{options[0][0]}**", view=view)

        return view.chosen

    async def run_possession(self, attacker, attacker_team, defender, defender_team, possession_num, quarter):
        """Run a single possession."""
        # Get attack options
        attack_options = self.get_attack_options(attacker_team, attacker_team)

        # Send attack poll
        attack_prompt = (
            f"🏀 **Q{quarter} | Possession {possession_num}**\n"
            f"Score: {self.player_a.display_name} **{self.score_a}** — **{self.score_b}** {self.player_b.display_name}\n\n"
            f"**Your turn to ATTACK!** Choose your play:"
        )

        # Both polls sent simultaneously
        attack_task = asyncio.create_task(self.send_poll(attacker, attack_options, attack_prompt))

        # Wait for attack choice first
        attack_choice = await attack_task

        if attack_choice is None:
            return False

        # Get defense options based on attack choice
        defense_options = self.get_defense_options(defender_team, defender_team, attack_choice)

        # Get attacker info
        atk_player, atk_ratings = self.get_attacker_ratings(attacker_team, attack_choice)
        dfn_player, dfn_ratings = self.get_defender_ratings(defender_team, attack_choice)

        # Post in channel what action was chosen
        action_labels = {
            "drive": "🏃 Driving to basket",
            "pull_up": "🎯 Pulling up for jumper",
            "three": "🌐 Kicking out for three",
            "post_up": "💪 Posting up",
            "pick_roll": "🔄 Running pick and roll"
        }
        await self.channel.send(
            f"⚔️ **{attacker.display_name}** chose: **{action_labels.get(attack_choice, attack_choice)}**\n"
            f"🛡️ **{defender.display_name}** — make your defensive move! Check your DMs!"
        )

        defense_prompt = (
            f"🛡️ **Q{quarter} | Possession {possession_num}**\n"
            f"**{attacker.display_name}** is {action_labels.get(attack_choice, 'attacking')}!\n\n"
            f"**Choose your DEFENSE:**"
        )

        defense_choice = await self.send_poll(defender, defense_options, defense_prompt)

        if defense_choice is None:
            return False

        # Calculate outcome
        result_type, points, action_type = calculate_outcome(
            attack_choice, atk_player, atk_ratings, dfn_player, dfn_ratings
        )

        # Handle momentum boost
        momentum_text = None
        if self.momentum == ("a" if attacker == self.player_a else "b"):
            points = points  # momentum gives slight boost (handled in calculate_outcome randomness)
            momentum_text = "🔥 ON FIRE!"

        # Update score
        if result_type == "make_2":
            if attacker == self.player_a:
                self.score_a += 2
            else:
                self.score_b += 2
            self.momentum = "a" if attacker == self.player_a else "b"

        elif result_type == "make_3":
            if attacker == self.player_a:
                self.score_a += 3
            else:
                self.score_b += 3
            self.momentum = "a" if attacker == self.player_a else "b"

        elif result_type == "foul":
            ft_made = calculate_free_throws(atk_ratings)
            if attacker == self.player_a:
                self.score_a += ft_made
            else:
                self.score_b += ft_made
            points = ft_made
            self.momentum = None

        else:
            self.momentum = "a" if defender == self.player_a else "b"

        # Generate commentary
        result_descriptions = {
            "make_2": "Success — 2 point basket",
            "make_3": "Success — 3 point basket",
            "miss": "Miss — shot didn't fall",
            "block": "Blocked — spectacular block",
            "steal": "Stolen — turnover on bad pass",
            "turnover": "Turnover — lost the ball",
            "foul": f"Foul — went to free throws, made {points}/2"
        }

        commentary = await generate_commentary(
            atk_player["name"],
            POSITION_LABELS.get(
                next((pos for pos, p in attacker_team.items() if p and p["_id"] == atk_player["_id"]), "PG"),
                "Player"
            ),
            action_labels.get(attack_choice, attack_choice),
            dfn_player["name"],
            POSITION_LABELS.get(
                next((pos for pos, p in defender_team.items() if p and p["_id"] == dfn_player["_id"]), "PG"),
                "Player"
            ),
            result_descriptions.get(result_type, result_type),
            self.score_a,
            self.score_b,
            self.player_a.display_name,
            self.player_b.display_name,
            momentum_text
        )

        # Post result in channel
        result_embed = discord.Embed(
            description=commentary,
            color=0xF7941D if result_type in ["make_2", "make_3"] else 0xFF0000 if result_type in ["block", "steal", "turnover"] else 0xFFFFFF
        )
        result_embed.set_footer(text=f"{self.player_a.display_name} {self.score_a} — {self.score_b} {self.player_b.display_name}")
        await self.channel.send(embed=result_embed)

        return True

    async def run_quarter(self, quarter):
        """Run a full quarter."""
        await self.channel.send(
            f"```\n🏀 QUARTER {quarter} STARTING!\n"
            f"{self.player_a.display_name} {self.score_a} — {self.score_b} {self.player_b.display_name}\n```"
        )
        await asyncio.sleep(3)

        # Alternate possessions
        for possession in range(1, self.ppq + 1):
            # Determine who attacks this possession (alternating)
            if possession % 2 == 1:
                attacker = self.player_a
                attacker_team = self.team_a
                defender = self.player_b
                defender_team = self.team_b
            else:
                attacker = self.player_b
                attacker_team = self.team_b
                defender = self.player_a
                defender_team = self.team_a

            success = await self.run_possession(
                attacker, attacker_team,
                defender, defender_team,
                possession, quarter
            )

            if not success:
                return False

            await asyncio.sleep(2)

        return True

    async def run_match(self):
        """Run the full match."""
        # Tip off
        c_a = self.team_a.get("C")
        c_b = self.team_b.get("C")

        c_a_rating = c_a["ratings"]["overall"] if c_a else 50
        c_b_rating = c_b["ratings"]["overall"] if c_b else 50

        tipoff_embed = discord.Embed(
            title="🏀 TIP OFF!",
            description=(
                f"**{self.player_a.display_name}** vs **{self.player_b.display_name}**\n\n"
                f"🔴 {c_a['name'] if c_a else 'Unknown'} (OVR: {c_a_rating}) jumps for **{self.player_a.display_name}**\n"
                f"🔵 {c_b['name'] if c_b else 'Unknown'} (OVR: {c_b_rating}) jumps for **{self.player_b.display_name}**\n\n"
                f"⏳ Rolling for tip off..."
            ),
            color=config.COLOR_GOLD
        )
        await self.channel.send(embed=tipoff_embed)
        await asyncio.sleep(3)

        # Higher rated center wins tip off (with small randomness)
        a_roll = c_a_rating + random.randint(-10, 10)
        b_roll = c_b_rating + random.randint(-10, 10)

        if a_roll >= b_roll:
            tipoff_winner = self.player_a
            await self.channel.send(f"🏆 **{self.player_a.display_name}** wins the tip off! First possession is theirs! 🔥")
        else:
            tipoff_winner = self.player_b
            await self.channel.send(f"🏆 **{self.player_b.display_name}** wins the tip off! First possession is theirs! 🔥")

        await asyncio.sleep(3)

        # Run 4 quarters
        for quarter in range(1, 5):
            success = await self.run_quarter(quarter)
            if not success:
                await self.channel.send("❌ Match cancelled due to inactivity.")
                return

            if quarter < 4:
                # Quarter break
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

        # Match over
        await self.end_match()

    async def end_match(self):
        """Handle match end — update DB, transfer coins, announce winner."""
        if self.score_a > self.score_b:
            winner = self.player_a
            loser = self.player_b
            winner_score = self.score_a
            loser_score = self.score_b
        elif self.score_b > self.score_a:
            winner = self.player_b
            loser = self.player_a
            winner_score = self.score_b
            loser_score = self.score_a
        else:
            # Tie — nobody wins or loses coins, no record change
            await self.channel.send(
                embed=discord.Embed(
                    title="🤝 IT'S A TIE!",
                    description=(
                        f"**{self.player_a.display_name}** {self.score_a} — {self.score_b} **{self.player_b.display_name}**\n\n"
                        f"What a game! Coins returned to both players!"
                    ),
                    color=config.COLOR_PRIMARY
                )
            )
            # Return coins
            await self.db.users.update_one(
                {"user_id": str(self.player_a.id)},
                {"$inc": {"currency": self.amount}}
            )
            await self.db.users.update_one(
                {"user_id": str(self.player_b.id)},
                {"$inc": {"currency": self.amount}}
            )
            return

        # Update winner
        await self.db.users.update_one(
            {"user_id": str(winner.id)},
            {
                "$inc": {
                    "wins": 1,
                    "currency": self.amount * 2,  # gets back own coins + opponent's
                    "skill_points": 3
                }
            }
        )

        # Update loser
        await self.db.users.update_one(
            {"user_id": str(loser.id)},
            {
                "$inc": {
                    "losses": 1,
                    "skill_points": 1  # consolation skill point
                }
            }
        )

        # Final embed
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

        # Can't accept own challenge
        if opponent.id == self.challenger.id:
            await interaction.response.send_message(
                "❌ You can't accept your own challenge!",
                ephemeral=True
            )
            return

        user_id = str(opponent.id)

        # Check opponent has account
        opponent_data = await self.db.users.find_one({"user_id": user_id})
        if not opponent_data:
            await interaction.response.send_message(
                "❌ You don't have an account! Use `bg start` first.",
                ephemeral=True
            )
            return

        # Check opponent has team
        if not opponent_data.get("team"):
            await interaction.response.send_message(
                "❌ You don't have a team! Use `bg claim` first.",
                ephemeral=True
            )
            return

        # Check opponent has lineup
        lineup = opponent_data.get("lineup", {})
        if not all(lineup.get(pos) for pos in ["PG", "SG", "SF", "PF", "C"]):
            await interaction.response.send_message(
                "❌ Your lineup isn't set! Use `bg lineup` first.",
                ephemeral=True
            )
            return

        # Check opponent has enough coins
        if opponent_data.get("currency", 0) < self.amount:
            await interaction.response.send_message(
                f"❌ You don't have enough coins! You need **{self.amount}** coins.",
                ephemeral=True
            )
            return

        # Check opponent not already in a match
        if user_id in active_matches:
            await interaction.response.send_message(
                "❌ You're already in a match!",
                ephemeral=True
            )
            return

        # All good — start match
        self.accepted = True
        self.stop()

        # Disable button
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content=f"🔥 **{self.challenger.display_name}** vs **{opponent.display_name}** — Match Starting!",
            view=self
        )

        # Deduct coins from both
        await self.db.users.update_one(
            {"user_id": str(self.challenger.id)},
            {"$inc": {"currency": -self.amount}}
        )
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$inc": {"currency": -self.amount}}
        )

        # Add both to active matches
        active_matches.add(str(self.challenger.id))
        active_matches.add(user_id)

        # Fetch challenger data
        challenger_data = await self.db.users.find_one({"user_id": str(self.challenger.id)})
        challenger_lineup = challenger_data.get("lineup", {})

        # Build team dicts (position -> player document)
        async def build_team(lineup_data, db):
            team = {}
            for pos, player_id in lineup_data.items():
                if player_id:
                    player = await db.players.find_one({"_id": ObjectId(player_id)})
                    if player:
                        team[pos] = player
            return team

        team_a = await build_team(challenger_lineup, self.db)
        team_b = await build_team(lineup, self.db)

        # Start match
        engine = MatchEngine(
            self.channel,
            self.challenger,
            opponent,
            team_a,
            team_b,
            challenger_lineup,
            lineup,
            self.amount,
            self.ppq,
            self.db
        )

        try:
            await engine.run_match()
        finally:
            # Always remove from active matches when done
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

        # Parse ppq
        try:
            possessions = int(ppq.replace("/q", "").replace("q", "").strip())
        except ValueError:
            await ctx.send("❌ Invalid format! Use like `bg play 500 6/q`")
            return

        # Validate possessions
        if possessions < 3:
            await ctx.send("❌ Minimum possessions per quarter is **3/q**!")
            return
        if possessions > 10:
            await ctx.send("❌ Maximum possessions per quarter is **10/q**!")
            return

        # Validate amount
        if amount < 100:
            await ctx.send("❌ Minimum wager is **100 coins**!")
            return

        # Check account
        user = await self.bot.db.users.find_one({"user_id": user_id})
        if not user:
            await ctx.send("❌ You don't have an account! Use `bg start` first.")
            return

        # Check team
        if not user.get("team"):
            await ctx.send("❌ You don't have a team! Use `bg claim` first.")
            return

        # Check lineup
        lineup = user.get("lineup", {})
        if not all(lineup.get(pos) for pos in ["PG", "SG", "SF", "PF", "C"]):
            await ctx.send("❌ Your lineup isn't fully set! Use `bg lineup` first.")
            return

        # Check coins
        if user.get("currency", 0) < amount:
            await ctx.send(f"❌ You don't have enough coins! You need **{amount}** coins.")
            return

        # Check not already in match
        if user_id in active_matches:
            await ctx.send("❌ You're already in a match!")
            return

        # Send challenge message
        embed = discord.Embed(
            title="🏀 OPEN CHALLENGE!",
            description=(
                f"**{ctx.author.display_name}** is looking for a match!\n\n"
                f"💰 Wager: **{amount}** coins\n"
                f"📊 Possessions/Quarter: **{possessions}/q**\n"
                f"⏳ **60 seconds** to accept!\n\n"
                f"Click ✅ to accept the challenge!"
            ),
            color=config.COLOR_GOLD
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)

        view = MatchAcceptView(ctx.author, amount, possessions, self.bot.db, ctx.channel)
        msg = await ctx.send(embed=embed, view=view)

        # Wait for match to be accepted or timeout
        await view.wait()

        if not view.accepted:
            # Nobody accepted
            for item in view.children:
                item.disabled = True
            await msg.edit(
                content="❌ **Matchmaking timed out!** No one accepted the challenge.",
                embed=None,
                view=view
            )


async def setup(bot):
    await bot.add_cog(Match(bot))