# models.py
# This file defines the database structure for the application using SQLAlchemy.
# It acts as the blueprint for our tables.

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize the database extension. This object will be linked to the Flask app.
db = SQLAlchemy() 

class User(UserMixin, db.Model):
    """
    Represents a user in the database.
    - UserMixin adds required methods for Flask-Login to work (e.g., is_authenticated).
    - db.Model is the base class for all models in Flask-SQLAlchemy.
    """
    # Define the table columns
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    encrypted_threads_token = db.Column(db.String(512), nullable=True)

    def set_password(self, password):
        """
        Creates a secure hash from a plain-text password and stores it.
        The original password is never saved.
        """
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """
        Checks if a submitted plain-text password matches the stored hash.
        Returns True if it matches, False otherwise.
        """
        return check_password_hash(self.password_hash, password)