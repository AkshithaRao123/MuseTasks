from flask import Flask, request, render_template, jsonify
import requests
import os
import datetime
from pymongo import MongoClient
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import threading
import re
# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import InstalledAppFlow
# from googleapiclient.discovery import build
load_dotenv()

app = Flask(__name__)

TOKEN = os.getenv("DISCORD_BOT_TOKEN")

GUILD = discord.Object(id=1341366670417203293)
webhook_url = f"{os.getenv('WEBHOOK_DAILY')}?wait=true"

MONGO_URI = os.getenv("MONGO_URI") 
# GOOGLE_CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH")

client = MongoClient(MONGO_URI)
db = client.tasks_db 
user_tasks_collection = db.user_tasks 
daily_task_messages_collection = db.daily_task_messages

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# # Google Calendar Setup
# SCOPES = ['https://www.googleapis.com/auth/calendar']
# creds = None
# if os.path.exists('token.json'):
#     creds = Credentials.from_authorized_user_file('token.json', SCOPES)
# if not creds or not creds.valid:
#     flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDENTIALS_PATH, SCOPES)
#     creds = flow.run_local_server(port=0)
#     with open('token.json', 'w') as token:
#         token.write(creds.to_json())
# calendar_service = build('calendar', 'v3', credentials=creds)

@bot.command(guild=GUILD)
@commands.is_owner()
async def sync_command(ctx, guild=GUILD):
    await bot.tree.sync(guild=guild)
    print("Commands synced")
    await ctx.send("✅ Commands synced successfully!", delete_after = 20)


date_today = datetime.datetime.now().strftime("%d-%m-%Y (%A)")

daily_channel_id = 1343804854056779869

scheduler = AsyncIOScheduler()

map_users = {
        "Manoj": 1169217682307043508,
        "Prashanth": 1169252470996869121,
        "Sandesh": 1185194615125577842,
        "Vivek": 1274011740761489440,
        "Akshitha": 1098204173922742305,
        "Adi": 1171425439076581379,
        "Pavithra": 1164823101524152380,
        "Saranya": 1168908845398118450,
        "Sharon": 1095989346022207508
    }

async def send_daily_reminders():
    await bot.wait_until_ready()
    channel = bot.get_channel(daily_channel_id)
    if channel:
        await channel.send("Reminder: Kindly update your everyday tasks by 10 pm!")

        # event = {
        #     'summary': 'Daily Task Reminder',
        #     'description': 'Update your daily tasks by 10 PM!',
        #     'start': {'dateTime': datetime.datetime.now().replace(hour=9, minute=0, second=0).isoformat(), 'timeZone': 'IST'},
        #     'end': {'dateTime': datetime.datetime.now().replace(hour=22, minute=0, second=0).isoformat(), 'timeZone': 'IST'},
        # }
        # calendar_service.events().insert(calendarId='primary', body=event).execute()


def send_tasks_to_db(user_id, tasks):
    for task in tasks:
        task_data = {
            "user_id": user_id,
            "date_today": date_today,
            "task_name": task['taskName'],
            "priority": task['priority'],
            "description": task['description'],
            "dependencies": task["dependencies"],
            "estimated_time": f"{task['estimatedTime']['value']} {task['estimatedTime']['unit']}",
            "completed": False
        }
        user_tasks_collection.insert_one(task_data)


def send_tasks_to_discord(user_id):
    webhook_url = f"{os.getenv('WEBHOOK_DAILY')}?wait=true"
    user_tasks = list(user_tasks_collection.find(
            {"user_id": user_id, "date_today": date_today}
        ))
    completed_count = sum(task.get("completed", False) for task in user_tasks)
    total_tasks = len(user_tasks)
    completion_percentage = int((completed_count / total_tasks) * 100) if total_tasks > 0 else 0

    embeds = []
    fields = []

    for i, task in enumerate(user_tasks, 0):
        checkmark = "✅" if task.get("completed", False) else ""
        priority_icon = ""
        if task.get("priority") == "High":
            priority_icon = "🟥"
        elif task.get("priority") == "Medium":
            priority_icon = "🟧"
        else:
            priority_icon = "🟩"

        fields.append({
                "name": f"{priority_icon} **Task {i+1}: {task['task_name']}** {checkmark}",
                "value": 
                    f"""📖 **Description:**\n{task['description']}
                        **\nDependencies:**\n<@{map_users[task['dependencies']] if task['dependencies'] != 'None' else 'None'}>\n
                        \n⏳ **Estimated Time:** {task['estimated_time']}\n
                        ────────────""",
            })
        
    embeds.append(
            {
                "title": f"📅 Tasks for {date_today}",
                "description": f"📝 **Tasks added by <@{user_id}>**\n\n",
                "inline": False,
                "fields": fields,
                "color": 0x0059FF,
                # "footer": f"Completion: {completion_percentage}% ✅"
            }
        )


    payload = {
        "embeds": embeds
    }

    response = requests.post(webhook_url, json=payload)

    if response.status_code == 200:
        message_data = response.json()  
        message_id = message_data.get("id")
        print("Message ID:", message_id)

        message_details = {
            "user_id": user_id, 
            "date_today": date_today, 
            "task_messages": message_id
        }
        msg = daily_task_messages_collection.insert_one(message_details)
        return msg.inserted_id

    else:
        print("Failed to send message:", response.text)

