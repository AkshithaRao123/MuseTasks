from flask import Flask, request, render_template, redirect, url_for, jsonify
import requests
import os
import datetime
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

MONGO_URI = os.getenv("MONGO_URI") 

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client.tasks_db 
user_tasks_collection = db.user_tasks 
user_tasks_weekly_collection = db.user_tasks_weekly

# Get today's date
date_today = datetime.datetime.now().strftime("%d-%m-%Y (%A)")

# Serve the form page
@app.route('/form')
def form():
    user_id = request.args.get('user_id') 
    return render_template('index.html', user_id=user_id)


def send_tasks_to_db(user_id, tasks):
    for task in tasks:
        task_data = {
            "user_id": user_id,
            "date": date_today,
            "task_name": task['taskName'],
            "priority": task['priority'],
            "description": task['description'],
            "estimated_time": f"{task['estimatedTime']['value']} {task['estimatedTime']['unit']}",
            "completed": False
        }
        user_tasks_collection.insert_one(task_data)



def send_tasks_to_discord(user_id, tasks):
    webhook_url = os.environ["WEBHOOK_URL"]

    embeds = []
    fields = []

    for i, task in enumerate(tasks, 0):
        fields.append({
                "name": f"📌 **Task {i+1}: {task['taskName']}**  |  🏷 **Priority:** {task['priority']}",
                "value": 
                    f"""📖 **Description:**\n{task['description']}\n
                        \n⏳ **Estimated Time:** {task['estimatedTime']['value']} {task['estimatedTime']['unit']}\n
                        ────────────""",
            })
        
    embeds.append(
            {
                "title": f"📅 Tasks for {date_today}",
                "description": f"📝 **Tasks added by <@{user_id}>**",
                "inline": False,
                "fields": fields,
                "color": 0x0059FF,
            }
        )

    payload = {
        "embeds": embeds
    }

    requests.post(webhook_url, json=payload)


@app.route('/submit', methods=['POST'])
def submit():
    # Get the JSON data sent from the frontend
    data = request.get_json()

    # Check if data is None (invalid JSON or missing Content-Type header)
    if not data:
        return jsonify({"status": "error", "message": "Invalid or missing JSON data"}), 400

    # Extract user_id, task_count, and tasks from the JSON payload
    user_id = data.get('user_id')
    task_count = data.get('task_count')
    tasks = data.get('tasks', [])

    # Validate that task_count matches the number of tasks
    if task_count is None or len(tasks) != task_count:
        return jsonify({"status": "error", "message": "Task count mismatch"}), 400

    send_tasks_to_db(user_id, tasks)
    send_tasks_to_discord(user_id, tasks)

    return jsonify({"status": "success", "message": "Tasks submitted successfully!"})


if __name__ == '__main__':
    app.run(debug=True)