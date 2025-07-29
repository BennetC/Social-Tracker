from flask_app import app

if __name__ == "__main__":

    # Create the database tables if they don't exist
    from flask_app import db
    with app.app_context():
        #db.drop_all()
        db.create_all()
        print("Database tables created successfully.")

    # Run the Flask application
    app.run(debug=True, port=5001)