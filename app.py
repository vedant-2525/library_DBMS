from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
import os
import pymysql
from pymysql.cursors import DictCursor
from datetime import date
from dotenv import load_dotenv
import re

load_dotenv()

# --- Database Config ---
DB_URL = os.getenv('DATABASE_URL', 'mysql://root:root@localhost:3306/librarydb')
m = re.match(r'mysql://(?P<user>[^:]+):(?P<pass>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)/(?P<db>.+)', DB_URL)
if not m: raise RuntimeError("Invalid DATABASE_URL in .env")
cfg = m.groupdict()

# --- INITIALIZE APP (Must happen before @app.route) ---
app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = 'secret_key_for_session'

def get_conn():
    return pymysql.connect(host=cfg['host'], user=cfg['user'], password=cfg['pass'], db=cfg['db'], port=int(cfg['port']), cursorclass=DictCursor, autocommit=False)

# --- ROUTES ---

@app.route('/')
def dashboard():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Stats
            cur.execute("SELECT COUNT(*) as c FROM Book")
            stats = {'total_books': cur.fetchone()['c']}
            cur.execute("SELECT COUNT(*) as c FROM Loan WHERE return_date IS NULL")
            stats['active_loans'] = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) as c FROM Loan WHERE return_date IS NULL AND due_date < CURRENT_DATE()")
            stats['overdue'] = cur.fetchone()['c']

            # Recent Loans
            cur.execute("""
                SELECT l.loan_id, b.title, m.name as borrower, l.due_date, l.return_date, l.fine_amount
                FROM Loan l
                JOIN Member m ON l.member_id = m.member_id
                JOIN BookCopy bc ON l.copy_id = bc.copy_id
                JOIN Book b ON bc.book_id = b.book_id
                ORDER BY l.issue_date DESC LIMIT 5
            """)
            loans = cur.fetchall()
            for l in loans:
                if l['return_date']: l['status'] = 'Returned'
                elif l['due_date'] < date.today(): l['status'] = 'Overdue'
                else: l['status'] = 'Issued'

        return render_template('dashboard.html', stats=stats, recent_loans=loans, page='dashboard')
    finally: conn.close()

@app.route('/loans')
def loans_page():
    filter_type = request.args.get('filter', 'all')
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Base query joining all necessary tables
            query = """
                SELECT l.loan_id, b.title, m.name as borrower, l.issue_date, l.due_date, l.return_date, l.fine_amount
                FROM Loan l
                JOIN Member m ON l.member_id = m.member_id
                JOIN BookCopy bc ON l.copy_id = bc.copy_id
                JOIN Book b ON bc.book_id = b.book_id
            """
            
            # Apply Filter Logic
            if filter_type == 'active':
                query += " WHERE l.return_date IS NULL"
            elif filter_type == 'overdue':
                query += " WHERE l.return_date IS NULL AND l.due_date < CURRENT_DATE()"
            
            query += " ORDER BY l.issue_date DESC"
            
            cur.execute(query)
            loans = cur.fetchall()
            
            # Process Status
            for l in loans:
                if l['return_date']: l['status'] = 'Returned'
                elif l['due_date'] < date.today(): l['status'] = 'Overdue'
                else: l['status'] = 'Issued'
                
        return render_template('loans.html', loans=loans, filter=filter_type, page='loans')
    finally:
        conn.close()

@app.route('/inventory')
def inventory():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Fetch Books
            cur.execute("""
                SELECT b.book_id, b.title, b.isbn, b.year, c.name as category, p.name as publisher,
                (SELECT COUNT(*) FROM BookCopy bc WHERE bc.book_id = b.book_id AND bc.copy_status='available') as available
                FROM Book b
                LEFT JOIN Category c ON b.category_id = c.category_id
                LEFT JOIN Publisher p ON b.publisher_id = p.publisher_id
                ORDER BY b.book_id DESC
            """)
            books = cur.fetchall()
            
            # Fetch Categories & Publishers for the "Add Book" dropdowns
            cur.execute("SELECT * FROM Category")
            categories = cur.fetchall()
            cur.execute("SELECT * FROM Publisher")
            publishers = cur.fetchall()
            
        return render_template('inventory.html', books=books, categories=categories, publishers=publishers, page='inventory')
    finally: conn.close()

