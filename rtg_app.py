import os
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import pusher
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime


# Configuración de logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Configuración segura de variables de entorno
def get_env_variable(var_name, default=None):
    value = os.getenv(var_name, default)
    if value is None:
        logger.error(f"CRITICAL: Environment variable {var_name} not set!")
    return value

# Pusher Configuration
pusher_client = pusher.Pusher(
    app_id=os.environ.get("1904573"),
    key=os.environ.get("d4db60f9f99c2c2b7f8c"),
    secret=os.environ.get("bcc85f0d3f4299526015"),
    cluster=os.environ.get("mt1"),
    ssl=True
)


    # Conexión a base de datos
    def get_db_connection():
        db_url = get_env_variable('DATABASE_URL')
        if not db_url:
            logger.error("DATABASE_URL not configured!")
            raise ValueError("No database URL provided")
        
        try:
            conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
            return conn
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise

except Exception as e:
    logger.error(f"Initialization error: {e}")

# Clase Adapter (copiada desde tu implementación original)
class ThirdPartyGanttLibrary:
    def __init__(self):
        self.tasks = []
        self.task_id_counter = 0
    
    def add_gantt_element(self, element_type: str, data: dict):
        self.task_id_counter += 1
        task = {
            "id": self.task_id_counter,
            "text": data["name"],
            "start_date": data["start"],
            "end_date": data["end"],
            "progress": data["progress"],
            "open": True
        }
        self.tasks.append(task)
        return self.task_id_counter
    
    def modify_element(self, element_id: int, new_data: dict):
        for task in self.tasks:
            if task["id"] == element_id:
                task.update({
                    "text": new_data["name"],
                    "start_date": new_data["start"],
                    "end_date": new_data["end"],
                    "progress": new_data["progress"]
                })
                break
    
    def get_element_data(self, element_id: int):
        for task in self.tasks:
            if task["id"] == element_id:
                return task
        return None
    
    def get_all_elements(self):
        return self.tasks

class GanttChartAdapter:
    def __init__(self):
        self.third_party_chart = ThirdPartyGanttLibrary()
    
    def create_task(self, task_data: dict):
        adapted_data = {
            "name": task_data.get("name"),
            "start": task_data.get("start_date"),
            "end": task_data.get("end_date"),
            "progress": float(task_data.get("progress", 0))
        }
        return self.third_party_chart.add_gantt_element("task", adapted_data)
    
    def update_task(self, task_id: int, task_data: dict):
        adapted_data = {
            "name": task_data.get("name"),
            "start": task_data.get("start_date"),
            "end": task_data.get("end_date"),
            "progress": float(task_data.get("progress", 0))
        }
        self.third_party_chart.modify_element(task_id, adapted_data)
    
    def get_task_timeline(self, task_id: int):
        return self.third_party_chart.get_element_data(task_id)
    
    def get_all_tasks(self):
        return self.third_party_chart.get_all_elements()

# Inicializar Flask
app = Flask(__name__)
CORS(app)
gantt_chart = GanttChartAdapter()

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


# Ruta de prueba para verificar funcionamiento básico
@app.route('/health')
def health_check():
    return jsonify({"status": "healthy"}), 200

# [Mantén tus rutas existentes]

@app.errorhandler(Exception)
def handle_error(e):
    logger.error(f"Unhandled exception: {e}")
    return jsonify(error=str(e)), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))