async def delete_old_msgs(user_id, latest_message_id):
    old_messages = list(
        daily_task_messages_collection.find(
            {"user_id": user_id, "date_today": date_today, "_id": {"$ne": latest_message_id}}
        )
    )

    # Delete old messages from Discord and the database
    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(webhook_url, session=session)

        for msg in old_messages:
            old_message_id = msg["task_messages"]

            try:
                # Fetch and delete the old message
                await webhook.delete_message(old_message_id)
                print(f"Deleted old message: {old_message_id}")
            except discord.NotFound:
                print(f"Message {old_message_id} not found — possibly deleted already.")
            except discord.Forbidden:
                print("Webhook lacks permission to delete the message.")
            except Exception as e:
                print(f"Error deleting message {old_message_id}: {e}")

    # Clean up the old messages from the database
    daily_task_messages_collection.delete_many(
        {"user_id": user_id, "date_today": date_today, "_id": {"$ne": latest_message_id}}
    )



class CompletionSelect(discord.ui.Select):
    def __init__(self, user_id, options):
        super().__init__(placeholder="Select tasks to mark as complete", min_values=1, max_values=len(options), options=options)
        self.user_id = user_id
        self.task_messages = list(daily_task_messages_collection.find({
            "user_id": self.user_id,
            "date_today": date_today
        }))

    async def callback(self, interaction: discord.Interaction):
        selected_task_names = [re.search(": .+", label).group()[2:] for label in self.values]

        user_tasks_collection.update_many(
            {"user_id": self.user_id, "task_name": {"$in": selected_task_names}, "date_today": date_today},
            {"$set": {"completed": True}}
        )

        # Update the message
        message_id = self.task_messages[-1]["task_messages"]
        if message_id:
            async with aiohttp.ClientSession() as session:
                webhook = discord.Webhook.from_url(webhook_url, session=session) 

                try:
                    message = await webhook.fetch_message(message_id)

                    if message:
                        embed = message.embeds[0]
                        embed.clear_fields()

                        user_tasks = list(user_tasks_collection.find({"user_id": self.user_id, "date_today": date_today}))
                        completed_count = sum(task.get("completed", False) for task in user_tasks)
                        total_tasks = len(user_tasks)
                        completion_percentage = int((completed_count / total_tasks) * 100) if total_tasks > 0 else 0

                        for i, task in enumerate(user_tasks):
                            checkmark = "✅" if task.get("completed", False) else ""
                            priority_icon = ""
                            if task.get("priority") == "High":
                                priority_icon = "🟥"
                            elif task.get("priority") == "Medium":
                                priority_icon = "🟧"
                            else:
                                priority_icon = "🟩"


                            embed.add_field(
                                name=f"{priority_icon} **Task {i+1}: {task['task_name']}** {checkmark}",
                                value=f"📖 **Description:**\n{task['description']}\n"
                                    f"**Dependencies:**\n<@{map_users[task['dependencies']] if task['dependencies'] != 'None' else 'None'}>\n"
                                    f"\n⏳ **Estimated Time:** {task['estimated_time']}\n"
                                    f"────────────",
                                inline=False
                            )

                        embed.set_footer(text=f"Completion: {completion_percentage}% ✅")
                        await webhook.edit_message(
                            message_id=message_id,
                            embed=embed
                        )

                        await interaction.response.send_message("✅ Tasks marked as complete!", ephemeral=True)

                except discord.NotFound:
                    await interaction.response.send_message("Could not find the message to edit.", ephemeral=True)
                except discord.Forbidden:
                    await interaction.response.send_message("Webhook lacks permission to edit the message.", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)


class CompletionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

        user_tasks = list(user_tasks_collection.find({"user_id": user_id, "date_today": date_today}))
        print(user_tasks)

        options = [
            discord.SelectOption(label=f"Task {i+1}: {task['task_name']}", value=str(i)+f": {task['task_name']}")
            for i, task in enumerate(user_tasks)
            if not task.get("completed", False)
        ]

        if options:
            self.add_item(CompletionSelect(user_id, options))


