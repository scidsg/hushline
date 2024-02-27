from flask import render_template, url_for, flash, redirect, request, Blueprint, current_app
from flask_login import login_user, current_user, logout_user, login_required
from yourapplication import db, limiter
from yourapplication.models import User, Post
from yourapplication.forms import RegistrationForm, LoginForm
from flask_limiter.util import get_remote_address

auth = Blueprint('auth', __name__)

@auth.route("/")
@auth.route("/home")
def home():
    posts = Post.query.order_by(Post.created_at.desc()).all()
    return render_template('home.html', posts=posts)

@auth.route("/register", methods=['GET', 'POST'])
@limiter.limit("5 per minute", key_func=get_remote_address)
def register():
    if current_user.is_authenticated:
        return redirect(url_for('auth.home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.password = form.password.data
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! You are now able to log in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('register.html', title='Register', form=form)

@auth.route("/login", methods=['GET', 'POST'])
@limiter.limit("10 per minute", key_func=get_remote_address)
def login():
    if current_user.is_authenticated:
        return redirect(url_for('auth.home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.verify_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            if next_page and url_for('auth.login') not in next_page:
                return redirect(next_page) if next_page else redirect(url_for('auth.home'))
            else:
                flash('Invalid redirect.', 'warning')
                return redirect(url_for('auth.home'))
        else:
            flash('Login Unsuccessful. Please check email and password.', 'danger')
    return render_template('login.html', title='Login', form=form)

@auth.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('auth.home'))

@auth.route("/account")
@login_required
def account():
    return render_template('account.html', title='Account')

# Error handling routes
@auth.app_errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@auth.app_errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500
