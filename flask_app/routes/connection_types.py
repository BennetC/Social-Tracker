from flask import request, redirect, url_for, render_template, flash
from sqlalchemy.exc import IntegrityError

from flask_app import app, db
from flask_app.models.models import ConnectionType


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