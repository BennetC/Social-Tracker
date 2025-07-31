from flask import jsonify, request
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from flask_app import app, db
from flask_app.models.models import Tag, Relationship, RelationshipTag, RelationshipConnectionType, event_participants


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


@app.route('/api/relationships/search')
def search_relationships():
    """
    Searches and filters relationships.
    If no filters are active, it returns the top 10 most frequent event attendees.
    """
    query = Relationship.query

    # Get query parameters from the request
    search_term = request.args.get('q')
    priority = request.args.get('priority')
    tag_id = request.args.get('tag_id')
    ctype_id = request.args.get('ctype_id')

    is_any_filter_active = any([search_term, priority, tag_id, ctype_id])

    if search_term:
        query = query.filter(Relationship.name.ilike(f'%{search_term}%'))
    if priority:
        query = query.filter(Relationship.priority == priority)
    if tag_id:
        query = query.join(RelationshipTag).filter(RelationshipTag.tag_id == tag_id)
    if ctype_id:
        query = query.join(RelationshipConnectionType).filter(RelationshipConnectionType.connection_type_id == ctype_id)

    if is_any_filter_active:
        relationships = query.order_by(Relationship.name).limit(50).all()
    else:
        # Default to showing the most frequent attendees
        top_attendees = db.session.query(
            Relationship,
            func.count(event_participants.c.event_id).label('event_count')
        ).outerjoin(event_participants).group_by(Relationship.id).order_by(
            func.count(event_participants.c.event_id).desc()
        ).limit(10).all()
        relationships = [rel for rel, count in top_attendees]

    return jsonify([{'id': str(rel.id), 'name': rel.name} for rel in relationships])