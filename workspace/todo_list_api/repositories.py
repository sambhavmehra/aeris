from typing import List
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import TodoItem
from config import Config


class TodoRepository:
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)

    def get_all_todo_items(self) -> List[TodoItem]:
        session = self.Session()
        try:
            return session.query(TodoItem).all()
        finally:
            session.close()

    def get_todo_item(self, id: int) -> TodoItem:
        session = self.Session()
        try:
            return session.query(TodoItem).filter_by(id=id).first()
        finally:
            session.close()

    def create_todo_item(self, title: str, description: str) -> TodoItem:
        session = self.Session()
        try:
            todo_item = TodoItem(title=title, description=description)
            session.add(todo_item)
            session.commit()
            return todo_item
        finally:
            session.close()

    def update_todo_item(self, id: int, title: str, description: str) -> TodoItem:
        session = self.Session()
        try:
            todo_item = session.query(TodoItem).filter_by(id=id).first()
            if todo_item:
                todo_item.title = title
                todo_item.description = description
                session.commit()
            return todo_item
        finally:
            session.close()

    def delete_todo_item(self, id: int) -> None:
        session = self.Session()
        try:
            todo_item = session.query(TodoItem).filter_by(id=id).first()
            if todo_item:
                session.delete(todo_item)
                session.commit()
        finally:
            session.close()
