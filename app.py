import os
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import pusher
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

# Pusher Configuration
pusher_client = pusher.Pusher(
    app_id=os.environ.get("1904573"),
    key=os.environ.get("d4db60f9f99c2c2b7f8c"),
    secret=os.environ.get("bcc85f0d3f4299526015"),
    cluster=os.environ.get("mt1"),
    ssl=True
)

# Database Connection
def get_db_connection():
    return psycopg2.connect(
        os.environ.get('DATABASE_URL', 'postgresql://localhost/realtime_gantt'),
        cursor_factory=RealDictCursor
    )

# Existing Adapter and ThirdPartyGanttLibrary classes remain the same as in rtg_app.py

app = Flask(__name__)
CORS(app)
gantt_chart = GanttChartAdapter()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks")
        tasks = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify({"data": tasks})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/tasks', methods=['POST'])
def create_task():
    task_data = request.json
    try:
        # Use Adapter to create task in third-party library
        task_id = gantt_chart.create_task(task_data)
        
        # Store in database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tasks (name, start_date, end_date, progress) 
            VALUES (%s, %s, %s, %s) RETURNING id
        """, (
            task_data['name'], 
            task_data['start_date'], 
            task_data['end_date'], 
            task_data.get('progress', 0)
        ))
        db_task_id = cur.fetchone()['id']
        conn.commit()
        cur.close()
        conn.close()
        
        # Trigger Pusher event
        pusher_client.trigger('tasks-channel', 'task-created', {
            'id': db_task_id,
            'name': task_data['name']
        })
        
        return jsonify({"id": db_task_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    task_data = request.json
    try:
        # Update in third-party library
        gantt_chart.update_task(task_id, task_data)
        
        # Update in database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE tasks 
            SET name = %s, start_date = %s, end_date = %s, progress = %s 
            WHERE id = %s
        """, (
            task_data['name'], 
            task_data['start_date'], 
            task_data['end_date'], 
            task_data.get('progress', 0),
            task_id
        ))
        conn.commit()
        cur.close()
        conn.close()
        
        # Trigger Pusher event
        pusher_client.trigger('tasks-channel', 'task-updated', {
            'id': task_id,
            'name': task_data['name']
        })
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    try:
        # Delete from database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
        conn.commit()
        cur.close()
        conn.close()
        
        # Trigger Pusher event
        pusher_client.trigger('tasks-channel', 'task-deleted', {
            'id': task_id
        })
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)