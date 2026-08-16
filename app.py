#!/usr/bin/env python3
"""SchoolFlow ERP prototype — zero-dependency SQLite web application."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from http import cookies
from pathlib import Path
from datetime import datetime, date
import csv, hashlib, json, os, secrets, sqlite3

ROOT = Path(__file__).parent
# Vercel functions may only write to /tmp. Local development keeps the database
# beside the app; deployed demos are seeded again when a serverless instance starts.
DB = Path("/tmp/schoolflow.db") if os.environ.get("VERCEL") else ROOT / "schoolflow.db"
SESSIONS = {}

PERMISSIONS = {
  "super_admin": ["*"],
  "school_admin": ["dashboard.view","students.*","academics.*","attendance.*","fees.*","exams.*","staff.*","settings.*","audit.view"],
  "principal": ["dashboard.view","students.view","academics.*","attendance.*","fees.view","exams.*","staff.view","audit.view"],
  "teacher": ["dashboard.view","students.view","attendance.manage","exams.manage"],
  "accountant": ["dashboard.view","students.view","fees.*"],
  "receptionist": ["dashboard.view","students.*","fees.view"],
}

def now(): return datetime.now().isoformat(timespec="seconds")
def password(value): return hashlib.sha256(value.encode()).hexdigest()
def db():
  con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
  con.execute("PRAGMA foreign_keys=ON"); return con
def rows(con, sql, args=()): return [dict(r) for r in con.execute(sql,args).fetchall()]
def one(con, sql, args=()):
  x=con.execute(sql,args).fetchone(); return dict(x) if x else None
def init_db():
  con=db()
  con.executescript('''
  CREATE TABLE IF NOT EXISTS schools(id INTEGER PRIMARY KEY, name TEXT, code TEXT, address TEXT, phone TEXT, email TEXT, academic_year TEXT, active_branch TEXT);
  CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, password TEXT, role TEXT, school_id INTEGER, branch TEXT, active INTEGER DEFAULT 1, created_at TEXT);
  CREATE TABLE IF NOT EXISTS parents(id INTEGER PRIMARY KEY, name TEXT, phone TEXT, email TEXT, relation TEXT, school_id INTEGER, branch TEXT);
  CREATE TABLE IF NOT EXISTS class_sections(id INTEGER PRIMARY KEY, class_name TEXT, section TEXT, class_teacher TEXT, school_id INTEGER, branch TEXT, UNIQUE(class_name,section,school_id,branch));
  CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY, admission_no TEXT UNIQUE, first_name TEXT, last_name TEXT, gender TEXT, dob TEXT, class_name TEXT, section TEXT, parent_id INTEGER, phone TEXT, status TEXT DEFAULT 'Active', school_id INTEGER, branch TEXT, created_at TEXT);
  CREATE TABLE IF NOT EXISTS subjects(id INTEGER PRIMARY KEY, name TEXT, code TEXT, class_name TEXT, school_id INTEGER, branch TEXT);
  CREATE TABLE IF NOT EXISTS staff(id INTEGER PRIMARY KEY, employee_no TEXT UNIQUE, name TEXT, designation TEXT, department TEXT, phone TEXT, email TEXT, school_id INTEGER, branch TEXT, joining_date TEXT, status TEXT DEFAULT 'Active');
  CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY, student_id INTEGER, attendance_date TEXT, status TEXT, marked_by INTEGER, school_id INTEGER, branch TEXT, UNIQUE(student_id,attendance_date));
  CREATE TABLE IF NOT EXISTS fee_invoices(id INTEGER PRIMARY KEY, invoice_no TEXT UNIQUE, student_id INTEGER, fee_type TEXT, amount REAL, due_date TEXT, paid_amount REAL DEFAULT 0, status TEXT DEFAULT 'Unpaid', school_id INTEGER, branch TEXT);
  CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY, receipt_no TEXT UNIQUE, invoice_id INTEGER, student_id INTEGER, amount REAL, payment_mode TEXT, received_at TEXT, received_by INTEGER, school_id INTEGER, branch TEXT);
  CREATE TABLE IF NOT EXISTS exams(id INTEGER PRIMARY KEY, name TEXT, term TEXT, class_name TEXT, starts_on TEXT, school_id INTEGER, branch TEXT);
  CREATE TABLE IF NOT EXISTS marks(id INTEGER PRIMARY KEY, exam_id INTEGER, student_id INTEGER, subject_id INTEGER, max_marks REAL, marks_obtained REAL, remarks TEXT, school_id INTEGER, branch TEXT, UNIQUE(exam_id,student_id,subject_id));
  CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY, occurred_at TEXT, user_name TEXT, action TEXT, entity TEXT, details TEXT, school_id INTEGER, branch TEXT);
  ''')
  if not one(con,"SELECT id FROM schools LIMIT 1"):
    con.execute("INSERT INTO schools VALUES(1,?,?,?,?,?,?,?)",("Greenfield International School","GFIS","12 Knowledge Park, Bengaluru","+91 80 4000 2100","office@greenfield.edu.in","2026–27","Main Campus"))
    users=[("Aarav Mehta","admin@greenfield.edu.in","school_admin"),("Dr. Nisha Rao","principal@greenfield.edu.in","principal"),("Priya Sharma","teacher@greenfield.edu.in","teacher"),("Kavya Singh","accounts@greenfield.edu.in","accountant")]
    for n,e,r in users: con.execute("INSERT INTO users(name,email,password,role,school_id,branch,created_at) VALUES(?,?,?,?,1,'Main Campus',?)",(n,e,password("Demo@123"),r,now()))
    parent_data=[("Rajesh Kumar","+91 98765 12001","rajesh@example.com","Father"),("Meera Iyer","+91 98765 12002","meera@example.com","Mother"),("Sameer Shah","+91 98765 12003","sameer@example.com","Father")]
    for p in parent_data: con.execute("INSERT INTO parents(name,phone,email,relation,school_id,branch) VALUES(?,?,?,?,1,'Main Campus')",p)
    students=[("GF2026001","Aanya","Kumar","Female","2015-04-12","Grade 5","A",1,"+91 98765 12001"),("GF2026002","Vivaan","Iyer","Male","2015-09-28","Grade 5","A",2,"+91 98765 12002"),("GF2026003","Anika","Shah","Female","2014-01-18","Grade 6","B",3,"+91 98765 12003"),("GF2026004","Arjun","Kumar","Male","2016-06-05","Grade 4","A",1,"+91 98765 12001")]
    for s in students: con.execute("INSERT INTO students(admission_no,first_name,last_name,gender,dob,class_name,section,parent_id,phone,school_id,branch,created_at) VALUES(?,?,?,?,?,?,?,?,?,1,'Main Campus',?)",(*s,now()))
    for c in [("Grade 4","A","Priya Sharma"),("Grade 5","A","Priya Sharma"),("Grade 6","B","")]: con.execute("INSERT INTO class_sections(class_name,section,class_teacher,school_id,branch) VALUES(?,?,?,1,'Main Campus')",c)
    for s in [("English","ENG-5","Grade 5"),("Mathematics","MAT-5","Grade 5"),("Science","SCI-5","Grade 5"),("English","ENG-6","Grade 6"),("Mathematics","MAT-6","Grade 6")]: con.execute("INSERT INTO subjects(name,code,class_name,school_id,branch) VALUES(?,?,?,1,'Main Campus')",s)
    for s in [("EMP-001","Priya Sharma","Class Teacher","Academics","+91 99000 10001","teacher@greenfield.edu.in"),("EMP-002","Kavya Singh","Accountant","Finance","+91 99000 10002","accounts@greenfield.edu.in")]: con.execute("INSERT INTO staff(employee_no,name,designation,department,phone,email,school_id,branch,joining_date) VALUES(?,?,?,?,?,?,1,'Main Campus','2024-06-01')",s)
    for sid,amt in [(1,24000),(2,24000),(3,26000),(4,22000)]: con.execute("INSERT INTO fee_invoices(invoice_no,student_id,fee_type,amount,due_date,school_id,branch) VALUES(?,?,?,?,?,1,'Main Campus')",(f"INV-2026-{sid:03d}",sid,"Term 1 Tuition",amt,"2026-09-15"))
    con.execute("INSERT INTO exams(name,term,class_name,starts_on,school_id,branch) VALUES('Mid-Term Assessment','Term 1','Grade 5','2026-09-05',1,'Main Campus')")
    con.commit()
  # Keep upgrades to an existing demo database usable as the schema evolves.
  if not one(con,"SELECT id FROM class_sections LIMIT 1"):
    for c in rows(con,"SELECT DISTINCT class_name,section FROM students WHERE school_id=1 AND branch='Main Campus'"):
      con.execute("INSERT OR IGNORE INTO class_sections(class_name,section,class_teacher,school_id,branch) VALUES(?,?,?,1,'Main Campus')",(c['class_name'],c['section'],''))
    con.commit()
  con.close()

def permitted(user, capability):
  for p in PERMISSIONS.get(user['role'],[]):
    if p=='*' or p==capability or (p.endswith('.*') and capability.startswith(p[:-1])): return True
  return False
def audit(con,user,action,entity,details): con.execute("INSERT INTO audit_logs(occurred_at,user_name,action,entity,details,school_id,branch) VALUES(?,?,?,?,?,?,?)",(now(),user['name'],action,entity,details,user['school_id'],user['branch']))
def scope(user): return (user['school_id'],user['branch'])

class App(SimpleHTTPRequestHandler):
  def log_message(self,*a): pass
  def send_json(self, data, code=200):
    raw=json.dumps(data,default=str).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
  def body(self):
    try: return json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or b'{}')
    except: return {}
  def user(self):
    jar=cookies.SimpleCookie(self.headers.get('Cookie')); token=jar.get('schoolflow_session'); return SESSIONS.get(token.value) if token else None
  def need(self, capability):
    u=self.user()
    if not u: self.send_json({'error':'Sign in required'},401); return None
    if not permitted(u,capability): self.send_json({'error':'You do not have permission for this action'},403); return None
    return u
  def do_GET(self):
    # The deployed client sends every API request to Vercel's single function
    # and places the original route in `_route`; local development uses paths directly.
    parsed = urlparse(self.path)
    forwarded = parse_qs(parsed.query).get('_route', [None])[0]
    if forwarded: self.path = forwarded
    path=urlparse(self.path).path
    if path.startswith('/api/'): return self.api_get(path)
    if path=='/': path='/index.html'
    self.path=path; return super().do_GET()
  def do_POST(self):
    parsed = urlparse(self.path)
    forwarded = parse_qs(parsed.query).get('_route', [None])[0]
    if forwarded: self.path = forwarded
    self.api_post(urlparse(self.path).path)
  def api_get(self,path):
    if path=='/api/me':
      u=self.user(); return self.send_json({'user':{k:u[k] for k in ('id','name','email','role','branch')} if u else None})
    u=self.need('dashboard.view')
    if not u:return
    con=db(); school,branch=scope(u); q=parse_qs(urlparse(self.path).query); search=q.get('q',[''])[0]; page=max(1,int(q.get('page',['1'])[0])); limit=12; offset=(page-1)*limit
    configs={
      '/api/dashboard':('dashboard.view',None),'/api/students':('students.view','students'),'/api/parents':('students.view','parents'),'/api/classes':('academics.view','class_sections'),'/api/subjects':('academics.view','subjects'),'/api/staff':('staff.view','staff'),'/api/invoices':('fees.view','fee_invoices'),'/api/receipts':('fees.view','receipts'),'/api/exams':('exams.view','exams'),'/api/audit':('audit.view','audit_logs'),'/api/settings':('settings.view','schools')}
    if path=='/api/dashboard':
      totals={k:one(con,f"SELECT count(*) n FROM {t} WHERE school_id=? AND branch=?",(school,branch))['n'] for k,t in [('students','students'),('staff','staff'),('invoices','fee_invoices'),('collections','receipts')]}
      totals['due']=one(con,"SELECT COALESCE(sum(amount-paid_amount),0) n FROM fee_invoices WHERE school_id=? AND branch=?",(school,branch))['n']
      return self.send_json({'totals':totals,'recent':rows(con,"SELECT s.first_name||' '||s.last_name student, f.invoice_no,f.amount,f.status FROM fee_invoices f JOIN students s ON s.id=f.student_id WHERE f.school_id=? AND f.branch=? ORDER BY f.id DESC LIMIT 5",(school,branch))})
    if path=='/api/attendance':
      if not permitted(u,'attendance.view') and not permitted(u,'attendance.manage'): return self.send_json({'error':'Permission denied'},403)
      dt=q.get('date',[str(date.today())])[0]; return self.send_json({'date':dt,'items':rows(con,"SELECT s.id student_id,s.admission_no,s.first_name||' '||s.last_name name,s.class_name,s.section,COALESCE(a.status,'Unmarked') status FROM students s LEFT JOIN attendance a ON a.student_id=s.id AND a.attendance_date=? WHERE s.school_id=? AND s.branch=? AND s.status='Active' ORDER BY s.class_name,s.first_name",(dt,school,branch))})
    if path=='/api/results':
      eid=q.get('exam_id',['0'])[0]; return self.send_json({'items':rows(con,"SELECT m.*,s.first_name||' '||s.last_name student,sub.name subject,e.name exam FROM marks m JOIN students s ON s.id=m.student_id JOIN subjects sub ON sub.id=m.subject_id JOIN exams e ON e.id=m.exam_id WHERE m.school_id=? AND m.branch=? AND (?='0' OR m.exam_id=?)",(school,branch,eid,eid))})
    if path=='/api/export/students':
      if not permitted(u,'students.view'): return self.send_json({'error':'Permission denied'},403)
      data=rows(con,"SELECT admission_no,first_name,last_name,class_name,section,phone,status FROM students WHERE school_id=? AND branch=?",(school,branch)); self.send_response(200);self.send_header('Content-Type','text/csv');self.send_header('Content-Disposition','attachment; filename=students.csv');self.end_headers();
      out=['Admission No,First Name,Last Name,Class,Section,Phone,Status']+ [','.join('"'+str(x.get(k,'')).replace('"','""')+'"' for k in ('admission_no','first_name','last_name','class_name','section','phone','status')) for x in data]; self.wfile.write('\n'.join(out).encode()); return
    if path not in configs: return self.send_json({'error':'Not found'},404)
    cap,table=configs[path]
    if not permitted(u,cap): return self.send_json({'error':'Permission denied'},403)
    if table=='schools': return self.send_json({'item':one(con,'SELECT * FROM schools WHERE id=?',(school,))})
    conditions='school_id=? AND branch=?'; args=[school,branch]
    if search:
      columns={'students':'admission_no||first_name||last_name||class_name','parents':'name||phone||email','class_sections':'class_name||section||class_teacher','subjects':'name||code||class_name','staff':'employee_no||name||designation','fee_invoices':'invoice_no||fee_type','receipts':'receipt_no||payment_mode','exams':'name||term','audit_logs':'user_name||action||entity||details'}[table]
      conditions+=f' AND ({columns}) LIKE ?';args.append('%'+search+'%')
    total=one(con,f'SELECT count(*) n FROM {table} WHERE {conditions}',args)['n']
    if table=='students': sql=f"SELECT s.*,p.name parent_name FROM students s LEFT JOIN parents p ON p.id=s.parent_id WHERE {conditions} ORDER BY s.id DESC LIMIT ? OFFSET ?"
    elif table=='fee_invoices': sql=f"SELECT f.*,s.first_name||' '||s.last_name student FROM fee_invoices f JOIN students s ON s.id=f.student_id WHERE {conditions} ORDER BY f.id DESC LIMIT ? OFFSET ?"
    elif table=='receipts': sql=f"SELECT r.*,s.first_name||' '||s.last_name student FROM receipts r JOIN students s ON s.id=r.student_id WHERE {conditions} ORDER BY r.id DESC LIMIT ? OFFSET ?"
    else: sql=f'SELECT * FROM {table} WHERE {conditions} ORDER BY id DESC LIMIT ? OFFSET ?'
    self.send_json({'items':rows(con,sql,args+[limit,offset]),'total':total,'page':page,'pages':max(1,(total+limit-1)//limit)})
  def api_post(self,path):
    if path=='/api/login':
      b=self.body();con=db();u=one(con,'SELECT * FROM users WHERE email=? AND password=? AND active=1',(b.get('email','').lower(),password(b.get('password',''))));con.close()
      if not u:return self.send_json({'error':'Invalid email or password'},401)
      token=secrets.token_urlsafe(32); SESSIONS[token]=u; self.send_response(200);self.send_header('Set-Cookie',f'schoolflow_session={token}; HttpOnly; SameSite=Lax; Path=/');self.send_header('Content-Type','application/json');self.end_headers();return self.wfile.write(json.dumps({'user':{k:u[k] for k in ('name','email','role','branch')}}).encode())
    if path=='/api/logout':
      jar=cookies.SimpleCookie(self.headers.get('Cookie'));t=jar.get('schoolflow_session');
      if t: SESSIONS.pop(t.value,None)
      self.send_json({'ok':True}); return
    action={'/api/students':'students.manage','/api/parents':'students.manage','/api/classes':'academics.manage','/api/subjects':'academics.manage','/api/staff':'staff.manage','/api/attendance':'attendance.manage','/api/invoices':'fees.manage','/api/receipts':'fees.manage','/api/exams':'exams.manage','/api/marks':'exams.manage','/api/settings':'settings.manage'}.get(path)
    u=self.need(action or 'dashboard.view')
    if not u:return
    b=self.body();con=db();school,branch=scope(u)
    try:
      if path=='/api/students':
        required=['admission_no','first_name','class_name','section'];
        if any(not b.get(x) for x in required): raise ValueError('Admission number, first name, class and section are required')
        con.execute("INSERT INTO students(admission_no,first_name,last_name,gender,dob,class_name,section,parent_id,phone,school_id,branch,created_at) VALUES(?,?,?,?,?,?,?,?,?, ?,?,?)",(b['admission_no'],b['first_name'],b.get('last_name',''),b.get('gender',''),b.get('dob',''),b['class_name'],b['section'],b.get('parent_id') or None,b.get('phone',''),school,branch,now())); entity='Student'; detail=b['admission_no']
      elif path=='/api/parents':
        if not b.get('name') or not b.get('phone'): raise ValueError('Parent name and phone are required')
        con.execute("INSERT INTO parents(name,phone,email,relation,school_id,branch) VALUES(?,?,?,?,?,?)",(b['name'],b['phone'],b.get('email',''),b.get('relation','Parent'),school,branch)); entity='Parent'; detail=b['name']
      elif path=='/api/subjects':
        if not all(b.get(x) for x in ('name','code','class_name')): raise ValueError('Subject name, code and class are required')
        con.execute("INSERT INTO subjects(name,code,class_name,school_id,branch) VALUES(?,?,?,?,?)",(b['name'],b['code'],b['class_name'],school,branch));entity='Subject';detail=b['name']
      elif path=='/api/classes':
        if not all(b.get(x) for x in ('class_name','section')): raise ValueError('Class and section are required')
        con.execute("INSERT INTO class_sections(class_name,section,class_teacher,school_id,branch) VALUES(?,?,?,?,?)",(b['class_name'],b['section'],b.get('class_teacher',''),school,branch));entity='Class / section';detail=b['class_name']+' '+b['section']
      elif path=='/api/staff':
        if not all(b.get(x) for x in ('employee_no','name','designation')): raise ValueError('Employee number, name and designation are required')
        con.execute("INSERT INTO staff(employee_no,name,designation,department,phone,email,school_id,branch,joining_date) VALUES(?,?,?,?,?,?,?,?,?)",(b['employee_no'],b['name'],b['designation'],b.get('department',''),b.get('phone',''),b.get('email',''),school,branch,b.get('joining_date',str(date.today()))));entity='Staff';detail=b['name']
      elif path=='/api/attendance':
        if not b.get('date') or not isinstance(b.get('records'),list): raise ValueError('Date and attendance records are required')
        for r in b['records']: con.execute("INSERT INTO attendance(student_id,attendance_date,status,marked_by,school_id,branch) VALUES(?,?,?,?,?,?) ON CONFLICT(student_id,attendance_date) DO UPDATE SET status=excluded.status,marked_by=excluded.marked_by",(r['student_id'],b['date'],r['status'],u['id'],school,branch))
        entity='Attendance';detail=b['date']
      elif path=='/api/invoices':
        if not all(b.get(x) for x in ('student_id','fee_type','amount','due_date')): raise ValueError('Student, fee type, amount and due date are required')
        num=f"INV-{date.today().year}-{int(datetime.now().timestamp())%100000:05d}";con.execute("INSERT INTO fee_invoices(invoice_no,student_id,fee_type,amount,due_date,school_id,branch) VALUES(?,?,?,?,?,?,?)",(num,b['student_id'],b['fee_type'],float(b['amount']),b['due_date'],school,branch));entity='Invoice';detail=num
      elif path=='/api/receipts':
        inv=one(con,"SELECT * FROM fee_invoices WHERE id=? AND school_id=? AND branch=?",(b.get('invoice_id'),school,branch));amount=float(b.get('amount',0))
        if not inv or amount<=0 or amount>inv['amount']-inv['paid_amount']+0.01: raise ValueError('Enter a valid outstanding invoice and amount')
        num=f"RCP-{date.today().year}-{int(datetime.now().timestamp())%100000:05d}";con.execute("INSERT INTO receipts(receipt_no,invoice_id,student_id,amount,payment_mode,received_at,received_by,school_id,branch) VALUES(?,?,?,?,?,?,?,?,?)",(num,inv['id'],inv['student_id'],amount,b.get('payment_mode','Cash'),now(),u['id'],school,branch)); paid=inv['paid_amount']+amount;con.execute("UPDATE fee_invoices SET paid_amount=?,status=? WHERE id=?",(paid,'Paid' if paid>=inv['amount'] else 'Partial',inv['id']));entity='Receipt';detail=num
      elif path=='/api/exams':
        if not all(b.get(x) for x in ('name','term','class_name','starts_on')): raise ValueError('Exam name, term, class and date are required')
        con.execute("INSERT INTO exams(name,term,class_name,starts_on,school_id,branch) VALUES(?,?,?,?,?,?)",(b['name'],b['term'],b['class_name'],b['starts_on'],school,branch));entity='Exam';detail=b['name']
      elif path=='/api/marks':
        if not all(b.get(x) for x in ('exam_id','student_id','subject_id','max_marks')): raise ValueError('Exam, student, subject and maximum marks are required')
        got=float(b.get('marks_obtained',0)); maximum=float(b['max_marks'])
        if got<0 or got>maximum: raise ValueError('Marks must be between zero and the maximum')
        con.execute("INSERT INTO marks(exam_id,student_id,subject_id,max_marks,marks_obtained,remarks,school_id,branch) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(exam_id,student_id,subject_id) DO UPDATE SET max_marks=excluded.max_marks,marks_obtained=excluded.marks_obtained,remarks=excluded.remarks",(b['exam_id'],b['student_id'],b['subject_id'],maximum,got,b.get('remarks',''),school,branch));entity='Marks';detail='Assessment updated'
      elif path=='/api/settings':
        if not all(b.get(x) for x in ('name','academic_year')): raise ValueError('School name and academic year are required')
        con.execute("UPDATE schools SET name=?,address=?,phone=?,email=?,academic_year=? WHERE id=?",(b['name'],b.get('address',''),b.get('phone',''),b.get('email',''),b['academic_year'],school));entity='Settings';detail='School profile updated'
      else: return self.send_json({'error':'Not found'},404)
      audit(con,u,'Created / updated',entity,detail);con.commit();self.send_json({'ok':True})
    except (ValueError,sqlite3.IntegrityError) as e: con.rollback();self.send_json({'error':str(e)},400)
    finally: con.close()

if __name__=='__main__':
  init_db(); port=int(os.environ.get('PORT',8000)); print(f'SchoolFlow running at http://localhost:{port}'); ThreadingHTTPServer(('0.0.0.0',port),App).serve_forever()
