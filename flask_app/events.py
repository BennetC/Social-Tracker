from datetime import datetime, UTC
from flask import request, redirect, url_for, render_template, flash

from flask_app import app, db
from flask_app.models import Event, Relationship


def validate_event_dates(start_date, end_date):
    """Validates that the start date is before the end date."""
    if start_date and end_date and start_date > end_date:
        raise ValueError("End date must be after start date.")
    return True


@app.route('/events')
def view_events():
    """Displays a dashboard of all upcoming and past events."""
    now = datetime.now(UTC)
    upcoming_events = Event.query.filter(Event.start_date >= now).order_by(Event.start_date.asc()).all()
    past_events = Event.query.filter(Event.start_date < now).order_by(Event.start_date.desc()).all()
    return render_template('events.html', upcoming_events=upcoming_events, past_events=past_events, now=now)


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
                end_date=end_date
            )
            participant_ids = request.form.getlist('participant_ids')
            if participant_ids:
                participants = Relationship.query.filter(Relationship.id.in_(participant_ids)).all()
                new_event.participants.extend(participants)

            db.session.add(new_event)
            db.session.commit()
            flash('Event added successfully!', 'success')
            return redirect(url_for('view_events'))
        except (ValueError, KeyError) as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')
    relationships = Relationship.query.order_by(Relationship.name).all()
    return render_template('add_event.html', relationships=relationships)


@app.route('/events/<int:event_id>')
def get_event(event_id):
    """Displays the detail page for a specific event."""
    event = Event.query.get_or_404(event_id)
    return render_template('event_detail.html', event=event)


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
            event.participants = []
            participant_ids = request.form.getlist('participant_ids')
            if participant_ids:
                participants = Relationship.query.filter(Relationship.id.in_(participant_ids)).all()
                event.participants.extend(participants)

            db.session.commit()
            flash('Event updated successfully!', 'success')
            return redirect(url_for('get_event', event_id=event.id))
        except (ValueError, KeyError) as e:
            db.session.rollback()
            flash(f'An error occurred: {e}', 'danger')
    relationships = Relationship.query.order_by(Relationship.name).all()
    participant_ids = {p.id for p in event.participants}
    return render_template('edit_event.html', event=event, relationships=relationships, participant_ids=participant_ids)


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