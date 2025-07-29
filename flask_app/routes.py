from datetime import datetime, UTC, timedelta

from flask import jsonify, request, redirect, url_for, render_template, current_app, flash
from sqlalchemy import case
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError

from flask_app import app, db
from flask_app.models import (
    Relationship, SocialMedia, Tag, Platform, ConnectionType,
    RelationshipConnectionType, RelationshipTag, InteractionHistory, Event
)


def _update_next_contact_date(relationship: Relationship):
    """
    Automatically calculates the next contact due date based on the relationship's
    follow-up frequency.
    """
    if not relationship.follow_up_frequency:
        return

    frequency_map = {
        'daily': timedelta(days=1),
        'weekly': timedelta(weeks=1),
        'bi-weekly': timedelta(weeks=2),
        'monthly': timedelta(days=30),
        'quarterly': timedelta(days=90)
    }

    delta = frequency_map.get(relationship.follow_up_frequency)
    if delta:
        relationship.next_contact_due = datetime.now(UTC) + delta


@app.route('/')
def index():
    """Main dashboard showing all relationships, with eager loading for efficiency."""
    priority_ordering = case(
        {
            'Very High': 5,
            'High': 4,
            'Medium': 3,
            'Low': 2,
            'Very Low': 1
        },
        value=Relationship.priority,
        else_=0
    ).desc()

    relationships = Relationship.query.options(
        joinedload(Relationship.connection_type_associations).joinedload(RelationshipConnectionType.connection_type),
        joinedload(Relationship.tag_associations).joinedload(RelationshipTag.tag),
        joinedload(Relationship.social_media).joinedload(SocialMedia.platform)
    ).order_by(
        Relationship.next_contact_due.asc().nullslast(),
        priority_ordering
    ).all()

    return render_template('dashboard.html', relationships=relationships, now=datetime.now(UTC))


@app.cli.command("seed")
def seed_all():
    """Seeds the database with initial platforms and connection types from config."""
    platform_rules = current_app.config.get('PLATFORM_CONFIG', {})
    print("Seeding platforms...")
    for name, rules in platform_rules.items():
        platform = Platform.query.filter_by(name=name).first()
        if not platform:
            platform = Platform(
                name=name,
                requires_handle=rules.get('requires_handle', True),
                requires_link=rules.get('requires_link', True)
            )
            db.session.add(platform)
            print(f"  Added platform: {name}")
        else:
            platform.requires_handle = rules.get('requires_handle', True)
            platform.requires_link = rules.get('requires_link', True)
    initial_types = current_app.config.get('CONNECTION_TYPES', [])
    print("\nSeeding connection types...")
    for type_name in initial_types:
        if not ConnectionType.query.filter_by(name=type_name).first():
            db.session.add(ConnectionType(name=type_name))
            print(f"  Added connection type: {type_name}")

    db.session.commit()
    print("\nDatabase seeding complete.")


@app.route('/add-relationship')
def add_relationship_form():
    """Show the added relationship form and pass dynamic data."""
    platforms = Platform.query.order_by(Platform.name).all()
    platforms_data = [{"name": p.name, "requires_handle": p.requires_handle, "requires_link": p.requires_link} for p in
                      platforms]
    connection_types = ConnectionType.query.order_by(ConnectionType.name).all()

    return render_template(
        'add_relationship.html',
        platforms_data=platforms_data,
        connection_types=connection_types
    )


