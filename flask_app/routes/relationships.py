from datetime import datetime, UTC
from flask import request, redirect, url_for, render_template, current_app, flash
from sqlalchemy.orm import joinedload

from flask_app import app, db
from flask_app.models.models import (
    Relationship, SocialMedia, Tag, Platform, ConnectionType,
    RelationshipConnectionType, RelationshipTag, FollowUp
)
from flask_app.routes.main import recalculate_all_ratings_logic, recalculate_all_event_importance_logic


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
            follow_up_frequency=data.get('follow_up_frequency') or None
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

        _process_social_media_data(relationship, data)

        db.session.commit()
        recalculate_all_ratings_logic()
        recalculate_all_event_importance_logic()
        flash("Relationship added successfully!", "success")
        return redirect(url_for('index'))

    except (ValueError, KeyError, IndexError) as e:
        db.session.rollback()
        print(f"ERROR in create_relationship: {type(e).__name__} - {e}")
        flash(f"An error occurred: {e}", "danger")
        return redirect(url_for('add_relationship_form'))


@app.route('/relationships/<uuid:relationship_id>')
def get_relationship(relationship_id):
    """Get relationship details"""
    relationship = Relationship.query.options(
        joinedload(Relationship.interactions),
        joinedload(Relationship.follow_ups)
    ).get_or_404(relationship_id)
    pending_follow_ups = sorted(
        [f for f in relationship.follow_ups if f.status == 'pending'],
        key=lambda x: x.due_date
    )
    return render_template('relationship_detail.html', relationship=relationship, pending_follow_ups=pending_follow_ups)


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

            # Update basic relationship fields
            relationship.name = data.get('name')
            relationship.goal = data.get('goal')
            relationship.execution_strategy = data.get('execution_strategy')
            relationship.priority = data.get('priority', 'Medium')
            relationship.interaction_level = data.get('interaction_level', 'Not Contacted')
            relationship.notes = data.get('notes')
            relationship.follow_up_frequency = data.get('follow_up_frequency') or None

            # Update connection types
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

            # Update tags
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

            # Update social media
            SocialMedia.query.filter_by(relationship_id=relationship.id).delete()
            _process_social_media_data(relationship, data)

            db.session.commit()
            recalculate_all_ratings_logic()
            recalculate_all_event_importance_logic()
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


def _process_social_media_data(relationship, data):
    """Helper function to process and save social media data for a relationship."""
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


@app.route('/relationships/<uuid:relationship_id>/add_follow_up', methods=['POST'])
def add_follow_up(relationship_id):
    """Adds a new manual follow-up task to a relationship."""
    relationship = Relationship.query.get_or_404(relationship_id)
    try:
        data = request.form
        topic = data.get('topic')
        due_date_str = data.get('due_date')

        if not topic or not due_date_str:
            raise ValueError("Topic and due date are required.")

        due_date = datetime.strptime(due_date_str, '%Y-%m-%d').replace(tzinfo=UTC)

        follow_up = FollowUp(
            relationship_id=relationship.id,
            topic=topic,
            due_date=due_date
        )
        db.session.add(follow_up)
        db.session.commit()
        flash('Follow-up task added.', 'success')
    except (ValueError, KeyError) as e:
        db.session.rollback()
        flash(f'Error adding follow-up: {e}', 'danger')

    return redirect(url_for('get_relationship', relationship_id=relationship_id) + '#follow-ups')


@app.route('/follow_ups/<int:follow_up_id>/delete', methods=['POST'])
def delete_follow_up(follow_up_id):
    """Deletes a follow-up task."""
    follow_up = FollowUp.query.get_or_404(follow_up_id)
    relationship_id = follow_up.relationship_id
    try:
        db.session.delete(follow_up)
        db.session.commit()
        flash('Follow-up task deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting task: {e}', 'danger')

    return redirect(url_for('get_relationship', relationship_id=relationship_id) + '#follow-ups')