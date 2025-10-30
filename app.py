from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps
from datetime import datetime
import bcrypt
import mysql.connector

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this in production

# ---------- DB CONNECTION ----------
def get_db_connection():
    return mysql.connector.connect(
        host='localhost',
        user='root',
        password='root',
        database='quiz_app'
    )

# ---------- LOGIN REQUIRED DECORATOR ----------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'student_id' not in session:
            flash('Please log in to access this page', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ---------- ROUTES ----------
@app.route('/')
def home():
    if 'student_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT * FROM students WHERE username = %s', (username,))
        student = cursor.fetchone()
        conn.close()

        if student and student['password'] == password:
            session['student_id'] = student['id']
            session['student_name'] = student['name']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')

    return render_template('login.html')




@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        name = request.form['name']

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO students (username, password, name) VALUES (%s, %s, %s)',
                           (username, password, name))
            conn.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except mysql.connector.IntegrityError:
            flash('Username already exists', 'danger')
        finally:
            conn.close()

    return render_template('register.html')

# @app.route('/dashboard')
# @login_required
# def dashboard():
#     conn = get_db_connection()
#     cursor = conn.cursor(dictionary=True)
#     cursor.execute('SELECT * FROM quizzes')
#     quizzes = cursor.fetchall()
#     conn.close()
#     return render_template('dashboard.html', quizzes=quizzes)

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch all quizzes
    cursor.execute('SELECT * FROM quizzes')
    quizzes = cursor.fetchall()

    # For each quiz, count its questions
    for quiz in quizzes:
        cursor.execute("SELECT COUNT(*) AS total FROM questions WHERE quiz_id = %s", (quiz['id'],))
        count = cursor.fetchone()['total']
        quiz['total_questions'] = count  # ✅ add total_questions key

    conn.close()

    return render_template('dashboard.html', quizzes=quizzes)


@app.route('/quiz/<int:quiz_id>')
@login_required
def quiz(quiz_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute('SELECT * FROM quizzes WHERE id = %s', (quiz_id,))
    quiz = cursor.fetchone()

    cursor.execute('SELECT * FROM questions WHERE quiz_id = %s', (quiz_id,))
    questions = cursor.fetchall()

    for q in questions:
        for i in range(1, 5):
            key = f'option{i}'
            if key in q and q[key] is None:
                q[key] = ''
                

    conn.close()

    if not quiz:
        flash('Quiz not found', 'danger')
        return redirect(url_for('dashboard'))

    return render_template('quiz.html', quiz=quiz, questions=questions)

@app.route('/submit/<int:quiz_id>', methods=['POST'])
@login_required
def submit_quiz(quiz_id):
    student_id = session['student_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch questions for this quiz
    cursor.execute("SELECT * FROM questions WHERE quiz_id = %s", (quiz_id,))
    questions = cursor.fetchall()

    score = 0
    total = len(questions)
    results_detail = []  # ✅ To store per-question result

    for q in questions:
        selected = request.form.get(f"question_{q['id']}")  # input name must be question ID
        correct = None

        if q['question_type'] == 'mcq':
            correct = q['correct_answer']
        elif q['question_type'] == 'fill_blank':
            correct = q['blanks_answer']
        elif q['question_type'] == 'true_false':
            correct = q['true_false_data']
        elif q['question_type'] == 'coding':
            correct = q['sample_output']

        is_correct = False
        if selected and correct:
            if selected.strip().lower() == str(correct).strip().lower():
                score += 1
                is_correct = True

        results_detail.append({
        "question": q['question_text'],
        "your_answer": selected if selected else "Not Answered",
        "correct_answer": correct if selected else "—",  # ✅ hide correct answer if not answered
        "is_correct": is_correct if selected else None   # None means not attempted
})


    # Save result in scores table
    cursor.execute(
        """
        INSERT INTO scores (student_id, quiz_id, score, total_questions)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE score=%s, total_questions=%s
        """,
        (student_id, quiz_id, score, total, score, total)
    )
    conn.commit()
    conn.close()

    # ✅ Save answers in session for result page
    session['results_detail'] = results_detail

    flash(f'Quiz submitted successfully! You scored {score}/{total}', 'success')
    return redirect(url_for('result', quiz_id=quiz_id))

@app.route('/result/<int:quiz_id>')
@login_required
def result(quiz_id):
    student_id = session['student_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM quizzes WHERE id = %s", (quiz_id,))
    quiz = cursor.fetchone()

    cursor.execute(
        "SELECT score, total_questions FROM scores WHERE student_id = %s AND quiz_id = %s ORDER BY created_at DESC LIMIT 1",
        (student_id, quiz_id)
    )
    result = cursor.fetchone()
    conn.close()

    score = result['score'] if result else 0
    total = result['total_questions'] if result else 0

    # ✅ Get results detail from session
    results_detail = session.pop('results_detail', [])

    return render_template("result.html", quiz=quiz, score=score, total=total, results_detail=results_detail)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ---------- MAIN ----------
if __name__ == '__main__':
    app.run(debug=True)