@app.route('/members')
def members():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM Member ORDER BY joined_date DESC")
            members = cur.fetchall()
        return render_template('members.html', members=members, page='members')
    finally: conn.close()

# --- ACTIONS ---

@app.route('/add_book', methods=['POST'])
def add_book_form():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Insert Book
            cur.execute("""INSERT INTO Book (title, isbn, publisher_id, category_id, year, total_copies) 
                           VALUES (%s, %s, %s, %s, %s, %s)""",
                        (request.form['title'], request.form['isbn'], request.form['publisher_id'], 
                         request.form['category_id'], request.form['year'], request.form['copies']))
            book_id = cur.lastrowid
            
            # Create Physical Copies
            copies = int(request.form['copies'])
            for _ in range(copies):
                cur.execute("INSERT INTO BookCopy (book_id) VALUES (%s)", (book_id,))
                
            # Handle Author (Simple: Find or Create)
            author_name = request.form['author'].strip()
            cur.execute("SELECT author_id FROM Author WHERE name=%s", (author_name,))
            auth = cur.fetchone()
            if auth:
                author_id = auth['author_id']
            else:
                cur.execute("INSERT INTO Author (name) VALUES (%s)", (author_name,))
                author_id = cur.lastrowid
            
            # Link Book to Author
            cur.execute("INSERT INTO BookAuthor (book_id, author_id) VALUES (%s, %s)", (book_id, author_id))
            
        conn.commit()
        flash("Book added to inventory!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "error")
    finally: conn.close()
    return redirect(url_for('inventory'))

@app.route('/issue_book', methods=['POST'])
def issue_book_form():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT copy_id FROM BookCopy WHERE book_id=%s AND copy_status='available' LIMIT 1", (request.form['book_id'],))
            copy = cur.fetchone()
            if not copy:
                flash("No copies available for this book.", "error")
                return redirect(url_for('dashboard'))
            
            cur.execute("INSERT INTO Loan(member_id, copy_id, issue_date, due_date) VALUES (%s, %s, CURRENT_DATE(), DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY))", 
                        (request.form['member_id'], copy['copy_id']))
        conn.commit()
        flash("Book issued!", "success")
    except Exception as e:
        flash(f"Error: {str(e)}", "error")
    finally: conn.close()
    return redirect(url_for('dashboard'))

@app.route('/return_book', methods=['POST'])
def return_book_form():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Check for fine before returning
            cur.execute("SELECT due_date FROM Loan WHERE loan_id=%s", (request.form['loan_id'],))
            loan = cur.fetchone()
            if not loan: raise Exception("Loan not found")
            
            # Update return date (Trigger calculates fine)
            cur.execute("UPDATE Loan SET return_date=CURRENT_DATE() WHERE loan_id=%s", (request.form['loan_id'],))
            
            # Check fine amount
            cur.execute("SELECT fine_amount FROM Loan WHERE loan_id=%s", (request.form['loan_id'],))
            fine = cur.fetchone()['fine_amount']
            
            msg = "Book returned."
            if fine > 0: msg += f" Fine due: ${fine}"
            
        conn.commit()
        flash(msg, "success" if fine == 0 else "error") # Show red if fine exists
    except Exception as e:
        flash(f"Error: {str(e)}", "error")
    finally: conn.close()
    return redirect(url_for('dashboard'))

@app.route('/add_member', methods=['POST'])
def add_member_form():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO Member(name, email) VALUES (%s, %s)", (request.form['name'], request.form['email']))
        conn.commit()
        flash("Member added!", "success")
    except Exception as e:
        flash(f"Error: {str(e)}", "error")
    finally: conn.close()
    return redirect(url_for('members')) 

@app.route('/api/books')
def search_api():
    conn = get_conn()
    q = request.args.get('q', '') + "%"
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM Book WHERE title LIKE %s OR isbn LIKE %s LIMIT 5", (q, q))
        rows = cur.fetchall()
    conn.close()
    return jsonify(rows)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)