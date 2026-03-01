import os
from dotenv import load_dotenv

load_dotenv()

#players data

BALL_API_KEY = os.getenv("BALL_API_KEY")

#bot

BOT_TOKEN=os.getenv("DISCORD_BOT_TOKEN")

PREFIX="bg "

#database

MONGO_URI=os.getenv("MONGO_URI")

DB_NAME="BasketballGoat"

#starting values


STARTING_CURRENCY=1000
STARTING_PLAYERS=[]


#colors


COLOR_PRIMARY = 0xF7941D   # NBA orange
COLOR_SUCCESS = 0x00FF00
COLOR_ERROR = 0xFF0000
COLOR_GOLD = 0xFFD700