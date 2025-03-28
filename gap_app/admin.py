from django.contrib import admin

from gap_app.models import Activity
from gap_app.models import Equipment
from gap_app.models import Kind


admin.site.register(Kind)
admin.site.register(Equipment)
admin.site.register(Activity)
