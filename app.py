from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import random

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///subscriptions.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'dev-secret-key-change-me'
db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'user' or 'admin'

class Plan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    quota_gb = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(500))
    active = db.Column(db.Boolean, default=True)

class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'), nullable=False)
    status = db.Column(db.String(20), default='active')  # active, cancelled
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime)
    
    # Relationships
    user = db.relationship('User', backref='subscriptions')
    plan = db.relationship('Plan', backref='subscriptions')

class Discount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_type = db.Column(db.String(20), nullable=False)  # 'percentage' or 'fixed'
    discount_value = db.Column(db.Float, nullable=False)
    min_amount = db.Column(db.Float, default=0.0)
    max_discount = db.Column(db.Float)
    valid_from = db.Column(db.DateTime, nullable=False)
    valid_until = db.Column(db.DateTime, nullable=False)
    usage_limit = db.Column(db.Integer, default=None)  # None for unlimited
    used_count = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)
    description = db.Column(db.String(500))

class DiscountUsage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    discount_id = db.Column(db.Integer, db.ForeignKey('discount.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscription.id'), nullable=False)
    discount_amount = db.Column(db.Float, nullable=False)
    used_at = db.Column(db.DateTime, default=datetime.utcnow)

class PaymentMethod(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    card_type = db.Column(db.String(20), nullable=False)  # visa, mastercard, etc.
    last_four_digits = db.Column(db.String(4), nullable=False)
    expiry_month = db.Column(db.Integer, nullable=False)
    expiry_year = db.Column(db.Integer, nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

class BillingHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscription.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method_id = db.Column(db.Integer, db.ForeignKey('payment_method.id'), nullable=True)
    status = db.Column(db.String(20), default='paid')  # paid, pending, failed
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    
    # Relationships
    user = db.relationship('User', backref='billing_history')
    subscription = db.relationship('Subscription', backref='billing_history')
    payment_method = db.relationship('PaymentMethod', backref='billing_history')

class Analytics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    metric_name = db.Column(db.String(100), nullable=False)
    metric_value = db.Column(db.Float, nullable=False)
    metric_date = db.Column(db.Date, nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor = db.Column(db.String(80))
    action = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Chatbot models (additive)
class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='chats')

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'), nullable=False)
    sender = db.Column(db.String(10), nullable=False)  # 'user' or 'bot'
    text = db.Column(db.String(2000), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    chat = db.relationship('Chat', backref='messages')

# Helpers
def seed_data():
    if User.query.count() == 0:
        admin = User(username='admin', password='admin123', role='admin')
        user = User(username='user1', password='user123', role='user')
        db.session.add_all([admin, user])
    if Plan.query.count() == 0:
        plans = [
            Plan(name='Basic Fiber', quota_gb=100, price=499.0, description='Basic broadband 100GB/mo'),
            Plan(name='Pro Fiber', quota_gb=500, price=899.0, description='Faster speeds for families'),
            Plan(name='Unlimited', quota_gb=0, price=1299.0, description='Unlimited plan (quota guide only)'),
        ]
        db.session.add_all(plans)
    if Discount.query.count() == 0:
        discounts = [
            Discount(
                name='Summer Special', 
                code='SUMMER20', 
                discount_type='percentage', 
                discount_value=20.0, 
                valid_from=datetime.utcnow(), 
                valid_until=datetime.utcnow() + timedelta(days=30),
                usage_limit=100,
                description='20% off on all plans for summer season'
            ),
            Discount(
                name='New User Welcome', 
                code='WELCOME10', 
                discount_type='fixed', 
                discount_value=100.0, 
                valid_from=datetime.utcnow(), 
                valid_until=datetime.utcnow() + timedelta(days=90),
                usage_limit=50,
                description='₹100 off for new users'
            )
        ]
        db.session.add_all(discounts)
    if PaymentMethod.query.count() == 0:
        # Add sample payment methods for user1
        user1 = User.query.filter_by(username='user1').first()
        if user1:
            payment_methods = [
                PaymentMethod(
                    user_id=user1.id,
                    card_type='visa',
                    last_four_digits='4242',
                    expiry_month=12,
                    expiry_year=2026,
                    is_default=True
                ),
                PaymentMethod(
                    user_id=user1.id,
                    card_type='mastercard',
                    last_four_digits='1234',
                    expiry_month=8,
                    expiry_year=2025,
                    is_default=False
                ),
                PaymentMethod(
                    user_id=user1.id,
                    card_type='upi',
                    last_four_digits='1234',
                    expiry_month=12,
                    expiry_year=2030,
                    is_default=False
                )
            ]
            db.session.add_all(payment_methods)
    
    # Add sample subscriptions for analytics
    if Subscription.query.count() == 0:
        user1 = User.query.filter_by(username='user1').first()
        if user1:
            plans = Plan.query.all()
            if plans:
                # Create sample subscriptions with different dates for analytics
                sample_subs = [
                    Subscription(
                        user_id=user1.id,
                        plan_id=plans[0].id,
                        status='active',
                        start_date=datetime.utcnow() - timedelta(days=30),
                        end_date=datetime.utcnow() + timedelta(days=30)
                    ),
                    Subscription(
                        user_id=user1.id,
                        plan_id=plans[1].id,
                        status='active',
                        start_date=datetime.utcnow() - timedelta(days=15),
                        end_date=datetime.utcnow() + timedelta(days=15)
                    ),
                    Subscription(
                        user_id=user1.id,
                        plan_id=plans[0].id,
                        status='cancelled',
                        start_date=datetime.utcnow() - timedelta(days=60),
                        end_date=datetime.utcnow() - timedelta(days=30)
                    )
                ]
                db.session.add_all(sample_subs)
    
    # Add sample billing history
    if BillingHistory.query.count() == 0:
        user1 = User.query.filter_by(username='user1').first()
        if user1:
            # Get user's subscriptions
            user_subs = Subscription.query.filter_by(user_id=user1.id).all()
            payment_method = PaymentMethod.query.filter_by(user_id=user1.id, is_default=True).first()
            
            billing_records = []
            for i, sub in enumerate(user_subs):
                billing_records.append(BillingHistory(
                    user_id=user1.id,
                    subscription_id=sub.id,
                    amount=sub.plan.price,
                    payment_method_id=payment_method.id if payment_method else None,
                    status='paid',
                    payment_date=datetime.utcnow() - timedelta(days=30-i*10),
                    invoice_number=f'INV-{1000+i}',
                    description=f'{sub.plan.name} subscription payment'
                ))
            db.session.add_all(billing_records)
    db.session.commit()

def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return User.query.get(uid)

# Routes
@app.route('/')
def index():
    user = current_user()
    return render_template('index.html', user=user)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session['user_id'] = user.id
            session['role'] = user.role
            session['login_at'] = datetime.utcnow().isoformat()
            flash('Logged in successfully', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out', 'info')
    return redirect(url_for('index'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form.get('role', 'user')  # Default to 'user' role
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return render_template('signup.html')
        
        # Create new user
        user = User(username=username, password=password, role=role)
        db.session.add(user)
        db.session.add(AuditLog(actor=username, action=f"User registered with role {role}"))
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('signup.html')

# User pages
@app.route('/user/dashboard')
def user_dashboard():
    user = current_user()
    if not user or user.role != 'user':
        return redirect(url_for('login'))
    subs = Subscription.query.filter_by(user_id=user.id).all()
    plans = Plan.query.filter_by(active=True).all()
    # Ensure chat tables exist (safe if already created)
    try:
        Chat.__table__.create(bind=db.engine, checkfirst=True)
        ChatMessage.__table__.create(bind=db.engine, checkfirst=True)
    except Exception:
        pass
    return render_template('user_dashboard.html', user=user, subs=subs, plans=plans)

@app.route('/plans')
def list_plans():
    user = current_user()
    plans = Plan.query.filter_by(active=True).all()
    return render_template('plans.html', plans=plans, user=user)

@app.route('/subscribe/<int:plan_id>', methods=['POST'])
def subscribe(plan_id):
    user = current_user()
    if not user or user.role != 'user':
        flash('Login as user to subscribe', 'warning')
        return redirect(url_for('login'))
    
    plan = Plan.query.get_or_404(plan_id)
    
    # Check if user has any payment methods
    payment_methods = PaymentMethod.query.filter_by(user_id=user.id, is_active=True).all()
    if not payment_methods:
        flash('Please add a payment method before subscribing', 'info')
        return redirect(url_for('user_payment_methods'))
    
    # Get discount code from form early (so redirects preserve it)
    discount_code = request.form.get('discount_code', '').strip().upper()

    # Check if payment method is selected in the form
    selected_payment_id = request.form.get('payment_method_id')
    if not selected_payment_id:
        # For AJAX requests, return JSON error; otherwise redirect
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Please select a payment method'})
        return redirect(url_for('select_payment_method', plan_id=plan_id, discount_code=discount_code))
    
    # Get the selected payment method
    selected_payment = PaymentMethod.query.filter_by(id=selected_payment_id, user_id=user.id, is_active=True).first()
    if not selected_payment:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Invalid payment method selected'})
        flash('Invalid payment method selected', 'danger')
        return redirect(url_for('select_payment_method', plan_id=plan_id, discount_code=discount_code))

    discount_amount = 0
    
    # Apply discount if code provided
    if discount_code:
        discount = Discount.query.filter_by(code=discount_code, active=True).first()
        if discount:
            now = datetime.utcnow()
            if now < discount.valid_from:
                flash('Discount not yet valid', 'warning')
            elif now > discount.valid_until:
                flash('Discount validity expired', 'warning')
            elif discount.usage_limit and discount.used_count >= discount.usage_limit:
                flash('Discount code usage limit exceeded', 'warning')
            else:
                if discount.discount_type == 'percentage':
                    discount_amount = (plan.price * discount.discount_value) / 100
                    if discount.max_discount:
                        discount_amount = min(discount_amount, discount.max_discount)
                else:
                    discount_amount = min(discount.discount_value, plan.price)
                
                # Update discount usage
                discount.used_count += 1
                db.session.add(discount)
        else:
            flash('Invalid discount code', 'warning')
    
    # Use the selected payment method
    default_payment = selected_payment
    
    # Create subscription
    sub = Subscription(
        user_id=user.id, 
        plan_id=plan.id, 
        status='active', 
        start_date=datetime.utcnow(), 
        end_date=datetime.utcnow()+timedelta(days=30)
    )
    db.session.add(sub)
    db.session.flush()  # Get the subscription ID
    
    # Create billing record
    final_amount = max(0, plan.price - discount_amount)
    billing_record = BillingHistory(
        user_id=user.id,
        subscription_id=sub.id,
        amount=final_amount,
        payment_method_id=default_payment.id,
        status='paid',
        payment_date=datetime.utcnow(),
        invoice_number=f'INV-{sub.id}-{int(datetime.utcnow().timestamp())}',
        description=f'{plan.name} subscription payment'
    )
    db.session.add(billing_record)
    
    # Create discount usage record if discount applied
    if discount_amount > 0:
        discount_usage = DiscountUsage(
            discount_id=discount.id,
            user_id=user.id,
            subscription_id=sub.id,
            discount_amount=discount_amount
        )
        db.session.add(discount_usage)
    
    action_msg = f"Subscribed to {plan.name}"
    if discount_amount > 0:
        action_msg += f" with {discount_code} discount (₹{discount_amount:.2f} off)"
    
    db.session.add(AuditLog(actor=user.username, action=action_msg))
    db.session.commit()
    
    # Demo-friendly success handling
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Return JSON so the frontend can show a success modal without redirecting
        return jsonify({
            'success': True,
            'message': 'Subscription successful',
            'final_amount': final_amount,
            'payment_method': f"{default_payment.card_type.upper()} ****{default_payment.last_four_digits}"
        })
    else:
        if discount_amount > 0:
            flash(f'Subscription successful! You saved ₹{discount_amount:.2f} with discount code {discount_code}. Payment processed using {default_payment.card_type.upper()} ending in {default_payment.last_four_digits}', 'success')
        else:
            flash(f'Subscription successful! Payment processed using {default_payment.card_type.upper()} ending in {default_payment.last_four_digits}', 'success')
        
        return redirect(url_for('user_dashboard'))

@app.route('/select-payment/<int:plan_id>')
def select_payment_method(plan_id):
    user = current_user()
    if not user or user.role != 'user':
        return redirect(url_for('login'))
    
    plan = Plan.query.get_or_404(plan_id)
    payment_methods = PaymentMethod.query.filter_by(user_id=user.id, is_active=True).all()
    discount_code = request.args.get('discount_code', '')
    
    if not payment_methods:
        flash('Please add a payment method before subscribing', 'info')
        return redirect(url_for('user_payment_methods'))
    
    # Calculate discount if code provided
    discount_amount = 0
    if discount_code:
        discount = Discount.query.filter_by(code=discount_code, active=True).first()
        if discount and discount.valid_from <= datetime.utcnow() <= discount.valid_until:
            if not discount.usage_limit or discount.used_count < discount.usage_limit:
                if discount.discount_type == 'percentage':
                    discount_amount = (plan.price * discount.discount_value) / 100
                    if discount.max_discount:
                        discount_amount = min(discount_amount, discount.max_discount)
                else:
                    discount_amount = min(discount.discount_value, plan.price)
    
    final_amount = max(0, plan.price - discount_amount)
    
    return render_template('select_payment_method.html', 
                         plan=plan, 
                         payment_methods=payment_methods, 
                         discount_code=discount_code,
                         discount_amount=discount_amount,
                         final_amount=final_amount)

@app.route('/apply_discount', methods=['POST'])
def apply_discount():
    user = current_user()
    if not user:
        return jsonify({'success': False, 'message': 'Please login first'})
    
    discount_code = request.form.get('discount_code', '').strip().upper()
    plan_id = request.form.get('plan_id')
    
    if not discount_code or not plan_id:
        return jsonify({'success': False, 'message': 'Please provide discount code and plan'})
    
    plan = Plan.query.get_or_404(plan_id)
    discount = Discount.query.filter_by(code=discount_code, active=True).first()
    
    if not discount:
        return jsonify({'success': False, 'message': 'Invalid discount code'})
    
    if not (discount.valid_from <= datetime.utcnow() <= discount.valid_until):
        return jsonify({'success': False, 'message': 'Discount code has expired'})
    
    if discount.usage_limit and discount.used_count >= discount.usage_limit:
        return jsonify({'success': False, 'message': 'Discount code usage limit exceeded'})
    
    if plan.price < discount.min_amount:
        return jsonify({'success': False, 'message': f'Minimum order amount of ₹{discount.min_amount} required'})
    
    # Calculate discount amount
    if discount.discount_type == 'percentage':
        discount_amount = (plan.price * discount.discount_value) / 100
        if discount.max_discount:
            discount_amount = min(discount_amount, discount.max_discount)
    else:
        discount_amount = min(discount.discount_value, plan.price)
    
    final_price = plan.price - discount_amount
    
    return jsonify({
        'success': True,
        'discount_amount': discount_amount,
        'original_price': plan.price,
        'final_price': final_price,
        'discount_name': discount.name,
        'discount_type': discount.discount_type
    })

@app.route('/cancel/<int:sub_id>', methods=['POST'])
def cancel(sub_id):
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    sub = Subscription.query.get_or_404(sub_id)
    if user.role!='admin' and sub.user_id != user.id:
        flash('Not authorized', 'danger')
        return redirect(url_for('user_dashboard'))
    sub.status = 'cancelled'
    db.session.add(AuditLog(actor=user.username, action=f"Cancelled subscription {sub.id}"))
    db.session.commit()
    flash('Subscription cancelled', 'info')
    return redirect(url_for('user_dashboard') if user.role=='user' else url_for('admin_dashboard'))

@app.route('/renew/<int:sub_id>', methods=['POST'])
def renew(sub_id):
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    sub = Subscription.query.get_or_404(sub_id)
    if user.role!='admin' and sub.user_id != user.id:
        flash('Not authorized', 'danger')
        return redirect(url_for('user_dashboard'))
    sub.status = 'active'
    sub.end_date = datetime.utcnow()+timedelta(days=30)
    db.session.add(AuditLog(actor=user.username, action=f"Renewed subscription {sub.id}"))
    db.session.commit()
    flash('Subscription renewed', 'success')
    return redirect(url_for('user_dashboard') if user.role=='user' else url_for('admin_dashboard'))

@app.route('/upgrade/<int:sub_id>', methods=['POST'])
def upgrade_subscription(sub_id):
    user = current_user()
    if not user or user.role != 'user':
        flash('Login as user to upgrade subscription', 'warning')
        return redirect(url_for('login'))
    
    sub = Subscription.query.get_or_404(sub_id)
    if sub.user_id != user.id:
        flash('Not authorized', 'danger')
        return redirect(url_for('user_dashboard'))
    
    new_plan_id = request.form.get('new_plan_id')
    if not new_plan_id:
        flash('Please select a plan to upgrade to', 'warning')
        return redirect(url_for('user_dashboard'))
    
    new_plan = Plan.query.get_or_404(new_plan_id)
    old_plan = sub.plan
    
    # Cancel current subscription
    sub.status = 'cancelled'
    
    # Create new subscription
    new_sub = Subscription(
        user_id=user.id,
        plan_id=new_plan.id,
        status='active',
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=30)
    )
    
    db.session.add(new_sub)
    db.session.add(AuditLog(actor=user.username, action=f"Upgraded from {old_plan.name} to {new_plan.name}"))
    db.session.commit()
    
    flash(f'Successfully upgraded from {old_plan.name} to {new_plan.name}', 'success')
    return redirect(url_for('user_dashboard'))

@app.route('/downgrade/<int:sub_id>', methods=['POST'])
def downgrade_subscription(sub_id):
    user = current_user()
    if not user or user.role != 'user':
        flash('Login as user to downgrade subscription', 'warning')
        return redirect(url_for('login'))
    
    sub = Subscription.query.get_or_404(sub_id)
    if sub.user_id != user.id:
        flash('Not authorized', 'danger')
        return redirect(url_for('user_dashboard'))
    
    new_plan_id = request.form.get('new_plan_id')
    if not new_plan_id:
        flash('Please select a plan to downgrade to', 'warning')
        return redirect(url_for('user_dashboard'))
    
    new_plan = Plan.query.get_or_404(new_plan_id)
    old_plan = sub.plan
    
    # Cancel current subscription
    sub.status = 'cancelled'
    
    # Create new subscription
    new_sub = Subscription(
        user_id=user.id,
        plan_id=new_plan.id,
        status='active',
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=30)
    )
    
    db.session.add(new_sub)
    db.session.add(AuditLog(actor=user.username, action=f"Downgraded from {old_plan.name} to {new_plan.name}"))
    db.session.commit()
    
    flash(f'Successfully downgraded from {old_plan.name} to {new_plan.name}', 'success')
    return redirect(url_for('user_dashboard'))

# Admin pages
@app.route('/admin/dashboard')
def admin_dashboard():
    user = current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    plans = Plan.query.all()
    discounts = Discount.query.filter_by(active=True).all()
    total_users = User.query.filter_by(role='user').count()
    total_subs = Subscription.query.count()
    from sqlalchemy import func
    plan_counts = db.session.query(Plan.name, func.count(Subscription.id)).join(Subscription, Subscription.plan_id==Plan.id).group_by(Plan.name).all()
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()
    return render_template('admin_dashboard.html', plans=plans, discounts=discounts, total_users=total_users, total_subs=total_subs, plan_counts=plan_counts, logs=logs)

@app.route('/admin/plans/create', methods=['GET','POST'])
def create_plan():
    user = current_user()
    if not user or user.role!='admin':
        return redirect(url_for('login'))
    if request.method=='POST':
        name = request.form['name']
        quota = int(request.form['quota_gb'])
        price = float(request.form['price'])
        desc = request.form.get('description','')
        plan = Plan(name=name, quota_gb=quota, price=price, description=desc, active=True)
        db.session.add(plan)
        db.session.add(AuditLog(actor=user.username, action=f"Created plan {name}"))
        db.session.commit()
        flash('Plan created', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('create_plan.html')

@app.route('/admin/plans/<int:plan_id>/edit', methods=['GET','POST'])
def edit_plan(plan_id):
    user = current_user()
    if not user or user.role!='admin':
        return redirect(url_for('login'))
    plan = Plan.query.get_or_404(plan_id)
    if request.method=='POST':
        plan.name = request.form['name']
        plan.quota_gb = int(request.form['quota_gb'])
        plan.price = float(request.form['price'])
        plan.description = request.form.get('description','')
        db.session.add(AuditLog(actor=user.username, action=f"Edited plan {plan.name}"))
        db.session.commit()
        flash('Plan updated', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('edit_plan.html', plan=plan)

@app.route('/admin/plans/<int:plan_id>/delete', methods=['POST'])
def delete_plan(plan_id):
    user = current_user()
    if not user or user.role!='admin':
        return redirect(url_for('login'))
    plan = Plan.query.get_or_404(plan_id)
    plan.active = False
    db.session.add(AuditLog(actor=user.username, action=f"Deactivated plan {plan.name}"))
    db.session.commit()
    flash('Plan deactivated', 'info')
    return redirect(url_for('admin_dashboard'))

# Discount Management Routes
@app.route('/admin/discounts')
def list_discounts():
    user = current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    discounts = Discount.query.all()
    return render_template('admin_discounts.html', discounts=discounts)

@app.route('/admin/discounts/create', methods=['GET', 'POST'])
def create_discount():
    user = current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form['name']
        code = request.form['code']
        discount_type = request.form['discount_type']
        discount_value = float(request.form['discount_value'])
        min_amount = float(request.form.get('min_amount', 0))
        max_discount = float(request.form.get('max_discount', 0)) if request.form.get('max_discount') else None
        valid_from = datetime.strptime(request.form['valid_from'], '%Y-%m-%d')
        valid_until = datetime.strptime(request.form['valid_until'], '%Y-%m-%d')
        usage_limit = int(request.form['usage_limit']) if request.form.get('usage_limit') else None
        description = request.form.get('description', '')
        
        discount = Discount(
            name=name, code=code, discount_type=discount_type, 
            discount_value=discount_value, min_amount=min_amount, 
            max_discount=max_discount, valid_from=valid_from, 
            valid_until=valid_until, usage_limit=usage_limit, 
            description=description
        )
        db.session.add(discount)
        db.session.add(AuditLog(actor=user.username, action=f"Created discount {name}"))
        db.session.commit()
        flash('Discount created successfully', 'success')
        return redirect(url_for('list_discounts'))
    return render_template('create_discount.html')

@app.route('/admin/discounts/<int:discount_id>/edit', methods=['GET', 'POST'])
def edit_discount(discount_id):
    user = current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    discount = Discount.query.get_or_404(discount_id)
    if request.method == 'POST':
        discount.name = request.form['name']
        discount.code = request.form['code']
        discount.discount_type = request.form['discount_type']
        discount.discount_value = float(request.form['discount_value'])
        discount.min_amount = float(request.form.get('min_amount', 0))
        discount.max_discount = float(request.form.get('max_discount', 0)) if request.form.get('max_discount') else None
        discount.valid_from = datetime.strptime(request.form['valid_from'], '%Y-%m-%d')
        discount.valid_until = datetime.strptime(request.form['valid_until'], '%Y-%m-%d')
        discount.usage_limit = int(request.form['usage_limit']) if request.form.get('usage_limit') else None
        discount.description = request.form.get('description', '')
        
        db.session.add(AuditLog(actor=user.username, action=f"Edited discount {discount.name}"))
        db.session.commit()
        flash('Discount updated successfully', 'success')
        return redirect(url_for('list_discounts'))
    return render_template('edit_discount.html', discount=discount)

@app.route('/admin/discounts/<int:discount_id>/toggle', methods=['POST'])
def toggle_discount(discount_id):
    user = current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    discount = Discount.query.get_or_404(discount_id)
    discount.active = not discount.active
    db.session.add(AuditLog(actor=user.username, action=f"Toggled discount {discount.name} to {'active' if discount.active else 'inactive'}"))
    db.session.commit()
    flash(f'Discount {"activated" if discount.active else "deactivated"}', 'info')
    return redirect(url_for('list_discounts'))

# Analytics Routes
@app.route('/admin/analytics')
def admin_analytics():
    user = current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    
    # Get subscription trends
    from sqlalchemy import func, extract
    monthly_subs_raw = db.session.query(
        extract('month', Subscription.start_date).label('month'),
        func.count(Subscription.id).label('count')
    ).group_by(extract('month', Subscription.start_date)).all()
    
    # Convert Row objects to dictionaries for JSON serialization
    monthly_subs = [{'month': int(row.month), 'count': row.count} for row in monthly_subs_raw]
    
    # Get plan popularity
    plan_popularity_raw = db.session.query(
        Plan.name, func.count(Subscription.id).label('count')
    ).join(Subscription, Subscription.plan_id == Plan.id).group_by(Plan.name).all()
    
    # Convert Row objects to dictionaries for JSON serialization
    plan_popularity = [{'name': row.name, 'count': row.count} for row in plan_popularity_raw]
    
    # Get churn rate
    total_subs = Subscription.query.count()
    cancelled_subs = Subscription.query.filter_by(status='cancelled').count()
    churn_rate = (cancelled_subs / total_subs * 100) if total_subs > 0 else 0
    
    # Get revenue data
    revenue_data_raw = db.session.query(
        Plan.name, func.sum(Plan.price).label('revenue')
    ).join(Subscription, Subscription.plan_id == Plan.id).group_by(Plan.name).all()
    
    # Convert Row objects to dictionaries for JSON serialization
    revenue_data = [{'name': row.name, 'revenue': float(row.revenue)} for row in revenue_data_raw]
    
    return render_template('admin_analytics.html', 
                         monthly_subs=monthly_subs,
                         plan_popularity=plan_popularity,
                         churn_rate=churn_rate,
                         revenue_data=revenue_data)

@app.route('/admin/seed_analytics')
def admin_seed_analytics():
    """Create additional synthetic subscriptions and billing records across the last 12 months.
    Admin-only for demo/analytics purposes.
    """
    user = current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))

    plans = Plan.query.all()
    if not plans:
        flash('No plans found to seed analytics data.', 'warning')
        return redirect(url_for('admin_analytics'))

    # Ensure an admin-owned demo user exists for analytics noise
    demo_user = User.query.filter_by(username='demo_analytics').first()
    if not demo_user:
        demo_user = User(username='demo_analytics', password='demo', role='user')
        db.session.add(demo_user)
        db.session.flush()  # get ID

    # Create synthetic subscriptions per month
    now = datetime.utcnow()
    created_count = 0
    for m in range(1, 13):  # last 12 months
        # pick a date roughly m months ago
        start_date = now - timedelta(days=30*m + random.randint(-5, 5))
        # create 2-5 subs per month with random plans and statuses
        for _ in range(random.randint(2, 5)):
            plan = random.choice(plans)
            status = random.choice(['active', 'cancelled'])
            # end_date 15-60 days after start for active, or before now for cancelled
            if status == 'active':
                end_date = start_date + timedelta(days=random.randint(30, 90))
            else:
                end_date = start_date + timedelta(days=random.randint(15, 45))
            sub = Subscription(
                user_id=demo_user.id,
                plan_id=plan.id,
                status=status,
                start_date=start_date,
                end_date=end_date
            )
            db.session.add(sub)
            created_count += 1

    db.session.commit()

    # Create billing history for active subscriptions
    payment_method = PaymentMethod.query.filter_by(user_id=demo_user.id, is_default=True).first()
    if not payment_method:
        payment_method = PaymentMethod(
            user_id=demo_user.id,
            card_type='visa',
            last_four_digits='0000',
            expiry_month=12,
            expiry_year=2030,
            is_default=True
        )
        db.session.add(payment_method)
        db.session.flush()

    subs = Subscription.query.filter_by(user_id=demo_user.id).all()
    invoice_base = 5000
    for i, sub in enumerate(subs):
        if BillingHistory.query.filter_by(subscription_id=sub.id).first():
            continue
        db.session.add(BillingHistory(
            user_id=demo_user.id,
            subscription_id=sub.id,
            amount=sub.plan.price,
            payment_method_id=payment_method.id,
            status='paid' if sub.status == 'active' else 'failed',
            payment_date=sub.start_date + timedelta(days=5),
            invoice_number=f'INV-{invoice_base + i}',
            description=f'{sub.plan.name} seeded payment'
        ))

    db.session.add(AuditLog(actor='admin', action=f"Seeded analytics data: {created_count} subscriptions"))
    db.session.commit()

    flash(f'Seeded analytics data with {created_count} subscriptions and billing entries.', 'success')
    return redirect(url_for('admin_analytics'))

@app.route('/api/analytics/subscription_trends')
def api_subscription_trends():
    from sqlalchemy import func, extract
    # Get active subscriptions by month
    active_data = db.session.query(
        extract('month', Subscription.start_date).label('month'),
        func.count(Subscription.id).label('count')
    ).filter(Subscription.status == 'active').group_by(extract('month', Subscription.start_date)).all()
    
    # Get cancelled subscriptions by month
    cancelled_data = db.session.query(
        extract('month', Subscription.start_date).label('month'),
        func.count(Subscription.id).label('count')
    ).filter(Subscription.status == 'cancelled').group_by(extract('month', Subscription.start_date)).all()
    
    # Create month mapping
    all_months = set()
    active_dict = {}
    cancelled_dict = {}
    
    for row in active_data:
        month = int(row.month)
        all_months.add(month)
        active_dict[month] = row.count
    
    for row in cancelled_data:
        month = int(row.month)
        all_months.add(month)
        cancelled_dict[month] = row.count
    
    # Sort months and create arrays
    sorted_months = sorted(all_months)
    months = [f"Month {month}" for month in sorted_months]
    active = [active_dict.get(month, 0) for month in sorted_months]
    cancelled = [cancelled_dict.get(month, 0) for month in sorted_months]
    
    return jsonify({
        'labels': months,
        'datasets': [
            {'label': 'Active Subscriptions', 'data': active, 'backgroundColor': '#1cc88a'},
            {'label': 'Cancelled Subscriptions', 'data': cancelled, 'backgroundColor': '#e74a3b'}
        ]
    })

@app.route('/api/analytics/revenue')
def api_revenue():
    from sqlalchemy import func, extract
    data = db.session.query(
        extract('month', Subscription.start_date).label('month'),
        func.sum(Plan.price).label('revenue')
    ).join(Plan, Subscription.plan_id == Plan.id).group_by(extract('month', Subscription.start_date)).all()
    
    months = [f"Month {int(r[0])}" for r in data]
    revenue = [float(r[1]) for r in data]
    
    return jsonify({'labels': months, 'data': revenue})

@app.route('/api/analytics/subscription_status')
def api_subscription_status():
    from sqlalchemy import func
    data = db.session.query(
        Subscription.status, func.count(Subscription.id).label('count')
    ).group_by(Subscription.status).all()
    
    labels = [row.status.title() for row in data]
    counts = [row.count for row in data]
    
    return jsonify({'labels': labels, 'data': counts})

@app.route('/api/analytics/subscription_growth')
def api_subscription_growth():
    from sqlalchemy import func, extract
    data = db.session.query(
        extract('month', Subscription.start_date).label('month'),
        func.count(Subscription.id).label('count')
    ).group_by(extract('month', Subscription.start_date)).order_by(extract('month', Subscription.start_date)).all()
    
    months = [f"Month {int(row.month)}" for row in data]
    counts = [row.count for row in data]
    
    return jsonify({'labels': months, 'data': counts})

@app.route('/api/analytics/subscription_duration')
def api_subscription_duration():
    from sqlalchemy import func, case
    from datetime import datetime, timedelta
    
    # Calculate duration categories
    now = datetime.utcnow()
    data = db.session.query(
        case(
            (Subscription.end_date > now + timedelta(days=30), 'Long-term (30+ days)'),
            (Subscription.end_date > now + timedelta(days=7), 'Medium-term (7-30 days)'),
            (Subscription.end_date > now, 'Short-term (1-7 days)'),
            else_='Expired'
        ).label('duration_category'),
        func.count(Subscription.id).label('count')
    ).group_by('duration_category').all()
    
    labels = [row.duration_category for row in data]
    counts = [row.count for row in data]
    
    return jsonify({'labels': labels, 'data': counts})

@app.route('/api/plan_counts')
def api_plan_counts():
    from sqlalchemy import func
    data = db.session.query(Plan.name, func.count(Subscription.id)).join(Subscription, Subscription.plan_id==Plan.id).group_by(Plan.name).all()
    labels = [r[0] for r in data]
    values = [r[1] for r in data]
    return jsonify({'labels': labels, 'values': values})

# User Recommendations and Notifications
@app.route('/user/recommendations')
def user_recommendations():
    user = current_user()
    if not user or user.role != 'user':
        return redirect(url_for('login'))
    
    from sqlalchemy import func
    
    # Get user's subscription history
    user_subs = Subscription.query.filter_by(user_id=user.id).all()
    current_plan = None
    for sub in user_subs:
        if sub.status == 'active':
            current_plan = sub.plan
            break
    
    # Get all available plans
    all_plans = Plan.query.filter_by(active=True).all()
    
    # Simple recommendation logic based on current plan
    recommendations = []
    if current_plan:
        for plan in all_plans:
            if plan.id != current_plan.id:
                if plan.price > current_plan.price:
                    recommendations.append({
                        'plan': plan,
                        'type': 'upgrade',
                        'reason': f'Get more features with {plan.name}',
                        'savings': None
                    })
                elif plan.price < current_plan.price:
                    recommendations.append({
                        'plan': plan,
                        'type': 'downgrade',
                        'reason': f'Save money with {plan.name}',
                        'savings': current_plan.price - plan.price
                    })
    else:
        # No current subscription - recommend based on popularity
        popular_plans = db.session.query(Plan, func.count(Subscription.id).label('count')).join(Subscription, Subscription.plan_id == Plan.id).group_by(Plan.id).order_by(func.count(Subscription.id).desc()).limit(3).all()
        for plan, count in popular_plans:
            recommendations.append({
                'plan': plan,
                'type': 'popular',
                'reason': f'Most popular choice ({count} subscribers)',
                'savings': None
            })
    
    return render_template('user_recommendations.html', recommendations=recommendations, current_plan=current_plan)

@app.route('/user/offers')
def user_offers():
    user = current_user()
    if not user or user.role != 'user':
        return redirect(url_for('login'))
    
    # Get active discounts
    active_discounts = Discount.query.filter(
        Discount.active == True,
        Discount.valid_from <= datetime.utcnow(),
        Discount.valid_until >= datetime.utcnow()
    ).all()
    
    # Get user's subscription history to personalize offers
    user_subs = Subscription.query.filter_by(user_id=user.id).all()
    current_plan = None
    for sub in user_subs:
        if sub.status == 'active':
            current_plan = sub.plan
            break
    
    return render_template('user_offers.html', discounts=active_discounts, current_plan=current_plan)

# ===== Chatbot API (additive, user-scoped) =====
from flask import jsonify

@app.route('/api/chats', methods=['GET'])
def api_get_chats():
    user = current_user()
    if not user or user.role != 'user':
        return jsonify([]), 200
    chats = Chat.query.filter_by(user_id=user.id).order_by(Chat.created_at.asc()).all()
    result = []
    for c in chats:
        result.append({
            'chat_id': c.id,
            'name': c.name,
            'messages': [
                {
                    'sender': m.sender,
                    'text': m.text,
                    'timestamp': m.timestamp.isoformat()
                } for m in sorted(c.messages, key=lambda x: x.timestamp)
            ]
        })
    return jsonify(result), 200

@app.route('/api/chats', methods=['POST'])
def api_create_chat():
    user = current_user()
    if not user or user.role != 'user':
        return jsonify({'error': 'unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    name = data.get('name') or f"Chat {datetime.utcnow().strftime('%H%M%S')}"
    chat = Chat(user_id=user.id, name=name)
    db.session.add(chat)
    db.session.commit()
    return jsonify({'chat_id': chat.id, 'name': chat.name, 'messages': []}), 201

@app.route('/api/chats/<int:chat_id>/message', methods=['POST'])
def api_add_message(chat_id: int):
    user = current_user()
    if not user or user.role != 'user':
        return jsonify({'error': 'unauthorized'}), 401
    chat = Chat.query.filter_by(id=chat_id, user_id=user.id).first()
    if not chat:
        return jsonify({'error': 'chat not found'}), 404
    data = request.get_json(silent=True) or {}
    sender = data.get('sender')
    text = (data.get('text') or '').strip()
    if sender not in ('user', 'bot') or not text:
        return jsonify({'error': 'invalid message'}), 400
    msg = ChatMessage(chat_id=chat.id, sender=sender, text=text)
    db.session.add(msg)
    db.session.commit()
    return jsonify({'status': 'ok'}), 200

@app.route('/api/chatbot', methods=['POST'])
def api_chatbot_reply():
    user = current_user()
    if not user or user.role != 'user':
        return jsonify({'reply': 'unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    chat_id = data.get('chat_id')
    if not message or not chat_id:
        return jsonify({'reply': 'Message or chat_id missing!'}), 400
    chat = Chat.query.filter_by(id=chat_id, user_id=user.id).first()
    if not chat:
        return jsonify({'reply': 'chat not found'}), 404

    # Plan-aware context and simple intent handling (greetings and plan suggestions)
    now = datetime.utcnow()
    # Current plan
    current_sub = next((s for s in Subscription.query.filter_by(user_id=user.id).all() if s.status == 'active'), None)
    if current_sub:
        cp_quota = 'Unlimited' if (current_sub.plan.quota_gb or 0) == 0 else f"{current_sub.plan.quota_gb}GB"
        current_plan_text = f"{current_sub.plan.name}: ₹{current_sub.plan.price}/mo, {cp_quota}"
    else:
        current_plan_text = "None"
    # Available plans
    plans = Plan.query.filter_by(active=True).all()
    plan_lines = []
    for p in plans:
        quota = 'Unlimited' if (p.quota_gb or 0) == 0 else f"{p.quota_gb}GB"
        plan_lines.append(f"- {p.name}: ₹{p.price}/mo, {quota}")
    # Active discounts
    discounts = Discount.query.filter(
        Discount.active == True,
        Discount.valid_from <= now,
        Discount.valid_until >= now
    ).all()
    discount_lines = []
    for d in discounts:
        val = f"{int(d.discount_value)}%" if d.discount_type == 'percentage' else f"₹{int(d.discount_value)}"
        discount_lines.append(f"- {d.name} ({d.code}): {val}")
    if not discount_lines:
        discount_lines = ["- None"]

    context_text = (
        "Current Plan: " + current_plan_text + "\n" +
        "Available Plans:\n" + "\n".join(plan_lines) + "\n" +
        "Active Discounts:\n" + "\n".join(discount_lines)
    )

    import re
    lower_msg = message.lower()
    handled = False
    reply = None

    # Greeting intent: short greeting response
    if re.search(r'\b(hi|hello|hey|hlo)\b', lower_msg) and len(lower_msg) <= 40:
        reply = "Hello! How can I help you today? Ask me to suggest subscription plans."
        handled = True

    # Suggestion intent: return subscription plan suggestions without external AI
    suggest_intent = re.search(r'\b(suggest|recommend|plan|plans|subscription|offer|offers|upgrade|change plan)\b', lower_msg)
    if not handled and suggest_intent:
        # Build 1–2 concise suggestions from available plans
        plans_sorted = sorted(plans, key=lambda p: p.price)
        suggestions = []
        # If user has a current plan, try to suggest an upgrade and a value option
        if current_sub:
            current_index = next((i for i, p in enumerate(plans_sorted) if p.id == current_sub.plan_id), None)
            next_plan = None
            if current_index is not None and current_index + 1 < len(plans_sorted):
                next_plan = plans_sorted[current_index + 1]
            basic = plans_sorted[0] if plans_sorted else None
            picks = [p for p in [next_plan, basic] if p]
        else:
            # New users: suggest the two most affordable options
            picks = plans_sorted[:2]

        for p in [pp for pp in picks if pp]:
            quota = 'Unlimited' if (p.quota_gb or 0) == 0 else f"{p.quota_gb}GB"
            suggestions.append(f"- {p.name}: ₹{p.price}/mo, {quota}")

        discount_tip = ""
        if discounts:
            d = discounts[0]
            val = f"{int(d.discount_value)}%" if d.discount_type == 'percentage' else f"₹{int(d.discount_value)}"
            discount_tip = f"\nTip: {d.name} ({d.code}) — {val} off."

        if suggestions:
            reply = "Here are my plan suggestions:\n" + "\n".join(suggestions) + discount_tip
            handled = True

    provider = (os.getenv('AI_PROVIDER') or '').lower()

    # If not handled above, fall back to placeholder and optionally provider response
    if not handled:
        reply = (
            "Thanks for your message. Here are some quick tips:\n"
            "- Check your current plan in My Subscriptions.\n"
            "- Visit Offers to apply discounts.\n"
            "- Use Account Settings to update your profile."
        )

    if not handled:
        try:
            if provider == 'openai' and os.getenv('OPENAI_API_KEY'):
                import json, urllib.request, urllib.error
                api_key = os.getenv('OPENAI_API_KEY')
                model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
                system = (
                    "You are a helpful assistant for an internet subscription app. "
                    "Use the provided context to recommend 1–2 plans. "
                    "Be concise and actionable. If a discount applies, mention it."
                )
                user_prompt = (
                    "Context:\n" + context_text + "\n\n" +
                    "User question: " + message + "\n\n" +
                    "Return: 1–2 suggested plan(s) with price, brief reason, and any discount."
                )
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 250,
                }
                req = urllib.request.Request(
                    "https://api.openai.com/v1/chat/completions",
                    data=json.dumps(payload).encode('utf-8'),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data_resp = json.loads(resp.read().decode('utf-8'))
                    reply = (
                        data_resp.get('choices', [{}])[0]
                        .get('message', {})
                        .get('content')
                    ) or reply
            elif provider == 'gemini' and os.getenv('GOOGLE_API_KEY'):
                import json, urllib.request, urllib.error
                api_key = os.getenv('GOOGLE_API_KEY')
                model = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')
                system = (
                    "You are a helpful assistant for an internet subscription app. "
                    "Use the provided context to recommend 1–2 plans. "
                    "Be concise and actionable. If a discount applies, mention it."
                )
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent?key={api_key}"
                )
                user_prompt = (
                    "Context:\n" + context_text + "\n\n" +
                    "User question: " + message + "\n\n" +
                    "Return: 1–2 suggested plan(s) with price, brief reason, and any discount."
                )
                payload = {
                    "contents": [
                        {"parts": [{"text": system}]},
                        {"parts": [{"text": user_prompt}]},
                    ]
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode('utf-8'),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data_resp = json.loads(resp.read().decode('utf-8'))
                    candidates = data_resp.get('candidates') or []
                    if candidates:
                        parts = candidates[0].get('content', {}).get('parts') or []
                        if parts and 'text' in parts[0]:
                            reply = parts[0]['text'] or reply
        except Exception:
            # On any failure, keep placeholder reply
            pass

    # Save both user message (if not already saved by frontend) and bot reply
    user_saved = data.get('user_saved', False)
    if not user_saved:
        db.session.add(ChatMessage(chat_id=chat.id, sender='user', text=message))
    db.session.add(ChatMessage(chat_id=chat.id, sender='bot', text=reply))
    db.session.commit()

    return jsonify({'reply': reply}), 200

@app.route('/api/user/notifications')
def user_notifications():
    user = current_user()
    if not user or user.role != 'user':
        return jsonify({'notifications': []})

    # Only show notifications within N seconds after login
    SHOW_WINDOW_SECONDS = 10  # visible only for a few seconds
    login_at_iso = session.get('login_at')
    if login_at_iso:
        try:
            login_at = datetime.fromisoformat(login_at_iso)
            if (datetime.utcnow() - login_at).total_seconds() > SHOW_WINDOW_SECONDS:
                return jsonify({'notifications': []})
        except Exception:
            pass

    notifications = []

    # Check for expiring subscriptions
    expiring_subs = Subscription.query.filter(
        Subscription.user_id == user.id,
        Subscription.status == 'active',
        Subscription.end_date <= datetime.utcnow() + timedelta(days=7)
    ).all()

    for sub in expiring_subs:
        days_left = (sub.end_date - datetime.utcnow()).days
        notifications.append({
            'type': 'warning',
            'title': 'Subscription Expiring Soon',
            'message': f'Your {sub.plan.name} subscription expires in {days_left} days',
            'action': 'renew',
            'action_url': url_for('renew', sub_id=sub.id)
        })

    # Check for new discounts
    new_discounts = Discount.query.filter(
        Discount.active == True,
        Discount.valid_from >= datetime.utcnow() - timedelta(days=1),
        Discount.valid_until >= datetime.utcnow()
    ).all()

    for discount in new_discounts:
        notifications.append({
            'type': 'info',
            'title': 'New Discount Available',
            'message': f'{discount.name}: {discount.code}',
            'action': 'view',
            'action_url': url_for('user_offers')
        })

    return jsonify({'notifications': notifications})

# Payment Methods Management
@app.route('/user/payment-methods')
def user_payment_methods():
    user = current_user()
    if not user or user.role != 'user':
        return redirect(url_for('login'))
    
    payment_methods = PaymentMethod.query.filter_by(user_id=user.id, is_active=True).all()
    return render_template('user_payment_methods.html', payment_methods=payment_methods)

@app.route('/user/payment-methods/add', methods=['GET', 'POST'])
def add_payment_method():
    user = current_user()
    if not user or user.role != 'user':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        card_type = request.form['card_type']
        is_default = 'is_default' in request.form
        
        # Handle UPI vs Card payment methods
        if card_type == 'upi':
            upi_id = request.form['upi_id']
            # For UPI, use the UPI ID as the identifier
            last_four_digits = upi_id.split('@')[0][-4:] if '@' in upi_id else upi_id[-4:]
            expiry_month = 12  # Default values for UPI
            expiry_year = 2030
        else:
            card_number = request.form['card_number'].replace(' ', '').replace('-', '')
            expiry_month = int(request.form['expiry_month'])
            expiry_year = int(request.form['expiry_year'])
            # Extract last 4 digits
            last_four_digits = card_number[-4:]
        
        # If this is set as default, unset other defaults
        if is_default:
            PaymentMethod.query.filter_by(user_id=user.id, is_default=True).update({'is_default': False})
        
        payment_method = PaymentMethod(
            user_id=user.id,
            card_type=card_type,
            last_four_digits=last_four_digits,
            expiry_month=expiry_month,
            expiry_year=expiry_year,
            is_default=is_default
        )
        
        db.session.add(payment_method)
        db.session.add(AuditLog(actor=user.username, action=f"Added {card_type} payment method ending in {last_four_digits}"))
        db.session.commit()
        
        flash('Payment method added successfully', 'success')
        return redirect(url_for('user_payment_methods'))
    
    return render_template('add_payment_method.html')

@app.route('/user/payment-methods/<int:payment_id>/set-default', methods=['POST'])
def set_default_payment_method(payment_id):
    user = current_user()
    if not user or user.role != 'user':
        return redirect(url_for('login'))
    
    payment_method = PaymentMethod.query.filter_by(id=payment_id, user_id=user.id).first_or_404()
    
    # Unset other defaults
    PaymentMethod.query.filter_by(user_id=user.id, is_default=True).update({'is_default': False})
    
    # Set this as default
    payment_method.is_default = True
    db.session.add(AuditLog(actor=user.username, action=f"Set {payment_method.card_type} ending in {payment_method.last_four_digits} as default payment method"))
    db.session.commit()
    
    flash('Default payment method updated', 'success')
    return redirect(url_for('user_payment_methods'))

@app.route('/user/payment-methods/<int:payment_id>/delete', methods=['POST'])
def delete_payment_method(payment_id):
    user = current_user()
    if not user or user.role != 'user':
        return redirect(url_for('login'))
    
    payment_method = PaymentMethod.query.filter_by(id=payment_id, user_id=user.id).first_or_404()
    
    # Soft delete
    payment_method.is_active = False
    db.session.add(AuditLog(actor=user.username, action=f"Deleted {payment_method.card_type} payment method ending in {payment_method.last_four_digits}"))
    db.session.commit()
    
    flash('Payment method deleted', 'info')
    return redirect(url_for('user_payment_methods'))

# Billing History
@app.route('/user/billing-history')
def user_billing_history():
    user = current_user()
    if not user or user.role != 'user':
        return redirect(url_for('login'))
    
    billing_records = BillingHistory.query.filter_by(user_id=user.id).order_by(BillingHistory.payment_date.desc()).all()
    return render_template('user_billing_history.html', billing_records=billing_records)

# Account Settings
@app.route('/user/account-settings')
def user_account_settings():
    user = current_user()
    if not user or user.role != 'user':
        return redirect(url_for('login'))
    
    return render_template('user_account_settings.html', user=user)

@app.route('/user/account-settings/update', methods=['POST'])
def update_account_settings():
    user = current_user()
    if not user or user.role != 'user':
        return redirect(url_for('login'))
    
    new_username = request.form.get('username', user.username)
    new_password = request.form.get('password', '')
    
    # Check if username is already taken by another user
    if new_username != user.username and User.query.filter_by(username=new_username).first():
        flash('Username already taken', 'danger')
        return redirect(url_for('user_account_settings'))
    
    user.username = new_username
    if new_password:
        user.password = new_password
    
    db.session.add(AuditLog(actor=user.username, action="Updated account settings"))
    db.session.commit()
    
    flash('Account settings updated successfully', 'success')
    return redirect(url_for('user_account_settings'))

if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists('subscriptions.db'):
            db.create_all()
            seed_data()
            print('DB initialized with seed data.')
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
