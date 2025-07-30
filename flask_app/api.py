from flask import jsonify
from flask_app import app
from flask_app.models import Tag


@app.route('/api/tags/recent')
def get_recent_tags():
    """Returns the 15 most recently used tags based on priority rating."""
    tags = Tag.query.order_by(Tag.priority_rating.desc()).limit(15).all()
    return jsonify([{'name': tag.name} for tag in tags])


@app.route('/api/tags/popular')
def get_popular_tags():
    """Returns the 15 most popular tags based on priority rating."""
    tags = Tag.query.order_by(Tag.priority_rating.desc()).limit(15).all()
    return jsonify([{'name': tag.name} for tag in tags])