@app.route('/relationships', methods=['POST'])
def create_relationship():
    """Create a new relationship with multiple, prioritized connections and tags."""
    try:
        data = request.form

        if not data.get('name'): raise ValueError("Full Name is a required field.")
        selected_ctype_ids = request.form.getlist('connection_type_ids')
        if not selected_ctype_ids: raise ValueError("You must select at least one Connection Type.")

        relationship = Relationship(
            name=data.get('name'),
            goal=data.get('goal'),
            execution_strategy=data.get('execution_strategy'),
            priority=data.get('priority', 'Medium'),
            interaction_level=data.get('interaction_level', 'Not Contacted'),
            notes=data.get('notes'),
            next_contact_due=datetime.strptime(data.get('next_contact_due'), '%Y-%m-%d').replace(
                tzinfo=UTC) if data.get('next_contact_due') else None,
            follow_up_frequency=data.get('follow_up_frequency') or None,
            next_follow_up_topic=data.get('next_follow_up_topic')
        )
        db.session.add(relationship)
        db.session.flush()

        primary_ctype_id = data.get('primary_connection_type')
        if len(selected_ctype_ids) == 1: primary_ctype_id = selected_ctype_ids[0]
        for ctype_id in selected_ctype_ids:
            db.session.add(RelationshipConnectionType(
                relationship_id=relationship.id,
                connection_type_id=int(ctype_id),
                is_primary=(str(ctype_id) == str(primary_ctype_id))
            ))

        tag_names_str = data.get('tags', '')
        primary_tag_name = data.get('primary_tag_name', '').strip().lower()
        all_tag_names = {name.strip().lower() for name in tag_names_str.split(',') if name.strip()}
        if primary_tag_name: all_tag_names.add(primary_tag_name)
        if len(all_tag_names) == 1 and not primary_tag_name: primary_tag_name = list(all_tag_names)[0]

        for tag_name in all_tag_names:
            tag = Tag.query.filter_by(name=tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                db.session.add(tag)
                db.session.flush()
            db.session.add(RelationshipTag(
                relationship_id=relationship.id,
                tag_id=tag.id,
                is_primary=(tag.name == primary_tag_name)
            ))

        platforms = data.getlist('platform[]')
        handles = data.getlist('handle[]')
        links = data.getlist('profile_link[]')
        primary_flags = data.getlist('is_primary')
        custom_names = iter(data.getlist('custom_platform_name[]'))
        custom_rules = iter(data.getlist('custom_platform_rule[]'))
        handle_idx, link_idx = 0, 0

        for i, platform_name in enumerate(platforms):
            if not platform_name: continue
            current_handle, current_link = '', ''
            platform = Platform.query.filter_by(name=platform_name).first()

            if platform_name == 'Other':
                try:
                    new_platform_name = next(custom_names)
                    if new_platform_name:
                        platform = Platform.query.filter_by(name=new_platform_name).first()
                        if not platform:
                            rule_key = next(custom_rules)
                            platform = Platform(
                                name=new_platform_name,
                                requires_handle=(rule_key in ['both', 'handle_only']),
                                requires_link=(rule_key in ['both', 'link_only'])
                            )
                            db.session.add(platform)
                            db.session.flush()
                except StopIteration:
                    continue

            if not platform: continue

            if platform.requires_handle:
                if handle_idx < len(handles):
                    current_handle = handles[handle_idx]
                    handle_idx += 1
            if platform.requires_link:
                if link_idx < len(links):
                    current_link = links[link_idx]
                    link_idx += 1
            if not current_link and current_handle:
                base_url = current_app.config.get('PLATFORM_BASE_URLS', {}).get(platform.name)
                if base_url:
                    if platform.name == 'Email':
                        current_link = f"{base_url}{current_handle}"
                    else:
                        current_link = f"{base_url}{current_handle.lstrip('@')}"

            is_primary = str(i + 1) in primary_flags
            db.session.add(SocialMedia(
                relationship_id=relationship.id,
                platform_id=platform.id,
                handle=current_handle or None,
                profile_link=current_link or None,
                is_primary=is_primary
            ))

        db.session.commit()
        recalculate_all_ratings_logic()
        flash("Relationship added successfully!", "success")
        return redirect(url_for('index'))

    except (ValueError, KeyError, IndexError) as e:
        db.session.rollback()
        print(f"ERROR in create_relationship: {type(e).__name__} - {e}")
        flash(f"An error occurred: {e}", "danger")
        return redirect(url_for('add_relationship_form'))


@app.cli.command("recalculate-all-ratings")
def recalculate_all_ratings_command():
    """CLI wrapper for the recalculation logic."""
    recalculate_all_ratings_logic()


def recalculate_all_ratings_logic():
    """Calculates and updates priority scores for Platforms, Connection Types, and Tags."""
    print("Starting rating recalculation for all items...")
    priority_scores = current_app.config.get('PRIORITY_SCORES', {})
    primary_multiplier = current_app.config.get('PRIMARY_ITEM_MULTIPLIER', 1.5)
    Platform.query.update({Platform.priority_rating: 0})
    ConnectionType.query.update({ConnectionType.priority_rating: 0})
    Tag.query.update({Tag.priority_rating: 0})
    platform_scores, ctype_scores, tag_scores = {}, {}, {}
    relationships = Relationship.query.options(
        joinedload(Relationship.social_media),
        joinedload(Relationship.connection_type_associations),
        joinedload(Relationship.tag_associations)
    ).all()
    for rel in relationships:
        base_score = priority_scores.get(rel.priority, 0)
        if base_score == 0: continue
        for social in rel.social_media:
            score = base_score * primary_multiplier if social.is_primary else base_score
            platform_scores[social.platform_id] = platform_scores.get(social.platform_id, 0) + score
        for assoc in rel.connection_type_associations:
            score = base_score * primary_multiplier if assoc.is_primary else base_score
            ctype_scores[assoc.connection_type_id] = ctype_scores.get(assoc.connection_type_id, 0) + score
        for assoc in rel.tag_associations:
            score = base_score * primary_multiplier if assoc.is_primary else base_score
            tag_scores[assoc.tag_id] = tag_scores.get(assoc.tag_id, 0) + score
    for model, scores in [(Platform, platform_scores), (ConnectionType, ctype_scores), (Tag, tag_scores)]:
        if scores:
            for item_id, score in scores.items():
                db.session.query(model).filter_by(id=item_id).update({'priority_rating': score})
    db.session.commit()
    print("Recalculation complete.")


@app.route('/connection-types', methods=['GET', 'POST'])
def manage_connection_types():
    """Page to view and add new Connection Types."""
    if request.method == 'POST':
        new_type_name = request.form.get('name', '').strip()
        if new_type_name:
            try:
                db.session.add(ConnectionType(name=new_type_name))
                db.session.commit()
                flash(f"Successfully added '{new_type_name}'.", "success")
            except IntegrityError:
                db.session.rollback()
                flash(f"Error: '{new_type_name}' already exists.", "danger")
        else:
            flash("Error: Name cannot be empty.", "danger")
        return redirect(url_for('manage_connection_types'))
    all_types = ConnectionType.query.order_by(ConnectionType.name).all()
    return render_template('manage_connection_types.html', connection_types=all_types)


@app.route('/relationships/<uuid:relationship_id>')
def get_relationship(relationship_id):
    """Get relationship details"""
    relationship = Relationship.query.options(
        joinedload(Relationship.interactions)
    ).get_or_404(relationship_id)
    return render_template('relationship_detail.html', relationship=relationship)


@app.route('/relationships/<uuid:relationship_id>/add_interaction', methods=['POST'])
def add_interaction(relationship_id):
    """Adds a new interaction to a relationship's history."""
    relationship = Relationship.query.get_or_404(relationship_id)
    try:
        data = request.form
        if not data.get('title'):
            raise ValueError("Title is required for an interaction.")

        interaction = InteractionHistory(
            relationship_id=relationship.id,
            title=data.get('title'),
            type=data.get('type'),
            platform=data.get('platform'),
            details=data.get('details')
        )
        db.session.add(interaction)
        relationship.last_contacted = datetime.now(UTC)
        _update_next_contact_date(relationship)
        relationship.next_follow_up_topic = None

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


@app.route('/platforms')
def view_platforms():
    """Displays a list of all platforms and their calculated priority ratings."""
    platforms = Platform.query.order_by(Platform.priority_rating.desc()).all()
    return render_template('platforms.html', platforms=platforms)


@app.route('/api/tags/recent')
def get_recent_tags():
    tags = Tag.query.order_by(Tag.priority_rating.desc()).limit(15).all()
    return jsonify([{'name': tag.name} for tag in tags])


@app.route('/api/tags/popular')
def get_popular_tags():
    tags = Tag.query.order_by(Tag.priority_rating.desc()).limit(15).all()
    return jsonify([{'name': tag.name} for tag in tags])


@app.route('/relationships/<uuid:relationship_id>/edit', methods=['GET', 'POST'])
def edit_relationship(relationship_id):
    """Handles editing an existing relationship."""
    relationship = Relationship.query.options(
        joinedload(Relationship.connection_type_associations).joinedload(RelationshipConnectionType.connection_type),
        joinedload(Relationship.tag_associations).joinedload(RelationshipTag.tag),
        joinedload(Relationship.social_media).joinedload(SocialMedia.platform)
    ).get_or_404(relationship_id)

    if request.method == 'POST':
        try:
            data = request.form
            if not data.get('name'): raise ValueError("Full Name is a required field.")
            relationship.name = data.get('name')
            relationship.goal = data.get('goal')
            relationship.execution_strategy = data.get('execution_strategy')
            relationship.priority = data.get('priority', 'Medium')
            relationship.interaction_level = data.get('interaction_level', 'Not Contacted')
            relationship.notes = data.get('notes')
            relationship.next_contact_due = datetime.strptime(data.get('next_contact_due'), '%Y-%m-%d').replace(
                tzinfo=UTC) if data.get('next_contact_due') else None
            relationship.follow_up_frequency = data.get('follow_up_frequency') or None
            relationship.next_follow_up_topic = data.get('next_follow_up_topic')
            RelationshipConnectionType.query.filter_by(relationship_id=relationship.id).delete()
            selected_ctype_ids = request.form.getlist('connection_type_ids')
            if not selected_ctype_ids: raise ValueError("You must select at least one Connection Type.")
            primary_ctype_id = data.get('primary_connection_type')
            if len(selected_ctype_ids) == 1: primary_ctype_id = selected_ctype_ids[0]
            for ctype_id in selected_ctype_ids:
                db.session.add(RelationshipConnectionType(
                    relationship_id=relationship.id,
                    connection_type_id=int(ctype_id),
                    is_primary=(str(ctype_id) == str(primary_ctype_id))
                ))
            RelationshipTag.query.filter_by(relationship_id=relationship.id).delete()
            tag_names_str = data.get('tags', '')
            primary_tag_name = data.get('primary_tag_name', '').strip().lower()
            all_tag_names = {name.strip().lower() for name in tag_names_str.split(',') if name.strip()}
            if primary_tag_name: all_tag_names.add(primary_tag_name)
            if len(all_tag_names) == 1 and not primary_tag_name: primary_tag_name = list(all_tag_names)[0]

            for tag_name in all_tag_names:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.session.add(tag)
                    db.session.flush()
                db.session.add(RelationshipTag(
                    relationship_id=relationship.id,
                    tag_id=tag.id,
                    is_primary=(tag.name == primary_tag_name)
                ))
            SocialMedia.query.filter_by(relationship_id=relationship.id).delete()
            platforms = data.getlist('platform[]')
            handles = data.getlist('handle[]')
            links = data.getlist('profile_link[]')
            primary_flags = data.getlist('is_primary')
            custom_names = iter(data.getlist('custom_platform_name[]'))
            custom_rules = iter(data.getlist('custom_platform_rule[]'))
            handle_idx, link_idx = 0, 0

            for i, platform_name in enumerate(platforms):
                if not platform_name: continue
                current_handle, current_link = '', ''
                platform = Platform.query.filter_by(name=platform_name).first()

                if platform_name == 'Other':
                    try:
                        new_platform_name = next(custom_names)
                        if new_platform_name:
                            platform = Platform.query.filter_by(name=new_platform_name).first()
                            if not platform:
                                rule_key = next(custom_rules)
                                platform = Platform(
                                    name=new_platform_name,
                                    requires_handle=(rule_key in ['both', 'handle_only']),
                                    requires_link=(rule_key in ['both', 'link_only'])
                                )
                                db.session.add(platform)
                                db.session.flush()
                    except StopIteration:
                        continue

                if not platform: continue

                if platform.requires_handle:
                    if handle_idx < len(handles): current_handle = handles[handle_idx]; handle_idx += 1
                if platform.requires_link:
                    if link_idx < len(links): current_link = links[link_idx]; link_idx += 1

                is_primary = str(i + 1) in primary_flags
                db.session.add(SocialMedia(
                    relationship_id=relationship.id,
                    platform_id=platform.id,
                    handle=current_handle or None,
                    profile_link=current_link or None,
                    is_primary=is_primary
                ))

            db.session.commit()
            recalculate_all_ratings_logic()
            flash('Relationship updated successfully!', 'success')
            return redirect(url_for('get_relationship', relationship_id=relationship.id))

        except (ValueError, KeyError, IndexError, AttributeError) as e:
            db.session.rollback()
            print(f"ERROR in edit_relationship: {type(e).__name__} - {e}")
            flash(f"An error occurred: {e}", "danger")
            return redirect(url_for('edit_relationship', relationship_id=relationship_id))
    platforms = Platform.query.order_by(Platform.name).all()
    platforms_data = [{"name": p.name, "requires_handle": p.requires_handle, "requires_link": p.requires_link} for p in
                      platforms]
    connection_types = ConnectionType.query.order_by(ConnectionType.name).all()

    social_media_data = [{"platform": {"name": sm.platform.name}, "handle": sm.handle, "profile_link": sm.profile_link,
                          "is_primary": sm.is_primary} for sm in relationship.social_media]
    tag_associations_data = [{"tag": {"name": assoc.tag.name}, "is_primary": assoc.is_primary} for assoc in
                             relationship.tag_associations]

    return render_template(
        'edit_relationship.html',
        relationship=relationship,
        platforms_data=platforms_data,
        connection_types=connection_types,
        social_media_data=social_media_data,
        tag_associations_data=tag_associations_data
    )


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

            new_event = Event(
                title=data.get('title'),
                details=data.get('details'),
                priority=data.get('priority', 'Medium'),
                start_date=datetime.strptime(data.get('start_date'), '%Y-%m-%d').replace(tzinfo=UTC) if data.get(
                    'start_date') else None,
                end_date=datetime.strptime(data.get('end_date'), '%Y-%m-%d').replace(tzinfo=UTC) if data.get(
                    'end_date') else None
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
            event.participants.clear()
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