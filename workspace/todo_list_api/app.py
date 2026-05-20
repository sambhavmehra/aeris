from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from config import Config
from models import TodoItem
from schemas import TodoItemSchema
from repositories import TodoItemRepository
from services import TodoItemService

app = Flask(__name__)
app.config.from_object(Config)

db = SQLAlchemy(app)
ma = Marshmallow(app)

repository = TodoItemRepository(db)
service = TodoItemService(repository)

@app.route('/todo', methods=['GET'])
def get_all_todo_items():
    try:
        todo_items = service.get_all_todo_items()
        return jsonify(todo_items), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/todo', methods=['POST'])
def create_todo_item():
    try:
        data = request.get_json()
        todo_item = service.create_todo_item(data)
        return jsonify(todo_item), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/todo/<int:todo_item_id>', methods=['GET'])
def get_todo_item(todo_item_id):
    try:
        todo_item = service.get_todo_item(todo_item_id)
        return jsonify(todo_item), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 404

@app.route('/todo/<int:todo_item_id>', methods=['PUT'])
def update_todo_item(todo_item_id):
    try:
        data = request.get_json()
        todo_item = service.update_todo_item(todo_item_id, data)
        return jsonify(todo_item), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/todo/<int:todo_item_id>', methods=['DELETE'])
def delete_todo_item(todo_item_id):
    try:
        service.delete_todo_item(todo_item_id)
        return jsonify({}), 204
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)