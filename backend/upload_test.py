import requests, os
base='http://127.0.0.1:5000/api'
root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
file_path = os.path.join(root, 'smoke_note.txt')
print('file exists', os.path.exists(file_path))
# login teacher
lt = requests.post(base + '/auth/login', json={'email':'smoke.teacher@example.com','password':'TeachPass123!'}, headers={'Origin': 'http://127.0.0.1:3005'})
print('teacher login', lt.status_code)
teacher_token = None
if lt.status_code == 200:
    teacher_token = lt.json().get('access_token')
# login student
ls = requests.post(base + '/auth/login', json={'email':'smoke.student@example.com','password':'StudPass123!'}, headers={'Origin': 'http://127.0.0.1:3005'})
print('student login', ls.status_code)
student_token = None
if ls.status_code == 200:
    student_token = ls.json().get('access_token')

if teacher_token:
    files = {'file': open(file_path,'rb')}
    data = {'numQuestions': '2', 'difficulty': 'easy', 'title': 'Smoke Test'}
    headers = {'Origin': 'http://127.0.0.1:3005', 'Authorization': f'Bearer {teacher_token}'}
    r = requests.post(base + '/teacher/materials', files=files, data=data, headers=headers, timeout=120)
    print('upload materials status', r.status_code)
    try:
        print(r.json())
    except Exception:
        print(r.text)
else:
    print('no teacher token')

if student_token:
    files = {'file': open(file_path,'rb')}
    headers = {'Origin': 'http://127.0.0.1:3005', 'Authorization': f'Bearer {student_token}'}
    r = requests.post(base + '/auth/upload-avatar', files=files, headers=headers, timeout=60)
    print('upload avatar status', r.status_code)
    try:
        print(r.json())
    except Exception:
        print(r.text)
else:
    print('no student token')
