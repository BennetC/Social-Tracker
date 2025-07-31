from datetime import datetime, UTC, timedelta

from flask import render_template, current_app
from sqlalchemy import case, func
from sqlalchemy.orm import joinedload

from flask_app import app, db
from flask_app.models.models import (
    Relationship, SocialMedia, Tag, Platform, ConnectionType,
    RelationshipConnectionType, RelationshipTag, Event, FollowUp
)


def _create_next_automated_follow_up(relationship: Relationship):
    """
    Creates a new FollowUp record based on the relationship's follow-up frequency.
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
        due_date = datetime.now(UTC) + delta
        new_follow_up = FollowUp(
            relationship_id=relationship.id,
            topic=f"Automated Follow-up ({relationship.follow_up_frequency.capitalize()})",
            due_date=due_date,
            status='pending'
        )
        db.session.add(new_follow_up)


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

    # Subquery to find the earliest pending due date for each relationship
    subquery = db.session.query(
        FollowUp.relationship_id,
        func.min(FollowUp.due_date).label('next_due_date')
    ).filter(FollowUp.status == 'pending').group_by(FollowUp.relationship_id).subquery()

    relationships = Relationship.query.outerjoin(
        subquery, Relationship.id == subquery.c.relationship_id
    ).options(
        joinedload(Relationship.connection_type_associations).joinedload(RelationshipConnectionType.connection_type),
        joinedload(Relationship.tag_associations).joinedload(RelationshipTag.tag),
        joinedload(Relationship.social_media).joinedload(SocialMedia.platform)
    ).order_by(
        subquery.c.next_due_date.asc().nullslast(),
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


def _calculate_single_event_importance(event, priority_scores):
    """Calculates the importance score for a single event based on its participants."""
    score = 0
    # Because participants is a 'dynamic' loader, accessing it here returns a query
    # which we can then iterate over.
    if not event.participants:
        return 0
    for participant in event.participants:
        score += priority_scores.get(participant.priority, 0)
    return score


def recalculate_all_event_importance_logic():
    """Recalculates importance scores for all events."""
    print("Starting importance recalculation for all events...")
    priority_scores = current_app.config.get('PRIORITY_SCORES', {})

    # MODIFIED: Removed the incompatible .options(joinedload(...))
    # We will let the 'lazy=dynamic' relationship handle loading participants
    # inside the loop.
    events = Event.query.all()

    for event in events:
        event.importance_score = _calculate_single_event_importance(event, priority_scores)
    db.session.commit()
    print("Event importance recalculation complete.")


@app.cli.command("recalculate-event-importance")
def recalculate_event_importance_command():
    """CLI wrapper for the event importance recalculation logic."""
    recalculate_all_event_importance_logic()