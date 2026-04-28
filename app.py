from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, session
import psycopg2
import io
import base64
import os

app = Flask(__name__)

# 🔐 SECRET KEY (required for sessions)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")

# Database connection
db = psycopg2.connect(os.environ.get("DATABASE_URL"))

# 🔥 FIX: auto reconnect
def get_db():
    global db
    try:
        if db.closed:
            db = psycopg2.connect(os.environ.get("DATABASE_URL"))
    except:
        db = psycopg2.connect(os.environ.get("DATABASE_URL"))
    return db


# 🔐 LOGIN CHECK DECORATOR
from functools import wraps

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


@app.route('/', methods=['GET' , 'POST'])
def userDashboard():
    return render_template('index.html')


@app.route('/dashboard')
@admin_required
def dashboard():
    return render_template('dashboard.html')


@app.route('/admin_login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            return "Please enter both email and password bro", 404

        cursor = get_db().cursor()
        cursor.execute("SELECT * FROM administrator WHERE email = %s AND password = %s", (email, password))
        user = cursor.fetchone()

        if user:
            session['admin_id'] = user[0]  # ✅ store session
            return redirect(url_for('dashboard'))
        else:
            return "Invalid email or password"

    return render_template('admin-login.html')


# ADD FACULTY
@app.route('/addFaculty', methods=['GET','POST'])
@admin_required
def addFaculty():
    if request.method == 'POST':
        facultyName = request.form.get('facultyName')

        if not facultyName:
            return 'No party Broo'

        cursor = get_db().cursor()
        cursor.execute("INSERT INTO faculty (faculty_name) VALUES (%s)", (facultyName,))
        get_db().commit()

        return 'faculty added succesfully'

    return render_template('addFaculty.html')


@app.route('/addCourse', methods=['GET','POST'])
@admin_required
def addCourse():
    cursor = get_db().cursor()

    cursor.execute("SELECT faculty_id, faculty_name FROM faculty")
    faculties = cursor.fetchall()

    if request.method == "POST":
        course_code = request.form.get('course_code')
        course_name = request.form.get('course_name')
        year_of_study = request.form.get('year_of_study')
        semester = request.form.get('semester')
        faculty_id = request.form.get('faculty_id')

        sql = """INSERT INTO course 
                 (course_code, course_name, year_of_study, semester, faculty_id)
                 VALUES (%s,%s,%s,%s,%s)"""

        cursor.execute(sql,(course_code,course_name,year_of_study,semester,faculty_id))
        get_db().commit()

        return "<script>alert('Course Added Successfully');window.location='/addCourse'</script>"

    return render_template('addCourse.html', faculties=faculties)


@app.route('/addPastPaper', methods=['GET','POST'])
@admin_required
def addPastPaper():
    cursor = get_db().cursor()

    cursor.execute("SELECT faculty_id, faculty_name FROM faculty")
    faculties = cursor.fetchall()

    if request.method == "POST":

        category = request.form.get('category')
        publication_year = request.form.get('publication_year')
        course_id = request.form.get('course_id')

        file = request.files['pdf_file']

        if file and file.filename.endswith('.pdf'):
            pdf_data = file.read()

            if len(pdf_data) > 3 * 1024 * 1024:
                return "<script>alert('File too large. Max 3MB');window.history.back()</script>"

            sql = """INSERT INTO pastpaper
                     (category, publication_year, file, course_id)
                     VALUES (%s,%s,%s,%s)"""

            cursor.execute(sql,(category, publication_year, pdf_data, course_id))
            get_db().commit()

            return "<script>alert('Past Paper Added');window.location='/addPastPaper'</script>"

    return render_template('addPastPaper.html', faculties=faculties)


@app.route('/getCourses/<faculty_id>')
def getCourses(faculty_id):
    cursor = get_db().cursor()
    cursor.execute("SELECT course_id, course_name FROM course WHERE faculty_id=%s",(faculty_id,))
    courses = cursor.fetchall()

    return jsonify(courses)


@app.route('/searchPaper', methods=['GET','POST'])
def searchPaper():
    papers = []

    if request.method == "POST":
        course_code = request.form.get('course_code')

        cursor = get_db().cursor()

        sql = """
        SELECT p.past_paper_id, c.course_code, c.course_name, c.year_of_study, c.semester,
        p.category, p.publication_year
        FROM pastpaper p
        JOIN course c ON p.course_id = c.course_id
        WHERE c.course_code = %s
        """

        cursor.execute(sql,(course_code,))
        papers = cursor.fetchall()

    return render_template("searchPaper.html", papers=papers)


@app.route('/viewPaper/<int:id>')
def viewPaper(id):

    cursor = get_db().cursor()

    cursor.execute("SELECT file FROM pastpaper WHERE past_paper_id=%s",(id,))
    pdf = cursor.fetchone()[0]

    return send_file(
        io.BytesIO(pdf),
        download_name="exam.pdf",
        mimetype="application/pdf"
    )


@app.route('/user/view/<int:id>')
def userView(id):
    return render_template("pdf_viewer.html", paper_id=id)


@app.route('/user/pdf/<int:id>')
def userPdf(id):
    cursor = get_db().cursor()
    cursor.execute("SELECT file FROM pastpaper WHERE past_paper_id=%s", (id,))
    result = cursor.fetchone()

    if not result:
        return "File not found"

    return send_file(
        io.BytesIO(result[0]),
        mimetype='application/pdf'
    )


@app.route('/user/results', methods=['GET'])
def userResults():
    course_code = request.args.get('course_code')
    year = request.args.get('year')

    cursor = get_db().cursor()

    cursor.execute("SELECT course_name FROM course WHERE course_code=%s", (course_code,))
    course = cursor.fetchone()

    course_name = course[0] if course else course_code

    sql = """
    SELECT p.past_paper_id,
           c.course_code,
           c.course_name,
           p.category,
           p.publication_year
    FROM pastpaper p
    JOIN course c ON p.course_id = c.course_id
    WHERE c.course_code = %s
    """

    params = [course_code]

    if year:
        sql += " AND p.publication_year = %s"
        params.append(year)

    sql += " ORDER BY p.past_paper_id DESC"

    cursor.execute(sql, tuple(params))
    papers = cursor.fetchall()

    return render_template(
        'user_results.html',
        papers=papers,
        course_code=course_code,
        course_name=course_name,
        selected_year=year
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