@app.route('/submit', methods=['POST'])
def submit():
    data = request.get_json()

    if not data:
        return jsonify({"status": "error", "message": "Invalid or missing JSON data"}), 400

    user_id = data.get('user_id')
    task_count = data.get('task_count')
    tasks = data.get('tasks', [])

    if task_count is None or len(tasks) != task_count:
        return jsonify({"status": "error", "message": "Task count mismatch"}), 400

    # Save tasks to the database
    send_tasks_to_db(user_id, tasks)

    # Send tasks to Discord and get the new message ID
    message_id = send_tasks_to_discord(user_id)

    # Ensure old messages get cleaned up (force async call from sync Flask)
    bot.loop.create_task(delete_old_msgs(user_id, message_id))

    return jsonify({"status": "success", "message": "Tasks submitted successfully!"})



if __name__ == '__main__':

    # Serve the form page
    @app.route('/form')
    def form():
        user_id = request.args.get('user_id') 
        return render_template('daily.html', user_id=user_id)

    @bot.event
    async def on_ready():
        scheduler.add_job(send_daily_reminders, CronTrigger(day_of_week="0-6", hour="7", minute="30", second="0"))
        scheduler.add_job(send_daily_reminders, CronTrigger(day_of_week="0-6", hour="21", minute="00", second="0"))
        scheduler.start()

    @bot.tree.command(name="task_daily", description="Submit your daily tasks", guild=GUILD)
    async def task_daily(interaction: discord.Interaction):
        user_id = interaction.user.id
        # Redirect the user to the Flask server's form page
        form_url = f"https://musetasks.onrender.com/form?user_id={user_id}"
        await interaction.response.send_message(f"Please fill out your tasks here: {form_url}", ephemeral=True)

    @bot.tree.command(name="complete_task_daily", description="Mark completion of your daily tasks", guild=GUILD)
    async def complete_task_daily(interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        await interaction.response.send_message("🔍 Select tasks to mark as complete.", view=CompletionView(user_id), ephemeral=True)

    def get_event_time(minutes_from_now: int):
        return discord.utils.utcnow() + datetime.timedelta(minutes=minutes_from_now)
    
    @bot.tree.command(name="daily_scores",
                      description="Calculate daily score",
                      guild=GUILD)
    @app_commands.choices(name=[
        app_commands.Choice(name='Manoj', value=1),
        app_commands.Choice(name='Prashanth', value=2),
        app_commands.Choice(name='Saranya', value=3),
        app_commands.Choice(name='Sandesh', value=4),
        app_commands.Choice(name='Vivek', value=5),
        app_commands.Choice(name='Pavithra', value=6),
        app_commands.Choice(name='Adi', value=7),
        app_commands.Choice(name='Akshitha', value=8),
        app_commands.Choice(name='Sharon', value=9)
    ])
    async def weekly_score(interaction: discord.Interaction, name: app_commands.Choice[int]):
        channel = bot.get_channel(daily_channel_id)
        user_id = map_users[name.name]
        print(user_id)
        user_tasks = list(
            user_tasks_collection.find({
                "user_id": str(user_id),
                "date_today": date_today
            }))
        
        score = 0; total_score = 0
        for task in user_tasks:
            if task['priority'] == "High":
                weight = 3
                total_score += weight
            elif task['priority'] == "Medium":
                weight = 2
                total_score += weight
            elif task['priority'] == "Low":
                weight = 1
                total_score += weight

            completed = 0 if task['completed'] == False else 1
            score += weight * completed

        print("user tasks: ", user_tasks)

        score = score / total_score
        await channel.send(f"<@{map_users[name.name]}>'s daily score: {score * 10} / 10")
    
    @bot.tree.command(name="schedule_event", description="Schedules a new Discord event", guild=GUILD)
    @app_commands.describe(name="Event name", description="Event description", minutes_from_now="Minutes until the event starts")
    async def schedule_event(interaction: discord.Interaction, name: str, description: str, minutes_from_now: int):
        guild = interaction.guild
        start_time = get_event_time(minutes_from_now)

        # try:
        await guild.create_scheduled_event(
            name=name,
            description=description,
            start_time=start_time,
            entity_type=discord.EntityType.voice,
            privacy_level=discord.PrivacyLevel.guild_only,
            channel=guild.voice_channels[0] 
        )
        await interaction.response.send_message(f'Event "{name}" scheduled at {start_time} UTC')
        # except Exception as e:
        #     await interaction.response.send_message(f'Failed to create event: {e}', ephemeral=True)

    def run_flask():
        app.run(host="0.0.0.0", port=5000, use_reloader=False)

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()


    bot.run(TOKEN)
