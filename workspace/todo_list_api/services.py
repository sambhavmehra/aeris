from typing import List
from repositories import TodoRepository
from models import Todo
from schemas import TodoSchema


class TodoService:
    def __init__(self, repository: TodoRepository, schema: TodoSchema):
        self.repository = repository
        self.schema = schema

    def get_all_todos(self) -> List[Todo]:
        """
        Retrieves all Todo items from the database.

        Returns:
            List[Todo]: A list of Todo items.
        """
        todos = self.repository.get_all_todos()
        return todos

    def get_todo_by_id(self, todo_id: int) -> Todo:
        """
        Retrieves a Todo item by its ID from the database.

        Args:
            todo_id (int): The ID of the Todo item.

        Returns:
            Todo: The Todo item with the specified ID.
        """
        todo = self.repository.get_todo_by_id(todo_id)
        if todo is None:
            raise ValueError("Todo item not found")
        return todo

    def create_todo(self, todo_data: dict) -> Todo:
        """
        Creates a new Todo item in the database.

        Args:
            todo_data (dict): The data for the new Todo item.

        Returns:
            Todo: The newly created Todo item.
        """
        todo = self.schema.load(todo_data)
        new_todo = self.repository.create_todo(todo)
        return new_todo

    def update_todo(self, todo_id: int, todo_data: dict) -> Todo:
        """
        Updates a Todo item in the database.

        Args:
            todo_id (int): The ID of the Todo item to update.
            todo_data (dict): The updated data for the Todo item.

        Returns:
            Todo: The updated Todo item.
        """
        todo = self.get_todo_by_id(todo_id)
        updated_todo = self.schema.load(todo_data)
        updated_todo.id = todo_id
        self.repository.update_todo(updated_todo)
        return updated_todo

    def delete_todo(self, todo_id: int) -> None:
        """
        Deletes a Todo item from the database.

        Args:
            todo_id (int): The ID of the Todo item to delete.
        """
        self.repository.delete_todo(todo_id)
