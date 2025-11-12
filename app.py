from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, migrate
from models import User, Transaction
from datetime import datetime
from datetime import timedelta
import sqlite3



app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///finance_db.sqlite3'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key'

app.permanent_session_lifetime = timedelta(minutes=15)

db.init_app(app)
migrate.init_app(app, db)



@app.route('/')
def home():
    user = None
    transactions_count = 0

    if 'user_id' in session:
        # Fetch user from database
        user = db.session.get(User, session['user_id'])
        transactions_count = Transaction.query.filter_by(user_id=user.id).count()

    return render_template('home.html', user=user, transactions_count=transactions_count)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Passwords do not match. Please try again.', 'danger')
            return redirect(url_for('register'))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered. Please login.', 'warning')
            return redirect(url_for('login'))

        hashed_password = generate_password_hash(password)
        user = User(name=name, email=email, password=hashed_password)
        db.session.add(user)
        db.session.commit()

        # Log in the new user immediately
        session['user_id'] = user.id
        flash('Registration successful! You are now logged in.', 'success')
        return redirect(url_for('login'))  # redirect to add transaction page

    return render_template('register.html')



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session.permanent = True
            session['user_id'] = user.id
            flash('Login successful!', 'success')

            # Check if user has any transactions
            if len(user.transactions) == 0:
                return redirect(url_for('home'))  # new user → go home to add later
            else:
                return redirect(url_for('dashboard'))  # old user, for now also redirect home

        else:
            flash('Invalid email or password', 'danger')
    return render_template('login.html')

@app.route('/add_transaction', methods=['GET', 'POST'])
def add_transaction():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        # Get form data
        t_type = request.form.get('type', '').strip().lower()  # store in lowercase
        date_str = request.form.get('date', '').strip()
        category = request.form.get('category', '').strip()
        amount_str = request.form.get('amount', '0').strip()
        payment_method = request.form.get('payment_method', '').strip()
        notes = request.form.get('notes', '').strip()

        # Validate amount
        try:
            amount = float(amount_str)
        except ValueError:
            flash('Invalid amount.', 'danger')
            return redirect(url_for('add_transaction'))

        # Validate and convert date
        try:
            transaction_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            flash('Invalid date format.', 'danger')
            return redirect(url_for('add_transaction'))

        # ✅ Ensure user exists before adding transaction
        user = db.session.get(User, session['user_id'])
        if not user:
            flash('User not found.', 'danger')
            return redirect(url_for('login'))

        # ✅ Create new transaction
        new_t = Transaction(
            type=t_type,
            category=category,
            amount=amount,
            payment_method=payment_method,
            note=notes,
            date=transaction_date,
            user_id=session['user_id']
        )

        # ✅ Save to database
        db.session.add(new_t)
        db.session.commit()

        flash('Transaction added successfully!', 'success')
        return redirect(url_for('dashboard'))

    # GET method → show form
    return render_template('add_transaction.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])

    # Filter by date if provided
    filter_date = request.args.get('filter_date')

    # Today's income, expense, balance
    today_income = sum(
        t.amount for t in user.transactions
        if t.type.lower() == 'income' and (not filter_date or t.date.date() == datetime.strptime(filter_date, '%Y-%m-%d').date())
    )
    today_expense = sum(
        t.amount for t in user.transactions
        if t.type.lower() == 'expense' and (not filter_date or t.date.date() == datetime.strptime(filter_date, '%Y-%m-%d').date())
    )
    today_balance = today_income - today_expense

    # Payment method summary
    total_cash = sum(t.amount for t in user.transactions if t.payment_method == 'Cash')
    total_upi = sum(t.amount for t in user.transactions if t.payment_method == 'UPI')
    total_amount = total_cash + total_upi

    # Monthly summary
    current_year = datetime.now().year
    monthly_income = {}
    monthly_expense = {}
    for t in user.transactions:
        if t.date.year == current_year:
            month = t.date.month
            if t.type.lower() == 'income':
                monthly_income[month] = monthly_income.get(month, 0) + t.amount
            elif t.type.lower() == 'expense':
                monthly_expense[month] = monthly_expense.get(month, 0) + t.amount

    # Running balance for all transactions
    transactions = sorted(user.transactions, key=lambda x: x.date)
    balance = 0
    running_balance = []
    for t in transactions:
        if t.type.lower() == 'income':
            balance += t.amount
        else:
            balance -= t.amount
        running_balance.append((t, balance))

    # Recent transactions (latest 5)
    recent_transactions = running_balance[-5:][::-1]

    return render_template(
        'dashboard.html',
        user=user,
        filter_date=filter_date,
        today_income=today_income,
        today_expense=today_expense,
        today_balance=today_balance,
        total_cash=total_cash,
        total_upi=total_upi,
        total_amount=total_amount,
        current_year=current_year,
        monthly_income=monthly_income,
        monthly_expense=monthly_expense,
        running_balance=running_balance,
        recent_transactions=[t for t, _ in recent_transactions]
    )

@app.route('/logout')
def logout():
    session.pop('user_id', None)  # remove the logged-in user
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))

@app.route('/view_transactions')
def view_transactions():
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    user = db.session.get(User, session['user_id'])
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('login'))

    transactions = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.date.desc()).all()

    return render_template('view_transactions.html', transactions=transactions)

@app.route('/edit_transaction/<int:id>', methods=['GET','POST'])
def edit_transaction(id):
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    transaction = Transaction.query.get_or_404(id)

    if request.method == 'POST':
        transaction.type = request.form['type']
        transaction.category = request.form['category']
        transaction.note = request.form['note']
        transaction.amount = float(request.form['amount'])
        db.session.commit()
        flash('Transaction updated successfully!', 'success')
        return redirect(url_for('view_transactions'))

    return render_template('edit_transaction.html', transaction=transaction)


@app.route('/delete_transaction/<int:id>')
def delete_transaction(id):
    if 'user_id' not in session:
        flash('Please log in first.', 'warning')
        return redirect(url_for('login'))

    transaction = Transaction.query.get_or_404(id)
    db.session.delete(transaction)
    db.session.commit()
    flash('Transaction deleted successfully!', 'success')
    return redirect(url_for('view_transactions'))


if __name__ == '__main__':
    app.run(debug=True)
