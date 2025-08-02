from flask import jsonify, request, url_for
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from flask_app import app, db
from flask_app.models.models import Tag, Relationship, RelationshipTag, RelationshipConnectionType, event_participants, \
    Event


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


@app.route('/api/calendar-events')
def get_calendar_events():
    """
    Returns all events in a format that FullCalendar can consume.
    """
    events = Event.query.all()
    event_list = []
    for event in events:
        event_data = {
            'title': event.title,
            'start': event.start_date.isoformat() if event.start_date else None,
            'end': event.calendar_end_date.isoformat() if event.calendar_end_date else None,
            'url': url_for('get_event', event_id=event.id),
            'allDay': True  # Assume all-day events for now
        }
        if event.is_potential:
            event_data['className'] = 'event-potential'
            event_data['color'] = 'var(--color-warning-bg)'
            event_data['textColor'] = 'var(--color-warning-text)'
        else:
            event_data['color'] = 'var(--accent-primary)'
            event_data['textColor'] = 'var(--text-inverted)'

        event_list.append(event_data)

    return jsonify(event_list)