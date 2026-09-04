from app import create_app
from extensions import db
from foundations.models import User

app = create_app()
with app.app_context():
    users = User.query.all()
    for u in users:
        print(f"ID: {u.id}, Email: {u.email}, Role: {u.role}, Full Name: {u.full_name}")
