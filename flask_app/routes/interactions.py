from datetime import datetime, UTC
from flask import request, redirect, url_for, render_template, flash
from sqlalchemy.orm import joinedload

from flask_app import app, db
from flask_app.models.models import Relationship, InteractionHistory, FollowUp
from flask_app.routes.main import _create_next_automated_follow_up


@app.route('/relationships/<uuid:relationship_id>/add_interaction', methods=['POST'])
def add_interaction(relationship_id):
    """Adds a new interaction to a relationship's history and optionally completes a follow-up."""
    relationship = Relationship.query.get_or_404(relationship_id)
    try:
        data = request.form
        if not data.get('title'):
            raise ValueError("Title is required for an interaction.")

        # Create the interaction record
        interaction = InteractionHistory(
            relationship_id=relationship.id,
            title=data.get('title'),
            type=data.get('type'),
            platform=data.get('platform'),
            details=data.get('details')
        )
        db.session.add(interaction)

        # Update last contacted date
        relationship.last_contacted = datetime.now(UTC)

        # Check if a specific follow-up was completed with this interaction
        completed_follow_up_id = data.get('completed_follow_up_id')
        if completed_follow_up_id:
            follow_up = FollowUp.query.get(completed_follow_up_id)
            if follow_up and follow_up.relationship_id == relationship.id:
                follow_up.status = 'completed'
                follow_up.completed_at = datetime.now(UTC)
                # If a cadence is set, create the next follow-up
                _create_next_automated_follow_up(relationship)

        db.session.commit()
        flash("Interaction logged successfully.", "success")
    except (ValueError, KeyError) as e:
        db.session.rollback()
        flash(f"Error logging interaction: {e}", "danger")

    return redirect(url_for('get_relationship', relationship_id=relationship.id) + '#interaction-history')


@app.route('/interactions/<int:interaction_id>')
def get_interaction(interaction_id):
    """Displays the details of a single interaction."""
    interaction = InteractionHistory.query.options(
        joinedload(InteractionHistory.relationship)
    ).get_or_404(interaction_id)
    return render_template('interaction_detail.html', interaction=interaction)


@app.route('/interactions/<int:interaction_id>/edit', methods=['GET', 'POST'])
def edit_interaction(interaction_id):
    """Handles editing an existing interaction."""
    interaction = InteractionHistory.query.get_or_404(interaction_id)

    if request.method == 'POST':
        try:
            data = request.form
            if not data.get('title'):
                raise ValueError("Title cannot be empty.")

            interaction.title = data.get('title')
            interaction.details = data.get('details')
            interaction.type = data.get('type')
            interaction.platform = data.get('platform')

            db.session.commit()
            flash('Interaction updated successfully!', 'success')
            return redirect(url_for('get_interaction', interaction_id=interaction.id))
        except ValueError as e:
            db.session.rollback()
            flash(f"An error occurred: {e}", "danger")

    return render_template('edit_interaction.html', interaction=interaction)


@app.route('/interactions/<int:interaction_id>/delete', methods=['POST'])
def delete_interaction(interaction_id):
    """Deletes an interaction."""
    interaction = InteractionHistory.query.get_or_404(interaction_id)
    relationship_id = interaction.relationship_id
    try:
        db.session.delete(interaction)
        db.session.commit()
        flash('Interaction deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting interaction: {e}', 'danger')

    return redirect(url_for('get_relationship', relationship_id=relationship_id) + '#interaction-history')