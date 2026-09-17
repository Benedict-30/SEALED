import os, sys, traceback
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_project.settings')
import django
django.setup()
from django.template.loader import get_template

out = []
for p in ['brgy/admin/manage_staff.html', 'brgy/admin/edit_staff.html']:
    try:
        html = get_template(p).render({})
        out.append('RENDER_OK | %s | %d bytes' % (p, len(html)))
    except Exception:
        out.append('RENDER_FAIL | %s' % p)
        out.append(traceback.format_exc())
out.append('DONE')
sys.stdout.write('\n'.join(out))
