import uuid
from datetime import datetime, UTC
from flask_app import db

priority_level_enum = db.Enum(
    'Very High', 'High', 'Medium', 'Low', 'Very Low',
    name='priority_level',
    create_type=False
)
interaction_type_enum = db.Enum(
    'comment', 'DM', 'email', 'help', 'follow-up', 'meeting', 'call',
    name='interaction_type',
    create_type=False
)
interaction_level_enum = db.Enum(
    'New', 'Active', 'Dormant', 'Not Contacted',
    name='interaction_level',
    create_type=False
)

event_participants = db.Table('event_participants',
    db.Column('event_id', db.Integer, db.ForeignKey('events.id'), primary_key=True),
    db.Column('relationship_id', db.Uuid(as_uuid=True), db.ForeignKey('relationships.id'), primary_key=True)
)


class RelationshipConnectionType(db.Model):
    __tablename__ = 'relationship_connection_types'
    relationship_id = db.Column(db.Uuid(as_uuid=True), db.ForeignKey('relationships.id'), primary_key=True)
    connection_type_id = db.Column(db.Integer, db.ForeignKey('connection_types.id'), primary_key=True)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)
    relationship = db.relationship('Relationship', back_populates='connection_type_associations')
    connection_type = db.relationship('ConnectionType', back_populates='relationship_associations')


class RelationshipTag(db.Model):
    __tablename__ = 'relationship_tags'
    relationship_id = db.Column(db.Uuid(as_uuid=True), db.ForeignKey('relationships.id'), primary_key=True)
    tag_id = db.Column(db.Integer, db.ForeignKey('tags.id'), primary_key=True)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)
    relationship = db.relationship('Relationship', back_populates='tag_associations')
    tag = db.relationship('Tag', back_populates='relationship_associations')


class Event(db.Model):
    __tablename__ = 'events'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text, nullable=True)
    start_date = db.Column(db.DateTime(timezone=True), nullable=True)
    end_date = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC),
                           onupdate=lambda: datetime.now(UTC))

    priority = db.Column(priority_level_enum, nullable=False, default='Medium')

    participants = db.relationship('Relationship', secondary=event_participants, back_populates='events',
                                   lazy='dynamic')

    def __repr__(self):
        return f'<Event {self.title}>'


class ConnectionType(db.Model):
    __tablename__ = 'connection_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    priority_rating = db.Column(db.Float, default=0.0, nullable=False, server_default='0.0')
    relationship_associations = db.relationship('RelationshipConnectionType', back_populates='connection_type',
                                                cascade="all, delete-orphan")

    def __repr__(self):
        return f'<ConnectionType {self.name}>'


class Tag(db.Model):
    __tablename__ = 'tags'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    priority_rating = db.Column(db.Float, default=0.0, nullable=False, server_default='0.0')
    relationship_associations = db.relationship('RelationshipTag', back_populates='tag', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Tag {self.name}>'


class Relationship(db.Model):
    __tablename__ = 'relationships'
    id = db.Column(db.Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(100), nullable=False)
    goal = db.Column(db.String(255))
    execution_strategy = db.Column(db.String(255))
    last_contacted = db.Column(db.DateTime(timezone=True))
    next_contact_due = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC),
                           onupdate=lambda: datetime.now(UTC))
    notes = db.Column(db.Text)
    follow_up_frequency = db.Column(db.String(50), nullable=True)
    next_follow_up_topic = db.Column(db.Text, nullable=True)

    priority = db.Column(priority_level_enum, nullable=False, default='Medium')
    interaction_level = db.Column(interaction_level_enum, nullable=False, default='Not Contacted')

    connection_type_associations = db.relationship('RelationshipConnectionType', back_populates='relationship',
                                                   cascade="all, delete-orphan")
    tag_associations = db.relationship('RelationshipTag', back_populates='relationship', cascade="all, delete-orphan")
    interactions = db.relationship('InteractionHistory', back_populates='relationship', cascade="all, delete-orphan",
                                   order_by="desc(InteractionHistory.date)")
    social_media = db.relationship('SocialMedia', back_populates='relationship', cascade="all, delete-orphan")
    events = db.relationship('Event', secondary=event_participants, back_populates='participants', lazy='dynamic')

    @property
    def connection_type(self):
        primary_assoc = next((assoc for assoc in self.connection_type_associations if assoc.is_primary), None)
        if primary_assoc:
            return primary_assoc.connection_type.name
        if self.connection_type_associations:
            return self.connection_type_associations[0].connection_type.name
        return "N/A"


class Platform(db.Model):
    __tablename__ = 'platforms'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    priority_rating = db.Column(db.Float, nullable=False, default=0.0, server_default='0.0')
    requires_handle = db.Column(db.Boolean, nullable=False, default=True, server_default='true')
    requires_link = db.Column(db.Boolean, nullable=False, default=True, server_default='true')
    social_media_accounts = db.relationship('SocialMedia', back_populates='platform')

    @property
    def registered_users(self):
        return len(self.social_media_accounts)

    def __repr__(self):
        return f'<Platform {self.name}>'


class SocialMedia(db.Model):
    __tablename__ = 'social_media'
    id = db.Column(db.Integer, primary_key=True)
    relationship_id = db.Column(db.Uuid(as_uuid=True), db.ForeignKey('relationships.id'), nullable=False)
    platform_id = db.Column(db.Integer, db.ForeignKey('platforms.id'), nullable=False)
    handle = db.Column(db.String(100), nullable=True)
    profile_link = db.Column(db.String(255), nullable=True)
    is_primary = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC))
    relationship = db.relationship('Relationship', back_populates='social_media')
    platform = db.relationship('Platform', back_populates='social_media_accounts')


class InteractionHistory(db.Model):
    __tablename__ = 'interaction_history'
    id = db.Column(db.Integer, primary_key=True)
    relationship_id = db.Column(db.Uuid(as_uuid=True), db.ForeignKey('relationships.id'), nullable=False)
    date = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC))
    title = db.Column(db.String(255), nullable=False, server_default="Untitled Interaction")
    details = db.Column(db.Text, nullable=True)
    platform = db.Column(db.String(50), nullable=True)

    type = db.Column(interaction_type_enum, nullable=False)

    relationship = db.relationship('Relationship', back_populates='interactions')