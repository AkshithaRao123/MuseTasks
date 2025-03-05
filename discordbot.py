import discord
from discord import app_commands
from discord.ext import commands
import os
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync() 

@bot.tree.command(name="task_daily", description="Submit your daily tasks")
async def task_daily(interaction: discord.Interaction):
    user_id = interaction.user.id
    # Redirect the user to the Flask server's form page
    form_url = f"http://localhost:5000/form?user_id={user_id}"
    await interaction.response.send_message(f"Please fill out your tasks here: {form_url}", ephemeral=True)

bot.run(TOKEN)