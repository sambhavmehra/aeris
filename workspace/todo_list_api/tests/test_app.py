import unittest
from app import create_app, db
from models import TodoItem
from schemas import TodoItemSchema
import json

class TestApp(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.appctx = self.app.app_context()
        self.appctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.appctx.pop()

    def test_create_todo_item(self):
        with self.app.test_client() as client:
            todo_item = {'title': 'Test Todo Item', 'description': 'This is a test todo item'}
            response = client.post('/todos', data=json.dumps(todo_item), content_type='application/json')
            self.assertEqual(response.status_code, 201)

    def test_get_all_todo_items(self):
        with self.app.test_client() as client:
            todo_item = {'title': 'Test Todo Item', 'description': 'This is a test todo item'}
            client.post('/todos', data=json.dumps(todo_item), content_type='application/json')
            response = client.get('/todos')
            self.assertEqual(response.status_code, 200)

    def test_get_todo_item_by_id(self):
        with self.app.test_client() as client:
            todo_item = {'title': 'Test Todo Item', 'description': 'This is a test todo item'}
            client.post('/todos', data=json.dumps(todo_item), content_type='application/json')
            response = client.get('/todos/1')
            self.assertEqual(response.status_code, 200)

    def test_update_todo_item(self):
        with self.app.test_client() as client:
            todo_item = {'title': 'Test Todo Item', 'description': 'This is a test todo item'}
            client.post('/todos', data=json.dumps(todo_item), content_type='application/json')
            updated_todo_item = {'title': 'Updated Test Todo Item', 'description': 'This is an updated test todo item'}
            response = client.put('/todos/1', data=json.dumps(updated_todo_item), content_type='application/json')
            self.assertEqual(response.status_code, 200)

    def test_delete_todo_item(self):
        with self.app.test_client() as client:
            todo_item = {'title': 'Test Todo Item', 'description': 'This is a test todo item'}
            client.post('/todos', data=json.dumps(todo_item), content_type='application/json')
            response = client.delete('/todos/1')
            self.assertEqual(response.status_code, 204)

if __name__ == '__main__':
    unittest.main()