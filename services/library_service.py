import os
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'xlsx', 'pptx', 'txt'}

def get_library_structure(base_path):
    structure = {}
    if not os.path.exists(base_path):
        return structure
    
    for category in os.listdir(base_path):
        cat_path = os.path.join(base_path, category)
        if os.path.isdir(cat_path):
            files = [f for f in os.listdir(cat_path) if '.' in f]
            structure[category] = files
    return structure

def save_user_upload(file, base_path):
    if file and '.' in file.filename and \
       file.filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS:
        
        filename = secure_filename(file.filename)
        target_dir = os.path.join(base_path, 'User_Uploads')
        
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
            
        file.save(os.path.join(target_dir, filename))
        return True
    return False