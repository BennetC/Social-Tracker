from flask import render_template

from flask_app import app
from flask_app.models import Platform


@app.route('/platforms')
def view_platforms():
    """Displays a list of all platforms and their calculated priority ratings."""
    platforms = Platform.query.order_by(Platform.priority_rating.desc()).all()
    return render_template('platforms.html', platforms=platforms)