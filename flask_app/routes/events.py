from datetime import datetime, UTC
from flask import request, redirect, url_for, render_template, flash, current_app

from flask_app import app, db
from flask_app.models.models import Event, Relationship, Tag, ConnectionType
from flask_app.routes.main import _calculate_single_event_importance


def validate_event_dates(start_date, end_date):
    """Validates that the start date is before the end date."""
    if start_date and end_date and start_date > end_date:
        raise ValueError("End date must be after start date.")
    return True


@app.route('/events')
def view_events():
    """Displays a dashboard of all upcoming, past, and potential events."""
    now = datetime.now(UTC)
    upcoming_events = Event.query.filter(
        Event.is_potential == False, Event.start_date >= now
    ).order_by(Event.start_date.asc()).all()
    potential_events = Event.query.filter(Event.is_potential == True).order_by(Event.start_date.asc()).all()
    past_events = Event.query.filter(
        Event.is_potential == False, Event.start_date < now
    ).order_by(Event.start_date.desc()).all()
    return render_template(
        'events.html',
        upcoming_events=upcoming_events,
        potential_events=potential_events,
        past_events=past_events,
        now=now
    )


@app.route('/events/add', methods=['GET', 'POST'])
def add_event():
    """Handles creating a new event."""
    if request.method == 'POST':
        try:
            data = request.form
            if not data.get('title'):
                raise ValueError("Event Title is a required field.")

            start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').replace(tzinfo=UTC) if data.get(
                'start_date') else None
            end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').replace(tzinfo=UTC) if data.get(
                'end_date') else None
            validate_event_dates(start_date, end_date)

            new_event = Event(
                title=data.get('title'),
                details=data.get('details'),
                priority=data.get('priority', 'Medium'),
                start_date=start_date,
                end_date=end_date,
                is_potential=data.get('is_potential') == 'on',
                pros=data.get('pros'),
                cons=data.get('cons')
            )
            participant_ids = request.form.getlist('participant_ids')
            if participant_ids:
                participants = Relationship.query.filter(Relationship.id.in_(participant_ids)).all()
                new_event.participants.extend(participants)

            priority_scores = current_app.config.get('PRIORITY_SCORES', {})
            new_event.importance_score = _calculate_single_event_importance(new_event, priority_scores)

            db.session.add(new_event)
            db.session.commit()
            flash('Event added successfully!', 'success')
            return redirect(url_for('view_events'))
        except (ValueError, KeyError) as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')

    tags = Tag.query.order_by(Tag.name).all()
    connection_types = ConnectionType.query.order_by(ConnectionType.name).all()
    priorities = ['Very High', 'High', 'Medium', 'Low', 'Very Low']
    return render_template('add_event.html', tags=tags, connection_types=connection_types, priorities=priorities)


@app.route('/events/<int:event_id>')
def get_event(event_id):
    """Displays the detail page for a specific event."""
    event = Event.query.get_or_404(event_id)
    return render_template('event_detail.html', event=event, now=datetime.now(UTC))


@app.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
def edit_event(event_id):
    """Handles editing an existing event."""
    event = Event.query.get_or_404(event_id)

    if request.method == 'POST':
        try:
            data = request.form
            if not data.get('title'):
                raise ValueError("Event Title is a required field.")

            event.title = data.get('title')
            event.details = data.get('details')
            event.priority = data.get('priority')
            event.start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').replace(tzinfo=UTC) if data.get(
                'start_date') else None
            event.end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').replace(tzinfo=UTC) if data.get(
                'end_date') else None
            validate_event_dates(event.start_date, event.end_date)

            event.is_potential = data.get('is_potential') == 'on'
            event.pros = data.get('pros')
            event.cons = data.get('cons')

            now = datetime.now(UTC)
            is_past_event = (event.end_date and event.end_date < now) or \
                            (not event.end_date and event.start_date and event.start_date < now)
            if is_past_event:
                event.outcome = data.get('outcome')
                event.learnings = data.get('learnings')

            event.participants = []
            participant_ids = request.form.getlist('participant_ids')
            if participant_ids:
                participants = Relationship.query.filter(Relationship.id.in_(participant_ids)).all()
                event.participants.extend(participants)

            priority_scores = current_app.config.get('PRIORITY_SCORES', {})
            event.importance_score = _calculate_single_event_importance(event, priority_scores)

            db.session.commit()
            flash('Event updated successfully!', 'success')
            return redirect(url_for('get_event', event_id=event.id))
        except (ValueError, KeyError) as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')

    tags = Tag.query.order_by(Tag.name).all()
    connection_types = ConnectionType.query.order_by(ConnectionType.name).all()
    priorities = ['Very High', 'High', 'Medium', 'Low', 'Very Low']
    selected_participants_data = [{'id': str(p.id), 'name': p.name} for p in event.participants]

    return render_template(
        'edit_event.html',
        event=event,
        tags=tags,
        connection_types=connection_types,
        priorities=priorities,
        selected_participants_data=selected_participants_data,
        now=datetime.now(UTC)
    )


@app.route('/events/<int:event_id>/delete', methods=['POST'])
def delete_event(event_id):
    """Deletes an event."""
    event = Event.query.get_or_404(event_id)
    try:
        db.session.delete(event)
        db.session.commit()
        flash('Event deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting event: {e}', 'danger')

    return redirect(url_for('view_events'))